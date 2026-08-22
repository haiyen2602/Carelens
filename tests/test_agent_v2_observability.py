"""BUILD-13 tests for privacy-minimized Agent V2 telemetry."""

from __future__ import annotations

from dataclasses import dataclass

from backend.agents.v2.model_gateway import ModelPlan, ModelRole, ModelUsage, StaticModelGateway, ToolCall
from backend.agents.v2.observability import (
    AgentMetricsCollector,
    AgentTelemetry,
    AlertSeverity,
    InMemoryTelemetrySink,
    ModelPrice,
    ModelPricingCatalog,
    MonitoringThresholds,
    TraceComponent,
    TraceContext,
    evaluate_alerts,
)
from backend.agents.v2.runtime import AgentRunLimits, ReadOnlyAgentRuntime, RunStatus
from backend.agents.v2.tools import ToolResult


def _clock(values: list[float]):
    return lambda: values.pop(0)


def test_trace_propagates_across_runtime_model_and_tool_without_prompt_or_patient_data():
    sink = InMemoryTelemetrySink()
    # BUILD-19B: a tool call now also spans a synthesize_read_only model
    # turn (RUNTIME + plan_read_only MODEL + TOOL + synthesize_read_only
    # MODEL = 4 spans, 2 clock reads each).
    now_values = [0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07]
    telemetry = AgentTelemetry(sink=sink, clock=_clock(now_values))
    trace = TraceContext.create(agent_run_id="agent-run-13")
    runtime = ReadOnlyAgentRuntime(
        StaticModelGateway(
            ModelPlan(
                (ToolCall("search_drug", {"query": "patient secret must not log", "limit": 1}),),
                "do not log this response",
                ModelUsage(input_tokens=11, cached_input_tokens=2, output_tokens=3),
                "req_13",
            )
        ),
        limits=AgentRunLimits(100, 4, 2, 2, 0, 5, 10),
        telemetry=telemetry,
        model_name="gpt-5.4-mini",
        clock=lambda: 1.0,
    )
    result = runtime.run(
        message="Patient Nguyen Van A says this must not be emitted",
        actor_role="patient",
        tools=_ToolGateway(),
        trace=trace,
    )
    assert result.status is RunStatus.COMPLETED
    assert {event.component for event in sink.events} >= {TraceComponent.RUNTIME, TraceComponent.MODEL, TraceComponent.TOOL}
    assert {event.trace.trace_id for event in sink.events} == {trace.trace_id}
    assert {event.trace.agent_run_id for event in sink.events} == {"agent-run-13"}
    rendered = " ".join(str(event.as_log_record()) for event in sink.events)
    assert "Nguyen Van A" not in rendered
    assert "patient secret" not in rendered
    assert "do not log this response" not in rendered


def test_trace_contract_supports_retrieval_web_safety_handoff_and_checkpoint_spans():
    sink = InMemoryTelemetrySink()
    telemetry = AgentTelemetry(sink=sink)
    trace = TraceContext.create(agent_run_id="full-path-run")
    for component, operation in (
        (TraceComponent.ROUTER, "classify"),
        (TraceComponent.RETRIEVAL, "retrieve"),
        (TraceComponent.WEB, "vinmec_search"),
        (TraceComponent.SAFETY, "assess"),
        (TraceComponent.HANDOFF, "create"),
        (TraceComponent.CHECKPOINT, "resume"),
    ):
        with telemetry.span(trace, component, operation=operation):
            telemetry.event(trace, component, "agent_component.completed", component_status="READY")
    assert {event.component for event in sink.events} >= {
        TraceComponent.ROUTER,
        TraceComponent.RETRIEVAL,
        TraceComponent.WEB,
        TraceComponent.SAFETY,
        TraceComponent.HANDOFF,
        TraceComponent.CHECKPOINT,
    }
    assert {event.trace.trace_id for event in sink.events} == {trace.trace_id}


def test_cost_telemetry_tracks_tokens_and_exact_role_breakdown_without_inventing_unknown_prices():
    prices = ModelPricingCatalog(
        {
            "router": ModelPrice(1.0, 0.5, 2.0),
            "main": ModelPrice(2.0, 1.0, 4.0),
            "fallback": ModelPrice(3.0, 1.5, 6.0),
            "embedding": ModelPrice(4.0, 2.0, 0.0),
            "judge": ModelPrice(5.0, 2.5, 10.0),
        }
    )
    telemetry = AgentTelemetry(sink=InMemoryTelemetrySink(), pricing=prices)
    trace = TraceContext.create(agent_run_id="cost-run")
    for role, model in (
        (ModelRole.ROUTER, "router"),
        (ModelRole.MAIN, "main"),
        (ModelRole.FALLBACK, "fallback"),
        (ModelRole.EMBEDDING, "embedding"),
        (ModelRole.JUDGE, "judge"),
    ):
        telemetry.record_model(
            trace,
            role=role,
            model=model,
            usage=ModelUsage(input_tokens=1_000_000, cached_input_tokens=200_000, output_tokens=100_000),
            latency_ms=20,
        )
    telemetry.record_model(
        trace,
        role=ModelRole.MAIN,
        model="unknown-version",
        usage=ModelUsage(input_tokens=1, output_tokens=1),
        latency_ms=1,
    )
    snapshot = telemetry.metrics.snapshot()
    assert snapshot.model_calls == 6
    assert snapshot.input_tokens == 5_000_001
    assert snapshot.cached_input_tokens == 1_000_000
    assert snapshot.output_tokens == 500_001
    assert set(snapshot.cost_by_role_usd) == {role.value for role in ModelRole}
    assert snapshot.unknown_cost_calls == 1
    assert snapshot.estimated_cost_usd > 0


def test_redaction_drops_prompt_phi_secret_and_arbitrary_tool_payload_fields():
    sink = InMemoryTelemetrySink()
    telemetry = AgentTelemetry(sink=sink)
    trace = TraceContext.create(agent_run_id="redaction-run")
    telemetry.event(
        trace,
        TraceComponent.TOOL,
        "agent_tool.completed",
        tool_name="get_today_doses",
        patient_id="patient-should-not-log",
        message="raw prompt should not log",
        prompt="hidden",
        api_key="sk-secret",
        data={"expected_items": ["raw clinical payload"]},
        provenance="operational-db:dose-occurrence:today",
        error_code="TOOL_UNAVAILABLE",
    )
    event = sink.events[-1]
    assert event.attributes == {
        "tool_name": "get_today_doses",
        "provenance": "operational-db:dose-occurrence:today",
        "error_code": "TOOL_UNAVAILABLE",
    }
    assert "raw" not in str(event.as_log_record())
    assert "sk-secret" not in str(event.as_log_record())


def test_percentiles_monitoring_and_critical_safety_alert_use_aggregate_metadata_only():
    metrics = AgentMetricsCollector()
    for latency in (10.0, 20.0, 30.0, 1000.0):
        metrics.record_run(latency_ms=latency, steps=1, tool_calls=1, terminal_status="FAILED")
    metrics.record_span(TraceComponent.RETRIEVAL, 40)
    metrics.record_span(TraceComponent.RETRIEVAL, 200)
    metrics.record_safety("SAFETY_DOMAIN_UNAVAILABLE")
    snapshot = metrics.snapshot()
    assert (snapshot.latency_p50_ms, snapshot.latency_p95_ms, snapshot.latency_p99_ms) == (20.0, 1000.0, 1000.0)
    assert snapshot.retrieval_latency_p95_ms == 200
    alerts = evaluate_alerts(
        snapshot,
        thresholds=MonitoringThresholds(latency_p95_ms=500, agent_failure_rate=0.1),
        tool_error_rate=0.1,
        context_overflow_rate=0.1,
        retrieval_failure_rate=0.2,
    )
    assert {alert.code for alert in alerts} >= {
        "AGENT_P95_LATENCY_REGRESSION",
        "AGENT_TOOL_ERROR_SPIKE",
        "AGENT_CONTEXT_OVERFLOW_SPIKE",
        "AGENT_FAILURE_SPIKE",
        "AGENT_RETRIEVAL_QUALITY_REGRESSION",
        "AGENT_SAFETY_DOMAIN_UNAVAILABLE",
    }
    assert next(alert for alert in alerts if alert.code == "AGENT_SAFETY_DOMAIN_UNAVAILABLE").severity is AlertSeverity.CRITICAL


@dataclass
class _ToolGateway:
    calls: list[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        self.calls = []

    def execute(self, name: str, arguments: dict) -> ToolResult:
        self.calls.append(name)
        return ToolResult(name=name, data={"items": []}, provenance="canonical-drug-v2:catalog")
