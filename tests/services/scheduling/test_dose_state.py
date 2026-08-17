"""DB-4G tests for V2 occurrence state and reminder outbox persistence."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.db.models import DoseEventLog, DoseOccurrence, NotificationJob
from backend.services.scheduling.dose_state import (
    CANCELLED,
    DELAYED,
    MISSED,
    PROCESSING,
    RETRY,
    SENT,
    SKIPPED,
    TAKEN,
    advance_dose_occurrences,
    claim_notification_job,
    complete_notification_job,
    transition_dose_occurrence,
)
from backend.services.scheduling.errors import InvalidDoseTransitionError

TABLES = (DoseOccurrence.__table__, DoseEventLog.__table__, NotificationJob.__table__)
SCHEDULED_AT = datetime(2026, 8, 17, 1, 0, tzinfo=UTC)


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for table in TABLES:
        table.create(engine)
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _occurrence(db: Session, occurrence_id: str = "occurrence-1") -> DoseOccurrence:
    occurrence = DoseOccurrence(
        id=occurrence_id,
        patient_id="patient-1",
        medication_plan_id="plan-1",
        drug_product_id="product-1",
        scheduled_at=SCHEDULED_AT,
        scheduled_local_date=date(2026, 8, 17),
        scheduled_local_time=time(8),
        timezone="Asia/Ho_Chi_Minh",
        status="SCHEDULED",
        generation_key=f"generation-{occurrence_id}",
        metadata_json={},
    )
    db.add(occurrence)
    db.flush()
    return occurrence


def _event_types(db: Session) -> list[str]:
    return db.execute(select(DoseEventLog.event_type).order_by(DoseEventLog.created_at)).scalars().all()


def test_due_reminders_are_idempotent_and_taken_cancels_pending_jobs(db: Session) -> None:
    occurrence = _occurrence(db)
    offsets = (timedelta(), timedelta(minutes=15))

    first = advance_dose_occurrences(db, now=SCHEDULED_AT, reminder_offsets=offsets)
    second = advance_dose_occurrences(
        db, now=SCHEDULED_AT + timedelta(minutes=1), reminder_offsets=offsets
    )
    taken = transition_dose_occurrence(
        db,
        occurrence_id=occurrence.id,
        target_status=TAKEN,
        event_at=SCHEDULED_AT + timedelta(minutes=10),
        source="PATIENT_CONFIRMATION",
        actor_type="PATIENT",
        actor_id="patient-1",
    )

    jobs = db.execute(select(NotificationJob).order_by(NotificationJob.scheduled_at)).scalars().all()
    assert (first.due, first.jobs_created) == (1, 2)
    assert (second.due, second.jobs_created, second.jobs_existing) == (0, 0, 2)
    assert taken.changed is True
    assert occurrence.status == TAKEN
    assert all(job.status == CANCELLED for job in jobs)
    assert _event_types(db) == [
        "OCCURRENCE_DUE",
        "REMINDER_QUEUED",
        "REMINDER_QUEUED",
        "OCCURRENCE_TAKEN",
        "REMINDER_CANCELLED",
        "REMINDER_CANCELLED",
    ]


@pytest.mark.parametrize(
    ("target", "event_at", "expected"),
    [
        (DELAYED, SCHEDULED_AT + timedelta(minutes=31), DELAYED),
        (SKIPPED, SCHEDULED_AT + timedelta(minutes=5), SKIPPED),
    ],
)
def test_due_occurrence_can_be_delayed_or_skipped(db: Session, target: str, event_at: datetime, expected: str) -> None:
    occurrence = _occurrence(db, target.lower())
    advance_dose_occurrences(db, now=SCHEDULED_AT, reminder_offsets=())

    result = transition_dose_occurrence(
        db,
        occurrence_id=occurrence.id,
        target_status=target,
        event_at=event_at,
        source="PATIENT_CONFIRMATION",
    )

    assert result.changed is True
    assert occurrence.status == expected
    assert occurrence.taken_at == event_at if target == DELAYED else occurrence.taken_at is None


def test_expired_scheduled_occurrence_records_due_then_missed_without_reminder(db: Session) -> None:
    occurrence = _occurrence(db)

    result = advance_dose_occurrences(
        db, now=SCHEDULED_AT + timedelta(minutes=31), reminder_offsets=(timedelta(),)
    )

    assert (result.due, result.missed, result.jobs_created) == (1, 1, 0)
    assert occurrence.status == MISSED
    assert _event_types(db) == ["OCCURRENCE_DUE", "OCCURRENCE_MISSED"]


def test_invalid_and_duplicate_transitions_do_not_create_duplicate_history(db: Session) -> None:
    occurrence = _occurrence(db)
    with pytest.raises(InvalidDoseTransitionError):
        transition_dose_occurrence(
            db,
            occurrence_id=occurrence.id,
            target_status=TAKEN,
            event_at=SCHEDULED_AT,
            source="PATIENT_CONFIRMATION",
        )

    advance_dose_occurrences(db, now=SCHEDULED_AT, reminder_offsets=())
    with pytest.raises(InvalidDoseTransitionError):
        transition_dose_occurrence(
            db,
            occurrence_id=occurrence.id,
            target_status=TAKEN,
            event_at=SCHEDULED_AT + timedelta(minutes=31),
            source="PATIENT_CONFIRMATION",
        )
    first = transition_dose_occurrence(
        db,
        occurrence_id=occurrence.id,
        target_status=TAKEN,
        event_at=SCHEDULED_AT + timedelta(minutes=1),
        source="PATIENT_CONFIRMATION",
    )
    duplicate = transition_dose_occurrence(
        db,
        occurrence_id=occurrence.id,
        target_status=TAKEN,
        event_at=SCHEDULED_AT + timedelta(minutes=2),
        source="PATIENT_CONFIRMATION",
    )

    assert (first.changed, duplicate.changed) == (True, False)
    assert _event_types(db).count("OCCURRENCE_TAKEN") == 1


def test_notification_retry_claim_and_delivery_are_serializable(db: Session) -> None:
    _occurrence(db)
    advance_dose_occurrences(db, now=SCHEDULED_AT, reminder_offsets=(timedelta(),))
    job = db.execute(select(NotificationJob)).scalar_one()

    claimed = claim_notification_job(db, job_id=job.id, now=SCHEDULED_AT)
    assert claimed is job and job.status == PROCESSING
    retry_at = SCHEDULED_AT + timedelta(minutes=5)
    retried = complete_notification_job(
        db, job_id=job.id, now=SCHEDULED_AT, delivered=False, retry_at=retry_at
    )
    assert retried is job and job.status == RETRY
    too_early = claim_notification_job(db, job_id=job.id, now=retry_at - timedelta(seconds=1))
    claimed_again = claim_notification_job(db, job_id=job.id, now=retry_at)
    assert too_early is None
    assert claimed_again is job and job.status == PROCESSING and job.attempt_count == 2
    sent = complete_notification_job(db, job_id=job.id, now=retry_at, delivered=True)

    assert sent is job and job.status == SENT
    assert _event_types(db) == [
        "OCCURRENCE_DUE",
        "REMINDER_QUEUED",
        "REMINDER_ATTEMPTED",
        "REMINDER_RETRY_SCHEDULED",
        "REMINDER_ATTEMPTED",
        "REMINDER_SENT",
    ]


def test_claimed_reminder_is_cancelled_when_the_occurrence_closes(db: Session) -> None:
    occurrence = _occurrence(db)
    advance_dose_occurrences(db, now=SCHEDULED_AT, reminder_offsets=(timedelta(),))
    job = db.execute(select(NotificationJob)).scalar_one()
    assert claim_notification_job(db, job_id=job.id, now=SCHEDULED_AT) is job

    transition_dose_occurrence(
        db,
        occurrence_id=occurrence.id,
        target_status=TAKEN,
        event_at=SCHEDULED_AT + timedelta(minutes=1),
        source="PATIENT_CONFIRMATION",
    )
    completed = complete_notification_job(
        db, job_id=job.id, now=SCHEDULED_AT + timedelta(minutes=1), delivered=True
    )

    assert completed is job and job.status == CANCELLED
    assert "REMINDER_SENT" not in _event_types(db)
    assert _event_types(db).count("REMINDER_CANCELLED") == 1


def test_state_and_events_roll_back_together(db: Session) -> None:
    occurrence = _occurrence(db)
    db.commit()

    with pytest.raises(RuntimeError), db.begin():
        advance_dose_occurrences(db, now=SCHEDULED_AT, reminder_offsets=(timedelta(),))
        raise RuntimeError("force rollback")

    db.expire_all()
    assert db.get(DoseOccurrence, occurrence.id).status == "SCHEDULED"
    assert db.execute(select(DoseEventLog)).scalars().all() == []
    assert db.execute(select(NotificationJob)).scalars().all() == []
