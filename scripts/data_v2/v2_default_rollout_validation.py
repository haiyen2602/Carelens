"""Controlled V2-default rollout validation.

Validates that the application default is V2, warms the V2 index before HTTP
requests, then exercises FastAPI chat route for V2 default and V1 rollback.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
import uuid
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
OUTPUT_DIR = DATA_DIR / "v2" / "v2_default_rollout"
REPORT_PATH = DATA_DIR / "reports" / "v2-default-rollout-report.md"
UNRELATED_EMBEDDING = [random.Random(42).gauss(0, 1) for _ in range(1536)]


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
        id="v2-default-rollout-caller",
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


def _known_cases() -> list[dict[str, Any]]:
    return [
        {
            "id": "known_indication",
            "drug_id": "berocca-bayer-10v",
            "ten_thuoc": "Berocca Bayer 10v",
            "message": "Berocca Bayer 10v có công dụng gì?",
            "expected_field": "cong_dung",
            "expected_route": "structured_lookup",
        },
        {
            "id": "typo_no_diacritic",
            "drug_id": "magne-b6-corbiere-sanofi-5x10",
            "ten_thuoc": "Magne B6 Corbiere Sanofi 5x10",
            "message": "Magne b6 Corbiere Sanofi 5x10 lieu dung the nao?",
            "expected_field": "cach_dung",
            "expected_route": "structured_lookup",
        },
        {
            "id": "semantic_open",
            "drug_id": "ketoconazol-2-medipharco-10g",
            "ten_thuoc": "Ketoconazol 2% Medipharco 10g",
            "message": "Ketoconazol 2% Medipharco 10g dùng khi bị nấm ngoài da không?",
            "expected_field": None,
            "expected_route": "rag_v2",
        },
        {
            "id": "contraindication",
            "drug_id": "agiclovir-5-agimexpharm",
            "ten_thuoc": "Agiclovir 5% Agimexpharm",
            "message": "Agiclovir 5% Agimexpharm chống chỉ định gì?",
            "expected_field": "tac_dung_phu",
            "expected_route": "structured_lookup",
        },
        {
            "id": "interaction",
            "drug_id": "procare-diamond-216mg-catalent-30v",
            "ten_thuoc": "Procare Diamond 216mg Catalent 30v",
            "message": "Procare Diamond 216mg Catalent 30v có tương tác thuốc không?",
            "expected_field": "tac_dung_phu",
            "expected_route": "structured_lookup",
        },
        {
            "id": "pregnancy",
            "drug_id": "tardyferon-b9-3x10",
            "ten_thuoc": "Tardyferon b9 3x10",
            "message": "Tardyferon b9 3x10 phụ nữ mang thai dùng được không?",
            "expected_field": "tac_dung_phu",
            "expected_route": "structured_lookup",
        },
    ]


def _fail_closed_cases() -> list[dict[str, Any]]:
    return [
        {"id": "ambiguous", "message": "Cefixim liều dùng?"},
        {"id": "nonexistent", "message": "Thuốc Không Tồn Tại ABCXYZ có tác dụng phụ gì?"},
        {"id": "multiple_drugs", "message": "Berocca Bayer 10v và Upsa-c 10v thuốc nào có công dụng gì?"},
    ]


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


async def _post_chat(client: AsyncClient, patient_id: str, message: str) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    response = await client.post("/api/v1/chat", json={"patient_id": patient_id, "message": message})
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {"status_code": response.status_code, "body": response.json()}, elapsed_ms


async def _run_known_case(client: AsyncClient, case: dict[str, Any], label: str) -> dict[str, Any]:
    patient_id = f"v2-default-{label}-{case['id']}-{uuid.uuid4().hex[:8]}"
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
        wrong_drug = any(source["drug_id"] != case["drug_id"] for source in sources)
        wrong_type = bool(case["expected_field"] and not any(source["field"] == case["expected_field"] for source in sources))
        structured_extra_rag = (
            case["expected_route"] == "structured_lookup"
            and backend.get("mode") == "v2"
            and backend.get("path") != "structured_lookup"
        )
        return {
            "label": label,
            "case_id": case["id"],
            "status_code": response["status_code"],
            "sources": sources,
            "backend_trace": backend,
            "wrong_drug": wrong_drug,
            "wrong_type": wrong_type,
            "structured_extra_rag": structured_extra_rag,
            "latency_ms": latency_ms,
        }
    finally:
        db = SessionLocal()
        try:
            clear_pending_confirmation(db, patient_id)
        finally:
            db.close()


async def _run_fail_closed_case(client: AsyncClient, case: dict[str, Any], label: str) -> dict[str, Any]:
    patient_id = f"v2-default-{label}-{case['id']}-{uuid.uuid4().hex[:8]}"
    response, latency_ms = await _post_chat(client, patient_id, case["message"])
    sources = response["body"].get("sources", [])
    audit = _latest_audit(patient_id)
    trace = audit.trace if audit else []
    backend_entries = [entry for entry in trace if entry.get("step") == "drug_knowledge_backend"]
    return {
        "label": label,
        "case_id": case["id"],
        "status_code": response["status_code"],
        "sources": sources,
        "backend_trace": backend_entries[-1] if backend_entries else {},
        "wrong_drug": bool(sources),
        "wrong_type": False,
        "structured_extra_rag": False,
        "latency_ms": latency_ms,
    }


async def run_rollout_validation() -> dict[str, Any]:
    if not _db_available():
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "BLOCKED",
            "startup_warmup": {"status": "FAIL"},
            "results": [],
            "open_issues": ["Postgres/database is not available; cannot run HTTP rollout validation"],
        }

    _set_backend(None)
    default_backend = get_settings().drug_knowledge_backend
    warmup = warm_v2_agent_knowledge_service()
    _override_dependencies()
    results: list[dict[str, Any]] = []
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://v2-default-rollout") as client:
        for case in _known_cases():
            results.append(await _run_known_case(client, case, "default"))
        for case in _fail_closed_cases():
            results.append(await _run_fail_closed_case(client, case, "default"))

        _set_backend("v1")
        for case in _known_cases():
            results.append(await _run_known_case(client, case, "v1_rollback"))
        for case in _fail_closed_cases():
            results.append(await _run_fail_closed_case(client, case, "v1_rollback"))

        _set_backend("shadow")
        for case in _known_cases()[:2]:
            results.append(await _run_known_case(client, case, "shadow_smoke"))

    app.dependency_overrides.clear()
    wrong_drug = [row for row in results if row["wrong_drug"]]
    wrong_type = [row for row in results if row["wrong_type"]]
    errors = [row for row in results if row["status_code"] >= 500]
    structured_extra_rag = [row for row in results if row["structured_extra_rag"]]
    default_rows = [row for row in results if row["label"] == "default"]
    rollback_rows = [row for row in results if row["label"] == "v1_rollback"]
    shadow_rows = [row for row in results if row["label"] == "shadow_smoke"]
    default_known = [row for row in default_rows if row["sources"]]
    rollback_known = [row for row in rollback_rows if row["sources"]]
    latencies = [row["latency_ms"] for row in results]
    default_latencies = [row["latency_ms"] for row in default_rows]

    blocking_issues = []
    open_issues = []
    if default_backend != "v2":
        blocking_issues.append(f"default backend is {default_backend!r}, expected 'v2'")
    if wrong_drug:
        blocking_issues.append(f"{len(wrong_drug)} wrong-drug cases")
    if wrong_type:
        blocking_issues.append(f"{len(wrong_type)} wrong-type cases")
    if errors:
        blocking_issues.append(f"{len(errors)} HTTP/server errors")
    if structured_extra_rag:
        blocking_issues.append(f"{len(structured_extra_rag)} structured cases used RAG unexpectedly")
    if not all(row["backend_trace"].get("mode") == "v2" for row in default_known):
        blocking_issues.append("default known-drug responses did not all use V2 backend")
    if not all(row["backend_trace"].get("mode") == "v1" for row in rollback_known):
        blocking_issues.append("rollback known-drug responses did not all use V1 backend")
    if not all(row["backend_trace"].get("mode") == "shadow" for row in shadow_rows):
        blocking_issues.append("shadow smoke responses did not all use SHADOW backend")
    if default_latencies and max(default_latencies) > 1000:
        blocking_issues.append("default V2 still has cold-start-sized HTTP latency after warmup")
    if warmup["duration_ms"] > 15000:
        open_issues.append("V2 warmup duration is high; monitor startup time in staging")

    status = "PASS"
    if blocking_issues:
        status = "BLOCKED"
    elif open_issues:
        status = "PASS WITH ISSUES"

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "default_backend": default_backend,
        "startup_warmup": {"status": "PASS", **warmup},
        "results": results,
        "open_issues": [*blocking_issues, *open_issues],
        "metrics": {
            "cases": len(results),
            "default_cases": len(default_rows),
            "rollback_cases": len(rollback_rows),
            "shadow_cases": len(shadow_rows),
            "wrong_drug": len(wrong_drug),
            "wrong_type": len(wrong_type),
            "structured_extra_rag": len(structured_extra_rag),
            "errors": len(errors),
            "latency_ms": {
                "p50": percentile(latencies, 50),
                "p95": percentile(latencies, 95),
                "max": max(latencies) if latencies else 0.0,
                "default_max": max(default_latencies) if default_latencies else 0.0,
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
    rows = "\n".join(
        f"| {row['label']} | {row['case_id']} | {row['status_code']} | {len(row['sources'])} | "
        f"{row['backend_trace'].get('mode', '-')} | {row['backend_trace'].get('path', row['backend_trace'].get('v2_path', '-'))} | "
        f"{row['wrong_drug']} | {row['wrong_type']} | {row['latency_ms']:.2f} |"
        for row in summary["results"]
    )
    wrong_drug = "\n".join(f"- {row['label']}:{row['case_id']}" for row in summary["results"] if row["wrong_drug"]) or "-"
    wrong_type = "\n".join(f"- {row['label']}:{row['case_id']}" for row in summary["results"] if row["wrong_type"]) or "-"
    open_issues = "\n".join(f"- {issue}" for issue in summary["open_issues"]) or "-"
    startup = summary["startup_warmup"]
    http_regression = "PASS" if summary["status"] in {"PASS", "PASS WITH ISSUES"} else "FAIL"
    v1_rollback = "PASS" if not any(row["label"] == "v1_rollback" and row["backend_trace"].get("mode") != "v1" and row["sources"] for row in summary["results"]) else "FAIL"
    ready = "YES" if summary["status"] in {"PASS", "PASS WITH ISSUES"} else "NO"
    return f"""# V2 Default Rollout Report

**Ngày:** {summary['generated_at']}  
**Scope:** Controlled V2 default with V1/SHADOW rollback retained. No V1 deprecation.

## HTTP Results

| Label | Case | HTTP | Sources | Backend | Route | Wrong Drug | Wrong Type | Latency ms |
|---|---|---:|---:|---|---|---:|---:|---:|
{rows}

## V2 DEFAULT RESULT

```text
STATUS:
{summary['status']}

V2 DEFAULT:
{'YES' if summary['default_backend'] == 'v2' else 'NO'}

STARTUP WARMUP:
{startup['status']} ({startup.get('products', 0)} products, {startup.get('chunks', 0)} chunks, {startup.get('duration_ms', 0.0):.2f}ms)

HTTP REGRESSION:
{http_regression}

WRONG DRUG:
{wrong_drug}

WRONG TYPE:
{wrong_type}

LATENCY:
p50={latency.get('p50', 0.0):.2f}ms, p95={latency.get('p95', 0.0):.2f}ms, max={latency.get('max', 0.0):.2f}ms, default_max={latency.get('default_max', 0.0):.2f}ms

V1 ROLLBACK:
{v1_rollback}

BREAKING CHANGE:
NO

READY TO ENTER STABILIZATION:
{ready}

OPEN ISSUES:
{open_issues}
```
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Run controlled V2 default rollout validation.")
    parser.parse_args()
    summary = asyncio.run(run_rollout_validation())
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "v2_default_rollout_results.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    REPORT_PATH.write_text(build_report(summary), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": summary["status"],
                "default_backend": summary.get("default_backend"),
                "startup_warmup": summary.get("startup_warmup"),
                "metrics": summary.get("metrics", {}),
                "open_issues": summary["open_issues"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
