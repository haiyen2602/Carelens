"""V2 stabilization and final validation.

Builds a larger HTTP regression suite for V2 default and a rollback sample for
V1. The suite uses the real FastAPI chat route with deterministic dependency
overrides, seeded pending confirmations for confirmed-drug cases, and fail-
closed new-message cases for ambiguous/nonexistent/multiple-drug queries.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
import unicodedata
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.agents.nodes.drug_confirmation_nodes import STAGE_OUT_RX_CONFIRM_TOP1_R1  # noqa: E402
from backend.agents.tools.drug_confirmation_store import clear_pending_confirmation, set_pending_confirmation  # noqa: E402
from backend.api.chat_deps import ChatServices, get_chat_services  # noqa: E402
from backend.api.security import CurrentUser, get_current_user  # noqa: E402
from backend.config import get_settings  # noqa: E402
from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import AuditLog  # noqa: E402
from backend.main import app  # noqa: E402
from backend.services.drug_knowledge.v2_agent import warm_v2_agent_knowledge_service  # noqa: E402
from backend.services.safety import SafetyFlag  # noqa: E402


DATA_DIR = ROOT / "data pharmacy"
V2_DIR = DATA_DIR / "v2"
OUTPUT_DIR = V2_DIR / "stabilization"
REPORT_PATH = DATA_DIR / "report" / "v2" / "v2-stabilization-report.md"
UNRELATED_EMBEDDING = [random.Random(42).gauss(0, 1) for _ in range(1536)]

TYPE_TO_FIELD = {
    "INDICATION": "cong_dung",
    "ADVERSE_EFFECT": "tac_dung_phu",
    "CONTRAINDICATION": "tac_dung_phu",
    "PRECAUTION": "tac_dung_phu",
    "INTERACTION": "tac_dung_phu",
    "PREGNANCY_LACTATION": "tac_dung_phu",
    "DRIVING_WARNING": "tac_dung_phu",
    "ADMINISTRATION": "cach_dung",
    "GENERAL_DOSAGE": "cach_dung",
    "STORAGE": "bao_quan",
}

QUERY_TEMPLATE = {
    "INDICATION": "{name} có công dụng gì?",
    "ADVERSE_EFFECT": "{name} có tác dụng phụ gì?",
    "CONTRAINDICATION": "{name} chống chỉ định gì?",
    "PRECAUTION": "{name} cần thận trọng gì?",
    "INTERACTION": "{name} có tương tác thuốc không?",
    "PREGNANCY_LACTATION": "{name} phụ nữ mang thai dùng được không?",
    "DRIVING_WARNING": "{name} có ảnh hưởng lái xe không?",
    "ADMINISTRATION": "{name} cách dùng như thế nào?",
    "GENERAL_DOSAGE": "{name} liều dùng thế nào?",
    "STORAGE": "{name} bảo quản thế nào?",
}


async def _safe_safety_check(_utterance: str) -> SafetyFlag:
    return SafetyFlag(
        is_redflag=False,
        matched_group=None,
        matched_keyword=None,
        source="keyword",
        level="Không đáng ngại",
        llm_category=None,
        llm_reasoning=None,
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _strip_diacritics(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


def _override_dependencies() -> None:
    def _generate_answer(_utterance: str, rag_results: list) -> str:
        sources = ", ".join(f"{result.drug_id}:{result.field_group}" for result in rag_results)
        return f"[fake answer grounded on {sources}]"

    app.dependency_overrides[get_chat_services] = lambda: ChatServices(
        classify_intent=lambda _u: ("drug_info", 0.95),
        classify_dose=lambda _u: ("TAKEN", 0.95),
        generate_answer=_generate_answer,
        classify_severity=lambda _combined_text: None,
        embed_query=lambda _text: UNRELATED_EMBEDDING,
        safety_check=_safe_safety_check,
        classify_drug_reply_plausibility=lambda _reply: True,
        select_fuzzy_candidate=lambda _utterance, candidates: candidates[0]["drug_id"] if candidates else None,
        classify_side_effect_match=lambda _utterance, _chunk: False,
    )
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="v2-stabilization-caller",
        role="caregiver",
        patient_id=None,
        doctor_id=None,
    )


def _set_backend(mode: str | None) -> None:
    if mode is None:
        os.environ.pop("DRUG_KNOWLEDGE_BACKEND", None)
    else:
        os.environ["DRUG_KNOWLEDGE_BACKEND"] = mode
    get_settings.cache_clear()


def _latest_audit(patient_id: str) -> AuditLog | None:
    db = SessionLocal()
    try:
        return (
            db.query(AuditLog)
            .filter(AuditLog.patient_id == patient_id)
            .order_by(AuditLog.created_at.desc())
            .first()
        )
    finally:
        db.close()


def build_eval_cases() -> list[dict[str, Any]]:
    products = _read_jsonl(V2_DIR / "drug_product.jsonl")
    knowledge = _read_jsonl(V2_DIR / "drug_knowledge.jsonl")
    product_by_id = {row["id"]: row for row in products}
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_by_type_category: set[tuple[str, str]] = set()
    for row in knowledge:
        knowledge_type = row["knowledge_type"]
        if knowledge_type not in TYPE_TO_FIELD:
            continue
        product = product_by_id[row["drug_product_id"]]
        category = product.get("category") or ""
        key = (knowledge_type, category)
        if key in seen_by_type_category:
            continue
        seen_by_type_category.add(key)
        by_type[knowledge_type].append({**row, "product": product})

    cases: list[dict[str, Any]] = []
    for knowledge_type in TYPE_TO_FIELD:
        for row in _spread_rows(by_type[knowledge_type], 5):
            name = row["product"]["display_name"]
            utterance = QUERY_TEMPLATE[knowledge_type].format(name=name)
            if len(cases) % 5 == 0:
                utterance = _strip_diacritics(utterance)
            cases.append(
                {
                    "id": f"{knowledge_type.lower()}_{len(cases):02d}",
                    "kind": "known",
                    "drug_id": row["legacy_drug_id"],
                    "ten_thuoc": name,
                    "category": row["product"].get("category", ""),
                    "message": utterance,
                    "expected_type": knowledge_type,
                    "expected_field": TYPE_TO_FIELD[knowledge_type],
                    "expected_route": "structured_lookup",
                }
            )

    semantic_seed = [
        ("ketoconazol-2-medipharco-10g", "Ketoconazol 2% Medipharco 10g", "Ketoconazol 2% Medipharco 10g dùng khi bị nấm ngoài da không?"),
        ("tardyferon-b9-3x10", "Tardyferon b9 3x10", "Tôi thiếu sắt thì Tardyferon b9 3x10 liên quan gì?"),
        ("berocca-bayer-10v", "Berocca Bayer 10v", "Berocca Bayer 10v dùng khi mệt mỏi có hợp lý không?"),
        ("agiclovir-5-agimexpharm", "Agiclovir 5% Agimexpharm", "Agiclovir 5% Agimexpharm dùng trong trường hợp da bị gì?"),
        ("procare-diamond-216mg-catalent-30v", "Procare Diamond 216mg Catalent 30v", "Procare Diamond 216mg Catalent 30v hỗ trợ nhóm người nào?"),
        ("cefixim-200mg-cuu-long-2x10", "Cefixim 200mg CỬU LONG 2x10", "Cefixim 200mg Cuu Long 2x10 thường dùng khi nhiễm khuẩn gì?"),
    ]
    for index, (drug_id, name, message) in enumerate(semantic_seed):
        cases.append(
            {
                "id": f"semantic_open_{index:02d}",
                "kind": "known",
                "drug_id": drug_id,
                "ten_thuoc": name,
                "category": "semantic",
                "message": message,
                "expected_type": None,
                "expected_field": None,
                "expected_route": "rag_v2",
            }
        )

    for index, message in enumerate(
        [
            "Cefixim liều dùng?",
            "Vitamin C có tác dụng phụ gì?",
            "Thuốc Không Tồn Tại ABCXYZ có tác dụng phụ gì?",
            "qzxjklmwvbpfgh0000zzzzxxxxyyyywwww9999",
            "Berocca Bayer 10v và Upsa-c 10v thuốc nào có công dụng gì?",
            "Tardyferon b9 3x10 và Procare Diamond 216mg Catalent 30v dùng chung sao?",
            "Panadol Extra Plus Ultra tác dụng phụ gì?",
            "Magne B6 và Berocca liều dùng thế nào?",
        ]
    ):
        cases.append({"id": f"fail_closed_{index:02d}", "kind": "fail_closed", "message": message})
    return cases


def _spread_rows(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if len(rows) <= limit:
        return rows
    sorted_rows = sorted(rows, key=lambda row: (str(row["product"].get("category", "")), row["legacy_drug_id"]))
    step = (len(sorted_rows) - 1) / max(1, limit - 1)
    indexes = []
    for i in range(limit):
        index = round(i * step)
        if index not in indexes:
            indexes.append(index)
    selected = [sorted_rows[index] for index in indexes]
    if len(selected) < limit:
        for row in sorted_rows:
            if row not in selected:
                selected.append(row)
            if len(selected) == limit:
                break
    return selected[:limit]


async def _post_chat(client: AsyncClient, patient_id: str, message: str) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    response = await client.post("/api/v1/chat", json={"patient_id": patient_id, "message": message})
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {"status_code": response.status_code, "body": response.json()}, elapsed_ms


async def _run_known_case(client: AsyncClient, case: dict[str, Any], label: str) -> dict[str, Any]:
    patient_id = f"stabilize-{label}-{case['id']}-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    try:
        set_pending_confirmation(
            db,
            patient_id,
            [{"drug_id": case["drug_id"], "ten_thuoc": case["ten_thuoc"]}],
            STAGE_OUT_RX_CONFIRM_TOP1_R1,
            case["message"],
        )
    finally:
        db.close()
    try:
        response, latency_ms = await _post_chat(client, patient_id, "có")
        audit = _latest_audit(patient_id)
        trace = audit.trace if audit else []
        backend_entries = [entry for entry in trace if entry.get("step") == "drug_knowledge_backend"]
        backend = backend_entries[-1] if backend_entries else {}
        sources = response["body"].get("sources", [])
        actual_types = [backend.get("knowledge_type") or backend.get("v2_knowledge_type")]
        wrong_drug = any(source["drug_id"] != case["drug_id"] for source in sources)
        wrong_type = bool(label == "v2_default" and case["expected_type"] and case["expected_type"] not in actual_types)
        structured_extra_rag = (
            case["expected_route"] == "structured_lookup"
            and backend.get("mode") == "v2"
            and backend.get("path") != "structured_lookup"
        )
        no_result = not sources
        return {
            "label": label,
            "case_id": case["id"],
            "kind": case["kind"],
            "category": case.get("category"),
            "expected_type": case.get("expected_type"),
            "status_code": response["status_code"],
            "sources": sources,
            "backend_trace": backend,
            "wrong_drug": wrong_drug,
            "wrong_type": wrong_type,
            "structured_extra_rag": structured_extra_rag,
            "no_result": no_result,
            "fail_closed": False,
            "latency_ms": latency_ms,
        }
    finally:
        db = SessionLocal()
        try:
            clear_pending_confirmation(db, patient_id)
        finally:
            db.close()


async def _run_fail_closed_case(client: AsyncClient, case: dict[str, Any], label: str) -> dict[str, Any]:
    patient_id = f"stabilize-{label}-{case['id']}-{uuid.uuid4().hex[:8]}"
    response, latency_ms = await _post_chat(client, patient_id, case["message"])
    sources = response["body"].get("sources", [])
    audit = _latest_audit(patient_id)
    trace = audit.trace if audit else []
    backend_entries = [entry for entry in trace if entry.get("step") == "drug_knowledge_backend"]
    return {
        "label": label,
        "case_id": case["id"],
        "kind": case["kind"],
        "category": "fail_closed",
        "expected_type": None,
        "status_code": response["status_code"],
        "sources": sources,
        "backend_trace": backend_entries[-1] if backend_entries else {},
        "wrong_drug": bool(sources),
        "wrong_type": False,
        "structured_extra_rag": False,
        "no_result": not sources,
        "fail_closed": not sources,
        "latency_ms": latency_ms,
    }


def _technical_debt() -> list[str]:
    summary_path = V2_DIR / "import_summary.json"
    review_queue_path = V2_DIR / "knowledge_search" / "new_product_review_queue.jsonl"
    if not summary_path.exists() or not review_queue_path.exists():
        return ["Migration-only technical-debt metadata is not packaged in the runtime image."]

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    new_products = _read_jsonl(review_queue_path)
    debt = [
        f"{summary.get('ingredient_warnings', 0)} ingredient parsing warnings remain RAW_PRESERVED/REVIEW_REQUIRED",
        f"{summary.get('unmapped_heading_total', 0)} unmapped headings remain REVIEW_REQUIRED",
        f"{len(new_products)} NEW_PRODUCT rows remain in review queue",
    ]
    return debt


async def run_stabilization() -> dict[str, Any]:
    if not _db_available():
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "BLOCKED",
            "results": [],
            "open_issues": ["Postgres/database is not available; cannot run HTTP stabilization"],
            "technical_debt": _technical_debt(),
        }

    _set_backend(None)
    default_backend = get_settings().drug_knowledge_backend
    warmup = warm_v2_agent_knowledge_service()
    cases = build_eval_cases()
    _override_dependencies()
    results: list[dict[str, Any]] = []
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://v2-stabilization") as client:
        for case in cases:
            if case["kind"] == "known":
                results.append(await _run_known_case(client, case, "v2_default"))
            else:
                results.append(await _run_fail_closed_case(client, case, "v2_default"))

        _set_backend("v1")
        for case in [c for c in cases if c["kind"] == "known"][:8]:
            results.append(await _run_known_case(client, case, "v1_rollback"))
        for case in [c for c in cases if c["kind"] == "fail_closed"][:3]:
            results.append(await _run_fail_closed_case(client, case, "v1_rollback"))

    app.dependency_overrides.clear()
    default_results = [row for row in results if row["label"] == "v2_default"]
    rollback_results = [row for row in results if row["label"] == "v1_rollback"]
    known_results = [row for row in default_results if row["kind"] == "known"]
    structured_results = [row for row in known_results if row["expected_type"]]
    fail_closed_results = [row for row in default_results if row["kind"] == "fail_closed"]
    wrong_drug = [row for row in default_results if row["wrong_drug"]]
    wrong_type = [row for row in structured_results if row["wrong_type"]]
    errors = [row for row in results if row["status_code"] >= 500]
    structured_extra_rag = [row for row in structured_results if row["structured_extra_rag"]]
    no_result = [row for row in known_results if row["no_result"]]
    rollback_failures = [
        row for row in rollback_results if row["sources"] and row["backend_trace"].get("mode") != "v1"
    ]
    latencies = [row["latency_ms"] for row in default_results]
    technical_debt = _technical_debt()

    p0_p1 = []
    if default_backend != "v2":
        p0_p1.append(f"default backend is {default_backend!r}, expected 'v2'")
    if wrong_drug:
        p0_p1.append(f"{len(wrong_drug)} wrong-drug cases")
    if wrong_type:
        p0_p1.append(f"{len(wrong_type)} wrong-type cases")
    if errors:
        p0_p1.append(f"{len(errors)} HTTP/server errors")
    if structured_extra_rag:
        p0_p1.append(f"{len(structured_extra_rag)} structured cases used RAG unexpectedly")
    if rollback_failures:
        p0_p1.append("V1 rollback backend trace mismatch")

    open_issues = []
    if no_result:
        open_issues.append(f"{len(no_result)} known-drug cases returned no sources")
    if warmup["duration_ms"] > 15000:
        open_issues.append("V2 startup warmup duration is high; monitor staging startup")

    status = "PASS"
    if p0_p1:
        status = "BLOCKED"
    elif open_issues or technical_debt:
        status = "PASS WITH ISSUES"

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "default_backend": default_backend,
        "warmup": warmup,
        "results": results,
        "technical_debt": technical_debt,
        "p0_p1_issues": p0_p1,
        "open_issues": open_issues,
        "metrics": {
            "eval_cases": len(default_results),
            "known_cases": len(known_results),
            "structured_cases": len(structured_results),
            "fail_closed_cases": len(fail_closed_results),
            "v1_rollback_cases": len(rollback_results),
            "wrong_drug": len(wrong_drug),
            "wrong_type": len(wrong_type),
            "fail_closed_rate": sum(1 for row in fail_closed_results if row["fail_closed"]) / max(1, len(fail_closed_results)),
            "structured_extra_rag": len(structured_extra_rag),
            "rag_route_cases": sum(1 for row in known_results if row["backend_trace"].get("path") == "rag_v2"),
            "no_result": len(no_result),
            "errors": len(errors),
            "latency_ms": {
                "p50": percentile(latencies, 50),
                "p95": percentile(latencies, 95),
                "max": max(latencies) if latencies else 0.0,
            },
        },
    }


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((pct / 100) * (len(ordered) - 1))))
    return ordered[index]


def build_report(summary: dict[str, Any]) -> str:
    metrics = summary.get("metrics", {})
    latency = metrics.get("latency_ms", {})
    type_counts = Counter(row["expected_type"] for row in summary["results"] if row["label"] == "v2_default" and row.get("expected_type"))
    category_counts = Counter(row.get("category") for row in summary["results"] if row["label"] == "v2_default" and row.get("category"))
    p0_p1 = "\n".join(f"- {issue}" for issue in summary["p0_p1_issues"]) or "-"
    technical_debt = "\n".join(f"- {item}" for item in summary["technical_debt"]) or "-"
    wrong_drug = "\n".join(f"- {row['case_id']}" for row in summary["results"] if row["label"] == "v2_default" and row["wrong_drug"]) or "-"
    wrong_type = "\n".join(f"- {row['case_id']}" for row in summary["results"] if row["label"] == "v2_default" and row["wrong_type"]) or "-"
    rows = "\n".join(
        f"| {row['label']} | {row['case_id']} | {row['kind']} | {row['status_code']} | {len(row['sources'])} | "
        f"{row['backend_trace'].get('mode', '-')} | {row['backend_trace'].get('path', '-')} | {row['wrong_drug']} | {row['wrong_type']} | {row['latency_ms']:.2f} |"
        for row in summary["results"]
    )
    ready = "YES" if summary["status"] in {"PASS", "PASS WITH ISSUES"} and not summary["p0_p1_issues"] else "NO"
    return f"""# V2 Stabilization Report

**Ngày:** {summary['generated_at']}  
**Scope:** V2 default HTTP stabilization; V1 rollback retained; no V1 deprecation.

## Coverage

- Eval cases: {metrics.get('eval_cases', 0)}
- Known-drug cases: {metrics.get('known_cases', 0)}
- Structured cases: {metrics.get('structured_cases', 0)}
- Fail-closed cases: {metrics.get('fail_closed_cases', 0)}
- V1 rollback sample: {metrics.get('v1_rollback_cases', 0)}
- Knowledge types: {dict(sorted(type_counts.items()))}
- Categories sampled: {dict(sorted(category_counts.items()))}

## HTTP Rows

| Label | Case | Kind | HTTP | Sources | Backend | Route | Wrong Drug | Wrong Type | Latency ms |
|---|---|---|---:|---:|---|---|---:|---:|---:|
{rows}

## V2 STABILIZATION RESULT

```text
STATUS:
{summary['status']}

EVAL CASES:
- {metrics.get('eval_cases', 0)} V2 default HTTP cases
- {metrics.get('v1_rollback_cases', 0)} V1 rollback sample cases

WRONG DRUG:
{wrong_drug}

WRONG TYPE:
{wrong_type}

FAIL CLOSED:
- {metrics.get('fail_closed_rate', 0.0):.2%}

HTTP REGRESSION:
{'PASS' if summary['status'] in {'PASS', 'PASS WITH ISSUES'} else 'FAIL'}

LATENCY:
- p50={latency.get('p50', 0.0):.2f}ms, p95={latency.get('p95', 0.0):.2f}ms, max={latency.get('max', 0.0):.2f}ms

P0/P1 ISSUES:
{p0_p1}

TECHNICAL DEBT:
{technical_debt}

V1 ROLLBACK:
{'PASS' if not any(row['label'] == 'v1_rollback' and row['sources'] and row['backend_trace'].get('mode') != 'v1' for row in summary['results']) else 'FAIL'}

READY TO CONSIDER V1 DEPRECATION:
{ready}
```
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V2 stabilization HTTP validation.")
    parser.parse_args()
    summary = asyncio.run(run_stabilization())
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "v2_stabilization_results.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    REPORT_PATH.write_text(build_report(summary), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": summary["status"],
                "metrics": summary.get("metrics", {}),
                "p0_p1_issues": summary.get("p0_p1_issues", []),
                "open_issues": summary.get("open_issues", []),
                "technical_debt": summary.get("technical_debt", []),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
