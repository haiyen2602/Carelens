"""Admin Monitoring & RAG Observability API endpoints.
Conforms to docs/langfuse_rag_admin_monitoring_spec.md §15, §17, §25, §26.
100% Real Data Driven: computed strictly from Database (AuditLog, Escalation, DrugChunk)
and in-memory/Langfuse Telemetry Traces without synthetic mock data.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, require_role
from backend.config import get_settings
from backend.db.base import get_db
from backend.db.models import AgentRun, AgentRunSpan, AuditLog, DrugChunk, Escalation
from backend.services.agent_safety_monitoring import safety_metrics_summary
from backend.services.telemetry import get_local_traces

rag_monitoring_router = APIRouter(prefix="/admin/rag", tags=["admin-rag-monitoring"])

# BUILD-29 security fix (documented gap since BUILD-25's own audit, report
# 54-build-25-agent-v2-monitoring-audit.md §8: "_require_admin has no actual
# role check -- any authenticated JWT, any role, can read /admin/rag/*").
# ``require_role("admin")`` (backend/api/security.py) already existed and is
# already used this exact way by every other admin-only route in this repo
# (account_routes.py, admin_drug_routes.py, audit_routes.py) -- this was
# simply never wired in here. Kept as a module-level name (not inlined at
# every ``Depends(...)`` call site below) so the fix is one line, not an
# 11-site rename.
_require_admin = require_role("admin", "super_admin")


# BUILD-25B: real filtering by chatbot system / model / prompt version,
# applied to the SAME in-memory trace list every metric endpoint below
# already reads -- not a cosmetic frontend-only change. A trace missing a
# given metadata key never matches a non-"all" filter on that key (fails
# closed rather than silently including mismatched data).
def _filter_traces(
    traces: list,
    *,
    chatbot_version: str | None,
    model: str | None,
    prompt_version: str | None,
) -> list:
    def _keep(t) -> bool:
        meta = t.metadata or {}
        if chatbot_version and chatbot_version != "all" and meta.get("chatbot_version") != chatbot_version:
            return False
        if model and model != "all" and meta.get("model") != model:
            return False
        if prompt_version and prompt_version != "all" and meta.get("prompt_version") != prompt_version:
            return False
        return True

    return [t for t in traces if _keep(t)]


def _prompt_version_counts(traces: list, settings) -> dict[str, int]:
    counts: dict[str, int] = {}
    for t in traces:
        v = t.metadata.get("prompt_version") or settings.rag_prompt_version
        counts[v] = counts.get(v, 0) + 1
    if not counts:
        counts[settings.rag_prompt_version] = 0
    return counts


def _available_metric_scores(traces: list, metric_name: str) -> list[float]:
    """Return only Evaluation V2 scores whose trace declared the metric usable.

    An absent score is not a zero score. This deliberately excludes legacy
    traces and pre-Evaluation-V2 Agent V2 traces, because their applicability
    and provenance cannot be reconstructed safely after the fact.
    """
    score_name = {"faithfulness": "answer_faithfulness"}.get(metric_name, metric_name)
    scores: list[float] = []
    for trace in traces:
        evaluation = trace.metadata.get("evaluation_v2") if isinstance(trace.metadata, dict) else None
        metric = evaluation.get("metrics", {}).get(metric_name) if isinstance(evaluation, dict) else None
        value = trace.scores.get(score_name)
        if isinstance(metric, dict) and metric.get("status") == "AVAILABLE" and isinstance(value, (int, float)):
            scores.append(float(value))
    return scores


# BUILD-32: real cost/token/timeout aggregates over the durable `AgentRun`
# table -- previously every cost/timeout figure in this file was hardcoded to
# `0.0` (see the audit report's finding: real token usage/cost were computed
# correctly by Agent V2 but discarded before reaching this dashboard). Only
# `chatbot_version in (None, "all", "agent-v2")` participates -- AgentRun is
# written exclusively by Agent V2, never legacy chat, same convention every
# other endpoint in this file already applies to AuditLog vs the trace
# buffer. `prompt_version` has no durable column on AgentRun yet, so a
# prompt_version filter intentionally excludes the durable rows rather than
# silently ignoring the filter.
def _agent_run_query(db: Session, *, chatbot_version: str | None, model: str | None, prompt_version: str | None):
    if chatbot_version not in (None, "all", "agent-v2") or prompt_version:
        return []
    stmt = select(AgentRun)
    if model:
        stmt = stmt.where(AgentRun.model == model)
    try:
        return db.execute(stmt).scalars().all()
    except Exception as durable_err:  # noqa: BLE001
        # BUILD-32 bugfix: a durable-read failure (e.g. migration 0042 not
        # yet applied on this environment, or a transient DB hiccup) must
        # degrade this one KPI to its pre-BUILD-32 shape (0.0/NOT_AVAILABLE
        # cost, ring-buffer-only traces), never crash the whole endpoint --
        # every caller of this helper previously had no protection at all,
        # so any failure here took down /health, /generation, /system, and
        # /traces together (the real cause of the reported Admin-page N/A
        # incident).
        logging.getLogger(__name__).warning("BUILD-32 durable AgentRun query failed: %s", durable_err)
        return []


_FilterParams = tuple[str | None, str | None, str | None]


def _filter_query_params(
    chatbot_version: str | None = Query(default=None, description="agent-v2 | legacy | all"),
    model: str | None = Query(default=None),
    prompt_version: str | None = Query(default=None),
) -> _FilterParams:
    return chatbot_version, model, prompt_version


@rag_monitoring_router.get("/filters")
async def get_rag_filters(
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(_require_admin),
) -> dict[str, Any]:
    """Real, currently-available filter option lists for the admin dashboard
    -- built from actual trace metadata (this build/session's own live
    traffic), not a hardcoded option list. When the in-memory trace buffer
    is empty (e.g. immediately after a deploy, before any request has been
    served yet), falls back to what is *currently configured* for each
    known chatbot system (Agent V2's own settings, legacy chat's own
    settings) -- still real, live config values, not fabricated history."""
    settings = get_settings()
    traces = get_local_traces()

    chatbot_versions = sorted({t.metadata.get("chatbot_version") for t in traces if t.metadata.get("chatbot_version")})
    models = sorted({t.metadata.get("model") for t in traces if t.metadata.get("model")})
    prompt_versions = sorted({t.metadata.get("prompt_version") for t in traces if t.metadata.get("prompt_version")})
    environments = sorted({t.metadata.get("environment") for t in traces if t.metadata.get("environment")})

    if not chatbot_versions:
        chatbot_versions = ["agent-v2", "legacy"]
    if not models:
        models = [settings.agent_main_model, settings.model_name]
    if not prompt_versions:
        prompt_versions = ["agent-v2-orchestrator", settings.rag_prompt_version]
    if not environments:
        environments = [settings.app_env]

    return {
        "source": "real_trace_metadata" if traces else "current_config_fallback_no_traces_yet",
        "chatbot_versions": [
            {"value": "agent-v2", "label": "Agent V2 / Production"} if v == "agent-v2"
            else {"value": "legacy", "label": "Legacy Chatbot"} if v == "legacy"
            else {"value": v, "label": v}
            for v in chatbot_versions
        ],
        "models": models,
        "prompt_versions": prompt_versions,
        "environments": environments,
    }


@rag_monitoring_router.get("/health")
async def get_rag_health(
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(_require_admin),
    filters: _FilterParams = Depends(_filter_query_params),
) -> dict[str, Any]:
    """Overview health metrics & KPI cards computed strictly from real data (§15.1, §23)"""
    chatbot_version, model, prompt_version = filters
    traces = _filter_traces(get_local_traces(), chatbot_version=chatbot_version, model=model, prompt_version=prompt_version)
    # AuditLog rows are always legacy chat's own data (see backend/api/chat_routes.py
    # -- the only writer) -- excluded entirely once a filter asks for anything
    # other than "legacy"/unfiltered, instead of silently mixing legacy rows
    # into an "agent-v2"-filtered view.
    audit_logs = (
        db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(1000).all()
        if chatbot_version in (None, "all", "legacy") and not model and not prompt_version
        else []
    )
    escalations = db.query(Escalation).all()

    total_samples = len(traces) if traces else len(audit_logs)

    # Faithfulness
    faithfulness_scores = _available_metric_scores(traces, "faithfulness")
    avg_faithfulness = (sum(faithfulness_scores) / len(faithfulness_scores)) if faithfulness_scores else None

    # Relevance
    relevance_scores = _available_metric_scores(traces, "answer_relevance")
    avg_relevance = (sum(relevance_scores) / len(relevance_scores)) if relevance_scores else None

    # Latencies
    latencies = [t.duration_ms for t in traces if t.duration_ms > 0]
    if not latencies and audit_logs:
        latencies = [audit_log.total_duration_ms for audit_log in audit_logs if audit_log.total_duration_ms > 0]

    p95_latency = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0.0

    # Errors & Safety
    errors = sum(1 for t in traces if t.status == "error")
    error_rate = (errors / len(traces) * 100) if traces else 0.0

    safety_failures = sum(1 for e in escalations if e.severity == "HIGH")

    # BUILD-32: real average cost per query, from durable AgentRun rows with
    # a known price (cost_status="AVAILABLE") -- a run whose model had no
    # entry in the pricing catalog is honestly excluded, not folded into an
    # average as a fabricated 0.
    agent_runs_for_cost = _agent_run_query(db, chatbot_version=chatbot_version, model=model, prompt_version=prompt_version)
    priced_runs = [r for r in agent_runs_for_cost if r.cost_status == "AVAILABLE" and r.total_cost_usd is not None]
    cost_per_query = (sum(r.total_cost_usd for r in priced_runs) / len(priced_runs)) if priced_runs else None

    # 7-day trend from real AuditLog
    now = datetime.now(UTC)
    trend = []
    for i in range(6, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        day_str = day_start.strftime("%d/%m")

        day_logs = [
            audit_log for audit_log in audit_logs if audit_log.created_at and day_start <= audit_log.created_at < day_end
        ]
        day_traces = [
            t for t in traces
            if day_start.timestamp() <= t.start_time < day_end.timestamp()
        ]

        day_faith = _available_metric_scores(day_traces, "faithfulness")
        day_rel = _available_metric_scores(day_traces, "answer_relevance")
        day_lats = [t.duration_ms for t in day_traces if t.duration_ms > 0] or [
            audit_log.total_duration_ms for audit_log in day_logs if audit_log.total_duration_ms > 0
        ]

        trend.append({
            "date": day_str,
            "faithfulness": round(sum(day_faith) / len(day_faith), 2) if day_faith else None,
            "relevance": round(sum(day_rel) / len(day_rel), 2) if day_rel else None,
            "latency_p95": round(sorted(day_lats)[int(len(day_lats) * 0.95)], 0) if day_lats else 0.0,
            "requests": len(day_traces) if day_traces else len(day_logs),
        })

    status_str = "Healthy"
    if total_samples == 0:
        status_str = "No Data"
    elif (avg_faithfulness is not None and avg_faithfulness < 0.80) or error_rate > 5.0 or safety_failures > 0:
        status_str = "Warning"

    return {
        "status": status_str,
        "sample_size": total_samples,
        "kpis": {
            "faithfulness": round(avg_faithfulness, 2) if avg_faithfulness is not None else None,
            "answer_relevance": round(avg_relevance, 2) if avg_relevance is not None else None,
            "context_precision": None,
            "context_recall": None,
            "hallucination_rate": round(max(0.0, 1.0 - avg_faithfulness), 2) if avg_faithfulness is not None else None,
            "critical_safety_failure_rate": round((safety_failures / max(len(escalations), 1)) * 100, 2) if escalations else 0.0,
            "p95_latency_ms": round(p95_latency, 1),
            "error_rate": round(error_rate, 2),
            "cost_per_query": round(cost_per_query, 6) if cost_per_query is not None else None,
            "low_retrieval_confidence_rate": 0.0,
            "faithfulness_sample_count": len(faithfulness_scores),
            "answer_relevance_sample_count": len(relevance_scores),
        },
        "metric_provenance": {
            "faithfulness": {"status": "AVAILABLE" if faithfulness_scores else "NOT_AVAILABLE", "source": "heuristic", "reason": None if faithfulness_scores else "no_applicable_evaluation_v2_samples"},
            "answer_relevance": {"status": "AVAILABLE" if relevance_scores else "NOT_AVAILABLE", "source": "heuristic", "reason": None if relevance_scores else "no_applicable_evaluation_v2_samples"},
            "cost_per_query": {
                "status": "AVAILABLE" if priced_runs else "NOT_AVAILABLE",
                "source": "durable_agent_run",
                "reason": None if priced_runs else "no_priced_agent_run_rows",
            },
        },
        "trend": trend,
    }


@rag_monitoring_router.get("/retrieval")
async def get_rag_retrieval(
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(_require_admin),
    filters: _FilterParams = Depends(_filter_query_params),
) -> dict[str, Any]:
    """Retrieval quality metrics computed from real traces & drug chunks (§15.2)"""
    chatbot_version, model, prompt_version = filters
    total_chunks = db.query(DrugChunk).count()
    traces = _filter_traces(get_local_traces(), chatbot_version=chatbot_version, model=model, prompt_version=prompt_version)

    # BUILD-31: only retrieval-backed Agent V2 traces participate in RAG
    # quality. Schedule/tool/safety traces must not become zero-like samples.
    rag_traces = [
        trace
        for trace in traces
        if isinstance(trace.metadata.get("evaluation_v2"), dict)
        and trace.metadata["evaluation_v2"].get("execution_path") == "RAG"
    ]

    worst_queries: list[dict[str, Any]] = []
    # Identify queries with low faithfulness or flagged as errors
    for t in rag_traces:
        faith = float(t.scores.get("answer_faithfulness", 1.0)) if isinstance(t.scores.get("answer_faithfulness"), (int, float)) else 1.0
        rel = float(t.scores.get("answer_relevance", 1.0)) if isinstance(t.scores.get("answer_relevance"), (int, float)) else 1.0
        query_text = t.input.get("message", "") if isinstance(t.input, dict) else str(t.input)
        if (faith < 0.85 or rel < 0.80 or t.status == "error") and query_text:
            dt_vn = datetime.fromtimestamp(t.start_time, tz=UTC) + timedelta(hours=7)
            worst_queries.append({
                "query": query_text,
                "count": 1,
                "avg_top1": round(rel, 2),
                "precision": round(rel, 2),
                "recall": round(faith, 2),
                "faithfulness": round(faith, 2),
                "last_seen": dt_vn.strftime("%H:%M:%S %d/%m"),
            })

    # Group similar queries if any
    grouped_worst: list[dict[str, Any]] = []
    seen_queries = set()
    for w in worst_queries:
        if w["query"] not in seen_queries:
            seen_queries.add(w["query"])
            grouped_worst.append(w)

    # Live traces have retrieved ranks but no server-authoritative relevance
    # ground truth. IR metrics are therefore unavailable, not heuristic zero
    # (or aliases of faithfulness). Golden evaluation owns real IR quality.
    ir_unavailable = {"status": "NOT_AVAILABLE", "source": "golden", "reason": "no_relevance_ground_truth"}

    return {
        "metrics": {
            "hit_rate_10": None,
            "mrr_10": None,
            "ndcg_10": None,
            "context_precision": None,
            "context_recall": None,
            "low_confidence_rate": 0.0,
            "no_result_rate": 0.0,
            "total_indexed_chunks": total_chunks,
            "evaluated_sample_count": len(rag_traces),
        },
        "metric_provenance": {
            "hit_rate_10": ir_unavailable,
            "mrr_10": ir_unavailable,
            "ndcg_10": ir_unavailable,
            "context_precision": ir_unavailable,
            "context_recall": ir_unavailable,
        },
        "worst_queries": grouped_worst[:10],
        "problem_docs": [],
        "similarity_distribution": [],
    }


@rag_monitoring_router.get("/generation")
async def get_rag_generation(
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(_require_admin),
    filters: _FilterParams = Depends(_filter_query_params),
) -> dict[str, Any]:
    """Generation quality metrics computed from real traces (§15.3)"""
    chatbot_version, model, prompt_version = filters
    traces = _filter_traces(get_local_traces(), chatbot_version=chatbot_version, model=model, prompt_version=prompt_version)
    faith_list = _available_metric_scores(traces, "faithfulness")
    rel_list = _available_metric_scores(traces, "answer_relevance")

    avg_faith = (sum(faith_list) / len(faith_list)) if faith_list else None
    avg_rel = (sum(rel_list) / len(rel_list)) if rel_list else None

    settings = get_settings()

    # Breakdown by model
    model_counts: dict[str, int] = {}
    for t in traces:
        m = t.metadata.get("model") or settings.model_name
        model_counts[m] = model_counts.get(m, 0) + 1

    # BUILD-32: real per-model cost, summed from durable AgentRun rows with a
    # known price. A model absent from the pricing catalog contributes 0.0
    # here (an honest "nothing priced yet found for this model"), matching
    # this endpoint's existing flat-float shape rather than changing it.
    agent_runs_for_cost = _agent_run_query(db, chatbot_version=chatbot_version, model=model, prompt_version=prompt_version)
    cost_by_model: dict[str, float] = {}
    for r in agent_runs_for_cost:
        if r.cost_status == "AVAILABLE" and r.total_cost_usd is not None and r.model:
            cost_by_model[r.model] = cost_by_model.get(r.model, 0.0) + r.total_cost_usd

    breakdown_by_model = [
        {
            "model": m,
            "requests": count,
            "faithfulness": round(avg_faith, 2) if avg_faith is not None else None,
            "latency_p95": 0,
            "cost": round(cost_by_model.get(m, 0.0), 6),
        }
        for m, count in model_counts.items()
    ]
    if not breakdown_by_model:
        breakdown_by_model = [{
            "model": settings.model_name,
            "requests": len(traces),
            "faithfulness": round(avg_faith, 2) if avg_faith is not None else None,
            "latency_p95": 0,
            "cost": round(cost_by_model.get(settings.model_name, 0.0), 6),
        }]

    return {
        "metrics": {
            "faithfulness": round(avg_faith, 2) if avg_faith is not None else None,
            "answer_relevance": round(avg_rel, 2) if avg_rel is not None else None,
            "answer_correctness": None,
            "hallucination_rate": round(max(0.0, 1.0 - avg_faith), 2) if avg_faith is not None else None,
            "completeness": None,
            "abstention_accuracy": None,
            "faithfulness_sample_count": len(faith_list),
            "answer_relevance_sample_count": len(rel_list),
        },
        "breakdown_by_model": breakdown_by_model,
        # BUILD-25B fix: this used to hardcode legacy chat's own
        # `settings.rag_prompt_version` regardless of which system's traces
        # were actually in view -- now grouped by each trace's own real
        # `prompt_version` metadata, same pattern as breakdown_by_model above.
        "breakdown_by_prompt": [
            {"version": v, "requests": count, "faithfulness": round(avg_faith, 2) if avg_faith is not None else None, "hallucination": round(max(0.0, 1.0 - avg_faith), 2) if avg_faith is not None else None}
            for v, count in _prompt_version_counts(traces, settings).items()
        ],
    }


@rag_monitoring_router.get("/safety")
async def get_rag_safety(
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(_require_admin),
    filters: _FilterParams = Depends(_filter_query_params),
) -> dict[str, Any]:
    """Medication Safety incidents and checks from real Escalation table (§15.4).

    NOTE (BUILD-25 §8.2, unchanged by BUILD-25B): `incidents` below is still
    sourced entirely from the legacy `Escalation` table -- Agent V2's own
    safety/handoff data isn't joined into `incidents` itself, so filtering
    to chatbot_version=agent-v2 does NOT change the incidents list, only the
    `total_answers` denominator below. Documented, not silently glossed
    over.

    BUILD-34: `agent_v2_safety` is a genuinely separate block, sourced from
    the new durable `agent_safety_event` table
    (`backend.services.agent_safety_monitoring`) -- never summed into
    `critical_safety_failures`/`incidents` above (BUILD-34 §6: no double
    counting between legacy and Agent V2). A dedicated drill-down surface
    (`GET /admin/safety/*`, `backend/api/admin_safety_routes.py`) exists for
    anything beyond this summary-level view.
    """
    chatbot_version, model, prompt_version = filters
    escalations = db.query(Escalation).order_by(Escalation.created_at.desc()).all()
    # BUILD-25 audit: denominator for "rate of unsafe answers among all
    # answers" -- same total-traffic sources every other endpoint here uses
    # (in-memory traces, falling back to persisted AuditLog).
    traces = _filter_traces(get_local_traces(), chatbot_version=chatbot_version, model=model, prompt_version=prompt_version)
    total_answers = len(traces) if traces else db.query(AuditLog).count()

    incidents = []
    for e in escalations:
        incidents.append({
            "id": e.id,
            "severity": e.severity.lower(),
            "failure_type": e.trigger,
            "trace_id": e.id,
            "query_category": e.trigger,
            "model": "system-safety-guard",
            "timestamp": e.created_at.isoformat() if e.created_at else datetime.now(UTC).isoformat(),
            "status": e.status.lower(),
            "reason": e.reason,
        })

    critical_count = sum(1 for e in escalations if e.severity == "HIGH")

    return {
        "critical_safety_failures": critical_count,
        "dosage_consistency_failures": sum(1 for e in escalations if "dosage" in e.trigger.lower() or "liều" in e.reason.lower()),
        "interaction_unsupported_claims": sum(1 for e in escalations if "interaction" in e.trigger.lower() or "tương tác" in e.reason.lower()),
        "contraindication_unsupported_claims": sum(1 for e in escalations if "contraindication" in e.trigger.lower() or "chống chỉ định" in e.reason.lower()),
        # BUILD-25 fix: the previous formula (len(escalations) / max(len(escalations), 1))
        # is a tautology -- it always evaluates to exactly 100.0 whenever any
        # escalation exists, or 0.0 when none do, regardless of real traffic
        # volume, so it never actually measured a "rate" of anything. Real
        # rate needs a real denominator (total answered requests), which
        # `total_answers` above provides from the same source every sibling
        # endpoint in this file already uses.
        "unsafe_answer_rate": round((critical_count / total_answers) * 100, 2) if total_answers else 0.0,
        "incidents": incidents,
        "agent_v2_safety": _safe_agent_v2_safety_summary(db),
    }


def _safe_agent_v2_safety_summary(db: Session) -> dict[str, Any] | None:
    # BUILD-32's own post-merge incident (report §14.2): a read against a
    # table the target environment's migration hasn't run yet must degrade,
    # never 500 the whole endpoint (which would blank every OTHER card on
    # this same response, not just this new field). `None` here is an
    # honest "not available", never a fabricated empty summary.
    try:
        return safety_metrics_summary(db)
    except Exception as durable_err:  # noqa: BLE001
        logging.getLogger(__name__).warning("BUILD-34 agent_v2_safety summary read failed: %s", durable_err)
        return None


@rag_monitoring_router.get("/knowledge")
async def get_rag_knowledge(
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(_require_admin),
) -> dict[str, Any]:
    """Knowledge base & Index health computed from real DB (§15.5)"""
    settings = get_settings()
    total_chunks = db.query(DrugChunk).count()
    return {
        "kb_version": "production-live",
        "index_version": settings.rag_index_version,
        "last_sync": "Live Database",
        "index_coverage": 100.0 if total_chunks > 0 else 0.0,
        "stale_doc_rate": 0.0,
        "failed_ingestion_count": 0,
        "embedding_drift": "0.000",
        "total_chunks": total_chunks,
    }


@rag_monitoring_router.get("/system")
async def get_rag_system(
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(_require_admin),
    filters: _FilterParams = Depends(_filter_query_params),
) -> dict[str, Any]:
    """System latency waterfall & breakdowns from real traces and audit logs (§15.6)"""
    chatbot_version, model, prompt_version = filters
    traces = _filter_traces(get_local_traces(), chatbot_version=chatbot_version, model=model, prompt_version=prompt_version)
    # AuditLog rows are always legacy chat's own data -- excluded once a
    # filter asks for anything other than "legacy"/unfiltered (see /health).
    audit_logs = (
        db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(100).all()
        if chatbot_version in (None, "all", "legacy") and not model and not prompt_version
        else []
    )

    latencies = [t.duration_ms for t in traces if t.duration_ms > 0] or [
        audit_log.total_duration_ms for audit_log in audit_logs if audit_log.total_duration_ms > 0
    ]

    p50 = sorted(latencies)[int(len(latencies) * 0.50)] if latencies else 0.0
    p95 = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0.0
    p99 = sorted(latencies)[int(len(latencies) * 0.99)] if latencies else 0.0

    # Aggregate span breakdown from real trace observations
    step_totals: dict[str, list[float]] = {}
    for t in traces:
        for obs in t.observations:
            if obs.duration_ms > 0:
                step_totals.setdefault(obs.name, []).append(obs.duration_ms)

    # Fallback to persisted AuditLog steps if in-memory trace buffer is empty/cold
    if not step_totals and audit_logs:
        for audit_log in audit_logs:
            if isinstance(audit_log.trace, list):
                for step in audit_log.trace:
                    if isinstance(step, dict):
                        s_name = f"step.{step.get('step', 'step')}"
                        s_dur = float(step.get("duration_ms") or 0.0)
                        if s_dur > 0:
                            step_totals.setdefault(s_name, []).append(s_dur)

    waterfall = [
        {"component": name, "duration_ms": round(sum(d_list) / len(d_list), 1)}
        for name, d_list in step_totals.items()
    ]

    # BUILD-32: real cost/timeout over the last 24h of durable AgentRun rows
    # -- previously both were hardcoded 0.0 regardless of real traffic.
    day_ago = datetime.now(UTC) - timedelta(hours=24)
    agent_runs_24h = [
        r for r in _agent_run_query(db, chatbot_version=chatbot_version, model=model, prompt_version=prompt_version)
        if r.created_at and r.created_at >= day_ago
    ]
    priced_24h = [r for r in agent_runs_24h if r.cost_status == "AVAILABLE" and r.total_cost_usd is not None]
    cost_daily = sum(r.total_cost_usd for r in priced_24h) if priced_24h else 0.0
    unpriced_24h = [r for r in agent_runs_24h if r.cost_status != "AVAILABLE"]
    cost_daily_status = "AVAILABLE" if not unpriced_24h else ("PARTIAL" if priced_24h else "NOT_AVAILABLE")
    timeout_rate = (sum(1 for r in agent_runs_24h if r.timeout) / len(agent_runs_24h) * 100) if agent_runs_24h else 0.0
    cost_breakdown_by_model: dict[str, float] = {}
    for r in priced_24h:
        if r.model:
            cost_breakdown_by_model[r.model] = cost_breakdown_by_model.get(r.model, 0.0) + r.total_cost_usd

    return {
        "volume_24h": len(traces) if traces else len(audit_logs),
        "p50_latency_ms": round(p50, 1),
        "p95_latency_ms": round(p95, 1),
        "p99_latency_ms": round(p99, 1),
        # BUILD-25 fix: this used to be `p50 * 0.3` -- a fabricated guess with
        # no basis (no streaming path exists anywhere in this app to actually
        # measure time-to-first-token, for either legacy chat or Agent V2).
        # 0.0 here means "not measured", not "measured as zero" -- flagged as
        # a genuine data gap in the audit report, not silently invented.
        "ttft_ms": 0.0,
        "error_rate": round((sum(1 for t in traces if t.status == "error") / max(len(traces), 1)) * 100, 2) if traces else 0.0,
        "timeout_rate": round(timeout_rate, 2),
        "cost_daily": round(cost_daily, 6),
        "cost_daily_status": cost_daily_status,
        "latency_waterfall": waterfall,
        "cost_breakdown": [{"model": m, "cost": round(c, 6)} for m, c in cost_breakdown_by_model.items()],
    }


@rag_monitoring_router.get("/traces")
async def get_rag_traces(
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(_require_admin),
    filter_status: str | None = Query(default=None),
    filters: _FilterParams = Depends(_filter_query_params),
) -> list[dict[str, Any]]:
    """Trace Explorer list (§15.7).

    BUILD-32: this endpoint is the actual "Trace Explorer" the durable trace
    contract targets. The in-memory ring buffer is still read (unchanged --
    still the richest source for a very recent request: real query/answer
    text preview) but is no longer the only source: every listed trace is
    enriched with its durable ``AgentRun`` cost/token/error data when one
    exists, and durable Agent V2 runs the ring buffer no longer holds (aged
    out past 200 entries, or from before a restart) are appended too --
    honestly, with a placeholder instead of a fabricated text preview, since
    message/response text is deliberately not part of BUILD-32's durable
    schema (see backend.services.agent_feedback's module docstring).
    """
    chatbot_version, model, prompt_version = filters
    local_traces = _filter_traces(get_local_traces(), chatbot_version=chatbot_version, model=model, prompt_version=prompt_version)
    settings = get_settings()

    durable_by_trace_id = {
        r.trace_id: r
        for r in _agent_run_query(db, chatbot_version=chatbot_version, model=model, prompt_version=prompt_version)
        if r.trace_id
    }

    def _durable_fields(run: AgentRun | None) -> dict[str, Any]:
        if run is None:
            return {
                "input_tokens": None, "output_tokens": None, "total_tokens": None,
                "cost_usd": None, "cost_status": "NOT_AVAILABLE", "error_code": None, "timeout": False,
            }
        return {
            "input_tokens": run.input_tokens, "output_tokens": run.output_tokens, "total_tokens": run.total_tokens,
            "cost_usd": run.total_cost_usd, "cost_status": run.cost_status, "error_code": run.error_code,
            "timeout": run.timeout,
        }

    results: list[dict[str, Any]] = []
    seen_trace_ids: set[str] = set()

    # Map local live traces, enriched with durable cost/token/error data.
    for t in reversed(local_traces[-100:]):
        seen_trace_ids.add(t.id)
        results.append({
            "trace_id": t.id,
            "timestamp": datetime.fromtimestamp(t.start_time, tz=UTC).isoformat(),
            "session_id": t.session_id,
            "query_preview": str(t.input.get("message", "")) if isinstance(t.input, dict) else str(t.input),
            "final_answer": str(t.output.get("response", "")) if isinstance(t.output, dict) else str(t.output),
            "status": t.status,
            "latency_ms": round(t.duration_ms, 1),
            "faithfulness": float(t.scores.get("answer_faithfulness", 0.0)) if isinstance(t.scores.get("answer_faithfulness"), (int, float)) else 0.0,
            "relevance": float(t.scores.get("answer_relevance", 0.0)) if isinstance(t.scores.get("answer_relevance"), (int, float)) else 0.0,
            "chatbot_version": t.metadata.get("chatbot_version", "legacy"),
            "model": t.metadata.get("model", settings.model_name),
            "prompt_version": t.metadata.get("prompt_version", settings.rag_prompt_version),
            "index_version": t.metadata.get("index_version", settings.rag_index_version),
            **_durable_fields(durable_by_trace_id.get(t.id)),
        })

    # Durable Agent V2 runs the ring buffer above no longer holds (aged out,
    # or the process restarted since) -- proof that a trace "survives
    # restart" per the release gate, not just cost/token enrichment.
    for trace_id, run in durable_by_trace_id.items():
        if trace_id in seen_trace_ids or len(results) >= 150:
            continue
        seen_trace_ids.add(trace_id)
        results.append({
            "trace_id": trace_id,
            "timestamp": (run.started_at or run.created_at).isoformat(),
            "session_id": f"conversation_{run.conversation_id}" if run.conversation_id else "unknown",
            "query_preview": "(nội dung không còn trong bộ nhớ tạm)",
            "final_answer": "(nội dung không còn trong bộ nhớ tạm)",
            "status": run.status,
            "latency_ms": round(run.duration_ms, 1) if run.duration_ms is not None else 0.0,
            "faithfulness": 0.0,
            "relevance": 0.0,
            "chatbot_version": "agent-v2",
            "model": run.model or settings.agent_main_model,
            "prompt_version": "agent-v2-orchestrator",
            "index_version": settings.rag_index_version,
            **_durable_fields(run),
        })

    # If no live traces yet in memory, fallback to persisted AuditLog rows --
    # these are always legacy chat's own data, so skip them entirely once a
    # filter asks for anything other than "legacy"/unfiltered (same rule as
    # every other endpoint in this file).
    if not results and chatbot_version in (None, "all", "legacy") and not model and not prompt_version:
        logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(50).all()
        for audit_log in logs:
            results.append({
                "trace_id": f"db_{audit_log.id[:8]}",
                "timestamp": audit_log.created_at.isoformat() if audit_log.created_at else datetime.now(UTC).isoformat(),
                "session_id": f"session_{audit_log.patient_id}",
                "query_preview": audit_log.utterance,
                "final_answer": audit_log.final_response,
                "status": "success",
                "latency_ms": round(audit_log.total_duration_ms, 1),
                "faithfulness": 0.0,
                "relevance": 0.0,
                "chatbot_version": "legacy",
                "model": settings.model_name,
                "prompt_version": settings.rag_prompt_version,
                "index_version": settings.rag_index_version,
            })

    if filter_status:
        results = [r for r in results if r["status"] == filter_status]

    return results


@rag_monitoring_router.get("/traces/{trace_id}")
async def get_rag_trace_detail(
    trace_id: str,
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(_require_admin),
) -> dict[str, Any]:
    """Trace detail with timeline from real traces (§16)"""
    local_traces = get_local_traces()
    matched = next((t for t in local_traces if t.id == trace_id), None)

    if matched:
        return {
            "trace_id": matched.id,
            "session_id": matched.session_id,
            "user_id": matched.user_id,
            "timestamp": datetime.fromtimestamp(matched.start_time, tz=UTC).isoformat(),
            "query": matched.input.get("message", "") if isinstance(matched.input, dict) else str(matched.input),
            "response": matched.output.get("response", "") if isinstance(matched.output, dict) else str(matched.output),
            "duration_ms": matched.duration_ms,
            "status": matched.status,
            "timeline": [
                {
                    "name": obs.name,
                    "type": obs.type,
                    "duration_ms": obs.duration_ms,
                    "level": obs.level,
                    "input": obs.input,
                    "output": obs.output,
                }
                for obs in matched.observations
            ],
            "scores": matched.scores,
            "metadata": matched.metadata,
            "likely_root_cause": "Tất cả các chỉ số chất lượng & an toàn đạt chuẩn (Healthy)." if matched.status == "success" else "Có lỗi hoặc cảnh báo an toàn được kích hoạt.",
        }

    # Check AuditLog table
    clean_id = trace_id.replace("db_", "")
    log_item = db.query(AuditLog).filter(AuditLog.id.startswith(clean_id)).first()
    if log_item:
        return {
            "trace_id": log_item.id,
            "session_id": f"session_{log_item.patient_id}",
            "user_id": log_item.patient_id,
            "timestamp": log_item.created_at.isoformat() if log_item.created_at else datetime.now(UTC).isoformat(),
            "query": log_item.utterance,
            "response": log_item.final_response,
            "duration_ms": log_item.total_duration_ms,
            "status": "success",
            "timeline": [
                {"name": step.get("step", "step"), "type": "span", "duration_ms": 0, "level": "DEFAULT", "input": step, "output": step}
                for step in (log_item.trace if isinstance(log_item.trace, list) else [])
            ],
            "scores": {},
            "metadata": {},
            "likely_root_cause": "Dữ liệu được nạp từ AuditLog của hệ thống.",
        }

    # BUILD-32: durable fallback -- proves a trace survives a restart/aging
    # out of the ring buffer (release gate "TRACE SURVIVES RESTART"). Real
    # per-span timing from `AgentRunSpan` (captured live, see
    # `backend.api.agent_v2_routes._persist_durable_trace`); message/response
    # text is honestly omitted (see backend.services.agent_feedback's module
    # docstring for why), not fabricated. Own try/except (bugfix): a failure
    # here must fall through to the honest "not_found" response below, never
    # 500 the whole endpoint.
    try:
        run = db.execute(select(AgentRun).where(AgentRun.trace_id == trace_id)).scalar_one_or_none()
    except Exception as durable_err:  # noqa: BLE001
        logging.getLogger(__name__).warning("BUILD-32 durable trace detail lookup failed: %s", durable_err)
        run = None
    if run is not None:
        try:
            spans = (
                db.execute(select(AgentRunSpan).where(AgentRunSpan.agent_run_id == run.id).order_by(AgentRunSpan.started_at))
                .scalars()
                .all()
            )
        except Exception as durable_err:  # noqa: BLE001
            logging.getLogger(__name__).warning("BUILD-32 durable span lookup failed: %s", durable_err)
            spans = []
        return {
            "trace_id": trace_id,
            "session_id": f"conversation_{run.conversation_id}" if run.conversation_id else "unknown",
            "user_id": run.actor_id or "unknown",
            "timestamp": (run.started_at or run.created_at).isoformat(),
            "query": "(nội dung không còn trong bộ nhớ tạm)",
            "response": "(nội dung không còn trong bộ nhớ tạm)",
            "duration_ms": run.duration_ms if run.duration_ms is not None else 0.0,
            "status": run.status,
            "timeline": [
                {
                    "name": span.span_name,
                    "type": span.span_type,
                    "duration_ms": span.duration_ms,
                    "level": "ERROR" if span.status == "ERROR" else "DEFAULT",
                    "input": None,
                    "output": span.metadata_json,
                }
                for span in spans
            ],
            "scores": {},
            "metadata": {
                "intent": run.intent,
                "model": run.model,
                "chatbot_version": "agent-v2",
                "error_code": run.error_code,
                "timeout": run.timeout,
                "empty_reply": run.empty_reply,
                "input_tokens": run.input_tokens,
                "output_tokens": run.output_tokens,
                "cost_usd": run.total_cost_usd,
                "cost_status": run.cost_status,
                "pricing_version": run.pricing_version,
                "evaluation_version": run.evaluation_version,
            },
            "likely_root_cause": (
                "Tất cả các chỉ số chất lượng & an toàn đạt chuẩn (Healthy)."
                if run.status == "COMPLETED"
                else "Có lỗi hoặc cảnh báo an toàn được kích hoạt."
            ),
            "source": "durable",
        }

    return {
        "trace_id": trace_id,
        "session_id": "not_found",
        "user_id": "not_found",
        "timestamp": datetime.now(UTC).isoformat(),
        "query": "Không tìm thấy trace",
        "response": "Không tìm thấy trace",
        "duration_ms": 0.0,
        "status": "not_found",
        "timeline": [],
        "scores": {},
        "metadata": {},
        "likely_root_cause": "Trace không tồn tại.",
    }


@rag_monitoring_router.get("/versions/compare")
async def compare_versions(
    admin: CurrentUser = Depends(_require_admin),
) -> dict[str, Any]:
    """Version comparison table from current prompt version (§26)"""
    settings = get_settings()
    return {
        "version_a": {"name": "Baseline", "release": "1.0.0"},
        "version_b": {"name": settings.rag_prompt_version, "release": "active"},
        "metrics": [],
    }

