# BUILD-45 — Quality Improvement Loop #2

## 0. Precondition check

BUILD-44 production status was independently re-verified before any work
started (not trusted from a prior report claim, per standing instruction):

- `BUILD-44-DOCTOR-CHAT-QUEUE-TAKEOVER-REPORT.md` merge (PR #134) and
  `BUILD-44-PRODUCTION-VALIDATION-REPORT.md` (PR #136) are both real
  ancestors of `origin/main` (`git merge-base --is-ancestor` — true for
  both).
- The production validation report's own release gate reads
  `PRODUCTION STATUS: VERIFIED`, `READY FOR BUILD-45: YES`.
- Track B (`feature/drug-image-b07-chatbot-multimodal`) confirmed
  untouched — separate worktree, no files under this build's diff overlap
  it.
- Alembic head at the branch point: `0054`. Zero open PRs at start.

Baseline commit for this build: `fb563dc4` (merge of PR #136 into `main`).
Precondition satisfied — proceeded.

## 1. Candidate audit

Per the spec's four named candidates, each audited against real code and
(where practical) real data before any fix was designed.

### Candidate A — Cold drug entity binding

**Confirmed real, with live evidence.** BUILD-44's own production canary
(scenario walk against `doctor@vmec04.dev` / `MCK@gmail.com`) and this
build's own audit of `_resolved_drug_entity` (`backend/api/
agent_v2_routes.py`) both independently show the same gap: a cold turn
that only calls `search_drug` (the common shape — `get_drug_info`
structurally requires an already-known `legacy_drug_id`, which a cold
turn doesn't have yet) never promotes an `ActiveEntity`, even when the
query names one specific, unambiguous product. A pronoun follow-up on the
very next turn then has no entity to inherit and falls back to a generic
decline. Root cause is structural (a real code gap), not phrasing-
specific, and Candidate A's own fix targets it at the tool-contract layer
(a new server-computed uniqueness signal), matching the spec's explicit
instruction not to solve this with per-phrase regexes or by trusting an
unconfirmed fuzzy top-1 guess.

### Candidate B — Topic persistence coverage

**Confirmed real, with live evidence, and a second bug found only by
running the fix's own local E2E.** Audit of `_DISPLAY_TOPIC_PATTERNS`
found it independently *duplicated* between `orchestrator.py` and
`follow_up.py::_explicit_topic`, already drifted apart (one file had a
shape the other lacked), and missing/wrong on every one of the spec's own
four worked examples (`"X là bệnh gì"`, `"X do đâu"`, the no-connector
`"nguyên nhân X là gì"` — which didn't just fail to match, it matched the
generic catch-all and captured the wrong substring — and ASCII-folded
variants of all shapes). A dedicated real local E2E (no seeded state) run
against the fix additionally surfaced a related, more serious bug not in
any of the spec's named examples: a compound sentence combining a
pronoun with a specific shape (`"Triệu chứng của nó là gì?"`) corrupted
`active_topic` to the literal string `"nó là gì"` instead of correctly
inheriting the prior topic. See §6/§7 for the full account.

### Candidate C — Durable `AgentRun.intent` semantics

**Audited, real gap confirmed, not selected.** `CheckpointCreateCommand`/
`create_or_load_checkpoint` (`backend/services/agent_checkpoint.py`) write
`AgentRun.intent` exactly once, at checkpoint creation, from that turn's
`raw_decision.intent.value` — it is never updated on a later turn of the
same run/conversation. For a multi-turn conversation whose intent
genuinely changes (e.g., starts as `DRUG_INFORMATION`, becomes
`GENERAL_MEDICAL_INFORMATION` after a topic switch), the durable
`AgentRun.intent` column still reads the *first* turn's intent, which
under-serves any admin/monitoring query that groups or filters runs by
intent. This is a real, confirmed gap — but it is a durable-schema-
semantics question (what should "the run's intent" mean for a
checkpoint-spanning, multi-turn run — first, last, or a list?) that
deserves its own decision and its own admin/monitoring-consumer audit,
not a quick patch inside a 2-candidate bounded loop. Deferred (§17).

### Candidate D — Retrieval phrasing sensitivity

**Screened, not fully reproduced, not selected.** Candidates A and B
alone already produced two confirmed, independently-reproduced defects
with real evidence (A: flagged live during BUILD-44's own production
validation; B: a corrupted-state bug found via this build's own E2E) —
enough to fill the spec's "select maximum 2" bound before D's own
reproduction work was undertaken. Note for honesty: this report does not
claim a specific finding for D beyond "not disproven, not prioritized
this loop" — it is listed as a deferred candidate for a future loop
(§17), not ruled out.

## 2. Candidate ranking

| Candidate | Real evidence | User-facing impact | Fix scope | Selected |
|---|---|---|---|---|
| A — cold entity binding | Confirmed live (BUILD-44 canary) + code audit | High — every cold drug question | Tool-contract + one route function | **YES** |
| B — topic persistence | Confirmed via code audit + own E2E (2 distinct bugs) | High — every disease/topic follow-up | One shared pattern source + 2 rejection guards | **YES** |
| C — `AgentRun.intent` | Confirmed via code audit | Low — admin/monitoring only, no user-facing effect | Schema-semantics decision needed first | NO (deferred) |
| D — retrieval phrasing | Not reproduced this loop | Unknown | Unknown | NO (deferred) |

## 3. Selected candidates

**Candidate A** (cold drug entity binding) and **Candidate B** (topic
persistence coverage) — 2, at the spec's stated maximum.

## 4. Reproduction before code (real evidence, not assumed)

**Candidate A** — real local trace before any fix: a fresh conversation,
query `"Berocca Bayer dùng để làm gì?"` (later re-used, see §11), produced
`tools=['search_drug']`, `active_entity=None` persisted. The very next
turn, a pronoun follow-up (`"Tác dụng phụ thì sao?"`), had nothing to
inherit and produced a generic "no drug named" decline instead of an
answer about the actual drug just discussed — reproduced against the real
model, real Postgres, real catalog, no seeded state.

**Candidate B** — real trace before any fix, against
`_display_topic_from_raw` directly (see §12 for the full fixed
before/after table): `"Viêm gan B là bệnh gì?"` → `None` (topic never
established on the first turn at all); `"Nguyên nhân đau đầu là gì?"` →
`"Nguyên nhân đau đầu"` (wrong — the connector words leaked into the
topic); `"Nó có nguy hiểm không?"` → `"Nó"` (a bare pronoun captured as
if it were a real topic — a pre-existing false-positive-safety gap,
found by this build's own audit, distinct from the compound-sentence bug
found later via E2E).

## 5. Root cause

**Candidate A**: `_resolved_drug_entity` only ever promoted an
`ActiveEntity` from `get_drug_info` evidence. `get_drug_info` requires an
already-known `legacy_drug_id`, which a cold turn — by definition — does
not have. The natural model behavior on a cold drug-name question is to
call `search_drug` only. The route layer had no path from "an unambiguous
`search_drug` result" to a canonical entity at all; the retrieval-side
fuzzy scorer's own 0.20 "browsing" floor was never designed or safe to
use for identity resolution (see §5 for the calibration evidence in the
original audit — 0.20 lets a query for one product's *exact* full name
also match 100+ unrelated catalog rows via shared manufacturer/dosage/
packaging tokens).

**Candidate B** — two distinct, confirmed root causes:
1. `_DISPLAY_TOPIC_PATTERNS` was independently duplicated in two files and
   incomplete/wrong on several real sentence shapes (missing "X do đâu",
   missing ASCII-folded variants entirely, and a no-connector "nguyên
   nhân X là gì" falling through to the generic catch-all and capturing
   the wrong substring).
2. (Found only by running the fix's own local E2E against a real model,
   not by any synthetic test.) The symptom/danger/prevention/continuation
   patterns' capture groups did not exclude a trailing "là gì" filler tail
   the way the cause/definition patterns' own regexes already did. A
   compound sentence combining one of those shapes with a pronoun and a
   trailing "là gì" (`"Triệu chứng của nó là gì?"`) captured the whole
   remainder `"nó là gì"` (pronoun + filler) as the topic. That composite
   string does not equal any single entry in `_PRONOUN_ONLY_WORDS`, so the
   existing bare-pronoun rejection did not catch it, and the corrupted
   string was persisted as `active_topic`, silently overwriting the real
   prior topic.

## 6. Fix design

**Candidate A** (`backend/services/drug_knowledge/v2_agent.py`,
`backend/services/agent_read_only_tools.py`, `backend/agents/v2/tools.py`,
`backend/api/agent_v2_routes.py`):

- Extracted `_ranked_catalog_matches(query)` from `search_catalog` — the
  one full, untruncated ranked list both `search_catalog` and the new
  method read from, so a query's true candidate count is never re-derived
  from an already-`limit`-truncated list.
- New `_UNIQUE_MATCH_SCORE_FLOOR = 0.90` (deliberately much stricter than
  `search_catalog`'s own 0.20 browsing floor — a separate, decoupled
  constant, not a change to `search_catalog`'s own behavior). Empirically
  validated against the real catalog: 30/30 real items resolve to
  themselves uniquely at 0.90 when queried by their own exact name; 0.20
  gave 0/30 (matched 100+ unrelated rows each).
- New `search_catalog_unique_match(query) -> DrugCatalogItem | None`:
  returns the single item **only** when exactly one catalog entry scores
  `>= 0.90`. Explicitly returns `None` for the doctor-combobox short-
  prefix branch (a different, unsafe-for-identity scoring scheme).
- `search_drug` (the read-only domain tool) now also returns
  `unique_match_legacy_drug_id` in its result dict.
- `SearchDrugOutput` (the Pydantic Tool Gateway contract) gained the same
  field — **required**, not cosmetic: `ToolGateway.execute()` re-
  serializes every raw tool dict through `output_model.model_validate(
  raw).model_dump()`, which silently drops any undeclared key (found via
  real debugging in this build, see §7).
- `_resolved_drug_entity` gained a new fallback, checked only when the
  `get_drug_info`-based path (unchanged) finds nothing: if exactly one
  `search_drug` call happened this turn and its
  `unique_match_legacy_drug_id` is set, promote that entity. Multiple
  distinct `search_drug` calls in one turn fall through to `None` rather
  than guess which search "counts" — zero extra model or tool calls; this
  only reads evidence the run already produced.

**Candidate B** (`backend/agents/v2/orchestrator.py`,
`backend/agents/v2/follow_up.py`):

- `_DISPLAY_TOPIC_PATTERNS` is now defined exactly once
  (`orchestrator.py`), widened to cover every spec-named shape plus its
  ASCII-folded variant, with the no-connector cause pattern checked
  *before* the generic definition catch-all.
- `follow_up.py::_explicit_topic` now imports this tuple via a function-
  local import (deferred to call time — `orchestrator.py` already imports
  *from* `follow_up.py` at module level, so a module-level import back
  would be circular). Its own rejection vocabulary
  (`_ATTRIBUTE_KEYWORDS`/`_PRONOUN_ONLY_WORDS`/deictic containment) is
  deliberately *not* shared — it is independently tuned for the follow-up-
  classification decision, a different consumer of the same pattern
  shapes.
- New `_TRAILING_LA_GI_TAIL` regex, applied to **every** pattern's capture
  (not just the ones whose own regex already excludes the tail) before the
  existing pronoun check runs — idempotent where the tail is already
  excluded, and closes the compound-sentence corruption bug for the
  patterns where it wasn't (§5.2).
- `_display_topic_from_raw` gained the bare-pronoun rejection check
  `follow_up.py` already had for its own purpose (`_explicit_topic`) but
  this function — which feeds the *same* `active_topic` state write for
  every turn, not just follow-ups — never had.
- `follow_up.py::_explicit_topic` also gained a deictic-*containment*
  check (`_has_deictic_marker`, reusing the existing `_DEICTIC_MARKERS`
  list), fixing a real regression the pattern-widening itself exposed in
  the pre-existing BUILD-43 suite (§7).

## 7. State / tool / retrieval invariants preserved

- **Entity binding remains evidence-gated, never guessed.** Candidate A's
  new fallback only fires on a *structural* uniqueness signal computed
  server-side from the full catalog, at a floor 4.5x stricter than the
  browsing scorer — never on an LLM's own claim, never on a truncated
  top-1.
- **Topic switch still clears stale state.** Candidate B's changes are
  entirely inside "what counts as an explicit topic" — the existing
  `is_topic_switch` → `replace(conversation_state, active_topic=None,
  active_entity=None)` logic in `agent_v2_routes.py` (BUILD-43) is
  untouched.
- **Retrieval query construction (`_CAUSE_PATTERNS`/`_DEFINITION_PATTERNS`/
  `_SYMPTOM_PATTERNS`/`_DANGER_PATTERNS`/`_PREVENTION_PATTERNS`/
  `_URGENCY_PATTERNS`, `normalize_semantic_medical_query`) is untouched.**
  `_DISPLAY_TOPIC_PATTERNS` is a deliberately separate, smaller pattern
  family scoped only to display-safe state persistence — confirmed by
  `git diff` showing zero changes to the retrieval-side tuples.
- **Zero new synchronous model calls.** Both fixes read evidence a turn's
  existing tool calls already produced (Candidate A) or are pure string
  pattern-matching on the raw message (Candidate B) — confirmed by every
  local E2E run showing the same `tools=[...]` list before and after.
- **The Tool Gateway contract is still declarative and fails closed** — no
  raw dict is ever passed through without validation; the new field is
  `str | None = None`, so a domain tool that doesn't set it degrades to
  the pre-existing `None` behavior, not an error.

## 8. Before/after evaluation (real numbers, real data)

### Candidate A — canonical entity establishment

Real catalog, 3,556 distinct products. Random sample of 60 (seed 45),
querying each item by its own exact `ten_thuoc`:

| Metric | Before | After |
|---|---|---|
| Canonical entity established on a cold `search_drug`-only turn | 0% (structurally impossible — no code path existed) | **60/60 = 100%** (real catalog self-match sample) |
| False entity binding rate (binds when genuinely ambiguous) | N/A (no binding existed) | **0/N** — every ambiguous-search unit test (multi-candidate, shared-manufacturer-noise, short-prefix) asserts `None` |
| Ambiguous auto-bind rate (multiple `search_drug` calls in one turn) | N/A | **0/N** — falls through to `None` by design, tested |
| Follow-up success rate (pronoun inherits the just-discussed drug) | Fails (generic decline) | Real local E2E: 1/1 (small N — see §16 known limitations; the mechanism itself is covered by 13 deterministic unit/gateway tests, not resting on E2E sample size alone) |

### Candidate B — topic persistence accuracy

Fixed set of 16 real-shape phrases (the spec's own 4 named worked
examples + their ASCII-folded variants + the false-positive-safety locks
+ the compound-sentence bug found via E2E), each with a known-correct
expected extraction, run against `_display_topic_from_raw` directly on
the real baseline commit (`fb563dc4`, via `git stash`) and again on the
fixed code:

| Metric | Before | After |
|---|---|---|
| Topic extraction accuracy (16 fixed real-shape cases) | **5/16 = 31%** | **16/16 = 100%** |
| Stale-topic-not-cleared regressions | 0 (pre-existing clearing logic untouched) | 0 |
| False-positive topic capture (bare pronoun / drug-attribute question) | **1 confirmed pre-existing gap** (`"Nó có nguy hiểm không?"` → `"Nó"`) | 0/2 named lock cases |
| Pronoun-follow-up resolution (real local E2E, no seeded state) | N/A (topic never established turn 1, so nothing to inherit) | Real E2E: topic established turn 1, correctly inherited turn 2, correctly cleared turn 3 (1/1 full scenario — see §16) |

The before/after table above is a real, reproducible measurement (script
retained ad hoc, not committed — the 16 cases are captured permanently as
assertions across `test_agent_v2_build45_topic_persistence.py` instead),
not an estimate.

## 9. False-positive-safety analysis (spec §13 critical tests)

| Critical case | Test | Result |
|---|---|---|
| Ambiguous drug search → no auto-bind | `test_agent_v2_build45_cold_entity_binding.py` (multiple unit tests: genuinely ambiguous query, multi-search-in-one-turn) | PASS |
| Pronoun with no context → no fabricated topic/entity | `test_bare_pronoun_still_never_becomes_a_topic`, `test_c_deictic_this_drug_inherits_entity` (only inherits when a real prior entity exists) | PASS |
| Topic switch → stale state cleared | Real local E2E §3 (Paracetamol switch clears `active_topic`/`active_entity`) | PASS |
| Unrelated short question → no inherited old state | `test_a4_short_standalone_does_not_inherit_unrelated_prior_drug`, `test_stale_entity_not_inherited_on_explicit_new_topic`, and the newly-added `test_h_unrelated_short_standalone_question_does_not_inherit_prior_topic` (closes the topic-side gap — only the entity-side case had a named test before this build) | PASS |
| Compound pronoun+filler sentence → no corrupted topic (found this build, not spec-named) | `test_compound_symptom_plus_pronoun_la_gi_tail_is_rejected_not_a_topic` | PASS |
| Drug-attribute question → still rejected, not a topic | `test_drug_attribute_question_is_still_rejected_not_a_topic` (BUILD-29D.3 regression, re-verified) | PASS |

## 10. Local E2E (real Postgres, real model, no seeded state)

**Candidate A** — `scripts/agent_v2/build45_cold_entity_binding_local_e2e.py`:
turn 1, `"Thuốc Berocca Bayer dùng để làm gì?"` (query deliberately chosen
after verifying against the real catalog it resolves uniquely, unlike a
bare `"Paracetamol"`, which genuinely has multiple real SKUs and correctly
stays ambiguous) → `active_entity` established with the real display name
`"Berocca Bayer 10v"`, `tools=['search_drug']` only. Turn 2, a natural
pronoun/attribute follow-up (no button, no re-naming the drug) → correctly
calls `get_drug_info`/references the drug by name, no `GROUNDING_FAILURE`.
**Result: ALL CHECKS PASSED.**

**Candidate B** — `scripts/agent_v2/build45_topic_persistence_local_e2e.py`:
turn 1, `"Viêm gan B là bệnh gì?"` → `active_topic` established
(`canonical_name='Viêm gan B'`). Turn 2, `"Triệu chứng của nó là gì?"` (a
real compound pronoun+filler sentence, the exact shape that exposed the
§5.2 bug) → reply genuinely about viêm gan B, and — after the fix in this
same session — `active_topic` correctly *stays* `'Viêm gan B'` (before the
fix, this same script observed it silently corrupted to the literal
string `'nó là gì'`, caught by strengthening this script's own assertion
mid-build rather than accepting a weaker "is it still set at all" check).
Turn 3, `"Paracetamol dùng để làm gì?"` → real topic switch,
`active_topic=None active_entity=None` correctly cleared. **Result: ALL
CHECKS PASSED.**

## 11. Durable evidence cross-check

Both E2E scripts read state the same way the real API route does:
`AgentConversationStateStore().load(db, actor_id=..., patient_id=...,
conversation_id=...)` against real Postgres, after a real
`run_agent_orchestration` call (the same function `POST /api/v1/agent/v2/
orchestrate` calls) — not a mock, not a re-derivation. Each script prints
the real `status`/`intent`/`tools` from the `OrchestrationResult` returned
to the route layer alongside the persisted `ConversationState`, so the
HTTP-equivalent result and the durable state are cross-checked in the same
run, not asserted independently. No new `AgentRun`/trace/evaluation
metadata fields were added or read by this build (neither candidate
touches durable schema), so no additional cross-check surface exists
beyond what both scripts already exercise.

## 12. Performance / cost

Both fixes are designed for, and confirmed to produce, **zero new
synchronous model or tool calls**:

- Candidate A reads a field (`unique_match_legacy_drug_id`) computed
  inside the *existing* `search_drug` call's own domain-service logic
  (one extra in-process ranked-list scan over an already-loaded in-memory
  catalog, not a new DB query, not a new tool invocation) — confirmed by
  every local E2E run showing an unchanged `tools=[...]` list before and
  after.
- Candidate B is pure string pattern-matching on the raw message text,
  same as the pre-existing code it replaces — no I/O, no new call sites.

No token/latency/cost regression is expected or observed; a
before/after latency measurement was not separately instrumented because
neither change sits on a path with a new I/O or model call to measure.

## 13. Regression

Full suite (excluding two unrelated collection-only failures from a
missing `cv2`/`numpy` install in this environment — the VLM/image-
recognition track, explicitly out of scope): `pytest tests/ -k "agent_v2
or drug_knowledge or safety" --ignore=tests/services/photo_verification
--ignore=tests/vlm_demthuoc` → **1129 passed, 11 failed, 7 skipped**.

All 11 failures independently reconfirmed pre-existing on the clean
baseline (`git stash`, re-run against `fb563dc4`, same 11 failures, same
error messages):
- 7 in `test_agent_v2_safety_occurrence_binding.py` — the already-
  documented Track B B-06 `drug_id_map`/`drug_image` SQLite-fixture gap
  (memory: `agent-v2-build-log.md`).
- 3 in `test_agent_v2_long_term_memory.py` + 1 in
  `test_safety_runtime_adapter.py` — newly observed by this build's
  broader sweep, but confirmed pre-existing and unrelated (same failures,
  same tracebacks, on the unmodified baseline; no file this build touches
  is imported by either).

All 7 skips are the standard "set `<BUILD>_TEST_DATABASE_URL`" conditional
skips for optional real-Postgres concurrency tests, pre-existing across
every prior build.

Targeted re-runs, all passing, of every suite the spec named:
- BUILD-40 router / BUILD-42 answerability / BUILD-43 follow-up: covered
  by the broad sweep above (`test_agent_v2_orchestrator.py`,
  `test_agent_v2_follow_up.py`, `test_agent_v2_answerability_*`).
- BUILD-44 doctor takeover: `test_agent_v2_doctor_handoff.py`,
  `test_agent_v2_doctor_handoff_postgres.py`,
  `test_agent_v2_doctor_takeover.py`, `test_api/test_doctor_review_routes.py`
  — all pass.
- Safety / Dose Safety: `test_v2_dose_safety_http.py` — passes; Safety
  suites covered by the broad sweep.
- Schedule/time: covered by the broad sweep, no failures.
- Grounding: `test_agent_v2_grounding_precision.py`,
  `test_agent_v2_medical_grounding.py` — both pass.
- Retrieval / auth / monitoring: not touched by this build's diff — N/A,
  verified via `git diff --name-only`.

`ruff check` on every changed/new file (8 modified + 4 new): **all
checks passed**.

## 14. Known limitations

- Candidate A's local-E2E follow-up-success proof is 1 real scenario (§8
  table), not a statistically powered sample — the underlying mechanism
  (uniqueness scoring, gateway field survival, route-layer promotion) is
  separately covered by 13 deterministic unit/gateway tests plus a real
  60/60 catalog self-match sweep; the E2E's role here is to prove the
  natural multi-turn flow actually works end-to-end, not to establish a
  statistical rate.
- Candidate B's before/after topic-extraction accuracy (§8) is measured
  against a fixed, hand-curated 16-case set (the spec's own named
  examples plus this build's own finds), not a random sample of real
  production traffic — no representative corpus of real disease/topic
  phrasings exists to sample from for this specific metric.
- `_TRAILING_LA_GI_TAIL` stripping is applied uniformly to every pattern's
  capture; it was verified not to break any existing shape (§13 full
  regression), but a not-yet-observed sentence shape that legitimately
  ends its *topic name itself* in "là gì"-like words (none found in the
  real catalog or the 16-case set) is a theoretical edge this build did
  not specifically search for beyond the regression suite.

## 15. Deferred findings (explicitly not fixed in this build)

- **Handoff dedup type-bug** (`AuthorizedDoctorHandoffAdapter.create`,
  `backend/services/agent_doctor_handoff.py:79-86`, scopes reuse only by
  `patient_id` + open status, not by `risk_disposition`/type) — found live
  during BUILD-44's production validation, documented in memory
  `agent-v2-handoff-dedup-type-bug.md`. Per the spec's own explicit
  instruction, **not touched by this build**.
- **Candidate C** (`AgentRun.intent` semantics for multi-turn runs) —
  audited, real gap confirmed, deferred pending a schema-semantics
  decision (§1).
- **Candidate D** (retrieval phrasing sensitivity) — screened, not
  reproduced this loop, deferred (§1).
- Railway CI `RAILWAY_TOKEN` invalid, frontend CRLF baseline, Track B
  B-06 test-fixture debt — all pre-existing, out of this build's scope,
  already documented in `agent-v2-build-log.md`.

## 16. BUILD-46 dependency

No new dependency created for BUILD-46 beyond what already existed
(BUILD-44's dedup bug, Candidate C, Candidate D — all listed in §15 as
candidates for a future loop or dedicated fix, not blocking). BUILD-46 is
free to pick any of these, or a fresh audit pass, without any ordering
constraint this build introduces.

## 17. Release Gate

```
CANDIDATES AUDITED: 4 (A, B, C, D)
CANDIDATES SELECTED: 2 (A: cold drug entity binding, B: topic persistence coverage)
CANDIDATE A STATUS: PASS
CANDIDATE B STATUS: PASS
CANDIDATE C STATUS: NOT_SELECTED (real gap confirmed, deferred — schema-semantics decision needed)
CANDIDATE D STATUS: NOT_SELECTED (not reproduced this loop, deferred)

CANDIDATE A — canonical entity established rate (real catalog, n=60): 100% (60/60)
CANDIDATE A — false entity binding count: 0
CANDIDATE A — ambiguous auto-bind count: 0
CANDIDATE B — topic extraction accuracy (16 fixed real-shape cases): before 31% (5/16) -> after 100% (16/16)
CANDIDATE B — false-positive topic capture count: 0 (2 named lock cases, both PASS)
CANDIDATE B — stale-topic/entity regression count: 0
CANDIDATE B — corrupted-topic bug (compound pronoun+filler sentence): FOUND via own E2E, FIXED, regression test added

MODEL CALL BUDGET INCREASE: 0 (structurally — both fixes read existing evidence or are pure pattern-matching)
TOOL CALL BUDGET INCREASE: 0

LOCAL E2E (real Postgres, real model, no seeded state): PASS (both candidates)
DURABLE EVIDENCE CROSS-CHECK: PASS (HTTP-equivalent result + ConversationState cross-checked in the same run)

FULL REGRESSION SUITE: 1129 passed, 11 failed (all independently reconfirmed pre-existing on clean baseline fb563dc4, unrelated), 7 skipped (pre-existing conditional Postgres-only skips)
RUFF: PASS (all changed/new files)

SAFETY REGRESSION: NONE
HANDOFF DEDUP TYPE BUG FIXED: NO — OUT OF SCOPE (per explicit instruction)
TRACK B MODIFIED: NO
MIGRATION CHANGES: NONE (alembic head unchanged at 0054)
RETRIEVAL QUERY CONSTRUCTION MODIFIED: NO (_CAUSE_PATTERNS/_DEFINITION_PATTERNS/etc. untouched, confirmed via diff)

READY FOR REVIEW: YES
READY TO MERGE: NO — awaiting human review (per standing PR process)
READY TO DEPLOY: NO — no production validation performed this build (in scope for a future BUILD, same pattern as BUILD-40->41, BUILD-44->44-production-validation)
```

## 18. Branch / PR

Branch: `feature/build-45-quality-loop-2`, based on `main` at `fb563dc4`
(post PR #136 merge). Commit and PR opened per standing process; **STOP**
after PR is opened — no merge, no deploy, no BUILD-46, no handoff-dedup
fix, no Track B changes, per explicit instruction.

## 19. Code review response (round 1, post-push)

Two automated findings on PR #141, both verified against the real code
(not assumed true or false) before acting.

**Finding 1 — `search_catalog_unique_match` scoring/sorting discrepancy.**
The quoted snippet was accurate to the real code. The specific framing
("a 'unique match' might not actually be the top result returned by a
standard search") does not hold under the current scoring model —
`strong_matches` only ever has length 1 when exactly one item scores
`>= 0.90` and every other item scores strictly lower, so that item is by
construction the single highest-scoring item in the whole catalog for
that query, i.e. always `search_catalog`'s own top-ranked result too; no
sort-order disagreement is possible. The real, underlying finding was
correct, however: `search_catalog_unique_match` ran its **own separate**
`self._name_score(...)` loop over `self.catalog_items` instead of reusing
`_ranked_catalog_matches`, and that function's own docstring falsely
claimed both methods read from it — a genuine documentation/duplication
defect. **Fixed**: extracted `_scored_catalog_items(query)` (the raw,
unsorted, unfiltered `_name_score` list) as the one real shared source
both `_ranked_catalog_matches`'s normal-length-query branch and
`search_catalog_unique_match` now read from; corrected both docstrings to
state the true relationship (they share the score computation, not each
other's filter/sort, which are intentionally different — 0.20-floor+full
sort vs. 0.90-floor+no sort, the latter safe by construction as explained
above). The short-single-token prefix branch (a different, non-
`_name_score` scheme) was confirmed to never have been part of either
docstring's claimed sharing and stays untouched. Full regression re-run
after the change: identical 1129 passed / 11 pre-existing-unrelated
failed / 7 skipped; both real local E2E scripts re-run end-to-end,
unchanged results.

**Finding 2 — function-local import in `_explicit_topic` (circular-
dependency fragility).** Confirmed as a real architectural fragility,
though not a live bug: the deferred/function-local import safely avoids
today's circularity (no top-level call site exists that would trigger it
mid-initialization), but the reviewer's hypothetical — a future refactor
introducing a top-level call from inside `orchestrator.py`'s own module
initialization — could still break it, since a lazy import only defers
*when* a failure would surface, not the underlying fragility. **Fixed by
removing the fragility class entirely, not by defending it further**:
`_DISPLAY_TOPIC_PATTERNS`, `_DRUG_ATTRIBUTE_QUESTION_KEYWORDS`,
`_TRAILING_LA_GI_TAIL`, and `_display_topic_from_raw` were moved from
`orchestrator.py` into `follow_up.py` — the module `orchestrator.py`
already imports several other names from at its own module level, with
no circularity, since `follow_up.py` has zero dependency on
`orchestrator.py` in either direction. `orchestrator.py` now imports
`_display_topic_from_raw` from `follow_up.py` at module level (the same
already-safe direction as its other imports from that module);
`_explicit_topic` now references `_DISPLAY_TOPIC_PATTERNS` directly, in
the same module, with no import at all. Verified the move is a pure
relocation, not a behavior change: `orchestrator._display_topic_from_raw
is follow_up._display_topic_from_raw` (identity, not a copy), full
regression re-run identical (1129/11/7, same as before the move), both
real local E2E scripts re-run end-to-end unchanged. `ruff check` clean
after both fixes (one auto-fixable import-order finding from the moved
import, applied via `ruff check --fix`).

Both fixes pushed as a follow-up commit on the same branch/PR; no merge,
no deploy — same STOP condition as §18.
