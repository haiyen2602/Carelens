# BUILD-5 — Short-Term Memory

Date: 2026-08-18  
Scope: session-scoped, non-authoritative short-term memory for the disabled Agent V2 path. `AGENT_RUNTIME_ENABLED=false` remains unchanged. No long-term facts, episodic/semantic memory, RAG redesign, Doctor Handoff, Agent write action, persistence migration, or legacy-chat change was made.

## Implementation

`backend/agents/v2/short_term_memory.py` provides a process-local `ShortTermMemoryStore` keyed by the complete authenticated session boundary:

```text
actor_id + conversation_id + session_id
```

All three identifiers are required; a blank identifier fails closed. The store has no global read/enumeration operation, and `clear()` affects only its exact session key. Memory is not written to PostgreSQL and is deliberately lost on a server restart in this BUILD-5 scope.

The memory input types are:

- Recent user and assistant messages.
- One current task/intent per session.
- Resolved references, only when the caller explicitly requests the matching reference ID.
- One pending clarification per session.

Selection is deterministic. Current task and pending clarification are included because they are current conversational state. Messages must meet the caller-provided relevance threshold and are limited to the recent-message count. Resolved references must both meet that threshold and be explicitly requested. There is no semantic retrieval, automatic memory expansion, or quota filling.

## Authority and clinical boundary

Short-term memory creates only these Context Manager authorities:

| Memory input | Context authority | Meaning |
| --- | --- | --- |
| User message | `USER_ASSERTED` | A user claim, never confirmation of a clinical event. |
| Assistant message, task, clarification, resolved reference | `MEMORY` | Conversational continuity only. |

The memory API has no parameter that can assign `OPERATIONAL_DB`, `SAFETY_DOMAIN`, `DOCTOR`, or other authoritative clinical authority. A resolved reference retains mandatory provenance such as its originating approved tool, but remains `MEMORY`; a future Agent run must re-read the authoritative source through its domain tool before relying on it for patient care or safety.

## Context Manager integration and budget

`ShortTermMemoryStore.build_context()` passes the selected entries directly to BUILD-4 `ContextManager` as `MEMORY` / `SHORT_TERM` `ContextItem`s. The existing configured `AGENT_CONTEXT_SHORT_TERM_FRACTION=0.10` remains a ceiling, not a reservation. With the default input budget of `3072`, short-term memory can contribute at most `307` tokens after integer rounding.

When a selected entry does not fit that cap, BUILD-4 behavior is preserved without model-generated rewriting:

```text
original entry → caller-supplied compact entry → explicit reference → drop
```

This applies only to non-authoritative memory. It cannot compact, replace, or override an Operational DB, Safety Domain, Doctor, or Drug Knowledge V2 fact.

## Validation

```text
pytest -q tests/test_agent_v2_short_term_memory.py \
  tests/test_agent_v2_context.py tests/test_agent_v2_runtime.py \
  tests/test_agent_v2_model_gateway.py tests/test_agent_v2_route.py \
  tests/test_chat_security_gate.py tests/test_chat_routes.py
43 passed

ruff check backend/agents/v2/short_term_memory.py \
  tests/test_agent_v2_short_term_memory.py backend/agents/v2/context.py \
  backend/agents/v2/runtime.py backend/agents/v2/model_gateway.py \
  backend/api/agent_v2_routes.py backend/config.py \
  tests/test_agent_v2_context.py tests/test_agent_v2_runtime.py \
  tests/test_agent_v2_model_gateway.py tests/test_agent_v2_route.py
PASS

python -m compileall -q backend/agents/v2
PASS

git diff --check
PASS
```

The BUILD-5 tests cover actor/conversation/session isolation; scoped clearing; recent messages; current task; selected resolved references; pending clarification; relevance filtering without quota fill; explicit user-claim versus memory authority; no memory-created clinical authority; the exact 10% cap; compact/reference overflow; and invalid isolation/provenance input. The regression set confirms the Agent V2 feature flag/route behavior and legacy chat behavior remain intact.

## Deferred by scope

- No conversation/message/agent-run persistence review or migration was made.
- No long-term facts, episodic memory, semantic memory, or cross-session recall exists.
- No semantic relevance model, RAG retrieval, or model call is used to select/compact memory.
- No runtime endpoint is enabled, and no legacy chat request is redirected to Agent V2.

## Conclusion

BUILD-5: PASS

SESSION MEMORY: PASS

ISOLATION: PASS

10% BUDGET: PASS

AUTHORITY: PASS

CONTEXT INTEGRATION: PASS

REGRESSION: PASS

READY FOR BUILD-6: YES
