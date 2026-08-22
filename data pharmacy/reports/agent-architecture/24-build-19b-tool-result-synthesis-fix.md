# BUILD-19B — Tool Result Synthesis Fix

Date: 2026-08-19
Scope: fix BUILD-19's P1 finding (`reply=""` on every Agent V2 turn that
called a tool) by implementing the missing second model turn — User → Model
→ Tool Call → Tool Result → Model Synthesis → Final Reply — then verify the
fix locally and on the existing Railway `staging` environment. Production
was never modified. `AGENT_RUNTIME_ENABLED` was `true` on staging only for
the duration of this build's live verification and was rolled back to
`false` at the end (confirmed via an authenticated request, not an
unauthenticated-401 guess). Vinmec Web DEGRADED was explicitly out of scope
and was not touched.

## Root cause (recap from BUILD-19)

`OpenAIModelGateway.plan_read_only()` made exactly one model call and
returned that call's own `output_text` as the final reply. When the OpenAI
Responses API returns a `function_call`, `output_text` for that same turn is
empty — standard, documented behavior. `ReadOnlyAgentRuntime._run()` executed
every planned tool call and then returned the *pre-tool* planning text as the
final answer. There was no second model turn that fed verified tool results
back for synthesis.

## Fix

### `backend/agents/v2/model_gateway.py`

- New `SynthesisEvidence` (`tool_name`, `provenance`, `data`) — deliberately
  independent of `tools.py`'s `ToolResult`, preserving this module's existing
  zero-dependency-on-tools.py layering. The runtime converts `ToolResult` →
  `SynthesisEvidence` itself.
- New `ModelSynthesis` (`response`, `usage`, `request_id`) — the typed result
  of the new second turn.
- New `synthesize_read_only(*, message, actor_role, evidence)` added to the
  `ModelGateway` Protocol, `OpenAIModelGateway`, `DisabledModelGateway`, and
  `StaticModelGateway` (test double; its default synthesis text is a fixed
  sentinel, deliberately **not** derived from `plan.response` — defaulting a
  tool-calling synthesis reply to the pre-tool text would let this double
  silently reintroduce the exact BUILD-19 defect it exists to catch).
- `OpenAIModelGateway.synthesize_read_only()` calls `responses.create()` with
  **no `tools=` parameter at all** — a structural guarantee, not a prompt
  request, that the model cannot call another tool or otherwise act during
  synthesis, and therefore cannot override Safety/Doctor/Operational DB
  provenance from that turn. The prompt supplies the verified tool evidence
  as JSON and instructs the model to treat it as ground truth. If
  `output_text` is empty even on this second call, the method raises
  (`MODEL_SYNTHESIS_EMPTY`) instead of returning empty text, so that failure
  mode flows through the same bounded-retry-then-fail-closed path as every
  other model-call failure — it cannot silently reproduce the BUILD-19 bug
  under a different name.

### `backend/agents/v2/runtime.py`

- `_run()`: after the tool-execution loop completes, if `plan.tool_calls` is
  empty the existing single-turn behavior is unchanged (no tool ran, so
  `plan.response` already is the one and only model turn's real answer — not
  the BUILD-19 defect path). If tool calls were made, the runtime now calls
  a new `_synthesize_with_limits()` and returns **its** response as the final
  reply — `plan.response` is never used as the final reply once a tool ran.
- New `_synthesize_with_limits()`, structurally mirroring the existing
  `_plan_with_limits()`: same cancellation/timeout/step/model-call budget
  checks before each attempt, same bounded-retry-then-`RunStatus.FAILED`
  pattern on exception (fixed safe message `"Agent tam thoi khong san
  sang."`, never fabricated content). Already-fetched tool results are kept
  in the returned `RunResult` even when synthesis ultimately fails, for audit
  transparency.
- Safety/Handoff short-circuits (`SAFETY_BLOCKED`, `HANDOFF_REQUIRED`,
  `HANDOFF_CREATED`) are unchanged and remain **before** any model call at
  all — synthesis is only ever reached after both a planning call and a tool
  loop have already run, so it structurally cannot be reached for those
  terminal states.
- Telemetry: the synthesis call gets its own `TraceComponent.MODEL` span
  (`operation="synthesize_read_only"`), separate from the planning span
  (`operation="plan_read_only"`) and the tool spans — confirmed as separate,
  distinctly-named events in staging logs (see §Observability below).
- `agent_max_model_calls` already defaulted to `2` (`backend/config.py`) —
  sized, by coincidence, exactly for one planning call plus one synthesis
  call, so no default needed to change for the common single-round case.
  `agent_max_steps` (default `4`) did need attention — see §Staging
  configuration below.

## Tests

Ten new regression scenarios (`tests/test_agent_v2_synthesis.py`), plus two
new `OpenAIModelGateway`-level unit tests
(`tests/test_agent_v2_model_gateway.py`) confirming the "no `tools=` schema"
structural guarantee and the fail-closed-on-empty-output-text behavior
directly against the real gateway implementation:

| # | Scenario | Result |
| - | --- | --- |
| 1 | Drug information + tool → non-empty reply | PASS |
| 2 | Today doses + tool → non-empty reply | PASS |
| 3 | Safety SAFE + tool → non-empty reply (the specifically-flagged BUILD-19 case) | PASS |
| 4 | Prescription query + tool → non-empty reply | PASS |
| 5 | Multiple tool calls → exactly one final synthesized reply | PASS |
| 6 | `SAFETY_BLOCKED` → no synthesis call (and no plan/tool call either) | PASS |
| 7 | `HANDOFF_CREATED` → no synthesis call | PASS |
| 8 | Synthesis failure (always-raising gateway) → fail-closed, never fabricates | PASS |
| 9 | Budget exceeded → synthesis is budget-gated, not exempt from limits | PASS |
| 10 | Checkpoint resume after completion does not replay the tool or synthesis call | PASS |

Existing tests updated for the new required second turn (every one of these
previously asserted the *old, buggy* behavior — that a tool-calling run's
final reply equals the pre-tool planning text — and needed to start
asserting the synthesized text instead):

- `tests/test_agent_v2_runtime.py::test_runtime_executes_only_allowlisted_read_tool`
  — now supplies an explicit `ModelSynthesis` and asserts against it; budget
  raised from `max_steps=2` to `max_steps=3` to fit the now-mandatory
  synthesis step.
- `tests/test_agent_v2_orchestrator.py::test_drug_information_query_calls_tools_and_completes`
  — same change; `_SpyModelGateway` extended with `synthesize_read_only` and
  a `synthesis_calls` recorder (also consumed unchanged by
  `tests/test_agent_v2_safety_occurrence_binding.py` and
  `tests/test_agent_v2_transaction_durability.py`, which import it — both
  still pass with no changes needed there).
- `tests/test_agent_v2_observability.py::test_trace_propagates_across_runtime_model_and_tool_without_prompt_or_patient_data`
  — the fixed clock-value list extended from 6 to 8 entries (2 more clock
  reads for the new synthesis span); still asserts no prompt/patient text
  ever appears in a telemetry event.

**Local regression:**

```
tests/ -k agent_v2 (excluding two unrelated cv2/numpy collection errors,
pre-existing and unrelated to this build):        174 passed, 2 skipped
tests/ (full repo, same two collections excluded): 712 passed, 7 failed, 19 skipped
```

The 7 failures are the same pre-existing, unrelated local-environment
failures established during BUILD-18B (`test_verify_email_flow`,
`test_verify_email_invalid_token_returns_400`,
`test_forgot_password_and_reset_password_flow`,
`test_reset_password_invalid_token_returns_400`,
`test_doctor_search_still_gets_full_fields_regression`,
`test_get_current_user_valid_jwt`,
`test_patient_role_cannot_read_or_hide_another_patients_chat_history`) — same
names, same count, zero new failures introduced by this build.

LOCAL REGRESSION: **PASS**

## Staging redeploy

Reused BUILD-18B's existing staging environment/service/Postgres — no new
provisioning. `railway up --service BE --environment staging -c`: build
succeeded, new image digest, new deployment id
(`578d99b0-c05e-4ecf-8840-fc2f9778727b`, superseding BUILD-19's
`d6c5818c...`). Pre- and post-deploy checks via a temporary TCP proxy
(created, used, deleted immediately both times):

```
alembic current:                    0033 (head) — unchanged
verify_rag_corpus_identity.py:      {"status": "PASS", "corpus_version": "legacy-drug-chunks-openai-v1", "drug_chunks_rows": 14423, "mismatches": []}
```

Identical to every prior build's baseline. No migration, corpus, or schema
change was part of this build.

## Staging configuration: `AGENT_MAX_STEPS` raised from the code default (4) to 6

The first live UAT pass (below) surfaced a real, in-scope consequence of this
fix: the *prescription query* scenario reasonably calls three tools
(`get_active_prescriptions`, `get_today_doses`, `get_upcoming_doses`). Under
the code default `agent_max_steps=4` (sized for the *old* single-model-turn
design: 1 planning step + up to 3 tool steps, no synthesis step ever
needed), 1 planning step + 3 tool steps already consumes the entire budget,
leaving zero room for the now-mandatory synthesis step. The runtime did
exactly what it should — failed closed to `BUDGET_EXCEEDED` with the fixed
safe message `"Agent run vuot gioi han model/step."`, never fabricating a
reply — but that scenario, one of the app's core use cases and one of
BUILD-19's four flagged empty-reply cases, still would not have produced a
real answer.

This build's own explicit requirement is "support multiple tool calls, while
still enforcing budgets" — the guardrail was correct, but the *default*
budget was sized for a design this build deliberately changed (every
tool-calling run now needs one more step than before, for synthesis). I
raised `AGENT_MAX_STEPS` to `6` on staging only (an environment variable,
not a code change — `railway variable set`, followed by a restart to apply
it) and re-ran the full UAT: the prescription-query scenario then completed
with a real three-tool synthesized reply. This is reported as a deliberate,
narrowly-scoped, reversible operational decision taken to properly verify
this build's own "multiple tool calls" requirement, not as scope creep into
BUILD-19's excluded items. **The `AGENT_MAX_STEPS` variable was removed from
staging again during rollback** (see §Rollback), restoring staging to
exactly BUILD-19's prior configuration; the code default in
`backend/config.py` (`agent_max_steps: int = Field(default=4, ...)`) was
**not** changed. Recommend a follow-up decision on whether to raise that
production-bound default (or make the effective step cost synthesis-aware)
before broader rollout — not applied here, since it was not asked for and is
a cross-cutting default, not specific to this fix.

## Live staging UAT re-run

`AGENT_RUNTIME_ENABLED=true` set (staging only), confirmed via `railway
variables` (not an HTTP-status guess), then a full restart to actually apply
it (`railway redeploy`). `scripts/agent_v2/uat_staging_scenarios.py` re-run
twice against fresh synthetic data (BUILD-18's `agent-v2-staging-*` accounts,
re-seeded via the existing idempotent `seed_staging_agent_v2_data.py`, plus
one dose occurrence transitioned to `MISSED` to reproduce the Safety SAFE
scenario exactly as BUILD-19 did) — once before, once after the
`AGENT_MAX_STEPS` change above.

| # | Scenario | BUILD-19 reply | BUILD-19B reply (after fix) |
| - | --- | --- | --- |
| 1 | Drug information (paracetamol) | **empty** | populated, correct (243–447 chars across runs) |
| 4 | Today's doses | **empty** | populated, correct, cites `operational-db:dose-occurrence:today` (408–520 chars) |
| 6 | Safety SAFE (real MISSED occurrence, reviewed low-risk policy) | **empty** | populated, correct — references the MISSED 01:00 dose and the still-PENDING 13:00 dose (309–313 chars) |
| 10 | Prescription query (3 tools) | **empty** | populated, correct — active prescription + today's + upcoming doses, all three tool results synthesized into one reply (529 chars) |

All four of BUILD-19's specifically-flagged empty-reply scenarios now
produce a real, non-empty, correct final reply. Scenario 6 (Safety SAFE) —
the case the user explicitly asked to watch — is fixed. Scenario 4 also
exercised a genuine multiple-tool-call synthesis in the second run
(`get_today_doses` + `get_active_prescriptions` → one reply), independently
confirming requirement #5.

TOOL-CALL LOOP: **PASS**
FINAL SYNTHESIS: **PASS**
NON-EMPTY TOOL REPLIES: **PASS**

### Safety / Handoff — no regression

- `safety_unresolved_pending_dose` (still-`PENDING` dose, unresolvable) →
  `SAFETY_BLOCKED`, fixed fallback string
  `"Khong the tra loi khi danh gia an toan chua duoc xac nhan."` — byte-
  identical to BUILD-19, confirming synthesis is never reached for this
  terminal state.
- `doctor_handoff` (dosage-change request) → `HANDOFF_CREATED`, fixed
  fallback string `"Yeu cau da duoc ghi nhan de bac si xem xet."` — byte-
  identical to BUILD-19, new genuine `handoff_id` each run, confirming
  synthesis is never reached here either.

SAFETY REGRESSION: **PASS** (none found)
HANDOFF REGRESSION: **PASS** (none found)

### Persistence — no duplication, no replay

Checked directly against the staging database (temporary TCP proxy, deleted
immediately after use):

```
agent_run:              63 rows total; +18 attributable to this build's two
                         UAT passes (9 orchestrator-reaching scenarios ×
                         2 runs), all with terminal statuses matching the
                         HTTP responses exactly, no gaps, no duplicates
agent_run_checkpoint:    63 rows — 1:1 with agent_run, as designed
doctor_review_request:   5 rows; +2, exactly the two new doctor_handoff
                         scenario calls (two distinct requests, not a
                         retry of the same one — no duplicate)
safety_event:            1 row despite two safety_safe scenario calls
                         against the same MISSED occurrence — the existing
                         idempotent-recording behavior correctly did not
                         create a second row for a repeat assessment of an
                         occurrence that hadn't changed state
```

`tests/test_agent_v2_synthesis.py::test_checkpoint_resume_after_completion_does_not_replay_tool_or_synthesis_calls`
additionally proves this at the unit level: a second `orchestrator.run()`
call for an already-`COMPLETED` `agent_run_id` raises `CheckpointTerminalError`
before the runtime is ever re-entered, so neither the tool call nor the
synthesis call can be replayed by a retried/duplicated request.

CHECKPOINT/IDEMPOTENCY: **PASS**
PERSISTENCE: no regression found (not one of the requested closeout keys,
recorded here for completeness, consistent with BUILD-19's own PASS)

### Authorization — no regression

Cross-patient denial (caregiver, unlinked `patient_2`) → `403`, unchanged
message, in both UAT passes. No other authorization boundary was exercised
beyond what BUILD-18/18B/19 already proved.

AUTHORIZATION: no regression found (consistent with BUILD-19's PASS)

### Observability — separate planning/tool/synthesis events, no leakage

`railway logs --service BE --environment staging --lines 300 --json`,
checked after both UAT passes:

```json
{"event":"agent_span.started","operation":"plan_read_only","model":"gpt-5.4-mini","model_role":"main", ...}
{"event":"agent_span.started","operation":"synthesize_read_only","model":"gpt-5.4-mini","model_role":"main", ...}
```

10 `plan_read_only` spans and 6 `synthesize_read_only` spans found across
the window (synthesis spans appear only for the runs that actually called a
tool — for those that failed the step budget before reaching the model call,
the span itself still records the attempt, distinctly, which is correct: it
shows a guardrail was hit, not that nothing happened). Both are
`TraceComponent.MODEL` events but are separately named and independently
countable — confirming "record planning/tool/synthesis model calls
separately."

Scanned the full 300-line window for the user's exact message text, patient
identifiers, drug names, and tool call arguments (`search_drug`, `query`,
`arguments`, `paracetamol`, the Vietnamese scenario phrases, the synthetic
patient id) — zero hits. Every field present is metadata (event name,
operation, model, role, latency, token counts, ids). No prompt, PHI/PII, or
tool payload was logged, consistent with BUILD-18B/19's existing redaction
behavior — the new synthesis span did not introduce a new leakage surface.

OBSERVABILITY: no regression found; "record planning/tool/synthesis
separately" requirement confirmed met.

## Rollback

```
railway variable delete AGENT_MAX_STEPS --service BE --environment staging
railway variable set "AGENT_RUNTIME_ENABLED=false" --service BE --environment staging
railway redeploy --service BE --environment staging -y   # required to actually
                                                            # apply both changes to
                                                            # the running process —
                                                            # see note below
```

**Verification note:** setting `AGENT_RUNTIME_ENABLED=false` and confirming
it via `railway variables` was **not sufficient by itself** — the already-
running process kept serving real orchestration responses (HTTP 200 with a
real reply) for a short window after the variable changed, until the
subsequent explicit `railway redeploy` actually restarted the process. This
matches BUILD-18B's own established correction (never trust a variable's
recorded value alone; confirm live behavior with a real authenticated
request). Confirmed OFF with three consecutive authenticated `POST
/api/v1/agent/v2/orchestrate` calls, all `404`, after the redeploy:

```
$ curl ... -H "Authorization: Bearer <valid patient JWT>" -d '{"patient_id":"...","message":"xin chao"}'
HTTP 404   (x3, consecutive)
```

Final staging variable state re-confirmed:
`AGENT_RUNTIME_ENABLED=false`, `AGENT_MAX_STEPS` absent (code default),
`AGENT_TOKEN_BUDGET=4096` (default, untouched) — staging restored to
BUILD-19's exact configuration baseline; only the deployed **code** differs
(the fix itself).

## Production

Production was never targeted by any write command in this build — every
`railway up`/`railway redeploy`/`railway variable set|delete` call was
explicitly scoped `--environment staging`. Production's Postgres service
instance is unchanged throughout this build (same deployment id
`f11b7343-a9f0-4175-8ef8-afa6769f0d49`, same `2026-08-12T09:02:57Z`
timestamp, checked at the start and the end of this build), and its
`DATABASE_URL` hashed identically (`e2f22a0f320a`, SHA-256 prefix, same
method) at both checks — the database itself was not touched.

**Transparency note, not a defect in this build:** production's `BE`/`FE`
app-layer deployments changed **twice** during this session, unprompted by
anything in this build — confirmed via `git fetch origin main` both times to
be ordinary, unrelated teammate PRs merging to `main` (PR #61
photo-verification wording fix, then PR #62/#63 doctor-drug-lookup and
admin-dashboard features), which Railway's standard CI/CD auto-deploys to
production independently of this Agent V2 work. This is normal concurrent
team activity, not something this build caused — verified by (a) the
Postgres service instance and `DATABASE_URL` being unchanged as above, and
(b) every write command this build issued being explicitly `--environment
staging`. Recorded here in the interest of the same rigor this project has
applied to every prior build's production-untouched claim, rather than
silently reusing a stale timestamp that no longer matched.

PRODUCTION CHANGED: **NO**

## New/changed files

- `backend/agents/v2/model_gateway.py` — `SynthesisEvidence`, `ModelSynthesis`,
  `synthesize_read_only()` on the Protocol/`OpenAIModelGateway`/
  `DisabledModelGateway`/`StaticModelGateway`.
- `backend/agents/v2/runtime.py` — `_synthesize_with_limits()`, `_run()`
  tail rewritten to call it whenever `plan.tool_calls` is non-empty,
  `_add_usage()` generalized to accept either a plan or a synthesis result.
- `tests/test_agent_v2_synthesis.py` (new) — the ten required regression
  scenarios.
- `tests/test_agent_v2_model_gateway.py` — two new `OpenAIModelGateway`-level
  unit tests for the synthesis turn's structural no-tools guarantee and its
  fail-closed-on-empty-output behavior.
- `tests/test_agent_v2_runtime.py`, `tests/test_agent_v2_orchestrator.py`,
  `tests/test_agent_v2_observability.py` — updated for the new required
  second turn (see §Tests).

No corpus, migration, or architecture-boundary file was changed. Vinmec Web
DEGRADED was not touched, per the explicit exclusion.

## Result

BUILD-19B: **PASS**

TOOL-CALL LOOP: PASS

FINAL SYNTHESIS: PASS

NON-EMPTY TOOL REPLIES: PASS

SAFETY REGRESSION: PASS

HANDOFF REGRESSION: PASS

CHECKPOINT/IDEMPOTENCY: PASS

LOCAL REGRESSION: PASS

LIVE STAGING UAT: PASS

PRODUCTION CHANGED: NO

BUILD-19 FINAL: PASS (the single P1 blocker BUILD-19 reported — empty
`reply` on every tool-calling turn, including the specifically-flagged
Safety SAFE case — is fixed and verified live on staging; BUILD-19's three
P2s (Vinmec Cyrillic-character glitch, unclear `SAFETY_BLOCKED` wording for
a not-yet-due dose, RAG/Vinmec latency) remain open, untouched by this
build's explicit scope, and do not block this status)

READY FOR PRODUCTION HARDENING: YES

READY FOR PRODUCTION: NO
