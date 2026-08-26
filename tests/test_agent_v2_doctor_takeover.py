"""BUILD-44: Agent V2 bot-suppression during an ACTIVE doctor takeover.

Real HTTP-route-level (``run_agent_orchestration``) tests against a real
on-disk SQLite DB (new, genuinely independent sessions per call -- same
discipline ``test_agent_v2_transaction_durability.py`` already established
for exactly this reason: a shared, still-open session can pass even when
the route never committed). An ACTIVE takeover short-circuits BEFORE
``OpenAIModelGateway.from_settings(...)`` is ever constructed (see
``agent_v2_routes.py::run_agent_orchestration``), so these tests make zero
network calls by construction -- no mocking required, and a real accidental
model call would simply hang/fail these tests rather than silently pass.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.api.agent_v2_routes import run_agent_orchestration
from backend.api.security import CurrentUser
from backend.config import get_settings
from backend.db.models import (
    AgentIdempotencyKey,
    AgentRun,
    AgentRunCheckpoint,
    DoctorReviewMessage,
    DoctorReviewRequest,
    Patient,
)
from backend.models.schemas import AgentV2OrchestrateRequest
from backend.services.doctor_handoff import get_active_takeover

TABLES = (
    Patient.__table__,
    AgentRun.__table__,
    AgentRunCheckpoint.__table__,
    DoctorReviewRequest.__table__,
    DoctorReviewMessage.__table__,
    AgentIdempotencyKey.__table__,
)


@pytest.fixture(autouse=True)
def _agent_runtime_enabled(monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def db_path(tmp_path) -> str:
    path = str(tmp_path / "takeover.db")
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    for table in TABLES:
        table.create(engine)
    engine.dispose()
    return path


def _new_session(db_path: str) -> Session:
    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
    return Session(engine, expire_on_commit=False)


def _seed_patient(db_path: str, patient_id: str = "patient-1") -> None:
    session = _new_session(db_path)
    try:
        session.add(Patient(id=patient_id, full_name="Test Patient"))
        session.commit()
    finally:
        session.close()


def _seed_handoff(db_path: str, *, patient_id: str = "patient-1", status: str, doctor_id: str | None = "doctor-1") -> str:
    session = _new_session(db_path)
    try:
        handoff_id = f"handoff-{uuid.uuid4().hex[:8]}"
        session.add(
            DoctorReviewRequest(
                id=handoff_id, patient_id=patient_id, created_by_actor_id="account-1",
                reason_code="REPEATED_CLARIFICATION", risk_disposition="UNCERTAINTY_HANDOFF",
                patient_question="test", agent_summary="test", status=status,
                idempotency_key=f"key-{handoff_id}", assigned_doctor_id=doctor_id,
            )
        )
        session.commit()
        return handoff_id
    finally:
        session.close()


def _actor(patient_id: str = "patient-1") -> CurrentUser:
    return CurrentUser(id="account-1", role="patient", patient_id=patient_id, doctor_id=None)


def _http_request(patient_id: str = "patient-1", **overrides) -> AgentV2OrchestrateRequest:
    values = dict(patient_id=patient_id, message="Tác dụng phụ thì sao?")
    values.update(overrides)
    return AgentV2OrchestrateRequest(**values)


# ---------------------------------------------------------------------------
# get_active_takeover: which statuses count (unit-level, no HTTP needed)
# ---------------------------------------------------------------------------


def test_get_active_takeover_returns_none_for_pending_and_assigned(db_path):
    _seed_patient(db_path)
    _seed_handoff(db_path, status="PENDING", doctor_id=None)
    session = _new_session(db_path)
    try:
        assert get_active_takeover(session, patient_id="patient-1") is None
    finally:
        session.close()

    _seed_patient(db_path, patient_id="patient-2")
    _seed_handoff(db_path, patient_id="patient-2", status="ASSIGNED")
    session = _new_session(db_path)
    try:
        assert get_active_takeover(session, patient_id="patient-2") is None
    finally:
        session.close()


def test_get_active_takeover_returns_the_row_for_active(db_path):
    _seed_patient(db_path)
    handoff_id = _seed_handoff(db_path, status="ACTIVE")
    session = _new_session(db_path)
    try:
        row = get_active_takeover(session, patient_id="patient-1")
        assert row is not None
        assert row.id == handoff_id
    finally:
        session.close()


def test_get_active_takeover_returns_none_after_resolved(db_path):
    _seed_patient(db_path)
    _seed_handoff(db_path, status="RESOLVED")
    session = _new_session(db_path)
    try:
        assert get_active_takeover(session, patient_id="patient-1") is None
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Real HTTP-route-level bot suppression
# ---------------------------------------------------------------------------


def test_active_takeover_suppresses_bot_with_zero_model_calls_and_persists_message(db_path):
    _seed_patient(db_path)
    handoff_id = _seed_handoff(db_path, status="ACTIVE")

    session = _new_session(db_path)
    try:
        response = run_agent_orchestration(_http_request(), db=session, actor=_actor())
    finally:
        session.close()

    assert response.status == "DOCTOR_ACTIVE"
    assert response.handoff_required is True
    assert response.handoff_id == handoff_id
    assert response.handoff_type == "UNCERTAINTY"
    assert "bác sĩ" in response.reply.casefold()

    session = _new_session(db_path)
    try:
        run = session.get(AgentRun, response.agent_run_id)
        assert run is not None
        assert run.status == "DOCTOR_ACTIVE"
        assert run.model_calls == 0
        assert run.completed_at is not None

        messages = session.execute(
            select(DoctorReviewMessage).where(DoctorReviewMessage.handoff_id == handoff_id)
        ).scalars().all()
        assert len(messages) == 1
        assert messages[0].sender_role == "PATIENT"
        assert messages[0].content == "Tác dụng phụ thì sao?"
        assert messages[0].actor_id == "account-1"
    finally:
        session.close()


def test_active_takeover_creates_no_duplicate_handoff(db_path):
    _seed_patient(db_path)
    _seed_handoff(db_path, status="ACTIVE")

    session = _new_session(db_path)
    try:
        run_agent_orchestration(_http_request(), db=session, actor=_actor())
    finally:
        session.close()

    session = _new_session(db_path)
    try:
        count = session.execute(
            select(DoctorReviewRequest).where(DoctorReviewRequest.patient_id == "patient-1")
        ).scalars().all()
        assert len(count) == 1
    finally:
        session.close()


def test_two_patient_messages_during_active_takeover_both_persisted_zero_bot_replies_in_order(db_path):
    """SS26-C: patient sends two messages during ACTIVE -> both persisted,
    zero bot replies, deterministic order."""
    _seed_patient(db_path)
    handoff_id = _seed_handoff(db_path, status="ACTIVE")

    for message in ("Tin nhắn thứ nhất", "Tin nhắn thứ hai"):
        session = _new_session(db_path)
        try:
            response = run_agent_orchestration(_http_request(message=message), db=session, actor=_actor())
        finally:
            session.close()
        assert response.status == "DOCTOR_ACTIVE"

    session = _new_session(db_path)
    try:
        messages = session.execute(
            select(DoctorReviewMessage)
            .where(DoctorReviewMessage.handoff_id == handoff_id)
            .order_by(DoctorReviewMessage.created_at, DoctorReviewMessage.id)
        ).scalars().all()
        assert [m.content for m in messages] == ["Tin nhắn thứ nhất", "Tin nhắn thứ hai"]
        assert all(m.sender_role == "PATIENT" for m in messages)
    finally:
        session.close()


def test_active_takeover_is_patient_scoped_not_conversation_scoped(db_path):
    """A fresh conversation_id for the SAME patient must still be
    suppressed while ACTIVE -- BUILD-42's own dedup scope, see the
    BUILD-44 report SS15."""
    _seed_patient(db_path)
    _seed_handoff(db_path, status="ACTIVE")

    session = _new_session(db_path)
    try:
        response = run_agent_orchestration(
            _http_request(conversation_id=f"brand-new-conversation-{uuid.uuid4().hex[:6]}"), db=session, actor=_actor()
        )
    finally:
        session.close()
    assert response.status == "DOCTOR_ACTIVE"


def test_active_takeover_for_a_different_patient_does_not_suppress(db_path):
    _seed_patient(db_path, patient_id="patient-1")
    _seed_patient(db_path, patient_id="patient-2")
    _seed_handoff(db_path, patient_id="patient-2", status="ACTIVE")

    session = _new_session(db_path)
    try:
        active = get_active_takeover(session, patient_id="patient-1")
    finally:
        session.close()
    assert active is None
