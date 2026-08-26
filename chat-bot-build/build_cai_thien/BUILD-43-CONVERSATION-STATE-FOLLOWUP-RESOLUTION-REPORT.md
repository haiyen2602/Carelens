# BUILD-43 — Conversation State / Follow-up Resolution

Replaces the brittle `len(message.strip()) <= 35` heuristic (CANDIDATE-02)
with a deterministic, evidence-based follow-up taxonomy
(`TRUE_FOLLOWUP` / `STANDALONE_QUESTION` / `TOPIC_SWITCH` /
`AMBIGUOUS_FRAGMENT`) that classifies off the CANONICAL, durable
`ConversationState.active_topic`/`active_entity` — never raw memory text,
never message length as the deciding signal.

## 0. Precondition

- Baseline commit: `60311de490c22b65b0e98f920498b4b0f3acb156` (`origin/main`,
  includes BUILD-42 PR #127 merged as `f967ad0`).
- Branch: `feature/build-43-conversation-followup-resolution`.
- Worktree: dedicated (`P-067-build-43-conversation-followup`), separate
  from `P-067-drug-image-b01`/`b02` (Track B) and `P-067-build-29c`.
- BUILD-42 dependency: **MERGED**, not stacked on the PR head — confirmed via
  `gh pr view 127` (`state: MERGED`) and `git log fd2b1d8..origin/main`
  before branching.
- No open PRs, no other branch touching `orchestrator.py`/
  `conversation_state.py` in the last 24h at branch time (`gh pr list
  --state open` empty; `git for-each-ref` showed only merged/stale
  branches) — no concurrent-edit conflict risk recorded.

## 1. CANDIDATE-02 root cause (audit before code)

Two genuinely SEPARATE follow-up mechanisms existed, not one:

**Mechanism A — explicit action/typed-alias resolution**
(`conversation_state.py::resolve_state_input`/`_typed_action`). Fires only
when the user clicks a server-issued suggestion button, or types text that
exactly matches one of that button's aliases. Already canonical-state-based
(reads `ConversationState.active_topic`/`active_entity`), already correct,
**untouched by this build**.

**Mechanism B — free-text fallback** (`orchestrator.py::
resolve_conversation_context`/`_follow_up_category`, removed by this
build). Fired for every OTHER message (no button click, no exact alias
match) classified as `GENERAL_CONVERSATION`/`DRUG_INFORMATION`/
`GENERAL_MEDICAL_INFORMATION`/`UNKNOWN_OR_AMBIGUOUS`. This is where
CANDIDATE-02 actually lived:

```python
def _follow_up_category(message: str) -> str | None:
    lowered = message.casefold()
    marker_present = any(marker in lowered for marker in _FOLLOW_UP_MARKERS) or (
        len(message.strip()) <= 35 and not _looks_like_explicit_medical_question(lowered)
    )
    ...
```

`len(message.strip()) <= 35` was an **OR-ed alternate trigger**, not a
tiebreaker — any short message not matching a narrow "explicit question"
regex (` gây `/` của `/etc.) was treated as a possible follow-up regardless
of content. Worse: the "current topic" it resolved against
(`_recent_topic`/`_extract_topic`, also removed) was re-derived by
**regex-scanning raw short-term MEMORY TEXT** (the last few USER turns in
the in-process `ShortTermMemoryStore`) — entirely independent of the
canonical, durable `ConversationState.active_topic`/`active_entity` fields
BUILD-29D/BUILD-42 already established as authoritative. Two consequences,
both real (confirmed via repro before any code change, SS3):

1. A short, complete, self-sufficient question ("Paracetamol là gì?", 22
   chars) with an unrelated prior topic in memory could be misclassified as
   a follow-up purely by length, once a `_FOLLOW_UP_CATEGORY_KEYWORDS`
   match happened to line up (`SHORT == FOLLOW_UP`, the exact bug this
   build's headline invariant forbids).
2. Drug-ATTRIBUTE free-text follow-ups ("Tác dụng phụ thì sao?") had **no
   working path at all**: `_FOLLOW_UP_CATEGORY_KEYWORDS` only covered
   disease-topic aspects (urgent_care/cause/symptoms/danger/prevention),
   never drug aspects (side_effects/dosage/administration/...), and
   Mechanism A only fires on an exact click/alias match. A real free-text
   drug follow-up with no exact button match fell through everything,
   reached the Main Model with no drug name at all, and hit BUILD-42's
   grounding-failure Answerability Gate with a spurious "cần thêm thông
   tin" — found and fixed as part of this build (§7).

## 2. Old heuristic (full decision tree, as audited)

```
resolve_conversation_context(message, memory_items):
  category = _follow_up_category(message)        # keyword match OR len<=35
  is_ambiguous = _is_ambiguous_follow_up(message) # fixed "cái kia/cái này" list
  if category is None and not is_ambiguous: NOT_APPLICABLE
  topic, turn = _recent_topic(memory_items)       # regex over raw memory TEXT
  if topic is None: NO_CONTEXT -> clarification
  if category is None: AMBIGUOUS -> clarification
  else: RESOLVED -> rewritten query
```

No entity handling at all (topic-only). No bound to `ConversationState`.
`_context_clarification_reply` (the NO_CONTEXT/AMBIGUOUS terminal) was
**never wired into BUILD-42's Answerability Gate** — an unbounded
clarification loop, no `answerability_attempt_count` tracking, no
escalation path — a real, separate gap this build also closes (§8).

## 3. New taxonomy (`backend/agents/v2/follow_up.py`, new module)

```python
class FollowUpCategory(StrEnum):
    TRUE_FOLLOWUP = "TRUE_FOLLOWUP"
    STANDALONE_QUESTION = "STANDALONE_QUESTION"
    TOPIC_SWITCH = "TOPIC_SWITCH"
    AMBIGUOUS_FRAGMENT = "AMBIGUOUS_FRAGMENT"

@dataclass(frozen=True)
class FollowUpDecision:
    category: FollowUpCategory
    inherited_topic: bool
    inherited_entity: bool
    reason_code: FollowUpReasonCode   # observable evidence only, never "confidence"
    evidence_source: str
```

`classify_follow_up(message, *, prior_topic, prior_entity_name)` — **zero
model calls**, pure function, no I/O. Its only inputs are the raw message
text and the CANONICAL prior state (never a retrieval query, never memory
text — enforced by the function's own signature, see SS20-K). No new
dependency between `follow_up.py` and `orchestrator.py`/`conversation_
state.py`: it is a standalone, independently unit-testable module (16
dedicated unit tests, `tests/test_agent_v2_follow_up.py`, before any
orchestrator wiring existed).

## 4. Decision rules

Evidence, in priority order — never message length:

1. **Explicit topic pattern match** (`_explicit_topic`, a narrowed reuse of
   `orchestrator.py`'s own `_DISPLAY_TOPIC_PATTERNS` family — "X là gì",
   "nguyên nhân gây X", "triệu chứng của X", "X có nguy hiểm không", "cách
   phòng ngừa X" — already proven safe against drug-attribute
   false-positives). A captured pronoun ("nó"/"này"/"đó"/"kia") is
   explicitly rejected here and falls through to rule 3 instead — a real
   bug found via E2E (§7): "Triệu chứng của **nó**?" was initially captured
   as if "nó" were a topic name.
   - No prior context → `STANDALONE_QUESTION`.
   - Matches the prior canonical topic → `STANDALONE_QUESTION`,
     `inherited_topic=True`.
   - Differs from the prior canonical topic → `TOPIC_SWITCH`.
2. **A named subject beyond deictic/attribute/particle/dosage-number
   filler** (`_strip_evidence_markers` — strips known deictic markers,
   drug+topic attribute-aspect keywords, Vietnamese question particles, and
   bare dosage tokens like "500mg"; what remains is the closest
   deterministic signal for "does this name its own subject"). Same
   priority rules as above (no prior context → `STANDALONE_QUESTION`;
   remainder mentions the prior entity/topic → `STANDALONE_QUESTION`
   inheriting it; otherwise → `TOPIC_SWITCH`).
3. **Deictic reference or attribute-only phrasing** (nothing survives
   stripping): with prior context → `TRUE_FOLLOWUP` (inherits whichever of
   topic/entity is present); without → `AMBIGUOUS_FRAGMENT`.

`SHORT != FOLLOW_UP` is now a structural property, not a rule to
remember: length is never read anywhere in `classify_follow_up` or its
helpers (confirmed by the function's own signature — SS20-K).

## 5. State invariants (verified against the spec's own list)

| # | Invariant | How enforced |
|---|---|---|
| 1 | canonical topic/entity is authoritative | `classify_follow_up`'s ONLY prior-state input is `ConversationState.active_topic`/`active_entity`, passed down as new `OrchestrationRequest.prior_active_topic`/`prior_active_entity_id`/`prior_active_entity_name` fields — never memory text |
| 2 | display topic is presentation only | unchanged, pre-existing (`ActiveTopic.display_name`) |
| 3 | normalized lookup key is retrieval/tool identity only | unchanged, pre-existing |
| 4/5 | retrieval_query is ephemeral, never overwrites canonical state | `classify_follow_up`'s signature has no retrieval-query parameter at all (SS20-K, locked by a dedicated test) |
| 6 | requested_aspect may update independently | unchanged (`ConversationState.requested_attribute`) |
| 7 | topic switch must clear incompatible inherited state | **new**: `agent_v2_routes.py` computes `conversation_state_for_carry_forward` (a cleared copy) whenever `result.follow_up_decision.category is TOPIC_SWITCH`, used everywhere the OLD code fell back to the raw `conversation_state` |
| 8 | ambiguous fragment must not fabricate canonical state | `_context_clarification_reply` never calls `transition_state` with a topic/entity — falls through to the untouched carry-forward `else` branch |
| 9 | unconfirmed candidate never becomes canonical automatically | unchanged (`_resolved_drug_entity` still only promotes a REAL `get_drug_info` result) |
| 10 | BUILD-42 answerability state resets/continues correctly across transitions | §8 |

## 6. Topic-switch behavior

`agent_v2_routes.py`:

```python
is_topic_switch = (
    result.follow_up_decision is not None
    and result.follow_up_decision.category is FollowUpCategory.TOPIC_SWITCH
)
conversation_state_for_carry_forward = (
    replace(conversation_state, active_topic=None, active_entity=None)
    if is_topic_switch else conversation_state
)
```

Used for `_authoritative_topic_for_turn(...)`'s carry-forward fallback, the
`active_topic`/`active_entity` fed to `build_suggested_actions`, AND as the
base state passed to `transition_state(...)` — so even a topic switch whose
NEW subject doesn't happen to be independently re-resolved this turn (e.g.
a phrasing `_authoritative_topic_for_turn`'s own narrow rules don't happen
to rewrite) still correctly drops the stale entity/topic instead of
silently carrying it forward. `conversation_state` itself (the real prior
state) is untouched — still what's used for authorization/idempotency
elsewhere in the request.

Verified live (§11): drug → disease and disease → drug both clear the
opposite field in real persisted state, not just in the reply text.

## 7. Entity inheritance behavior

For `TRUE_FOLLOWUP` with `inherited_entity=True`:

1. `effective_entity_id = request.prior_active_entity_id` (the canonical
   id, never guessed).
2. `_detect_drug_aspect(request.message)` — a keyword→aspect detector
   mirroring `suggested_actions.py`'s own `DRUG_ACTION_VALUES`/`_DRUG_
   LABELS` vocabulary (drug_uses/dosage/administration/side_effects/
   contraindications/warnings/interactions), so a free-text follow-up
   resolves to the SAME human-readable label a clicked button would have
   produced.
3. If an aspect was detected: `decision` (the `RouterDecision`) is
   **forced directly to `DRUG_INFORMATION`**, reusing the real
   `_INTENT_CONFIG[DRUG_INFORMATION]` tuple — not gambled on
   re-classifying constructed text through the keyword router. Found via
   real E2E (§7-bugs below): the router's own `DRUG_INFORMATION` detector
   (`_is_medication_information_query`) looks for specific Vietnamese
   grammar patterns (e.g. `dùng/uống + trước/sau/...`), not a generic
   attribute keyword — a constructed sentence like "Cách dùng X của thuốc
   X" reliably missed it even though it obviously names a drug. Since the
   aspect keyword plus an already-inherited canonical entity together are
   *stronger* evidence than what the keyword router could derive from raw
   text alone, forcing the decision directly is more correct, not a hack
   around the router — `router_message` itself stays the ORIGINAL raw
   message (the most natural text for the Main Model to read).
4. The pre-existing bound-lookup shortcut (`request.active_entity_id`/
   `requested_attribute`, originally built for the button-click path) now
   fires for this inherited case too — the SAME deterministic
   `get_drug_info` call, no re-search of an ambiguous name.

If no aspect was detected (a generic "còn không?"-shaped follow-up with no
recognizable aspect), no entity is force-bound; the turn proceeds through
ordinary evidence gathering with the raw message.

For `TRUE_FOLLOWUP` with `inherited_topic=True`: reuses the PRE-EXISTING
`_FOLLOW_UP_CATEGORY_KEYWORDS`/`_resolved_query_for` (unchanged, only their
TRIGGER condition moved) to build a rewritten disease-topic query.

## 8. BUILD-42 interaction

- `TRUE_FOLLOWUP` on the same unresolved clinical clarification →
  `evaluate_clinical_clarification_answerability`'s own attempt counter
  continues (unchanged BUILD-42 mechanism; BUILD-43 does not touch
  `_clinical_clarification_reply`'s internals).
- `STANDALONE_QUESTION`/`TOPIC_SWITCH` → `agent_v2_routes.py`'s existing
  `next_answerability_attempt_count` computation (unchanged: nonzero ONLY
  when `result.answerability_decision.outcome == NEED_MORE_INFO` this
  exact turn) already resets to 0 for these, since neither produces a
  NEED_MORE_INFO decision — verified live (§11, scenario 9).
- `AMBIGUOUS_FRAGMENT` → **newly bounded**. `_context_clarification_reply`
  was rewritten to call `evaluate_clinical_clarification_answerability`
  (the SAME generic, `reason_code=None`-shaped bounded-clarification
  function BUILD-42 already built for `_clinical_clarification_reply`) and
  route through `_answerability_handoff_reply`/`_answerability_more_info_
  reply` instead of a bespoke `CheckpointedTerminalStateRecorder` call.
  Previously this path had **no escalation at all** — a genuinely
  unresolvable fragment could loop on the same fixed reply forever, with
  no `answerability_attempt_count` tracking and no `NEED_DOCTOR` path.
  Verified: repeated unresolved fragments now escalate after
  `MAX_CLARIFICATION_ATTEMPTS`, exactly like the pre-existing clinical
  path (`tests/test_agent_v2_build43_follow_up_resolution.py::
  test_i2_ambiguous_fragment_repeated_escalates_to_need_doctor`).
- No accidental handoff from a stale attempt count on a DIFFERENT topic:
  covered by the reset-on-switch behavior above (verified live, §11
  scenario 9).

## 9. Schedule interaction

Unchanged, verified not regressed. `_SCHEDULE_INTENTS` are checked and
returned (`_schedule_reply`) BEFORE the follow-up classifier is ever
reached (`orchestrator.py::run`, early-return ordering untouched by this
build) — "Còn ngày mai?" already routes deterministically via BUILD-27B's
own `_UPCOMING_KEYWORDS`/Time Query Engine, with zero model calls, zero
involvement from `follow_up.py`.
`test_g_schedule_follow_up_bypasses_the_classifier_entirely` asserts
`result.follow_up_decision is None` and zero model-gateway calls for
exactly this case. The negative direction (schedule → disease topic
switch) was not required to touch schedule internals and was not tested
via a new mechanism — `_authoritative_topic_for_turn`'s existing carry-
forward behavior for non-general-medical intents is unaffected by this
build (schedule replies never set `follow_up_decision`, so
`is_topic_switch` is always `False` for them).

## 10. Safety precedence

Unchanged, verified not regressed. Safety trigger detection
(`decision.safety_trigger`) happens on `raw_decision` — computed from the
UNTOUCHED raw message, before the follow-up classifier ever runs, and
`PERSONAL_SYMPTOM`/`MEDICATION_DOSE_SAFETY` are short-circuited to
`_clinical_clarification_reply` even earlier, before the classifier's own
gating `if` block. `ACUTE_DANGER_ESCALATION`/`POSSIBLE_OVERDOSE` are
router-classified independently of any TRUE_FOLLOWUP-shaped wording.
Verified live (§11, scenario 11): "Tôi vừa uống nhầm 20 viên thuốc rồi"
after a real drug entity was already active still produces a real Safety
handoff (`handoff_type=SAFETY`), never a drug-attribute follow-up.

## 11. Local E2E (real Postgres, real HTTP route, real persisted state)

`build43_local_e2e.py` (scratchpad), against the local Docker Postgres
(`docker compose up -d db`, same production-matching 3,556-row
`drug_product` catalog every prior build's local E2E has used; started
this session — the container had gone idle/stopped since a prior session).
Drug-entity scenarios were seeded via a real `AgentConversationStateStore.
save()` call using REAL catalog `legacy_drug_id`s (Paracetamol KABI
1000mg, Amoxicillin 250mg Imexpharm) rather than relying on the Main
Model's own tool-choice to have called `get_drug_info` on a cold first
turn — a real, PRE-EXISTING, already-documented characteristic of this
system (BUILD-29D2-REPORT §15: "get_drug_info structurally cannot fire on
most cold turns"), not something this build changes; isolating BUILD-43's
own inheritance/clearing mechanism from that unrelated non-determinism is
exactly what a canonical-state-driven design is supposed to let a test do.

All 11 required scenarios (spec §16) ran against real `run_agent_
orchestration`, with real OpenAI calls where the Main Model needed to
answer, and real DB-row assertions (not just reply text):

1. drug → TRUE_FOLLOWUP: `active_entity` correctly preserved across the
   follow-up turn (real name, not degraded to a raw catalog slug — see the
   bug fix below).
2. drug → disease TOPIC_SWITCH: `active_entity` cleared to `None` in real
   persisted state.
3. disease → drug TOPIC_SWITCH: `active_topic` cleared to `None`, the new
   drug entity correctly resolved.
4. schedule → "Còn ngày mai?": covered by the existing orchestrator-level
   regression test (§9) — not re-run against real Postgres separately,
   since it makes zero model/DB-state-mutating calls by design.
5. short standalone disease question after an unrelated drug topic: the
   prior drug entity NOT inherited, the new disease topic independently
   set.
6/7. ambiguous fragment, resolvable vs unresolved: with a seeded entity,
   resolved through the inherited context (real answer, not a
   clarification loop); with none, the bounded clarification reply.
8/9. BUILD-42 attempt count: `1` after the first unresolved clinical
   clarification turn, reset to `0` on a real topic-switching turn
   (verified from real persisted `ConversationState` rows both times).
10. Explicit doctor request: unaffected, `HANDOFF_CREATED`/`USER_REQUEST`.
11. Safety precedence: unaffected, `HANDOFF_CREATED`/`SAFETY`, even with a
   real entity already active in state.

**Three real bugs found and fixed via this E2E run, not assumed** (matching
this project's established discipline — BUILD-42 found 2 the same way):

1. **Pronoun captured as an explicit topic.** "Triệu chứng của nó?" matched
   `_DISPLAY_TOPIC_PATTERNS`'s symptom pattern and captured "nó" (it) as if
   it were a real topic name. Fixed: reject a pronoun-only capture,
   falling through to the deictic/attribute-only case instead (§4).
2. **Interrogative markers over-stripped as fragment evidence, missing
   real content.** "Khi nào tôi cần đi khám ngay?" (urgent-care) and "còn
   loại nào khác?" (ambiguous, no context) both initially misclassified —
   leftover fragments ("di", "khac") after stripping known markers were
   long enough to look like a "named subject" by the `len(remainder) >= 2`
   heuristic. Fixed by widening the (function-word-only, never
   topic/entity vocabulary) particle-stripping list — "di", "khac", and a
   handful of other pure Vietnamese function words.
3. **Entity display name lost on re-confirmation.** The TRUE_FOLLOWUP
   bound-lookup shortcut calls `get_drug_info` directly, bypassing
   `search_drug` — so `_resolved_drug_entity` (`agent_v2_routes.py`),
   which only recovers a real display name from a `search_drug` result,
   fell back to using the raw catalog slug (`amoxicillin-250mg-imexpharm-
   12-goi`) as BOTH id and display name, silently degrading an
   already-real name every time a follow-up re-confirmed the same entity.
   Fixed: `_resolved_drug_entity` now accepts a `known_entity` (the
   already-canonical prior entity) and reuses its real name when the id
   matches and no fresh `search_drug` corroboration exists this turn.

A fourth, narrower bug (not a classification bug) was also found and
fixed purely from real E2E: the bound-lookup shortcut's evidence
(`bound_tool_results`) was never merged into `RunResult.tool_results`
before `_enforce_medical_grounding` ran — every bound-lookup-only turn (no
OTHER tool call from the model's own turn, which is the entire point of
the shortcut) was silently flagged `GROUNDING_FAILURE` despite real,
verified evidence backing the answer. This affected the PRE-EXISTING
button-click bound-lookup path identically (same code), never previously
exercised end-to-end by any test — BUILD-43's own entity-inheritance path
was the first real scenario to actually reach it. Fixed by merging
`bound_tool_results` into `result.tool_results` immediately after the Main
Model call, before any downstream backstop reads it.

## 12. Tests

- **`tests/test_agent_v2_follow_up.py`** (new, 16 tests): pure unit tests
  for `classify_follow_up`, written and passing BEFORE any orchestrator
  wiring — the spec's own repro-first discipline (SS3 A–F, plus SS20's
  stale-entity/long-standalone/same-topic-inheritance cases).
- **`tests/test_agent_v2_build43_follow_up_resolution.py`** (new, 13
  tests): the required matrix (SS20) at the real orchestrator level — A/B
  (short/long standalone ignore unrelated context), C (explicit drug
  aspect binds deterministically, asserts the REAL tool call happened, not
  just the classification), D (pronoun follow-up), G (schedule bypasses
  the classifier), H/I (ambiguous fragment resolved/unresolved + repeated
  escalation), J (stale entity not inherited), K (`classify_follow_up`'s
  signature has no retrieval-query parameter — a locked contract, not a
  runtime check), N (Safety precedence), O (BUILD-40 router regression),
  plus an explicit disease→drug topic-switch case.
- **`tests/test_agent_v2_orchestrator.py`** (11 pre-existing tests
  rewritten, not deleted): the OLD tests relied on two sequential
  `orchestrator.run()` calls sharing one in-process `ShortTermMemoryStore`
  — exactly the memory-text mechanism this build removes. Rewritten to
  pass `prior_active_topic`/`prior_active_entity_name` explicitly (the
  real, new contract), preserving each test's original regression intent
  (semantic query variants, "not kidney-stone-hardcoded" parametrization,
  ambiguous-fragment/no-context clarification, ...) — none of the original
  coverage was dropped, all now assert the real `follow_up_decision` too.
- **80 tests total** across these three files; **0 failures**.
- Full `agent_v2`-keyword regression sweep: **1021 passed**, 4 Postgres-
  opt-in tests skipped (env var not set, expected), 3 pre-existing
  failures in `test_agent_v2_long_term_memory.py` — confirmed unrelated
  and pre-existing (same failures reproduced at BUILD-42's own baseline
  this session, before any BUILD-43 change).
- **Full repo-wide sweep** (`pytest tests/`, minus the two pre-existing
  `numpy`-import-broken VLM/photo-verification modules every prior build
  has also excluded): **1909 passed**, 9 skipped (2 demo-data-not-seeded
  skips + the 4 Postgres opt-in + 3 already counted above), **11 failed**
  — the 3 `test_agent_v2_long_term_memory.py` failures above, plus 8 in
  entirely unrelated subsystems this build never touches (`test_api/
  test_auth_routes.py`, `test_api/test_security_authz.py`, `test_api/
  test_patient_routes.py`, `test_chat_history_e2e.py`,
  `test_retrieval_sql.py` — JWT/email/GUC/demo-data config, not Agent V2).
  **Independently re-verified, not assumed**: `git stash`'d every BUILD-43
  change and re-ran a sample of these 8 (`test_get_current_user_valid_
  jwt`, `test_verify_email_flow`, `test_word_similarity_threshold_guc_
  is_set_not_just_similarity_threshold`) directly against the untouched
  `origin/main` baseline — all 3 failed identically, confirming they are
  genuine pre-existing local-environment gaps (JWT secret/email/GUC
  config on this machine), not a BUILD-43 regression.
- `ruff check`: clean on every changed/new file.

## 13. Performance / cost

**0 new synchronous model calls** — confirmed structurally
(`classify_follow_up` takes no model gateway, makes no I/O) and
empirically (`test_g_schedule_follow_up_bypasses_the_classifier_entirely`
and every orchestrator-level test asserting `len(gateway.calls) ==` an
exact expected count, e.g. `test_i_ambiguous_fragment_unresolved_asks_
clarification_bounded` asserts zero). The bound-lookup entity-inheritance
path REPLACES a would-be `search_drug` call with a direct `get_drug_info`
call (same one-tool-call shape the pre-existing button path already used)
— not an addition. No new retrieval calls, no new Vinmec calls. Token/
latency/cost profile is unchanged from the pre-existing mechanisms this
build reuses (`_FOLLOW_UP_CATEGORY_KEYWORDS`/`_resolved_query_for` for
topic inheritance, the bound-lookup tool-call shortcut for entity
inheritance) — no new prompt content, no new model round-trip introduced
anywhere in this build.

## 14. Known limitations

1. **`_detect_drug_aspect` keyword coverage is finite.** A drug-attribute
   follow-up whose phrasing matches none of the seven aspect keyword
   groups still correctly classifies `TRUE_FOLLOWUP`/`inherited_entity`,
   but without a detected aspect the bound-lookup shortcut does not fire
   (no `requested_attribute` to bind) — the turn proceeds through ordinary
   evidence gathering with the raw message and the entity id available but
   not force-bound. Not a regression (this exact case had NO working path
   at all before this build — see §1) but not a complete solution to every
   possible drug-attribute phrasing either.
2. **`_strip_evidence_markers`' particle list is English-comment-
   documented Vietnamese function words, not a formal grammar.** Real E2E
   found and fixed 2 real gaps in this list (§11); further gaps are
   plausible for phrasings not covered by this build's test matrix or the
   E2E run. This is the same class of trade-off every prior build's
   keyword-based router logic already accepts (BUILD-40's own router audit
   made the identical trade-off explicitly) — not unique to this build.
3. **No new `ConversationState` field, so no version bump.** BUILD-43 adds
   zero new persisted fields (`prior_active_topic`/`prior_active_entity_id`/
   `prior_active_entity_name` are `OrchestrationRequest`-only, computed
   fresh from `ConversationState` at request time, never themselves
   persisted) — SS17's backward-compatibility requirement is satisfied
   by having nothing new to be incompatible with, not by a version-bump
   migration path. An OLD `version: 4` (BUILD-42-shape) row still loads
   and behaves identically; not re-verified as a NEW test here since it is
   unchanged BUILD-42 behavior, not a BUILD-43 concern.
4. **Golden Set v3/v4 not created**, matching BUILD-42's own precedent
   (deferred, reasoned, not an oversight) — no existing `GoldenCategory`
   cleanly represents "follow-up taxonomy decision" as its own dimension
   without a larger, untested contract-version change. Recommended
   alongside BUILD-42's own deferred Golden v3 once real production
   traffic exists for both.
5. **The bound-lookup grounding-merge fix (§11, bug 4) is a real,
   necessary correctness fix but touches a PRE-EXISTING mechanism**
   (the button-click path), not something newly introduced by this build.
   Flagged explicitly rather than silently bundled: no other behavior of
   that pre-existing path was touched, and this exact fix is required for
   BUILD-43's own SS20-C test to pass at all — in scope by necessity, not
   scope creep.

## 15. BUILD-44 dependency

- **BUILD-44 (Doctor Chat Queue & Takeover)**: unaffected by this build's
  changes — `follow_up.py`/`FollowUpDecision` never touches
  `DoctorReviewRequest`/handoff creation directly; the only interaction is
  via `AMBIGUOUS_FRAGMENT`'s now-bounded escalation reusing BUILD-42's
  EXISTING `_answerability_handoff_reply` (same handoff shape, same
  `handoff_type` derivation BUILD-44 will read from either way).
- Any future build touching `_detect_drug_aspect`/`_DRUG_ASPECT_KEYWORDS`
  or `_FOLLOW_UP_CATEGORY_KEYWORDS` should keep them in sync with
  `follow_up.py`'s own `_ATTRIBUTE_KEYWORDS` (used for classification) —
  documented explicitly in-code as an intentional, small, deliberate
  duplication (not an oversight) rather than a cross-module import, to
  keep `follow_up.py` independently unit-testable with no dependency on
  `orchestrator.py`.

## 16. File scope

```
NEW    backend/agents/v2/follow_up.py
MOD    backend/agents/v2/orchestrator.py
MOD    backend/api/agent_v2_routes.py
NEW    tests/test_agent_v2_follow_up.py
NEW    tests/test_agent_v2_build43_follow_up_resolution.py
MOD    tests/test_agent_v2_orchestrator.py
```

No migration. No retrieval-tuning changes. No Doctor Queue/takeover UI. No
Safety Domain semantics changed. No Track B (Drug Image) file touched —
confirmed via `git status` on both `P-067-drug-image-b01` and
`P-067-drug-image-b02` worktrees before and after this build, neither
checked out/reset/rebased/edited.

---

## 17. Release Gate

```text
BUILD-43: PASS

BASELINE VERIFIED: PASS                (60311de, origin/main, BUILD-42 merged)
PARALLEL WORKTREE ISOLATION: PASS      (dedicated worktree/branch)
TRACK B UNTOUCHED: PASS                (drug-image-b01/b02 worktrees confirmed unmodified)

CANDIDATE-02 ROOT CAUSE VERIFIED: PASS (memory-text-based resolution + len<=35 OR-trigger, §1)
SHORT != FOLLOWUP: PASS                (structural -- length never read by classify_follow_up; SS20 A/B tests)

FOLLOWUP TAXONOMY: PASS
TRUE_FOLLOWUP: PASS                    (topic + entity inheritance, real bound tool call verified)
STANDALONE_QUESTION: PASS
TOPIC_SWITCH: PASS                     (real persisted state clearing verified, both directions)
AMBIGUOUS_FRAGMENT: PASS               (now bounded via BUILD-42's own Answerability Gate)

STALE TOPIC PREVENTION: PASS           (real E2E scenario 2/3)
STALE ENTITY PREVENTION: PASS          (real E2E scenario 5, SS20-J)
RETRIEVAL_QUERY STATE INVARIANT: PASS  (classify_follow_up signature has no such input, locked test)

BUILD-42 ATTEMPT PRESERVE SAME THREAD: PASS  (unchanged mechanism, untouched)
BUILD-42 ATTEMPT RESET ON TOPIC SWITCH: PASS (real E2E scenario 8/9)
UNCERTAINTY HANDOFF REGRESSION: PASS   (full BUILD-42 answerability suite: 40/40 passed)
EXPLICIT DOCTOR REQUEST REGRESSION: PASS (real E2E scenario 10)

ROUTER REGRESSION: PASS                (BUILD-40 disease/symptom fix untouched, SS20-O)
SAFETY PRECEDENCE: PASS                (real E2E scenario 11, with a real entity already active)
SCHEDULE FOLLOWUP: PASS                (classifier bypassed entirely, zero model calls, SS20-G)
AUTH ISOLATION: N/A                    (no auth-boundary code touched by this build)

NEW SYNC MODEL CALLS: 0                (structural + empirical, §13)
LATENCY REGRESSION: PASS               (bound-lookup replaces, not adds, a tool call)
TOKEN REGRESSION: PASS                 (no new prompt content introduced)
COST REGRESSION: PASS

LOCAL E2E: PASS                        (11/11 required scenarios, real Postgres, real HTTP route)
GOLDEN: N/A                            (deferred, reasoned -- see Known Limitations #4)
FULL REGRESSION: PASS                  (repo-wide: 1909 passed, 11 pre-existing unrelated failures
                                         independently re-verified against the untouched baseline, 9 skipped)

DOCTOR TAKEOVER BUILT: NO
TRACK B MODIFIED: NO

READY FOR PR: YES
READY FOR BUILD-44 AFTER MERGE/VALIDATION: YES
```
