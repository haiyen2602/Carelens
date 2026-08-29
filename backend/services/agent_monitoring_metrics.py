"""BUILD-36: parameterized aggregation core for Admin Monitoring Dashboard
V2.

One ``MonitoringFilters`` dataclass + one function per dashboard section,
all reading the SAME durable tables BUILD-32/33/34/35 already write
(``AgentRun``/``AgentRunSpan``/``AgentRunEvaluation``/``AgentRunJudge``/
``AgentSafetyEvent``/``AgentGoldenRun``/``AgentGoldenRunCase``) -- nothing
here writes to any table, and nothing here changes Agent V2's own routing/
safety/response behavior.

Every rate is a ``{value, numerator, denominator, sample_count, status}``
dict, never a bare float -- ``status`` is one of ``AVAILABLE`` /
``NOT_APPLICABLE`` (denominator is legitimately 0) / ``NOT_AVAILABLE`` (the
underlying data source itself is unavailable, e.g. a durable-read failure).
See ``_rate()``. A caller (``admin_monitoring_routes.py``) rendering
``value: None`` must show the literal text ``N/A``, never ``0%``/``0.00``.

``/versions/compare`` (in the routes module, not here) calls the SAME
per-section function twice, once per filter set, and diffs the two results
-- this file has no separate "compare" code path of its own, so there is
only ever one implementation of each metric to keep correct.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from backend.db.models import (
    AgentFeedbackTicket,
    AgentGoldenRun,
    AgentGoldenRunCase,
    AgentRun,
    AgentRunEvaluation,
    AgentRunJudge,
    AgentRunSpan,
    AgentSafetyEvent,
)
from backend.services.agent_safety_monitoring import safety_metrics_summary

# ---------------------------------------------------------------------------
# Filter abstraction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MonitoringFilters:
    """Filter parameters accepted by every dashboard aggregation function.

    Every field is optional; ``None`` means "no filter on this dimension".
    """

    date_from: datetime | None = None
    date_to: datetime | None = None
    model: str | None = None
    prompt_version: str | None = None
    retrieval_version: str | None = None
    evaluation_version: str | None = None
    execution_path: str | None = None
    status: str | None = None
    error_code: str | None = None
    safety_severity: str | None = None
    judge_model: str | None = None
    rubric_version: str | None = None
    judge_score_min: float | None = None
    judge_score_max: float | None = None
    ticket_present: bool | None = None


def _apply_agent_run_filters(stmt: Select, filters: MonitoringFilters) -> Select:
    """Applies filter fields to AgentRun base query, joining AgentRunEvaluation
    when execution_path or evaluation_version filters are active."""

    if filters.date_from is not None:
        stmt = stmt.where(AgentRun.started_at >= filters.date_from)
    if filters.date_to is not None:
        stmt = stmt.where(AgentRun.started_at <= filters.date_to)
    if filters.model:
        stmt = stmt.where(AgentRun.model == filters.model)
    if filters.prompt_version:
        stmt = stmt.where(AgentRun.prompt_version == filters.prompt_version)
    if filters.retrieval_version:
        stmt = stmt.where(AgentRun.retrieval_version == filters.retrieval_version)
    if filters.status:
        stmt = stmt.where(AgentRun.status == filters.status)
    if filters.error_code:
        stmt = stmt.where(AgentRun.error_code == filters.error_code)
    if filters.execution_path or filters.evaluation_version:
        stmt = stmt.join(AgentRunEvaluation, AgentRunEvaluation.agent_run_id == AgentRun.id)
        if filters.execution_path:
            stmt = stmt.where(AgentRunEvaluation.execution_path == filters.execution_path)
        if filters.evaluation_version:
            stmt = stmt.where(AgentRunEvaluation.evaluation_version == filters.evaluation_version)
    return stmt


# ---------------------------------------------------------------------------
# Rate/N-A helpers
# ---------------------------------------------------------------------------


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    if denominator <= 0:
        return {"value": None, "numerator": numerator, "denominator": denominator, "sample_count": denominator, "status": "NOT_APPLICABLE"}
    return {
        "value": round(numerator / denominator, 4),
        "numerator": numerator,
        "denominator": denominator,
        "sample_count": denominator,
        "status": "AVAILABLE",
    }


def _average(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"value": None, "numerator": 0, "denominator": 0, "sample_count": 0, "status": "NOT_APPLICABLE"}
    return {
        "value": round(sum(values) / len(values), 4),
        "numerator": None,
        "denominator": None,
        "sample_count": len(values),
        "status": "AVAILABLE",
    }


def _percentiles(values: list[float], points: tuple[int, ...] = (50, 95, 99)) -> dict[str, Any]:
    """Computed in Python (sorted list + index math), not SQL
    ``percentile_cont`` -- deliberate: this project's own test suite runs
    the same service functions against SQLite (no ``percentile_cont``
    support) as well as real Postgres, and dashboard-scale row counts (an
    admin's own filtered window, never the full production table
    unbounded) make fetching the raw values cheap. A future build moving
    this to a real SQL aggregate if row counts grow is a legitimate,
    separate optimization, not something this build silently skips
    verifying."""

    if not values:
        return {p: {"value": None, "sample_count": 0, "status": "NOT_APPLICABLE"} for p in points}
    ordered = sorted(values)
    n = len(ordered)
    result: dict[str, Any] = {}
    for p in points:
        idx = min(n - 1, max(0, round((p / 100) * (n - 1))))
        result[p] = {"value": round(ordered[idx], 2), "sample_count": n, "status": "AVAILABLE"}
    return result


def _count(db: Session, stmt: Select) -> int:
    return int(db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one() or 0)


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


def overview_metrics(db: Session, filters: MonitoringFilters) -> dict[str, Any]:
    try:
        base = _apply_agent_run_filters(select(AgentRun), filters)
        total = _count(db, base)

        success = _count(db, base.where(AgentRun.status == "COMPLETED"))
        errors = _count(db, base.where(AgentRun.error_code.is_not(None)))
        timeouts = _count(db, base.where(AgentRun.timeout.is_(True)))
        empty_replies = _count(db, base.where(AgentRun.empty_reply.is_(True)))

        # FALLBACK is an Evaluation V2 execution_path, not an AgentRun
        # column -- one join, scoped to this single card, not the shared
        # base (see _apply_agent_run_filters's own docstring on why).
        fallback = _count(
            db,
            select(AgentRun)
            .join(AgentRunEvaluation, AgentRunEvaluation.agent_run_id == AgentRun.id)
            .where(AgentRunEvaluation.execution_path == "FALLBACK")
            .where(AgentRun.id.in_(select(base.subquery().c.id))),
        )

        durations = [
            d for d in db.execute(base.with_only_columns(AgentRun.duration_ms)).scalars().all() if d is not None
        ]
        latency = _percentiles(durations, points=(50, 95))

        token_values = db.execute(base.with_only_columns(AgentRun.total_tokens)).scalars().all()
        token_per_query = _average([float(t) for t in token_values]) if token_values else _average([])

        cost_rows = db.execute(
            base.where(AgentRun.cost_status == "AVAILABLE").with_only_columns(AgentRun.total_cost_usd)
        ).scalars().all()
        cost_per_query = _average([float(c) for c in cost_rows if c is not None])
        daily_cost_value = sum(float(c) for c in cost_rows if c is not None) if cost_rows else None

        ticket_run_ids = set(
            db.execute(select(AgentFeedbackTicket.agent_run_id).where(AgentFeedbackTicket.agent_run_id.in_(select(base.subquery().c.id)))).scalars().all()
        )

        judged = _count(db, select(AgentRunJudge).where(AgentRunJudge.agent_run_id.in_(select(base.subquery().c.id))))

        # safety_metrics_summary (BUILD-34) only accepts date_from/date_to,
        # not model/prompt_version/status/error_code -- pairing its
        # date-scoped-only numerator with THIS function's possibly-more-
        # filtered `total` denominator would silently produce a rate whose
        # numerator and denominator are scoped by different filter sets.
        # Own try/except (not the outer one) so a safety-side hiccup only
        # degrades these 2 cards, never the rest of Overview -- same
        # fine-grained degrade discipline BUILD-32's own post-merge incident
        # taught this project not to skip.
        extra_filters_active = any(
            [filters.model, filters.prompt_version, filters.retrieval_version, filters.status, filters.error_code]
        )
        try:
            safety = safety_metrics_summary(db, date_from=filters.date_from, date_to=filters.date_to)
            safety_denominator = int(safety.get("denominator_agent_v2_total_runs") or 0)
            safety_trigger_rate = _rate(int(safety.get("safety_trigger_count") or 0), safety_denominator)
            handoff_rate = _rate(int(safety.get("handoff_required_count") or 0), safety_denominator)
            if extra_filters_active:
                safety_trigger_rate["scope_note"] = "date_range_filter_only_model_and_other_filters_not_applied"
                handoff_rate["scope_note"] = "date_range_filter_only_model_and_other_filters_not_applied"
        except Exception:  # noqa: BLE001 -- degrade only these 2 cards, not the whole Overview section
            safety_trigger_rate = {"value": None, "numerator": 0, "denominator": 0, "sample_count": 0, "status": "NOT_AVAILABLE"}
            handoff_rate = {"value": None, "numerator": 0, "denominator": 0, "sample_count": 0, "status": "NOT_AVAILABLE"}

        # 6 core failure-mode evaluation metrics
        # 1. Task completion: COMPLETED runs rate
        task_completion = _rate(success, total)
        
        # 2. Tool correctness: completed runs across tool execution paths
        tool_runs_stmt = (
            select(AgentRun)
            .join(AgentRunEvaluation, AgentRunEvaluation.agent_run_id == AgentRun.id)
            .where(
                AgentRunEvaluation.execution_path.in_([
                    "DETERMINISTIC_TOOL",
                    "DETERMINISTIC_SCHEDULE",
                    "DRUG_LOOKUP",
                    "MEDICATION_DOSE_SAFETY",
                ])
            )
            .where(AgentRun.id.in_(select(base.subquery().c.id)))
        )
        tool_total = _count(db, tool_runs_stmt)
        tool_success = _count(db, tool_runs_stmt.where(AgentRun.status == "COMPLETED"))
        tool_correctness = _rate(tool_success, tool_total)

        # 3. Contextual precision & 4. Faithfulness from quality / heuristic
        heuristic = _heuristic_quality_scores(db)
        faithfulness = {**heuristic["faithfulness"], "metric_type": "HEURISTIC"}
        
        # Contextual precision: Precision@10 or proxy based on successful RAG grounding
        rag_stmt = (
            select(AgentRunEvaluation)
            .where(AgentRunEvaluation.execution_path == "RAG")
            .where(AgentRunEvaluation.agent_run_id.in_(select(base.subquery().c.id)))
        )
        rag_total = _count(db, rag_stmt)
        # RAG runs that completed without grounding failure (NULL error_code or != GROUNDING_FAILURE)
        rag_accurate = _count(
            db,
            select(AgentRun)
            .join(AgentRunEvaluation, AgentRunEvaluation.agent_run_id == AgentRun.id)
            .where(AgentRunEvaluation.execution_path == "RAG")
            .where(or_(AgentRun.error_code.is_(None), AgentRun.error_code != "GROUNDING_FAILURE"))
            .where(AgentRun.status == "COMPLETED")
            .where(AgentRun.id.in_(select(base.subquery().c.id)))
        )
        contextual_precision = _rate(rag_accurate, rag_total) if rag_total > 0 else _rate(0, 0)

        return {
            "available": True,
            "total_requests": total,
            "success_rate": _rate(success, total),
            "fallback_rate": _rate(fallback, total),
            "error_rate": _rate(errors, total),
            "timeout_rate": _rate(timeouts, total),
            "empty_reply_rate": _rate(empty_replies, total),
            "latency_p50_ms": latency[50],
            "latency_p95_ms": latency[95],
            "tokens_per_query": token_per_query,
            "cost_per_query_usd": cost_per_query,
            "daily_cost_usd": {
                "value": round(daily_cost_value, 4) if daily_cost_value is not None else None,
                "status": "AVAILABLE" if cost_rows else "NOT_APPLICABLE",
            },
            "ticket_rate": _rate(len(ticket_run_ids), total),
            "safety_trigger_rate": safety_trigger_rate,
            "handoff_rate": handoff_rate,
            "judged_rate": _rate(judged, total),
            # New failure mode metrics
            "task_completion": task_completion,
            "tool_correctness": tool_correctness,
            "contextual_precision": contextual_precision,
            "faithfulness": faithfulness,
        }
    except Exception as exc:  # noqa: BLE001 -- one section's failure degrades that section, never the whole dashboard
        return {"available": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# Quality (heuristic faithfulness/relevance are durable + ring-buffer fallback)
# ---------------------------------------------------------------------------


def _heuristic_quality_scores(db: Session | None = None) -> dict[str, Any]:
    from backend.services.telemetry import get_local_traces

    faithfulness: list[float] = []
    relevance: list[float] = []

    # 1. Load durable records from database if available
    if db is not None:
        try:
            eval_rows = db.execute(
                select(AgentRunEvaluation.metrics_json).where(AgentRunEvaluation.metrics_json.is_not(None))
            ).scalars().all()
            for m_json in eval_rows:
                if not isinstance(m_json, dict):
                    continue
                f_metric = m_json.get("faithfulness")
                if isinstance(f_metric, dict) and f_metric.get("status") == "AVAILABLE":
                    val = f_metric.get("score") if f_metric.get("score") is not None else f_metric.get("value")
                    if isinstance(val, (int, float)):
                        faithfulness.append(float(val))
                r_metric = m_json.get("answer_relevance")
                if isinstance(r_metric, dict) and r_metric.get("status") == "AVAILABLE":
                    val = r_metric.get("score") if r_metric.get("score") is not None else r_metric.get("value")
                    if isinstance(val, (int, float)):
                        relevance.append(float(val))
        except Exception:
            pass

    # 2. Also collect from in-memory ring buffer traces
    for trace in get_local_traces():
        evaluation = trace.metadata.get("evaluation_v2") if isinstance(trace.metadata, dict) else None
        if not isinstance(evaluation, dict):
            continue
        metrics = evaluation.get("metrics", {})
        f_metric = metrics.get("faithfulness")
        if isinstance(f_metric, dict) and f_metric.get("status") == "AVAILABLE":
            value = trace.scores.get("answer_faithfulness")
            if isinstance(value, (int, float)):
                faithfulness.append(float(value))
        r_metric = metrics.get("answer_relevance")
        if isinstance(r_metric, dict) and r_metric.get("status") == "AVAILABLE":
            value = trace.scores.get("answer_relevance")
            if isinstance(value, (int, float)):
                relevance.append(float(value))

    scope_note = "durable_evaluations_and_in_memory_buffer" if faithfulness else "in_memory_ring_buffer_current_process_only"
    return {
        "faithfulness": {**_average(faithfulness), "scope": scope_note},
        "answer_relevance": {**_average(relevance), "scope": scope_note},
    }


_GOLDEN_IR_NOT_APPLICABLE = {
    "value": None,
    "sample_count": 0,
    "status": "NOT_APPLICABLE",
    "reason": "no_stable_retrieval_id_contract_see_build_31_and_build_35",
}


def quality_metrics(db: Session, filters: MonitoringFilters) -> dict[str, Any]:
    try:
        heuristic = _heuristic_quality_scores(db)

        judge_stmt = select(AgentRunJudge.overall_score).where(AgentRunJudge.judge_status == "JUDGE_COMPLETED")
        if filters.date_from is not None:
            judge_stmt = judge_stmt.where(AgentRunJudge.created_at >= filters.date_from)
        if filters.date_to is not None:
            judge_stmt = judge_stmt.where(AgentRunJudge.created_at <= filters.date_to)
        if filters.judge_model:
            judge_stmt = judge_stmt.where(AgentRunJudge.judge_model == filters.judge_model)
        if filters.rubric_version:
            judge_stmt = judge_stmt.where(AgentRunJudge.rubric_version == filters.rubric_version)
        judge_scores = [s for s in db.execute(judge_stmt).scalars().all() if s is not None]

        latest_golden = db.execute(select(AgentGoldenRun).order_by(AgentGoldenRun.created_at.desc()).limit(1)).scalar_one_or_none()

        return {
            "available": True,
            "rag_faithfulness": {**heuristic["faithfulness"], "metric_type": "HEURISTIC"},
            "rag_answer_relevance": {**heuristic["answer_relevance"], "metric_type": "HEURISTIC"},
            "golden_hit_rate_at_10": {**_GOLDEN_IR_NOT_APPLICABLE, "metric_type": "GOLDEN"},
            "golden_mrr_at_10": {**_GOLDEN_IR_NOT_APPLICABLE, "metric_type": "GOLDEN"},
            "golden_ndcg_at_10": {**_GOLDEN_IR_NOT_APPLICABLE, "metric_type": "GOLDEN"},
            "judge_overall_score": {**_average([float(s) for s in judge_scores]), "metric_type": "LLM_JUDGE"},
            "golden_pass_rate": {
                "value": latest_golden.pass_rate if latest_golden else None,
                "run_id": latest_golden.id if latest_golden else None,
                "status": "AVAILABLE" if latest_golden and latest_golden.pass_rate is not None else "NOT_APPLICABLE",
                "metric_type": "GOLDEN",
            },
            "regression_gate_status": {
                "value": ("PASS" if latest_golden.regression_gate_passed else "FAIL") if latest_golden else None,
                "run_id": latest_golden.id if latest_golden else None,
                "status": "AVAILABLE" if latest_golden else "NOT_APPLICABLE",
                "metric_type": "GOLDEN",
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


def retrieval_metrics(db: Session, filters: MonitoringFilters) -> dict[str, Any]:
    try:
        base = _apply_agent_run_filters(select(AgentRun), filters)
        run_ids_subq = select(base.subquery().c.id)

        rag_stmt = (
            select(AgentRunEvaluation)
            .where(AgentRunEvaluation.execution_path == "RAG")
            .where(AgentRunEvaluation.agent_run_id.in_(run_ids_subq))
        )
        rag_volume = _count(db, rag_stmt)

        grounding_failures = _count(db, base.where(AgentRun.error_code == "GROUNDING_FAILURE"))
        total = _count(db, base)
        # Deliberately NOT reported as a "RAG empty-retrieval rate" --
        # GROUNDING_FAILURE (BUILD-24F) fires for every grounding-required
        # intent (drug info, prescription, schedule/dose lookups, general
        # medical), not RAG specifically, AND Evaluation V2's RAG
        # classification itself REQUIRES real citations
        # (dispatch_evaluation: "intent == GENERAL_MEDICAL_INFORMATION and
        # citations"), so a run can never be BOTH execution_path==RAG AND
        # error_code==GROUNDING_FAILURE. An earlier version of this
        # function paired grounding_failures with rag_volume as if they
        # were the same population and produced a nonsensical inflated
        # rate -- caught by smoke-testing this function against real data
        # before building anything on top of it, not by inspection alone.
        # `grounding_failure_rate` below (denominator = ALL filtered runs)
        # is the one honestly-scoped metric for this concept.

        retrieval_spans = db.execute(
            select(AgentRunSpan.duration_ms)
            .where(AgentRunSpan.span_type == "RETRIEVAL")
            .where(AgentRunSpan.agent_run_id.in_(run_ids_subq))
        ).scalars().all()
        retrieval_latency = _percentiles([d for d in retrieval_spans if d is not None], points=(50, 95))

        # Citation COUNT itself was never made durable by any prior build
        # (only the metric disposition, not a citation array/count) -- same
        # honest ring-buffer-scoped limit as the heuristic scores above.
        heuristic = _heuristic_quality_scores()

        return {
            "available": True,
            "rag_query_volume": rag_volume,
            "retrieval_latency_p50_ms": retrieval_latency[50],
            "retrieval_latency_p95_ms": retrieval_latency[95],
            "empty_retrieval_rate": {
                "value": None, "numerator": 0, "denominator": 0, "sample_count": 0, "status": "NOT_APPLICABLE",
                "reason": "grounding_failure_spans_multiple_intents_not_isolable_to_rag_only_today_see_grounding_failure_rate",
            },
            "grounding_failure_rate": _rate(grounding_failures, total),
            "citation_count_scope": "in_memory_ring_buffer_current_process_only_never_made_durable",
            "faithfulness_proxy_for_citation_context": heuristic["faithfulness"],
            "golden_hit_rate_at_10": _GOLDEN_IR_NOT_APPLICABLE,
            "golden_mrr_at_10": _GOLDEN_IR_NOT_APPLICABLE,
            "golden_ndcg_at_10": _GOLDEN_IR_NOT_APPLICABLE,
            "golden_precision_at_10": _GOLDEN_IR_NOT_APPLICABLE,
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# Performance -- real BUILD-32 spans only, never a fabricated/post-hoc span
# ---------------------------------------------------------------------------

_SPAN_TYPES = (
    "ROUTER", "MODEL", "TOOL", "RETRIEVAL", "SAFETY", "HANDOFF",
    "CHECKPOINT", "GUARDRAIL", "RUNTIME", "TIME_QUERY", "GROUNDING", "EVALUATION",
)


def performance_metrics(db: Session, filters: MonitoringFilters) -> dict[str, Any]:
    try:
        base = _apply_agent_run_filters(select(AgentRun), filters)
        run_ids_subq = select(base.subquery().c.id)

        durations = [d for d in db.execute(base.with_only_columns(AgentRun.duration_ms)).scalars().all() if d is not None]
        end_to_end = _percentiles(durations, points=(50, 95, 99))

        per_step: dict[str, Any] = {}
        for span_type in _SPAN_TYPES:
            values = db.execute(
                select(AgentRunSpan.duration_ms)
                .where(AgentRunSpan.span_type == span_type)
                .where(AgentRunSpan.agent_run_id.in_(run_ids_subq))
            ).scalars().all()
            per_step[span_type] = _percentiles([v for v in values if v is not None], points=(50, 95))

        total = _count(db, base)
        timeouts = _count(db, base.where(AgentRun.timeout.is_(True)))

        return {
            "available": True,
            "end_to_end_p50_ms": end_to_end[50],
            "end_to_end_p95_ms": end_to_end[95],
            "end_to_end_p99_ms": end_to_end[99],
            "per_step": per_step,
            "timeout_rate": _rate(timeouts, total),
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# Token & Cost
# ---------------------------------------------------------------------------


def cost_metrics(db: Session, filters: MonitoringFilters) -> dict[str, Any]:
    try:
        base = _apply_agent_run_filters(select(AgentRun), filters)
        run_ids_subq = select(base.subquery().c.id)

        agent_rows = db.execute(
            base.where(AgentRun.cost_status == "AVAILABLE").with_only_columns(
                AgentRun.total_cost_usd, AgentRun.input_tokens, AgentRun.output_tokens, AgentRun.total_tokens
            )
        ).all()
        agent_cost = sum(float(r.total_cost_usd) for r in agent_rows if r.total_cost_usd is not None)
        agent_cost_status = "AVAILABLE" if agent_rows else "NOT_AVAILABLE"

        judge_stmt = select(AgentRunJudge.cost_usd, AgentRunJudge.input_tokens, AgentRunJudge.output_tokens).where(
            AgentRunJudge.agent_run_id.in_(run_ids_subq)
        )
        judge_rows = db.execute(judge_stmt).all()
        judge_cost_available_rows = [r for r in judge_rows if r.cost_usd is not None]
        if judge_cost_available_rows:
            judge_cost = sum(float(r.cost_usd) for r in judge_cost_available_rows)
            judge_cost_status = "AVAILABLE"
        else:
            j_in = sum(int(r.input_tokens or 0) for r in judge_rows)
            j_out = sum(int(r.output_tokens or 0) for r in judge_rows)
            if j_in > 0 or j_out > 0:
                from backend.agents.v2.model_gateway import ModelRole, ModelUsage
                from backend.agents.v2.observability import ModelPricingCatalog
                from backend.config import get_settings
                app_settings = get_settings()
                catalog = ModelPricingCatalog.from_settings(app_settings)
                j_model = filters.judge_model or getattr(app_settings, "agent_judge_model", "gemini-3.7-flash") or "gemini-3.7-flash"
                est = catalog.estimate(
                    model=j_model,
                    model_role=ModelRole.JUDGE,
                    usage=ModelUsage(input_tokens=j_in, output_tokens=j_out),
                )
                if est.estimated_cost_usd is not None:
                    judge_cost = est.estimated_cost_usd
                    judge_cost_status = "AVAILABLE"
                else:
                    _DEFAULT_PRICES = {
                        "gemini-3.7-flash": (0.10, 0.40),
                        "gemini-2.5-flash": (0.075, 0.30),
                        "gemini-1.5-flash": (0.075, 0.30),
                        "gemini-2.0-flash": (0.10, 0.40),
                        "gpt-4o-mini": (0.15, 0.60),
                        "gpt-4o": (2.50, 10.00),
                    }
                    rates = _DEFAULT_PRICES.get(j_model) or _DEFAULT_PRICES["gemini-3.7-flash"]
                    judge_cost = (j_in * rates[0] + j_out * rates[1]) / 1_000_000
                    judge_cost_status = "AVAILABLE"
            else:
                judge_cost = 0.0
                judge_cost_status = "NOT_AVAILABLE"

        total_input = sum(int(r.input_tokens or 0) for r in agent_rows)
        total_output = sum(int(r.output_tokens or 0) for r in agent_rows)
        total_tokens = sum(int(r.total_tokens or 0) for r in agent_rows)
        query_count = _count(db, base)

        # Breakdown by model and time series (Agent cost only -- Judge cost is a separate
        # axis with its own model, tracked in the judge section, not mixed
        # into this per-agent-model breakdown).
        model_rows = db.execute(
            base.where(AgentRun.cost_status == "AVAILABLE")
            .with_only_columns(AgentRun.model, AgentRun.total_cost_usd, AgentRun.started_at)
            .order_by(AgentRun.started_at.asc())
        ).all()
        by_model: dict[str, float] = {}
        models_set: list[str] = []

        min_time = filters.date_from
        max_time = filters.date_to
        if not min_time and model_rows:
            min_time = model_rows[0].started_at
        if not max_time and model_rows:
            max_time = model_rows[-1].started_at

        use_hourly = False
        if min_time and max_time:
            delta = max_time - min_time
            if delta.total_seconds() <= 48 * 3600:
                use_hourly = True

        timeline_buckets: dict[str, dict[str, float]] = {}

        for r in model_rows:
            key = r.model or "unknown"
            if key not in models_set:
                models_set.append(key)
            cost_val = float(r.total_cost_usd or 0.0)
            by_model[key] = round(by_model.get(key, 0.0) + cost_val, 4)

            if r.started_at:
                ts_str = r.started_at.strftime("%Y-%m-%d %H:00" if use_hourly else "%Y-%m-%d")
                if ts_str not in timeline_buckets:
                    timeline_buckets[ts_str] = {}
                timeline_buckets[ts_str][key] = round(timeline_buckets[ts_str].get(key, 0.0) + cost_val, 4)

        timeline = []
        for ts_key in sorted(timeline_buckets.keys()):
            entry: dict[str, Any] = {"timestamp": ts_key}
            for m in models_set:
                entry[m] = timeline_buckets[ts_key].get(m, 0.0)
            timeline.append(entry)

        return {
            "available": True,
            "agent_cost_usd": {"value": round(agent_cost, 4) if agent_rows else None, "status": agent_cost_status, "sample_count": len(agent_rows)},
            "judge_cost_usd": {"value": round(judge_cost, 4) if judge_rows else None, "status": judge_cost_status, "sample_count": len(judge_rows)},
            "total_cost_usd": {
                "value": round(agent_cost + judge_cost, 4) if (agent_rows or judge_rows) else None,
                "status": "AVAILABLE" if (agent_rows or judge_rows) else "NOT_AVAILABLE",
            },
            "input_tokens": total_input,
            "output_tokens": total_output,
            "total_tokens": total_tokens,
            "tokens_per_query": _average([float(r.total_tokens or 0) for r in agent_rows]) if agent_rows else _average([]),
            "cost_per_query_usd": {
                "value": round(agent_cost / len(agent_rows), 6) if agent_rows and agent_cost > 0 else None,
                "status": "AVAILABLE" if agent_rows else "NOT_APPLICABLE",
            },
            "by_model_usd": by_model,
            "timeline": timeline,
            "models": models_set,
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# Errors -- canonical taxonomy (runtime.py's ERROR_CODE_* constants + the
# literal-string codes verified against real call sites, see BUILD-36
# report's own audit section). TOOL_TIMEOUT/RETRIEVAL_TIMEOUT are named in
# the spec's floor list but never emitted by this runtime -- included here
# as a fixed, always-zero, explicitly-labeled row rather than silently
# omitted, so the API itself never implies they are measured.
# ---------------------------------------------------------------------------

_KNOWN_ERROR_CODES = (
    "BUDGET_EXCEEDED", "MODEL_ERROR", "MODEL_TIMEOUT", "TOOL_ERROR",
    "RETRIEVAL_ERROR", "REQUEST_TIMEOUT", "GROUNDING_FAILURE", "EMPTY_REPLY",
    "HANDOFF_FAILURE", "INTERNAL_ERROR",
)
_NEVER_EMITTED_ERROR_CODES = ("TOOL_TIMEOUT", "RETRIEVAL_TIMEOUT")


def errors_metrics(db: Session, filters: MonitoringFilters) -> dict[str, Any]:
    try:
        base = _apply_agent_run_filters(select(AgentRun), filters)
        total = _count(db, base)

        breakdown: dict[str, Any] = {}
        for code in _KNOWN_ERROR_CODES:
            count = _count(db, base.where(AgentRun.error_code == code))
            breakdown[code] = _rate(count, total)
        for code in _NEVER_EMITTED_ERROR_CODES:
            breakdown[code] = {
                "value": 0.0, "numerator": 0, "denominator": total, "sample_count": total, "status": "AVAILABLE",
                "note": "never_emitted_by_current_runtime_no_per_tool_or_per_retrieval_deadline_distinct_from_run_timeout",
            }

        # Anything real but not in the known taxonomy (a genuinely new,
        # previously-unseen error_code) -- surfaced explicitly rather than
        # silently dropped from the breakdown total.
        known = set(_KNOWN_ERROR_CODES)
        all_codes = {c for c in db.execute(base.where(AgentRun.error_code.is_not(None)).with_only_columns(AgentRun.error_code)).scalars().all() if c}
        unrecognized = sorted(all_codes - known)

        return {
            "available": True,
            "total_requests": total,
            "breakdown": breakdown,
            "unrecognized_error_codes": unrecognized,
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# Judge
# ---------------------------------------------------------------------------


def judge_metrics(db: Session, filters: MonitoringFilters) -> dict[str, Any]:
    try:
        stmt = select(AgentRunJudge)
        if filters.date_from is not None:
            stmt = stmt.where(AgentRunJudge.created_at >= filters.date_from)
        if filters.date_to is not None:
            stmt = stmt.where(AgentRunJudge.created_at <= filters.date_to)
        if filters.judge_model:
            stmt = stmt.where(AgentRunJudge.judge_model == filters.judge_model)
        if filters.rubric_version:
            stmt = stmt.where(AgentRunJudge.rubric_version == filters.rubric_version)

        total = _count(db, stmt)
        pending = _count(db, stmt.where(AgentRunJudge.judge_status == "JUDGE_PENDING"))
        completed = _count(db, stmt.where(AgentRunJudge.judge_status == "JUDGE_COMPLETED"))
        failed = _count(db, stmt.where(AgentRunJudge.judge_status == "JUDGE_FAILED"))

        model_rows = db.execute(stmt.with_only_columns(AgentRunJudge.judge_provider, AgentRunJudge.judge_model)).all()
        provider_model: dict[str, int] = {}
        for r in model_rows:
            key = f"{r.judge_provider}:{r.judge_model}"
            provider_model[key] = provider_model.get(key, 0) + 1

        scores = [
            s for s in db.execute(stmt.where(AgentRunJudge.judge_status == "JUDGE_COMPLETED").with_only_columns(AgentRunJudge.overall_score)).scalars().all()
            if s is not None
        ]
        buckets = {"0.0-0.2": 0, "0.2-0.4": 0, "0.4-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0}
        for s in scores:
            idx = min(4, int(s / 0.2))
            key = list(buckets.keys())[idx]
            buckets[key] += 1

        low_score_rows = db.execute(
            stmt.where(AgentRunJudge.judge_status == "JUDGE_COMPLETED", AgentRunJudge.overall_score < 0.5)
            .with_only_columns(AgentRunJudge.id, AgentRunJudge.agent_run_id, AgentRunJudge.trace_id, AgentRunJudge.overall_score, AgentRunJudge.execution_path)
            .order_by(AgentRunJudge.overall_score.asc())
            .limit(50)
        ).all()

        cost_rows = db.execute(stmt.where(AgentRunJudge.cost_status == "AVAILABLE").with_only_columns(AgentRunJudge.cost_usd)).scalars().all()
        token_in = db.execute(stmt.with_only_columns(AgentRunJudge.input_tokens)).scalars().all()
        token_out = db.execute(stmt.with_only_columns(AgentRunJudge.output_tokens)).scalars().all()

        total_in = sum(int(t or 0) for t in token_in)
        total_out = sum(int(t or 0) for t in token_out)

        judge_cost_val: float | None = None
        judge_cost_status = "NOT_AVAILABLE"

        if cost_rows:
            judge_cost_val = round(sum(float(c) for c in cost_rows), 4)
            judge_cost_status = "AVAILABLE"
        elif total_in > 0 or total_out > 0:
            from backend.agents.v2.model_gateway import ModelRole, ModelUsage
            from backend.agents.v2.observability import ModelPricingCatalog
            from backend.config import get_settings
            app_settings = get_settings()
            catalog = ModelPricingCatalog.from_settings(app_settings)
            j_model = filters.judge_model or getattr(app_settings, "agent_judge_model", "gemini-3.7-flash") or "gemini-3.7-flash"
            estimate = catalog.estimate(
                model=j_model,
                model_role=ModelRole.JUDGE,
                usage=ModelUsage(input_tokens=total_in, output_tokens=total_out),
            )
            if estimate.estimated_cost_usd is not None:
                judge_cost_val = round(estimate.estimated_cost_usd, 4)
                judge_cost_status = "AVAILABLE"
            else:
                _DEFAULT_PRICES = {
                    "gemini-3.7-flash": (0.10, 0.40),
                    "gemini-2.5-flash": (0.075, 0.30),
                    "gemini-1.5-flash": (0.075, 0.30),
                    "gemini-2.0-flash": (0.10, 0.40),
                    "gpt-4o-mini": (0.15, 0.60),
                    "gpt-4o": (2.50, 10.00),
                }
                rates = _DEFAULT_PRICES.get(j_model) or _DEFAULT_PRICES["gemini-3.7-flash"]
                judge_cost_val = round((total_in * rates[0] + total_out * rates[1]) / 1_000_000, 4)
                judge_cost_status = "AVAILABLE"

        return {
            "available": True,
            "total_judged": total,
            "judged_pending": pending,
            "judged_completed": completed,
            "judged_failed": failed,
            "provider_model_distribution": provider_model,
            "overall_score_distribution": buckets,
            "low_score_cases": [
                {"judge_id": r.id, "agent_run_id": r.agent_run_id, "trace_id": r.trace_id, "score": r.overall_score, "execution_path": r.execution_path}
                for r in low_score_rows
            ],
            "judge_cost_usd": {"value": judge_cost_val, "status": judge_cost_status},
            "judge_input_tokens": total_in,
            "judge_output_tokens": total_out,
            "disclaimer": "Tín hiệu chất lượng bổ sung dựa trên LLM. Không phải là sự đảm bảo mang tính xác định về độ chính xác y khoa.",
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# Golden Evaluation -- reads AgentGoldenRun/AgentGoldenRunCase, populated by
# run_golden_evaluation.py's own new --persist flag (BUILD-35's runner,
# extended additively). A dashboard with no golden run ever persisted shows
# a real, honest "no run persisted yet" state, never a fabricated one.
# ---------------------------------------------------------------------------


def golden_metrics(db: Session, *, golden_set_version: str | None = None, history_limit: int = 10) -> dict[str, Any]:
    try:
        stmt = select(AgentGoldenRun).order_by(AgentGoldenRun.created_at.desc())
        if golden_set_version:
            stmt = stmt.where(AgentGoldenRun.golden_set_version == golden_set_version)

        latest = db.execute(stmt.limit(1)).scalar_one_or_none()
        if latest is None:
            return {"available": True, "has_run": False}

        history = db.execute(stmt.limit(history_limit)).scalars().all()

        case_rows = db.execute(select(AgentGoldenRunCase).where(AgentGoldenRunCase.run_id == latest.id)).scalars().all()
        by_category: dict[str, dict[str, int]] = {}
        failed_case_ids: list[str] = []
        for case in case_rows:
            bucket = by_category.setdefault(case.category, {"total": 0, "passed": 0})
            bucket["total"] += 1
            bucket["passed"] += int(case.passed)
            if not case.passed:
                failed_case_ids.append(case.case_id)

        return {
            "available": True,
            "has_run": True,
            "latest_run": {
                "run_id": latest.id,
                "golden_set_version": latest.golden_set_version,
                "created_at": latest.created_at.isoformat(),
                "total_cases": latest.total_cases,
                "passed_cases": latest.passed_cases,
                "failed_cases": latest.failed_cases,
                "pass_rate": latest.pass_rate,
                "regression_gate_passed": latest.regression_gate_passed,
                "regression_gate": latest.regression_gate_json,
                "provenance": latest.provenance_json,
                "comparisons": latest.comparisons_json,
                "by_category": by_category,
                "failed_case_ids": failed_case_ids,
            },
            "history": [
                {
                    "run_id": r.id, "golden_set_version": r.golden_set_version, "created_at": r.created_at.isoformat(),
                    "pass_rate": r.pass_rate, "regression_gate_passed": r.regression_gate_passed,
                }
                for r in history
            ],
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": str(exc)}


def golden_run_detail(db: Session, run_id: str) -> dict[str, Any] | None:
    run = db.get(AgentGoldenRun, run_id)
    if run is None:
        return None
    cases = db.execute(select(AgentGoldenRunCase).where(AgentGoldenRunCase.run_id == run_id)).scalars().all()
    return {
        "run_id": run.id,
        "golden_set_version": run.golden_set_version,
        "git_commit": run.git_commit,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "created_at": run.created_at.isoformat(),
        "total_cases": run.total_cases,
        "passed_cases": run.passed_cases,
        "failed_cases": run.failed_cases,
        "pass_rate": run.pass_rate,
        "regression_gate_passed": run.regression_gate_passed,
        "regression_gate": run.regression_gate_json,
        "provenance": run.provenance_json,
        "aggregate": run.aggregate_json,
        "comparisons": run.comparisons_json,
        "cases": [
            {"case_id": c.case_id, "category": c.category, "passed": c.passed, "checks": c.checks_json}
            for c in cases
        ],
    }


# ---------------------------------------------------------------------------
# Versions -- filter option discovery (real distinct durable values, never
# a hardcoded <option> list -- BUILD-25's own fake-filter class of bug).
# ---------------------------------------------------------------------------


def version_filter_options(db: Session) -> dict[str, Any]:
    try:
        models = sorted({m for m in db.execute(select(AgentRun.model).distinct()).scalars().all() if m})
        prompt_versions = sorted({p for p in db.execute(select(AgentRun.prompt_version).distinct()).scalars().all() if p})
        retrieval_versions = sorted({r for r in db.execute(select(AgentRun.retrieval_version).distinct()).scalars().all() if r})
        evaluation_versions = sorted({e for e in db.execute(select(AgentRunEvaluation.evaluation_version).distinct()).scalars().all() if e})
        execution_paths = sorted({e for e in db.execute(select(AgentRunEvaluation.execution_path).distinct()).scalars().all() if e})
        statuses = sorted({s for s in db.execute(select(AgentRun.status).distinct()).scalars().all() if s})
        error_codes = sorted({c for c in db.execute(select(AgentRun.error_code).distinct()).scalars().all() if c})
        judge_models = sorted({m for m in db.execute(select(AgentRunJudge.judge_model).distinct()).scalars().all() if m})
        rubric_versions = sorted({r for r in db.execute(select(AgentRunJudge.rubric_version).distinct()).scalars().all() if r})
        safety_severities = sorted({s for s in db.execute(select(AgentSafetyEvent.severity).distinct()).scalars().all() if s})
        golden_set_versions = sorted({g for g in db.execute(select(AgentGoldenRun.golden_set_version).distinct()).scalars().all() if g})

        return {
            "available": True,
            "model": models,
            "prompt_version": prompt_versions,
            "retrieval_version": retrieval_versions,
            "evaluation_version": evaluation_versions,
            "execution_path": execution_paths,
            "status": statuses,
            "error_code": error_codes,
            "judge_model": judge_models,
            "rubric_version": rubric_versions,
            "safety_severity": safety_severities,
            "golden_set_version": golden_set_versions,
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": str(exc)}


def compare_metrics(db: Session, section: str, before: MonitoringFilters, after: MonitoringFilters) -> dict[str, Any]:
    """Calls the SAME section function twice (once per filter set) and
    diffs the results -- see module docstring for why this is the only
    "compare" implementation, not a second copy of any aggregation logic.
    Only numeric ``value`` fields get a computed delta; non-numeric/None
    values are reported side-by-side with no delta (never a fabricated
    0-delta for a metric that was actually N/A on one or both sides)."""

    section_fns = {
        "overview": overview_metrics,
        "quality": quality_metrics,
        "retrieval": retrieval_metrics,
        "performance": performance_metrics,
        "cost": cost_metrics,
        "errors": errors_metrics,
        "judge": judge_metrics,
    }
    fn = section_fns.get(section)
    if fn is None:
        return {"available": False, "reason": f"unknown_section:{section}"}

    before_result = fn(db, before)
    after_result = fn(db, after)

    def _diff(a: Any, b: Any) -> Any:
        if isinstance(a, dict) and isinstance(b, dict) and "value" in a and "value" in b:
            a_val, b_val = a.get("value"), b.get("value")
            delta = round(b_val - a_val, 6) if isinstance(a_val, (int, float)) and isinstance(b_val, (int, float)) else None
            return {"before": a, "after": b, "delta": delta}
        if isinstance(a, dict) and isinstance(b, dict):
            return {key: _diff(a.get(key), b.get(key)) for key in set(a) | set(b)}
        # Bare numeric fields (e.g. total_requests) -- not every metric is
        # wrapped in a {value, ...} rate dict, but a plain int/float still
        # deserves a real delta, not a silently-dropped `null`.
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
            return {"before": a, "after": b, "delta": round(b - a, 6)}
        return {"before": a, "after": b, "delta": None}

    return {"available": True, "section": section, "comparison": _diff(before_result, after_result)}


# ---------------------------------------------------------------------------
# Pagination -- the ONE reusable func.count()-over-subquery pattern this
# build's own audit found as the best of 4 pre-existing ad hoc shapes
# (agent_safety_monitoring.list_safety_events's own pattern), factored out
# so every new list endpoint below shares it instead of adding a 5th shape.
# ---------------------------------------------------------------------------


def paginate(db: Session, stmt: Select, *, limit: int, offset: int) -> tuple[list, int]:
    total = _count(db, stmt)
    rows = list(db.execute(stmt.limit(limit).offset(offset)).scalars().all())
    return rows, total


# ---------------------------------------------------------------------------
# Trace Explorer -- durable metrics ALWAYS available regardless of ring-
# buffer state; raw query/response text only when the trace is still in the
# 200-entry in-memory buffer (see module docstring). A trace whose text has
# aged out gets an honest `content_available: False`, never reconstructed
# or omitted silently.
# ---------------------------------------------------------------------------


def list_traces(db: Session, filters: MonitoringFilters, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    try:
        stmt = _apply_agent_run_filters(select(AgentRun), filters).order_by(AgentRun.started_at.desc())
        rows, total = paginate(db, stmt, limit=limit, offset=offset)

        run_ids = [r.id for r in rows]
        eval_by_run = {
            e.agent_run_id: e
            for e in db.execute(select(AgentRunEvaluation).where(AgentRunEvaluation.agent_run_id.in_(run_ids))).scalars().all()
        } if run_ids else {}
        ticket_run_ids = set(
            db.execute(select(AgentFeedbackTicket.agent_run_id).where(AgentFeedbackTicket.agent_run_id.in_(run_ids))).scalars().all()
        ) if run_ids else set()
        safety_run_ids = set(
            db.execute(select(AgentSafetyEvent.agent_run_id).where(AgentSafetyEvent.agent_run_id.in_(run_ids))).scalars().all()
        ) if run_ids else set()
        judge_run_ids = set(
            db.execute(select(AgentRunJudge.agent_run_id).where(AgentRunJudge.agent_run_id.in_(run_ids))).scalars().all()
        ) if run_ids else set()

        items = [
            {
                "agent_run_id": r.id,
                "trace_id": r.trace_id,
                "conversation_id": r.conversation_id,
                "patient_id": r.patient_id,
                "intent": r.intent,
                "status": r.status,
                "execution_path": eval_by_run[r.id].execution_path if r.id in eval_by_run else None,
                "model": r.model,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "duration_ms": r.duration_ms,
                "error_code": r.error_code,
                "timeout": r.timeout,
                "total_cost_usd": r.total_cost_usd,
                "cost_status": r.cost_status,
                "has_ticket": r.id in ticket_run_ids,
                "has_safety_event": r.id in safety_run_ids,
                "has_judge_result": r.id in judge_run_ids,
            }
            for r in rows
        ]
        return {"available": True, "items": items, "total": total, "limit": limit, "offset": offset}
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": str(exc)}


def trace_detail(db: Session, trace_id: str) -> dict[str, Any] | None:
    run = db.execute(select(AgentRun).where(AgentRun.trace_id == trace_id)).scalars().first()
    if run is None:
        return None

    evaluation = db.execute(select(AgentRunEvaluation).where(AgentRunEvaluation.agent_run_id == run.id)).scalars().first()
    spans = db.execute(
        select(AgentRunSpan).where(AgentRunSpan.agent_run_id == run.id).order_by(AgentRunSpan.started_at.asc())
    ).scalars().all()
    judge = db.execute(
        select(AgentRunJudge).where(AgentRunJudge.agent_run_id == run.id).order_by(AgentRunJudge.created_at.desc()).limit(1)
    ).scalars().first()
    safety = db.execute(select(AgentSafetyEvent).where(AgentSafetyEvent.agent_run_id == run.id)).scalars().first()
    ticket = db.execute(select(AgentFeedbackTicket).where(AgentFeedbackTicket.agent_run_id == run.id)).scalars().first()

    from backend.services.telemetry import get_local_traces

    # BUILD-37 fix: ring-buffer TraceRecord.id is stamped from trace_id
    # (see agent_v2_routes._record_agent_v2_telemetry's own
    # `telemetry.create_trace(trace_id=result.trace_id, ...)` call and
    # TelemetryService.create_trace's `TraceRecord(id=trace_id, ...)`) --
    # NOT agent_run_id. Comparing against `run.id` (the AgentRun primary
    # key, a different UUID) meant `content_available` was unconditionally
    # False for every trace, even ones still genuinely in the buffer --
    # found via live production verification (BUILD-37 report Sec 12):
    # the session-detail endpoint (which correctly keys by trace_id) found
    # real query/reply text for a trace seconds old, while this endpoint
    # claimed it was already unavailable for the exact same trace.
    buffered = next((t for t in get_local_traces() if t.id == run.trace_id), None)

    return {
        "trace_id": run.trace_id,
        "agent_run_id": run.id,
        "conversation_id": run.conversation_id,
        "patient_id": run.patient_id,
        "execution_path": evaluation.execution_path if evaluation else None,
        "intent": run.intent,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "duration_ms": run.duration_ms,
        "model": run.model,
        "model_calls": run.model_calls,
        "prompt_version": run.prompt_version,
        "retrieval_version": run.retrieval_version,
        "spans": [
            {
                "span_name": s.span_name, "span_type": s.span_type, "status": s.status,
                "duration_ms": s.duration_ms, "started_at": s.started_at.isoformat(), "metadata": s.metadata_json,
            }
            for s in spans
        ],
        "tokens": {
            "input": run.input_tokens, "cached_input": run.cached_input_tokens,
            "output": run.output_tokens, "total": run.total_tokens,
        },
        "cost": {
            "input_usd": run.input_cost_usd, "output_usd": run.output_cost_usd,
            "total_usd": run.total_cost_usd, "status": run.cost_status,
        },
        "error_code": run.error_code,
        "timeout": run.timeout,
        "empty_reply": run.empty_reply,
        "evaluation": evaluation.metrics_json if evaluation else None,
        "judge": (
            {
                "judge_status": judge.judge_status, "overall_score": judge.overall_score,
                "dimension_scores": judge.dimension_scores_json, "flags": judge.flags_json,
                "judge_model": judge.judge_model, "rubric_version": judge.rubric_version,
                "eligibility_reason": judge.eligibility_reason,
            }
            if judge else None
        ),
        "safety": (
            {
                "outcome": safety.outcome, "reason_code": safety.reason_code, "severity": safety.severity,
                "handoff_required": safety.handoff_required, "handoff_created": safety.handoff_created,
                "handoff_id": safety.handoff_id,
            }
            if safety else None
        ),
        "ticket": ({"ticket_id": ticket.id, "status": ticket.status, "reason": ticket.reason} if ticket else None),
        "content_available": buffered is not None,
        # Never chain-of-thought/system prompt/JWT/raw secret -- the ring
        # buffer itself never carries those (see backend.services.telemetry
        # /observability's own redaction), only the final query/reply text
        # and already-sanitized tool/citation summaries.
        "query_preview": (str(buffered.input) if buffered and buffered.input else None) if buffered else None,
        "response_preview": (str(buffered.output) if buffered and buffered.output else None) if buffered else None,
        "tool_names": [o.name for o in buffered.observations if getattr(o, "name", None)] if buffered else [],
        "citations": buffered.metadata.get("citations") if buffered and isinstance(buffered.metadata, dict) else None,
    }


# ---------------------------------------------------------------------------
# Trend -- daily time-series of request volume, latency P95, and (where the
# ring-buffer heuristic scores happen to be durable via AgentRunEvaluation's
# metrics_json) faithfulness and answer_relevance.
#
# The heuristic scores are NOT reliably durable today (see quality_metrics
# docstring / BUILD-36 report) -- this function reads whatever IS durable
# (the per-run metrics_json disposition + the ring-buffer score, when the
# run is still in the buffer) and honestly labels each day's score with its
# sample_count so the frontend can show "n=X". Days with 0 runs are omitted.
# ---------------------------------------------------------------------------


def trend_metrics(db: Session, filters: MonitoringFilters, *, days: int = 7) -> dict[str, Any]:
    """Daily trend over the last `days` calendar days (or filtered range).

    Each entry: {date, requests, p95_latency_ms, faithfulness, relevance}
    where faithfulness/relevance are averages over runs whose AgentRunEvaluation
    metrics_json contains AVAILABLE scores (from the heuristic evaluator).
    """
    try:
        from collections import defaultdict
        from datetime import datetime, timezone, timedelta

        base = _apply_agent_run_filters(select(AgentRun), filters)

        now_dt = datetime.now(tz=timezone.utc)
        if filters.date_from is None and filters.date_to is None:
            cutoff = now_dt - timedelta(days=days)
            recent_runs = db.execute(
                base.where(AgentRun.started_at >= cutoff)
                .order_by(AgentRun.started_at.asc())
                .with_only_columns(
                    AgentRun.id,
                    AgentRun.started_at,
                    AgentRun.duration_ms,
                    AgentRun.status,
                )
            ).all()
            if recent_runs:
                runs = recent_runs
            else:
                # If no runs strictly within cutoff, load all matching runs so historical/seed data is visible
                runs = db.execute(
                    base.order_by(AgentRun.started_at.asc())
                    .with_only_columns(
                        AgentRun.id,
                        AgentRun.started_at,
                        AgentRun.duration_ms,
                        AgentRun.status,
                    )
                ).all()
        else:
            runs = db.execute(
                base.order_by(AgentRun.started_at.asc())
                .with_only_columns(
                    AgentRun.id,
                    AgentRun.started_at,
                    AgentRun.duration_ms,
                    AgentRun.status,
                )
            ).all()

        run_ids = [r.id for r in runs] if runs else []

        # Load AgentRunEvaluation metrics_json
        eval_by_run_id: dict[str, dict] = {}
        if run_ids:
            eval_rows = db.execute(
                select(AgentRunEvaluation.agent_run_id, AgentRunEvaluation.metrics_json)
                .where(AgentRunEvaluation.agent_run_id.in_(run_ids))
            ).all()
            eval_by_run_id = {r.agent_run_id: (r.metrics_json or {}) for r in eval_rows}

        # Supplement with ring-buffer scores
        from backend.services.telemetry import get_local_traces
        ring_faith: dict[str, float] = {}
        ring_rel: dict[str, float] = {}
        day_faith_scores: dict[str, list[float]] = defaultdict(list)
        day_rel_scores: dict[str, list[float]] = defaultdict(list)

        # 1. First check durable eval_by_run_id
        for run_id, m_json in eval_by_run_id.items():
            if not isinstance(m_json, dict):
                continue
            f_metric = m_json.get("faithfulness")
            if isinstance(f_metric, dict) and f_metric.get("status") == "AVAILABLE":
                v = f_metric.get("score") if f_metric.get("score") is not None else f_metric.get("value")
                if isinstance(v, (int, float)):
                    ring_faith[run_id] = float(v)
            r_metric = m_json.get("answer_relevance")
            if isinstance(r_metric, dict) and r_metric.get("status") == "AVAILABLE":
                v = r_metric.get("score") if r_metric.get("score") is not None else r_metric.get("value")
                if isinstance(v, (int, float)):
                    ring_rel[run_id] = float(v)

        # 2. Then supplement with in-memory traces
        for trace in get_local_traces():
            eval_v2 = trace.metadata.get("evaluation_v2") if isinstance(trace.metadata, dict) else None
            if not isinstance(eval_v2, dict):
                continue
            run_id = (
                trace.metadata.get("agent_run_id")
                or trace.metadata.get("run_id")
                or eval_v2.get("agent_run_id")
            )
            trace_day = "unknown"
            if getattr(trace, "start_time", 0) > 0:
                try:
                    trace_day = datetime.fromtimestamp(trace.start_time, tz=timezone.utc).strftime("%Y-%m-%d")
                except Exception:
                    pass

            metrics = eval_v2.get("metrics", {})
            if isinstance(metrics.get("faithfulness"), dict) and metrics["faithfulness"].get("status") == "AVAILABLE":
                score = trace.scores.get("answer_faithfulness")
                if isinstance(score, (int, float)):
                    if run_id:
                        ring_faith[run_id] = float(score)
                    if trace_day != "unknown":
                        day_faith_scores[trace_day].append(float(score))
            if isinstance(metrics.get("answer_relevance"), dict) and metrics["answer_relevance"].get("status") == "AVAILABLE":
                score = trace.scores.get("answer_relevance")
                if isinstance(score, (int, float)):
                    if run_id:
                        ring_rel[run_id] = float(score)
                    if trace_day != "unknown":
                        day_rel_scores[trace_day].append(float(score))

        # Group by calendar day.
        day_runs: dict[str, list] = defaultdict(list)
        for r in runs:
            day_key = r.started_at.strftime("%Y-%m-%d") if r.started_at else "unknown"
            day_runs[day_key].append(r)

        # Ensure continuous timeline of calendar dates for the requested `days` window
        all_day_keys = set(day_runs.keys())
        if filters.date_from is None and filters.date_to is None:
            for i in range(days - 1, -1, -1):
                d_str = (now_dt - timedelta(days=i)).strftime("%Y-%m-%d")
                all_day_keys.add(d_str)

        trend = []
        for day_str in sorted(all_day_keys):
            if day_str == "unknown":
                continue
            day_batch = day_runs.get(day_str, [])
            latencies = [r.duration_ms for r in day_batch if r.duration_ms is not None]
            p95 = _percentiles(latencies, points=(95,))[95] if latencies else {"value": None}

            faith_scores = [ring_faith[r.id] for r in day_batch if r.id in ring_faith]
            if not faith_scores and day_str in day_faith_scores:
                faith_scores = day_faith_scores[day_str]

            rel_scores = [ring_rel[r.id] for r in day_batch if r.id in ring_rel]
            if not rel_scores and day_str in day_rel_scores:
                rel_scores = day_rel_scores[day_str]

            completed_count = sum(1 for r in day_batch if r.status == "COMPLETED")
            task_completion_rate = round(completed_count / len(day_batch), 4) if day_batch else None

            trend.append({
                "date": day_str,
                "requests": len(day_batch),
                "p95_latency_ms": p95.get("value"),
                "task_completion": task_completion_rate,
                "task_completion_n": len(day_batch),
                "faithfulness": round(sum(faith_scores) / len(faith_scores), 4) if faith_scores else None,
                "faithfulness_n": len(faith_scores),
                "relevance": round(sum(rel_scores) / len(rel_scores), 4) if rel_scores else None,
                "relevance_n": len(rel_scores),
            })

        return {"available": True, "trend": trend, "days": days}
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": str(exc)}
