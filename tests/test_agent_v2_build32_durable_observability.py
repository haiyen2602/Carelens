"""BUILD-32: unit tests for the new durable observability plumbing --
BufferingSink (real-timed span buffering/eviction), runtime.py's error_code
taxonomy classification, and agent_v2_routes._persist_durable_trace (the
best-effort post-response function that makes token/cost/duration/spans/
evaluation durable).
"""

from __future__ import annotations

from types import SimpleNamespace

import openai
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.agents.v2.model_gateway import (
    EmptySynthesisError,
    ModelUsage,
    ToolCall,
)
from backend.agents.v2.observability import (
    AgentTelemetry,
    BufferingSink,
    InMemoryTelemetrySink,
    ModelPricingCatalog,
    StructuredLogSink,
    TraceComponent,
    TraceContext,
)
from backend.agents.v2.runtime import (
    ERROR_CODE_BUDGET_EXCEEDED,
    ERROR_CODE_EMPTY_REPLY,
    ERROR_CODE_MODEL_ERROR,
    ERROR_CODE_MODEL_TIMEOUT,
    ERROR_CODE_REQUEST_TIMEOUT,
    ERROR_CODE_TOOL_ERROR,
    AgentRunLimits,
    ReadOnlyAgentRuntime,
    RunStatus,
)
from backend.agents.v2.tools import ToolExecutionError, ToolGateway
from backend.api.security import CurrentUser
from backend.db.models import AgentRun, AgentRunEvaluation, AgentRunSpan

# ---------------------------------------------------------------------------
# BufferingSink
# ---------------------------------------------------------------------------


def _event(trace_id: str, name: str = "agent_span.finished") -> object:
    from datetime import UTC, datetime

    return SimpleNamespace(
        name=name,
        trace=TraceContext(trace_id=trace_id, agent_run_id=f"run-{trace_id}"),
        component=TraceComponent.MODEL,
        occurred_at=datetime.now(UTC),
        attributes={"latency_ms": 5.0, "outcome": "OK"},
    )


def test_buffering_sink_still_delegates_to_inner_sink():
    inner = InMemoryTelemetrySink()
    sink = BufferingSink(inner)
    event = _event("t-1")
    sink.emit(event)
    assert inner.events == [event]


def test_buffering_sink_pop_returns_and_clears_only_that_trace():
    sink = BufferingSink(InMemoryTelemetrySink())
    e1, e2, e3 = _event("t-1"), _event("t-1"), _event("t-2")
    for e in (e1, e2, e3):
        sink.emit(e)
    assert sink.pop("t-1") == [e1, e2]
    assert sink.pop("t-1") == []  # already popped
    assert sink.pop("t-2") == [e3]


def test_buffering_sink_evicts_oldest_unflushed_trace_when_full():
    sink = BufferingSink(InMemoryTelemetrySink(), max_traces=2)
    sink.emit(_event("t-1"))
    sink.emit(_event("t-2"))
    sink.emit(_event("t-3"))  # evicts t-1 (FIFO)
    assert sink.pop("t-1") == []
    assert len(sink.pop("t-2")) == 1
    assert len(sink.pop("t-3")) == 1


# ---------------------------------------------------------------------------
# runtime.py error_code classification
# ---------------------------------------------------------------------------


class _RaisingGateway:
    """Model gateway whose plan_read_only always raises a configured exception."""

    def __init__(self, exc: Exception):
        self._exc = exc

    def plan_read_only(self, *, message, actor_role):
        raise self._exc

    def synthesize_read_only(self, *, message, actor_role, evidence):
        raise self._exc


def _runtime(gateway, *, model_timeout_seconds=100.0, run_timeout_seconds=100.0, max_retries=0) -> ReadOnlyAgentRuntime:
    return ReadOnlyAgentRuntime(
        gateway,
        limits=AgentRunLimits(1000, 4, 2, 2, max_retries, model_timeout_seconds, run_timeout_seconds),
        model_name="gpt-5.4-mini",
        clock=lambda: 1.0,  # frozen -- never trips the elapsed-time fallback
    )


def test_openai_timeout_exception_is_classified_as_model_timeout_on_exhaustion():
    runtime = _runtime(_RaisingGateway(openai.APITimeoutError(request=SimpleNamespace())), max_retries=0)
    result = runtime.run(message="hi", actor_role="patient", tools=ToolGateway(SimpleNamespace(), context=SimpleNamespace()))
    assert result.status is RunStatus.FAILED
    assert result.error_code == ERROR_CODE_MODEL_TIMEOUT


def test_generic_exception_is_classified_as_model_error_on_exhaustion():
    runtime = _runtime(_RaisingGateway(RuntimeError("boom")), max_retries=0)
    result = runtime.run(message="hi", actor_role="patient", tools=ToolGateway(SimpleNamespace(), context=SimpleNamespace()))
    assert result.status is RunStatus.FAILED
    assert result.error_code == ERROR_CODE_MODEL_ERROR


def test_empty_synthesis_error_is_classified_as_empty_reply_on_exhaustion():
    class _Plan:
        tool_calls = (ToolCall("noop_tool", {}),)
        response = ""
        usage = ModelUsage(1, 0, 1)
        request_id = "req-1"

    class _PlanThenEmptyGateway:
        def plan_read_only(self, *, message, actor_role):
            return _Plan()

        def synthesize_read_only(self, *, message, actor_role, evidence):
            raise EmptySynthesisError("MODEL_SYNTHESIS_EMPTY")

    class _NoopTools:
        def execute(self, name, arguments):
            from backend.agents.v2.tools import ToolResult

            return ToolResult(name=name, data={}, provenance="test")

    runtime = _runtime(_PlanThenEmptyGateway(), max_retries=0)
    tools = ToolGateway.__new__(ToolGateway)  # bypass real ToolGateway construction
    tools.execute = _NoopTools().execute  # type: ignore[method-assign]
    result = runtime.run(message="hi", actor_role="patient", tools=tools)
    assert result.status is RunStatus.FAILED
    assert result.error_code == ERROR_CODE_EMPTY_REPLY


def test_run_timeout_is_classified_as_request_timeout():
    # A clock that advances by 1s on every read: `started` is read once,
    # the very next `_timed_out(started)` check already sees >0s elapsed --
    # always over the run_timeout_seconds=0.0 budget below.
    ticking = iter(float(n) for n in range(1000))
    runtime = ReadOnlyAgentRuntime(
        _RaisingGateway(RuntimeError("slow")),
        limits=AgentRunLimits(1000, 4, 2, 2, 0, 100.0, 0.0),  # run_timeout_seconds=0 -> always timed out
        model_name="gpt-5.4-mini",
        clock=lambda: next(ticking),
    )
    result = runtime.run(message="hi", actor_role="patient", tools=ToolGateway(SimpleNamespace(), context=SimpleNamespace()))
    assert result.status is RunStatus.TIMEOUT
    assert result.error_code == ERROR_CODE_REQUEST_TIMEOUT


def test_token_budget_exceeded_is_classified_as_budget_exceeded():
    class _BigUsagePlan:
        tool_calls = ()
        response = "ok"
        usage = ModelUsage(input_tokens=999, cached_input_tokens=0, output_tokens=999)
        request_id = "req-2"

    class _BigUsageGateway:
        def plan_read_only(self, *, message, actor_role):
            return _BigUsagePlan()

    runtime = ReadOnlyAgentRuntime(
        _BigUsageGateway(),
        limits=AgentRunLimits(token_budget=10, max_steps=4, max_model_calls=2, max_tool_calls=2, max_retries=0, model_timeout_seconds=100.0, run_timeout_seconds=100.0),
        model_name="gpt-5.4-mini",
        clock=lambda: 1.0,
    )
    result = runtime.run(message="hi", actor_role="patient", tools=ToolGateway(SimpleNamespace(), context=SimpleNamespace()))
    assert result.status is RunStatus.BUDGET_EXCEEDED
    assert result.error_code == ERROR_CODE_BUDGET_EXCEEDED


def test_tool_execution_error_is_classified_as_tool_error():
    class _ToolCallPlan:
        tool_calls = (ToolCall("bad_tool", {}),)
        response = ""
        usage = ModelUsage(1, 0, 1)
        request_id = "req-3"

    class _ToolCallGateway:
        def plan_read_only(self, *, message, actor_role):
            return _ToolCallPlan()

    class _FailingTools:
        def execute(self, name, arguments):
            raise ToolExecutionError("TOOL_UNAVAILABLE")

    runtime = ReadOnlyAgentRuntime(
        _ToolCallGateway(),
        limits=AgentRunLimits(1000, 4, 2, 2, 0, 100.0, 100.0),
        model_name="gpt-5.4-mini",
        clock=lambda: 1.0,
    )
    tools = ToolGateway.__new__(ToolGateway)
    tools.execute = _FailingTools().execute  # type: ignore[method-assign]
    result = runtime.run(message="hi", actor_role="patient", tools=tools)
    assert result.status is RunStatus.FAILED
    assert result.error_code == ERROR_CODE_TOOL_ERROR


# ---------------------------------------------------------------------------
# _persist_durable_trace
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


def _fake_result(*, agent_run_id: str, trace_id: str, status=RunStatus.COMPLETED, error_code=None, response="ok"):
    from backend.agents.v2.runtime import RunMetrics

    return SimpleNamespace(
        agent_run_id=agent_run_id,
        trace_id=trace_id,
        status=status,
        response=response,
        error_code=error_code,
        intent=SimpleNamespace(value="GENERAL_MEDICAL_INFORMATION"),
        tool_results=(),
        citations=(),
        safety_decision=None,
        handoff_result=None,
        metrics=RunMetrics(steps=1, model_calls=1, tool_calls=0, retries=0, input_tokens=100, cached_input_tokens=0, output_tokens=50, elapsed_ms=123.0),
    )


def _actor() -> CurrentUser:
    return CurrentUser(id="actor-1", role="patient", patient_id="patient-1", doctor_id=None)


def test_persist_durable_trace_stamps_agent_run_and_writes_spans_and_evaluation(db, monkeypatch):
    import backend.api.agent_v2_routes as routes

    sink = BufferingSink(StructuredLogSink())
    monkeypatch.setattr(routes, "_telemetry_sink", sink)
    telemetry = AgentTelemetry(sink=sink, pricing=ModelPricingCatalog({}, version="v1"))

    run_id, trace_id = "run-durable-1", "trace-durable-1"
    db.add(AgentRun(id=run_id, status="RUNNING", started_at=__import__("datetime").datetime.now(__import__("datetime").UTC)))
    db.commit()

    # Buffer one real span for this trace before persisting, the same way a
    # real request would (span() emits started+finished into the shared sink).
    trace = TraceContext(trace_id=trace_id, agent_run_id=run_id)
    with telemetry.span(trace, TraceComponent.TOOL, operation="execute", attributes={"tool_name": "search_drug"}):
        pass

    result = _fake_result(agent_run_id=run_id, trace_id=trace_id)
    settings = SimpleNamespace(agent_main_model="gpt-5.4-mini")
    routes._persist_durable_trace(db, result=result, telemetry=telemetry, settings=settings, actor=_actor())

    run = db.get(AgentRun, run_id)
    assert run.trace_id == trace_id
    assert run.actor_id == "actor-1"
    assert run.input_tokens == 100
    assert run.output_tokens == 50
    assert run.total_tokens == 150
    assert run.model_calls == 1
    assert run.model == "gpt-5.4-mini"
    assert run.duration_ms == 123.0
    assert run.cost_status == "NOT_AVAILABLE"  # empty pricing catalog -- honest, not fabricated
    assert run.timeout is False
    assert run.error_code is None
    assert run.empty_reply is False

    spans = db.execute(select(AgentRunSpan).where(AgentRunSpan.agent_run_id == run_id)).scalars().all()
    span_types = {s.span_type for s in spans}
    assert "TOOL" in span_types  # the buffered span
    assert "EVALUATION" in span_types  # dispatch_evaluation's own real span

    evaluation = db.execute(select(AgentRunEvaluation).where(AgentRunEvaluation.agent_run_id == run_id)).scalar_one_or_none()
    assert evaluation is not None
    assert evaluation.evaluation_version == "evaluation-v2"


def test_persist_durable_trace_marks_zero_model_calls_as_real_zero_cost_not_na(db, monkeypatch):
    import backend.api.agent_v2_routes as routes
    from backend.agents.v2.runtime import RunMetrics

    sink = BufferingSink(StructuredLogSink())
    monkeypatch.setattr(routes, "_telemetry_sink", sink)
    telemetry = AgentTelemetry(sink=sink, pricing=ModelPricingCatalog({}, version="v1"))

    run_id, trace_id = "run-durable-2", "trace-durable-2"
    db.add(AgentRun(id=run_id, status="RUNNING", started_at=__import__("datetime").datetime.now(__import__("datetime").UTC)))
    db.commit()

    result = _fake_result(agent_run_id=run_id, trace_id=trace_id)
    result.metrics = RunMetrics(steps=1, model_calls=0, tool_calls=1, retries=0, input_tokens=0, cached_input_tokens=0, output_tokens=0, elapsed_ms=5.0)
    settings = SimpleNamespace(agent_main_model="gpt-5.4-mini")
    routes._persist_durable_trace(db, result=result, telemetry=telemetry, settings=settings, actor=_actor())

    run = db.get(AgentRun, run_id)
    assert run.cost_status == "AVAILABLE"
    assert run.total_cost_usd == 0.0


def test_persist_durable_trace_marks_empty_reply(db, monkeypatch):
    import backend.api.agent_v2_routes as routes

    sink = BufferingSink(StructuredLogSink())
    monkeypatch.setattr(routes, "_telemetry_sink", sink)
    telemetry = AgentTelemetry(sink=sink, pricing=ModelPricingCatalog({}, version="v1"))

    run_id, trace_id = "run-durable-3", "trace-durable-3"
    db.add(AgentRun(id=run_id, status="RUNNING", started_at=__import__("datetime").datetime.now(__import__("datetime").UTC)))
    db.commit()

    result = _fake_result(agent_run_id=run_id, trace_id=trace_id, status=RunStatus.FAILED, error_code=ERROR_CODE_EMPTY_REPLY, response="   ")
    settings = SimpleNamespace(agent_main_model="gpt-5.4-mini")
    routes._persist_durable_trace(db, result=result, telemetry=telemetry, settings=settings, actor=_actor())

    run = db.get(AgentRun, run_id)
    assert run.empty_reply is True
    assert run.error_code == ERROR_CODE_EMPTY_REPLY


def test_persist_durable_trace_is_exception_safe_and_never_raises(db, monkeypatch):
    """A DB failure inside this best-effort function must never break the
    real chat response already returned to the caller."""
    import backend.api.agent_v2_routes as routes

    sink = BufferingSink(StructuredLogSink())
    monkeypatch.setattr(routes, "_telemetry_sink", sink)
    telemetry = AgentTelemetry(sink=sink, pricing=ModelPricingCatalog({}, version="v1"))

    def _boom():
        raise RuntimeError("simulated DB failure")

    monkeypatch.setattr(db, "commit", _boom)

    result = _fake_result(agent_run_id="run-does-not-exist", trace_id="trace-x")
    settings = SimpleNamespace(agent_main_model="gpt-5.4-mini")
    # Must not raise.
    routes._persist_durable_trace(db, result=result, telemetry=telemetry, settings=settings, actor=_actor())


# ---------------------------------------------------------------------------
# rag_monitoring_routes._agent_run_query -- BUILD-32 bugfix: this is the
# single choke point /health, /generation, /system, and /traces all read
# through. Before this fix it had no error handling at all, so a durable-read
# failure (e.g. migration 0042 not yet applied on this environment) took the
# whole Admin dashboard down at once -- the real root cause traced back for
# the reported "Admin page N/A" incident.
# ---------------------------------------------------------------------------


def test_agent_run_query_degrades_to_empty_list_on_db_failure(db, monkeypatch):
    from backend.api import rag_monitoring_routes

    def _boom(*_args, **_kwargs):
        raise Exception("simulated missing column (migration not applied)")  # noqa: BLE001

    monkeypatch.setattr(db, "execute", _boom)
    result = rag_monitoring_routes._agent_run_query(db, chatbot_version=None, model=None, prompt_version=None)
    assert result == []
