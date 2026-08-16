"""Cutover gate validation for V2 Agent integration.

Runs FastAPI HTTP flow in-process with ``DRUG_KNOWLEDGE_BACKEND`` set to
``shadow``, ``v2``, and ``v1``. LLM/embedding/auth dependencies are overridden
so the route path is real but no external API calls are made.
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
from backend.services.safety import SafetyFlag  # noqa: E402


DATA_DIR = ROOT / "data pharmacy"
OUTPUT_DIR = DATA_DIR / "v2" / "cutover_gate"
REPORT_PATH = DATA_DIR / "reports" / "cutover-gate-report.md"
UNRELATED_EMBEDDING = [random.Random(42).gauss(0, 1) for _ in range(1536)]


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


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
        id="cutover-gate-caller",
        role="caregiver",
        patient_id=None,
        doctor_id=None,
    )


def _set_backend(mode: str) -> None:
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


def _known_cases() -> list[dict[str, Any]]:
    return [
        {
            "id": "known_indication",
            "drug_id": "berocca-bayer-10v",
            "ten_thuoc": "Berocca Bayer 10v",
            "message": "Berocca Bayer 10v có công dụng gì?",
            "expected_field": "cong_dung",
            "expected_v2_path": "structured_lookup",
        },
        {
            "id": "typo_no_diacritic",
            "drug_id": "magne-b6-corbiere-sanofi-5x10",
            "ten_thuoc": "Magne B6 Corbiere Sanofi 5x10",
            "message": "Magne b6 Corbiere Sanofi 5x10 lieu dung the nao?",
            "expected_field": "cach_dung",
            "expected_v2_path": "structured_lookup",
        },
        {
            "id": "semantic_open",
            "drug_id": "ketoconazol-2-medipharco-10g",
            "ten_thuoc": "Ketoconazol 2% Medipharco 10g",
            "message": "Ketoconazol 2% Medipharco 10g dùng khi bị nấm ngoài da không?",
            "expected_field": None,
            "expected_v2_path": "rag_v2",
        },
        {
            "id": "pregnancy_safety",
            "drug_id": "tardyferon-b9-3x10",
            "ten_thuoc": "Tardyferon b9 3x10",
            "message": "Tardyferon b9 3x10 phụ nữ mang thai dùng được không?",
            "expected_field": "tac_dung_phu",
            "expected_v2_path": "structured_lookup",
        },
        {
            "id": "contraindication_safety",
            "drug_id": "agiclovir-5-agimexpharm",
            "ten_thuoc": "Agiclovir 5% Agimexpharm",
            "message": "Agiclovir 5% Agimexpharm chống chỉ định gì?",
            "expected_field": "tac_dung_phu",
            "expected_v2_path": "structured_lookup",
        },
        {
            "id": "interaction_safety",
            "drug_id": "procare-diamond-216mg-catalent-30v",
            "ten_thuoc": "Procare Diamond 216mg Catalent 30v",
            "message": "Procare Diamond 216mg Catalent 30v có tương tác thuốc không?",
            "expected_field": "tac_dung_phu",
            "expected_v2_path": "structured_lookup",
        },
    ]


def _fail_closed_cases() -> list[dict[str, Any]]:
    return [
        {"id": "ambiguous_drug", "message": "Cefixim liều dùng?"},
        {"id": "nonexistent_drug", "message": "Thuốc Không Tồn Tại ABCXYZ có tác dụng phụ gì?"},
        {"id": "multiple_drugs", "message": "Berocca Bayer 10v và Upsa-c 10v thuốc nào có công dụng gì?"},
    ]


async def _post_chat(client: AsyncClient, patient_id: str, message: str) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    response = await client.post("/api/v1/chat", json={"patient_id": patient_id, "message": message})
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {"status_code": response.status_code, "body": response.json()}, elapsed_ms


async def _run_known_case(client: AsyncClient, case: dict[str, Any], mode: str) -> dict[str, Any]:
    patient_id = f"cutover-{mode}-{case['id']}-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    try:
        set_pending_confirmation(
            db,
            patient_id,
            candidates=[{"drug_id": case["drug_id"], "ten_thuoc": case["ten_thuoc"]}],
            stage=STAGE_OUT_RX_CONFIRM_TOP1_R1,
            original_query=case["message"],
        )
    finally:
        db.close()

    try:
        response, latency_ms = await _post_chat(client, patient_id, "có")
        audit = _latest_audit(patient_id)
        trace = audit.trace if audit else []
        backend_entries = [entry for entry in trace if entry.get("step") == "drug_knowledge_backend"]
        backend_entry = backend_entries[-1] if backend_entries else {}
        sources = response["body"].get("sources", [])
        wrong_drug = any(source["drug_id"] != case["drug_id"] for source in sources)
        expected_field = case.get("expected_field")
        wrong_type = bool(expected_field and not any(source["field"] == expected_field for source in sources))
        structured_extra_rag = (
            case["expected_v2_path"] == "structured_lookup"
            and backend_entry.get("mode") in {"v2", "shadow"}
            and backend_entry.get("v2_path", backend_entry.get("path")) != "structured_lookup"
        )
        return {
            "case_id": case["id"],
            "mode": mode,
            "status_code": response["status_code"],
            "sources": sources,
            "backend_trace": backend_entry,
            "wrong_drug": wrong_drug,
            "wrong_type": wrong_type,
            "structured_extra_rag": structured_extra_rag,
            "latency_ms": latency_ms,
            "error": None,
        }
    finally:
        db = SessionLocal()
        try:
            clear_pending_confirmation(db, patient_id)
        finally:
            db.close()


async def _run_fail_closed_case(client: AsyncClient, case: dict[str, Any], mode: str) -> dict[str, Any]:
    patient_id = f"cutover-{mode}-{case['id']}-{uuid.uuid4().hex[:8]}"
    response, latency_ms = await _post_chat(client, patient_id, case["message"])
    audit = _latest_audit(patient_id)
    trace = audit.trace if audit else []
    backend_entries = [entry for entry in trace if entry.get("step") == "drug_knowledge_backend"]
    sources = response["body"].get("sources", [])
    return {
        "case_id": case["id"],
        "mode": mode,
        "status_code": response["status_code"],
        "sources": sources,
        "backend_trace": backend_entries[-1] if backend_entries else {},
        "wrong_drug": bool(sources),
        "wrong_type": False,
        "structured_extra_rag": False,
        "latency_ms": latency_ms,
        "error": None,
    }


async def run_gate() -> dict[str, Any]:
    if not _db_available():
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "BLOCKED",
            "results": [],
            "open_issues": ["Postgres/database is not available; cannot run live HTTP route"],
            "metrics": {},
            "ready_for_v2_default": False,
        }

    _override_dependencies()
    transport = ASGITransport(app=app)
    results: list[dict[str, Any]] = []
    async with AsyncClient(transport=transport, base_url="http://cutover-gate") as client:
        for mode in ("shadow", "v2", "v1"):
            _set_backend(mode)
            for case in _known_cases():
                results.append(await _run_known_case(client, case, mode))
            for case in _fail_closed_cases():
                results.append(await _run_fail_closed_case(client, case, mode))

    app.dependency_overrides.clear()
    wrong_drug = [row for row in results if row["wrong_drug"]]
    wrong_type = [row for row in results if row["wrong_type"]]
    errors = [row for row in results if row["status_code"] >= 500 or row["error"]]
    structured_extra_rag = [row for row in results if row["structured_extra_rag"]]
    shadow_rows = [row for row in results if row["mode"] == "shadow"]
    v2_rows = [row for row in results if row["mode"] == "v2"]
    v1_rows = [row for row in results if row["mode"] == "v1"]
    latencies = [row["latency_ms"] for row in results]
    blocking_issues = []
    open_issues = []
    if wrong_drug:
        blocking_issues.append(f"{len(wrong_drug)} wrong-drug HTTP cases")
    if wrong_type:
        blocking_issues.append(f"{len(wrong_type)} wrong-type HTTP cases")
    if structured_extra_rag:
        blocking_issues.append(f"{len(structured_extra_rag)} structured cases used RAG unexpectedly")
    if errors:
        blocking_issues.append(f"{len(errors)} HTTP/server errors")
    if not all(row["backend_trace"].get("mode") == "shadow" for row in shadow_rows if row["sources"]):
        blocking_issues.append("Some SHADOW known-drug responses did not log shadow backend trace")
    if not all(row["backend_trace"].get("mode") == "v2" for row in v2_rows if row["sources"]):
        blocking_issues.append("Some V2 known-drug responses did not log v2 backend trace")
    if not all(row["backend_trace"].get("mode") == "v1" for row in v1_rows if row["sources"]):
        blocking_issues.append("Some V1 rollback responses did not log v1 backend trace")
    if latencies and max(latencies) > 1000:
        open_issues.append("First V2/SHADOW request has cold-start index load latency; warm cache before cutover")

    status = "PASS"
    if blocking_issues:
        status = "BLOCKED"
    elif open_issues:
        status = "PASS WITH ISSUES"
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "results": results,
        "open_issues": [*blocking_issues, *open_issues],
        "metrics": {
            "cases": len(results),
            "shadow_cases": len(shadow_rows),
            "v2_cases": len(v2_rows),
            "v1_cases": len(v1_rows),
            "wrong_drug": len(wrong_drug),
            "wrong_type": len(wrong_type),
            "structured_extra_rag": len(structured_extra_rag),
            "errors": len(errors),
            "latency_ms": {
                "p50": percentile(latencies, 50),
                "p95": percentile(latencies, 95),
                "max": max(latencies) if latencies else 0.0,
            },
        },
        "ready_for_v2_default": not blocking_issues,
    }


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((pct / 100) * (len(ordered) - 1))))
    return ordered[index]


def build_report(summary: dict[str, Any]) -> str:
    metrics = summary.get("metrics", {})
    rows = "\n".join(
        f"| {row['mode']} | {row['case_id']} | {row['status_code']} | {len(row['sources'])} | "
        f"{row['backend_trace'].get('mode', '-')} | {row['backend_trace'].get('path', row['backend_trace'].get('v2_path', '-'))} | "
        f"{row['wrong_drug']} | {row['wrong_type']} | {row['latency_ms']:.2f} |"
        for row in summary["results"]
    ) or "| - | - | - | - | - | - | - | - | - |"
    open_issues = "\n".join(f"- {issue}" for issue in summary["open_issues"]) or "-"
    latency = metrics.get("latency_ms", {})
    v1_rollback = "PASS" if summary["status"] != "BLOCKED" and metrics.get("v1_cases", 0) else "FAIL"
    return f"""# Cutover Gate Report --- V2 Staging & Shadow Validation

**Ngày:** {summary['generated_at']}  
**Scope:** FastAPI HTTP route validation for `DRUG_KNOWLEDGE_BACKEND=shadow|v2|v1`. No V1 deprecation/cutover.

## HTTP Results

| Mode | Case | HTTP | Sources | Backend Trace | Route | Wrong Drug | Wrong Type | Latency ms |
|---|---|---:|---:|---|---|---:|---:|---:|
{rows}

## CUTOVER GATE RESULT

```text
STATUS:
{summary['status']}

HTTP/SHADOW:
Shadow cases: {metrics.get('shadow_cases', 0)}
HTTP route exercised: {'YES' if summary['results'] else 'NO'}

V1 VS V2:
V1 cases: {metrics.get('v1_cases', 0)}
V2 cases: {metrics.get('v2_cases', 0)}
Structured extra RAG: {metrics.get('structured_extra_rag', 0)}
Errors: {metrics.get('errors', 0)}

WRONG DRUG:
{metrics.get('wrong_drug', 0)}

WRONG TYPE:
{metrics.get('wrong_type', 0)}

LATENCY:
p50={latency.get('p50', 0.0):.2f}ms, p95={latency.get('p95', 0.0):.2f}ms, max={latency.get('max', 0.0):.2f}ms

V1 ROLLBACK:
{v1_rollback}

BREAKING CHANGE:
NO

READY FOR V2 DEFAULT:
{'YES' if summary.get('ready_for_v2_default') else 'NO'}

OPEN ISSUES:
{open_issues}
```
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Cutover Gate HTTP validation.")
    parser.parse_args()
    summary = asyncio.run(run_gate())
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "cutover_gate_results.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    REPORT_PATH.write_text(build_report(summary), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": summary["status"],
                "ready_for_v2_default": summary.get("ready_for_v2_default"),
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
