# BUILD-9 â€” Safety Integration

Date: 2026-08-18  
Scope: Agent V2 Safety Domain boundary only. `AGENT_RUNTIME_ENABLED=false`
remains unchanged. No Agent write action, Doctor Handoff creation, escalation
delivery, notification provider, RAG redesign, or runtime cutover was made.

## Boundary and reuse

`backend/agents/v2/safety.py` introduces a typed `SafetyGateway`; it contains
no medication-risk rule, prompt, model call, ORM query, or policy resolution.
The sole production adapter is `backend/services/agent_safety.py`, which calls
the existing DB-4H `assess_dose_safety` service. That service remains the
authoritative, idempotent assessment/event implementation. The adapter does
not call `process_safety_escalation`, create a doctor handoff, or deliver a
notification.

The trusted server-side trigger contract identifies these cases as mandatory
Safety candidates: `MISSED_DOSE`, `DELAYED_DOSE`, future `DOSE_ACTION`, and
future `SAFETY_ESCALATION`. A mandatory request requires a resolved V2 dose
occurrence ID; the typed request rejects an absent identifier. General
information is explicitly non-Safety and never substitutes for a patient
specific assessment. Intent values are a server routing contract, not a model
or prompt instruction.

## Decisions, authority, and terminal routing

The Gateway maps the immutable Safety Domain assessment to exactly one of:

| Domain result | Agent outcome |
| --- | --- |
| Explicit reviewed policy, known risk, no `REQUIRE_MEDICAL_REVIEW` | `SAFE` |
| `UNKNOWN`, `REQUIRE_MEDICAL_REVIEW`, or any non-`REVIEWED` policy (including legacy-unreviewed/default) | `HANDOFF_REQUIRED` |
| Safety service error, timeout, or incomplete result | `SAFETY_BLOCKED` |

Each decision retains assessment ID, risk, recommended action, policy source,
review status, reason code, timestamp, and `safety-domain:<assessment-id>`
provenance. `to_context_item()` emits protected `TOOL` context with
`SAFETY_DOMAIN` authority (90), therefore Web/RAG/Memory/User context cannot
compact, drop, or override it.

`ReadOnlyAgentRuntime.run(..., safety_decision=...)` now evaluates a Safety
decision before model planning or Tool Gateway execution. `SAFETY_BLOCKED` and
`HANDOFF_REQUIRED` return existing BUILD-3 terminal states with a generic
non-clinical response; model and tools receive no chance to produce a partial
or conflicting answer. A configured server-side
`AGENT_SAFETY_TIMEOUT_SECONDS=5` bounds the Gateway.

Doctor Handoff remains only a terminal status in this BUILD. No handoff record
is created and no provider notification is sent.

## Validation

- Typed gateway: reviewed SAFE, legacy/unreviewed/default handoff, invalid
  request, failure, and timeout are covered.
- Authority/provenance: Safety Context is protected and preserved verbatim
  under an insufficient context budget.
- Bypass prevention: a fake model that attempts an unsafe response is called
  zero times for blocked or handoff outcomes; no tool executes.
- Existing DB-4H service adapter: tested as a typed projection only; it does
  not invoke escalation.
- Agent V2 regression plus lint: **77 passed**.
- Existing Safety Domain/runtime and legacy safety regression: **26 passed**.
- Combined focused validation: **103 passed**.
- `ruff check` and `git diff --check`: PASS.

## P0/P1

- **P0: none.** The disabled runtime cannot reach model/tool execution after
  unresolved Safety, and Safety policy is not reproduced in an Agent prompt.
- **P1: trusted intent/occurrence resolution is a future orchestration task.**
  The current Agent V2 endpoint remains feature-flagged off and is still a
  read-only skeleton. BUILD-10/11 orchestration must bind authenticated dose
  context to this gateway before enabling the runtime; client/model claims
  alone must never select `GENERAL_INFORMATION` to bypass it.
- **P1: operational timeout cancellation.** The synchronous DB-4H service is
  measured and discarded if late; production task orchestration should add a
  request deadline/cancellation boundary around its DB session.

## Conclusion

BUILD-9: PASS

SAFETY GATEWAY: PASS

SAFETY AUTHORITY: PASS

BLOCK/HANDOFF ROUTING: PASS

FAIL-CLOSED: PASS

PROVENANCE: PASS

REGRESSION: PASS

READY FOR BUILD-10: YES
