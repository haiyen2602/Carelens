# BUILD-44 — Doctor Chat Queue & Takeover

Branch: `feature/build-44-doctor-chat-takeover`
Worktree: `P-067-build-44-doctor-takeover`
Baseline: `6f15deb` (BUILD-43 production validation merged, PR #131)
Commits: `4fbd2a9` (feat), `19ef763` (merge origin/main), `25327a3` (fix: migration 0053 collision)

## 0. Precondition

`git log -1 origin/main` at start: `6f15deb` (BUILD-43 merged, production-validated). Alembic head on
this worktree's baseline: `0052`. Local Postgres confirmed healthy (`p-067-db-1`, docker). Track B
(Drug Image Intelligence) confirmed running in parallel in a separate worktree
(`P-067-drug-image-b04`), at B-04 at the time this build started.

## 1. Scope

Builds the real doctor workflow that consumes a `DoctorReviewRequest` after BUILD-42 (Safety/
Answerability handoff creation) or BUILD-43 (conversation-state-aware follow-up resolution) hands off:
queue → claim → activate → converse → resolve → bot resumes. **Non-goals, held to exactly**: no
changes to Safety policy (`backend/agents/v2/safety.py`), the Answerability Gate
(`backend/agents/v2/answerability.py`), or the follow-up classifier (`backend/agents/v2/follow_up.py`)
— confirmed via `git diff --name-only` before opening this PR. BUILD-45 (`AgentRun.intent` mismatch,
`_display_topic_from_raw` widening, the cold-turn `get_drug_info` gap documented in the BUILD-43
production-validation report) is explicitly not touched here.

## 2. Audit before code — findings that shaped the design

Real greps/reads before writing anything, per the standing rule:

- **`assign_doctor_review_request` is dead code for the general-queue use case.** It requires
  `doctor_id == resolve_approved_doctor(patient_id)` — but `create_doctor_review_request` only ever
  leaves a row `PENDING` when `resolve_approved_doctor` already returned `None` at creation time (no
  unique treating doctor). Calling `assign_doctor_review_request` on a genuinely-`PENDING` row
  therefore fails authorization for *any* doctor, by construction. Confirmed by reading both functions
  side by side, not assumed. Resolved by adding a new, separately-scoped `claim_doctor_review_request`
  (any active doctor may claim; the `.with_for_update()` row lock — not a treating-doctor check — is
  what prevents a double-claim) and leaving `assign_doctor_review_request` completely untouched (it may
  have another intended caller not yet built).
- **`Conversation`/`Message` (db/models.py) have zero real callers anywhere** — `grep -rln` across the
  whole backend. Entirely dead tables.
- **`ChatMessage` (`chat_messages`) is only written by the legacy `chat_routes.py`** (`save_chat_message`
  at its own line 326-327); `agent_v2_routes.py` never calls it. Agent V2 production traffic does not
  populate this table (consistent with the earlier, already-established finding that Agent V2 is the
  real production chat path). Neither existing table was a safe fit for a doctor/patient message
  thread scoped to one handoff episode — a new, narrow `doctor_review_message` table was added instead
  (§4).
- **`AuditLog` (`audit_log`) is legacy-utterance-shaped** (one row = one patient utterance,
  `BR-7.5`), not lifecycle-event-shaped. Rather than force-fit `HANDOFF_CLAIMED`/`HANDOFF_ACTIVATED`/
  etc. into a mismatched table, this build relies on `DoctorReviewRequest`'s own new lifecycle
  timestamp columns (`assigned_at`+`assigned_doctor_id`, `activated_at`, `resolved_at`+
  `resolved_by_doctor_id`, `cancelled_at`) plus the `doctor_review_message` rows themselves as the
  durable trail — every named event in the spec's own list is reconstructable from these: `HANDOFF_
  CREATED` = `created_at`, `HANDOFF_CLAIMED` = `assigned_at`, `HANDOFF_ACTIVATED` = `activated_at`,
  `DOCTOR_MESSAGE_SENT`/`PATIENT_MESSAGE_DURING_TAKEOVER` = `doctor_review_message` rows filtered by
  `sender_role`, `HANDOFF_RESOLVED` = `resolved_at`, `HANDOFF_CANCELLED` = `cancelled_at`.
- **A real regression in existing Admin Monitoring, found only by auditing what BUILD-44's own new
  `RESOLVED` status would break** — see §14.
- **A latent dedup gap in BUILD-42's own cross-run handoff-reuse check**, also found only by auditing
  what BUILD-44's new `ACTIVE` status would break: `agent_doctor_handoff.py`'s `_ACTIVE_HANDOFF_STATUSES
  = ("PENDING", "ASSIGNED")` did not include `ACTIVE`. In the real production route this is currently
  unreachable while ACTIVE (§7's own gate returns first), but the dedup check was not correct *on its
  own terms* — reachable directly (or by a future refactor), it would create a second, rival
  `DoctorReviewRequest` for a patient a doctor is already actively handling. Fixed defensively (added
  `ACTIVE`), with a regression test (§19).

## 3. Workflow state machine

Reuses `HandoffStatus` (`backend/services/doctor_handoff.py`), additive only:

```
PENDING --claim--> ASSIGNED --activate--> ACTIVE --resolve--> RESOLVED
   |                   |                     |
   +------------------cancel-----------------+--------------> CANCELLED
```

`ANSWERED` (the pre-existing "quick answer" terminal state, BUILD-10) is untouched and structurally
separate — a request only ever reaches `ANSWERED` via the old `answer_doctor_review_request` path,
never via this build's `activate`/`resolve` calls. `status` on `doctor_review_request` stays a plain
unconstrained `String` (matching every prior migration's own convention for this table), so adding
`ACTIVE`/`RESOLVED` needed no migration of its own beyond the new columns (§4).

## 4. Migration

`migrations/versions/0054_doctor_review_takeover.py` — additive:
- `doctor_review_request` gains `activated_at`, `resolved_at`, `resolved_by_doctor_id` (all nullable).
- New table `doctor_review_message` (`id`, `handoff_id` FK → `doctor_review_request.id`, `patient_id`,
  `sender_role` with `CHECK (sender_role IN ('PATIENT','DOCTOR','SYSTEM'))`, `actor_id` nullable,
  `content` Text, `created_at`), indexes on `(handoff_id, created_at)` and `patient_id`.

Verified `upgrade` → `downgrade` → `upgrade` clean against real local Postgres (see §16 for a real
incident this uncovered and how it was resolved).

## 5. Authorization

Every `/doctor/reviews/*` route: `require_role("doctor")` + `require_active_doctor` (new,
`backend/services/agent_doctor_takeover.py`) — a **fresh, per-request** `Account` lookup confirming
`role == "doctor"`, `status == "active"`, and `doctor_id` set and matching, never trusted from JWT
claims alone (same discipline `resolve_approved_doctor` already uses). Patient identity for the
patient-facing `/agent/v2/handoff/status` route is derived exclusively from `require_agent_patient_
access`, never a client-supplied `patient_id` alone.

## 6. Claim concurrency (real Postgres, no SELECT-then-UPDATE race)

`claim_doctor_review_request`/`activate_doctor_review_request`/`resolve_doctor_review_request`/
`cancel_doctor_review_request` all use `select(...).with_for_update()` — the row lock, not an
apparent PENDING/ASSIGNED read followed by a separate UPDATE. Verified with genuine concurrency
(`asyncio.gather` of two real HTTP calls through `ASGITransport`, real Postgres):
`test_two_doctors_claiming_the_same_request_concurrently_exactly_one_succeeds` — `sorted(statuses) ==
[200, 409]`, exactly one doctor assigned.

## 7. Takeover semantics — what suppresses the bot

`ACTIVE` is the **only** status that suppresses Agent V2 — `PENDING`/`ASSIGNED` do not (a claimed-but-
not-yet-activated request must not silently go quiet on the patient while a doctor might not open it
for a while). `get_active_takeover(db, patient_id=...)` (`doctor_handoff.py`) is the single source of
truth both the bot-suppression check and the doctor-facing status view use — by construction at most
one row can be `ACTIVE` for a given patient at a time (BUILD-42's own patient-level dedup already
guarantees this upstream). **Patient-scoped, not conversation-scoped** — matches BUILD-42's own dedup
scope; a patient starting a fresh `conversation_id` does not bypass an active takeover (verified,
`test_active_takeover_is_patient_scoped_not_conversation_scoped`).

The check runs in `run_agent_orchestration` (`agent_v2_routes.py`) **immediately after** resolving
`patient_id`/`conversation_id` — structurally before `OpenAIModelGateway.from_settings(settings)` is
ever constructed. This is not a policy choice enforced by convention; it is a code-order guarantee: 0
model/network calls while a doctor owns the conversation, verified via a real `AgentRun.model_calls ==
0` assertion against a genuinely-persisted row (`test_active_takeover_suppresses_bot_with_zero_model_
calls_and_persists_message`), not a mock.

## 8. Doctor messages

`send_doctor_message` (`doctor_review_routes.py`) requires `status == ACTIVE` and `assigned_doctor_id
== doctor_id`; persists the doctor's text **verbatim** — never rewritten, summarized, or passed
through the Main Model before delivery. Sender role is an explicit `DOCTOR` value on the row, never
faked as `ASSISTANT`.

## 9. Patient messages during ACTIVE

`_respond_with_doctor_takeover_active` (`agent_v2_routes.py`) persists the patient's message as a real
`PATIENT`-role `doctor_review_message` row, builds a minimal durable `AgentRun` (`status=
"DOCTOR_ACTIVE"`, `model_calls=0`, `cost_status="NOT_APPLICABLE"`), and returns a fixed safe
acknowledgement (`"Bác sĩ đang theo dõi cuộc trò chuyện này. Tin nhắn của bạn đã được gửi."`) — never
routed to Agent V2 orchestration, never silently dropped.

## 10. Resolve → resume

`resolve_doctor_review_request` (idempotent for a repeat call by the same resolving doctor) transitions
`ACTIVE → RESOLVED`; no automatic bot message is generated, and the patient's canonical
`ConversationState` is left completely intact (untouched by this build's own resolve path) — the next
real patient turn goes through ordinary Agent V2 orchestration exactly as before the takeover began,
verified end-to-end in the local E2E (§17, step 14: a real model call, a real non-empty reply, `status
!= "DOCTOR_ACTIVE"`).

## 11. Safety-during-ACTIVE-takeover — documented architecture decision, not silently implemented

While a doctor holds an `ACTIVE` takeover, a patient's message is persisted and acknowledged **before**
it ever reaches Safety, the Answerability Gate, or the router (§7/§9) — this is a genuine, deliberate
trade-off, not an oversight: **known limitation**, documented here rather than casually "fixed" by
routing patient messages through Safety-only-evaluation-without-a-bot-reply (out of this build's scope
— that would be new Safety-adjacent code this build's own non-goals forbid touching). The Safety Domain
is never downgraded, weakened, or bypassed for any message that does *not* arrive during an ACTIVE
takeover; this limitation applies only to the narrow, human-supervised window where a doctor is already
directly reading the patient's messages in real time. If a genuinely acute message arrives during that
window, the doctor is the one reading it live — this is the same trust model as any live human-staffed
chat handoff, not a gap this build introduces silently.

## 12. Episode scope

Patient-level, not conversation-level: `get_active_takeover` looks up by `patient_id` only. Chosen to
match BUILD-42's own cross-run/patient-level dedup scope (`AuthorizedDoctorHandoffAdapter`) rather than
introduce a second, narrower notion of "episode" this build would then have to keep in sync with it.

## 13. API endpoints / frontend

`backend/api/doctor_review_routes.py`: `GET /doctor/reviews` (queue, `status`/`handoff_type`/
`assigned_to_me` filters, Safety-first-then-oldest sort — a display-ordering choice reusing Safety's
own upstream urgency call, not a new medical-urgency judgment), `GET /doctor/reviews/{id}` (detail +
thread), `POST .../claim`, `.../activate`, `.../messages`, `.../resolve`, `.../cancel`. Patient-facing
`GET /agent/v2/handoff/status` returns only `PATIENT`/`DOCTOR` messages, never a raw `SYSTEM` row.

Minimal frontend (`frontend/src/app/doctor/reviews/`): a queue page (filters, claim button) and a
per-handoff workspace page (claim/activate/message/resolve, message thread), proxied through new
`app/api/doctor/reviews/*` Next.js routes following this repo's existing proxy convention
(`forwardAuthorization` helper, matching `app/api/accounts/authorization.ts`). Nav entry added to
`app/doctor/layout.tsx`. **Real-time, honestly**: no WebSocket exists for this workflow; the workspace
page polls every 5s while `status === "ACTIVE"` — documented in the page's own comment, not presented
as real-time.

## 14. Admin Monitoring — extension, and a real regression this build's own new status would have caused

New `backend/services/agent_doctor_handoff_metrics.py` + `GET /admin/monitoring/doctor-queue`
(`admin_monitoring_routes.py`, admin-only): status counts, handoff-type counts, time-to-claim/activate/
resolve averages — every average is `{value, sample_count, status: AVAILABLE|NOT_APPLICABLE}`, never a
fabricated 0 for an empty sample. An `UNCERTAINTY`/`USER_REQUEST` row is never counted as a Safety event
here (this module never queries `AgentSafetyEvent` at all).

**Regression found and fixed during audit, not merely "extended":** `agent_safety_monitoring.py`'s
`_HANDOFF_RESOLVED_STATUSES` was `{"ANSWERED", "CANCELLED"}` and `_compute_live_status`'s
`resolved_at` fallback chain was `answered_at or cancelled_at` — neither knew about this build's new
`RESOLVED` status/`resolved_at` column. Without the fix, a **SAFETY**-type handoff a doctor fully
resolved through this build's new claim→activate→resolve workflow would have shown in existing Admin
Monitoring as *permanently unresolved* — a real regression this build would otherwise have silently
introduced into pre-existing, already-shipped code. Fixed additively (`RESOLVED` added to the status
set; `resolved_at` added to the fallback chain); a new regression test
(`test_safety_metrics_summary_resolved_via_build44_doctor_workflow_counts_as_resolved`) locks the fix
in.

## 15. Golden/Evaluation scope

Deferred, matching BUILD-42/43's own precedent: this workflow has no model-generated text of its own
to grade (the bot reply during takeover is a fixed string; doctor messages are human-authored, never
passed through the Main Model) — there is no new model-output surface for a Golden case to exercise.

## 16. A real incident found and resolved during this build: migration revision collision with Track B

Fetching `origin/main` mid-build surfaced that Track B's `feature/drug-image-b04-visual-retrieval`
(merged as PR #132, `fa581ca`) had added `migrations/versions/0053_drug_image_embeddings.py` with
`revision="0053"`, `down_revision="0052"` — the **same** revision id BUILD-44 had independently used
for its own migration, both branched from the same `0052` head before either merged. A genuine Alembic
branch collision (two heads on the same parent), not a Git text conflict — `backend/db/models.py`
(touched by both branches) merged cleanly at the text level.

Per the standing "STOP-and-report on migration conflicts" rule, this was surfaced to the user rather
than silently resolved. Resolution (user-directed): renamed BUILD-44's migration to `0054`,
`down_revision="0053"`, chaining after Track B's now-merged migration; content/logic unchanged.
`origin/main` was merged into this branch first so the real `0053` file existed locally. The shared
local Postgres DB was then found to be in an inconsistent state — its `alembic_version` was stamped
`"0053"` from an *earlier, pre-rename* verification run of BUILD-44's own migration under the old
revision id, while Track B's real `0053` schema (a `drug_image_embedding` table) had never actually
been applied to it. Left as-is, a fresh `alembic upgrade head` would have silently skipped Track B's
real changes. Reconciled by manually reverting BUILD-44's old schema objects via raw SQL and resetting
`alembic_version` to a true `0052`, then running a genuine `alembic upgrade head` (0052 → 0053 Track B
→ 0054 BUILD-44) and a full `downgrade` → `upgrade` cycle — both clean. This incidentally closed a
pre-existing gap: Track B's own `0053` migration had never actually been verified against this shared
local DB before. Full BUILD-44 test suite (58 tests) and the local E2E script (32/32 checks) re-run and
re-verified passing against the reconciled schema. Track B's own files were touched **only** by the
merge commit (`19ef763`) — confirmed via `git diff --name-only 6f15deb 4fbd2a9` (BUILD-44's own feat
commit) showing zero Track B files.

## 17. Local E2E (real Postgres, real HTTP-equivalent calls, real model calls)

`scripts/agent_v2/build44_doctor_takeover_local_e2e.py` — three scenarios, **32/32 checks passed**:

- **Core/Uncertainty (15 steps)**: seeds `ConversationState.answerability_attempt_count =
  MAX_CLARIFICATION_ATTEMPTS` (the same proven, 0-model-call `test_e_repeated_clarification_unresolved_
  escalates_to_doctor` recipe from BUILD-42's own suite) → real `"Tôi bị đau đầu"` turn → `NEED_DOCTOR`
  → real `PENDING` `DoctorReviewRequest`, `handoff_type=UNCERTAINTY` → claim → activate → patient
  message during ACTIVE (0 model calls, persisted) → doctor reads → doctor responds (verbatim) →
  patient reads (order: PATIENT then DOCTOR) → resolve → `get_active_takeover` → `None` → **real**
  patient turn resumes (`"Paracetamol dùng để làm gì?"`, real model call, real non-empty reply, `status
  != DOCTOR_ACTIVE`) → confirmed zero `AgentSafetyEvent` rows for this handoff throughout.
- **Safety**: `"Tôi vừa nôn ra máu"` → real Safety-Domain-sourced handoff, `handoff_type=SAFETY` →
  confirms a real `AgentSafetyEvent` **was** recorded for the trigger itself, and that claim/activate/
  resolve create **zero additional** `AgentSafetyEvent` rows.
- **Explicit User Request**: `"Tôi muốn nói chuyện với bác sĩ."` → `handoff_type=USER_REQUEST`, 0 model
  calls, zero `AgentSafetyEvent` rows, then a full claim→activate→resolve pass.

A genuine script bug was found and fixed on the first run (not the product): a single frozen
`datetime.now(UTC)` reused across every simulated "server call" put a later real action (the patient's
live-stamped ACTIVE message) before an earlier script call in `created_at` order — fixed by calling
`datetime.now(UTC)` fresh at each doctor-action call site, matching what the real route itself always
does (SS19: server timestamp only, never client-supplied).

## 18. Concurrency test matrix (spec A–F)

| Scenario | Test | Result |
|---|---|---|
| A: two doctors claim the same PENDING request concurrently | `test_two_doctors_claiming_the_same_request_concurrently_exactly_one_succeeds` (real Postgres, `asyncio.gather`) | exactly one 200, one 409 |
| B: doctor resolves while a patient message hits the same handoff concurrently | `test_doctor_resolve_and_patient_message_persist_concurrently_no_corruption` (real Postgres, genuine OS-thread concurrency via `asyncio.to_thread`) | both legitimate orderings verified internally consistent; the patient's message is never lost; stable across 5 repeated runs |
| C: patient sends two messages during ACTIVE | `test_two_patient_messages_during_active_takeover_both_persisted_zero_bot_replies_in_order` | both persisted, in order, zero bot replies |
| D: sequential duplicate claim retry | `test_sequential_duplicate_claim_retry_rejected_not_crashed` | clean 409, not a crash; handoff stays assigned to the original doctor |
| E: repeated activate by the same doctor | `test_repeated_activate_is_idempotent` | idempotent, 200 both times |
| F: repeated resolve by the same doctor | inside `test_full_claim_activate_message_resolve_workflow` | idempotent, 200 both times |

## 19. Tests (this build)

- `tests/test_agent_v2_doctor_takeover.py` — 8 tests, SQLite-file-based, real independent sessions per
  call (same discipline as `test_agent_v2_transaction_durability.py`): `get_active_takeover` status
  filtering (3), bot suppression with a real `model_calls == 0` assertion, no duplicate handoff, message
  ordering, patient-scope (not conversation-scope), cross-patient isolation.
- `tests/test_api/test_doctor_review_routes.py` — 10 tests, real Postgres, real minted JWTs, real
  `ASGITransport` HTTP calls: authorization (patient/caregiver/unauthenticated denied on every route),
  cross-doctor/cross-patient isolation, the full claim→activate→message→resolve workflow (including a
  409 before ACTIVE), idempotent activate, the two concurrency scenarios (A, B).
- `tests/test_api/test_admin_monitoring_routes.py` — 2 new tests: real seeded-row expected-count deltas
  (SAFETY/UNCERTAINTY/USER_REQUEST counted correctly, never folded together), and real timing averages
  from a genuine claim→activate→resolve pass with known offsets (found and fixed a real test-isolation
  bug on first run — see §20).
- `tests/test_agent_v2_build34_safety_monitoring.py` — 1 new regression test locking in the §14 fix.
- `tests/test_agent_v2_doctor_handoff.py` — 1 new regression test locking in the §2 dedup fix (an
  `ACTIVE` handoff is reused, not duplicated, by `AuthorizedDoctorHandoffAdapter.create`).

**22 tests newly authored for this build** (8 + 10 + 2 + 1 + 1 above). Re-running the full touched test
files (new tests together with every pre-existing test already in them, since a new addition to a
shared file can regress a neighbor) gives **66 passed, 0 failed** — this is the honest total, not
inflated by counting pre-existing tests as "BUILD-44-specific."

## 20. A real test-isolation bug found and fixed (not a product bug)

`test_doctor_queue_metrics_time_to_claim_and_resolve_from_real_workflow`'s first run asserted
`time_to_claim_avg_seconds == 60.0` but got `10.02s` — the `/admin/monitoring/doctor-queue` endpoint has
no `patient_id` filter (it is a genuine cross-patient aggregate), and the test's `date_from`/`date_to`
window spanned a full day anchored at "today" — wide enough to also average in leftover rows this same
session's own earlier E2E script runs had left in the shared local Postgres table. Fixed by anchoring
the test's `created_at` in the past (2020) with a tight one-hour window, which cannot collide with any
real same-day data. Confirms `doctor_queue_metrics` itself was correct all along; the bug was in test
isolation.

## 21. No-Judge-control invariant

No code path in this build derives urgency, routing, or authorization from an LLM Judge score.
`_TYPE_SORT_RANK` (queue display order) is a fixed, deterministic mapping from `HandoffType` (itself
already deterministic — `handoff_type_for`, BUILD-42) — not a Judge-derived priority.

## 22. Regression sweep

- BUILD-44 targeted: 22 newly-authored tests, 66/66 passed across the full touched test files (§19).
- BUILD-42 Answerability + BUILD-43 follow-up + orchestrator: `test_agent_v2_build42_answerability.py`,
  `test_agent_v2_follow_up.py`, `test_agent_v2_build43_follow_up_resolution.py`,
  `test_agent_v2_orchestrator.py` — 122/122 passed.
- Safety/router/schedule/admin-safety/doctor-handoff: `test_agent_v2_safety.py`,
  `test_agent_v2_safety_occurrence_binding.py`, `test_agent_v2_safety_policy_review_workflow.py`,
  `test_safety.py`, `test_agent_v2_build40_router_taxonomy.py`, `test_agent_v2_router_remediation.py`,
  `test_agent_v2_time_aware_schedule.py`, `test_today_schedule_node.py`, `test_v2_dose_safety_http.py`,
  `test_api/test_admin_safety_routes.py`, `test_agent_v2_doctor_handoff.py`,
  `test_agent_v2_doctor_handoff_postgres.py`, `test_agent_v2_transaction_durability.py` — 179 passed, 1
  pre-existing skip (`BUILD10_TEST_DATABASE_URL` not set in this env — unrelated to BUILD-44).
- `ruff check` on every changed/new BUILD-44 file: clean.
- Frontend: `eslint` clean, `tsc --noEmit` clean, `next build` clean (all new routes/pages compile and
  are listed in the build's own route manifest).
- Full repo-wide `pytest tests/` (excluding two pre-existing, environment-only collection failures —
  `cv2`/`numpy` not installed in this backend venv, `tests/vlm_demthuoc/*` and one
  `photo_verification` VLM-prompt test, unrelated to this build): **2070 passed, 11 failed, 9 skipped**
  (668 warnings, 10m26s). The 11 failures were independently re-verified — not assumed pre-existing —
  by running the exact same 11 tests against a disposable worktree checked out clean from `origin/main`
  (`fa581ca`, the commit this branch's own merge came from): **all 11 fail identically there**, with the
  same assertion messages (`test_agent_v2_long_term_memory.py` ×3, `test_api/test_auth_routes.py` ×4,
  `test_api/test_patient_routes.py::test_doctor_search_still_gets_full_fields_regression`,
  `test_api/test_security_authz.py::test_get_current_user_valid_jwt`,
  `test_chat_history_e2e.py::test_patient_role_cannot_read_or_hide_another_patients_chat_history`,
  `test_retrieval_sql.py::test_word_similarity_threshold_guc_is_set_not_just_similarity_threshold`) —
  confirmed pre-existing and environment-related (SMTP/token-flow, `pg_trgm` GUC configuration, JWT
  fixture drift), zero relation to BUILD-44's own changes. None of the 11 touch any file this build
  modified. The 9 skips are all env-gated opt-in Postgres tests (`BUILD10_TEST_DATABASE_URL`,
  `BUILD12_TEST_DATABASE_URL`, `BUILD22_TEST_DATABASE_URL`, `BUILD42_TEST_DATABASE_URL`,
  `DB4I_TEST_DATABASE_URL`, `APP5_TEST_DATABASE_URL` unset in this dev env) plus 2 demo-seed-data-gated
  tests, none new to this build.

## 23. Release Gate

```text
BUILD-44: PASS

BASELINE VERIFIED: PASS                (6f15deb, origin/main at start, BUILD-43 production-validated)
PARALLEL WORKTREE ISOLATION: PASS      (dedicated worktree/branch)
TRACK B UNTOUCHED BY BUILD-44'S OWN COMMITS: PASS  (git diff 6f15deb..4fbd2a9 touches zero Track B files;
                                                     Track B files entered only via the origin/main merge)
MIGRATION COLLISION WITH TRACK B: FOUND AND RESOLVED (§16, user-directed renumber to 0054)

AUDIT BEFORE CODE: PASS                (§2 -- assign_doctor_review_request dead-code finding,
                                         Conversation/Message/ChatMessage/AuditLog table-fit findings)

WORKFLOW STATE MACHINE: PASS           (PENDING/ASSIGNED/ACTIVE/RESOLVED/CANCELLED, ANSWERED untouched)
MIGRATION UPGRADE/DOWNGRADE/UPGRADE: PASS  (verified against reconciled real local Postgres, §16)

AUTHORIZATION FAIL-CLOSED: PASS        (require_active_doctor, fresh per-request Account check)
CLAIM CONCURRENCY (REAL POSTGRES): PASS (scenario A, exactly one winner)
NO SELECT-THEN-UPDATE RACE: PASS       (with_for_update() on every transition)

ACTIVE-ONLY BOT SUPPRESSION: PASS      (PENDING/ASSIGNED do not suppress, verified)
ZERO MODEL CALLS DURING TAKEOVER: PASS (structural -- gateway constructed after the check; empirical --
                                         real AgentRun.model_calls == 0)
PATIENT-SCOPED NOT CONVERSATION-SCOPED: PASS (fresh conversation_id still suppressed)
CROSS-PATIENT ISOLATION: PASS

DOCTOR MESSAGES NEVER REWRITTEN: PASS  (persisted verbatim, explicit DOCTOR sender role)
PATIENT MESSAGES DURING TAKEOVER PERSISTED, NOT ROUTED TO AGENT V2: PASS
NO FAKE ASSISTANT-ROLE MESSAGES: PASS

RESOLVE -> BOT RESUME: PASS            (real model call, real reply, real E2E step 14)
CONVERSATIONSTATE UNTOUCHED BY RESOLVE: PASS
SAFETY-DURING-ACTIVE-TAKEOVER: DOCUMENTED LIMITATION, NOT SILENTLY IMPLEMENTED (§11)

NO FAKE AgentSafetyEvent FOR UNCERTAINTY/USER_REQUEST HANDOFFS: PASS (E2E + unit tests)
REAL AgentSafetyEvent STILL RECORDED FOR SAFETY HANDOFFS: PASS
ADMIN MONITORING REGRESSION FOUND AND FIXED: PASS (§14 -- RESOLVED status now counted correctly)
CROSS-RUN DEDUP GAP FOUND AND FIXED: PASS (§2 -- ACTIVE handoffs now reused, not duplicated)
NEW ADMIN DOCTOR-QUEUE METRICS: PASS   (N/A != 0 discipline, real expected-count + timing tests)
NO JUDGE-DERIVED PRIORITY/AUTHORIZATION: PASS

CONCURRENCY MATRIX A-F: PASS           (§18, all 6 scenarios)
LOCAL E2E (CORE/SAFETY/USER_REQUEST): PASS  (32/32 checks, real Postgres, real model calls)

FRONTEND: ESLINT PASS, TSC PASS, NEXT BUILD PASS
REAL-TIME: HONESTLY DOCUMENTED AS POLLING, NOT WEBSOCKET

BUILD-44 TARGETED TESTS: 22 NEW, 66/66 PASS (full touched test files, new + pre-existing)
BUILD-42/43 REGRESSION: 122/122 PASS
SAFETY/ROUTER/SCHEDULE/DOCTOR-HANDOFF REGRESSION: 179/180 PASS (1 pre-existing env-gated skip)
RUFF (all changed/new files): PASS
GOLDEN: N/A (deferred, reasoned -- §15, no new model-output surface)
FULL REPO REGRESSION: PASS             (2070 passed, 11 failed, 9 skipped -- all 11 failures independently
                                         reproduced identically on a disposable clean origin/main worktree,
                                         confirmed pre-existing and unrelated, §22)

READY FOR PR REVIEW: YES
READY TO MERGE/DEPLOY: NO -- awaiting human review per standing process
READY TO START BUILD-45: NO -- pending this PR's review/merge
```

## Explicit non-actions per this build's own STOP condition

Per spec: after audit/implementation/migration/tests/concurrency-tests/local-E2E/regression/report,
this build stops here. Not done in this session, by design: no merge, no deploy, no BUILD-45 work
(`AgentRun.intent` mismatch, `_display_topic_from_raw` widening, cold-turn `get_drug_info` gap — all
BUILD-43-documented, separate follow-ups), no Track B changes beyond the unavoidable `origin/main`
merge (§16), no hot-fixing of any other pre-existing, unrelated limitation encountered along the way.
