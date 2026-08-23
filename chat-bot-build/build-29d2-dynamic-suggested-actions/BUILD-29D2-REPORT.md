# BUILD-29D.2 Report

## 1. Initial Audit

Audit date: 2026-08-23. Branch: `feature/build-29d2-dynamic-suggested-actions`, created from `origin/main` at `d56e4c4`.

- Backend response already exposed `suggested_actions` through `AgentV2OrchestrateResponse` and the frontend `/api/chat` proxy.
- `frontend/src/components/chat-message.tsx` already rendered only the action array stored with each assistant message. Its buttons forwarded a structured `selected_action` through `frontend/src/app/patient/assistant/page.tsx`.
- The authoritative state was persisted per actor, patient, and conversation by `backend/services/agent_conversation_state.py`; the route checked the client action against that state before binding it.
- The fault was in `backend/agents/v2/conversation_state.py`: `transition_state()` always rebuilt one fixed disease list (`causes`, `symptoms`, `danger`, `prevention`, `urgent_care`) or one fixed drug list (`uses`, `dosage`, `side_effects`, `contraindications`) whenever a topic/entity existed. The list was independent of the reply, the query's requested attribute, real tool evidence, or the Agent's current capability.
- Actions used old types `topic_attribute` and `drug_attribute`. The old semantic values did not match the BUILD-29D.2 allowlist.
- Typed numeric and text follow-up existed, but was tied to the same fixed list. A stale/forged structured action was already safely ignored at the route boundary.
- No reply-text parser generated actions. Therefore a model answer could offer A/B/C while the stored state and UI rendered the unrelated fixed list.
- `BUILD-30` activity snapshots were independently persisted and the frontend rendered the trace timeline. `BUILD-29` feedback and report controls are siblings of the suggestion rendering.

## 2. Root Cause

Suggested-action generation was embedded in the generic conversation-state transition. That transition had no response, tool-evidence, or capability input, so it could only generate universal static templates. The frontend faithfully rendered the backend array, but the array was not derived from the assistant's answer.

## 3. Architecture Before

`Agent result -> transition_state(topic/entity) -> fixed action templates -> persisted state -> API -> frontend buttons`

The answer and action list were independent outputs.

## 4. Architecture After

`Agent result + authoritative state + tool evidence -> build_suggested_actions() -> reply with the exact offered labels + allowlisted structured actions -> transition_state(action record only) -> persisted state -> API -> frontend buttons`

`transition_state()` no longer owns a disease/drug button template. The new generator runs only after the agent has produced a completed answer, accepts the real intent/query/topic/entity/evidence, chooses 0–3 supported semantic follow-ups, and appends the identical labels to the reply. Safety, failed, unsupported, ambiguous, and evidence-free drug runs produce `[]`.

## 5. Suggested Action Contract

`POST /api/v1/agent/v2/orchestrate` retains `selected_action`, but action types are now `topic_followup`, `drug_followup`, and `schedule_followup`.

- General medical values: `definition`, `causes`, `symptoms`, `treatment`, `prevention`, `danger`, `urgent_signs`, `diagnosis`, `monitoring`.
- Drug values: `drug_uses`, `dosage`, `administration`, `side_effects`, `contraindications`, `warnings`, `interactions`.
- Medication-schedule values: `today_schedule`, `next_dose`, `upcoming_schedule`, `adherence_history`.

The state loader, state transition, and route validation all reject/discard values outside this allowlist. The route only accepts an action matching the latest server-issued action for the same authenticated actor/patient/conversation; it never uses client `topic` or `entity_id` as an authority.

## 6. Conversation State Integration

State serialization is bumped to version 2. It stores the exact dynamic actions issued for the most recent assistant turn. New authoritative topic/entity results replace the opposite active context and overwrite actions; a safety event clears actions. Consequently an older topic/entity action cannot be applied after a switch. Typed exact labels, short aliases (for example `nguyên nhân`, `công dụng`), and numeric choices are resolved only from this latest state.

## 7. Backend Changes

- Added `backend/agents/v2/suggested_actions.py`: response-consistent generator, action labels, allowlisted semantic ordering, evidence gate for drug actions, and reply footer.
- Reworked `backend/agents/v2/conversation_state.py`: removed `_TOPIC_ATTRIBUTES`/`_DRUG_ATTRIBUTES`; added action allowlists, type-aware validation, dynamic action persistence, numeric/typed compatibility, and topic/drug query binding.
- Updated `backend/api/agent_v2_routes.py`: generates actions after the completed orchestration result, sends the generated reply/actions, passes server-authored drug labels to the bound tool, and persists user-safe activity events.
- Updated `backend/models/schemas.py` DTO type literals.

## 8. Frontend Changes

- Updated TypeScript action union in `frontend/src/types/chat.ts` and `/api/chat` proxy DTO.
- The existing assistant message renderer continues to render only the server-returned action array; it does not render an empty action container or internal JSON/IDs.
- Action buttons are responsive/touch-sized, keyboard focusable, disabled during submission, and now have a synchronous `submitInFlight` guard to prevent a double-click before React Query updates `isPending`.
- Clicking a button creates the normal user message and sends the structured action through `/api/chat` as before.

## 9. Security / Authorization

The protection path remains server authoritative. `is_allowed_action()` validates type/value/context shape; `_validated_selected_action()` then requires all client fields to match one current server-issued action. State persistence is scoped by actor, patient, and conversation. Bound drug follow-ups use the previously resolved canonical server entity and server-authored label, never a client-supplied entity ID. Existing patient authorization remains unchanged.

## 10. Safety Interaction

No BUILD-29C Safety rule was changed. Raw message routing still happens before normal follow-up resolution. A safety intent or safety decision supplies no actions and clears pending offered actions, so a dangerous message such as `tôi vừa nôn ra máu` cannot apply an ordinary active-topic follow-up.

## 11. Activity Timeline Integration

BUILD-30 remains durable and user-safe. The snapshot builder receives the validated selected action and newly generated actions, adding only `suggested_action.selected` (the label the user saw) and `suggested_actions.created`. It never stores action IDs, entity IDs, internal tool names, or reasoning.

## 12. Tests Added

- Replaced the BUILD-29D.1 fixed-template state test with dynamic-action coverage: disease reply/action consistency, drug evidence and canonical binding, typed and numeric resolution, forged/stale action rejection, topic switch invalidation, safety clearing, and actor/patient/conversation isolation.
- Added activity-timeline coverage proving action events are label-only and do not expose IDs.

Commands and results:

```text
pytest -q tests/test_agent_v2_conversation_state.py tests/test_agent_activity.py tests/test_agent_v2_route.py tests/test_agent_v2_orchestrator.py
98 passed, 1 warning in 0.60s

pytest -q tests/test_agent_feedback_service.py tests/test_get_current_patient_id.py tests/test_agent_v2_time_query_engine.py
211 passed, 4 skipped, 1 warning in 5.23s

ruff check backend/agents/v2/conversation_state.py backend/agents/v2/suggested_actions.py backend/api/agent_v2_routes.py backend/models/schemas.py backend/services/agent_activity.py tests/test_agent_v2_conversation_state.py tests/test_agent_activity.py
All checks passed!

npx eslint src/types/chat.ts src/app/api/chat/route.ts src/app/patient/assistant/page.tsx
PASS (no output)
```

The four skipped authorization integration tests require a local PostgreSQL instance. A full `pytest -q` was started but did not produce a result after 60 seconds and was stopped; it is not counted as passing.

(Superseded by §14: re-run in session 2 against a real local Postgres after the §13.2 fix — all 4 previously-skipped tests now execute for real, 313 passed total.)

## 13. Local E2E Evidence (2026-08-23, session 2 — BUILD-29D.2 completion)

### 13.1 Runtime-gate blocker, root cause and local-only fix

`POST /api/v1/agent/v2/orchestrate` returned HTTP 404 locally because
`backend/api/agent_v2_routes.py` (`run_agent_orchestration`) checks
`Settings.agent_runtime_enabled` (default `False`, `backend/config.py`) before
authorizing or touching the DB — see the 404 branch and its docstring at
`agent_v2_routes.py:156-168`. The repo's `.env` (gitignored, never committed)
had no `AGENT_RUNTIME_ENABLED` entry, so the flag stayed at its safe default.

Fix (**local only**): added `AGENT_RUNTIME_ENABLED=true` to the local `.env`
with a comment explaining the file is gitignored and production reads its own
env vars from the real deploy host, never from this file — see `.env`. No
file under version control changed to enable this; `agent_canary_allowlist`
and `agent_rollout_percentage` (the two other gates that apply once the flag
is on) were left untouched at their safe defaults. Backend and frontend were
restarted (`uvicorn backend.main:app`, `next start`) to pick up the new env
var. Confirmed the gate was cleared: `POST /agent/v2/orchestrate` with no
Authorization now returns 401 (auth check) instead of 404 (feature gate).

### 13.2 New regression found via real E2E, and its fix (in-scope, 2 files)

Running Flow B for real (`"Công dụng của thuốc Long Huyết là gì"`, a message
that both names a specific drug and contains the router's generic `"là gì"`
keyword) surfaced a genuine defect in this build's own new code, independent
of the runtime-gate blocker:

- `classify_intent()` (pre-existing router, unchanged) can label a
  drug-specific message `GENERAL_MEDICAL_INFORMATION` purely because it
  contains a generic phrase like `"là gì"`, even while the orchestrator still
  answers correctly from that drug's real evidence.
- `agent_v2_routes.py` trusted that label unconditionally: `topic` was set to
  the raw semantic-normalized message text whenever `result.intent ==
  GENERAL_MEDICAL_INFORMATION`, regardless of whether a real drug entity had
  actually been resolved that turn.
- `conversation_state.transition_state()` nulls `next_entity` when `topic` is
  set, then nulls `next_topic` when `entity` is set (in that order) — when
  both were truthy on the same turn, this left the persisted state with
  **both** `active_topic` and `active_entity` at `None`, discarding a real
  drug resolution.
- `suggested_actions.build_suggested_actions()` only considered the
  `drug_followup` branch when `intent is DRUG_INFORMATION`, so a mislabeled
  turn fell into the `topic_followup` branch and offered garbage suggestions
  built from the raw message (`"Nguyên nhân gây cong dung cua thuoc long
  huyet"`) with `entity_id: null` — no canonical binding at all, for an
  answer that was genuinely about one specific drug.

**Fix** (both files already owned by this build, no router/architecture
change): `agent_v2_routes.py` now only treats a turn as general-topic when
`resolved_entity is None`; `suggested_actions.py` now checks
`entity and _has_drug_evidence(tool_results)` *before* the topic branch,
independent of the intent label, since a server-resolved drug entity backed
by real tool evidence is authoritative over the router's own text-keyword
guess. See the inline comments added at both call sites for the full
rationale. Verified with the full regression suite after the fix — see §14.

### 13.3 Real E2E results (real OpenAI calls, real local Postgres, real JWT auth)

A fresh patient account was registered through the real
`POST /api/v1/auth/register` (patient `BN00008`), and every message below was
sent through the real Next.js proxy (`http://127.0.0.1:3000/api/chat`,
forwarding the real bearer JWT), never directly to the backend, so the same
code path a browser uses was exercised end-to-end.

**Flow A — general-medical topic, dynamic suggestions, click-through, topic
binding: PASS.**
1. `"gan nhiễm mỡ là gì"` → real grounded reply (citations from `Glutaone
   600`, `Anbaliv 400`, `NEW Hepalkey` — real hepatoprotective-drug RAG
   chunks) + 3 dynamic `topic_followup` actions (`causes`, `treatment`,
   `urgent_signs`), all bound to `topic: "gan nhiem mo"`.
2. Clicked the `causes` action (sent its exact `action_id`/`type`/`value`/
   `topic` as `selected_action`) → real causes answer for the *same* topic,
   3 new actions still bound to `"gan nhiem mo"`.

**Topic-switch invalidation: PASS.** In the same conversation, asked
`"đau đầu là gì"` (a different topic) → state moved to `"dau dau"`. Replaying
the *stale* `treatment` action from step 2 above (still a structurally valid,
allowlisted action shape, just no longer the latest server-issued one) was
rejected: the server discarded it and fell back to treating the message as
plain text, which correctly failed to find data for the disconnected text
rather than reusing the old topic's context. `state.offered_actions` had
already moved to the `"dau dau"` set.

**Safety priority: PASS.** In the same conversation, sent
`"tôi vừa nôn ra máu"` → real Safety escalation: `status: HANDOFF_CREATED`,
`safety_disposition: HANDOFF_REQUIRED`, `severity: HIGH`, `safety_flag: true`,
`suggested_actions: []`. A follow-up reusing a pre-safety-event action
(`"dau dau"`'s `causes`) was also rejected (state's offered actions were
cleared by the safety turn), and the message was correctly re-answered fresh
instead of resuming the old bound context.

**Flow B — drug entity binding: partially verified; the literal 3-step
script could not be completed live. See §13.4 for why, and §15 for the
newly-discovered underlying cause.** The regression in §13.2 *is* fixed and
covered by the (now 313-passing, real-Postgres-backed) unit/integration
suite, including the exact `drug_followup`/canonical-binding/stale-action
scenarios — but no real conversation in this session ever got the live model
to actually call `get_drug_info` on a cold turn (4 phrasings tried: a
generic product query, an explicit "công dụng ... là gì", a rephrase
avoiding every `GENERAL_MEDICAL_INFORMATION` keyword, and a side-effect
question for a second, well-known drug). Every one of them called only
`search_drug` (catalog metadata, no verified-content citations) and then
synthesized directly. `entity`/`_has_drug_evidence` are both keyed off a real
`get_drug_info` tool result, so with no such call, no drug turn in this
session ever reached the fixed `drug_followup` branch live end-to-end — see
§15 for why this appears to be structural, not bad luck.

**Ticket (BUILD-29 feedback) + Activity Timeline (BUILD-30): PASS, real
requests.** `POST /agent/v2/feedback` against a real trace from the flow
above returned `201` with a real ticket (`status: OPEN`, `priority: P3`).
`GET /agent/v2/traces/{trace_id}/activity` against the same trace returned
`200` with the real 4-step timeline (`intent → retrieval → generation →
suggested_actions.created`) — confirms BUILD-30's `suggested_actions.created`
integration renders from a real run, label-only, no IDs, as designed.

### 13.4 Why Flow B's literal script couldn't run live

The user-specified script asks a *generic* "info about drug X" question
first, then expects a "Công dụng" button to click. A generic first message
correctly returns `suggested_actions: []` (no verified attribute evidence to
offer yet — this is the intended fail-closed behavior per §4/§10, not a
bug), so there is no such button to click on that exact script. The 4
rephrasings above were an attempt to reach a state where a real
`drug_followup` action *did* get offered; none of them did, for the
structural reason in §15.

### 13.5 Frontend production build

Frontend production compilation was independently verified after restoring
dependencies from the lockfile:

```text
cmd /c npm ci --no-audit --no-fund
npm run build
PASS: frontend/.next/BUILD_ID created
```

## 14. Regression Results

Re-run after the §13.2 fix, against the real local Postgres (no longer
skipped — the 4 authorization integration tests that needed a DB now
actually execute instead of skipping):

```text
pytest -q tests/test_agent_v2_conversation_state.py tests/test_agent_activity.py \
        tests/test_agent_v2_route.py tests/test_agent_v2_orchestrator.py \
        tests/test_agent_feedback_service.py tests/test_get_current_patient_id.py \
        tests/test_agent_v2_time_query_engine.py
313 passed in 17.65s
```

(One stale row left in the local `account` table by an earlier, interrupted
test run — `test-caregiver-conftest`, disposable fixture data, not real
patient data — was blocking `tests/test_get_current_patient_id.py` with a
unique-constraint error; deleted directly so the fixture's own
insert/teardown could run cleanly. Two of the tests above also depend on
`agent_runtime_enabled` being `False` — they were run with
`AGENT_RUNTIME_ENABLED=false` overriding this session's local `.env`, and
confirmed to fail for that environmental reason alone, not from the code
change, when run against the flipped-on local flag.)

- BUILD-29 feedback/ticket service regression: passed above; additionally
  confirmed live in §13.3 (`POST /agent/v2/feedback` → real `201`).
- BUILD-30 timeline regression: passed above; additionally confirmed live in
  §13.3 (`GET /agent/v2/traces/{id}/activity` → real `200`, real 4-step
  trace including `suggested_actions.created`).
- BUILD-28 Time Query Engine regression: passed above.
- BUILD-29C safety/state regression: passed above; additionally confirmed
  live in §13.3 (real acute-danger message → real `HANDOFF_CREATED`, actions
  cleared, stale pre-safety action rejected).

## 15. Known Limitations

- Suggested-action selection is deterministic and allowlisted; it does not make a second LLM call. The backend appends the chosen, capability-appropriate directions to the displayed reply so reply/UI consistency is structural.
- Repository-wide frontend lint currently reports pre-existing CRLF/Prettier errors across the untouched tree (26,061 findings); the three changed frontend files pass ESLint when targeted.
- **Newly discovered, pre-existing, out-of-scope for this build**: a cold
  conversation turn asking about one specific drug's attribute
  (`DRUG_INFORMATION` intent) appears structurally unable to get grounded
  citations or set `active_entity` via the model's own tool planning.
  `get_drug_info` requires a `legacy_drug_id` that only `search_drug`'s
  result can provide, so answering with real evidence needs two sequential
  tool calls; `Settings.agent_max_model_calls` defaults to `2`
  (`backend/config.py`), which — per the observed real trace spans (exactly
  one `plan_read_only` model call followed by one `synthesize_read_only`
  model call, and BUILD-20's own documented step-cost model) — covers one
  planning call and one synthesis call, with no budget for a second planning
  round after seeing `search_drug`'s output. Across 4 different real
  phrasings in this session (varying keywords, a generic product query, an
  explicit attribute question, and a second, well-known drug), the live
  model always stopped at `search_drug` and synthesized from general
  knowledge (with appropriate "not from verified data" hedging) rather than
  chaining into `get_drug_info`. The one path that *does* reliably reach
  `get_drug_info` is the deterministic server-side bind at
  `agent_v2_routes.py`/`orchestrator.py:1414` (`active_entity_id` +
  `requested_attribute` both present) — which itself requires
  `active_entity` to already be set from a *prior* turn, i.e. it cannot
  bootstrap a brand-new entity on a cold conversation either. This is not a
  BUILD-29D.2 regression (nothing in this build's diff touches
  `agent_max_model_calls`, the router, or the tool-execution loop) — it
  predates this build and was never previously exercised end-to-end with a
  live model (the report's own §13, prior revision, records local E2E as
  never having reached completion at all). Recommend a dedicated follow-up
  to review `agent_max_model_calls` for `DRUG_INFORMATION` specifically, or
  a compound/two-hop-aware tool design, with its own cost/latency review —
  out of scope to change here per this session's explicit instruction not to
  alter architecture without a build-scoped regression to justify it.

## 16. Files Changed

- `backend/agents/v2/conversation_state.py`
- `backend/agents/v2/suggested_actions.py` (new)
- `backend/api/agent_v2_routes.py`
- `backend/models/schemas.py`
- `backend/services/agent_activity.py`
- `frontend/src/app/api/chat/route.ts`
- `frontend/src/app/patient/assistant/page.tsx`
- `frontend/src/types/chat.ts`
- `specs/api-contracts.md`
- `tests/test_agent_activity.py`
- `tests/test_agent_v2_conversation_state.py`
- this report

## 17. Commit / Branch / PR

- Branch: `feature/build-29d2-dynamic-suggested-actions`
- Base: `origin/main` at `d56e4c4` (`fix(patient): clear stale photo-verification banner when the hero card switches doses (#102)`).
- The local runtime gate (§13.1) is resolved locally only — no committed file
  changed to clear it; `.env` is gitignored and production reads its own env
  vars from the real deploy host.
- Commit / push / PR: created after this report update — see repo history
  for the commit on this branch and the opened PR. Not deployed; deploy
  requires review/merge per instruction.

## 18. Release Gate

```text
BUILD-29D.2: PASS (conditional — see note)
HARDCODED SUGGESTIONS REMOVED: PASS
DYNAMIC SUGGESTED ACTIONS: PASS
REPLY/ACTION CONSISTENCY: PASS
ACTIVE TOPIC BINDING: PASS (real E2E, §13.3 Flow A)
ACTIVE ENTITY BINDING: PASS at unit/integration-test level (313 tests, real
  Postgres); NOT exercised live end-to-end with a live model in this
  session — see §13.4/§15 for the pre-existing, out-of-scope reason
TYPED FOLLOW-UP: PASS (unit/integration suite)
NUMERIC SELECTION: PASS (unit/integration suite)
ACTION ALLOWLIST: PASS
STALE ACTION PROTECTION: PASS (real E2E, §13.3 topic-switch + post-safety)
SAFETY PRIORITY: PASS (real E2E, §13.3 — real acute-danger escalation)
CONVERSATION ISOLATION: PASS (unit/integration suite)
CROSS-PATIENT PROTECTION: PASS (real Postgres integration tests now execute,
  no longer skipped — 313/313 passing)
TICKET REGRESSION: PASS (real E2E, §13.3)
ACTIVITY TIMELINE REGRESSION: PASS (real E2E, §13.3)
REAL LOCAL APP CHAT: PASS for general-medical/topic flows, safety, ticket,
  timeline (real OpenAI + real Postgres + real JWT auth, §13.3). Drug-entity
  binding (Flow B) could not be driven live in this session for a reason
  outside this build's scope (§15) — condition on this gate: the fix in
  §13.2 is real and unit/integration-verified, but a follow-up should
  confirm it end-to-end once the underlying model-call-budget question is
  resolved.
REAL PRODUCTION APP CHAT: NOT RUN (no reviewed merge/deploy — do not deploy
  before review, per instruction)
```

Report deliverable at
`chat-bot-build/build-29d2-dynamic-suggested-actions/BUILD-29D2-REPORT.md`.
PASS is conditional on the §15 limitation being tracked as a separate
follow-up, not silently accepted as resolved. Do not deploy before review.
