from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from backend.db.models import DoctorReviewMessage, DoctorReviewRequest
from backend.services.doctor_handoff import DOCTOR_CONVERSATION_STOP_MESSAGE, HandoffStatus
from backend.services.doctor_takeover_timeout import close_inactive_takeovers


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
        assert len(patient_message_selects) == 1
    finally:
        event.remove(db.bind, "before_cursor_execute", record_statement)
        db.close()
