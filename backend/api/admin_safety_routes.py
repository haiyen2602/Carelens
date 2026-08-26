"""BUILD-34: Admin "Safety & Handoff Monitoring" domain for Agent V2.

Every route here is admin-only (``require_role("admin")``, same dependency
every other admin surface in this repo already uses). Source of truth is
the durable ``agent_safety_event`` table (BUILD-34, written purely from
completed ``OrchestrationResult``s) plus a LIVE join to
``DoctorReviewRequest`` for current handoff status -- never the in-memory
telemetry ring buffer, and never the legacy ``Escalation`` table alone (see
``backend.services.agent_safety_monitoring`` module docstring).

Every endpoint below degrades to a clearly-labeled empty/unavailable shape
on a durable-read failure instead of a bare 500 -- BUILD-32's own post-merge
incident (report §14.2) was exactly this gap (a target environment whose
migration for a new table hadn't run yet turned a missing try/except into a
blank Admin dashboard); this module does not repeat it.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.api.security import require_role
from backend.db.base import get_db
from backend.services.agent_safety_monitoring import (
    judge_suspected_missed_risk_signals,
    legacy_escalation_count,
    list_safety_events,
    safety_event_detail,
    safety_metrics_summary,
)

admin_safety_router = APIRouter(prefix="/admin/safety", tags=["admin-safety-monitoring"])

_require_admin = require_role("admin", "super_admin")
_logger = logging.getLogger(__name__)


@admin_safety_router.get("/summary")
def get_safety_summary(
    db: Session = Depends(get_db),
    _admin=Depends(_require_admin),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
) -> dict[str, Any]:
    """BUILD-34 §3: safety_trigger_count/rate, handoff required/created/
    failure count+rate, unresolved handoff count, severity/reason_code/
    handoff_status distributions, time_to_review -- every rate has an
    explicit denominator (``denominator_agent_v2_total_runs``, real
    ``agent_run`` count), N/A stays ``null`` (never a fabricated 0) when
    the denominator itself is 0.

    ``legacy_escalation_count`` is returned as its OWN, clearly separate
    field -- never summed into the Agent V2 numbers above (BUILD-34 §6: no
    double counting, legacy stays legacy)."""

    try:
        metrics = safety_metrics_summary(db, date_from=date_from, date_to=date_to)
        metrics["legacy_escalation_count"] = legacy_escalation_count(db, date_from=date_from, date_to=date_to)
        metrics["judge_suspected_missed_risk_signals"] = judge_suspected_missed_risk_signals(db)
        metrics["available"] = True
        return metrics
    except Exception as durable_err:  # noqa: BLE001 -- degrade, never 500 the whole Admin page
        _logger.warning("BUILD-34 safety summary read failed: %s", durable_err)
        return {"available": False}


@admin_safety_router.get("/events")
def get_safety_events(
    db: Session = Depends(get_db),
    _admin=Depends(_require_admin),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    severity: str | None = Query(default=None),
    reason_code: str | None = Query(default=None),
) -> dict[str, Any]:
    """BUILD-34 §5: metric -> event list. Live handoff status per row --
    never a stale snapshot."""

    try:
        items, total = list_safety_events(db, limit=limit, offset=offset, severity=severity, reason_code=reason_code)
        return {"items": items, "total": total, "limit": limit, "offset": offset, "available": True}
    except Exception as durable_err:  # noqa: BLE001
        _logger.warning("BUILD-34 safety events list read failed: %s", durable_err)
        return {"items": [], "total": 0, "limit": limit, "offset": offset, "available": False}


@admin_safety_router.get("/events/{event_id}")
def get_safety_event_detail(
    event_id: str, db: Session = Depends(get_db), _admin=Depends(_require_admin)
) -> dict[str, Any]:
    """BUILD-34 §5: event -> session (conversation_id)/trace (trace_id)/
    handoff (live status + assigned doctor)/ticket (id if one exists)/Judge
    (latest result if one exists) -- every real id an Admin needs to drill
    down further, no manual copy/paste of any id required."""

    try:
        detail = safety_event_detail(db, event_id)
    except Exception as durable_err:  # noqa: BLE001 -- a real read failure is distinct from "not found"
        _logger.warning("BUILD-34 safety event detail read failed for event_id=%s: %s", event_id, durable_err)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Khong doc duoc safety event luc nay"
        ) from durable_err
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay safety event")
    return detail


@admin_safety_router.get("/judge-review-signals")
def get_judge_review_signals(
    db: Session = Depends(get_db),
    _admin=Depends(_require_admin),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """BUILD-34 §4: REVIEW_SUSPECTED_MISSED_RISK -- deterministic Safety did
    NOT trigger on these runs, but Judge's own real, numeric red_flag_
    handling score (TRIAGE rubric) came back low. Read-only correlation,
    never writes anything, never changes a SafetyDecision, never creates a
    handoff -- see ``judge_suspected_missed_risk_signals``'s own docstring."""

    try:
        return {"signals": judge_suspected_missed_risk_signals(db, limit=limit), "available": True}
    except Exception as durable_err:  # noqa: BLE001
        _logger.warning("BUILD-34 judge review signals read failed: %s", durable_err)
        return {"signals": [], "available": False}


__all__ = ["admin_safety_router"]
