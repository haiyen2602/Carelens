# BUILD-13 — Agent V2 Observability

Date: 2026-08-18  
Scope: structured logging, trace propagation, metrics, cost estimation, and
monitoring design for Agent V2. `AGENT_RUNTIME_ENABLED=false` remains
unchanged. No model API call, production exporter, notification, or legacy-chat
change was added.

## Structured logging and redaction

`backend/agents/v2/observability.py` introduces a vendor-neutral telemetry
contract. `StructuredLogSink` emits one JSON event per sanitized record and a
test sink supports deterministic verification. Each record carries only:

- timestamp, `trace_id`, `agent_run_id`, component, operation/outcome;
- model/role, provider request ID, token usage, latency, and estimated cost;
- tool name/provenance, Safety/Handoff disposition, terminal status, retry, and
  safe error code.

The allowlist drops prompt/message/response/reasoning, tool arguments/results,
patient/user identity, arbitrary payload fields, API keys, tokens, passwords,
and unknown attributes. String formats for identifiers, model IDs, provenance,
and error/status codes are restricted. Checkpoint storage and telemetry remain
separate; no event writes raw checkpoint state.

## Tracing

`TraceContext` creates or receives an `agent_run_id` and propagates the same
trace through spans. The component contract covers:

```text
ROUTER -> MODEL -> TOOL -> RETRIEVAL -> WEB -> SAFETY -> HANDOFF -> CHECKPOINT -> RUNTIME
```

The BUILD-3 read-only runtime now accepts optional telemetry and trace context.
When supplied, it emits runtime/model/tool spans, model usage/cost telemetry,
terminal status, and budget/loop/timeout/retry guardrail events. BUILD-12
checkpoint adapters can also emit Tool, Safety, Handoff, Checkpoint, and
terminal events with the caller-supplied trace. The endpoint remains disabled;
there is no automatic production exporter or client-visible trace surface.

## Metrics and cost telemetry

`AgentMetricsCollector` maintains export-ready aggregate metadata:

- run and retrieval latency P50/P95/P99;
- input, cached-input, and output tokens;
- model/tool calls and Agent steps;
- terminal, Safety, and Handoff outcomes;
- total estimated cost, unknown-price calls, and cost broken down by Router,
  Main, Fallback, Embedding, and Judge roles.

Prices use an exact-model `ModelPricingCatalog`. The new
`AGENT_MODEL_PRICING_JSON` configuration is intentionally `{}` by default:
unknown model/version prices are counted as unknown rather than guessed. A
deployment must populate it from the currently approved provider pricing
catalog before treating cost as a financial control. The estimator supports
separate input, cached-input, and output per-million-token rates.

## Monitoring and alert design

`MonitoringThresholds` and `evaluate_alerts` provide the initial dashboard and
alert contract:

| Area | Signal | Initial action |
| --- | --- | --- |
| Performance | P95 latency regression | warning / investigate dependency latency |
| Tools | tool error-rate spike | warning / inspect typed gateway availability |
| Cost | daily cost budget | warning when deployment configures a budget |
| Context | overflow spike | warning / inspect context/retrieval sizing |
| Runtime | failure, timeout, budget, loop rate | warning / investigate guardrail path |
| Retrieval | quality/failure regression | warning / evaluate corpus/index/embedder |
| Safety | Safety Domain unavailable | critical |

Critical production alerts still required before enablement: cross-patient
authorization violation, required Doctor Handoff bypass, unexpected clinical
write attempt, and Policy Context construction failure. They are specified as
operational alerts but have no delivery provider in this phase.

## Validation

- Trace propagation: runtime/model/tool and contract spans for Router,
  Retrieval, Web, Safety, Handoff, and Checkpoint preserve one trace/run ID.
- Metrics: P50/P95/P99, retrieval latency, token accounting, terminal/Safety
  counters, and model-role cost breakdown validated.
- Cost: exact configured prices calculate input/cached/output cost; unknown
  model prices remain explicitly unknown.
- Redaction: patient ID, prompt/message, raw tool data, and API key-shaped
  values are omitted from emitted events.
- Runtime: retry, timeout, budget, and loop paths emit only safe guardrail
  event codes.
- Focused observability/runtime/checkpoint tests: **25 passed**.
- Full Agent V2 regression: **103 passed, 2 skipped** (opt-in PostgreSQL
  tests without a supplied disposable database URL).
- Ruff for changed files and `git diff --check`: **PASS**.

## P0/P1

- **P0: none.** Telemetry is opt-in, sanitized by allowlist, and Agent V2 is
  still disabled.
- **P1: production exporter and retention.** Select/configure a reviewed
  metrics/log/trace backend, access control, retention/deletion, dashboards,
  and alert delivery before runtime enablement. Do not export PHI/PII.
- **P1: pricing operations.** The team must update the exact-model price
  catalog and daily/monthly budget thresholds from approved current provider
  information; unknown prices must remain visible rather than coerced to zero.
- **P1: route orchestration.** A future enabled orchestration path must pass
  one server-generated trace into Retrieval/Web/Safety/Handoff adapters; the
  current flag-gated endpoint does not enable those flows.

## Conclusion

BUILD-13: PASS

LOGGING: PASS

TRACING: PASS

METRICS: PASS

COST TELEMETRY: PASS

REDACTION: PASS

MONITORING: PASS

REGRESSION: PASS

READY FOR BUILD-14: YES
