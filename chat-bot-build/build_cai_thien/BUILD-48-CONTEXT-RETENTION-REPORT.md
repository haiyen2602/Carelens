# BUILD-48 — Conversation Context Retention

## 0. Precondition check

- Branch: `feature/BUILD-48-context-retention`, cut from
  `feature/BUILD-47-follow-up-observability` (`d4aa7e5`), not from `main` —
  this build's E2E verification reads the `agent_run.follow_up_*` columns
  BUILD-47 added, and BUILD-47 is not merged yet.
- Working tree clean at branch point. Alembic head `0063` (BUILD-47's), no
  new migration in this build.
- BUILD-47's own release gate: tests green, PR intentionally not opened.

## 1. Root cause (audit before code)

The user reported the chatbot "forgets" mid-conversation and initially
proposed appending previous answers into the next prompt. That proposal was
**rejected**: `follow_up.py`'s own module docstring records that BUILD-43
deliberately replaced exactly that mechanism (`resolve_conversation_context`,
which regex-scanned raw memory text) as brittle. Re-introducing it would undo
BUILD-43.

Instead, BUILD-47's durable `agent_run.follow_up_category` column made the
real failure visible for the first time, and each defect below was then
**reproduced directly** by calling `classify_follow_up()` with the exact
failing message — not inferred from reading code.

Critically, the loss is **persisted, not transient**: on a TOPIC_SWITCH the
route builds `replace(conversation_state, active_topic=None,
active_entity=None)` (`agent_v2_routes.py:1066-1071`) and passes that wiped
copy as the *base state* to `transition_state`. When the turn resolves
nothing new (`topic=None, entity=None`), `transition_state`'s `else` branch
(`conversation_state.py:309-311`) carries forward from the wiped base, and
that is what `state_store.save` writes.

### Defect 1 — polite filler and the generic noun "thuốc" read as a new subject

`_strip_evidence_markers` left request framing and generic category nouns in
the remainder, and `has_named_subject` was `len(remainder) >= 2`.

| message | remainder | was |
| --- | --- | --- |
| `cho mình thông tin thuốc` (real, 17:13:46) | `cho minh` | TOPIC_SWITCH |
| `tác dụng phụ của thuốc là gì` | `thuoc` | TOPIC_SWITCH |
| `cho tôi xem` / `giúp mình với` / `cho hỏi` | `cho xem` / `giup minh voi` / `cho` | TOPIC_SWITCH |

The second row is the worst: a textbook follow-up, discarded because the
generic word "thuốc" (a *class*, never a product name) counted as a subject.

Contributing: only the COMPOUND attribute keywords were listed
(`tac dung phu`, `thong tin thuoc`), so the bare `tac dung` / `thong tin`
survived stripping.

### Defect 2 — Case 1 never compares against the prior ENTITY

`classify_follow_up` Case 1 (the `_explicit_topic` branch) compared the
extracted topic only against `prior_topic`; Case 2 has always checked both
topic and entity. Reproduced:

```
"An Cung Ngưu Hoàng có nguy hiểm không"
  prior_entity_name="An Cung Ngưu Hoàng"  -> TOPIC_SWITCH, inherited_entity=False
  prior_topic="An Cung Ngưu Hoàng"        -> STANDALONE_QUESTION (correct)
```

Naming the very drug under discussion wiped it, purely because the prior
context happened to be stored as an entity rather than a topic.

### Defects 3 & 4 — nothing remembered from an ambiguous search

`_resolved_drug_entity` promotes only via one `get_drug_info` call or a
`search_drug` carrying `unique_match_legacy_drug_id`. That flag
(`v2_agent.py:407-439`) is computed from the QUERY STRING: score every
catalog item, keep `>= 0.90`, return only if exactly one clears. A typo kills
the matched token, so a mistyped query yields **zero** strong matches — not
"several candidates", but no unique match at all.

Real trace (`agent_run_span`): the turn that correctly described "AN CUNG
NGƯU Hoàng HOÀN HỘP GỖ 3v" ran `search_drug` only, `tool_calls=1`. Next turn:
`NAMED_SUBJECT_NO_PRIOR_CONTEXT`.

Nothing recorded what had been *offered* either, so picking a product
afterwards ("loại 400 Stella") re-searched the whole catalog — "Stella" is a
manufacturer shared by dozens of unrelated products — and returned Acyclovir
Stella, Crotamiton Stella, etc.

## 2. Design

### Defect 1 — `_NON_SUBJECT_WORDS` + `_has_named_subject`

A read-only set of words that can never BE a subject (request framing +
`thuoc`/`benh`). The remainder names a subject when **any** surviving token
is outside that set.

Deliberately **not** merged into `_QUESTION_PARTICLES`, which is *subtracted*
token by token: adding `cho` there would erase real names — "chó cắn" folds
to `cho can`, and `can` is already a particle, so the whole subject would
vanish. All-or-nothing only *judges* the remainder, so a real name anywhere
in the message always survives. Verified: `bị chó cắn phải làm sao` still
switches.

Bare `tac dung` / `thong tin` added to `_ATTRIBUTE_KEYWORDS`. Stripping is
longest-first, so the compounds still win and no existing match changes.

### Defect 2 — mirror Case 2's check

Case 1 now checks `_mentions(folded, prior_entity_name)` before concluding
TOPIC_SWITCH, reusing `NAMED_SUBJECT_MATCHES_PRIOR_ENTITY` rather than
inventing a second notion of "same subject".

### Defects 3 & 4 — offer the candidates, remember the pick

`suggested_actions.py` gains a branch (after the resolved-entity branch, so
the aspect-button flow is unreachable from it) that, when no entity resolved
and exactly one `search_drug` returned 1–4 items, offers one
`drug_followup` action per candidate. `resolve_state_input` gains a branch
(after the existing aspect branch) so picking one resolves. The route
promotes it via `_picked_candidate_entity`.

Reuses the existing `SuggestedAction` shape and `offered_actions`
persistence — no new state type, no migration. Picking works by button, by
typing the product name, or by typing its number, all through the existing
`_typed_action` matching.

**Product decision (user's, explicit): never auto-bind top-1.** In a medical
app, silently attaching the wrong product would go on to answer dosage and
contraindication questions about a drug the patient never asked about.

**One load-bearing detail:** candidate and aspect actions share the
`drug_followup` type and can both carry `value="drug_uses"`, so `value`
cannot distinguish them — and an aspect label is templated, so mistaking one
for a candidate would store "Tác dụng phụ của Paracetamol" as the drug's own
name. A dedicated server-issued `action_id` prefix
(`DRUG_CANDIDATE_ACTION_PREFIX`) is the discriminator; it is re-validated
against `offered_actions` every turn, so client input cannot forge one. Locked
by `test_an_aspect_button_is_never_mistaken_for_a_candidate_pick`.

## 3. Tests

`tests/test_agent_v2_build48_context_retention.py` — 29 tests, all passing,
written before the fix (confirmed red: 15 failed / 7 passed) per
`adrs/0001-test-strategy.md`.

The negative cases carry as much weight as the positive ones: a fix that
simply stopped switching topics would be worse than the bug. Locked as
**still switching**: `Paracetamol là gì`, `Viêm gan B là gì`, `thuốc
Amoxicillin dùng thế nào`, `cho tôi thông tin thuốc Paracetamol` (polite
filler *and* a real name), `tiểu đường có nguy hiểm không`, `bị chó cắn phải
làm sao`. Also locked: no-prior-context versions stay AMBIGUOUS_FRAGMENT
rather than silently answering about an unspecified drug.

Regression: 127/127 across `test_agent_v2_follow_up.py`,
`build43_follow_up_resolution`, `build45_topic_persistence`,
`build45_cold_entity_binding`, `conversation_state`,
`build47_follow_up_observability`, `build42_answerability`.

`ruff check` clean on every changed file.

## 4. Known limitations

- Defect 1's `_NON_SUBJECT_WORDS` is a hand-maintained Vietnamese list, same
  class of mechanism as the rest of this module. It covers the phrasings seen
  in real sessions plus the obvious neighbours; a phrasing outside it can
  still misclassify. BUILD-47's column is how the next gap gets found.
- A single-token message that is *only* a filler word (e.g. bare "chó cắn"
  reducing to `cho`) now reads as subject-less. With no prior context it
  becomes AMBIGUOUS_FRAGMENT — a clarification request, which is the safe
  outcome — but it is a real behavior change, recorded here rather than
  discovered later.
- Candidate offers are capped at 4 by `transition_state`, so a search
  returning more products offers none rather than an arbitrary subset.
- The candidate list is only offered when exactly one `search_drug` ran;
  two searches in one turn is itself ambiguity and is left alone.
- Nothing here changes Safety, Doctor Handoff, or schedule paths.

## 5. File scope

```
backend/agents/v2/follow_up.py                                (modified)
backend/agents/v2/conversation_state.py                       (modified)
backend/agents/v2/suggested_actions.py                        (modified)
backend/api/agent_v2_routes.py                                (modified)
tests/test_agent_v2_build48_context_retention.py              (new)
chat-bot-build/build_cai_thien/BUILD-48-CONTEXT-RETENTION-REPORT.md (new)
```

Not touched: `admin_monitoring_routes.py`, `agent_monitoring_metrics.py`, any
admin UI, any migration. The `"kê đơn thuốc mới"` router misroute (a real,
separately-confirmed defect where that request is read as a *lookup* of an
existing prescription) was explicitly left out of this build's scope.

## 6. Release gate

- New tests: **PASS** (29/29).
- Related regression: **PASS** (127/127).
- Lint: **PASS**.
- Full-suite controlled comparison vs baseline: **PASS** (below).
- **PR: NOT CREATED — intentionally**, at the requester's instruction, so
  they can test locally first. Reviewer per `GIT_WORKFLOW.md`: Trương Quốc
  Trường.

### Full-suite controlled comparison

The whole suite was run under identical conditions on the BUILD-47 baseline
and on this branch, and the sorted `FAILED`/`ERROR` lists diffed:

| | baseline (`d4aa7e5`) | this branch |
| --- | --- | --- |
| failed | 46 | 46 |
| errors | 74 | 74 |
| passed | 1912 | **1941** |

The 120-entry failure list is **byte-identical** (`diff` reports no
difference). Passed rises by exactly 29 — this build's own new tests. **This
build changes zero existing test outcomes.**

Those 46 + 74 pre-existing failures are environmental, not defects:
`tests/conftest.py` builds fixtures from the real `SessionLocal`, but
`Settings.database_url` falls back to the `.env` placeholder
`postgresql://.../dbname` unless `DATABASE_URL` is exported, so every
real-DB-backed test fails to connect (a sample failure is
`sqlite3.OperationalError: no such table: drug_id_map`, unrelated to any file
in this build). Running the suite against the real `vmec04` was deliberately
NOT done: those tests write real rows, and that database holds seeded demo
data and paid-for drug embeddings. `test_agent_v2_deepeval_judge.py` cannot
be collected locally at all — `deepeval` is not installed.
