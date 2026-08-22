# BUILD-2 — Model Gateway + Real Model Smoke Tests

Date: 2026-08-18  
Scope: config-driven, backend-only OpenAI Model Gateway validation. Agent V2 remains OFF by default. No RAG, memory, Doctor Handoff, Agent write action, migration, or runtime cutover was added.

## Implementation

- Added one backend-only workload configuration for each initial Agent V2 role. A workload-specific `OPENAI_*_API_KEY` wins; the already-supported `OPENAI_API_KEY` is an explicit local/development fallback. No credential value is returned by the gateway, included in prompts, printed by the smoke runner, or committed.
- Configured the approved mapping:

| Role | Environment model setting | Default model |
| --- | --- | --- |
| Router | `AGENT_ROUTER_MODEL` | `gpt-5.4-nano` |
| Main | `AGENT_MAIN_MODEL` | `gpt-5.4-mini` |
| Fallback | `AGENT_FALLBACK_MODEL` | `gpt-5.4` |
| Embedding | `AGENT_EMBEDDING_MODEL` | `text-embedding-3-small` |
| Judge | `RAG_JUDGE_MODEL` | `gpt-4o` |

- Implemented `OpenAIModelGateway` behind the existing Agent V2 route flag. It can only declare the six BUILD-1 read-only tool schemas. A provider failure produces the existing non-sensitive terminal `FAILED` run status; it does not expose a provider message, request content, or secret.
- Added `scripts/agent_v2/smoke_model_gateway.py`. It preflights all credentials before making any request and emits only role, model, pass/fail, latency, numeric token telemetry, request ID, and a sanitized error type. It makes no request containing patient data.
- `AGENT_RUNTIME_ENABLED` was rechecked as `false`. The legacy chat route remains unchanged.

## Automated validation

```text
pytest -q tests/test_agent_v2_model_gateway.py tests/test_agent_v2_runtime.py \
  tests/test_agent_v2_route.py tests/test_chat_security_gate.py tests/test_chat_routes.py
20 passed

ruff check backend/agents/v2 backend/api/agent_v2_routes.py backend/config.py \
  scripts/agent_v2/smoke_model_gateway.py tests/test_agent_v2_model_gateway.py \
  tests/test_agent_v2_runtime.py tests/test_agent_v2_route.py
PASS

python -m compileall -q backend/agents/v2 backend/api/agent_v2_routes.py \
  backend/config.py scripts/agent_v2/smoke_model_gateway.py
PASS

git diff --check
PASS
```

The tests cover exact model mapping, credential preflight before any network call, structured Router output, forced Main function-call compatibility, terminal failure sanitization, and the existing Agent V2/legacy-chat regression set.

## Real API smoke tests

The runner first confirmed a backend credential source was available without displaying it. A sandboxed attempt could not reach the API; the definitive run was made from the local backend environment. It used a fixed non-PII smoke prompt and no Agent runtime route was enabled.

| Workload | Model | API check | Result | Input / cached / output tokens | Latency | Sanitized error |
| --- | --- | --- | --- | --- | --- | --- |
| Router | `gpt-5.4-nano` | Responses + strict JSON Schema | PASS | 35 / 0 / 16 | 2645.26 ms | — |
| Main | `gpt-5.4-mini` | Responses + forced `search_drug` function call | PASS | 63 / 0 / 23 | 1447.97 ms | — |
| Fallback | `gpt-5.4` | Responses text generation | PASS | 13 / 0 / 5 | 1045.26 ms | — |
| Embedding | `text-embedding-3-small` | Embeddings endpoint | PASS | 5 / — / — | 2403.52 ms | — |
| Judge | `gpt-4o` | Responses text generation | PASS | 14 / 0 / 2 | 2426.82 ms | — |

`OPENAI_FALLBACK_API_KEY` was subsequently configured and the isolated Fallback retry passed. The complete five-workload rerun above is the final BUILD-2 evidence. The raw provider response and all credential values were deliberately not persisted. No rate-limit error was observed.

## Conclusion

BUILD-2: PASS

ROUTER: PASS

MAIN: PASS

FALLBACK: PASS

EMBEDDING: PASS

JUDGE: PASS

READY FOR BUILD-3: YES
