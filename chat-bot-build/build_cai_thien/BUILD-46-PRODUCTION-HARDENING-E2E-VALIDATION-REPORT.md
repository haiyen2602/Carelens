# BUILD-46 — Production Hardening & E2E Validation

Not a feature build: production findings → audit/rank → fix highest-risk
defects → comprehensive E2E → (pending) production validation → final
readiness decision.

## 1. Executive Summary

Fixed 2 real, production-confirmed defects at their root: (A) the
`search_drug` model-visible tool schema didn't declare the same
`limit`/`query` bounds its Pydantic runtime validation enforces, so an
occasional out-of-range model choice hard-failed a turn with
`TOOL_ERROR` (found live during BUILD-45's own production validation);
(B) cross-run doctor-handoff dedup could reuse/mislabel a genuinely
open SAFETY handoff for a brand-new USER_REQUEST/UNCERTAINTY trigger
(found live during BUILD-44's own production validation). Both were
reproduced first — B was reproduced end-to-end with a real model and
then dramatically confirmed fixed (the exact same script, run against
the pre-fix code via `git stash`, shows the USER_REQUEST turn's
`handoff_id` literally equal to the SAFETY turn's own id; post-fix, they
are always distinct). Audited every other Agent V2 tool for the same
class of schema/validation drift and closed 2 more instances
(`get_drug_info`, `get_dose_status`), plus added a generic regression
test so this class of drift cannot silently ship again for any future
tool. Candidates C (`AgentRun.intent` semantics) and D (retrieval
phrasing robustness) were audited and explicitly deferred, per the
task's own bounded-scope instruction. Full regression: 1155 passed, 11
pre-existing-unrelated failures (independently reconfirmed via
`git stash` against the clean baseline), 8 skipped, ruff clean. Zero new
synchronous model calls, zero new tool calls. Production deploy/canary
were **not** performed in this task — per the task's own instruction
("deploy through the single release owner") and this project's standing
rule that the AI never merges or deploys without being explicitly asked
— this report covers everything through PR-opened; a follow-up task will
run BUILD-46's own production validation once merged and deployed, the
same two-step pattern BUILD-44/45 already used.

## 2. Baseline

- `git fetch origin main` → tip `b451f03` (merge of PR #142, Track B's
  B-08 evaluation/safety production-validation report — code-free, a
  documentation-only PR, confirmed via `git diff --name-only`).
- BUILD-45's own merge commit (`bdf0eb3`) independently re-verified as an
  ancestor of `b451f03` (`git merge-base --is-ancestor`).
- BUILD-45's own production validation report (PR #143, still open —
  report-only, no code, does not block this build) re-read: `PRODUCTION
  STATUS: PARTIAL`, `READY FOR BUILD-46: YES`, with the exact
  `search_drug` finding (§7 of that report) this build's Fix A resolves.
  BUILD-45's own report is also directly quoted in the task file itself,
  so its content did not need re-derivation, only honoring.
- Worktree: `feature/build-46-production-hardening`, branched from
  `origin/main` at `b451f03`.
- Open PRs at start: only #143 (BUILD-45's own report-only PR, no code
  conflict).
- Track B's own active worktree (`drug-image-b08`) confirmed separate;
  zero files under Track B's ownership touched by this build's diff.
- Alembic head: `0055`, single head, unchanged throughout this build (no
  migrations added or needed).

**BASELINE VERIFIED: PASS**

## 3. Hardening candidate audit

**A — search_drug tool-schema contract.** Confirmed real and already
reproduced live (BUILD-45's own production validation, §7 of that
report). Root cause traced precisely: `SearchDrugArguments` (`tools.py`)
requires `limit` in `[1, 20]` and `1 <= len(query) <= 100`, but the
model-visible JSON schema (`model_gateway.py::_READ_ONLY_TOOL_SCHEMAS`)
declared only bare `{"type": "integer"}`/`{"type": "string"}` — no bound
at all. An occasional model-chosen out-of-range value passed the
(unconstrained) schema and then hard-failed at
`ToolGateway.execute()`'s own Pydantic boundary. **Mandatory per the
task; selected.**

**B — Doctor handoff dedup type safety.** Confirmed real and already
found live (BUILD-44's own production validation). Root cause traced
precisely this build (see §6): the reuse-check `if` guard in
`AuthorizedDoctorHandoffAdapter.create` only ever gates on the INCOMING
command's own `risk_disposition` — but `"UNCERTAINTY_HANDOFF"` is the
same literal, hardcoded value both a genuine UNCERTAINTY handoff and a
USER_REQUEST handoff are created with (USER_REQUEST vs UNCERTAINTY is a
DERIVED display distinction computed from `reason_code`, not its own
stored disposition). The candidate query itself matched by `patient_id`
+ open `status` alone, with no filter on the EXISTING row's own type.
**Strongly preferred per the task; selected.**

**C — `AgentRun.intent` semantics.** Re-audited (already audited once
during BUILD-45, no new information this build). Real, confirmed gap
(set once at checkpoint creation, never updated across a multi-turn
run), but resolving it requires a schema-semantics DECISION first (what
should "the run's intent" mean for a checkpoint-spanning run — first,
last, or a list?) and an audit of every consumer (Admin Monitoring,
evaluation, Judge, tracing, filters, cost metrics) before any change,
per the task's own explicit instruction ("Do not mutate semantics
silently... If semantics remain unresolved: DEFER"). Given A+B already
represent the full bounded scope this task allows, **deferred**, not
implemented.

**D — Retrieval phrasing robustness.** Not reproduced this task (no new
reproduction work was undertaken — A+B's own real evidence filled the
task's effort budget). Per the task's own explicit instruction ("Only
select if reproduced... If not reproduced: DEFER"), **deferred**.

## 4. Ranking / selection

| Candidate | Patient safety | Runtime reliability | Production evidence | Monitoring correctness | Regression/scope risk | Selected |
|---|---|---|---|---|---|---|
| A — search_drug schema | Low (no unsafe data, just a failed turn) | High (real live TOOL_ERROR) | Confirmed live | Low impact | Tiny, mechanical, well-tested | **YES** |
| B — handoff dedup type safety | **High** (a real SAFETY episode could be silently mislabeled/lost track of) | Medium | Confirmed live | High (mislabeled handoff type) | Small, precisely scoped, preserves BUILD-44 locking | **YES** |
| C — AgentRun.intent | None (monitoring-only) | Low | Confirmed via audit, not live incident | Medium | Requires a semantics decision first | DEFERRED |
| D — retrieval robustness | Unknown | Unknown | Not reproduced | Unknown | Unknown | DEFERRED |

**SELECTED HARDENING CANDIDATES: A (search_drug tool-schema contract), B (handoff dedup type safety)**

## 5. Reproduction

**A**: BUILD-45's own production validation already reproduced this live
(exact evidence in that report's §7). This build additionally verified
the precise mechanism directly: `SearchDrugArguments.model_validate(
{"query": "...", "limit": 0})` and `{"limit": 50}` both raise a real
`pydantic.ValidationError` locally, matching the ~0.06ms failure latency
observed on the real production span trail (too fast to be real catalog
work — an instant input-validation rejection).

**B**: reproduced fresh, end-to-end, with a real model, this build (no
prior script existed for this exact scenario). Real local E2E
(`scripts/agent_v2/build46_handoff_type_isolation_local_e2e.py`): seed a
genuine SAFETY handoff via `"Tôi vừa nôn ra máu"`, then send `"Tôi muốn
nói chuyện với bác sĩ."` (the task's own exact example phrase). Run
against the pre-fix code (`git stash` on `agent_doctor_handoff.py`): the
USER_REQUEST turn's `handoff_id` is **literally identical** to the
SAFETY turn's own id — the exact defect, reproduced with a real model,
not assumed from the unit-level adapter test alone.

## 6. Root causes

**A**: `SearchDrugArguments` and its JSON schema declaration are two
independently-maintained representations of the same contract, with
nothing enforcing they stay in sync — a structural gap, not a logic bug.

**B**: `"UNCERTAINTY_HANDOFF"` is a single, shared literal
`risk_disposition` value both `HandoffType.UNCERTAINTY` and
`HandoffType.USER_REQUEST` are built from
(`answerability.handoff_type_for` derives the DISPLAY distinction
from `reason_code`, never from a separately stored disposition — see
`handoff.py::create_for_uncertainty`'s own hardcoded
`risk_disposition="UNCERTAINTY_HANDOFF"`). The adapter's reuse-check
`if` guard therefore correctly identifies "this command MAY reuse
something" but the query beneath it never re-checks WHAT it may reuse
against — a missing type filter on the candidate side, not the trigger
side.

## 7. Tool-schema hardening (Fix A)

`backend/agents/v2/model_gateway.py::_READ_ONLY_TOOL_SCHEMAS`:
`search_drug`'s `limit` now declares `"minimum": 1, "maximum": 20`;
`query` now declares `"minLength": 1, "maxLength": 100` — the exact
bounds `SearchDrugArguments` (`tools.py`) already enforces. **Required
invariant satisfied**: model-visible schema constraints == runtime
validation constraints, for this tool.

**Researched, not assumed**: OpenAI's own structured-outputs/strict-mode
documentation states `minLength`/`maxLength`/`minimum`/`maximum` are NOT
enforced by constrained decoding the way `type`/`enum`/`required` are.
Verified directly against the real API this project uses
(`gpt-5.4-mini` via `.responses.create()`): a `strict: True` schema with
these keys present is accepted, not rejected (both the single-tool case
and the full real 7-tool schema set were tested). This is harm
reduction — the model typically respects a declared bound even without
hard grammar-level enforcement — not an absolute guarantee; Pydantic's
own runtime validation remains the real fail-closed safety net,
unchanged.

**Not solved by** (per the task's own explicit exclusions, all
confirmed avoided): silently clamping invalid model output (no clamping
anywhere in the fix), catching `ValidationError` and pretending success
(the existing fail-closed `ToolExecutionError` path is untouched), a
second model retry (no retry added — `ToolGateway.execute()`'s
try/except structure is unchanged), increasing the model-call budget
(structurally zero — see §13).

## 8. Handoff dedup hardening (Fix B)

`backend/services/agent_doctor_handoff.py::AuthorizedDoctorHandoffAdapter.create`:
the reuse-check now derives the canonical `HandoffType` for the incoming
command via the SAME existing `answerability.handoff_type_for` function
already authoritative for this distinction elsewhere (never a second,
parallel type derivation — the "preferred" approach the task itself
names), fetches all open-status candidates for the patient (unchanged
query shape), and reuses only the most-recent candidate whose OWN
derived type (computed the identical way, from that row's own
`reason_code`/`risk_disposition`) matches. A more recent but
type-incompatible row is skipped, not returned, and does not block a
fresh create for the new type either. **BUILD-44's own Patient-row lock
and state machine are completely untouched** — the lock still runs
unconditionally inside the same `if risk_disposition ==
"UNCERTAINTY_HANDOFF"` branch, before any type comparison, so the
concurrency guarantee it provides (§11) is preserved for every type, not
just same-type races.

## 9. Optional C/D decisions

Both deferred — see §3 for the full reasoning. No code touched for
either candidate. Recommendation for a future build: resolve C's own
semantics question (raw vs. final intent, or track both) as a dedicated
small design task before any implementation; reproduce D with a
semantic-equivalent query cluster (per the task's own §5 guidance)
before selecting it.

## 10. State invariants (regression lock, re-verified not just assumed)

| Invariant | Evidence |
|---|---|
| Ambiguous drug != active_entity | `tests/test_agent_v2_build45_cold_entity_binding.py` (unaffected by this build, re-run clean) |
| Unconfirmed visual candidate != active_entity | Track B's own scope, untouched |
| True follow-up inherits canonical entity/topic | `scripts/agent_v2/build46_search_drug_schema_fix_local_e2e.py` (8/8 real repeats), `scripts/agent_v2/build45_topic_persistence_local_e2e.py` (re-run, PASS) |
| Standalone short question != automatic follow-up | `tests/test_agent_v2_follow_up.py` (unaffected, re-run clean) |
| Topic switch clears stale entity/topic | `build45_topic_persistence_local_e2e.py` step 3 (re-run, PASS) |
| Retrieval query never overwrites canonical state | No retrieval-query-construction file touched by this build's diff (`git diff --name-only`) |
| Doctor ACTIVE suppresses bot | `scripts/agent_v2/build44_doctor_takeover_local_e2e.py` (re-run, PASS, 0 model calls confirmed on the active-suppression turn) |
| Resolve resumes bot | Same script, resolve → bot-resume real model call, PASS |

## 11. Safety invariants

Not altered — no file under `backend/agents/v2/safety.py` or the Safety
Domain touched by this build's diff. Regression re-verified:

| Invariant | Evidence |
|---|---|
| Acute Danger → Safety first | `build44_doctor_takeover_local_e2e.py`'s own Safety scenario re-run: `"Tôi vừa nôn ra máu"` → real `AgentSafetyEvent` recorded, `handoff_type=SAFETY`, PASS |
| Possible overdose → Safety/Dose Safety first | Full regression suite (unaffected files) |
| Schedule query → deterministic path | `scripts/agent_v2/build46_handoff_type_isolation_local_e2e.py` implicitly + full regression |
| Safety handoff → SAFETY only | Re-confirmed via §5's own reproduction: the SAFETY turn's own `handoff_type` stayed `SAFETY` in every run, pre- and post-fix |
| Uncertainty → UNCERTAINTY only | `build46_handoff_type_isolation_local_e2e.py` scenario F, PASS |
| Explicit doctor request → USER_REQUEST only | `build46_handoff_type_isolation_local_e2e.py` scenario D, PASS |
| **No handoff type cross-contamination** | **This is Fix B itself** — the exact invariant it restores, confirmed via real reproduction-then-fix (§5) |

## 12. Failure injection

New `tests/test_agent_v2_build46_failure_injection.py` (runtime-level,
not just Tool-Gateway-unit-level):

- Invalid tool arguments (the exact class Fix A closes) → `RunStatus.
  FAILED`, `error_code=TOOL_ERROR`, fixed safe message, no raw exception
  text, never a stuck/non-terminal run.
- A genuine domain/infrastructure tool failure (`TOOL_UNAVAILABLE`) →
  same safe terminal path.
- A failed tool call's own metrics are never ambiguously counted as a
  successful `tool_call`.

Additionally audited (not newly tested, confirmed safe by direct code
read): model timeout/error (`runtime.py`'s `_plan_with_limits`/
`_synthesize_with_limits` — bounded retry then fail-closed with a
correct `error_code`, unchanged by this build), the route-level
uncaught-exception boundary (`agent_v2_routes.py`'s own
`run_agent_orchestration`: `except Exception: db.rollback()` + a
best-effort minimal `INTERNAL_ERROR` `AgentRun` record + `raise` — never
swallowed, never a fabricated success), and grounding failure
(`GROUNDING_FAILURE` error code + a real honest-decline reply, unchanged,
observed live during BUILD-45's own production validation and again in
this build's own local E2E runs).

**FAILURE INJECTION: PASS**

## 13. Concurrency

Real Postgres (`BUILD42_TEST_DATABASE_URL`), `tests/test_agent_v2_answerability_dedup_postgres.py`:

- Pre-existing same-type concurrent-create test (BUILD-42's own):
  re-verified passing, unaffected by this build's changes.
- New `test_postgres_concurrent_different_type_handoffs_for_the_same_patient_serialize_correctly_into_two_rows`:
  two concurrent agent runs for the SAME patient, DIFFERENT types
  (UNCERTAINTY vs USER_REQUEST) — both still serialize on the same
  Patient-row lock (unchanged), both correctly create their OWN row
  (never merged just because they share the lock), exactly 2 durable
  rows, no orphan, no corrupted state.
- Doctor-side concurrency (claim race, resolve/message race) unaffected
  by this build — re-run via `tests/test_api/test_doctor_review_routes.py`,
  clean.

**CONCURRENCY: PASS**

## 14. Full local E2E

Real Postgres + real model, no seeded state except where explicitly
noted (the established, pre-existing decoupling technique for the
UNCERTAINTY scenario, unchanged from BUILD-44's own script):

- **A** (`build46_search_drug_schema_fix_local_e2e.py`): 8 repeated real
  attempts of `"Thuốc Berocca Bayer dùng để làm gì?"` →
  `"Tác dụng phụ thì sao?"`. **8/8 COMPLETED, 0 TOOL_ERROR** (pre-fix
  production rate was 1/4).
- **B** (ambiguous drug, no false bind): covered by BUILD-45's own
  existing local E2E/tests, unaffected, re-verified via the full
  regression sweep.
- **C** (topic persistence): `build45_topic_persistence_local_e2e.py`
  re-run, ALL CHECKS PASSED.
- **D/E/F** (`build46_handoff_type_isolation_local_e2e.py`, new): SAFETY
  → USER_REQUEST (no reuse/mislabel), repeated USER_REQUEST (compatible
  reuse, same row), UNCERTAINTY (correct type, no cross-reuse). **ALL
  CHECKS PASSED** — and dramatically confirmed as a real fix via
  `git stash` (§5).
- **G** (BUILD-44 takeover): `build44_doctor_takeover_local_e2e.py`
  re-run in full — Core/Safety/Uncertainty/Explicit-User-Request, claim
  → activate → 0 model calls during ACTIVE suppression → messages →
  resolve → bot resumes. **ALL CHECKS PASSED**, unaffected by this
  build.
- **H** (schedule/time): deterministic `TODAY_DOSES` resolution
  confirmed via the full regression sweep (schedule-tagged tests
  untouched, all pass) and BUILD-45's own production validation smoke.
- **I** (Safety): confirmed unchanged via G's own Safety scenario
  re-run (real `AgentSafetyEvent`, correct `SAFETY` type) plus the full
  Safety-tagged regression sweep.

**LOCAL E2E: PASS**

## 15. Regression

`pytest tests/ -k "agent_v2 or drug_knowledge or safety" --ignore=tests/services/photo_verification --ignore=tests/vlm_demthuoc`
→ **1155 passed, 11 failed, 8 skipped**.

All 11 failures independently reconfirmed pre-existing via `git stash`
(re-run against the clean `b451f03` baseline, identical 11 failures,
identical tracebacks — the same 7-failure Track B B-06 SQLite-fixture
gap already documented in `agent-v2-build-log.md`, plus 4 unrelated
long-term-memory/scheduling failures independently reconfirmed
pre-existing during BUILD-45's own broader sweep). All 8 skips are the
standard `set <BUILD>_TEST_DATABASE_URL` conditional skips for optional
real-Postgres concurrency tests.

Targeted suites explicitly named by the task, all re-run this build:
BUILD-40 router / BUILD-42 answerability / BUILD-43 follow-up / BUILD-44
doctor takeover / BUILD-45 entity+topic fixes — all covered by the broad
sweep above, zero failures. Safety, Dose Safety, Time/Schedule,
Grounding, Drug tools — covered by the broad sweep, zero failures.
Monitoring: `tests/test_api/test_admin_monitoring_routes.py` re-run
(unaffected file, but a real consumer of `DoctorReviewRequest` data),
clean. Auth: `test_api/test_doctor_review_routes.py`'s own auth-gating
tests re-run, clean. Migrations: `alembic heads` still a single `0055`
head throughout — no migration touched. `ruff check` on every
changed/new file (2 modified + 5 new backend/test/script files, plus 1
further modified test file): all clean. Frontend: not touched by this
build's diff (`git diff --name-only` confirms zero `frontend/` files).

**FULL REGRESSION: PASS**

## 16. Cost / model-call impact

Both fixes are, by construction, zero new model or tool calls:

- Fix A is a pure JSON-schema literal addition (`minimum`/`maximum`/
  `minLength`/`maxLength` keys on an already-existing property dict) —
  no new code path, no new call site.
- Fix B replaces a single-row `.first()` fetch with a `.all()` fetch
  over the same query plus an in-process Python filter — the same
  number of DB round-trips (still exactly one `SELECT`), zero model or
  tool calls added.

Empirically confirmed: every local E2E run in §14 shows `model_calls`/
`tool_calls` counts consistent with the pre-BUILD-46 baseline shape (2
model calls for a typical plan+synthesize turn, 0 for the ACTIVE-
suppression/deterministic-schedule paths) — no run shows an inflated
count attributable to either fix.

**NEW SYNC MODEL CALLS: 0**
**NEW TOOL CALLS: 0**

## 17. Production deploy

**Not performed in this task.** Per the task's own explicit sequencing
("After: LOCAL PASS → PUSH → PR → REVIEW → MERGE → then deploy through
the single release owner") and this project's standing rule that the AI
never merges or deploys without being explicitly asked first, this
report covers everything through PR-opened. Deploy is the release
owner's decision, to happen after human review and merge — the same
two-step pattern (local work + PR, then a separate explicitly-requested
production-validation task) BUILD-44 and BUILD-45 both already used
successfully in this project.

**PRODUCTION DEPLOYMENT: NOT PERFORMED (pending merge + release-owner deploy)**

## 18. Production canary

**Not performed** — depends on §17. Will be run as a dedicated follow-up
task once merged and deployed, using the same real-account, fresh-
conversation-id, durable-evidence-cross-check methodology
BUILD-44/45's own production validations already established, targeting
the two scenarios this build's own fixes touch: (A) `search_drug`
natural follow-up flow with 0 `TOOL_ERROR` observed across several real
attempts, and (B) a real SAFETY-then-USER_REQUEST sequence, cross-checked
against durable `DoctorReviewRequest` rows to confirm no type
cross-contamination on production specifically.

**PRODUCTION CANARY: NOT PERFORMED (pending)**

## 19. Durable evidence

Every local E2E claim in this report is backed by a durable read, not a
reply-text-only check: `build46_handoff_type_isolation_local_e2e.py`
reads real `DoctorReviewRequest` rows via SQL and derives each one's
`HandoffType` independently (via the same `handoff_type_for` the fix
itself uses, confirming the FIX and the TEST agree without the test
merely re-asserting the fix's own internal state);
`build46_search_drug_schema_fix_local_e2e.py` reads the real
`OrchestrationResult.status`/`.tools` for every one of its 8 repeats,
not just the final reply text. No new durable schema/telemetry field was
added by this build (neither fix touches `AgentRun`/`AgentRunSpan`
columns), so no new cross-check surface exists beyond what's already
exercised.

## 20. Remaining known limitations

- Fix A's harm-reduction schema hints are not a hard guarantee (§7) —
  OpenAI's own documentation states these keywords aren't enforced by
  constrained decoding; the Pydantic runtime validation remains the real
  safety net, unchanged and still fail-closed.
- Candidates C and D remain open, deferred with documented reasoning
  (§3, §9) — not defects introduced by this build, pre-existing findings
  from BUILD-45's own audit, carried forward.
- Production canary for this build's own fixes has not yet run (§18) —
  the local E2E evidence (§14) is strong (a real reproduction-then-fix
  for B, an 8/8 repeated real-model confirmation for A) but production
  traffic patterns can differ from a controlled local script.
- The already-documented handoff dedup TYPE-mislabeling bug this build
  fixes is distinct from, and does not touch, the separately-documented
  (and still open) admin-response `handoff_type` API mis-reporting nuance
  noted in earlier reports — re-verify that nuance is fully closed by
  this fix in the production canary follow-up, since Fix B changes the
  underlying reuse mechanism this nuance was originally observed through.

## 21. Final roadmap status

BUILD-42 through BUILD-45 all production-verified or production-partial-
verified; BUILD-46 closes the 2 highest-priority hardening findings
those validations surfaced, fully locally verified (E2E + regression +
concurrency + failure injection), pending only merge + deploy +
production canary to close the loop. No new critical or blocking runtime
defect was discovered during this build's own audit beyond the 2 already
fixed.

**AGENT V2 ROADMAP STATUS: PARTIAL** (production-hardened locally; awaiting
merge/deploy/production-canary to reach fully verified)

## 22. Release Gate

```
BUILD-46: PASS

BASELINE VERIFIED: PASS
BUILD-45 PROD VALIDATION CONSUMED: PASS
TRACK B UNTOUCHED: PASS

SELECTED HARDENING CANDIDATES: A (search_drug tool-schema contract), B (handoff dedup type safety)

SEARCH_DRUG SCHEMA: PASS
MODEL SCHEMA limit [1,20]: PASS
SEARCH_DRUG TOOL_ERROR REPRO: FOUND (BUILD-45 production validation + this build's own direct Pydantic repro)
SEARCH_DRUG TOOL_ERROR AFTER FIX: 0 (8/8 real repeated local E2E attempts)
NEW MODEL RETRIES: 0

HANDOFF TYPE DEDUP: PASS
SAFETY -> USER_REQUEST CROSS-REUSE: 0 (real E2E reproduced-then-fixed, git-stash-confirmed)
SAFETY -> UNCERTAINTY CROSS-REUSE: 0
SAME-TYPE HANDOFF REUSE: PASS (repeated USER_REQUEST reuses the same row, real E2E confirmed)

AGENTRUN INTENT: DEFERRED
RETRIEVAL ROBUSTNESS: DEFERRED

ENTITY STATE: PASS
TOPIC STATE: PASS
SAFETY: PASS
DOSE SAFETY: PASS
DOCTOR TAKEOVER: PASS
SCHEDULE/TIME: PASS
NO STUCK RUNS: PASS

FAILURE INJECTION: PASS
CONCURRENCY: PASS
NEW SYNC MODEL CALLS: 0

LOCAL E2E: PASS
FULL REGRESSION: PASS (1155 passed, 11 pre-existing-unrelated failed, 8 skipped, ruff clean)

PRODUCTION DEPLOYMENT: NOT PERFORMED (pending merge + release-owner deploy)
PRODUCTION CANARY: NOT PERFORMED (pending)

PRODUCTION STATUS: PARTIAL (local hardening complete and verified; production validation pending as a follow-up task)

OPEN CRITICAL SAFETY DEFECTS: 0
OPEN BLOCKING RUNTIME DEFECTS: 0

AGENT V2 ROADMAP STATUS: PARTIAL

READY TO CLOSE TRACK A: NO — pending production validation follow-up (same two-step pattern as BUILD-44/45)
```

## 23. Stop condition

Per the task's own instruction: audit → reproduce → implement selected
fixes → local tests → full E2E → regression → **PR** → review → merge →
controlled deploy → production validation → final report. This report
and the accompanying PR complete everything through PR-opened. **STOP
here** — no merge, no deploy, no BUILD-47, no unrelated fixes. Merge,
deploy, and the production-validation follow-up are for the release
owner / a separate explicitly-requested task.

## 24. Code review response (round 1, post-push)

One automated finding on PR #144, verified against the real code before
acting.

**Finding ("Potential Race Condition")** — the label doesn't quite fit:
the Patient-row lock already serializes concurrent creates correctly
(confirmed by both the pre-existing and this build's own new
different-type concurrency test, §13, both passing). The underlying
technical observation was accurate, though: Fix B's reuse query changed
from a SQL-bounded `.first()` (`LIMIT 1`) to an unbounded `.all()` —
required for the new type-aware filtering (which needs to see more than
just the single most recent row), but with no SQL limit at all, so a
pathological per-patient active-handoff count would hold the Patient-row
lock over an unbounded scan.

**Fixed**: added `_MAX_REUSE_CANDIDATES = 20` as a SQL `LIMIT` on the
same query — generous headroom over any realistic per-patient count of
simultaneously open handoffs (a personal escalation queue, not a shared
table), so it changes no real outcome. A genuinely pathological patient
beyond the bound degrades to "create a fresh row" — still correct, still
strictly safer than the pre-fix behavior (never a type-incompatible
reuse), just no longer an unbounded scan.

Re-verified after the change: unit tests (30 passed), real-Postgres
concurrency tests (2 passed, unchanged), real local E2E
(`build46_handoff_type_isolation_local_e2e.py`, ALL CHECKS PASSED,
unchanged results), `ruff check` clean. Pushed as commit `20f039a` on
the same branch/PR; no merge, no deploy — same STOP condition as §23.
