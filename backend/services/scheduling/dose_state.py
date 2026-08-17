"""DB-4G V2 dose state machine and idempotent reminder outbox.

This module deliberately owns persistence only.  A future scheduler may call
``advance_dose_occurrences`` and a future delivery worker may claim jobs, but
neither cron wiring nor a notification provider is introduced here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import DoseEventLog, DoseOccurrence, NotificationJob
from backend.services.scheduling.errors import (
    DoseOccurrenceNotFoundError,
    InvalidDoseTransitionError,
    InvalidReminderConfigurationError,
)

SCHEDULED = "SCHEDULED"
DUE = "DUE"
TAKEN = "TAKEN"
DELAYED = "DELAYED"
MISSED = "MISSED"
SKIPPED = "SKIPPED"

QUEUED = "QUEUED"
PROCESSING = "PROCESSING"
RETRY = "RETRY"
SENT = "SENT"
CANCELLED = "CANCELLED"

DOSE_WINDOW_HALF_WIDTH = timedelta(minutes=30)
NOTIFICATION_TYPE_DOSE_REMINDER = "DOSE_REMINDER"
RECIPIENT_PATIENT = "PATIENT"

_TERMINAL_STATES = frozenset({TAKEN, DELAYED, MISSED, SKIPPED})
_ALLOWED_TARGETS = {
    SCHEDULED: frozenset({DUE}),
    DUE: _TERMINAL_STATES,
}


@dataclass(frozen=True)
class StateTransitionResult:
    """Result of one state command; services never commit the caller's work."""

    occurrence_id: str
    status: str
    changed: bool


@dataclass
class ReminderAdvanceResult:
    """Observable result of one clock scan, suitable for a future cron metric."""

    due: int = 0
    missed: int = 0
    jobs_created: int = 0
    jobs_existing: int = 0
    jobs_cancelled: int = 0


def _require_utc_instant(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _stored_utc_instant(value: datetime, field_name: str) -> datetime:
    """Read a persisted UTC timestamp, including SQLite's timezone-less test adapter.

    PostgreSQL `TIMESTAMPTZ` is the operational store. SQLite drops tzinfo in
    unit tests even though the value supplied to the model is already UTC, so
    interpreting that test-adapter representation as UTC preserves the same
    instant without weakening validation of public command timestamps.
    """

    return value.replace(tzinfo=UTC) if value.tzinfo is None else _require_utc_instant(value, field_name)


def _stable_id(namespace: str, key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"vmec04:{namespace}:{key}"))


def _event_key(occurrence_id: str, event_type: str, suffix: str = "") -> str:
    return f"dose:{occurrence_id}:event:{event_type}{':' + suffix if suffix else ''}"


def _notification_key(occurrence_id: str, offset: timedelta) -> str:
    return f"dose:{occurrence_id}:reminder:{int(offset.total_seconds())}"


def _find_staged_or_persisted(
    db: Session, model: type[DoseEventLog] | type[NotificationJob], key: str
) -> DoseEventLog | NotificationJob | None:
    """Find a row even when the caller uses a non-autoflush session."""

    for row in db.new:
        if isinstance(row, model) and row.idempotency_key == key:
            return row
    return db.execute(select(model).where(model.idempotency_key == key)).scalar_one_or_none()


def _append_event(
    db: Session,
    occurrence: DoseOccurrence,
    *,
    event_type: str,
    event_at: datetime,
    source: str,
    actor_type: str | None = None,
    actor_id: str | None = None,
    key_suffix: str = "",
    metadata: dict | None = None,
) -> bool:
    """Append an immutable event once; no event row is ever modified or removed."""

    key = _event_key(occurrence.id, event_type, key_suffix)
    if _find_staged_or_persisted(db, DoseEventLog, key) is not None:
        return False
    db.add(
        DoseEventLog(
            id=_stable_id("dose-event", key),
            dose_occurrence_id=occurrence.id,
            patient_id=occurrence.patient_id,
            medication_plan_id=occurrence.medication_plan_id,
            drug_product_id=occurrence.drug_product_id,
            event_type=event_type,
            event_at=event_at,
            source=source,
            actor_type=actor_type,
            actor_id=actor_id,
            idempotency_key=key,
            metadata_json=metadata or {},
        )
    )
    return True


def _locked_occurrence(db: Session, occurrence_id: str) -> DoseOccurrence:
    occurrence = db.execute(
        select(DoseOccurrence).where(DoseOccurrence.id == occurrence_id).with_for_update()
    ).scalar_one_or_none()
    if occurrence is None:
        raise DoseOccurrenceNotFoundError("Không tìm thấy liều V2.", occurrence_id=occurrence_id)
    return occurrence


def _ensure_window(occurrence: DoseOccurrence) -> None:
    """Backfill V2 timing context lazily from the approved ±30-minute rule."""

    scheduled_at = _stored_utc_instant(occurrence.scheduled_at, "scheduled_at")
    occurrence.scheduled_at = scheduled_at
    occurrence.due_at = occurrence.due_at or scheduled_at
    occurrence.window_start = occurrence.window_start or scheduled_at - DOSE_WINDOW_HALF_WIDTH
    occurrence.window_end = occurrence.window_end or scheduled_at + DOSE_WINDOW_HALF_WIDTH
    if occurrence.window_end < occurrence.window_start:
        raise InvalidDoseTransitionError(
            "Cửa sổ liều không hợp lệ.", occurrence_id=occurrence.id
        )


def _same_scheduled_local_day(occurrence: DoseOccurrence, event_at: datetime) -> bool:
    if not occurrence.timezone:
        return False
    try:
        local_date = event_at.astimezone(ZoneInfo(occurrence.timezone)).date()
    except ZoneInfoNotFoundError:
        return False
    return local_date == occurrence.scheduled_local_date


def _validate_transition(occurrence: DoseOccurrence, target_status: str, event_at: datetime) -> None:
    current_status = occurrence.status or SCHEDULED
    if target_status not in _ALLOWED_TARGETS.get(current_status, frozenset()):
        raise InvalidDoseTransitionError(
            "Chuyển trạng thái liều không hợp lệ.",
            occurrence_id=occurrence.id,
            current_status=current_status,
            target_status=target_status,
        )
    _ensure_window(occurrence)
    assert occurrence.window_start is not None
    assert occurrence.window_end is not None
    if target_status == DUE and event_at < occurrence.due_at:
        raise InvalidDoseTransitionError("Liều chưa đến hạn.", occurrence_id=occurrence.id)
    if target_status == TAKEN and not occurrence.window_start <= event_at <= occurrence.window_end:
        raise InvalidDoseTransitionError("Xác nhận TAKEN nằm ngoài dose window.", occurrence_id=occurrence.id)
    if target_status == DELAYED and (
        event_at <= occurrence.window_end or not _same_scheduled_local_day(occurrence, event_at)
    ):
        raise InvalidDoseTransitionError(
            "DELAYED chỉ hợp lệ sau window_end trong cùng ngày địa phương.", occurrence_id=occurrence.id
        )
    if target_status == MISSED and event_at <= occurrence.window_end:
        raise InvalidDoseTransitionError("Dose window chưa kết thúc.", occurrence_id=occurrence.id)


def _cancel_pending_jobs(
    db: Session, occurrence: DoseOccurrence, *, event_at: datetime, source: str
) -> int:
    jobs = db.execute(
        select(NotificationJob).where(
            NotificationJob.dose_occurrence_id == occurrence.id,
            NotificationJob.status.in_((QUEUED, RETRY)),
        )
    ).scalars()
    cancelled = 0
    for job in jobs:
        job.status = CANCELLED
        job.updated_at = event_at
        _append_event(
            db,
            occurrence,
            event_type="REMINDER_CANCELLED",
            event_at=event_at,
            source=source,
            key_suffix=job.idempotency_key,
            metadata={"notification_job_id": job.id},
        )
        cancelled += 1
    return cancelled


def _transition_locked(
    db: Session,
    occurrence: DoseOccurrence,
    *,
    target_status: str,
    event_at: datetime,
    source: str,
    actor_type: str | None,
    actor_id: str | None,
) -> StateTransitionResult:
    current_status = occurrence.status or SCHEDULED
    if current_status == target_status:
        return StateTransitionResult(occurrence.id, current_status, changed=False)
    _validate_transition(occurrence, target_status, event_at)
    occurrence.status = target_status
    occurrence.status_reason = {
        DUE: "SCHEDULED_TIME_REACHED",
        TAKEN: "CONFIRMED_WITHIN_WINDOW",
        DELAYED: "CONFIRMED_AFTER_WINDOW_SAME_LOCAL_DAY",
        MISSED: "WINDOW_EXPIRED",
        SKIPPED: "EXPLICITLY_SKIPPED",
    }[target_status]
    occurrence.updated_at = event_at
    if target_status in {TAKEN, DELAYED}:
        occurrence.taken_at = event_at
    _append_event(
        db,
        occurrence,
        event_type=f"OCCURRENCE_{target_status}",
        event_at=event_at,
        source=source,
        actor_type=actor_type,
        actor_id=actor_id,
        metadata={"from_status": current_status, "to_status": target_status},
    )
    if target_status in _TERMINAL_STATES:
        _cancel_pending_jobs(db, occurrence, event_at=event_at, source=source)
    return StateTransitionResult(occurrence.id, target_status, changed=True)


def transition_dose_occurrence(
    db: Session,
    *,
    occurrence_id: str,
    target_status: str,
    event_at: datetime,
    source: str,
    actor_type: str | None = None,
    actor_id: str | None = None,
) -> StateTransitionResult:
    """Atomically apply one allowed V2 state transition and append its event."""

    event_at = _require_utc_instant(event_at, "event_at")
    occurrence = _locked_occurrence(db, occurrence_id)
    result = _transition_locked(
        db,
        occurrence,
        target_status=target_status,
        event_at=event_at,
        source=source,
        actor_type=actor_type,
        actor_id=actor_id,
    )
    db.flush()
    return result


def _validated_offsets(offsets: Sequence[timedelta]) -> tuple[timedelta, ...]:
    unique_offsets = tuple(sorted(set(offsets)))
    if any(offset < timedelta() or offset > DOSE_WINDOW_HALF_WIDTH for offset in unique_offsets):
        raise InvalidReminderConfigurationError(
            "Reminder offset phải nằm trong dose window ±30 phút.", offsets=list(unique_offsets)
        )
    return unique_offsets


def _queue_reminders(
    db: Session,
    occurrence: DoseOccurrence,
    *,
    offsets: Sequence[timedelta],
    event_at: datetime,
) -> tuple[int, int]:
    created = 0
    existing = 0
    for offset in _validated_offsets(offsets):
        job_key = _notification_key(occurrence.id, offset)
        if _find_staged_or_persisted(db, NotificationJob, job_key) is not None:
            existing += 1
            continue
        scheduled_at = _stored_utc_instant(occurrence.scheduled_at, "scheduled_at") + offset
        db.add(
            NotificationJob(
                id=_stable_id("notification-job", job_key),
                patient_id=occurrence.patient_id,
                dose_occurrence_id=occurrence.id,
                notification_type=NOTIFICATION_TYPE_DOSE_REMINDER,
                recipient_type=RECIPIENT_PATIENT,
                recipient_id=occurrence.patient_id,
                scheduled_at=scheduled_at,
                status=QUEUED,
                idempotency_key=job_key,
                payload={"reminder_offset_seconds": int(offset.total_seconds())},
            )
        )
        _append_event(
            db,
            occurrence,
            event_type="REMINDER_QUEUED",
            event_at=event_at,
            source="REMINDER_DOMAIN",
            key_suffix=job_key,
            metadata={"notification_job_id": _stable_id("notification-job", job_key)},
        )
        created += 1
    return created, existing


def advance_dose_occurrences(
    db: Session, *, now: datetime, reminder_offsets: Sequence[timedelta]
) -> ReminderAdvanceResult:
    """Advance due/missed occurrences and enqueue explicitly configured reminders.

    Follow-up cadence is intentionally supplied by the caller.  The documented
    T+15/T+30 proposal has not been approved by PM, so this domain never
    silently adopts it as a production policy.
    """

    now = _require_utc_instant(now, "now")
    offsets = _validated_offsets(reminder_offsets)
    result = ReminderAdvanceResult()
    occurrence_ids = db.execute(
        select(DoseOccurrence.id).where(
            DoseOccurrence.status.in_((SCHEDULED, DUE)), DoseOccurrence.scheduled_at <= now
        )
    ).scalars()
    for occurrence_id in occurrence_ids:
        occurrence = _locked_occurrence(db, occurrence_id)
        _ensure_window(occurrence)
        assert occurrence.window_end is not None
        if occurrence.status == SCHEDULED:
            due = _transition_locked(
                db,
                occurrence,
                target_status=DUE,
                event_at=now,
                source="REMINDER_DOMAIN",
                actor_type="SYSTEM",
                actor_id=None,
            )
            result.due += int(due.changed)
        if occurrence.status == DUE and now > occurrence.window_end:
            missed = _transition_locked(
                db,
                occurrence,
                target_status=MISSED,
                event_at=now,
                source="REMINDER_DOMAIN",
                actor_type="SYSTEM",
                actor_id=None,
            )
            result.missed += int(missed.changed)
            result.jobs_cancelled += _cancel_pending_jobs(
                db, occurrence, event_at=now, source="REMINDER_DOMAIN"
            )
        elif occurrence.status == DUE:
            created, existing = _queue_reminders(db, occurrence, offsets=offsets, event_at=now)
            result.jobs_created += created
            result.jobs_existing += existing
    db.flush()
    return result


def claim_notification_job(db: Session, *, job_id: str, now: datetime) -> NotificationJob | None:
    """Claim one due job under a row lock; a provider worker owns actual delivery."""

    now = _require_utc_instant(now, "now")
    reference = db.get(NotificationJob, job_id)
    if reference is None:
        return None
    occurrence = _locked_occurrence(db, reference.dose_occurrence_id) if reference.dose_occurrence_id else None
    job = db.execute(select(NotificationJob).where(NotificationJob.id == job_id).with_for_update()).scalar_one()
    if (
        job is None
        or job.status not in {QUEUED, RETRY}
        or _stored_utc_instant(job.scheduled_at, "scheduled_at") > now
        or occurrence is not None and occurrence.status != DUE
    ):
        return None
    job.status = PROCESSING
    job.attempt_count += 1
    job.last_attempt_at = now
    job.updated_at = now
    if occurrence is not None:
        _append_event(
            db,
            occurrence,
            event_type="REMINDER_ATTEMPTED",
            event_at=now,
            source="NOTIFICATION_WORKER",
            key_suffix=f"{job.idempotency_key}:attempt:{job.attempt_count}",
            metadata={"notification_job_id": job.id, "attempt_count": job.attempt_count},
        )
    db.flush()
    return job


def complete_notification_job(
    db: Session, *, job_id: str, now: datetime, delivered: bool, retry_at: datetime | None = None
) -> NotificationJob | None:
    """Persist delivery result; retry timing is explicit so no backoff is invented."""

    now = _require_utc_instant(now, "now")
    reference = db.get(NotificationJob, job_id)
    if reference is None:
        return None
    occurrence = _locked_occurrence(db, reference.dose_occurrence_id) if reference.dose_occurrence_id else None
    job = db.execute(select(NotificationJob).where(NotificationJob.id == job_id).with_for_update()).scalar_one()
    if job.status != PROCESSING:
        return None
    if occurrence is not None and occurrence.status != DUE:
        job.status = CANCELLED
        job.updated_at = now
        _append_event(
            db,
            occurrence,
            event_type="REMINDER_CANCELLED",
            event_at=now,
            source="NOTIFICATION_WORKER",
            key_suffix=job.idempotency_key,
            metadata={"notification_job_id": job.id, "reason": "OCCURRENCE_CLOSED"},
        )
        db.flush()
        return job
    if delivered:
        job.status = SENT
        job.sent_at = now
        event_type = "REMINDER_SENT"
    else:
        if retry_at is None:
            raise InvalidReminderConfigurationError("retry_at là bắt buộc khi delivery thất bại.")
        job.status = RETRY
        job.scheduled_at = _require_utc_instant(retry_at, "retry_at")
        event_type = "REMINDER_RETRY_SCHEDULED"
    job.updated_at = now
    if occurrence is not None:
        _append_event(
            db,
            occurrence,
            event_type=event_type,
            event_at=now,
            source="NOTIFICATION_WORKER",
            key_suffix=f"{job.idempotency_key}:attempt:{job.attempt_count}:{event_type}",
            metadata={"notification_job_id": job.id, "attempt_count": job.attempt_count},
        )
    db.flush()
    return job


__all__ = [
    "CANCELLED",
    "DELAYED",
    "DOSE_WINDOW_HALF_WIDTH",
    "DUE",
    "MISSED",
    "PROCESSING",
    "QUEUED",
    "RETRY",
    "SCHEDULED",
    "SENT",
    "SKIPPED",
    "TAKEN",
    "ReminderAdvanceResult",
    "StateTransitionResult",
    "advance_dose_occurrences",
    "claim_notification_job",
    "complete_notification_job",
    "transition_dose_occurrence",
]
