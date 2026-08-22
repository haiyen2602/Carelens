"""BUILD-29: unit tests for backend/services/agent_feedback.py -- trace
ownership verification, deterministic priority classification, and
idempotent ticket creation. Uses a real (SQLite, isolated) DB for the ticket
table and the real TelemetryService to seed the in-memory trace buffer, so
these exercise the actual hashing/lookup logic, not a mocked stand-in.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import backend.services.telemetry as telemetry_module
from backend.api.security import CurrentUser
from backend.db.models import AgentFeedbackTicket
from backend.models.schemas import AgentFeedbackCreateRequest
from backend.services.agent_feedback import (
    CrossPatientTraceError,
    classify_priority,
    create_ticket,
    session_messages,
    trace_summary_out,
    verify_trace_ownership,
)
from backend.services.telemetry import TelemetryService, hash_identifier


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    AgentFeedbackTicket.__table__.create(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def clean_trace_buffer():
    """Save/restore the module-level ring buffer so these tests never bleed
    fake traces into (or lose real ones from) another test/process."""
    original = list(telemetry_module._LOCAL_TRACE_BUFFER)
    telemetry_module._LOCAL_TRACE_BUFFER.clear()
    yield telemetry_module._LOCAL_TRACE_BUFFER
    telemetry_module._LOCAL_TRACE_BUFFER.clear()
    telemetry_module._LOCAL_TRACE_BUFFER.extend(original)


def _seed_trace(*, trace_id: str, user_id: str, session_id: str, intent: str | None = None, message="hi", response="ok", status="success"):
    svc = TelemetryService()
    trace = svc.create_trace(
        trace_id=trace_id,
        session_id=session_id,
        user_id=user_id,
        input_data={"message": message},
        metadata={"intent": intent} if intent else {},
    )
    svc.finalize_trace(trace, output_data={"response": response}, status=status)
    return trace


def _actor(actor_id="patient-account-1", patient_id="patient-1") -> CurrentUser:
    return CurrentUser(id=actor_id, role="patient", patient_id=patient_id, doctor_id=None)


def _payload(**overrides) -> AgentFeedbackCreateRequest:
    values = dict(
        conversation_id="conv-1",
        trace_id="trace-1",
        agent_run_id="run-1",
        user_message="tôi uống thuốc gì hôm nay",
        assistant_message="bạn chưa có đơn thuốc nào",
        reason="WRONG_ANSWER",
        user_note=None,
    )
    values.update(overrides)
    return AgentFeedbackCreateRequest(**values)


# ---------------------------------------------------------------------------
# verify_trace_ownership
# ---------------------------------------------------------------------------


def test_ownership_not_found_is_treated_as_owned(clean_trace_buffer):
    result = verify_trace_ownership("does-not-exist", actor_id="actor-1")
    assert result.found is False
    assert result.owned is True
    assert result.trace is None


def test_ownership_none_trace_id_is_treated_as_owned(clean_trace_buffer):
    result = verify_trace_ownership(None, actor_id="actor-1")
    assert result.found is False
    assert result.owned is True


def test_ownership_match(clean_trace_buffer):
    _seed_trace(trace_id="t-1", user_id="actor-1", session_id="conv-1")
    result = verify_trace_ownership("t-1", actor_id="actor-1")
    assert result.found is True
    assert result.owned is True
    assert result.trace is not None


def test_ownership_mismatch_is_denied(clean_trace_buffer):
    # Real trace belongs to a DIFFERENT account -- the exact cross-patient
    # attribution attack BUILD-29 §10 requires this module to catch.
    _seed_trace(trace_id="t-2", user_id="actor-victim", session_id="conv-victim")
    result = verify_trace_ownership("t-2", actor_id="actor-attacker")
    assert result.found is True
    assert result.owned is False


# ---------------------------------------------------------------------------
# classify_priority
# ---------------------------------------------------------------------------


def test_unsafe_reason_is_always_p0():
    priority, p0 = classify_priority("UNSAFE_OR_INAPPROPRIATE", trace=None)
    assert (priority, p0) == ("P0", True)


def test_acute_danger_trace_intent_forces_p0_regardless_of_reason(clean_trace_buffer):
    trace = _seed_trace(trace_id="t-3", user_id="a", session_id="c", intent="ACUTE_DANGER_ESCALATION")
    priority, p0 = classify_priority("WRONG_ANSWER", trace=trace)
    assert (priority, p0) == ("P0", True)


def test_doctor_review_trace_intent_forces_p0(clean_trace_buffer):
    trace = _seed_trace(trace_id="t-4", user_id="a", session_id="c", intent="DOCTOR_REVIEW")
    priority, p0 = classify_priority("OTHER", trace=trace)
    assert (priority, p0) == ("P0", True)


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("WRONG_MEDICATION_INFO", ("P1", False)),
        ("WRONG_ANSWER", ("P2", False)),
        ("NOT_UNDERSTOOD", ("P2", False)),
        ("TECHNICAL_ERROR", ("P2", False)),
        ("OTHER", ("P3", False)),
    ],
)
def test_ordinary_reasons_map_to_the_documented_priority(reason, expected):
    assert classify_priority(reason, trace=None) == expected


def test_ordinary_intent_does_not_escalate_priority(clean_trace_buffer):
    trace = _seed_trace(trace_id="t-5", user_id="a", session_id="c", intent="TODAY_DOSES")
    assert classify_priority("WRONG_ANSWER", trace=trace) == ("P2", False)


# ---------------------------------------------------------------------------
# create_ticket -- authorization binding, priority, idempotency
# ---------------------------------------------------------------------------


def test_create_ticket_binds_actor_and_patient_server_side(db, clean_trace_buffer):
    actor = _actor(actor_id="acct-1", patient_id="patient-99")
    ticket, created = create_ticket(db, actor=actor, payload=_payload(trace_id=None))
    db.commit()
    assert created is True
    assert ticket.actor_id == "acct-1"
    assert ticket.patient_id == "patient-99"
    assert ticket.status == "OPEN"
    assert ticket.priority == "P2"  # WRONG_ANSWER, no trace


def test_create_ticket_rejects_a_trace_owned_by_someone_else(db, clean_trace_buffer):
    _seed_trace(trace_id="t-6", user_id="victim-account", session_id="conv-victim")
    actor = _actor(actor_id="attacker-account")
    with pytest.raises(CrossPatientTraceError):
        create_ticket(db, actor=actor, payload=_payload(trace_id="t-6"))


def test_create_ticket_is_idempotent_for_the_same_actor_run_reason(db, clean_trace_buffer):
    actor = _actor()
    payload = _payload(agent_run_id="run-dup")
    ticket1, created1 = create_ticket(db, actor=actor, payload=payload)
    db.commit()
    ticket2, created2 = create_ticket(db, actor=actor, payload=payload)
    db.commit()

    assert created1 is True
    assert created2 is False
    assert ticket1.id == ticket2.id
    assert db.query(AgentFeedbackTicket).count() == 1


def test_create_ticket_same_turn_different_reason_is_a_distinct_ticket(db, clean_trace_buffer):
    actor = _actor()
    create_ticket(db, actor=actor, payload=_payload(agent_run_id="run-x", reason="WRONG_ANSWER"))
    db.commit()
    create_ticket(db, actor=actor, payload=_payload(agent_run_id="run-x", reason="TECHNICAL_ERROR"))
    db.commit()
    assert db.query(AgentFeedbackTicket).count() == 2


def test_create_ticket_classifies_unsafe_reason_as_p0_review_required(db, clean_trace_buffer):
    actor = _actor()
    ticket, _ = create_ticket(db, actor=actor, payload=_payload(agent_run_id="run-unsafe", reason="UNSAFE_OR_INAPPROPRIATE", trace_id=None))
    db.commit()
    assert ticket.priority == "P0"
    assert ticket.p0_review_required is True


# ---------------------------------------------------------------------------
# trace_summary_out / session_messages
# ---------------------------------------------------------------------------


def test_trace_summary_out_not_found_is_a_clean_negative_result(clean_trace_buffer):
    summary = trace_summary_out("nonexistent")
    assert summary.found is False
    assert summary.trace_id == "nonexistent"


def test_trace_summary_out_never_exposes_hidden_reasoning_only_final_response(clean_trace_buffer):
    svc = TelemetryService()
    trace = svc.create_trace(trace_id="t-7", session_id="c", user_id="a", input_data={"message": "hi"}, metadata={"intent": "DRUG_INFORMATION", "model": "gpt-5.4-mini"})
    obs = svc.start_observation(trace, name="tool.search_drug", obs_type="retriever", input_data={"tool": "search_drug"})
    svc.end_observation(obs, output_data={"items": []})
    svc.finalize_trace(trace, output_data={"response": "Paracetamol la thuoc giam dau."}, status="success")

    summary = trace_summary_out("t-7")
    assert summary.found is True
    assert summary.final_response == "Paracetamol la thuoc giam dau."
    assert summary.tools == ["search_drug"]
    assert summary.intent == "DRUG_INFORMATION"
    assert summary.model == "gpt-5.4-mini"


def test_session_messages_filters_by_conversation_and_paginates(clean_trace_buffer):
    _seed_trace(trace_id="s-1", user_id="a", session_id="conv-A", message="m1", response="r1")
    _seed_trace(trace_id="s-2", user_id="a", session_id="conv-A", message="m2", response="r2")
    _seed_trace(trace_id="s-3", user_id="a", session_id="conv-B", message="other", response="other")

    items, total = session_messages("conv-A", limit=10, offset=0)
    assert total == 2
    assert {item.trace_id for item in items} == {"s-1", "s-2"}


def test_session_messages_marks_the_reported_turn(clean_trace_buffer):
    _seed_trace(trace_id="s-4", user_id="a", session_id="conv-C")
    items, _ = session_messages("conv-C", limit=10, offset=0, highlight_trace_id="s-4")
    assert items[0].is_reported_turn is True
