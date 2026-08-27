"""BUILD-44 SS21/SS22: Admin Monitoring extension for the Doctor Chat Queue
& Takeover workflow.

Separate module from ``agent_safety_monitoring.py`` on purpose -- that file
already has its own well-scoped concern (per-run Safety/Handoff events,
``AgentSafetyEvent``); this one aggregates the doctor-side QUEUE lifecycle
(``DoctorReviewRequest``/``DoctorReviewMessage``) directly, independent of
whether any given handoff happened to also get an ``AgentSafetyEvent`` row
(UNCERTAINTY/USER_REQUEST handoffs never do -- see BUILD-42 SS17). Reusing
``agent_safety_monitoring``'s own N/A discipline: every rate/average is
``{value, sample_count, status}`` where ``status`` is
``AVAILABLE | NOT_APPLICABLE`` -- never a fabricated 0/None when the
underlying sample is empty, and an UNCERTAINTY/USER_REQUEST row is never
counted as a Safety event here (this module has no ``AgentSafetyEvent``
query at all).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.agents.v2.answerability import handoff_type_for
from backend.db.models import DoctorReviewRequest

_logger = logging.getLogger(__name__)

_OPEN_STATUSES = ("PENDING", "ASSIGNED", "ACTIVE")
_ALL_STATUSES = ("PENDING", "ASSIGNED", "ACTIVE", "RESOLVED", "ANSWERED", "CANCELLED")
_ALL_TYPES = ("SAFETY", "UNCERTAINTY", "USER_REQUEST")


@dataclass(frozen=True)
class _Rate:
    value: float | None
    sample_count: int
    status: str  # AVAILABLE | NOT_APPLICABLE

    def as_dict(self) -> dict[str, Any]:
        return {"value": self.value, "sample_count": self.sample_count, "status": self.status}


def _avg_seconds(durations: list[float]) -> _Rate:
    if not durations:
        return _Rate(value=None, sample_count=0, status="NOT_APPLICABLE")
    return _Rate(value=sum(durations) / len(durations), sample_count=len(durations), status="AVAILABLE")


def doctor_queue_metrics(
    db: Session, *, date_from: datetime | None = None, date_to: datetime | None = None
) -> dict[str, Any]:
    """Real SQL read of every ``DoctorReviewRequest`` in range (small table,
    no pagination needed at this aggregate level -- matches
    ``safety_metrics_summary``'s own approach). ``handoff_type`` is derived
    the SAME way the doctor-facing queue route computes it
    (``handoff_type_for``), never a second, potentially-drifting
    classification."""

    try:
        stmt = select(DoctorReviewRequest)
        if date_from is not None:
            stmt = stmt.where(DoctorReviewRequest.created_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(DoctorReviewRequest.created_at <= date_to)
        rows = db.execute(stmt).scalars().all()

        status_counts = dict.fromkeys(_ALL_STATUSES, 0)
        type_counts = dict.fromkeys(_ALL_TYPES, 0)
        time_to_claim: list[float] = []
        time_to_activate: list[float] = []
        time_to_resolve: list[float] = []

        for row in rows:
            if row.status in status_counts:
                status_counts[row.status] += 1
            handoff_type = handoff_type_for(reason_code=row.reason_code, risk_disposition=row.risk_disposition).value
            if handoff_type in type_counts:
                type_counts[handoff_type] += 1

            if row.assigned_at is not None:
                time_to_claim.append(max(0.0, (row.assigned_at - row.created_at).total_seconds()))
            if row.activated_at is not None and row.assigned_at is not None:
                time_to_activate.append(max(0.0, (row.activated_at - row.assigned_at).total_seconds()))
            # BUILD-44's own workflow only -- the pre-existing ANSWERED/
            # CANCELLED quick-answer path never has `activated_at`, so it is
            # not included here (a separate, already-existing metric --
            # `safety_metrics_summary.time_to_review_avg_seconds` -- covers
            # that path's own creation-to-resolution latency).
            if row.resolved_at is not None and row.activated_at is not None:
                time_to_resolve.append(max(0.0, (row.resolved_at - row.activated_at).total_seconds()))

        open_count = sum(status_counts[s] for s in _OPEN_STATUSES)

        return {
            "available": True,
            "total_count": len(rows),
            "open_count": open_count,
            "status_counts": status_counts,
            "handoff_type_counts": type_counts,
            "time_to_claim_avg_seconds": _avg_seconds(time_to_claim).as_dict(),
            "time_to_activate_avg_seconds": _avg_seconds(time_to_activate).as_dict(),
            "time_to_resolve_avg_seconds": _avg_seconds(time_to_resolve).as_dict(),
        }
    except Exception as exc:  # noqa: BLE001 -- same degrade-safety discipline as agent_monitoring_metrics.py (BUILD-32 post-merge incident, report SS14.2)
        _logger.exception("doctor_queue_metrics failed")
        return {"available": False, "reason": str(exc)}


__all__ = ["doctor_queue_metrics"]
