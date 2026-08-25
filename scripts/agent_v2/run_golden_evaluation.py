"""BUILD-35: Golden Set & Continuous Evaluation -- real Agent V2 runner
(I/O layer).

Calls the SAME public entry points a real request uses --
``backend.api.agent_v2_routes.run_agent_orchestration`` and
``get_trace_activity`` -- directly (same pattern BUILD-32/33/34's own local
E2E scripts and ``tests/test_agent_v2_transaction_durability.py`` use), so a
golden run exercises the identical code path production traffic does, never
a parallel test-only shortcut. Grading/regression logic itself lives in
``backend.agents.v2.golden_evaluation`` (pure, no I/O) -- this file's only
job is: load dataset -> run each case for real -> extract a ``CaseOutcome``
from the real response plus durable BUILD-32/33/34 tables -> grade -> compare
to an optional baseline -> evaluate the regression gate -> write JSON +
Markdown artifacts -> exit with a code CI can act on.

Usage:

    # full real run, default dataset, no Judge, no baseline
    python scripts/agent_v2/run_golden_evaluation.py

    # CI-safe subset only: zero-model-call categories, no paid credentials,
    # no live RAG/model variance (see _DETERMINISTIC_CATEGORIES below)
    python scripts/agent_v2/run_golden_evaluation.py --deterministic-only

    # opt into real Judge scoring for this run (needs AGENT_JUDGE_* creds)
    python scripts/agent_v2/run_golden_evaluation.py --with-judge

    # compare against a prior run's saved JSON artifact
    python scripts/agent_v2/run_golden_evaluation.py --baseline scripts/agent_v2/golden/runs/2026-08-20T120000Z.json

Producing an origin/main baseline artifact: this script deliberately never
performs git operations itself (a runner silently checking out a different
ref mid-run is exactly the kind of "risky implicit behavior" this project's
own standing rules warn against). Instead, reuse the git-worktree technique
already proven throughout BUILD-33/34's own review-response work: create a
disposable worktree of ``origin/main``, run this same script there against
the same dataset file, and pass its output JSON path as ``--baseline`` here.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import select  # noqa: E402

from backend.agents.v2.evaluation_v2 import EvaluationPath  # noqa: E402
from backend.agents.v2.golden_evaluation import (  # noqa: E402
    CaseOutcome,
    CaseResult,
    DatasetValidationError,
    GoldenCase,
    GoldenCategory,
    RegressionGateResult,
    RunProvenance,
    aggregate_results,
    compare_to_baseline,
    evaluate_regression_gate,
    grade_case,
    load_golden_set,
    validate_golden_set,
)
from backend.api.agent_v2_routes import get_trace_activity, run_agent_orchestration  # noqa: E402
from backend.api.security import CurrentUser  # noqa: E402
from backend.config import get_settings  # noqa: E402
from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import AgentRun, AgentRunEvaluation, AgentRunJudge, AgentSafetyEvent  # noqa: E402
from backend.models.schemas import AgentV2OrchestrateRequest  # noqa: E402
from backend.services.agent_conversation_state import AgentConversationStateStore  # noqa: E402
from backend.services.agent_judge_worker import enqueue_golden_judge, process_pending_judge_batch  # noqa: E402

DEFAULT_DATASET_DIR = Path(__file__).resolve().parent / "golden"
DEFAULT_RUNS_DIR = DEFAULT_DATASET_DIR / "runs"

# The already-seeded canary account BUILD-32/33/34's own local E2E work
# reuses throughout (scripts/agent_v2/seed_staging_agent_v2_data.py) --
# never a fresh/synthetic patient created ad hoc by this script.
DEFAULT_PATIENT_ID = "agent-v2-staging-patient-1"
DEFAULT_ACTOR_ID = "agent-v2-staging-patient1-account"
# Deliberately unlinked from DEFAULT_ACTOR_ID's caregiver relationship (see
# that same seed script) -- the real "a different patient" identity
# GOLD-AUTH-001 needs, not a synthetic id with no seeded row at all.
CROSS_PATIENT_ID = "agent-v2-staging-patient-2"
CROSS_PATIENT_ACTOR_ID = "agent-v2-staging-patient2-crossaccess-probe"

# Categories whose real grading contract asserts `model_calls == 0`
# (backend.agents.v2.golden_evaluation._grade_schedule/_grade_triage_or_
# dose_safety) or otherwise structurally never reaches the model gateway
# (SAFETY escalation is keyword-triggered; OUT_OF_SCOPE and AUTH_ISOLATION
# never call the model at all) -- safe to run in CI with a fake
# OPENAI_API_KEY and no live RAG/model variance. RAG/DRUG_*/MULTI_TURN/
# FALLBACK all render their final answer through the real main model and are
# excluded here, not because they are non-deterministic in outcome, but
# because this build's own CI-integration constraint (BUILD-35 spec) is "no
# dependency on paid model credentials," which is a credential/cost property,
# not a correctness one.
_DETERMINISTIC_CATEGORIES = frozenset(
    {
        GoldenCategory.SCHEDULE_PAST,
        GoldenCategory.SCHEDULE_TODAY,
        GoldenCategory.SCHEDULE_FUTURE,
        GoldenCategory.PERSONAL_SYMPTOM,
        GoldenCategory.MEDICATION_DOSE_SAFETY,
        GoldenCategory.POSSIBLE_OVERDOSE,
        GoldenCategory.ACUTE_DANGER,
        GoldenCategory.OUT_OF_SCOPE,
        GoldenCategory.AUTH_ISOLATION,
    }
)


def _resolve_dataset_path(dataset_arg: str) -> Path:
    """Accepts either a literal path (contains a path separator or ends
    `.json`) or a bare version string (`v1` -> `golden/golden_set_v1.json`)
    -- the CLI shape the spec asks for (`--dataset <version>`) without this
    script performing any hidden filesystem convention magic beyond this one
    documented rule."""

    if "/" in dataset_arg or "\\" in dataset_arg or dataset_arg.endswith(".json"):
        return Path(dataset_arg)
    return DEFAULT_DATASET_DIR / f"golden_set_{dataset_arg}.json"


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=True, cwd=Path(__file__).resolve().parents[2]
        )
        return result.stdout.strip()
    except Exception:  # noqa: BLE001 -- provenance is best-effort metadata, never blocks a run
        return "UNKNOWN"


def _optional_str_setting(settings: Any, name: str) -> str | None:
    """Genuinely missing/empty -> None, never the string `"None"`. A naive
    `str(getattr(settings, name, "") or None)` stringifies the fallback
    itself (`str(None) == "None"`, which is truthy) before the final `or
    None` ever runs, so it silently returns the literal text "None" instead
    of the real value None -- exactly the kind of state-collapse bug this
    project's own principles warn against elsewhere (see agent_judge_worker.
    _float_setting's docstring for the same class of defect with 0 vs
    None)."""

    value = getattr(settings, name, None)
    return str(value) if value else None


def _build_provenance(*, settings: Any, golden_set_version: str, started_at: datetime) -> RunProvenance:
    return RunProvenance(
        git_commit=_git_commit(),
        # This codebase has no separate per-deploy semantic version for the
        # Agent V2 pipeline itself (confirmed by audit: no APP_VERSION/
        # AGENT_VERSION setting exists anywhere in backend/config.py) --
        # `git_commit` above is the field that actually pins reproducibility;
        # these two are fixed pipeline-name constants, not fabricated
        # version numbers.
        agent_version="agent-v2",
        chatbot_version="agent-v2",
        # The only real, already-versioned prompt in this codebase (BUILD-31)
        # -- covers the RAG answer prompt specifically, not a separate
        # agent-wide system prompt version (none exists).
        prompt_version=str(getattr(settings, "rag_prompt_version", "") or "NOT_AVAILABLE"),
        router_model=str(getattr(settings, "agent_router_model", "") or "NOT_AVAILABLE"),
        main_model=str(getattr(settings, "agent_main_model", "") or "NOT_AVAILABLE"),
        fallback_model=str(getattr(settings, "agent_fallback_model", "") or "NOT_AVAILABLE"),
        embedding_model=str(getattr(settings, "agent_embedding_model", "") or "NOT_AVAILABLE"),
        retrieval_version=str(getattr(settings, "rag_retriever_version", "") or "NOT_AVAILABLE"),
        judge_model=_optional_str_setting(settings, "agent_judge_model"),
        rubric_version=_optional_str_setting(settings, "agent_judge_rubric_version"),
        evaluation_version="evaluation-v2",
        golden_set_version=golden_set_version,
        started_at=started_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# Real Agent V2 calls
# ---------------------------------------------------------------------------


def _actor(patient_id: str, actor_id: str) -> CurrentUser:
    return CurrentUser(id=actor_id, role="patient", patient_id=patient_id, doctor_id=None)


def _run_turn(message: str, *, patient_id: str, actor_id: str, conversation_id: str):
    """One real orchestration call, own session -- same shape as
    scripts/agent_v2/build34_safety_monitoring_local_e2e.py's own `_run`."""

    db = SessionLocal()
    try:
        request = AgentV2OrchestrateRequest(patient_id=patient_id, message=message, conversation_id=conversation_id)
        return run_agent_orchestration(request, db=db, actor=_actor(patient_id, actor_id))
    finally:
        db.close()


def _durable_facts(agent_run_id: str) -> dict[str, Any]:
    """Fresh session, deliberately separate from the write above -- a real
    restart-durability proxy (same reasoning as BUILD-34's own
    `_safety_event_for_trace`): this reads a real committed row, never
    in-process state carried over from `_run_turn`."""

    db = SessionLocal()
    try:
        run = db.get(AgentRun, agent_run_id)
        evaluation = (
            db.execute(select(AgentRunEvaluation).where(AgentRunEvaluation.agent_run_id == agent_run_id))
            .scalars()
            .first()
        )
        safety = (
            db.execute(select(AgentSafetyEvent).where(AgentSafetyEvent.agent_run_id == agent_run_id)).scalars().first()
        )
        return {
            "model_calls": int(run.model_calls) if run else 0,
            "error_code": run.error_code if run else None,
            "execution_path": evaluation.execution_path if evaluation else None,
            "evaluation_version": evaluation.evaluation_version if evaluation else None,
            "safety_outcome": safety.outcome if safety else None,
            "safety_reason_code": safety.reason_code if safety else None,
            "safety_severity": safety.severity if safety else None,
            "handoff_required": bool(safety.handoff_required) if safety else False,
            "handoff_created": bool(safety.handoff_created) if safety else False,
        }
    finally:
        db.close()


def _conversation_state_facts(*, actor_id: str, patient_id: str, conversation_id: str) -> dict[str, Any]:
    db = SessionLocal()
    try:
        state = AgentConversationStateStore().load(db, actor_id=actor_id, patient_id=patient_id, conversation_id=conversation_id)
        return {
            "active_topic": state.active_topic.canonical_name if state.active_topic else None,
            "active_entity": state.active_entity.canonical_name if state.active_entity else None,
            "requested_aspect": state.requested_aspect,
        }
    finally:
        db.close()


def _maybe_enqueue_golden_judge(*, response: Any, turn_query: str, durable: dict[str, Any], settings: Any) -> None:
    db = SessionLocal()
    try:
        raw_path = durable.get("execution_path")
        try:
            execution_path = EvaluationPath(raw_path) if raw_path else None
        except ValueError:
            execution_path = None
        enqueue_golden_judge(
            db,
            agent_run_id=response.agent_run_id,
            trace_id=response.trace_id,
            query=turn_query,
            response_text=response.reply,
            execution_path=execution_path,
            tool_names=tuple(response.tools),
            citation_titles=tuple(c.title for c in response.citations),
            evaluation_version=durable.get("evaluation_version"),
            settings=settings,
        )
    finally:
        db.close()


def _judge_facts(agent_run_id: str) -> dict[str, Any]:
    db = SessionLocal()
    try:
        row = (
            db.execute(
                select(AgentRunJudge)
                .where(AgentRunJudge.agent_run_id == agent_run_id)
                .order_by(AgentRunJudge.created_at.desc())
            )
            .scalars()
            .first()
        )
        if row is None:
            return {"judge_overall_score": None, "judge_status": None}
        return {"judge_overall_score": row.overall_score, "judge_status": row.judge_status}
    finally:
        db.close()


def _run_regular_case(case: GoldenCase, *, run_judge: bool, settings: Any) -> CaseResult:
    patient_id = str(case.fixture.get("patient") or DEFAULT_PATIENT_ID)
    conversation_id = f"golden-{case.case_id}-{uuid.uuid4().hex[:8]}"
    outcomes: list[CaseOutcome] = []
    for turn in case.turns:
        response = _run_turn(turn.query, patient_id=patient_id, actor_id=DEFAULT_ACTOR_ID, conversation_id=conversation_id)
        durable = _durable_facts(response.agent_run_id)
        state_facts = _conversation_state_facts(actor_id=DEFAULT_ACTOR_ID, patient_id=patient_id, conversation_id=conversation_id)
        if run_judge:
            _maybe_enqueue_golden_judge(response=response, turn_query=turn.query, durable=durable, settings=settings)
        outcomes.append(
            CaseOutcome(
                execution_path=durable["execution_path"],
                intent=response.intent,
                status=response.status,
                response_text=response.reply,
                citation_titles=tuple(c.title for c in response.citations),
                tool_names=tuple(response.tools),
                model_calls=durable["model_calls"],
                safety_outcome=durable["safety_outcome"],
                safety_reason_code=durable["safety_reason_code"],
                safety_severity=durable["safety_severity"],
                handoff_required=durable["handoff_required"],
                handoff_created=durable["handoff_created"],
                active_topic=state_facts["active_topic"],
                active_entity=state_facts["active_entity"],
                requested_aspect=state_facts["requested_aspect"],
                trace_id=response.trace_id,
                agent_run_id=response.agent_run_id,
                error_code=durable["error_code"],
                http_status=None,
            )
        )
    return grade_case(case, outcomes)


def _run_auth_isolation_case(case: GoldenCase) -> CaseResult:
    """BUILD-35 §4/§16 AUTH_ISOLATION contract: not a chat turn at all -- a
    real cross-patient read attempt against BUILD-30's own patient-safe
    activity endpoint. Seeds one real trace as the canary patient, then
    attempts to read that trace's activity AS A DIFFERENT REAL PATIENT
    identity, expecting the same fail-closed 403
    `get_trace_activity` already gives production traffic (BUILD-30 §3) --
    calls that route function directly (same in-process pattern as
    `run_agent_orchestration` above), never over real HTTP."""

    # A deterministic, zero-model-call query -- this scenario only needs ANY
    # real trace with an activity snapshot to exist; it never inspects this
    # turn's own content/execution_path, so there is no reason to pay for a
    # real model call here.
    conversation_id = f"golden-{case.case_id}-{uuid.uuid4().hex[:8]}"
    seed_response = _run_turn(
        "Hôm nay tôi uống thuốc gì?", patient_id=DEFAULT_PATIENT_ID, actor_id=DEFAULT_ACTOR_ID, conversation_id=conversation_id
    )

    db = SessionLocal()
    http_status: int | None = None
    try:
        get_trace_activity(seed_response.trace_id, db=db, actor=_actor(CROSS_PATIENT_ID, CROSS_PATIENT_ACTOR_ID))
        http_status = 200
    except HTTPException as exc:
        http_status = exc.status_code
    finally:
        db.close()

    outcome = CaseOutcome(trace_id=seed_response.trace_id, agent_run_id=seed_response.agent_run_id, http_status=http_status)
    return grade_case(case, [outcome])


def run_case(case: GoldenCase, *, run_judge: bool, settings: Any) -> CaseResult:
    if case.category is GoldenCategory.AUTH_ISOLATION:
        return _run_auth_isolation_case(case)
    return _run_regular_case(case, run_judge=run_judge, settings=settings)


def _drain_judge_batch(settings: Any, *, max_ticks: int = 20) -> int:
    """Judge scoring is normally an out-of-band worker tick
    (`process_pending_judge_batch`, run periodically off the shared
    scheduler) -- a golden run that opts into `--with-judge` wants a real
    score in THIS run's own output, not just a PENDING row, so this drains
    the queue synchronously by calling the exact same production function
    repeatedly until it reports nothing left (bounded by `max_ticks` so a
    provider outage can never hang the run forever)."""

    db = SessionLocal()
    total = 0
    try:
        for _ in range(max_ticks):
            processed = process_pending_judge_batch(db, settings=settings, limit=None)
            total += processed
            if processed == 0:
                break
        return total
    finally:
        db.close()


def _patch_judge_scores(result: CaseResult) -> CaseResult:
    patched_outcomes = []
    for outcome in result.turn_outcomes:
        if outcome.agent_run_id is None:
            patched_outcomes.append(outcome)
            continue
        facts = _judge_facts(outcome.agent_run_id)
        patched_outcomes.append(dataclasses.replace(outcome, **facts))
    return dataclasses.replace(result, turn_outcomes=tuple(patched_outcomes))


# ---------------------------------------------------------------------------
# Baseline load + output artifacts
# ---------------------------------------------------------------------------


def _load_baseline_results(path: str | None) -> list[CaseResult] | None:
    """A baseline artifact is a prior run's own JSON output (see module
    docstring for how to produce one for `origin/main` via a worktree) --
    only `case_id`/`category`/`passed` are needed for comparison, so this
    reconstructs minimal `CaseResult` objects (empty checks/turn_outcomes)
    rather than requiring the full original object graph."""

    if not path:
        return None
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    results = raw.get("results", raw) if isinstance(raw, dict) else raw
    return [
        CaseResult(
            case_id=item["case_id"], category=item["category"], tags=tuple(item.get("tags", ())),
            passed=bool(item["passed"]), checks=(), turn_outcomes=(),
        )
        for item in results
    ]


def _write_outputs(
    *,
    out_dir: Path,
    run_id: str,
    provenance: RunProvenance,
    results: list[CaseResult],
    aggregate: dict[str, Any],
    comparisons,
    gate: RegressionGateResult,
    dataset_errors: list[DatasetValidationError],
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "provenance": provenance.as_dict(),
        "dataset_errors": [{"case_id": e.case_id, "reason": e.reason} for e in dataset_errors],
        "aggregate": aggregate,
        "regression_gate": {
            "passed": gate.passed,
            "critical_failures": list(gate.critical_failures),
            "regressed_non_critical": list(gate.regressed_non_critical),
            "non_critical_pass_rate": gate.non_critical_pass_rate,
            "non_critical_threshold": gate.non_critical_threshold,
        },
        "comparisons": [
            {
                "case_id": c.case_id, "category": c.category, "status": c.status.value,
                "baseline_passed": c.baseline_passed, "candidate_passed": c.candidate_passed,
            }
            for c in comparisons
        ],
        "results": [r.as_dict() for r in results],
    }
    json_path = out_dir / f"{run_id}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        f"# Golden Evaluation Run {run_id}",
        "",
        f"- git_commit: `{provenance.git_commit}`",
        f"- golden_set_version: `{provenance.golden_set_version}`",
        f"- started_at: {provenance.started_at}",
        f"- total_cases: {aggregate['total_cases']} | passed: {aggregate['passed_cases']} | failed: {aggregate['failed_cases']} | pass_rate: {aggregate['pass_rate']}",
        f"- regression gate: {'PASS' if gate.passed else 'FAIL'}",
    ]
    if gate.critical_failures:
        md_lines.append(f"  - CRITICAL FAILURES: {', '.join(gate.critical_failures)}")
    if gate.regressed_non_critical:
        md_lines.append(f"  - regressed (non-critical): {', '.join(gate.regressed_non_critical)}")
    md_lines.append("")
    md_lines.append("## By category")
    for category, bucket in aggregate["by_category"].items():
        md_lines.append(f"- {category}: {bucket['passed']}/{bucket['total']}")
    md_lines.append("")
    md_lines.append("## Failed cases")
    failed = [r for r in results if not r.passed]
    if not failed:
        md_lines.append("(none)")
    for r in failed:
        failing_checks = ", ".join(c.name for c in r.checks if c.status.value == "FAIL")
        md_lines.append(f"- {r.case_id} ({r.category}): {failing_checks}")

    md_path = out_dir / f"{run_id}.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return json_path, md_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BUILD-35 golden-set continuous-evaluation runner")
    parser.add_argument("--dataset", default="v1", help="golden set version (e.g. v1) or a literal path to a .json file")
    parser.add_argument("--baseline", default=None, help="path to a prior run's JSON output, for comparison")
    parser.add_argument("--with-judge", action="store_true", help="enqueue + synchronously score real Judge results for this run")
    parser.add_argument("--deterministic-only", action="store_true", help="run only zero-model-call categories (CI-safe, no paid credentials)")
    parser.add_argument("--non-critical-threshold", type=float, default=0.8)
    parser.add_argument("--out-dir", default=str(DEFAULT_RUNS_DIR))
    parser.add_argument("--case-id", action="append", default=None, help="restrict to one or more specific case_id values (repeatable)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    settings = get_settings()

    dataset_path = _resolve_dataset_path(args.dataset)
    cases = load_golden_set(dataset_path)
    dataset_errors = validate_golden_set(cases)
    if dataset_errors:
        print(f"DATASET VALIDATION FAILED ({len(dataset_errors)} error(s)) -- no case was run:")
        for err in dataset_errors:
            print(f"  {err.case_id}: {err.reason}")
        return 2

    if args.case_id:
        wanted = set(args.case_id)
        cases = [c for c in cases if c.case_id in wanted]
    if args.deterministic_only:
        cases = [c for c in cases if c.category in _DETERMINISTIC_CATEGORIES]

    if not cases:
        print("No cases selected to run (check --case-id/--deterministic-only filters).")
        return 2

    started_at = datetime.now(UTC)
    golden_set_version = cases[0].golden_set_version
    provenance = _build_provenance(settings=settings, golden_set_version=golden_set_version, started_at=started_at)

    results: list[CaseResult] = []
    for case in cases:
        t0 = time.monotonic()
        try:
            result = run_case(case, run_judge=args.with_judge, settings=settings)
        except Exception as exc:  # noqa: BLE001 -- one case's unexpected failure must not abort the whole run
            result = CaseResult(
                case_id=case.case_id, category=case.category.value, tags=tuple(case.tags), passed=False,
                checks=(), turn_outcomes=(CaseOutcome(error_code=f"RUNNER_EXCEPTION:{exc}"),),
            )
            print(f"  [{case.case_id}] RUNNER EXCEPTION: {exc}")
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        print(f"  [{case.case_id}] {case.category.value} -> {'PASS' if result.passed else 'FAIL'} ({elapsed_ms:.0f}ms)")
        results.append(result)

    if args.with_judge:
        scored = _drain_judge_batch(settings)
        print(f"Judge: scored {scored} pending row(s)")
        results = [_patch_judge_scores(r) for r in results]

    aggregate = aggregate_results(results)
    baseline_results = _load_baseline_results(args.baseline)
    comparisons = compare_to_baseline(results, baseline_results)
    gate = evaluate_regression_gate(results, comparisons, non_critical_threshold=args.non_critical_threshold)

    completed_at = datetime.now(UTC)
    provenance = dataclasses.replace(provenance, completed_at=completed_at.isoformat())

    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    json_path, md_path = _write_outputs(
        out_dir=Path(args.out_dir), run_id=run_id, provenance=provenance, results=results, aggregate=aggregate,
        comparisons=comparisons, gate=gate, dataset_errors=[],
    )

    print(f"\n{aggregate['passed_cases']}/{aggregate['total_cases']} cases passed (pass_rate={aggregate['pass_rate']})")
    print(f"Regression gate: {'PASS' if gate.passed else 'FAIL'}")
    if gate.critical_failures:
        print(f"  CRITICAL FAILURES: {gate.critical_failures}")
    if gate.regressed_non_critical:
        print(f"  regressed (non-critical): {gate.regressed_non_critical}")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")

    return 0 if gate.passed else 1


if __name__ == "__main__":
    # Deliberately set here, not at module import time: this module is
    # imported both by the real CLI entry point below AND by
    # tests/test_agent_v2_build35_golden_runner.py (pure helper-function
    # tests, no DB) and scripts/agent_v2/build35_golden_evaluation_local_
    # e2e.py (which sets this itself before importing, same as every other
    # local E2E script in this project). `os.environ` is process-global --
    # a module-level `setdefault` here would leak into every OTHER test in
    # the same pytest session merely from this module being imported (a
    # real regression this exact ordering fixed: see BUILD-35 report §12).
    os.environ.setdefault("AGENT_RUNTIME_ENABLED", "true")
    raise SystemExit(main())
