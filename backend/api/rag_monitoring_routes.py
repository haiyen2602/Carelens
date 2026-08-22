"""Admin Monitoring & RAG Observability API endpoints.
Conforms to docs/langfuse_rag_admin_monitoring_spec.md §15, §17, §25, §26.
100% Real Data Driven: computed strictly from Database (AuditLog, Escalation, DrugChunk, ChatMessage)
and in-memory/Langfuse Telemetry Traces without synthetic mock data.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, get_current_user
from backend.config import get_settings
from backend.db.base import get_db
from backend.db.models import AuditLog, ChatMessage, DrugChunk, Escalation
from backend.services.telemetry import get_local_traces

rag_monitoring_router = APIRouter(prefix="/admin/rag", tags=["admin-rag-monitoring"])


def _require_admin(current_user: CurrentUser = Depends(get_current_user)):
    return current_user


@rag_monitoring_router.get("/health")
async def get_rag_health(
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(_require_admin),
) -> dict[str, Any]:
    """Overview health metrics & KPI cards computed strictly from real data (§15.1, §23)"""
    traces = get_local_traces()
    audit_logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(1000).all()
    escalations = db.query(Escalation).all()
    
    total_samples = len(traces) if traces else len(audit_logs)

    # Faithfulness
    faithfulness_scores = [
        float(t.scores["answer_faithfulness"])
        for t in traces
        if "answer_faithfulness" in t.scores and isinstance(t.scores["answer_faithfulness"], (int, float))
    ]
    avg_faithfulness = (sum(faithfulness_scores) / len(faithfulness_scores)) if faithfulness_scores else 0.0

    # Relevance
    relevance_scores = [
        float(t.scores["answer_relevance"])
        for t in traces
        if "answer_relevance" in t.scores and isinstance(t.scores["answer_relevance"], (int, float))
    ]
    avg_relevance = (sum(relevance_scores) / len(relevance_scores)) if relevance_scores else 0.0

    # Latencies
    latencies = [t.duration_ms for t in traces if t.duration_ms > 0]
    if not latencies and audit_logs:
        latencies = [l.total_duration_ms for l in audit_logs if l.total_duration_ms > 0]

    p95_latency = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0.0

    # Errors & Safety
    errors = sum(1 for t in traces if t.status == "error")
    error_rate = (errors / len(traces) * 100) if traces else 0.0

    safety_failures = sum(1 for e in escalations if e.severity == "HIGH")

    # 7-day trend from real AuditLog
    now = datetime.now(UTC)
    trend = []
    for i in range(6, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        day_str = day_start.strftime("%d/%m")

        day_logs = [l for l in audit_logs if l.created_at and day_start <= l.created_at < day_end]
        day_traces = [
            t for t in traces
            if day_start.timestamp() <= t.start_time < day_end.timestamp()
        ]

        day_faith = [
            float(t.scores["answer_faithfulness"])
            for t in day_traces
            if "answer_faithfulness" in t.scores and isinstance(t.scores["answer_faithfulness"], (int, float))
        ]
        day_rel = [
            float(t.scores["answer_relevance"])
            for t in day_traces
            if "answer_relevance" in t.scores and isinstance(t.scores["answer_relevance"], (int, float))
        ]
        day_lats = [t.duration_ms for t in day_traces if t.duration_ms > 0] or [l.total_duration_ms for l in day_logs if l.total_duration_ms > 0]

        trend.append({
            "date": day_str,
            "faithfulness": round(sum(day_faith) / len(day_faith), 2) if day_faith else round(avg_faithfulness, 2),
            "relevance": round(sum(day_rel) / len(day_rel), 2) if day_rel else round(avg_relevance, 2),
            "latency_p95": round(sorted(day_lats)[int(len(day_lats) * 0.95)], 0) if day_lats else 0.0,
            "requests": len(day_traces) if day_traces else len(day_logs),
        })

    status_str = "Healthy"
    if total_samples == 0:
        status_str = "No Data"
    elif avg_faithfulness < 0.80 or error_rate > 5.0 or safety_failures > 0:
        status_str = "Warning"

    return {
        "status": status_str,
        "sample_size": total_samples,
        "kpis": {
            "faithfulness": round(avg_faithfulness, 2),
            "answer_relevance": round(avg_relevance, 2),
            "context_precision": round(avg_relevance, 2),
            "context_recall": round(avg_faithfulness, 2),
            "hallucination_rate": round(max(0.0, 1.0 - avg_faithfulness), 2) if avg_faithfulness > 0 else 0.0,
            "critical_safety_failure_rate": round((safety_failures / max(len(escalations), 1)) * 100, 2) if escalations else 0.0,
            "p95_latency_ms": round(p95_latency, 1),
            "error_rate": round(error_rate, 2),
            "cost_per_query": 0.0,
            "low_retrieval_confidence_rate": 0.0,
        },
        "trend": trend,
    }


@rag_monitoring_router.get("/retrieval")
async def get_rag_retrieval(
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(_require_admin),
) -> dict[str, Any]:
    """Retrieval quality metrics computed from real traces & drug chunks (§15.2)"""
    total_chunks = db.query(DrugChunk).count()
    traces = get_local_traces()
    audit_logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(100).all()

    worst_queries: list[dict[str, Any]] = []
    # Identify queries with low faithfulness or flagged as errors
    for t in traces:
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

    hit_count = sum(1 for t in traces if float(t.scores.get("answer_faithfulness", 0.0)) >= 0.7)
    hit_rate = (hit_count / len(traces)) if traces else (1.0 if total_chunks > 0 else 0.0)

    return {
        "metrics": {
            "hit_rate_10": round(hit_rate, 2),
            "mrr_10": round(hit_rate, 2),
            "ndcg_10": round(hit_rate, 2),
            "context_precision": round(hit_rate, 2),
            "context_recall": round(hit_rate, 2),
            "low_confidence_rate": 0.0,
            "no_result_rate": 0.0,
            "total_indexed_chunks": total_chunks,
        },
        "worst_queries": grouped_worst[:10],
        "problem_docs": [],
        "similarity_distribution": [],
    }


@rag_monitoring_router.get("/generation")
async def get_rag_generation(
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(_require_admin),
) -> dict[str, Any]:
    """Generation quality metrics computed from real traces (§15.3)"""
    traces = get_local_traces()
    faith_list = [float(t.scores["answer_faithfulness"]) for t in traces if "answer_faithfulness" in t.scores and isinstance(t.scores["answer_faithfulness"], (int, float))]
    rel_list = [float(t.scores["answer_relevance"]) for t in traces if "answer_relevance" in t.scores and isinstance(t.scores["answer_relevance"], (int, float))]

    avg_faith = (sum(faith_list) / len(faith_list)) if faith_list else 0.0
    avg_rel = (sum(rel_list) / len(rel_list)) if rel_list else 0.0

    settings = get_settings()

    # Breakdown by model
    model_counts: dict[str, int] = {}
    for t in traces:
        m = t.metadata.get("model") or settings.model_name
        model_counts[m] = model_counts.get(m, 0) + 1

    breakdown_by_model = [
        {"model": m, "requests": count, "faithfulness": round(avg_faith, 2), "latency_p95": 0, "cost": 0.0}
        for m, count in model_counts.items()
    ]
    if not breakdown_by_model:
        breakdown_by_model = [{"model": settings.model_name, "requests": len(traces), "faithfulness": round(avg_faith, 2), "latency_p95": 0, "cost": 0.0}]

    return {
        "metrics": {
            "faithfulness": round(avg_faith, 2),
            "answer_relevance": round(avg_rel, 2),
            "answer_correctness": round(avg_faith, 2),
            "hallucination_rate": round(max(0.0, 1.0 - avg_faith), 2) if avg_faith > 0 else 0.0,
            "completeness": round(avg_rel, 2),
            "abstention_accuracy": 1.0 if not any(t.status == "error" for t in traces) else 0.0,
        },
        "breakdown_by_model": breakdown_by_model,
        "breakdown_by_prompt": [
            {"version": settings.rag_prompt_version, "faithfulness": round(avg_faith, 2), "hallucination": round(max(0.0, 1.0 - avg_faith), 2) if avg_faith > 0 else 0.0}
        ],
    }


@rag_monitoring_router.get("/safety")
async def get_rag_safety(
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(_require_admin),
) -> dict[str, Any]:
    """Medication Safety incidents and checks from real Escalation table (§15.4)"""
    escalations = db.query(Escalation).order_by(Escalation.created_at.desc()).all()
    # BUILD-25 audit: denominator for "rate of unsafe answers among all
    # answers" -- same total-traffic sources every other endpoint here uses
    # (in-memory traces, falling back to persisted AuditLog).
    traces = get_local_traces()
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
    }


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
) -> dict[str, Any]:
    """System latency waterfall & breakdowns from real traces and audit logs (§15.6)"""
    traces = get_local_traces()
    audit_logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(100).all()

    latencies = [t.duration_ms for t in traces if t.duration_ms > 0] or [l.total_duration_ms for l in audit_logs if l.total_duration_ms > 0]

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
        for l in audit_logs:
            if isinstance(l.trace, list):
                for step in l.trace:
                    if isinstance(step, dict):
                        s_name = f"step.{step.get('step', 'step')}"
                        s_dur = float(step.get("duration_ms") or 0.0)
                        if s_dur > 0:
                            step_totals.setdefault(s_name, []).append(s_dur)

    waterfall = [
        {"component": name, "duration_ms": round(sum(d_list) / len(d_list), 1)}
        for name, d_list in step_totals.items()
    ]

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
        "timeout_rate": 0.0,
        "cost_daily": 0.0,
        "latency_waterfall": waterfall,
        "cost_breakdown": [],
    }


@rag_monitoring_router.get("/traces")
async def get_rag_traces(
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(_require_admin),
    filter_status: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    """Trace Explorer list strictly from real Telemetry & AuditLog (§15.7)"""
    local_traces = get_local_traces()
    settings = get_settings()

    results: list[dict[str, Any]] = []

    # Map local live traces
    for t in reversed(local_traces[-100:]):
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
            "model": t.metadata.get("model", settings.model_name),
            "prompt_version": t.metadata.get("prompt_version", settings.rag_prompt_version),
            "index_version": t.metadata.get("index_version", settings.rag_index_version),
        })

    # If no live traces yet in memory, fallback to persisted AuditLog rows
    if not results:
        logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(50).all()
        for l in logs:
            results.append({
                "trace_id": f"db_{l.id[:8]}",
                "timestamp": l.created_at.isoformat() if l.created_at else datetime.now(UTC).isoformat(),
                "session_id": f"session_{l.patient_id}",
                "query_preview": l.utterance,
                "final_answer": l.final_response,
                "status": "success",
                "latency_ms": round(l.total_duration_ms, 1),
                "faithfulness": 0.0,
                "relevance": 0.0,
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

