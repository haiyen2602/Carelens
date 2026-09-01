"""Vendor-neutral, privacy-minimized observability primitives for Agent V2.

The telemetry boundary records operational metadata only. It never receives or
persists raw prompts, model responses/reasoning, tool payloads, secret values,
or patient/user identifying fields. Production exporters can implement the
``TelemetrySink`` protocol without changing Agent domain logic.
"""

from __future__ import annotations

import json
import logging
import math
import re
import time
import uuid
from collections import Counter, OrderedDict, defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from threading import Lock
from typing import Any, Protocol

from backend.agents.v2.model_gateway import ModelRole, ModelUsage

LOGGER = logging.getLogger("backend.agents.v2.telemetry")


class TraceComponent(StrEnum):
    ROUTER = "ROUTER"
    MODEL = "MODEL"
    TOOL = "TOOL"
    RETRIEVAL = "RETRIEVAL"
    WEB = "WEB"
    SAFETY = "SAFETY"
    HANDOFF = "HANDOFF"
    CHECKPOINT = "CHECKPOINT"
    GUARDRAIL = "GUARDRAIL"
    RUNTIME = "RUNTIME"
    # BUILD-32: added so the durable span contract (BUILD-32-TO-36-MASTER-
    # PLAN.md §4) can name every real span type it lists. CONVERSATION_CONTEXT
    # is deliberately not added here -- see the BUILD-32 report's "Honest
    # scope limits" section for why it is out of scope this build.
    TIME_QUERY = "TIME_QUERY"
    GROUNDING = "GROUNDING"
    ANSWER_COMPOSITION = "ANSWER_COMPOSITION"
    EVALUATION = "EVALUATION"


@dataclass(frozen=True)
class TraceContext:
    trace_id: str
    agent_run_id: str

    @classmethod
    def create(cls, *, agent_run_id: str | None = None) -> TraceContext:
        return cls(trace_id=str(uuid.uuid4()), agent_run_id=agent_run_id or str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if not _SAFE_IDENTIFIER.fullmatch(self.trace_id) or not _SAFE_IDENTIFIER.fullmatch(self.agent_run_id):
            raise ValueError("trace_id and agent_run_id must be safe identifiers")


@dataclass(frozen=True)
class ModelPrice:
    input_per_million: float
    cached_input_per_million: float
    output_per_million: float

    def __post_init__(self) -> None:
        values = (self.input_per_million, self.cached_input_per_million, self.output_per_million)
        if not all(math.isfinite(value) and value >= 0 for value in values):
            raise ValueError("model prices must be finite and non-negative")


@dataclass(frozen=True)
class CostEstimate:
    model: str
    model_role: ModelRole
    usage: ModelUsage
    estimated_cost_usd: float | None
    # BUILD-32: which pricing catalog produced this estimate -- lets a
    # durably-persisted cost figure always be traced back to the price list
    # that computed it (see backend.config.Settings.agent_model_pricing_version).
    # "unversioned" (the settings default) when the operator never assigned one.
    pricing_version: str = "unversioned"
    # BUILD-32: input/output cost breakdown (durable trace contract §6 wants
    # both, not just the total). `None` exactly when `estimated_cost_usd` is
    # `None` (unknown model, no invented cost).
    input_cost_usd: float | None = None
    output_cost_usd: float | None = None


class ModelPricingCatalog:
    """Exact-model price configuration; unknown models never get invented cost."""

    def __init__(self, prices: dict[str, ModelPrice] | None = None, *, version: str = "unversioned") -> None:
        self._prices = prices or {}
        self.version = version

    @classmethod
    def from_settings(cls, settings: object) -> ModelPricingCatalog:
        raw = str(getattr(settings, "agent_model_pricing_json", "{}") or "{}")
        try:
            configured = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError("AGENT_MODEL_PRICING_JSON must be valid JSON") from error
        if not isinstance(configured, dict):
            raise ValueError("AGENT_MODEL_PRICING_JSON must be an object")
        prices: dict[str, ModelPrice] = {}
        for model, value in configured.items():
            if not isinstance(model, str) or not _SAFE_MODEL.fullmatch(model) or not isinstance(value, dict):
                raise ValueError("invalid model pricing catalog entry")
            try:
                prices[model] = ModelPrice(
                    float(value["input_per_million"]),
                    float(value.get("cached_input_per_million", value["input_per_million"])),
                    float(value["output_per_million"]),
                )
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("invalid model pricing values") from error
        version = str(getattr(settings, "agent_model_pricing_version", "unversioned") or "unversioned")
        return cls(prices, version=version)

    def estimate(self, *, model: str, model_role: ModelRole, usage: ModelUsage) -> CostEstimate:
        price = self._prices.get(model)
        if price is None:
            return CostEstimate(model, model_role, usage, None, self.version)
        input_tokens = int(usage.input_tokens or 0)
        cached_tokens = int(usage.cached_input_tokens or 0)
        if cached_tokens > input_tokens:
            cached_tokens = input_tokens
        uncached_tokens = input_tokens - cached_tokens
        output_tokens = int(usage.output_tokens or 0)
        input_cost = (uncached_tokens * price.input_per_million + cached_tokens * price.cached_input_per_million) / 1_000_000
        output_cost = (output_tokens * price.output_per_million) / 1_000_000
        return CostEstimate(model, model_role, usage, input_cost + output_cost, self.version, input_cost, output_cost)


@dataclass(frozen=True)
class TelemetryEvent:
    name: str
    trace: TraceContext
    component: TraceComponent
    occurred_at: datetime
    attributes: dict[str, str | int | float | bool | None]

    def as_log_record(self) -> dict[str, object]:
        return {
            "event": self.name,
            "timestamp": self.occurred_at.isoformat(),
            "trace_id": self.trace.trace_id,
            "agent_run_id": self.trace.agent_run_id,
            "component": self.component.value,
            **self.attributes,
        }


class TelemetrySink(Protocol):
    def emit(self, event: TelemetryEvent) -> None: ...


class StructuredLogSink:
    """JSON logger with a single sanitized payload field."""

    def emit(self, event: TelemetryEvent) -> None:
        LOGGER.info(json.dumps(event.as_log_record(), separators=(",", ":"), sort_keys=True))


@dataclass
class InMemoryTelemetrySink:
    """Test sink; production code should use a structured exporter."""

    events: list[TelemetryEvent] = field(default_factory=list)

    def emit(self, event: TelemetryEvent) -> None:
        self.events.append(event)


# BUILD-32: BUFFERING_SINK_MAX_TRACES bounds how many in-flight traces'
# events this process will hold in memory at once. `AgentTelemetry.span()`/
# `record_model()` already measure real wall-clock timing live, during the
# actual runtime/orchestrator call (see their docstrings/callers) -- the gap
# this build closes is that the only sink wired in production
# (`StructuredLogSink`) threw that real data away into an unqueryable log
# line. `BufferingSink` keeps every existing sink's behavior (it always
# delegates to an inner sink first) and additionally buffers each trace's
# events in memory, keyed by trace_id, so a post-response step
# (`backend.api.agent_v2_routes._persist_durable_trace`) can pop them and
# write real `AgentRunSpan` rows -- the DB write happens a few milliseconds
# after the run finishes, but the durations inside it were captured live, not
# reconstructed. Bounded/FIFO-evicting for the same reason
# `backend.services.telemetry`'s ring buffer is capped at 200: a run whose
# post-response persistence step never fires (process crash, an orchestrator-
# level exception before a trace_id is ever popped) must not leak memory
# forever.
_BUFFERING_SINK_MAX_TRACES = 500


class BufferingSink:
    """Tee sink: forwards every event to `inner`, and separately buffers it
    per trace_id for later durable persistence. Thread-safe (multiple
    concurrent requests share one `AgentTelemetry` instance/sink)."""

    def __init__(self, inner: TelemetrySink, *, max_traces: int = _BUFFERING_SINK_MAX_TRACES) -> None:
        self._inner = inner
        self._max_traces = max_traces
        self._lock = Lock()
        self._buffers: OrderedDict[str, list[TelemetryEvent]] = OrderedDict()

    def emit(self, event: TelemetryEvent) -> None:
        self._inner.emit(event)
        trace_id = event.trace.trace_id
        with self._lock:
            bucket = self._buffers.get(trace_id)
            if bucket is None:
                if len(self._buffers) >= self._max_traces:
                    evicted_id, _ = self._buffers.popitem(last=False)
                    LOGGER.warning("BufferingSink evicted unflushed trace %s (buffer full)", evicted_id)
                bucket = []
                self._buffers[trace_id] = bucket
            bucket.append(event)

    def pop(self, trace_id: str) -> list[TelemetryEvent]:
        """Return and remove every buffered event for `trace_id` (empty list
        if none/already popped/evicted)."""
        with self._lock:
            return self._buffers.pop(trace_id, [])


@dataclass(frozen=True)
class AgentMetricsSnapshot:
    count: int
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    latency_p99_ms: float | None
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    model_calls: int
    tool_calls: int
    agent_steps: int
    estimated_cost_usd: float
    unknown_cost_calls: int
    terminal_statuses: dict[str, int]
    safety_outcomes: dict[str, int]
    handoff_outcomes: dict[str, int]
    retrieval_latency_p95_ms: float | None
    cost_by_role_usd: dict[str, float]


class AgentMetricsCollector:
    """In-process aggregator with export-ready snapshot fields and no content."""

    def __init__(self) -> None:
        self._latencies: list[float] = []
        self._retrieval_latencies: list[float] = []
        self._input_tokens = 0
        self._cached_input_tokens = 0
        self._output_tokens = 0
        self._model_calls = 0
        self._tool_calls = 0
        self._agent_steps = 0
        self._estimated_cost = 0.0
        self._unknown_cost_calls = 0
        self._terminal_statuses: Counter[str] = Counter()
        self._safety_outcomes: Counter[str] = Counter()
        self._handoff_outcomes: Counter[str] = Counter()
        self._cost_by_role: defaultdict[str, float] = defaultdict(float)

    def record_span(self, component: TraceComponent, latency_ms: float) -> None:
        if component is TraceComponent.RETRIEVAL:
            self._retrieval_latencies.append(latency_ms)

    def record_model(self, estimate: CostEstimate) -> None:
        self._model_calls += 1
        self._input_tokens += int(estimate.usage.input_tokens or 0)
        self._cached_input_tokens += int(estimate.usage.cached_input_tokens or 0)
        self._output_tokens += int(estimate.usage.output_tokens or 0)
        if estimate.estimated_cost_usd is None:
            self._unknown_cost_calls += 1
            return
        self._estimated_cost += estimate.estimated_cost_usd
        self._cost_by_role[estimate.model_role.value] += estimate.estimated_cost_usd

    def record_run(self, *, latency_ms: float, steps: int, tool_calls: int, terminal_status: str) -> None:
        self._latencies.append(latency_ms)
        self._agent_steps += steps
        self._tool_calls += tool_calls
        self._terminal_statuses[terminal_status] += 1

    def record_safety(self, outcome: str) -> None:
        self._safety_outcomes[outcome] += 1

    def record_handoff(self, outcome: str) -> None:
        self._handoff_outcomes[outcome] += 1

    def snapshot(self) -> AgentMetricsSnapshot:
        return AgentMetricsSnapshot(
            count=len(self._latencies),
            latency_p50_ms=_percentile(self._latencies, 0.50),
            latency_p95_ms=_percentile(self._latencies, 0.95),
            latency_p99_ms=_percentile(self._latencies, 0.99),
            input_tokens=self._input_tokens,
            cached_input_tokens=self._cached_input_tokens,
            output_tokens=self._output_tokens,
            model_calls=self._model_calls,
            tool_calls=self._tool_calls,
            agent_steps=self._agent_steps,
            estimated_cost_usd=self._estimated_cost,
            unknown_cost_calls=self._unknown_cost_calls,
            terminal_statuses=dict(self._terminal_statuses),
            safety_outcomes=dict(self._safety_outcomes),
            handoff_outcomes=dict(self._handoff_outcomes),
            retrieval_latency_p95_ms=_percentile(self._retrieval_latencies, 0.95),
            cost_by_role_usd=dict(self._cost_by_role),
        )


@dataclass(frozen=True)
class MonitoringThresholds:
    latency_p95_ms: float = 5_000.0
    tool_error_rate: float = 0.05
    daily_cost_usd: float = 0.0
    context_overflow_rate: float = 0.05
    agent_failure_rate: float = 0.05
    retrieval_failure_rate: float = 0.10
    safety_domain_unavailable_count: int = 1


class AlertSeverity(StrEnum):
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class MonitoringAlert:
    code: str
    severity: AlertSeverity


def evaluate_alerts(
    snapshot: AgentMetricsSnapshot,
    *,
    thresholds: MonitoringThresholds,
    tool_error_rate: float = 0.0,
    context_overflow_rate: float = 0.0,
    retrieval_failure_rate: float = 0.0,
) -> tuple[MonitoringAlert, ...]:
    """Return operational alerts from aggregate metadata, never raw events."""
    alerts: list[MonitoringAlert] = []
    if snapshot.latency_p95_ms is not None and snapshot.latency_p95_ms > thresholds.latency_p95_ms:
        alerts.append(MonitoringAlert("AGENT_P95_LATENCY_REGRESSION", AlertSeverity.WARNING))
    if tool_error_rate > thresholds.tool_error_rate:
        alerts.append(MonitoringAlert("AGENT_TOOL_ERROR_SPIKE", AlertSeverity.WARNING))
    if thresholds.daily_cost_usd > 0 and snapshot.estimated_cost_usd > thresholds.daily_cost_usd:
        alerts.append(MonitoringAlert("AGENT_DAILY_COST_BUDGET", AlertSeverity.WARNING))
    if context_overflow_rate > thresholds.context_overflow_rate:
        alerts.append(MonitoringAlert("AGENT_CONTEXT_OVERFLOW_SPIKE", AlertSeverity.WARNING))
    failures = sum(snapshot.terminal_statuses.get(status, 0) for status in ("FAILED", "TIMEOUT", "BUDGET_EXCEEDED"))
    if snapshot.count and failures / snapshot.count > thresholds.agent_failure_rate:
        alerts.append(MonitoringAlert("AGENT_FAILURE_SPIKE", AlertSeverity.WARNING))
    if retrieval_failure_rate > thresholds.retrieval_failure_rate:
        alerts.append(MonitoringAlert("AGENT_RETRIEVAL_QUALITY_REGRESSION", AlertSeverity.WARNING))
    if snapshot.safety_outcomes.get("SAFETY_DOMAIN_UNAVAILABLE", 0) >= thresholds.safety_domain_unavailable_count:
        alerts.append(MonitoringAlert("AGENT_SAFETY_DOMAIN_UNAVAILABLE", AlertSeverity.CRITICAL))
    return tuple(alerts)


class AgentTelemetry:
    """Trace propagation, structured events, metrics, and privacy enforcement."""

    def __init__(
        self,
        *,
        sink: TelemetrySink | None = None,
        metrics: AgentMetricsCollector | None = None,
        pricing: ModelPricingCatalog | None = None,
        clock: Callable[[], float] = time.perf_counter,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._sink = sink or StructuredLogSink()
        self.metrics = metrics or AgentMetricsCollector()
        self._pricing = pricing or ModelPricingCatalog()
        self._clock = clock
        self._now = now

    @property
    def pricing(self) -> ModelPricingCatalog:
        """BUILD-32: read-only access so a post-response persistence step
        (`backend.api.agent_v2_routes._persist_durable_trace`) can estimate a
        run's total cost from its aggregated `RunMetrics` token counts using
        the SAME catalog/version this run's own per-call estimates used."""
        return self._pricing

    def start_run(self, *, agent_run_id: str | None = None) -> TraceContext:
        trace = TraceContext.create(agent_run_id=agent_run_id)
        self.emit("agent_run.started", trace, TraceComponent.RUNTIME)
        return trace

    @contextmanager
    def span(
        self,
        trace: TraceContext,
        component: TraceComponent,
        *,
        operation: str,
        attributes: dict[str, Any] | None = None,
    ) -> Iterator[None]:
        started = self._clock()
        self.emit("agent_span.started", trace, component, operation=operation, **(attributes or {}))
        outcome = "OK"
        try:
            yield
        except Exception:
            outcome = "ERROR"
            raise
        finally:
            latency = max(0.0, (self._clock() - started) * 1000)
            self.metrics.record_span(component, latency)
            self.emit(
                "agent_span.finished",
                trace,
                component,
                operation=operation,
                outcome=outcome,
                latency_ms=latency,
            )

    def record_model(
        self,
        trace: TraceContext,
        *,
        role: ModelRole,
        model: str,
        usage: ModelUsage,
        latency_ms: float,
        request_id: str | None = None,
    ) -> CostEstimate:
        estimate = self._pricing.estimate(model=model, model_role=role, usage=usage)
        self.metrics.record_model(estimate)
        self.emit(
            "agent_model.completed",
            trace,
            TraceComponent.MODEL,
            model_role=role.value,
            model=model,
            latency_ms=latency_ms,
            input_tokens=int(usage.input_tokens or 0),
            cached_input_tokens=int(usage.cached_input_tokens or 0),
            output_tokens=int(usage.output_tokens or 0),
            estimated_cost_usd=estimate.estimated_cost_usd,
            input_cost_usd=estimate.input_cost_usd,
            output_cost_usd=estimate.output_cost_usd,
            provider_request_id=request_id,
        )
        return estimate

    def record_terminal(
        self,
        trace: TraceContext,
        *,
        status: str,
        latency_ms: float,
        steps: int,
        tool_calls: int,
        retries: int,
        safety_disposition: str | None = None,
        handoff_outcome: str | None = None,
    ) -> None:
        self.metrics.record_run(latency_ms=latency_ms, steps=steps, tool_calls=tool_calls, terminal_status=status)
        if safety_disposition:
            self.metrics.record_safety(safety_disposition)
        if handoff_outcome:
            self.metrics.record_handoff(handoff_outcome)
        self.emit(
            "agent_run.finished",
            trace,
            TraceComponent.RUNTIME,
            terminal_status=status,
            latency_ms=latency_ms,
            agent_steps=steps,
            tool_calls=tool_calls,
            retries=retries,
            safety_disposition=safety_disposition,
            handoff_outcome=handoff_outcome,
        )

    def event(self, trace: TraceContext, component: TraceComponent, name: str, **attributes: Any) -> None:
        self.emit(name, trace, component, **attributes)

    def emit(self, name: str, trace: TraceContext, component: TraceComponent, **attributes: Any) -> None:
        safe_name = name if _SAFE_EVENT.fullmatch(name) else "agent_event.invalid_name"
        self._sink.emit(
            TelemetryEvent(
                safe_name,
                trace,
                component,
                self._now(),
                _sanitize_attributes(attributes),
            )
        )


_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SAFE_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SAFE_EVENT = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_SAFE_CODE = re.compile(r"^[A-Z][A-Z0-9_:-]{0,127}$")
_SAFE_PROVENANCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}$")
_ALLOWED_ATTRIBUTE_KEYS = frozenset(
    {
        "agent_steps",
        "cached_input_tokens",
        "checkpoint_status",
        "component_status",
        "context_resolution_used",
        "error_code",
        "estimated_cost_usd",
        "final_router_intent",
        # TASK-V2.5-004 (CP1 contract mục 3): per-call cost BREAKDOWN, not
        # just the total -- durable trace §6 already wanted both (see
        # CostEstimate's own input_cost_usd/output_cost_usd fields), but
        # record_model never emitted them until this task needed real
        # per-call cost data to fix the MULTI_MODEL accounting bug (a run
        # mixing two models/prices cannot be re-priced from aggregate tokens
        # against a single assumed model).
        "input_cost_usd",
        "output_cost_usd",
        # BUILD-47: the follow-up classifier's own decision (BUILD-43,
        # emitted as `agent_context_resolution.completed`). These were
        # emitted from day one but never allowlisted, so every one was
        # dropped here before reaching any sink -- the decision was
        # unmeasurable in logs and in the DB alike.
        "follow_up_category",
        "follow_up_reason_code",
        "handoff_outcome",
        "inherited_entity",
        "inherited_topic",
        "input_tokens",
        "latency_ms",
        "model",
        "model_role",
        "operation",
        "outcome",
        "output_tokens",
        "provider_request_id",
        "provenance",
        "retries",
        "resolution_source_turn",
        "resolution_status",
        "resolved_topic",
        "safety_disposition",
        "terminal_status",
        "tool_calls",
        "tool_name",
    }
)


def _sanitize_attributes(values: dict[str, Any]) -> dict[str, str | int | float | bool | None]:
    safe: dict[str, str | int | float | bool | None] = {}
    for key, value in values.items():
        if key not in _ALLOWED_ATTRIBUTE_KEYS:
            continue
        if value is None:
            safe[key] = None
        elif isinstance(value, bool):
            safe[key] = value
        elif isinstance(value, int):
            safe[key] = max(0, value) if "token" in key or key in {"agent_steps", "tool_calls", "retries"} else value
        elif isinstance(value, float) and math.isfinite(value):
            safe[key] = max(0.0, value) if key in {"latency_ms", "estimated_cost_usd", "input_cost_usd", "output_cost_usd"} else value
        elif key in {"model", "provider_request_id"} and isinstance(value, str) and _SAFE_MODEL.fullmatch(value):
            safe[key] = value
        elif key in {"error_code", "terminal_status", "safety_disposition", "handoff_outcome", "component_status"} and isinstance(value, str) and _SAFE_CODE.fullmatch(value):
            safe[key] = value
        elif key == "provenance" and isinstance(value, str) and _SAFE_PROVENANCE.fullmatch(value):
            safe[key] = value
        elif key in {"final_router_intent", "resolution_status", "follow_up_category", "follow_up_reason_code"} and isinstance(value, str) and _SAFE_CODE.fullmatch(value):
            safe[key] = value
        elif key == "resolved_topic" and isinstance(value, str):
            safe[key] = value[:80]
        elif key in {"model_role", "operation", "outcome", "tool_name", "checkpoint_status"} and isinstance(value, str) and _SAFE_IDENTIFIER.fullmatch(value):
            safe[key] = value
    return safe


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * quantile) - 1))
    return ordered[index]


__all__ = [
    "AgentMetricsCollector",
    "AgentMetricsSnapshot",
    "AgentTelemetry",
    "AlertSeverity",
    "BufferingSink",
    "CostEstimate",
    "InMemoryTelemetrySink",
    "ModelPrice",
    "ModelPricingCatalog",
    "MonitoringAlert",
    "MonitoringThresholds",
    "StructuredLogSink",
    "TraceComponent",
    "TraceContext",
    "evaluate_alerts",
]
