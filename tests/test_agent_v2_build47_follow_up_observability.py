"""BUILD-47: the follow-up classifier's own decision must become durable.

BUILD-43 built the deterministic follow-up taxonomy (`backend/agents/v2/
follow_up.py`) that decides whether a turn inherits the prior topic/entity,
and BUILD-43 already emits it as an `agent_context_resolution.completed`
telemetry event -- but the four attributes that actually carry the decision
were never in `_ALLOWED_ATTRIBUTE_KEYS`, so `_sanitize_attributes` silently
dropped them before the event reached any sink, and the event itself is a
bare marker (no `latency_ms`) that `_build_span_rows` deliberately never
turns into an `AgentRunSpan` row. Net effect: there was no way -- log or DB --
to measure how often the classifier inherits context versus loses it.

These tests lock both halves of the fix: the sanitizer must let the four keys
through, and `_persist_durable_trace` must stamp them onto the run row.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.agents.v2.follow_up import (
    FollowUpCategory,
    FollowUpDecision,
    FollowUpReasonCode,
)
from backend.agents.v2.model_gateway import ModelPlan
from backend.agents.v2.observability import (
    AgentTelemetry,
    BufferingSink,
    ModelPricingCatalog,
    StructuredLogSink,
    _sanitize_attributes,
)
from backend.agents.v2.runtime import RunMetrics, RunStatus
from backend.api.security import CurrentUser
from backend.db.models import AgentRun, AgentRunEvaluation, AgentRunSpan
from tests.test_agent_v2_orchestrator import _orchestrator, _request, _SpyModelGateway, _tools

# ---------------------------------------------------------------------------
# _sanitize_attributes allowlist
# ---------------------------------------------------------------------------


def test_sanitize_attributes_allows_follow_up_keys():
    """All four follow-up attributes survive sanitization.

    Before BUILD-47 every one of these was dropped, which is why the
    `agent_context_resolution.completed` log line carried only
    `final_router_intent` and nothing about the actual decision.
    """
    safe = _sanitize_attributes(
        {
            "follow_up_category": "TRUE_FOLLOWUP",
            "follow_up_reason_code": "DEICTIC_OR_ATTRIBUTE_ONLY_WITH_PRIOR_CONTEXT",
            "inherited_topic": False,
            "inherited_entity": True,
            "final_router_intent": "DRUG_INFORMATION",
        }
    )
    assert safe["follow_up_category"] == "TRUE_FOLLOWUP"
    assert safe["follow_up_reason_code"] == "DEICTIC_OR_ATTRIBUTE_ONLY_WITH_PRIOR_CONTEXT"
    assert safe["inherited_topic"] is False
    assert safe["inherited_entity"] is True


def test_sanitize_attributes_still_rejects_malformed_follow_up_values():
    """The allowlist widens; the value discipline does not.

    `_SAFE_CODE` is what keeps a free-text/user-controlled string out of the
    telemetry record -- widening the key allowlist must not become a hole for
    arbitrary content (e.g. a raw patient message) to reach the log.
    """
    safe = _sanitize_attributes(
        {
            "follow_up_category": "tôi bị đau đầu quá",  # not a SAFE_CODE constant
            "follow_up_reason_code": "lowercase_not_a_code",
        }
    )
    assert "follow_up_category" not in safe
    assert "follow_up_reason_code" not in safe


def test_sanitize_attributes_passes_through_none_follow_up_values():
    """A turn that never ran the classifier emits None, not a fabricated value."""
    safe = _sanitize_attributes({"follow_up_category": None, "follow_up_reason_code": None})
    assert safe["follow_up_category"] is None
    assert safe["follow_up_reason_code"] is None


# ---------------------------------------------------------------------------
# _persist_durable_trace stamping
# ---------------------------------------------------------------------------


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    AgentRun.__table__.create(engine)
    AgentRunSpan.__table__.create(engine)
    AgentRunEvaluation.__table__.create(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _actor() -> CurrentUser:
    return CurrentUser(id="actor-1", role="patient", patient_id="patient-1", doctor_id=None)


def _fake_result(*, agent_run_id: str, trace_id: str, follow_up_decision=None):
    return SimpleNamespace(
        agent_run_id=agent_run_id,
        trace_id=trace_id,
        status=RunStatus.COMPLETED,
        response="ok",
        error_code=None,
        intent=SimpleNamespace(value="DRUG_INFORMATION"),
        tool_results=(),
        citations=(),
        safety_decision=None,
        handoff_result=None,
        metrics=RunMetrics(
            steps=1,
            model_calls=1,
            tool_calls=0,
            retries=0,
            input_tokens=100,
            cached_input_tokens=0,
            output_tokens=50,
            elapsed_ms=123.0,
        ),
        follow_up_decision=follow_up_decision,
    )


def _persist(db: Session, monkeypatch, result) -> AgentRun:
    import backend.api.agent_v2_routes as routes

    sink = BufferingSink(StructuredLogSink())
    monkeypatch.setattr(routes, "_telemetry_sink", sink)
    telemetry = AgentTelemetry(sink=sink, pricing=ModelPricingCatalog({}, version="v1"))
    settings = SimpleNamespace(agent_main_model="gpt-5.4-mini")
    routes._persist_durable_trace(db, result=result, telemetry=telemetry, settings=settings, actor=_actor())
    return db.get(AgentRun, result.agent_run_id)


def _seed_run(db: Session, run_id: str) -> None:
    db.add(AgentRun(id=run_id, status="RUNNING", started_at=datetime.now(UTC)))
    db.commit()


def test_persist_durable_trace_stamps_follow_up_fields_when_decision_present(db, monkeypatch):
    _seed_run(db, "run-fu-1")
    decision = FollowUpDecision(
        category=FollowUpCategory.TRUE_FOLLOWUP,
        inherited_topic=False,
        inherited_entity=True,
        reason_code=FollowUpReasonCode.DEICTIC_OR_ATTRIBUTE_ONLY_WITH_PRIOR_CONTEXT,
        evidence_source="deictic_marker",
    )
    run = _persist(db, monkeypatch, _fake_result(agent_run_id="run-fu-1", trace_id="trace-fu-1", follow_up_decision=decision))

    assert run.follow_up_category == "TRUE_FOLLOWUP"
    assert run.follow_up_reason_code == "DEICTIC_OR_ATTRIBUTE_ONLY_WITH_PRIOR_CONTEXT"
    assert run.follow_up_inherited_topic is False
    assert run.follow_up_inherited_entity is True


def test_persist_durable_trace_stamps_topic_switch_decision(db, monkeypatch):
    """A lost-context turn must be as visible as an inherited one.

    TOPIC_SWITCH/STANDALONE_QUESTION are exactly the categories worth counting
    -- they are what a mis-classified follow-up degrades into.
    """
    _seed_run(db, "run-fu-2")
    decision = FollowUpDecision(
        category=FollowUpCategory.TOPIC_SWITCH,
        inherited_topic=False,
        inherited_entity=False,
        reason_code=FollowUpReasonCode.NAMED_SUBJECT_DIFFERS_FROM_PRIOR,
        evidence_source="named_subject",
    )
    run = _persist(db, monkeypatch, _fake_result(agent_run_id="run-fu-2", trace_id="trace-fu-2", follow_up_decision=decision))

    assert run.follow_up_category == "TOPIC_SWITCH"
    assert run.follow_up_reason_code == "NAMED_SUBJECT_DIFFERS_FROM_PRIOR"
    assert run.follow_up_inherited_topic is False
    assert run.follow_up_inherited_entity is False


def test_persist_durable_trace_leaves_follow_up_fields_none_when_no_decision(db, monkeypatch):
    """Schedule/safety/out-of-scope turns never reach the classifier at all.

    `None` is the honest value for those -- never a fabricated
    STANDALONE_QUESTION, which would pollute the very distribution this build
    exists to measure.
    """
    _seed_run(db, "run-fu-3")
    run = _persist(db, monkeypatch, _fake_result(agent_run_id="run-fu-3", trace_id="trace-fu-3", follow_up_decision=None))

    assert run.follow_up_category is None
    assert run.follow_up_reason_code is None
    assert run.follow_up_inherited_topic is None
    assert run.follow_up_inherited_entity is None


def test_every_follow_up_enum_value_survives_the_sanitizer():
    """Guards the exact failure mode this build exists to fix.

    `_SAFE_CODE` silently DROPS a value it does not match -- which is how
    these attributes went missing for entire builds without anyone noticing.
    A future member added to either enum in a shape that regex rejects (a
    lowercase or space-containing value) would vanish from telemetry just as
    quietly, so every member is checked here rather than the two sample
    values the tests above happen to use.
    """
    for category in FollowUpCategory:
        safe = _sanitize_attributes({"follow_up_category": category.value})
        assert safe.get("follow_up_category") == category.value, f"{category} would be dropped from telemetry"
    for reason in FollowUpReasonCode:
        safe = _sanitize_attributes({"follow_up_reason_code": reason.value})
        assert safe.get("follow_up_reason_code") == reason.value, f"{reason} would be dropped from telemetry"


def test_real_orchestrator_decision_reaches_the_durable_column(db, monkeypatch):
    """End-to-end seam: a real run's decision, not a hand-built fixture.

    Every other test here feeds `_persist_durable_trace` a SimpleNamespace,
    which cannot catch a mismatch between what the orchestrator actually
    produces and what the write path expects. This drives a real
    `orchestrator.run()` (spy model gateway -- no network, no API cost) and
    asserts the resulting `OrchestrationResult.follow_up_decision` lands in
    the column intact.
    """
    orchestrator, _gateway = _orchestrator(model_gateway=_SpyModelGateway(ModelPlan(response="grounded")))
    result = orchestrator.run(
        _request("Viêm gan B là gì?", prior_active_entity_id="drug-1", prior_active_entity_name="Amoxicillin"),
        tools=_tools(),
    )
    assert result.follow_up_decision is not None, "this message must reach the follow-up classifier"

    _seed_run(db, result.agent_run_id)
    run = _persist(db, monkeypatch, result)

    assert run.follow_up_category == result.follow_up_decision.category.value
    assert run.follow_up_reason_code == result.follow_up_decision.reason_code.value
    assert run.follow_up_inherited_topic == result.follow_up_decision.inherited_topic
    assert run.follow_up_inherited_entity == result.follow_up_decision.inherited_entity


def test_persist_durable_trace_tolerates_result_without_follow_up_attribute(db, monkeypatch):
    """`_persist_durable_trace` is best-effort and must never raise.

    Not every object reaching this function is a full OrchestrationResult
    (see the minimal fallback rows agent_v2_routes builds on failure paths),
    so a missing attribute must degrade to None rather than AttributeError.
    """
    _seed_run(db, "run-fu-4")
    result = _fake_result(agent_run_id="run-fu-4", trace_id="trace-fu-4")
    del result.follow_up_decision
    run = _persist(db, monkeypatch, result)

    assert run.follow_up_category is None
    assert run.follow_up_inherited_entity is None
