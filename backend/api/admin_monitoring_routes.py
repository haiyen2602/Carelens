"""BUILD-36: Admin Monitoring Dashboard V2 for Agent V2.

Every route here is admin-only (``require_role("admin")``, same dependency
every other admin surface in this repo already uses). Source of truth is
the durable ``agent_run``/``agent_run_span``/``agent_run_evaluation``/
``agent_run_judge``/``agent_safety_event``/``agent_golden_run(_case)``
tables BUILD-32/33/34/35 already write (see
``backend.services.agent_monitoring_metrics`` for the actual aggregation
logic -- this module is routing/param-parsing/degrade-wrapping only, same
split as ``admin_safety_routes.py``).

Every endpoint below degrades to a clearly-labeled ``{"available": False}``
shape on a durable-read failure instead of a bare 500 -- BUILD-32's own
post-merge incident (report §14.2) was exactly this gap; this module does
not repeat it. Safety & Handoff data is NOT duplicated here -- the
dashboard's Safety tab calls the existing ``/admin/safety/*`` endpoints
directly (see BUILD-36 report's Information Architecture section).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.api.security import require_role
from backend.db.base import get_db
from backend.services.monitoring_events import monitoring_broadcaster
from backend.services.agent_doctor_handoff_metrics import doctor_queue_metrics
from backend.services.agent_feedback import session_messages
from backend.services.agent_monitoring_metrics import (
    MonitoringFilters,
    compare_metrics,
    cost_metrics,
    errors_metrics,
    golden_metrics,
    golden_run_detail,
    judge_metrics,
    list_traces,
    overview_metrics,
    performance_metrics,
    quality_metrics,
    retrieval_metrics,
    trace_detail,
    trend_metrics,
    version_filter_options,
)

admin_monitoring_router = APIRouter(prefix="/admin/monitoring", tags=["admin-monitoring-v2"])

_require_admin = require_role("admin", "super_admin")
_logger = logging.getLogger(__name__)


def _filters(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    model: str | None = Query(default=None),
    prompt_version: str | None = Query(default=None),
    retrieval_version: str | None = Query(default=None),
    evaluation_version: str | None = Query(default=None),
    execution_path: str | None = Query(default=None),
    status_: str | None = Query(default=None, alias="status"),
    error_code: str | None = Query(default=None),
    safety_severity: str | None = Query(default=None),
    judge_model: str | None = Query(default=None),
    rubric_version: str | None = Query(default=None),
    judge_score_min: float | None = Query(default=None),
    judge_score_max: float | None = Query(default=None),
) -> MonitoringFilters:
    return MonitoringFilters(
        date_from=date_from, date_to=date_to, model=model, prompt_version=prompt_version,
        retrieval_version=retrieval_version, evaluation_version=evaluation_version,
        execution_path=execution_path, status=status_, error_code=error_code,
        safety_severity=safety_severity, judge_model=judge_model, rubric_version=rubric_version,
        judge_score_min=judge_score_min, judge_score_max=judge_score_max,
    )


@admin_monitoring_router.get("/overview")
def get_overview(db: Session = Depends(get_db), _admin=Depends(_require_admin), filters: MonitoringFilters = Depends(_filters)) -> dict[str, Any]:
    return overview_metrics(db, filters)


@admin_monitoring_router.get("/doctor-queue")
def get_doctor_queue(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin=Depends(_require_admin),
) -> dict[str, Any]:
    """BUILD-44 SS21/SS22: doctor-queue lifecycle metrics (status/type
    counts, time-to-claim/activate/resolve). Separate from Safety's own
    ``/admin/safety/*`` -- an UNCERTAINTY/USER_REQUEST handoff is counted
    here but never as an ``AgentSafetyEvent`` (see
    ``agent_doctor_handoff_metrics`` module docstring)."""
    return doctor_queue_metrics(db, date_from=date_from, date_to=date_to)


@admin_monitoring_router.get("/trend")
def get_trend(
    db: Session = Depends(get_db),
    _admin=Depends(_require_admin),
    filters: MonitoringFilters = Depends(_filters),
    days: int = Query(default=7, ge=1, le=90),
) -> dict[str, Any]:
    """Daily time-series trend (requests, P95 latency, faithfulness, relevance)
    over the last `days` calendar days or within the provided date_from/date_to
    filter window. Used by Quality tab trend chart on the admin monitoring
    dashboard (see BUILD-36 redesign plan, Phương án B)."""
    return trend_metrics(db, filters, days=days)


@admin_monitoring_router.get("/quality")
def get_quality(db: Session = Depends(get_db), _admin=Depends(_require_admin), filters: MonitoringFilters = Depends(_filters)) -> dict[str, Any]:
    return quality_metrics(db, filters)


@admin_monitoring_router.get("/retrieval")
def get_retrieval(db: Session = Depends(get_db), _admin=Depends(_require_admin), filters: MonitoringFilters = Depends(_filters)) -> dict[str, Any]:
    return retrieval_metrics(db, filters)


@admin_monitoring_router.get("/performance")
def get_performance(db: Session = Depends(get_db), _admin=Depends(_require_admin), filters: MonitoringFilters = Depends(_filters)) -> dict[str, Any]:
    return performance_metrics(db, filters)


@admin_monitoring_router.get("/cost")
def get_cost(db: Session = Depends(get_db), _admin=Depends(_require_admin), filters: MonitoringFilters = Depends(_filters)) -> dict[str, Any]:
    return cost_metrics(db, filters)


@admin_monitoring_router.get("/errors")
def get_errors(db: Session = Depends(get_db), _admin=Depends(_require_admin), filters: MonitoringFilters = Depends(_filters)) -> dict[str, Any]:
    return errors_metrics(db, filters)


@admin_monitoring_router.get("/judge")
def get_judge(db: Session = Depends(get_db), _admin=Depends(_require_admin), filters: MonitoringFilters = Depends(_filters)) -> dict[str, Any]:
    return judge_metrics(db, filters)


@admin_monitoring_router.get("/golden")
def get_golden(
    db: Session = Depends(get_db),
    _admin=Depends(_require_admin),
    golden_set_version: str | None = Query(default=None),
) -> dict[str, Any]:
    return golden_metrics(db, golden_set_version=golden_set_version)


@admin_monitoring_router.get("/golden/{run_id}")
def get_golden_run(run_id: str, db: Session = Depends(get_db), _admin=Depends(_require_admin)) -> dict[str, Any]:
    try:
        detail = golden_run_detail(db, run_id)
    except Exception as durable_err:  # noqa: BLE001
        _logger.warning("BUILD-36 golden run detail read failed for run_id=%s: %s", run_id, durable_err)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Khong doc duoc golden run luc nay") from durable_err
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay golden run")
    return detail


@admin_monitoring_router.get("/versions/filters")
def get_version_filters(db: Session = Depends(get_db), _admin=Depends(_require_admin)) -> dict[str, Any]:
    return version_filter_options(db)


@admin_monitoring_router.get("/versions/compare")
def get_versions_compare(
    db: Session = Depends(get_db),
    _admin=Depends(_require_admin),
    section: str = Query(...),
    before_date_from: datetime | None = Query(default=None),
    before_date_to: datetime | None = Query(default=None),
    before_model: str | None = Query(default=None),
    before_prompt_version: str | None = Query(default=None),
    before_retrieval_version: str | None = Query(default=None),
    after_date_from: datetime | None = Query(default=None),
    after_date_to: datetime | None = Query(default=None),
    after_model: str | None = Query(default=None),
    after_prompt_version: str | None = Query(default=None),
    after_retrieval_version: str | None = Query(default=None),
) -> dict[str, Any]:
    """Spec §13: before/after comparison, e.g. gpt-5.4-mini prompt-v1 vs
    prompt-v2 -- 2 independent filter sets, one per side. Calls the SAME
    section function twice (see ``compare_metrics``'s own docstring), never
    a second copy of any aggregation logic."""

    before = MonitoringFilters(
        date_from=before_date_from, date_to=before_date_to, model=before_model,
        prompt_version=before_prompt_version, retrieval_version=before_retrieval_version,
    )
    after = MonitoringFilters(
        date_from=after_date_from, date_to=after_date_to, model=after_model,
        prompt_version=after_prompt_version, retrieval_version=after_retrieval_version,
    )
    return compare_metrics(db, section, before, after)


@admin_monitoring_router.get("/traces")
def get_traces(
    db: Session = Depends(get_db),
    _admin=Depends(_require_admin),
    filters: MonitoringFilters = Depends(_filters),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Real server-side pagination/filtering (spec §17) -- replaces the
    legacy ``/admin/rag/traces``'s hardcoded ring-buffer caps with a real
    ``LIMIT``/``OFFSET`` over the durable ``agent_run`` table."""

    return list_traces(db, filters, limit=limit, offset=offset)


@admin_monitoring_router.get("/traces/{trace_id}")
def get_trace_detail(trace_id: str, db: Session = Depends(get_db), _admin=Depends(_require_admin)) -> dict[str, Any]:
    try:
        detail = trace_detail(db, trace_id)
    except Exception as durable_err:  # noqa: BLE001
        _logger.warning("BUILD-36 trace detail read failed for trace_id=%s: %s", trace_id, durable_err)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Khong doc duoc trace luc nay") from durable_err
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay trace")
    return detail


@admin_monitoring_router.get("/sessions/{conversation_id}")
def get_session_detail(
    conversation_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(_require_admin),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Reuses ``agent_feedback.session_messages`` -- the SAME ring-buffer +
    durable-fallback merge BUILD-29's own ticket session sub-route already
    uses (``GET /admin/tickets/{id}/session``) -- not a second,
    independent implementation of "list one conversation's turns"."""

    try:
        items, total = session_messages(db, conversation_id, limit=limit, offset=offset)
        return {"available": True, "items": items, "total": total, "limit": limit, "offset": offset}
    except Exception as durable_err:  # noqa: BLE001
        _logger.warning("BUILD-36 session detail read failed for conversation_id=%s: %s", conversation_id, durable_err)
        return {"available": False, "items": [], "total": 0, "limit": limit, "offset": offset}


@admin_monitoring_router.get("/stream")
async def get_monitoring_stream(
    _admin=Depends(_require_admin),
) -> StreamingResponse:
    """Server-Sent Events (SSE) stream for realtime monitoring updates."""
    queue = monitoring_broadcaster.subscribe()
    return StreamingResponse(
        monitoring_broadcaster.stream_events(queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


__all__ = ["admin_monitoring_router"]
