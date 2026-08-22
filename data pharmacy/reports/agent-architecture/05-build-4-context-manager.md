# BUILD-4 — Context Manager

Date: 2026-08-18  
Scope: deterministic Context Manager foundation for Agent V2. `AGENT_RUNTIME_ENABLED=false` remains unchanged. No long-term-memory persistence, RAG retrieval redesign, Doctor Handoff, write action, migration, or legacy-chat change was made.

## Context model

`backend/agents/v2/context.py` introduces a typed `ContextItem` with required `authority`, `priority`, `freshness`, and `provenance`, plus deterministic token metadata. The supported layers are:

```text
POLICY → SYSTEM → TASK → USER → MEMORY → RETRIEVAL → TOOL
```

- `POLICY` is `NEVER DROP`.
- `SYSTEM` is `PROTECTED`.
- Authoritative clinical sources (`DRUG_KNOWLEDGE_V2`, `OPERATIONAL_DB`, `SAFETY_DOMAIN`, and `DOCTOR`) are also protected: their source content is never compacted, rewritten, offloaded, or silently dropped.
- All lower-authority items are ordered by layer protection, priority, authority, relevance, then freshness.
- The manager does not infer authority or clinical truth. Future domain adapters must supply the correct provenance and authority.

## Context budget manager

The budget is fully backend-configured and reserves output tokens before any model input is assembled.

| Variable | Default | Purpose |
| --- | ---: | --- |
| `AGENT_TOKEN_BUDGET` | 4096 | Whole model-call budget from BUILD-3 |
| `AGENT_CONTEXT_TOKEN_BUDGET` | 3072 | Maximum bounded context input |
| `AGENT_OUTPUT_TOKEN_RESERVE` | 1024 | Reserved model-output capacity |
| `AGENT_CONTEXT_SHORT_TERM_FRACTION` | 10% | Maximum short-term-memory share |
| `AGENT_CONTEXT_LONG_TERM_FACTS_FRACTION` | 4% | Maximum long-term-facts share |
| `AGENT_CONTEXT_EPISODIC_FRACTION` | 3% | Maximum episodic-memory share |
| `AGENT_CONTEXT_SEMANTIC_FRACTION` | 3% | Maximum semantic-memory share |

The four memory allocations are ceilings, not reservations. Missing or irrelevant memory never causes the manager to fill a quota. The current local configuration was verified as `3072` input tokens plus `1024` output reserve within the `4096` total budget.

## Overflow behavior

For non-protected context, selection uses the bounded sequence: keep the relevant original item if it fits, otherwise use a caller-supplied compact representation, then an explicit reference/offload representation, then drop it with a reason. The manager never invokes an LLM to compact content in this phase.

If `POLICY`, `SYSTEM`, or an authoritative clinical item alone exceeds the input budget, every protected item is retained verbatim and the result is `OVERFLOW` with `PROTECTED_CONTEXT_EXCEEDS_INPUT_BUDGET`. A later runtime caller must fail gracefully rather than call a model with truncated clinical/policy context.

## Validation

```text
pytest -q tests/test_agent_v2_context.py tests/test_agent_v2_runtime.py \
  tests/test_agent_v2_model_gateway.py tests/test_agent_v2_route.py \
  tests/test_chat_security_gate.py tests/test_chat_routes.py
36 passed

ruff check backend/agents/v2 backend/api/agent_v2_routes.py backend/config.py \
  tests/test_agent_v2_context.py tests/test_agent_v2_runtime.py \
  tests/test_agent_v2_model_gateway.py tests/test_agent_v2_route.py
PASS

python -m compileall -q backend/agents/v2 backend/api/agent_v2_routes.py backend/config.py
PASS

git diff --check
PASS
```

The test suite covers all seven layers, priority/authority/freshness ordering, Policy never-drop, System/protected overflow, immutable authoritative clinical facts, non-reserved memory allocation targets, compact/reference/drop overflow behavior, output-token reserve validation, and Agent V2/legacy-chat regression.

## Deferred by scope

- No long-term facts, episodic memory, or semantic memory is persisted or retrieved.
- No RAG source, tool result, or patient clinical fact is created or altered by this manager.
- No model is called during compaction; adapters may provide a pre-approved compact representation in a later phase.
- No Agent V2 runtime request is enabled or redirected through legacy chat.

## Conclusion

BUILD-4: PASS

CONTEXT LAYERS: PASS

POLICY NEVER-DROP: PASS

BUDGET MANAGER: PASS

MEMORY ALLOCATION: PASS

OVERFLOW: PASS

REGRESSION: PASS

READY FOR BUILD-5: YES
