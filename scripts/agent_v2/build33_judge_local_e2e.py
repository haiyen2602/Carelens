"""BUILD-33 section 13/15: real local E2E for the production Judge V2.

Calls ``backend.api.agent_v2_routes.run_agent_orchestration`` directly --
the exact function the real HTTP route uses, just in-process (same pattern
``tests/test_agent_v2_transaction_durability.py`` and BUILD-32's own local
E2E used) -- against real local Postgres, with real OpenAI calls, using the
already-seeded ``agent-v2-staging-patient-1`` canary account.

Scenarios A-D go through the real orchestrator (real chat turn, then a
separate, later step calls the Judge worker -- proving the chat response
never waits on Judge). Scenarios E/F are constructed fixtures (a genuinely
"unsupported" RAG answer and a FAILED/fallback run) -- pushed through the
same real enqueue + real Judge-call + real persistence path without forcing
a real live model into an unreliable failure state. Scenario G deliberately
misconfigures the Judge credential to prove a real provider failure marks
JUDGE_FAILED without touching the chat response already returned in A-D.

Usage (run from repo root, needs a real OPENAI_API_KEY in .env; Judge
provider is forced to "openai"/"gpt-4o" here since no live GOOGLE_API_KEY is
configured in this environment -- see BUILD-33 report section 2/13):

    python scripts/agent_v2/build33_judge_local_e2e.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

os.environ.setdefault("AGENT_RUNTIME_ENABLED", "true")
os.environ["AGENT_JUDGE_ENABLED"] = "true"
os.environ["AGENT_JUDGE_PROVIDER"] = "openai"
os.environ["AGENT_JUDGE_MODEL"] = "gpt-4o"
os.environ["AGENT_JUDGE_SAMPLING_RATE"] = "1.0"  # guarantee every scenario below is Judge-eligible

from backend.agents.v2.evaluation_v2 import EvaluationPath  # noqa: E402
from backend.api.agent_v2_routes import run_agent_orchestration  # noqa: E402
from backend.api.security import CurrentUser  # noqa: E402
from backend.config import get_settings  # noqa: E402
from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import AgentRun, AgentRunEvaluation, AgentRunJudge  # noqa: E402
from backend.models.schemas import AgentV2OrchestrateRequest  # noqa: E402
from backend.services.agent_judge_worker import enqueue_run_judge, process_pending_judge_batch  # noqa: E402

get_settings.cache_clear()

PATIENT_ID = "agent-v2-staging-patient-1"
ACTOR_ID = "agent-v2-staging-patient1-account"


def _actor() -> CurrentUser:
    return CurrentUser(id=ACTOR_ID, role="patient", patient_id=PATIENT_ID, doctor_id=None)


def _run(message: str, conversation_id: str) -> tuple[object, float]:
    db = SessionLocal()
    try:
        request = AgentV2OrchestrateRequest(patient_id=PATIENT_ID, message=message, conversation_id=conversation_id)
        started = time.monotonic()
        response = run_agent_orchestration(request, db=db, actor=_actor())
        elapsed_ms = (time.monotonic() - started) * 1000.0
        return response, elapsed_ms
    finally:
        db.close()


def _judge_row_for_trace(trace_id: str) -> AgentRunJudge | None:
    """Fresh session -- proves this reads real committed rows, not
    in-process state from the call above."""
    db = SessionLocal()
    try:
        from sqlalchemy import select

        return db.execute(select(AgentRunJudge).where(AgentRunJudge.trace_id == trace_id)).scalars().first()
    finally:
        db.close()


def main() -> int:
    print("BUILD-33 local E2E -- real Postgres, real OpenAI, agent-v2-staging-patient-1\n")

    scenarios = [
        ("A-RAG-good", "gan nhiem mo la gi"),
        ("B-PERSONAL_SYMPTOM", "Toi cam thay dau dau"),
        ("C-MEDICATION_DOSE_SAFETY", "Toi co the uong 10 vien vitamin C de tang suc de khang duoc khong?"),
        ("D-SAFETY", "Toi vua non ra mau"),
    ]

    chat_traces: list[tuple[str, str]] = []
    for label, message in scenarios:
        response, elapsed_ms = _run(message, conversation_id=f"build33-e2e-{label}")
        print(f"[{label}] status={response.status} intent={response.intent} chat_latency_ms={elapsed_ms:.0f}")
        chat_traces.append((label, response.trace_id))

    # ---- Scenario E: constructed "RAG unsupported" fixture -----------------
    # A real, grounded live call cannot reliably be coerced into an
    # unsupported answer (BUILD-24F's own grounding enforcement is working
    # as designed) -- this fixture instead pushes a deliberately-hallucinated
    # response + real (but non-supporting) evidence through the SAME real
    # enqueue -> real Judge call -> real persistence path, proving that path
    # end-to-end without faking the Judge call itself.
    from types import SimpleNamespace

    db = SessionLocal()
    try:
        fixture_run_id, fixture_trace_id = "build33-e2e-fixture-rag-unsupported", "build33-e2e-fixture-rag-unsupported-trace"
        db.merge(AgentRun(id=fixture_run_id, status="COMPLETED", started_at=__import__("datetime").datetime.now(__import__("datetime").UTC)))
        db.commit()
        fixture_result = SimpleNamespace(
            agent_run_id=fixture_run_id,
            trace_id=fixture_trace_id,
            intent=SimpleNamespace(value="GENERAL_MEDICAL_INFORMATION"),
            status=SimpleNamespace(value="COMPLETED"),
            response="Panadol la thuoc dieu tri ung thu va co the thay the hoa tri.",
            tool_results=(SimpleNamespace(name="search_drug", data={"name": "Panadol", "cong_dung": "giam dau, ha sot"}),),
            citations=(SimpleNamespace(title="Panadol", source="catalog", url=None),),
            safety_decision=None,
            handoff_result=None,
            error_code=None,
        )
        row = enqueue_run_judge(db, result=fixture_result, request_message="Panadol dung de lam gi?", settings=get_settings(), sample_roll=0.0)
        print(f"[E-RAG-unsupported-fixture] enqueued={row is not None}")
        db.commit()
    finally:
        db.close()

    # ---- Scenario F: constructed FALLBACK fixture --------------------------
    db = SessionLocal()
    try:
        fixture_run_id, fixture_trace_id = "build33-e2e-fixture-fallback", "build33-e2e-fixture-fallback-trace"
        db.merge(AgentRun(id=fixture_run_id, status="FAILED", started_at=__import__("datetime").datetime.now(__import__("datetime").UTC)))
        db.commit()
        fixture_result = SimpleNamespace(
            agent_run_id=fixture_run_id,
            trace_id=fixture_trace_id,
            intent=SimpleNamespace(value="DRUG_INFORMATION"),
            status=SimpleNamespace(value="FAILED"),
            response="Xin loi, toi khong the giup gi ca.",
            tool_results=(),
            citations=(),
            safety_decision=None,
            handoff_result=None,
            error_code="MODEL_ERROR",
        )
        row = enqueue_run_judge(db, result=fixture_result, request_message="Thuoc nay co dung cho ba bau khong?", settings=get_settings(), sample_roll=0.0)
        print(f"[F-FALLBACK-fixture] enqueued={row is not None}")
        db.commit()
    finally:
        db.close()

    chat_traces.append(("E-RAG-unsupported-fixture", "build33-e2e-fixture-rag-unsupported-trace"))
    chat_traces.append(("F-FALLBACK-fixture", "build33-e2e-fixture-fallback-trace"))

    # ---- Process the Judge queue for real -----------------------------------
    print("\nProcessing pending Judge queue (real OpenAI calls)...")
    db = SessionLocal()
    try:
        processed = process_pending_judge_batch(db, settings=get_settings(), limit=20)
        print(f"Processed {processed} row(s).")
    finally:
        db.close()

    print("\nVerifying durable AgentRunJudge rows (fresh DB session per lookup):")
    all_ok = True
    for label, trace_id in chat_traces:
        row = _judge_row_for_trace(trace_id)
        if row is None:
            print(f"[{label}] NO AgentRunJudge ROW FOUND -- unexpected")
            all_ok = False
            continue
        print(
            f"[{label}] judge_status={row.judge_status} rubric={row.rubric_name} "
            f"eligibility={row.eligibility_reason} overall_score={row.overall_score} "
            f"input_tokens={row.input_tokens} output_tokens={row.output_tokens} "
            f"cost_status={row.cost_status} cost_usd={row.cost_usd}"
        )
        if row.judge_status not in ("JUDGE_COMPLETED", "JUDGE_FAILED"):
            all_ok = False

    # ---- Scenario G: real provider failure isolation ------------------------
    print("\n[G-PROVIDER-FAILURE] enqueuing with a deliberately invalid credential...")
    db = SessionLocal()
    try:
        fixture_run_id, fixture_trace_id = "build33-e2e-fixture-bad-credential", "build33-e2e-fixture-bad-credential-trace"
        db.merge(AgentRun(id=fixture_run_id, status="COMPLETED", started_at=__import__("datetime").datetime.now(__import__("datetime").UTC)))
        db.commit()
        db.add(
            AgentRunEvaluation(
                agent_run_id=fixture_run_id, trace_id=fixture_trace_id, evaluation_version="evaluation-v2",
                execution_path="GENERAL_MODEL", metrics_json={},
            )
        )
        db.commit()
        from backend.agents.v2.judge_rubrics import rubric_for_path

        db.add(
            AgentRunJudge(
                agent_run_id=fixture_run_id, trace_id=fixture_trace_id, judge_status="JUDGE_PENDING",
                eligibility_reason="RANDOM_SAMPLE", priority=4, execution_path="GENERAL_MODEL",
                judge_provider="openai", judge_model="gpt-4o",
                judge_config_json={"reasoning_effort": "", "timeout_seconds": 10.0},
                rubric_name=rubric_for_path(EvaluationPath.GENERAL_MODEL).name, rubric_version="rubric-v1",
                judge_prompt_version="judge-v1", evaluation_version="evaluation-v2",
                dimension_scores_json={}, flags_json=[], sanitized_query="q", sanitized_response="a",
                sanitized_context_json={"execution_path": "GENERAL_MODEL", "tool_names": [], "citations": [], "retrieved_evidence": [], "expected_ground_truth": None},
            )
        )
        db.commit()
    finally:
        db.close()

    # Deliberately wrong credential -- process just this one row.
    original_settings = get_settings()
    bad_settings = SimpleNamespace(**{**original_settings.__dict__, "openai_judge_api_key": "sk-deliberately-invalid", "openai_api_key": "sk-deliberately-invalid"})
    db = SessionLocal()
    try:
        processed = process_pending_judge_batch(db, settings=bad_settings, limit=1)
        print(f"Processed {processed} row(s) with a bad credential.")
    finally:
        db.close()

    row = _judge_row_for_trace("build33-e2e-fixture-bad-credential-trace")
    if row is not None and row.judge_status == "JUDGE_FAILED" and row.failure_reason and "AUTH" in row.failure_reason:
        print(f"[G-PROVIDER-FAILURE] JUDGE_FAILED as expected: {row.failure_reason} -- chat scenarios A-D were entirely unaffected (already returned before this ran).")
    else:
        print(f"[G-PROVIDER-FAILURE] UNEXPECTED: {row}")
        all_ok = False

    print(f"\n{'ALL CHECKS OK' if all_ok else 'SOME CHECKS FAILED -- see above'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
