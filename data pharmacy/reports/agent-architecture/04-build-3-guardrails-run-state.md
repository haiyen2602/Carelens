# BUILD-3 — Guardrails + Run State

Date: 2026-08-18  
Scope: bounded execution and terminal run-state contract for the isolated Agent V2 read-only path. `AGENT_RUNTIME_ENABLED` remains `false`; no RAG, memory, Doctor Handoff implementation, write action, migration, or legacy-chat change was made.

## Implementation

### Config-driven limits

`AgentRunLimits` reads all runtime limits from backend settings. The `.env.example` documents the same server-side variables.

| Variable | Default | Enforced boundary |
| --- | ---: | --- |
| `AGENT_TOKEN_BUDGET` | 4096 | Observed input + output tokens from each Model Gateway plan |
| `AGENT_MAX_STEPS` | 4 | Model-planning and tool-execution steps combined |
| `AGENT_MAX_MODEL_CALLS` | 2 | Every attempt, including a retry |
| `AGENT_MAX_TOOL_CALLS` | 6 | Planned allowlisted tool calls before execution |
| `AGENT_MAX_RETRIES` | 1 | Transient/unavailable Model Gateway attempts |
| `AGENT_MODEL_TIMEOUT_SECONDS` | 15 | Per OpenAI SDK request and observed model-call deadline |
| `AGENT_RUN_TIMEOUT_SECONDS` | 30 | Whole Agent V2 run deadline |

The OpenAI SDK client is configured with `max_retries=0`; this prevents hidden SDK retries from exceeding the runtime's configured model-call/retry limits. The configured per-request timeout is passed to the SDK.

### Guardrail behavior

- Model usage (`input_tokens`, cached input tokens, and `output_tokens`) now returns in `ModelPlan` and is recorded in `RunMetrics` without logging prompts or credentials.
- A token, model-call, tool-call, or step overrun terminates before any additional tool is executed.
- A repeated identical tool signature in one plan is detected as a loop and terminated before the duplicate can execute.
- Model exceptions are retried only within both retry and model-call budgets. Provider errors remain non-sensitive to API callers.
- Model/run deadlines return `TIMEOUT`. Read-only synchronous tool calls are checked immediately before and after execution; they are not force-cancelled across a shared SQLAlchemy session.
- `CANCELLED` is supported through a server-side cancellation callback. There is no public cancellation API in this scope.
- A caller can pass `SafetyContext.UNRESOLVED` from a future Safety Domain boundary. If a budget or timeout guardrail fires in that state, the result is `SAFETY_BLOCKED`, never a partial/reassuring response. BUILD-3 does not classify safety itself.

### Terminal run-state contract

```text
COMPLETED
FAILED
BUDGET_EXCEEDED
TIMEOUT
SAFETY_BLOCKED
HANDOFF_REQUIRED
HANDOFF_CREATED
CANCELLED
```

`HANDOFF_REQUIRED` can represent an upstream disposition without creating anything. `HANDOFF_CREATED` is reserved in the common contract for the later Doctor Handoff domain; BUILD-3 deliberately does not create a handoff or any write record.

## Validation

```text
pytest -q tests/test_agent_v2_runtime.py tests/test_agent_v2_model_gateway.py \
  tests/test_agent_v2_route.py tests/test_chat_security_gate.py tests/test_chat_routes.py
29 passed

ruff check backend/agents/v2 backend/api/agent_v2_routes.py backend/config.py \
  tests/test_agent_v2_runtime.py tests/test_agent_v2_model_gateway.py \
  tests/test_agent_v2_route.py
PASS

python -m compileall -q backend/agents/v2 backend/api/agent_v2_routes.py backend/config.py
PASS

git diff --check
PASS
```

The tests cover token budget, step/model/tool limits, bounded retry accounting, model timeout, unresolved-safety budget/timeout fail-closed behavior, loop detection, cancellation, handoff-required representation, exact terminal-state contract, Agent V2 authorization/flag behavior, and legacy chat regression.

`AGENT_RUNTIME_ENABLED=false` was rechecked after the test run.

## P1 follow-up, not in BUILD-3

Agent-run persistence, a public cancellation endpoint, cooperative tool cancellation, Safety Domain integration, and Doctor Handoff creation are intentionally deferred. None is required to activate this guardrail contract while the Agent V2 path remains disabled.

## Conclusion

BUILD-3: PASS

TOKEN GUARDRAIL: PASS

STEP/MODEL/TOOL LIMITS: PASS

TIMEOUT/LOOP: PASS

RUN STATES: PASS

REGRESSION: PASS

READY FOR BUILD-4: YES
