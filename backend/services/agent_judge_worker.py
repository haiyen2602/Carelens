"""BUILD-33: Judge enqueue (synchronous, cheap) + Judge scoring worker
(asynchronous, real LLM call, run off the shared scheduler).

Architecture (BUILD-33 §4/§14, BUILD-32-TO-36-MASTER-PLAN.md §BUILD-33):

    Agent Run -> Evaluation V2 -> Judge Eligibility -> [enqueue_*_judge]
        -> durable AgentRunJudge(JUDGE_PENDING) row
        -> (later, off-request, on a timer) process_pending_judge_batch()
        -> AgentRunJudge(JUDGE_COMPLETED | JUDGE_FAILED)

``enqueue_run_judge``/``enqueue_ticket_judge`` never call the Judge model --
they are called from the synchronous chat/ticket request path and must stay
cheap (one eligibility check, one sanitization pass, one DB insert) so Judge
review is never on the critical path of a real chat response.
``process_pending_judge_batch`` is the only function in this module that
performs a real network call, and it is never invoked from a request handler
-- only from ``backend.services.escalation_scheduler``'s periodic job.
"""

from __future__ import annotations

import json
import logging
import random
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.agents.v2.evaluation_v2 import EvaluationPath, EvaluationResult, MetricStatus, dispatch_evaluation
from backend.agents.v2.judge_eligibility import (
    JudgeEligibility,
    evaluate_sampling_eligibility,
    ticket_eligibility,
)
from backend.agents.v2.judge_input import JudgeInputPayload, JudgeInputRejectedError, build_judge_input
from backend.agents.v2.judge_provider import call_judge, resolve_base_url, resolve_credential
from backend.agents.v2.judge_rubrics import Rubric, render_prompt, rubric_for_path
from backend.db.models import AgentRunEvaluation, AgentRunJudge

logger = logging.getLogger("agent_judge_worker")


def _heuristic_score(result: Any, evaluation: EvaluationResult, request_message: str) -> float | None:
    """Same lightweight, deterministic heuristic already used to gate the
    ring-buffer's own relevance/faithfulness scores
    (backend.api.agent_v2_routes._record_agent_v2_telemetry) -- reused here
    ONLY to decide LOW_SCORE Judge eligibility, never persisted as a Judge
    result itself. `None` when neither metric is applicable to this
    execution path (e.g. a deterministic schedule/tool run)."""

    response_text = str(getattr(result, "response", "") or "")
    if not response_text or evaluation.metrics["answer_relevance"].status is not MetricStatus.AVAILABLE:
        return None

    from backend.services.evaluators import LLMJudgeEvaluator

    scores: list[float] = []
    if request_message:
        scores.append(LLMJudgeEvaluator.evaluate_answer_relevance(request_message, response_text).value)
    if evaluation.metrics["faithfulness"].status is MetricStatus.AVAILABLE:
        contexts: list[str] = []
        for tool_result in tuple(getattr(result, "tool_results", ()) or ()):
            try:
                contexts.append(json.dumps(tool_result.data, ensure_ascii=False, default=str))
            except Exception:  # noqa: BLE001 -- heuristic gating only, never block enqueue
                continue
        scores.append(LLMJudgeEvaluator.evaluate_faithfulness(contexts, response_text).value)
    if not scores:
        return None
    return min(float(score) for score in scores)


def _float_setting(settings: Any, name: str, default: float) -> float:
    """``getattr(...) or default`` silently replaces a legitimate, explicit
    ``0.0`` (e.g. "disable low-score sampling entirely") with ``default`` --
    exactly the "0 vs N/A vs unset" collapse this project's own principles
    explicitly warn against elsewhere. Only ``None``/missing falls back."""

    value = getattr(settings, name, None)
    return float(value) if value is not None else float(default)


def _judge_config(settings: Any) -> dict:
    return {
        "reasoning_effort": str(getattr(settings, "agent_judge_reasoning_effort", "") or ""),
        "timeout_seconds": _float_setting(settings, "agent_judge_timeout_seconds", 30.0),
    }


def _insert_row(db: Session, row: AgentRunJudge) -> AgentRunJudge | None:
    """Duplicate-protected insert (BUILD-33 §8) -- same nested-savepoint +
    IntegrityError pattern as backend.services.agent_idempotency/
    agent_feedback.create_ticket. Returns None (not an error) when a row for
    this exact (agent_run_id, judge_model, rubric_version, prompt_version)
    already exists.

    Deliberately commits (unlike ``create_ticket``, which leaves that to its
    HTTP-route caller) -- ``enqueue_run_judge``/``enqueue_ticket_judge`` are
    meant to be fully self-contained, call-directly-with-no-extra-wrapping
    best-effort units, same shape as ``agent_v2_routes._persist_durable_
    trace``. Since ``db.commit()`` commits the WHOLE session, not just this
    row, this function's precondition is that its caller's own prior work is
    ALREADY committed by the time it runs -- both real call sites honor this
    (``agent_v2_routes.py`` calls this right after ``_persist_durable_
    trace``'s own commit; ``agent_feedback_routes.py`` calls this right
    after the ticket's own commit) and this has been verified directly
    against real Postgres. The alternative (never commit here, require every
    caller to commit afterward) trades this for a strictly worse, previously
    REAL failure mode in this exact codebase -- see
    ``tests/test_agent_v2_transaction_durability.py``'s own docstring on the
    historical "run_agent_orchestration never called db.commit()" defect --
    so this is a considered trade-off, not an oversight."""

    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
        db.commit()
        return row
    except IntegrityError:
        db.rollback()
        return None


def _new_row(
    *,
    agent_run_id: str,
    trace_id: str,
    execution_path: EvaluationPath | None,
    evaluation_version: str | None,
    settings: Any,
    eligibility: JudgeEligibility,
    payload: JudgeInputPayload,
) -> AgentRunJudge:
    rubric = rubric_for_path(execution_path) if execution_path is not None else rubric_for_path(EvaluationPath.OUT_OF_SCOPE)
    return AgentRunJudge(
        agent_run_id=agent_run_id,
        trace_id=trace_id,
        judge_status="JUDGE_PENDING",
        eligibility_reason=eligibility.reason.value if eligibility.reason else "UNKNOWN",
        priority=eligibility.priority,
        execution_path=execution_path.value if execution_path is not None else None,
        judge_provider=str(getattr(settings, "agent_judge_provider", "") or ""),
        judge_model=str(getattr(settings, "agent_judge_model", "") or ""),
        judge_config_json=_judge_config(settings),
        rubric_name=rubric.name,
        rubric_version=str(getattr(settings, "agent_judge_rubric_version", "") or ""),
        judge_prompt_version=str(getattr(settings, "agent_judge_prompt_version", "") or ""),
        evaluation_version=evaluation_version,
        dimension_scores_json={},
        flags_json=[],
        sanitized_query=payload.query,
        sanitized_response=payload.response,
        sanitized_context_json=payload.as_context_dict(),
    )


def enqueue_run_judge(
    db: Session,
    *,
    result: Any,
    request_message: str,
    settings: Any,
    sample_roll: float | None = None,
) -> AgentRunJudge | None:
    """Sampling/anomaly/error-triggered enqueue -- called once per completed
    run, right after ``AgentRunEvaluation`` is persisted
    (backend.api.agent_v2_routes._persist_durable_trace's caller). Never
    raises; caller wraps this in its own best-effort try/except, same as
    every other post-response durability step in that module."""

    if not bool(getattr(settings, "agent_judge_enabled", False)):
        return None

    try:
        evaluation = dispatch_evaluation(result=result)
        heuristic_score = _heuristic_score(result, evaluation, request_message)
        roll = random.random() if sample_roll is None else sample_roll
        eligibility = evaluate_sampling_eligibility(
            result=result,
            evaluation=evaluation,
            heuristic_score=heuristic_score,
            sampling_rate=_float_setting(settings, "agent_judge_sampling_rate", 0.0),
            low_score_threshold=_float_setting(settings, "agent_judge_low_score_threshold", 0.5),
            sample_roll=roll,
        )
        if not eligibility.eligible:
            return None

        try:
            payload = build_judge_input(
                query=request_message,
                response=str(getattr(result, "response", "") or ""),
                path=evaluation.path,
                tool_results=tuple(getattr(result, "tool_results", ()) or ()),
                citations=tuple(getattr(result, "citations", ()) or ()),
            )
        except JudgeInputRejectedError as rejected:
            logger.warning("Judge input rejected for agent_run_id=%s: %s", getattr(result, "agent_run_id", "?"), rejected)
            return None

        evaluation_version = str(evaluation.as_dict().get("evaluator_version") or "")
        row = _new_row(
            agent_run_id=result.agent_run_id,
            trace_id=result.trace_id,
            execution_path=evaluation.path,
            evaluation_version=evaluation_version,
            settings=settings,
            eligibility=eligibility,
            payload=payload,
        )
        return _insert_row(db, row)
    except Exception:  # noqa: BLE001 -- Judge enqueue is best-effort; it must never break the real chat response
        db.rollback()
        logger.exception("Judge enqueue failed for agent_run_id=%s", getattr(result, "agent_run_id", "?"))
        return None


def enqueue_ticket_judge(db: Session, *, ticket: Any, settings: Any) -> AgentRunJudge | None:
    """Ticket-triggered enqueue (BUILD-33 §3/§11: "Ticket nen duoc uu tien
    Judge theo policy") -- always eligible, never subject to sampling.

    Uses the ticket's own durable ``user_message``/``assistant_message``
    (already the patient's own submitted text, already durable on
    ``AgentFeedbackTicket`` since BUILD-29) as the Judge input text, since a
    ticket may be filed long after the run's own in-memory ring buffer has
    evicted it -- see ``AgentRunJudge``'s own docstring. The real
    ``execution_path`` (for correct rubric selection) is looked up from the
    durable ``AgentRunEvaluation`` row BUILD-32 already wrote for this same
    ``agent_run_id`` when the run completed; a lookup miss (pre-BUILD-32 run,
    or a durable-read hiccup) degrades to the generic rubric, never blocks
    ticket creation.
    """

    if not bool(getattr(settings, "agent_judge_enabled", False)):
        return None

    try:
        agent_run_id = str(getattr(ticket, "agent_run_id", "") or "")
        execution_path: EvaluationPath | None = None
        try:
            raw_path = db.execute(
                select(AgentRunEvaluation.execution_path).where(AgentRunEvaluation.agent_run_id == agent_run_id)
            ).scalar_one_or_none()
            if raw_path:
                execution_path = EvaluationPath(raw_path)
        except Exception as lookup_err:  # noqa: BLE001 -- a lookup failure degrades to the generic rubric, never blocks the ticket
            logger.warning("Judge ticket execution_path lookup failed for agent_run_id=%s: %s", agent_run_id, lookup_err)

        try:
            payload = build_judge_input(
                query=str(getattr(ticket, "user_message", "") or ""),
                response=str(getattr(ticket, "assistant_message", "") or ""),
                path=execution_path or EvaluationPath.OUT_OF_SCOPE,
                tool_results=(),
                citations=(),
            )
        except JudgeInputRejectedError as rejected:
            logger.warning("Judge ticket input rejected for ticket_id=%s: %s", getattr(ticket, "id", "?"), rejected)
            return None

        row = _new_row(
            agent_run_id=agent_run_id,
            trace_id=str(getattr(ticket, "trace_id", "") or agent_run_id),
            execution_path=execution_path,
            evaluation_version=None,
            settings=settings,
            eligibility=ticket_eligibility(),
            payload=payload,
        )
        return _insert_row(db, row)
    except Exception:  # noqa: BLE001 -- Judge enqueue is best-effort; it must never break ticket creation
        db.rollback()
        logger.exception("Judge ticket enqueue failed for ticket_id=%s", getattr(ticket, "id", "?"))
        return None


def process_pending_judge_batch(db: Session, *, settings: Any, limit: int | None = None) -> int:
    """Real, out-of-band Judge scoring pass. Ordered by priority ascending
    (ticket/golden first, random sample last), then FIFO within a priority
    tier. Commits each row independently -- one Judge call failing must never
    roll back or block another row's result (BUILD-33 §4/§10).

    Returns the number of rows scored (COMPLETED or FAILED -- both count as
    "processed", since a provider failure is a real, terminal, non-retried
    outcome per this build's "no SDK-level retry" design, see config.py).
    """

    batch_limit = int(limit if limit is not None else getattr(settings, "agent_judge_max_per_tick", 5))
    rows = (
        db.execute(
            select(AgentRunJudge)
            .where(AgentRunJudge.judge_status == "JUDGE_PENDING")
            .order_by(AgentRunJudge.priority.asc(), AgentRunJudge.created_at.asc())
            .limit(batch_limit)
        )
        .scalars()
        .all()
    )

    processed = 0
    for row in rows:
        try:
            _score_one_row(db, row=row, settings=settings)
            processed += 1
        except Exception:  # noqa: BLE001 -- one row's unexpected failure must not stop the batch or the scheduler
            db.rollback()
            logger.exception("Unexpected failure scoring AgentRunJudge id=%s", row.id)
    return processed


def _rubric_for_row(row: AgentRunJudge) -> Rubric:
    try:
        path_enum = EvaluationPath(row.execution_path) if row.execution_path else None
    except ValueError:
        path_enum = None
    return rubric_for_path(path_enum) if path_enum is not None else rubric_for_path(EvaluationPath.OUT_OF_SCOPE)


def _judge_cost(*, model: str, settings: Any, input_tokens: int, output_tokens: int) -> tuple[float | None, str]:
    from backend.agents.v2.model_gateway import ModelRole, ModelUsage
    from backend.agents.v2.observability import ModelPricingCatalog

    try:
        catalog = ModelPricingCatalog.from_settings(settings)
        estimate = catalog.estimate(
            model=model,
            model_role=ModelRole.JUDGE,
            usage=ModelUsage(input_tokens=input_tokens, output_tokens=output_tokens),
        )
    except Exception:  # noqa: BLE001 -- a misconfigured price catalog must degrade to NOT_AVAILABLE, never crash scoring
        return None, "NOT_AVAILABLE"
    if estimate.estimated_cost_usd is None:
        return None, "NOT_AVAILABLE"
    return estimate.estimated_cost_usd, "AVAILABLE"


def _score_one_row(db: Session, *, row: AgentRunJudge, settings: Any) -> None:
    payload = JudgeInputPayload(
        query=row.sanitized_query or "",
        response=row.sanitized_response or "",
        execution_path=row.execution_path or "",
        tool_names=tuple(row.sanitized_context_json.get("tool_names") or ()),
        citations=tuple(row.sanitized_context_json.get("citations") or ()),
        retrieved_evidence=tuple(row.sanitized_context_json.get("retrieved_evidence") or ()),
        expected_ground_truth=row.sanitized_context_json.get("expected_ground_truth"),
    )
    prompt = render_prompt(rubric=_rubric_for_row(row), payload=payload)

    api_key = resolve_credential(
        provider=row.judge_provider,
        openai_judge_api_key=str(getattr(settings, "openai_judge_api_key", "") or ""),
        openai_api_key=str(getattr(settings, "openai_api_key", "") or ""),
        google_api_key=str(getattr(settings, "agent_judge_google_api_key", "") or ""),
    )
    base_url = resolve_base_url(
        provider=row.judge_provider, configured_base_url=str(getattr(settings, "agent_judge_base_url", "") or "")
    )
    config = row.judge_config_json or {}

    call_result = call_judge(
        provider=row.judge_provider,
        model=row.judge_model,
        api_key=api_key,
        base_url=base_url,
        reasoning_effort=str(config.get("reasoning_effort") or ""),
        timeout_seconds=float(config["timeout_seconds"]) if config.get("timeout_seconds") is not None else 30.0,
        prompt=prompt,
    )

    row.input_tokens = call_result.input_tokens
    row.output_tokens = call_result.output_tokens
    row.failure_reason = call_result.failure_reason
    row.evaluated_at = datetime.now(UTC)

    if call_result.status == "SCORED":
        row.judge_status = "JUDGE_COMPLETED"
        row.overall_score = call_result.overall_score
        row.dimension_scores_json = call_result.dimension_scores
        row.flags_json = call_result.flags
        row.confidence = call_result.confidence
        row.cost_usd, row.cost_status = _judge_cost(
            model=row.judge_model, settings=settings, input_tokens=call_result.input_tokens, output_tokens=call_result.output_tokens
        )
    else:
        row.judge_status = "JUDGE_FAILED"

    db.commit()


__all__ = [
    "enqueue_run_judge",
    "enqueue_ticket_judge",
    "process_pending_judge_batch",
]
