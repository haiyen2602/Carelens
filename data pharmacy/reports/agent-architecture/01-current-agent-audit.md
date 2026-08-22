# BUILD-0 — Current Agent Audit

Date: 2026-08-18  
Scope: factual audit only. No runtime refactor, migration, feature flag, model call, or deployment was performed.

## Scope and baseline

The audited checkout is `main` at `2713b1b` (merge of Database Architecture V2). The current Alembic source chain ends at revision `0029`; the older Application Integration closeout references `0027`, so the closeout evidence must be reconciled to the current chain before it is reused as a clean-DB gate.

The existing chatbot is a legacy, task-specific LangGraph-style workflow. It is useful evidence and provides reusable components, but is **not** the proposed Agent V2 Core. Agent V2 must be introduced alongside it, behind a disabled-by-default flag, rather than replacing `POST /api/v1/chat`.

## Current runtime map

| Flow | Current implementation | Notes for Agent V2 |
| --- | --- | --- |
| Patient chat UI | `frontend/src/app/patient/assistant/page.tsx` → `useChatMessage` → Next proxy `frontend/src/app/api/chat/route.ts` | UI sends `patient_id` and message; it keeps its own conversation list/messages in browser `localStorage`. It does not use persisted backend chat history. |
| Chat API | `POST /api/v1/chat` in `backend/api/chat_routes.py` | JWT is required. The route runs input guardrail, a staged direct-node workflow, output guardrail, then writes audit and two chat-message rows. Existing response DTO must remain compatible. |
| Orchestration | `backend/agents/orchestrator.py::run_conversation` | Runs a legacy safety task concurrently with an ordered list of Python node functions. It is not a general tool planner, has no bounded agent/tool loop, checkpoint, or Agent V2 terminal states. |
| LLM/prompt calls | `backend/services/classification.py`, injected by `backend/api/chat_deps.py` | One `settings.model_name` (default `gpt-4o-mini`) is used for intent, dose, answer, safety, and several narrow LLM gates. Prompts/structured Pydantic outputs already exist, but there is no Model Gateway, separate model routing, per-run token/cost accounting, or runtime smoke-test suite. |
| Legacy RAG | `backend/services/retrieval.py` + `DrugChunk` | PostgreSQL/pgvector HNSW vector search plus pg_trgm lexical search, RRF fusion, explicit score thresholds, and source-bearing result objects. Once a drug is confirmed it uses direct `drug_id` filtering. |
| Drug Knowledge V2 | `backend/services/drug_knowledge/v2_agent.py` | Loads Final Canonical V2 JSONL artifacts, resolves legacy ID → canonical product ID, preserves provenance in chunks, uses structured knowledge-type lookup first, and then an in-memory sparse retrieval fallback. It is not exposed as a typed Agent tool yet. |
| Conversation persistence | `ChatMessage` / `HourlyConversationSummary` and `backend/agents/tools/chat_history_tool.py` | Full display history, 15-minute context, explicit history search, and hourly summaries exist. They are keyed by patient, not conversation. `Conversation`, `Message`, `AgentRun`, and `AgentToolEvent` ORM classes are present but have no runtime caller and no migration in the current Alembic chain. |
| Prescription and dose data | `backend/services/prescription/service.py`, `backend/services/scheduling/runtime_adapter.py`, API routes | Existing V2 sidecar/generation/state services are available behind legacy/shadow/V2 modes, but legacy chat nodes query ORM/session directly instead of calling typed domain tools. |
| Safety and escalation | legacy `backend/services/safety.py` / `escalation.py`; V2 `backend/services/safety_policy_domain/` | Legacy chat safety runs a keyword + LLM classifier and can directly initiate legacy escalation. The V2 service `process_dose_safety_runtime` atomically wraps assessment plus policy-gated escalation and fails closed. These are distinct paths. |

## Authentication and patient context

- `get_current_user` validates a bearer JWT and checks the account status.
- For role `patient`, `get_current_patient_id` ignores body `patient_id` and uses the JWT claim.
- For role `doctor` or `caregiver`, the chat helper currently accepts the request body patient ID without relationship verification. `verify_patient_access` likewise currently returns `True` for those roles. This cannot be reused as an Agent V2 authorization decision.
- The V2 dose API contains stronger caregiver-link checking, but this logic is not a reusable shared authorization tool contract.

## REUSABLE COMPONENTS

| Component | Reuse decision | Required boundary in a later build |
| --- | --- | --- |
| JWT identity (`CurrentUser`) and patient-role self binding | Reuse | Centralize server-side actor/patient authorization in the Tool Gateway; never accept model-produced IDs. |
| Next.js chat proxy, patient assistant page, chat request/response DTO | Reuse for compatibility | Add a separate feature-flagged Agent endpoint/mode; retain legacy endpoint and DTO behavior. |
| Input/output guardrails and rate limiter | Reuse as defense-in-depth | Policy context/tool authorization remains server-enforced and cannot be replaced by text guardrails. |
| `DrugChunk` hybrid pgvector retrieval | Reuse as legacy RAG implementation/evaluation baseline | Wrap it behind a retrieval interface with bounded context and provenance. Do not use similarity to resolve patient medicine identity. |
| Final Canonical V2 lookup service | Reuse first for `search_drug` and `get_drug_info` | Make canonical `drug_product_id`, provenance, ambiguous/not-found disposition, and output schema explicit. |
| Prescription, V2 dose-group adapter, and V2 state-domain services | Reuse as authoritative domain implementations | Expose read-only tool wrappers first; any write action requires separately approved confirmation, idempotency, and authorization policy. |
| V2 Safety Policy Runtime | Reuse only through its domain entry point | Agent must request a result and explain it; it must not reproduce policy/risk logic in a prompt. |
| Append-only `AuditLog`, `ChatMessage`, and hourly summaries | Reuse as legacy audit/history data | Do not treat them as the Agent V2 run/tool-event contract. Preserve PII minimization and retention policy. |
| Existing unit/API tests | Reuse as regression suite | Add Agent-specific deterministic/tool/auth/safety tests; do not weaken legacy tests. |

## GAPS

1. No `AGENT_RUNTIME_ENABLED` or other Agent V2 flags, no isolated Agent endpoint, and no LEGACY/SHADOW/read-only Agent rollout mode.
2. No Model Gateway: router/main/fallback/embedding/judge models, per-workload credentials, timeout/retry policy, structured tool-call interface, and cost/token telemetry are absent.
3. No typed Tool Gateway. Current chat nodes receive a SQLAlchemy `Session` and query tables/services directly, which conflicts with the required “Agent calls tools, never ORM” boundary.
4. No Agent V2 Context Manager, policy-context never-drop contract, context budget/compaction, file offload, or checkpoint/recovery state.
5. Existing `Conversation`, `Message`, `AgentRun`, and `AgentToolEvent` models are neither migrated nor used. Current persistence instead uses legacy `chat_messages`, hourly summaries, and `audit_log`.
6. No generic RAG corpus/index versioning, golden dataset, deterministic retrieval metrics, DeepEval/LLM-judge harness, embedding-drift gate, or Agent release report.
7. No approved Vinmec domain allowlist/search tool, doctor-review request lifecycle, recipient resolution, or long-term-memory consent/retention policy.
8. Existing logging is a JSON trace in `AuditLog`; there is no request/run trace correlation, tool-event persistence, latency/token/cost metrics, monitoring, or alert contract for Agent V2.

## CONFLICTS WITH AGENT ARCHITECTURE

- The legacy workflow can perform dose classification/state-related handling and direct escalation within chat orchestration. Agent V2 must start read-only and route missed/delayed safety through the audited V2 Safety Domain, not recreate decisions through prompts or legacy node sequencing.
- Chat nodes contain direct `Session` access for retrieval, prescriptions, schedules, and chat history. They must not be imported as Agent V2 tools without an adapter boundary.
- Existing chat history is patient-scoped, not conversation-scoped, and the frontend independently stores UI conversations locally. It does not meet the proposed conversation/message/run relationship or memory metadata model.
- The legacy one-model client conflicts with the approved configurable Router/Main/Fallback/Embedding/Judge architecture.
- Current legacy RAG and V2 knowledge retrieval are two different implementations (pgvector hybrid vs in-memory sparse JSONL lookup). They need an explicit source-of-truth and evaluation boundary; neither should silently substitute for the other.
- Legacy chat safety/escalation and V2 safety policy/escalation have different authority/provenance semantics. They cannot be merged by a prompt or by a generic “safety tool” without an approved adapter.

## FILES/MODULES TO CHANGE IN BUILD-1 (proposal only)

| Area | Candidate files/modules | Intended change |
| --- | --- | --- |
| Runtime isolation | new `backend/agents/v2/` package and a new API route module | Define disabled-by-default Agent Runtime Skeleton; do not alter legacy `chat_routes.py` behavior. |
| Configuration | `backend/config.py` | Add validated Agent V2 feature flags/configuration only after the exact configuration contract is approved. |
| Auth/tool boundary | `backend/api/security.py` plus new authorization/tool-gateway module | Enforce actor/patient relationship before every tool invocation; do not reuse permissive chat body-ID behavior. |
| Model boundary | new model-gateway module | Separate configurable router/main/fallback/embedding clients, structured outputs, timeouts, and backend-only key references. |
| Read-only tool adapters | new wrappers around `v2_agent.py`, prescription service, and scheduling runtime adapter | Implement allowlisted schemas for drug search/info, active prescriptions, today/upcoming doses, and dose status. |
| Observability contract | new Agent-run persistence/service after explicit schema approval | Record terminal run state and sanitized tool events without hidden reasoning or raw secrets. Existing models are not sufficient evidence that the tables exist. |
| Tests | new focused Agent V2 unit/API tests | Cover disabled flag, authorization isolation, typed tool validation, bounded execution, and legacy regression. |

## Feature flags

Existing runtime flags are limited to Drug Knowledge and Application Integration:

```text
DRUG_KNOWLEDGE_BACKEND=v1|v2|shadow     (default v2)
PRESCRIPTION_V2_MODE=legacy|shadow      (default legacy)
DOSE_RUNTIME_MODE=legacy|shadow|v2      (default legacy)
SAFETY_RUNTIME_MODE=legacy|shadow       (default legacy)
```

No `AGENT_*` flag currently exists. BUILD-1 must keep the new Agent path OFF by default and leave the legacy chat route untouched.

## Logging, tracing, and test tooling

- Current audit: `AuditLog` persists a request-level legacy node trace, final response, and duration. It intentionally is not hidden chain-of-thought.
- Current history: `ChatMessage` and `HourlyConversationSummary` have focused tests and explicit patient filters.
- Current tests include chat API/security/history/guardrail/orchestrator/retrieval/safety tests, V2 catalog tests, scheduling/state tests, and V2 safety-policy tests. They are a valuable regression baseline.
- Missing: Agent V2 test package, real model smoke tests for the approved stack, tool authorization matrix, prompt-injection tests across retrieval/web/tool output, cross-patient Agent tests, deterministic RAG metrics, tracing/metrics dashboards, and browser E2E automation.

## P0/P1 RISKS

### P0

- **Non-patient chat context is not relationship-authorized.** A doctor/caregiver caller can currently supply another `patient_id` to the legacy chat helper. Any Agent V2 endpoint/tool must fail closed until a server-side actor-to-patient authorization contract is enforced for every read and write. This is a build-enable gate, not permission to change legacy behavior in BUILD-0.
- **The required Agent-run persistence is not deployable as-is.** `Conversation`, `Message`, `AgentRun`, and `AgentToolEvent` are ORM-only in the audited source: no migration and no caller reference them. BUILD-1 must either remain fully non-persistent or obtain explicit schema/retention approval before adding a migration; it must not assume these tables exist.

### P1

- Reconcile the Application Integration closeout’s `0027` clean-DB assertion with the current Alembic source head `0029` before using it as a shared reproducibility gate.
- Replace/reconcile the frontend localStorage conversation UX with an approved server conversation contract only in a later, separately approved persistence/memory step.
- Define a common authorization adapter: dose routes have stronger caregiver-link checks than chat, while doctor access semantics remain broad.
- Define shared provenance/recipient semantics before comparing legacy chat escalation to V2 Safety Domain behavior.
- Add browser E2E and approved Agent/RAG evaluation datasets before broader user traffic.

## Proposed BUILD-1 — Agent Boundary + Runtime Skeleton

1. Add a disabled-by-default Agent V2 runtime flag and isolated endpoint; retain `POST /api/v1/chat` as the legacy compatibility path.
2. Build the authenticated context envelope from server-derived actor/patient data only. Enforce patient relationship authorization before the runtime can read any domain data.
3. Add a minimal Model Gateway interface and test doubles; do not call legacy ORM nodes from the new runtime.
4. Add a bounded read-only execution skeleton with explicit terminal statuses and a static allowlist. Initial tool contracts should be wrappers for canonical drug search/info, active prescriptions, today/upcoming doses, and dose status.
5. Add minimal sanitized request/run logging only after deciding whether it needs an approved persistence migration. No dose action, safety action, Vinmec web search, Doctor Handoff, RAG redesign, long-term memory, or production scheduler is in BUILD-1.
6. Gate all new behavior behind OFF-by-default configuration and add regression tests proving legacy chat behavior is unchanged.

## Conclusion

BUILD-0: PASS

CURRENT STATE:

- Legacy patient chatbot is live as a JWT-protected FastAPI route, a localStorage-backed frontend chat UI, a direct-node orchestration workflow, legacy pgvector RAG, and append-only audit/history persistence.
- Canonical Drug Knowledge V2, prescription/dose runtime adapters, and V2 Safety Policy services are present and are the correct domain dependencies for future typed tools.
- No Agent V2 endpoint, Tool Gateway, Model Gateway, Agent flags, Agent-run persistence, or evaluation/observability architecture is implemented.

REUSABLE:

- JWT identity/self-patient binding, UI/API compatibility shell, guardrails/rate limiting, legacy RAG baseline, Final Canonical V2 knowledge service, V2 Prescription/Dose/Safety domain services, and existing regression tests.

GAPS:

- Isolated runtime/flags, server-side relationship authorization, typed tools, model gateway, context/memory/checkpoint architecture, migrated Agent persistence, web/handoff, evaluation, and observability.

P0/P1:

- P0: non-patient authorization is not safe for an Agent tool surface; AgentRun/Conversation ORM models are not migrated or used.
- P1: migration-head evidence drift, localStorage/server conversation split, authorization semantic divergence, shared escalation semantics, browser E2E, and Agent evaluation tooling.

READY FOR BUILD-1: YES — only as an OFF-by-default, read-only skeleton whose first acceptance gate is server-side actor/patient authorization. It is not ready for Agent user traffic or any Agent write action.
