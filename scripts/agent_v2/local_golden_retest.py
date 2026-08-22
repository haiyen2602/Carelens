"""BUILD-24J (V2 RC hardening, Phase 2): local, in-process 101-query golden
retest against the REAL orchestrator -- real OpenAI model, real tools, real
RAG, real Safety Domain, real Doctor Handoff, real local Postgres. No
Railway involved at all; this exercises exactly the same wiring
``backend/api/agent_v2_routes.py::run_agent_orchestration`` uses, just
called directly in-process instead of over HTTP, against a local dev
database seeded by ``scripts/agent_v2/seed_staging_agent_v2_data.py``.

Source of the 101 queries: BUILD-24C's own already-fetched golden set
(``data pharmacy/reports/agent-architecture/34-build-24c-golden-set-results.json``)
-- reuses only the query text + expected_* fields (never the old
actual_answer/verdict), so this is not a re-fetch of the Google Sheet, just
a re-run of the same fixed query list against the current code.

Usage::

    PRESCRIPTION_V2_MODE=shadow DOSE_RUNTIME_MODE=shadow \
        python scripts/agent_v2/local_golden_retest.py [--limit N] [--start N]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agents.v2.context import ContextBudget, ContextManager  # noqa: E402
from backend.agents.v2.handoff import DoctorHandoffGateway  # noqa: E402
from backend.agents.v2.model_gateway import OpenAIModelGateway  # noqa: E402
from backend.agents.v2.observability import AgentTelemetry, ModelPricingCatalog  # noqa: E402
from backend.agents.v2.orchestrator import AgentOrchestrator, OrchestrationRequest  # noqa: E402
from backend.agents.v2.retrieval import RetrievalConfig, RetrievalGateway  # noqa: E402
from backend.agents.v2.runtime import AgentRunLimits, ReadOnlyAgentRuntime  # noqa: E402
from backend.agents.v2.safety import SafetyGateway  # noqa: E402
from backend.agents.v2.short_term_memory import ShortTermMemoryStore  # noqa: E402
from backend.agents.v2.tools import AuthorizedToolContext, ToolGateway  # noqa: E402
from backend.agents.v2.vinmec_web import VinmecWebConfig, VinmecWebSearchGateway  # noqa: E402
from backend.config import get_settings  # noqa: E402
from backend.db.base import SessionLocal  # noqa: E402
from backend.services.agent_doctor_handoff import AuthorizedDoctorHandoffAdapter  # noqa: E402
from backend.services.agent_read_only_tools import AgentReadOnlyDomainTools  # noqa: E402
from backend.services.agent_retrieval import AgentRetrievalDomainService  # noqa: E402
from backend.services.agent_safety import SafetyDomainAdapter  # noqa: E402
from backend.services.vinmec_web_search import VinmecWebSearchService  # noqa: E402

GOLDEN_SOURCE = Path(__file__).resolve().parents[2] / "data pharmacy" / "reports" / "agent-architecture" / "34-build-24c-golden-set-results.json"

ACTOR_ID = "agent-v2-staging-patient1-account"
ACTOR_ROLE = "patient"
PATIENT_ID = "agent-v2-staging-patient-1"


class _FakeActor:
    """Mimics CurrentUser -- this harness bypasses the HTTP auth layer
    entirely (already covered by BUILD-16..23's own dedicated authorization
    tests) and calls the orchestrator directly, but Doctor Handoff creation
    still goes through the real ``require_agent_patient_access`` check
    (``AuthorizedDoctorHandoffAdapter.create``), which needs ``patient_id``/
    ``doctor_id`` populated exactly like the real ``CurrentUser`` dataclass
    -- a bare ``id``/``role`` stand-in raises AttributeError there and was
    caught by the orchestrator's own try/except, silently turning every
    handoff-bound query (MISSED/DELAYED_DOSE, DOCTOR_REVIEW,
    ACUTE_DANGER_ESCALATION) into a generic FAILED result. Found and fixed
    before grading -- see report 42's own note on this harness bug."""

    def __init__(self, actor_id: str, role: str, *, patient_id: str | None = None, doctor_id: str | None = None) -> None:
        self.id = actor_id
        self.role = role
        self.patient_id = patient_id
        self.doctor_id = doctor_id


def _run_one(query: dict, *, index: int, total: int) -> dict:
    settings = get_settings()
    db = SessionLocal()
    started = time.monotonic()
    try:
        context_manager = ContextManager(ContextBudget.from_settings(settings))
        model_gateway = OpenAIModelGateway.from_settings(settings)
        telemetry = AgentTelemetry(pricing=ModelPricingCatalog.from_settings(settings))
        orchestrator = AgentOrchestrator(
            runtime=ReadOnlyAgentRuntime(
                model_gateway, limits=AgentRunLimits.from_settings(settings), telemetry=telemetry, model_name=settings.agent_main_model
            ),
            context_manager=context_manager,
            safety_gateway=SafetyGateway.from_settings(SafetyDomainAdapter(db), settings),
            handoff_gateway=DoctorHandoffGateway(
                AuthorizedDoctorHandoffAdapter(db, _FakeActor(ACTOR_ID, ACTOR_ROLE, patient_id=PATIENT_ID))
            ),
            retrieval_gateway=RetrievalGateway(model_gateway, AgentRetrievalDomainService(db), config=RetrievalConfig.from_settings(settings)),
            vinmec_gateway=VinmecWebSearchGateway(VinmecWebSearchService(), config=VinmecWebConfig.from_settings(settings)),
            short_term_memory=ShortTermMemoryStore(context_manager),
            telemetry=telemetry,
        )
        tools = ToolGateway(
            AgentReadOnlyDomainTools(db),
            context=AuthorizedToolContext(actor_id=ACTOR_ID, actor_role=ACTOR_ROLE, patient_id=PATIENT_ID),
        )
        request = OrchestrationRequest(
            message=query["query"],
            actor_id=ACTOR_ID,
            actor_role=ACTOR_ROLE,
            patient_id=PATIENT_ID,
            conversation_id=f"local-golden-retest:{query['query_id']}",
            session_id=str(uuid.uuid4()),
        )
        try:
            result = orchestrator.run(request, tools=tools, checkpoint_db=db)
            db.commit()
            elapsed_ms = round((time.monotonic() - started) * 1000, 1)
            row = {
                "query_id": query["query_id"],
                "query": query["query"],
                "expected_category": query.get("expected_category"),
                "expected_technical_branch": query.get("expected_technical_branch"),
                "expected_difficulty": query.get("expected_difficulty"),
                "expected_safety_level": query.get("expected_safety_level"),
                "expected_criteria": query.get("expected_criteria"),
                "target_patient_id": PATIENT_ID,
                "agent_status": result.status.value,
                "intent": result.intent.value,
                "tools_used": [t.name for t in result.tool_results],
                "safety_disposition": result.safety_decision.outcome.value if result.safety_decision else None,
                "handoff_id": result.handoff_result.request_id if result.handoff_result else None,
                "citations": [{"title": c.title, "source": c.source, "url": c.url} for c in result.citations],
                "latency_ms": elapsed_ms,
                "actual_answer": result.response,
            }
        except Exception as exc:  # noqa: BLE001 -- record and keep going; a single query's exception must not abort the batch
            db.rollback()
            elapsed_ms = round((time.monotonic() - started) * 1000, 1)
            row = {
                "query_id": query["query_id"],
                "query": query["query"],
                "expected_category": query.get("expected_category"),
                "expected_technical_branch": query.get("expected_technical_branch"),
                "expected_difficulty": query.get("expected_difficulty"),
                "expected_safety_level": query.get("expected_safety_level"),
                "expected_criteria": query.get("expected_criteria"),
                "target_patient_id": PATIENT_ID,
                "agent_status": "EXCEPTION",
                "intent": None,
                "tools_used": [],
                "safety_disposition": None,
                "handoff_id": None,
                "citations": [],
                "latency_ms": elapsed_ms,
                "actual_answer": f"{type(exc).__name__}: {exc}",
            }
    finally:
        db.close()
    print(f"[{index}/{total}] id={row['query_id']} status={row['agent_status']} intent={row['intent']} latency={row['latency_ms']}ms", flush=True)
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--ids", type=str, default=None, help="comma-separated query_id list, overrides --start/--limit")
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    with GOLDEN_SOURCE.open(encoding="utf-8") as f:
        source = json.load(f)
    id_filter = {int(x) for x in args.ids.split(",")} if args.ids else None

    def _wanted(query_id: int) -> bool:
        if id_filter is not None:
            return query_id in id_filter
        return query_id >= args.start

    queries = [
        {
            "query_id": row["query_id"],
            "query": row["query"],
            "expected_category": row.get("expected_category"),
            "expected_technical_branch": row.get("expected_technical_branch"),
            "expected_difficulty": row.get("expected_difficulty"),
            "expected_safety_level": row.get("expected_safety_level"),
            "expected_criteria": row.get("expected_criteria"),
        }
        for row in source
        if _wanted(row["query_id"])
    ]
    if args.limit is not None:
        queries = queries[: args.limit]

    results = []
    total = len(queries)
    for i, query in enumerate(queries, start=1):
        results.append(_run_one(query, index=i, total=total))

    out_path = Path(args.out) if args.out else Path(__file__).resolve().parents[2] / "data pharmacy" / "reports" / "agent-architecture" / "42-build-24j-local-golden-results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {len(results)} results to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
