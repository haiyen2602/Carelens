"""BUILD-29: unit tests for backend/services/agent_feedback.py -- trace
ownership verification, deterministic priority classification, and
idempotent ticket creation. Uses a real (SQLite, isolated) DB for the ticket
table and the real TelemetryService to seed the in-memory trace buffer, so
these exercise the actual hashing/lookup logic, not a mocked stand-in.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import backend.services.telemetry as telemetry_module
from backend.api.security import CurrentUser
from backend.db.models import AgentFeedbackTicket, AgentRun, AgentRunEvaluation, AgentRunSpan
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
    # BUILD-32: verify_trace_ownership/trace_summary_out/session_messages now
    # query AgentRun/AgentRunSpan first (durable source of truth) -- those
    # tables need to exist here too, not just AgentFeedbackTicket.
    engine = create_engine("sqlite+pysqlite:///:memory:")
    AgentFeedbackTicket.__table__.create(engine)
    AgentRun.__table__.create(engine)
    AgentRunSpan.__table__.create(engine)
    AgentRunEvaluation.__table__.create(engine)
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


def test_ownership_not_found_is_treated_as_owned(db, clean_trace_buffer):
    result = verify_trace_ownership(db, "does-not-exist", actor_id="actor-1")
    assert result.found is False
    assert result.owned is True
    assert result.intent is None


def test_ownership_none_trace_id_is_treated_as_owned(db, clean_trace_buffer):
    result = verify_trace_ownership(db, None, actor_id="actor-1")
    assert result.found is False
    assert result.owned is True


def test_ownership_match(db, clean_trace_buffer):
    _seed_trace(trace_id="t-1", user_id="actor-1", session_id="conv-1")
    result = verify_trace_ownership(db, "t-1", actor_id="actor-1")
    assert result.found is True
    assert result.owned is True


def test_ownership_mismatch_is_denied(db, clean_trace_buffer):
    # Real trace belongs to a DIFFERENT account -- the exact cross-patient
    # attribution attack BUILD-29 §10 requires this module to catch.
    _seed_trace(trace_id="t-2", user_id="actor-victim", session_id="conv-victim")
    result = verify_trace_ownership(db, "t-2", actor_id="actor-attacker")
    assert result.found is True
    assert result.owned is False


# ---------------------------------------------------------------------------
# classify_priority
# ---------------------------------------------------------------------------


def test_unsafe_reason_is_always_p0():
    priority, p0 = classify_priority("UNSAFE_OR_INAPPROPRIATE", intent=None)
    assert (priority, p0) == ("P0", True)


def test_acute_danger_trace_intent_forces_p0_regardless_of_reason():
    priority, p0 = classify_priority("WRONG_ANSWER", intent="ACUTE_DANGER_ESCALATION")
    assert (priority, p0) == ("P0", True)


def test_doctor_review_trace_intent_forces_p0():
    priority, p0 = classify_priority("OTHER", intent="DOCTOR_REVIEW")
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
    assert classify_priority(reason, intent=None) == expected


def test_ordinary_intent_does_not_escalate_priority():
    assert classify_priority("WRONG_ANSWER", intent="TODAY_DOSES") == ("P2", False)


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


def test_trace_summary_out_not_found_is_a_clean_negative_result(db, clean_trace_buffer):
    summary = trace_summary_out(db, "nonexistent")
    assert summary.found is False
    assert summary.trace_id == "nonexistent"


def test_trace_summary_out_never_exposes_hidden_reasoning_only_final_response(db, clean_trace_buffer):
    # No durable AgentRun row for this trace_id -- falls back to the ring
    # buffer, same as before BUILD-32 (see verify_trace_ownership's own
    # docstring for why the fallback exists).
    svc = TelemetryService()
    trace = svc.create_trace(trace_id="t-7", session_id="c", user_id="a", input_data={"message": "hi"}, metadata={"intent": "DRUG_INFORMATION", "model": "gpt-5.4-mini"})
    obs = svc.start_observation(trace, name="tool.search_drug", obs_type="retriever", input_data={"tool": "search_drug"})
    svc.end_observation(obs, output_data={"items": []})
    svc.finalize_trace(trace, output_data={"response": "Paracetamol la thuoc giam dau."}, status="success")

    summary = trace_summary_out(db, "t-7")
    assert summary.found is True
    assert summary.final_response == "Paracetamol la thuoc giam dau."
    assert summary.tools == ["search_drug"]
    assert summary.intent == "DRUG_INFORMATION"
    assert summary.model == "gpt-5.4-mini"


def test_trace_summary_out_prefers_the_ring_buffer_when_both_exist(db, clean_trace_buffer):
    """BUILD-32 bugfix: the ring buffer wins when a trace is present in both
    -- it carries the real final_response/tool-output/scores the durable
    row deliberately never does. An earlier version of this function got
    this backwards (durable-first), which meant almost every ticket detail
    silently lost its real reply text the moment AgentRun existed (i.e.
    always, since AgentRun is written at checkpoint time on every request)."""
    _seed_trace(trace_id="t-durable", user_id="a", session_id="c", intent="DRUG_INFORMATION")
    db.add(
        AgentRun(
            id="run-durable",
            trace_id="t-durable",
            conversation_id="c",
            actor_id="a",
            intent="DRUG_INFORMATION",
            status="COMPLETED",
            started_at=datetime.now(UTC),
            model="gpt-5.4-mini",
            duration_ms=42.0,
        )
    )
    db.commit()

    summary = trace_summary_out(db, "t-durable")
    assert summary.found is True
    # Ring-buffer-sourced fields, NOT the durable row's -- proves priority.
    assert summary.status == "success"
    assert summary.final_response == "ok"  # _seed_trace's default response


def test_trace_summary_out_falls_back_to_the_durable_row_when_buffer_lacks_it(db, clean_trace_buffer):
    """No ring-buffer entry for this trace_id (aged out / pre-restart) --
    durable AgentRun is still readable, with its own honest scope limit
    (no final_response text)."""
    db.add(
        AgentRun(
            id="run-durable-2",
            trace_id="t-durable-only",
            conversation_id="c",
            actor_id="a",
            intent="DRUG_INFORMATION",
            status="COMPLETED",
            started_at=datetime.now(UTC),
            model="gpt-5.4-mini",
            duration_ms=42.0,
        )
    )
    db.commit()

    summary = trace_summary_out(db, "t-durable-only")
    assert summary.found is True
    assert summary.status == "COMPLETED"
    assert summary.model == "gpt-5.4-mini"
    assert summary.latency_ms == 42.0
    # Honest scope limit (BUILD-32 report): message/response text is not part
    # of the durable schema.
    assert summary.final_response is None


def test_session_messages_filters_by_conversation_and_paginates(db, clean_trace_buffer):
    _seed_trace(trace_id="s-1", user_id="a", session_id="conv-A", message="m1", response="r1")
    _seed_trace(trace_id="s-2", user_id="a", session_id="conv-A", message="m2", response="r2")
    _seed_trace(trace_id="s-3", user_id="a", session_id="conv-B", message="other", response="other")

    items, total = session_messages(db, "conv-A", limit=10, offset=0)
    assert total == 2
    assert {item.trace_id for item in items} == {"s-1", "s-2"}


def test_session_messages_marks_the_reported_turn(db, clean_trace_buffer):
    _seed_trace(trace_id="s-4", user_id="a", session_id="conv-C")
    items, _ = session_messages(db, "conv-C", limit=10, offset=0, highlight_trace_id="s-4")
    assert items[0].is_reported_turn is True


# ---------------------------------------------------------------------------
# BUILD-32 bugfix: a durable-read failure (e.g. migration not yet applied on
# this environment) must degrade to the pre-BUILD-32 ring-buffer-only
# behavior, never raise out and break the whole page/ticket flow -- this is
# the real root cause the reported Admin-page "N/A" incident traced back to.
# ---------------------------------------------------------------------------


def test_verify_trace_ownership_degrades_to_ring_buffer_on_durable_read_failure(db, clean_trace_buffer, monkeypatch):
    _seed_trace(trace_id="t-degrade", user_id="actor-1", session_id="c")

    def _boom(*_args, **_kwargs):
        raise Exception("simulated missing column")  # noqa: BLE001

    monkeypatch.setattr(db, "execute", _boom)
    result = verify_trace_ownership(db, "t-degrade", actor_id="actor-1")
    # Durable lookup failed (caught, logged, run=None) -- falls through to
    # the ring-buffer loop, which reads the in-memory buffer directly (no
    # `db` involved) and still finds the real match.
    assert result.found is True
    assert result.owned is True


def test_trace_summary_out_degrades_to_ring_buffer_on_durable_read_failure(db, clean_trace_buffer, monkeypatch):
    _seed_trace(trace_id="t-degrade-2", user_id="a", session_id="c", response="real answer")

    def _boom(*_args, **_kwargs):
        raise Exception("simulated missing column")  # noqa: BLE001

    monkeypatch.setattr(db, "execute", _boom)
    # Ring buffer is checked FIRST now, so this succeeds without ever
    # touching the (broken) durable path.
    summary = trace_summary_out(db, "t-degrade-2")
    assert summary.found is True
    assert summary.final_response == "real answer"


def test_session_messages_degrades_to_ring_buffer_on_durable_read_failure(db, clean_trace_buffer, monkeypatch):
    _seed_trace(trace_id="t-degrade-3", user_id="a", session_id="conv-D")

    def _boom(*_args, **_kwargs):
        raise Exception("simulated missing column")  # noqa: BLE001

    monkeypatch.setattr(db, "execute", _boom)
    items, total = session_messages(db, "conv-D", limit=10, offset=0)
    assert total == 1
    assert items[0].trace_id == "t-degrade-3"
