from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from backend.db.models import DoctorReviewMessage, DoctorReviewRequest
from backend.services.doctor_handoff import (
    DOCTOR_CONVERSATION_STOP_MESSAGE,
    PATIENT_CONVERSATION_STOP_MESSAGE,
    HandoffStatus,
    stop_active_doctor_review_request,
    stop_inactive_doctor_review_request,
)
from backend.services.doctor_takeover_timeout import _as_utc, close_inactive_takeovers


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    DoctorReviewRequest.__table__.create(engine)
    DoctorReviewMessage.__table__.create(engine)
    return Session(engine)


def _active_handoff(db: Session, *, handoff_id: str = "handoff-1", activated_at: datetime) -> DoctorReviewRequest:
    row = DoctorReviewRequest(
        id=handoff_id,
        patient_id="patient-1",
        created_by_actor_id="account-1",
        reason_code="REPEATED_CLARIFICATION",
        risk_disposition="UNCERTAINTY_HANDOFF",
        patient_question="test",
        agent_summary="test",
        status=HandoffStatus.ACTIVE,
        idempotency_key=f"timeout-test-{handoff_id}",
        activated_at=activated_at,
    )
    db.add(row)
    db.commit()
    return row


def test_timeout_stops_inactive_takeover_once_and_persists_terminal_message() -> None:
    now = datetime(2026, 8, 30, 12, tzinfo=UTC)
    db = _session()
    try:
        _active_handoff(db, activated_at=now - timedelta(minutes=10))

        assert close_inactive_takeovers(db, now=now) == 1
        row = db.get(DoctorReviewRequest, "handoff-1")
        assert row is not None
        assert row.status == HandoffStatus.RESOLVED
        messages = db.execute(select(DoctorReviewMessage)).scalars().all()
        assert [(message.sender_role, message.content) for message in messages] == [
            ("SYSTEM", DOCTOR_CONVERSATION_STOP_MESSAGE)
        ]

        assert close_inactive_takeovers(db, now=now + timedelta(minutes=1)) == 0
        assert db.execute(select(DoctorReviewMessage)).scalars().all() == messages
    finally:
        db.close()


def test_timeout_waits_for_ten_minutes_after_latest_patient_message() -> None:
    now = datetime(2026, 8, 30, 12, tzinfo=UTC)
    db = _session()
    try:
        _active_handoff(db, activated_at=now - timedelta(hours=1))
        db.add(
            DoctorReviewMessage(
                handoff_id="handoff-1",
                patient_id="patient-1",
                sender_role="PATIENT",
                actor_id="account-1",
                content="Tôi vẫn đang trao đổi",
                created_at=now - timedelta(minutes=9),
            )
        )
        db.commit()

        assert close_inactive_takeovers(db, now=now) == 0
        assert db.get(DoctorReviewRequest, "handoff-1").status == HandoffStatus.ACTIVE
    finally:
        db.close()


def test_patient_stop_persists_patient_terminal_message_once() -> None:
    now = datetime(2026, 8, 30, 12, tzinfo=UTC)
    db = _session()
    try:
        _active_handoff(db, activated_at=now)

        stopped = stop_active_doctor_review_request(
            db,
            request_id="handoff-1",
            patient_id="patient-1",
            stopped_at=now,
        )
        db.commit()
        assert stopped.status == HandoffStatus.RESOLVED
        assert [
            (message.sender_role, message.content)
            for message in db.execute(select(DoctorReviewMessage)).scalars().all()
        ] == [("SYSTEM", PATIENT_CONVERSATION_STOP_MESSAGE)]

        repeated = stop_active_doctor_review_request(
            db,
            request_id="handoff-1",
            patient_id="patient-1",
            stopped_at=now + timedelta(minutes=1),
        )
        db.commit()
        assert repeated.status == HandoffStatus.RESOLVED
        assert db.execute(select(DoctorReviewMessage)).scalars().all()[0].content == PATIENT_CONVERSATION_STOP_MESSAGE
    finally:
        db.close()


def test_timeout_loads_patient_activity_in_one_query_for_all_active_handoffs() -> None:
    now = datetime(2026, 8, 30, 12, tzinfo=UTC)
    db = _session()
    statements: list[str] = []

    def record_statement(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        statements.append(statement)

    try:
        _active_handoff(db, handoff_id="handoff-1", activated_at=now - timedelta(minutes=10))
        _active_handoff(db, handoff_id="handoff-2", activated_at=now - timedelta(minutes=10))
        event.listen(db.bind, "before_cursor_execute", record_statement)

        assert close_inactive_takeovers(db, now=now) == 2

        patient_message_selects = [
            statement
            for statement in statements
            if statement.lstrip().upper().startswith("SELECT") and DoctorReviewMessage.__tablename__ in statement
        ]
        # One aggregate query finds candidates. Each candidate is then
        # rechecked under its own row lock to close the stale-read race.
        assert len([statement for statement in patient_message_selects if "max(" in statement.lower()]) == 1
        assert len(patient_message_selects) == 3
    finally:
        event.remove(db.bind, "before_cursor_execute", record_statement)
        db.close()


def test_timeout_rechecks_activity_after_acquiring_handoff_lock() -> None:
    now = datetime(2026, 8, 30, 12, tzinfo=UTC)
    db = _session()
    try:
        _active_handoff(db, activated_at=now - timedelta(hours=1))
        # Simulates a patient turn committed after the scanner found an old
        # candidate but before it acquired this handoff's lifecycle lock.
        db.add(
            DoctorReviewMessage(
                handoff_id="handoff-1",
                patient_id="patient-1",
                sender_role="PATIENT",
                actor_id="account-1",
                content="Tôi vừa nhắn tiếp",
                created_at=now - timedelta(seconds=1),
            )
        )
        db.commit()

        assert (
            stop_inactive_doctor_review_request(
                db,
                request_id="handoff-1",
                stopped_at=now,
                inactive_for=timedelta(minutes=10),
            )
            is None
        )
        assert db.get(DoctorReviewRequest, "handoff-1").status == HandoffStatus.ACTIVE
    finally:
        db.close()


def test_naive_timestamp_is_rejected_outside_sqlite() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _as_utc(datetime(2026, 8, 30, 12), dialect_name="postgresql")
