"""TASK-V2.5-004 CP1 contract mục 3: ``AgentRun.model``/``MULTI_MODEL``
accounting audit -- explicitly flagged in the merged CP1 contract as NOT YET
DONE, a real CP2 prerequisite before the renderer capability can be
considered canary-ready (a run mixing planner=MAIN + renderer=RENDERER now
uses two different models/prices in one run).

Root cause (before this fix): ``_persist_durable_trace`` derived
``run.model``/``run.total_cost_usd`` from the RUN'S AGGREGATE token counts
(``RunMetrics.input_tokens``/``output_tokens``, summed across every model
call regardless of role) priced as a single ``ModelRole.MAIN`` call against
``settings.agent_main_model`` -- correct only because every model call in a
run happened to share one model before this task. ``AgentTelemetry.
record_model`` already computes an accurate PER-CALL ``CostEstimate``
(model, role, real usage) for every real model call and buffers it as an
``agent_model.completed`` event -- this fix makes ``_persist_durable_trace``
read cost from those real per-call events instead of re-deriving it from a
single assumed model.

These tests drive ``_persist_durable_trace`` with REAL buffered telemetry
events (``telemetry.record_model(...)``), not just metrics/settings, so they
catch exactly the class of bug the old code had.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.agents.v2.model_gateway import ModelRole, ModelUsage
from backend.agents.v2.observability import (
    AgentTelemetry,
    BufferingSink,
    ModelPrice,
    ModelPricingCatalog,
    StructuredLogSink,
    TraceContext,
    _sanitize_attributes,
)
from backend.agents.v2.runtime import RunMetrics, RunStatus
from backend.api.security import CurrentUser
from backend.db.models import AgentRun, AgentRunEvaluation, AgentRunSpan

# ---------------------------------------------------------------------------
# _sanitize_attributes / record_model: input_cost_usd / output_cost_usd must
# survive to the buffered event -- the per-call breakdown this fix depends on.
# ---------------------------------------------------------------------------


def test_sanitize_attributes_allows_input_and_output_cost_usd():
    safe = _sanitize_attributes({"input_cost_usd": 0.001, "output_cost_usd": 0.002})
    assert safe["input_cost_usd"] == 0.001
    assert safe["output_cost_usd"] == 0.002


def test_sanitize_attributes_clamps_negative_cost_breakdown_like_estimated_cost():
    safe = _sanitize_attributes({"input_cost_usd": -1.0, "output_cost_usd": -2.0})
    assert safe["input_cost_usd"] == 0.0
    assert safe["output_cost_usd"] == 0.0


def test_record_model_emits_input_and_output_cost_breakdown_on_the_event():
    sink = BufferingSink(StructuredLogSink())
    pricing = ModelPricingCatalog({"main": ModelPrice(2.0, 1.0, 4.0)}, version="v1")
    telemetry = AgentTelemetry(sink=sink, pricing=pricing)
    trace = TraceContext.create(agent_run_id="cost-breakdown-run")

    telemetry.record_model(
        trace, role=ModelRole.MAIN, model="main", usage=ModelUsage(input_tokens=1_000_000, output_tokens=1_000_000), latency_ms=10
    )

    events = sink.pop(trace.trace_id)
    completed = [e for e in events if e.name == "agent_model.completed"]
    assert len(completed) == 1
    assert completed[0].attributes["input_cost_usd"] == pytest.approx(2.0)
    assert completed[0].attributes["output_cost_usd"] == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# _persist_durable_trace -- real multi-model run accounting.
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


def _seed_run(db: Session, run_id: str) -> None:
    db.add(AgentRun(id=run_id, status="RUNNING", started_at=datetime.now(UTC)))
    db.commit()


def _fake_result(*, agent_run_id: str, trace_id: str, model_calls: int, input_tokens: int, output_tokens: int):
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
            steps=model_calls,
            model_calls=model_calls,
            tool_calls=0,
            retries=0,
            input_tokens=input_tokens,
            cached_input_tokens=0,
            output_tokens=output_tokens,
            elapsed_ms=123.0,
        ),
    )


def test_two_model_run_is_stamped_multi_model_not_the_single_settings_model(db, monkeypatch):
    """The real bug: a run with MAIN (planner) + RENDERER (Luna) calls must
    never be labeled with just settings.agent_main_model -- that silently
    reports the wrong model for half the run's real cost."""
    import backend.api.agent_v2_routes as routes

    sink = BufferingSink(StructuredLogSink())
    monkeypatch.setattr(routes, "_telemetry_sink", sink)
    pricing = ModelPricingCatalog(
        {"gpt-5.4-mini": ModelPrice(0.75, 0.075, 4.50), "gpt-5.6-luna": ModelPrice(0.20, 0.02, 1.20)}, version="v1"
    )
    telemetry = AgentTelemetry(sink=sink, pricing=pricing)

    run_id, trace_id = "run-multi-1", "trace-multi-1"
    _seed_run(db, run_id)
    trace = TraceContext(trace_id=trace_id, agent_run_id=run_id)
    telemetry.record_model(
        trace, role=ModelRole.MAIN, model="gpt-5.4-mini", usage=ModelUsage(input_tokens=100, output_tokens=50), latency_ms=10
    )
    telemetry.record_model(
        trace, role=ModelRole.RENDERER, model="gpt-5.6-luna", usage=ModelUsage(input_tokens=160, output_tokens=86), latency_ms=20
    )

    result = _fake_result(agent_run_id=run_id, trace_id=trace_id, model_calls=2, input_tokens=260, output_tokens=136)
    settings = SimpleNamespace(agent_main_model="gpt-5.4-mini")
    routes._persist_durable_trace(db, result=result, telemetry=telemetry, settings=settings, actor=_actor())

    run = db.get(AgentRun, run_id)
    assert run.model == "MULTI_MODEL"
    assert run.cost_status == "AVAILABLE"
    expected_total = ((100 * 0.75 + 50 * 4.50) + (160 * 0.20 + 86 * 1.20)) / 1_000_000
    assert run.total_cost_usd == pytest.approx(expected_total)


def test_single_model_run_still_reports_the_real_model_from_its_own_calls(db, monkeypatch):
    """Non-regression: a run whose calls all share one model is still
    labeled with that real model -- derived from its own telemetry now,
    not merely copied from settings.agent_main_model (same value here, but
    for the right reason: this is what the real calls actually used)."""
    import backend.api.agent_v2_routes as routes

    sink = BufferingSink(StructuredLogSink())
    monkeypatch.setattr(routes, "_telemetry_sink", sink)
    pricing = ModelPricingCatalog({"gpt-5.4-mini": ModelPrice(0.75, 0.075, 4.50)}, version="v1")
    telemetry = AgentTelemetry(sink=sink, pricing=pricing)

    run_id, trace_id = "run-single-1", "trace-single-1"
    _seed_run(db, run_id)
    trace = TraceContext(trace_id=trace_id, agent_run_id=run_id)
    telemetry.record_model(
        trace, role=ModelRole.MAIN, model="gpt-5.4-mini", usage=ModelUsage(input_tokens=100, output_tokens=50), latency_ms=10
    )
    telemetry.record_model(
        trace, role=ModelRole.MAIN, model="gpt-5.4-mini", usage=ModelUsage(input_tokens=10, output_tokens=5), latency_ms=5
    )

    result = _fake_result(agent_run_id=run_id, trace_id=trace_id, model_calls=2, input_tokens=110, output_tokens=55)
    settings = SimpleNamespace(agent_main_model="gpt-5.4-mini")
    routes._persist_durable_trace(db, result=result, telemetry=telemetry, settings=settings, actor=_actor())

    run = db.get(AgentRun, run_id)
    assert run.model == "gpt-5.4-mini"
    assert run.cost_status == "AVAILABLE"
    expected_total = ((100 * 0.75 + 50 * 4.50) + (10 * 0.75 + 5 * 4.50)) / 1_000_000
    assert run.total_cost_usd == pytest.approx(expected_total)


def test_model_calls_claimed_but_no_events_buffered_degrades_honestly_to_not_available(db, monkeypatch):
    """A lost/evicted telemetry buffer must never fabricate a model/cost --
    NOT_AVAILABLE (honest) beats silently guessing settings.agent_main_model
    for calls we have no real record of."""
    import backend.api.agent_v2_routes as routes

    sink = BufferingSink(StructuredLogSink())
    monkeypatch.setattr(routes, "_telemetry_sink", sink)
    telemetry = AgentTelemetry(sink=sink, pricing=ModelPricingCatalog({}, version="v1"))

    run_id, trace_id = "run-lost-1", "trace-lost-1"
    _seed_run(db, run_id)
    # Deliberately no telemetry.record_model call -- buffer has zero
    # agent_model.completed events for this trace_id.
    result = _fake_result(agent_run_id=run_id, trace_id=trace_id, model_calls=1, input_tokens=100, output_tokens=50)
    settings = SimpleNamespace(agent_main_model="gpt-5.4-mini")
    routes._persist_durable_trace(db, result=result, telemetry=telemetry, settings=settings, actor=_actor())

    run = db.get(AgentRun, run_id)
    assert run.model is None
    assert run.cost_status == "NOT_AVAILABLE"
    assert run.total_cost_usd is None


def test_zero_model_calls_still_reports_real_zero_cost_unchanged(db, monkeypatch):
    """Non-regression: the existing "schedule/clarification reply, zero
    model calls -> real definite zero, not NOT_AVAILABLE" behavior must
    survive this fix untouched."""
    import backend.api.agent_v2_routes as routes

    sink = BufferingSink(StructuredLogSink())
    monkeypatch.setattr(routes, "_telemetry_sink", sink)
    telemetry = AgentTelemetry(sink=sink, pricing=ModelPricingCatalog({}, version="v1"))

    run_id, trace_id = "run-zero-1", "trace-zero-1"
    _seed_run(db, run_id)
    result = _fake_result(agent_run_id=run_id, trace_id=trace_id, model_calls=0, input_tokens=0, output_tokens=0)
    settings = SimpleNamespace(agent_main_model="gpt-5.4-mini")
    routes._persist_durable_trace(db, result=result, telemetry=telemetry, settings=settings, actor=_actor())

    run = db.get(AgentRun, run_id)
    assert run.cost_status == "AVAILABLE"
    assert run.total_cost_usd == 0.0


def test_unknown_model_price_degrades_to_not_available_not_partial_multi_model(db, monkeypatch):
    """One of two real calls uses a model absent from the pricing catalog --
    honest NOT_AVAILABLE for the whole run, never a partial/silently-wrong
    total that only counts the known-priced call."""
    import backend.api.agent_v2_routes as routes

    sink = BufferingSink(StructuredLogSink())
    monkeypatch.setattr(routes, "_telemetry_sink", sink)
    pricing = ModelPricingCatalog({"gpt-5.4-mini": ModelPrice(0.75, 0.075, 4.50)}, version="v1")
    telemetry = AgentTelemetry(sink=sink, pricing=pricing)

    run_id, trace_id = "run-unknown-1", "trace-unknown-1"
    _seed_run(db, run_id)
    trace = TraceContext(trace_id=trace_id, agent_run_id=run_id)
    telemetry.record_model(
        trace, role=ModelRole.MAIN, model="gpt-5.4-mini", usage=ModelUsage(input_tokens=100, output_tokens=50), latency_ms=10
    )
    telemetry.record_model(
        trace, role=ModelRole.RENDERER, model="gpt-5.6-luna", usage=ModelUsage(input_tokens=160, output_tokens=86), latency_ms=20
    )

    result = _fake_result(agent_run_id=run_id, trace_id=trace_id, model_calls=2, input_tokens=260, output_tokens=136)
    settings = SimpleNamespace(agent_main_model="gpt-5.4-mini")
    routes._persist_durable_trace(db, result=result, telemetry=telemetry, settings=settings, actor=_actor())

    run = db.get(AgentRun, run_id)
    assert run.cost_status == "NOT_AVAILABLE"
    assert run.total_cost_usd is None
    assert run.model == "MULTI_MODEL"
