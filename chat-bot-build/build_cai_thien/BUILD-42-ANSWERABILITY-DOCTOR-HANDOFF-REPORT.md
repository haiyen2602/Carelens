# BUILD-42 — Answerability Gate & Doctor Handoff

Adds a structured, deterministic decision (ANSWERABLE / NEED_MORE_INFO /
NEED_DOCTOR) between existing tool/RAG/model evidence and the final reply,
so the chatbot can escalate a non-emergency, unresolved question to a
human doctor — a capability that did not exist before this build (the only
prior escalation path was Safety-Domain-triggered, for acute clinical
risk). Does **not** build the full doctor live-chat takeover workflow
(BUILD-44) and does **not** fix CANDIDATE-02 (BUILD-43).

## 1. Audit before code

Full audit performed via a dedicated read-only research pass before any
code was written; see the 9 numbered questions and file:line evidence in
this build's own working notes. Condensed findings:

- **Exactly one physical `DoctorReviewRequest(` construction site** in the
  whole backend (`backend/services/doctor_handoff.py::create_doctor_review_request`),
  reached through exactly one orchestrator call site
  (`AgentOrchestrator._create_handoff`), itself reached only when a
  `SafetyDecision.outcome is SafetyOutcome.HANDOFF_REQUIRED`. Five router/
  Safety paths (MISSED_DOSE/DELAYED_DOSE, dose-unresolved,
  ACUTE_DANGER_ESCALATION, POSSIBLE_OVERDOSE, and the pre-existing
  `DOCTOR_REVIEW` keyword intent) all funnel through this ONE gate, which
  **hard-asserts** a `SafetyDecision` — `DoctorHandoffGateway.create` raises
  if `safety.outcome is not SafetyOutcome.HANDOFF_REQUIRED`.
- **No non-safety review path exists today.** `DOCTOR_REVIEW` (a dosage-
  change/stop-medication keyword match, no clinical risk assessment at
  all) is forced through the exact same Safety-shaped machinery purely to
  satisfy that gate's assertion — confirmed by reading `orchestrator.py`'s
  synthetic `SafetyDecision(reason_code="DOCTOR_REVIEW_REQUESTED", ...)`
  construction for this intent.
- `DoctorReviewRequest.status` is `PENDING | ASSIGNED | ANSWERED | CANCELLED`
  (a plain, non-DB-enum-constrained `String` column). No `priority`/`type`
  column exists — only `reason_code` (free string) and `risk_disposition`
  (until this build, always `"HANDOFF_REQUIRED"`, since that was the only
  value any producer ever passed).
- **Duplicate-handoff prevention today is per-agent-run only**
  (`idempotency_key = f"agent-run:{agent_run_id}:handoff"`, deduped via a
  unique DB index) — confirmed via direct code read that **no query
  anywhere checks for an existing PENDING/ASSIGNED request for the same
  patient before creating a new one.** Two separate messages from the same
  patient would each get their own row today.
- Authorization on the creation path is `require_agent_patient_access`
  (the same fail-closed boundary every other Agent V2 tool read already
  uses). No doctor-facing read/assign/answer endpoint exists at all yet
  (`assign_doctor_review_request`/`answer_doctor_review_request` have zero
  API callers — out of this build's scope, belongs to BUILD-44).
- `EvaluationPath.HANDOFF` already exists in the enum (`evaluation_v2.py`)
  with a docstring describing exactly "a standalone doctor-review handoff
  without a safety decision" — but was **unreachable/dead code** under the
  current call graph, since every real handoff always also has a non-None
  `safety_decision` today.
- `GROUNDING_FAILURE` (Cluster B, BUILD-38) replaces a reply's text but
  keeps `status=COMPLETED` and never escalates. `ContextResolutionStatus.
  AMBIGUOUS/NO_CONTEXT` (CANDIDATE-02-adjacent) and the PERSONAL_SYMPTOM/
  MEDICATION_DOSE_SAFETY triage clarifications (`_clinical_clarification_reply`)
  ask the same fixed question forever with no bound.
- No `attempt_count`/retry-counter field existed anywhere in
  `ConversationState` (`backend/agents/v2/conversation_state.py`) — confirmed
  via grep before adding one.

## 2. Existing handoff architecture (post-audit summary)

```
needs_handoff (Safety-sourced only, pre-BUILD-42)
  -> AgentOrchestrator._create_handoff
  -> DoctorHandoffGateway.create (asserts SafetyDecision)
  -> AuthorizedDoctorHandoffAdapter.create
  -> create_doctor_review_request (the one real INSERT)
```

BUILD-42 adds a **second, parallel** entry into the same final two layers,
never through the Safety-asserting gate:

```
AnswerabilityDecision.outcome == NEED_DOCTOR
  -> AgentOrchestrator._create_answerability_handoff
  -> DoctorHandoffGateway.create_for_uncertainty (NO SafetyDecision required)
  -> AuthorizedDoctorHandoffAdapter.create (risk_disposition == "UNCERTAINTY_HANDOFF" branch)
  -> create_doctor_review_request (the SAME function, SAME table)
```

`DoctorReviewRequest` is reused exactly as-is — **zero migration**. The only
schema-adjacent additions are two new *string values* on existing columns
(`risk_disposition="UNCERTAINTY_HANDOFF"`, and `reason_code` values from
the new `AnswerabilityReasonCode` enum), which the column's own type
(a plain `String`, confirmed in the audit) already accepts without change.

## 3. Answerability taxonomy

New module `backend/agents/v2/answerability.py`:

```python
class AnswerabilityOutcome(StrEnum):
    ANSWERABLE, NEED_MORE_INFO, NEED_DOCTOR

class AnswerabilityReasonCode(StrEnum):
    GROUNDING_INSUFFICIENT, UNRESOLVED_ENTITY, AMBIGUOUS_MEDICAL_REQUEST,
    MISSING_REQUIRED_CONTEXT, REPEATED_CLARIFICATION,
    UNSUPPORTED_MEDICAL_QUESTION, EXPLICIT_DOCTOR_REQUEST,
    TOOL_DATA_INSUFFICIENT, MAX_ATTEMPTS_REACHED

@dataclass(frozen=True)
class AnswerabilityDecision:
    outcome: AnswerabilityOutcome
    reason_code: AnswerabilityReasonCode | None
    provenance: str
    attempt_count: int
```

Only the reason codes actually reachable by real, observable evidence are
ever assigned (`AMBIGUOUS_MEDICAL_REQUEST`/`TOOL_DATA_INSUFFICIENT` are
defined in the enum per the spec's own required list but are not currently
assigned by any code path — no invented state).

`handoff_priority`/`confidence` fields from the spec's suggested shape were
**not** added: `handoff_priority` has no real signal to derive from today
(every Answerability-Gate handoff is uniformly non-emergency by
definition — see SS4/SS9) and adding a fabricated priority value would
violate the "no fake metrics" standing rule. `AgentHandoffResult.status`
already carries the real, durable state instead.

## 4. Decision policy — no LLM confidence, only structured evidence

Every `AnswerabilityDecision` is derived from already-computed evidence
that existed in the pipeline before this build:

| Signal | Source |
|---|---|
| Explicit doctor request | deterministic regex on raw message text (`is_explicit_doctor_request`) |
| Grounding failure | `result.tool_results`/`citations` empty (existing `_enforce_medical_grounding` condition) |
| Repeated clarification | `ConversationState.answerability_attempt_count` (new, durable) |
| Intent category | existing `OrchestrationIntent`/`_GENERAL_MEDICAL_DECLINE_INTENTS` |

**Zero model calls** anywhere in `answerability.py`. **Zero "LLM says
confidence is low"** branches anywhere in this build's diff (verified —
`grep`ed the full diff for any new model-gateway call inside the
Answerability Gate's own code path; none exists).

## 5. Safety handoff vs uncertainty handoff — kept structurally distinct

- **Safety Gate always runs first, unchanged.** The explicit-doctor-request
  check is placed in `run()` **after** `needs_handoff`/`is_safety_blocked`
  are fully computed from the existing Safety pipeline, guarded by
  `not needs_handoff and not is_safety_blocked` — a message that is BOTH a
  real Safety trigger (e.g. an overdose report) AND happens to mention
  wanting a doctor is Safety's, by construction, not inference (see test
  `test_explicit_doctor_request_does_not_override_active_overdose_safety`).
- **`DoctorHandoffGateway.create_for_uncertainty` never touches the Safety
  Domain or records an `AgentSafetyEvent`** (contrast: `create` always runs
  after `CheckpointedSafetyGateway.record`, which is what produces that
  row). This is the actual mechanism that keeps `safety_trigger_rate`
  unaffected (SS17) — not a metric-layer filter bolted on afterward.
- `handoff_type` (SAFETY / UNCERTAINTY / USER_REQUEST) is **derived, never
  a new persisted column** — `answerability.handoff_type_for(reason_code,
  risk_disposition)`: `risk_disposition != "UNCERTAINTY_HANDOFF"` → SAFETY;
  else `EXPLICIT_DOCTOR_REQUEST` → USER_REQUEST; else UNCERTAINTY.
  Confirmed via a dedicated unit test (`test_handoff_type_for_derivation`).

## 6. Grounding failure policy (SS23)

Explicitly **not** `if GROUNDING_FAILURE: handoff()`. The existing
`_GENERAL_MEDICAL_DECLINE_INTENTS` split (BUILD-38 Cluster B) already
separates "general educational question" (GENERAL_MEDICAL_INFORMATION,
UNKNOWN_OR_AMBIGUOUS) from "drug/prescription/dose-specific" intents —
this build reuses that exact, already-audited split as the medical-
specificity signal:

- **General educational grounding failure**: completely untouched — the
  existing honest decline (`_UNGROUNDED_GENERAL_MEDICAL_DECLINE_REPLY`)
  stays, `status=COMPLETED`, no Answerability Gate involvement, no handoff.
  Confirmed via `test_g_general_grounding_failure_does_not_auto_handoff`.
- **Personalized-medication-shaped grounding failure**
  (DRUG_INFORMATION/PRESCRIPTION_INFORMATION/DOSE_STATUS): now routed
  through `evaluate_grounding_answerability` — first occurrence in a
  conversation → NEED_MORE_INFO (a focused clarification, not the old
  fixed decline); a second occurrence in the same conversation → NEED_DOCTOR.

## 7. Clarification policy — bounded, not unbounded

`MAX_CLARIFICATION_ATTEMPTS = 2` (`answerability.py`). Chosen because 1
would hand off after the very first clarification question ever asked —
never giving the user a real chance to answer it — while the spec's own
example (SS8) uses exactly 2 bounded attempts before escalating. Applied
identically to two pre-existing clarification code paths:

1. **Grounding-failure clarification** (new, SS6 above) — first attempt
   text is a focused ask keyed to the actual gap (`_NEED_MORE_INFO_REPLIES`,
   e.g. "Bạn đang dùng thuốc tên đầy đủ và hàm lượng bao nhiêu mg?"), not
   a generic "can you provide more information?".
2. **PERSONAL_SYMPTOM/MEDICATION_DOSE_SAFETY triage clarification**
   (`_clinical_clarification_reply`, pre-existing since BUILD-29F) — the
   FIRST-attempt text is completely unchanged; only the previously-
   unbounded "ask forever" behavior is now bounded.

`ConversationState` gained two new fields (`answerability_attempt_count`,
`last_answerability_reason`), persisted in the existing durable
`AgentRun.metadata_json` JSON blob (no migration — the store already
serializes this state as JSON; see `AgentConversationStateStore`).
`transition_state`'s new `answerability_attempt_count` parameter defaults
to 0 (reset), and `agent_v2_routes.py` only passes a nonzero value when
THIS turn's own `OrchestrationResult.answerability_decision.outcome` was
NEED_MORE_INFO — every other turn (answered, topic switch, or NEED_DOCTOR)
resets the counter.

**Real multi-turn discovery** (found only by local E2E, not by unit
tests): `classify_intent()` is stateless per message, so a generic
follow-up like "tôi không biết" does NOT stay classified as
PERSONAL_SYMPTOM turn-over-turn — it independently routes to
UNKNOWN_OR_AMBIGUOUS's own, separately-tracked grounding-failure path
instead. This is expected, pre-existing router behavior (unrelated to
BUILD-42), not a bug — a realistic user re-describing the same symptom
("tôi bị đau đầu" again) is what reliably exercises the SAME clarification
path, and that is what the local E2E script uses.

## 8. Duplicate handoff prevention (SS12)

New: `AuthorizedDoctorHandoffAdapter.create` queries for an existing
`PENDING`/`ASSIGNED` `DoctorReviewRequest` for the same `patient_id`
**before** creating a new one — but **only** when
`command.risk_disposition == "UNCERTAINTY_HANDOFF"`. A Safety-sourced
command's `risk_disposition` is always `"HANDOFF_REQUIRED"`, so this new
branch never fires for — and never changes — the pre-existing Safety path
(confirmed via `test_dedup_is_scoped_to_uncertainty_handoffs_only_not_safety`,
and via real local E2E: two real Safety-triggered messages, acute danger
then overdose, in the same conversation, each still correctly create their
own row).

Verified via real local E2E (§13): a repeated clarification exhausted on
turn 3 created ONE row; an explicit doctor request sent immediately after,
in the same conversation, reused that SAME row (`handoff_id` identical,
`created: false`) rather than duplicating it — with `handoff_type` in the
response correctly reflecting `USER_REQUEST` for the reusing request even
though the underlying row's own `reason_code` is `REPEATED_CLARIFICATION`
(the response's `handoff_type` describes what triggered THIS turn's
match, not the original row's provenance — a deliberate, documented
choice, not a bug: the row itself keeps its true original reason_code).

## 9. DoctorReviewRequest reuse

No new table. `HandoffContextSource` (`handoff.py`) and the parallel
domain-layer `VerifiedContextSource` (`doctor_handoff.py`) both gained one
new value, `ANSWERABILITY_GATE` — additive-only. **A real integration bug
was found and fixed here via local E2E, not code review**: these two
enums are kept in sync only by convention (one crosses into the other via
`agent_doctor_handoff.py::_context_ref`); the second enum was initially
missed, causing a raw `ValueError` the first time a real
`HandoffContextRef` was actually converted (my own orchestrator-level unit
tests used a pure in-memory stub domain, and my adapter-level unit tests
passed an empty `verified_context_refs` tuple — neither exercised this
conversion for real). Fixed, and a new regression test
(`test_gateway_create_for_uncertainty_end_to_end_with_real_context_ref`)
now exercises the real gateway + real adapter + real DB with a populated
ref, specifically to keep this class of bug caught by the fast test suite
going forward.

**A second real bug found the same way**: the checkpoint/resume system's
`record_handoff_created`/`handoff_idempotency_key` (`agent_checkpoint.py`)
both hard-require `checkpoint.safety_disposition == "HANDOFF_REQUIRED"` —
a real Safety Domain artifact this build's whole point is to not fabricate
for an uncertainty handoff. `finish_run` (used by the generic
`CheckpointedTerminalStateRecorder`) also explicitly rejects a
`HANDOFF_CREATED` status outright. There is structurally no existing, safe
way to checkpoint-terminalize this exact status without touching
Safety-coupled code. **Resolution**: `_create_answerability_handoff`
never routes through the checkpoint system at all — it calls
`DoctorHandoffGateway.create_for_uncertainty` directly. See SS16 (Known
Limitations) for the accepted trade-off this creates.

## 10. Observability

- `OrchestrationResult.answerability_decision: AnswerabilityDecision | None`
  — durable per-run evidence of the gate's decision, `None` for the
  overwhelming majority of ordinary ANSWERABLE turns.
- Telemetry events: `agent_answerability.handoff_created` (reason_code
  attribute) on every Answerability-Gate handoff creation, using the same
  `TraceComponent.HANDOFF` component the existing Safety-handoff telemetry
  uses — no chain-of-thought, only the reason_code enum value.
- `AgentV2OrchestrateResponse` gained two new user-safe fields:
  `handoff_required: bool` and `handoff_type: str | None` (SAFETY /
  UNCERTAINTY / USER_REQUEST) — no raw internal reasoning, risk score, or
  Judge output exposed, matching SS14's explicit "do not expose" list.
- `EvaluationPath.HANDOFF` (pre-existing, previously dead/unreachable
  enum value) is now genuinely reachable for the first time — confirmed
  directly: an `OrchestrationResult` with a populated `handoff_result` and
  `safety_decision=None` classifies as `HANDOFF` under the existing
  `dispatch_evaluation` logic with **zero changes to evaluation_v2.py**.
  NEED_MORE_INFO replies land in pre-existing buckets (`TRIAGE`/
  `MEDICATION_DOSE_SAFETY`/`GENERAL_MODEL`, depending on intent) exactly as
  the pre-BUILD-42 fixed-reply clarifications already did — also zero
  changes needed, confirmed via direct interpreter checks (see §16 below).

## 11. Admin Monitoring impact

**No backend/frontend changes made.** Audited BUILD-36's existing
`/admin/safety/*` routes and `agent_safety_monitoring.py`: they read
`AgentSafetyEvent` and `DoctorReviewRequest` directly, and since
Answerability-Gate handoffs are real `DoctorReviewRequest` rows (just with
a new `risk_disposition` value and no linked `AgentSafetyEvent`), the
existing admin drill-down already shows them — just without a
severity/safety-severity facet (correctly, since they have none). A
dedicated `handoff_type`/`risk_disposition` filter on the admin dashboard
would be a genuine, small, justified addition, but was not implemented
this build (no admin-facing requirement forced it, and the spec's own
SS18 makes this conditional: "only if directly required for
observability" — durable data already exists for a future build to add
the filter without any backend rework).

## 12. Golden Set — deliberately NOT versioned this build

No `golden_set_v3.json` was created. Reasoning, not an oversight: every
existing `GoldenCategory` (`ACUTE_DANGER`, `POSSIBLE_OVERDOSE`,
`PERSONAL_SYMPTOM`, `FALLBACK`, ...) has a required-key shape tied to its
own specific semantic (Safety severity, deterministic tool paths, etc.)
that does not cleanly fit a NEED_MORE_INFO/uncertainty-NEED_DOCTOR case
without either (a) forcing a semantically-wrong category onto these cases,
or (b) a new category + a `GROUND_TRUTH_CONTRACT_VERSION` bump — a
materially larger, untested change this build did not have room to design
and verify properly on top of everything else. This build's real coverage
of the required behavior instead comes from 39 targeted unit/integration
tests (§14) plus a real local E2E run against live Postgres with actual DB
row verification (§13) — stronger ground-truth evidence for THIS specific
build than a golden case would add on its own. Recommended as a
well-scoped task for BUILD-45 (Quality Loop #2) or a dedicated follow-up,
once real production Answerability-Gate traffic exists to draw
de-identified cases from.

## 13. Local E2E (real Postgres, real DB rows)

Ran against real local Postgres (migration head unchanged at `0051` — no
new migration). Full script output, condensed:

```
E. Repeated clarification -> NEED_DOCTOR
  turn1: COMPLETED (triage clarification, unchanged text)
  turn2: COMPLETED (same clarification -- attempt_count now 2)
  turn3: HANDOFF_CREATED, handoff_type=UNCERTAINTY
  DB row: status=PENDING reason_code=REPEATED_CLARIFICATION risk_disposition=UNCERTAINTY_HANDOFF
  DoctorReviewRequest rows: 1

F. Explicit doctor request -> reuses E's still-active handoff (dedup)
  status=HANDOFF_CREATED, handoff_type=USER_REQUEST, SAME handoff_id as turn3
  DoctorReviewRequest rows: still 1 (no duplicate)

I. Acute danger -> Safety handoff wins
  status=HANDOFF_CREATED, handoff_type=SAFETY, safety_disposition=HANDOFF_REQUIRED

J. Possible overdose -> Safety handoff wins
  status=HANDOFF_CREATED, handoff_type=SAFETY

K. Out-of-scope -> no doctor handoff
  handoff_required=False

Final DB state: 3 real DoctorReviewRequest rows
  1x UNCERTAINTY_HANDOFF (reason_code=REPEATED_CLARIFICATION)
  2x HANDOFF_REQUIRED (reason_code=ACUTE_DANGER_DETECTED / POSSIBLE_OVERDOSE_REPORTED, unchanged Safety path)

ALL BUILD-42 LOCAL E2E ASSERTIONS PASSED
```

Two real bugs (§9) were found and fixed exclusively through this E2E run —
neither was caught by the 39 unit/integration tests written first,
confirming the value of the spec's own requirement to verify actual DB
rows rather than only mocked/stubbed paths.

## 14. Tests

New `tests/test_agent_v2_build42_answerability.py` — 39 tests:
`is_explicit_doctor_request` (7 positive/7 negative keyword cases),
`evaluate_grounding_answerability`/`evaluate_clinical_clarification_answerability`
pure-logic unit tests, `handoff_type_for` derivation, the full required
matrix A/B/C/D/E/F/G/I/J/K/L (H is covered by C/E's same code path — no
separate "unsupported personalized question" trigger exists beyond
grounding-failure escalation), a Safety-precedence-over-explicit-request
test, a zero-new-model-calls test, and M/N/O/P (duplicate prevention,
active-handoff reuse, patient authorization, cross-patient 403) against a
real in-memory SQLite `DoctorReviewRequest` table — plus the real-context-ref
regression test from §9.

`tests/test_agent_v2_medical_grounding.py` updated: the one existing test
whose behavior legitimately changed
(`test_golden_query_21_omeprazole_ungrounded_answer_is_now_declined`,
golden query_id 21) now asserts the new first-attempt NEED_MORE_INFO text
instead of the old fixed decline, with a new companion test
(`test_golden_query_21_second_grounding_failure_escalates_to_doctor`)
covering the third-turn escalation. `_enforce_medical_grounding`'s own unit
tests (calling that function directly, not through `run()`) are
unaffected — the function itself was not changed.

Full targeted run: 204 passed, then 39 in the new file alone (post-fix),
0 failed.

## 15. Latency / token / cost

**0 new synchronous model calls** — confirmed both by code inspection
(no new call to any model gateway anywhere in `answerability.py` or the
new orchestrator branches) and by a dedicated test
(`test_no_new_synchronous_model_calls_for_answerability_paths`: explicit
request and exhausted-clarification handoff both assert `len(gateway.
calls) == 0`). The explicit-doctor-request check runs before Tools/RAG/
Model entirely (SS10's own "no need to force clarification"). No
model-based router was introduced or considered. Token/cost are
unaffected by construction — every new code path either short-circuits
before the Main Model or reuses the exact reply text an existing path
already produced.

## 16. Known limitations

1. **Checkpoint/resume is not available for Answerability-Gate-created
   handoffs** (§9). A genuine mid-run process crash between claiming the
   handoff and the DB commit (not an ordinary HTTP retry, which
   `agent_idempotency` handles completely separately) could, on resume,
   re-attempt the handoff creation call — safe by construction (the same
   `agent-run:{id}:handoff` idempotency key is reused, and
   `create_doctor_review_request` is itself idempotent), but the
   checkpoint row for that specific run stays permanently non-terminal.
   This is a deliberate, documented trade-off, not an oversight — fixing
   it properly would require either fabricating a Safety Domain artifact
   (exactly what this build avoids) or a genuine redesign of the
   checkpoint system's own state machine, out of scope here.
2. **Golden Set v3 deferred** (§12).
3. **Admin dashboard has no dedicated `handoff_type` filter yet** (§11) —
   the durable data already supports adding one without backend rework.
4. **CANDIDATE-02 untouched** (§17 below) — this build adds one more
   entry point into the SAME pre-existing short-message heuristic
   (PERSONAL_SYMPTOM's clarification loop can now also end in NEED_DOCTOR),
   but does not change the heuristic itself.
5. `AnswerabilityReasonCode.AMBIGUOUS_MEDICAL_REQUEST` and
   `TOOL_DATA_INSUFFICIENT` are defined (per the spec's required list) but
   not currently assigned by any code path — no invented trigger for a
   state this build cannot actually observe yet.

## 17. BUILD-43/44 dependencies

- **BUILD-43 (Conversation State / CANDIDATE-02)**: this build's own
  `answerability_attempt_count` mechanism is intentionally independent of
  the `_follow_up_category`/`len<=35` heuristic — it does not read or
  write anything CANDIDATE-02 touches. BUILD-43's eventual
  TRUE_FOLLOWUP/STANDALONE_QUESTION/TOPIC_SWITCH/AMBIGUOUS_FRAGMENT
  taxonomy should be checked against this build's own multi-turn
  discovery (§7): a real user re-describing the same symptom is what
  reliably keeps the SAME clarification path active turn-over-turn, which
  BUILD-43's more precise follow-up resolution should make more robust,
  not less.
- **BUILD-44 (Doctor Chat Queue & Takeover)**: this build creates the
  `DoctorReviewRequest` row and stops — `assign_doctor_review_request`/
  `answer_doctor_review_request` (pre-existing, zero API callers per the
  audit) are exactly where BUILD-44 should start. The new `handoff_type`
  field (derived, always available) is what BUILD-44's doctor-facing queue
  should use to distinguish SAFETY/UNCERTAINTY/USER_REQUEST priority and
  presentation, without needing any new persisted field.

## 18. File scope

```
NEW    backend/agents/v2/answerability.py
MOD    backend/agents/v2/orchestrator.py
MOD    backend/agents/v2/handoff.py
MOD    backend/agents/v2/checkpoint.py
MOD    backend/agents/v2/conversation_state.py
MOD    backend/services/agent_doctor_handoff.py
MOD    backend/services/doctor_handoff.py
MOD    backend/api/agent_v2_routes.py
MOD    backend/models/schemas.py
NEW    tests/test_agent_v2_build42_answerability.py
MOD    tests/test_agent_v2_medical_grounding.py
```

No migration. No retrieval-tuning changes (BUILD-38 untouched). No
CANDIDATE-02 fix. No Track B (Drug Image) file touched — confirmed via
`git status` on both `feature/drug-image-b01-data-audit` and
`feature/drug-image-b02-collection` worktrees before and after this build,
neither checked out/reset/rebased/edited.

---

## 19. Release Gate

```text
BUILD-42: PASS

PARALLEL WORKTREE ISOLATION: PASS      (dedicated worktree/branch, baseline fd2b1d8 recorded)
TRACK B UNTOUCHED: PASS                (drug-image-b01/b02 worktrees confirmed unmodified)

HANDOFF AUDIT: PASS                    (9 questions answered with file:line evidence before any code)
ANSWERABILITY TAXONOMY: PASS
ANSWERABILITY GATE: PASS

ANSWERABLE PATH: PASS                  (tests A/B, unchanged behavior confirmed)
NEED_MORE_INFO PATH: PASS              (tests C/D + real E2E)
NEED_DOCTOR PATH: PASS                 (tests E/F + real E2E, real DB rows)

EXPLICIT DOCTOR REQUEST: PASS          (7/7 positive, 7/7 negative keyword match; 0 model calls)
REPEATED CLARIFICATION HANDOFF: PASS   (bounded at 2 attempts, real multi-turn E2E)
GROUNDING POLICY: PASS                 (general-medical decline unchanged; drug-shaped bounded)
TECHNICAL ERROR DOES NOT SPAM DOCTOR: PASS (MODEL_ERROR/TOOL_ERROR/TIMEOUT paths untouched by this build)

SAFETY HANDOFF DISTINCT: PASS          (risk_disposition HANDOFF_REQUIRED vs UNCERTAINTY_HANDOFF)
UNCERTAINTY HANDOFF DISTINCT: PASS
SAFETY PRECEDENCE: PASS                (guarded by not needs_handoff/not is_safety_blocked; real E2E I/J)
JUDGE DOES NOT CONTROL HANDOFF: PASS   (no Judge reference anywhere in answerability.py or its call sites)

DUPLICATE HANDOFF PREVENTION: PASS     (scoped to UNCERTAINTY_HANDOFF only; real E2E)
EXISTING ACTIVE HANDOFF REUSE: PASS    (real E2E: F reused E's row, same handoff_id)

DOCTOR_REVIEW_REQUEST REUSED: PASS     (zero new table, zero migration)
NO PARALLEL HANDOFF PERSISTENCE: PASS

OBSERVABILITY: PASS                    (answerability_decision on OrchestrationResult, new telemetry event, EvaluationPath.HANDOFF now reachable)
ADMIN MONITORING: PASS                 (existing DoctorReviewRequest drill-down already shows these rows; no backend change required)
METRIC SEMANTICS: PASS                 (safety_trigger_rate unaffected by construction -- no new AgentSafetyEvent rows)

NEW SYNC MODEL CALLS: 0
LATENCY REGRESSION: PASS
TOKEN REGRESSION: PASS
COST REGRESSION: PASS

ROUTER REGRESSION: PASS                (BUILD-40 router tests unaffected, 0 changes to classify_intent's own logic)
CONVERSATION STATE REGRESSION: PASS    (new fields additive-only, version bumped 3->4, old rows still deserialize)
GOLDEN: PASS                           (v2 untouched, not modified in place; v3 deliberately deferred with reasoning)
SAFETY ZERO-TOLERANCE: PASS            (ACUTE_DANGER/POSSIBLE_OVERDOSE/SCHEDULE_*/MULTI_TURN_CONTEXT/AUTH_ISOLATION all in the byte-identical full-suite baseline)
AUTH ISOLATION: PASS                   (cross-patient uncertainty-handoff creation confirmed 403)
FULL REGRESSION: PASS                  (11 failed = byte-identical pre-existing baseline, 0 new; 1864 passed)

CANDIDATE-02 TOUCHED: NO
FULL DOCTOR TAKEOVER BUILT: NO

READY FOR PR: YES
READY FOR BUILD-43 AFTER MERGE/VALIDATION: YES
```

🤖 Generated with [Claude Code](https://claude.com/claude-code)
