"""Automatic closure of inactive doctor takeovers for TASK-021."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.models import DoctorReviewMessage, DoctorReviewRequest
from backend.services.doctor_handoff import HandoffStatus, stop_inactive_doctor_review_request

INACTIVITY_TIMEOUT = timedelta(minutes=10)


def _as_utc(value: datetime, *, dialect_name: str) -> datetime:
    """Normalise SQLite test values; reject naïve production timestamps."""
    if value.tzinfo is None or value.utcoffset() is None:
        if dialect_name != "sqlite":
            raise ValueError("doctor takeover timestamps must be timezone-aware outside SQLite tests")
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def close_inactive_takeovers(db: Session, *, now: datetime | None = None) -> int:
    """Resolve ACTIVE handoffs with no patient message for at least 10 minutes.

    Last patient activity is loaded as a correlated aggregate in the same SQL
    query as ACTIVE handoffs (not one query per handoff). The per-handoff stop
    service then locks the row before changing state, so concurrent scheduler
    ticks or a patient-initiated stop cannot duplicate the terminal message.
    """
    now = now or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    dialect_name = db.get_bind().dialect.name

    last_patient_message_at = (
        select(func.max(DoctorReviewMessage.created_at))
        .where(
            DoctorReviewMessage.handoff_id == DoctorReviewRequest.id,
            DoctorReviewMessage.sender_role == "PATIENT",
        )
        .correlate(DoctorReviewRequest)
        .scalar_subquery()
    )
    rows = db.execute(
        select(DoctorReviewRequest, last_patient_message_at.label("last_patient_message_at")).where(
            DoctorReviewRequest.status == HandoffStatus.ACTIVE
        )
    ).all()
    stopped = 0
    for row, last_patient_message in rows:
        last_activity = last_patient_message or row.activated_at
        if last_activity is None or now - _as_utc(last_activity, dialect_name=dialect_name) < INACTIVITY_TIMEOUT:
            continue
        if stop_inactive_doctor_review_request(
            db, request_id=row.id, stopped_at=now, inactive_for=INACTIVITY_TIMEOUT
        ) is not None:
            stopped += 1
    if stopped:
        db.commit()
    return stopped
