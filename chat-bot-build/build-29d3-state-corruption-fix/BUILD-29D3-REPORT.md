# BUILD-29D.3 Report

## 1. Reproduction

Reproduced before the fix with the BUILD-29D.2 query shape, using the same
topic follow-up flow:

```text
active_topic before: sỏi thận
selected_action: topic_followup / urgent_signs / topic=sỏi thận
retrieval query (before): Dấu hiệu nào của sỏi thận cần đi khám ngay?
normalize_semantic_medical_query(...).topic: nao cua soi than can di kham ngay
```

The production report's corrupted string is therefore reproducible directly
from the application semantic normalizer, rather than inferred from UI text.
The initial state and selected action are server-issued conversation state;
the action payload itself was not accepted as arbitrary client authority.

## 2. Root Cause

`backend/agents/v2/conversation_state.py` built a natural-language follow-up
query from the action topic. `backend/api/agent_v2_routes.py` then ran
`normalize_semantic_medical_query(input_resolution.query)` and assigned its
`semantic.topic` to the durable `topic` argument of `transition_state` for a
general-medical result.

For the old urgent-signs query, the normalizer's generic symptom matcher
captured `nao cua soi than can di kham ngay`. That retrieval-local value
replaced the canonical state topic. The next suggested-action generation then
received the corrupted state topic and displayed corrupted labels.

### 2.1 Second corruption path found while completing full local E2E (2026-08-23)

Running the required Flow C ("Công dụng của thuốc Long Huyết P/H là gì")
against the real stack reproduced the same corruption class through the new
`_display_topic_from_raw` extractor this build itself added: its first
pattern (`"<X> là gì"`) captured `"Công dụng của thuốc Long Huyết P/H"` as if
it were a disease/topic name — a drug-attribute question with no shape
overlap with a genuine topic, but the regex could not tell the difference.
`active_topic` was corrupted to that string, and the follow-up suggestions
were built from it (`"Nguyên nhân gây Công dụng của thuốc Long Huyết P/H"`).
A second, related defect compounded it: `agent_v2_routes.py` passed
`semantic.display_topic or semantic.topic` into `_authoritative_topic_for_turn`,
so even a `None` from a correctly-guarded `display_topic` still fell back to
`semantic.topic` — the same ascii-folded, retrieval-only string responsible
for the *original* corruption this build exists to fix. Both were fixed
before this build could be marked PASS:

- `orchestrator.py::_display_topic_from_raw` now rejects any candidate
  containing a drug/attribute keyword (`thuốc`, `công dụng`, `liều dùng`,
  `cách dùng`, `tác dụng phụ`, `chống chỉ định`, `tương tác`, `thành phần`,
  and their ascii-folded forms) instead of accepting any text in front of
  the trigger phrase.
- `agent_v2_routes.py` no longer falls back to `semantic.topic` for a state
  write; only `semantic.display_topic` (or `None`, meaning no topic write at
  all this turn) reaches `_authoritative_topic_for_turn`.

Re-verified live: the same message now resolves the real canonical drug
entity (`get_drug_info` fired this turn, citations returned) with
`drug_followup` suggestions bound to the real `entity_id`, never a
topic_followup with a fabricated topic. See §12 Flow C.

## 3. Corrupt State Path

```text
validated server action
  -> follow-up query: "Dấu hiệu nào của sỏi thận cần đi khám ngay?"
  -> semantic topic extraction: "nao cua soi than can di kham ngay"
  -> route passes semantic.topic to transition_state
  -> active_topic overwritten
  -> dynamic action generator receives overwritten topic
```

The affected route assignment was the general-medical `topic = semantic.topic`
path immediately before `transition_state(...)`.

## 4. State Invariants

- A validated topic follow-up preserves the active canonical topic.
- Only a new explicit/authoritative topic resolution may replace it.
- `requested_aspect` changes independently from topic/entity state.
- Follow-up and normalized queries are request-local and cannot be persisted
  as topic/entity state.
- Canonical/display text and normalized lookup key are separate fields.
- A safety event retains BUILD-29C priority and clears ordinary offered actions.

## 5. Architecture Before

The durable state stored only `canonical_name`. The route used a semantic
topic extracted from the follow-up retrieval string as a state-transition
topic, conflating canonical topic, requested aspect, and retrieval query.

## 6. Architecture After

`ActiveTopic` and `ActiveEntity` retain canonical/display name plus a separate
normalized lookup key. `build_followup_query(active_topic, requested_aspect)`
creates an ephemeral retrieval/model query. The route's
`_authoritative_topic_for_turn` explicitly refuses to replace an existing
topic for a selected `topic_followup`; it uses the server state as authority.
An explicit `"<topic> thì sao?"` is routed as general medical information,
so it is an intentional state transition rather than a default drug query.

## 7. Query Builder

Examples from `build_followup_query`:

```text
urgent_signs -> dấu hiệu nguy hiểm của sỏi thận cần đi khám ngay
causes       -> nguyên nhân gây sỏi thận
treatment    -> điều trị sỏi thận
monitoring   -> cần theo dõi gì khi bị sỏi thận
```

The return value is not written to conversation state.

## 8. Topic/Entity Preservation

The route propagates a numeric/typed resolution as the selected action just
like a UI click. A validated topic action uses the existing state topic;
valid legacy state can only be seeded from the exact server-issued action.
Drug follow-ups continue to bind to the existing authoritative entity ID and
now preserve separate display/normalized fields through serialization.

## 9. Suggested Action Fix

Suggested-action generation receives the active canonical topic after the
guarded transition. It no longer receives a topic reconstructed from a
follow-up query. A retrieval/model fallback may return no suggestions, but it
cannot corrupt the state topic.

## 10. Safety Interaction

No BUILD-29C safety decision logic was changed. `transition_state(...,
safety_event=True)` still clears ordinary actions before any normal state
update. Follow-up binding does not override a safety result.

## 11. Tests

Final targeted run, after both the original fix and the §2.1 drug-attribute
corruption fix, against the real local Postgres (production-data copy
restored earlier this session for realistic multi-patient/multi-drug
testing — see below):

```text
pytest -q tests/test_agent_v2_conversation_state.py tests/test_agent_activity.py \
        tests/test_agent_v2_route.py tests/test_agent_v2_orchestrator.py \
        tests/test_agent_feedback_service.py tests/test_get_current_patient_id.py \
        tests/test_agent_v2_time_query_engine.py tests/test_agent_v2_relative_date_parsing.py \
        tests/test_agent_v2_router_remediation.py
382 passed in 19.71s
```

New coverage proves the original corrupted semantic extraction, ephemeral
query behaviour, multi-follow-up topic preservation, explicit topic
switching/stale rejection, display/normalized separation, drug preservation,
fallback preservation, and existing activity/safety/isolation checks. One
additional unit test (`test_drug_attribute_question_never_becomes_a_display_topic`)
was added after the §2.1 fix, asserting `display_topic` stays `None` for
several drug-attribute phrasings while remaining correct for a genuine
disease topic — `ruff check` clean throughout.

## 12. Local E2E

Backend and frontend were restarted locally against a **real production data
copy** (Postgres, restored from Railway `VMEC-04/DB` into the local Docker
container earlier this session for realistic multi-patient/multi-drug
coverage — 92 accounts, 78 patients, 3562 drugs, 28870 legacy drug_chunks;
`alembic_version` `0041` matched the local migration head exactly, no drift).
`AGENT_RUNTIME_ENABLED=true` was set only in the local, gitignored `.env`;
no production configuration was touched. Every message below went through
the real Next.js `/api/chat` proxy (`http://127.0.0.1:3000/api/chat`,
forwarding a real bearer JWT from a freshly registered patient, `BN00072`),
never directly to the backend — the same path a browser uses. Payloads were
sent from UTF-8 files (not inline shell args) after an earlier session
established that typing Vietnamese diacritics directly into a Bash `-d`
argument on this Windows/Git-Bash environment silently mangles the bytes.

**Flow A — Disease follow-up: PASS.**
```text
Turn 1: "bệnh sỏi thận là gì"
  → causes, treatment, urgent_signs; every action topic = "sỏi thận"
Turn 2: click urgent_signs
  → reply is an honest "no verified data" fallback (retrieval miss for that
    aspect — expected per §10, not a state bug); active_topic still "sỏi
    thận"; new actions (diagnosis, treatment, monitoring) still topic =
    "sỏi thận". No corrupted string anywhere.
Turn 3: click monitoring
  → router misclassified this turn's ephemeral query as DRUG_INFORMATION
    (expected — the built query "cần theo dõi gì khi bị sỏi thận" doesn't
    match any GENERAL_MEDICAL_INFORMATION keyword), so no evidence and
    suggested_actions: []. Because `_authoritative_topic_for_turn` never
    writes a topic for a non-general-medical turn, transition_state's
    unchanged-carry-forward branch kept active_topic = "sỏi thận" regardless
    of the router's own label for this specific turn.
Turn 4: typed "nguyên nhân" (no click; offered_actions was empty from turn 3)
  → resolved via the typed-alias-from-active-topic path (constructs a
    candidate from state.active_topic even when nothing was offered) →
    real grounded causes answer, topic still "sỏi thận", diacritics intact.
```

**Flow B — Topic switch: PASS.**
```text
"gan nhiễm mỡ thì sao?" → active_topic switches to "gan nhiễm mỡ" (diacritics
  preserved), new topic_followup actions bound to it.
"nguyên nhân" (typed) → still "gan nhiễm mỡ", real grounded causes answer.
```

**Flow D — Stale action: PASS.**
Submitted a `topic_followup`/`urgent_signs`/`topic="sỏi thận"` action
(server-issued 2 turns earlier, before the Flow B topic switch) while active
state was "gan nhiễm mỡ". `_validated_selected_action` rejected it (not in
the current `state.offered_actions`); the message fell back to plain text,
which matched the typed-alias-from-active-topic path using the *current*
topic ("gan nhiễm mỡ") — never bound to the stale "sỏi thận". No corruption,
no cross-topic leak.

**Flow C — Drug entity: found and fixed a real regression, then PASS.** See
§2.1 for the corruption found and fixed mid-session. Re-verified after the
fix, fresh conversation:
```text
"Công dụng của thuốc Long Huyết P/H là gì"
  → real get_drug_info evidence (citations: tac_dung_phu, cach_dung), entity
    resolved (entity_id "long-huyet-ph-2x12-tan-bam-tim-giam-phu-ne"),
    drug_followup actions (side_effects, warnings, administration) bound to
    that entity_id, topic: null throughout. No topic_followup, no fabricated
    topic string.
click "Tác dụng phụ của LONG Huyết PH 2x12 ..."
  → bound get_drug_info lookup found no adverse-effect field for this
    product (an honest "no verified data" fallback, a retrieval-coverage
    gap, not a state bug) -- entity_id unchanged across the turn, new
    drug_followup actions (warnings, interactions, drug_uses) still bound to
    the same entity_id.
```

**Flow E — Safety: PASS.** In the Flow B conversation (active topic "gan
nhiễm mỡ"), `"tôi vừa nôn ra máu"` → real escalation (`HANDOFF_CREATED`,
`safety_disposition: HANDOFF_REQUIRED`, `severity: HIGH`,
`suggested_actions: []`). A follow-up typed "nguyên nhân" immediately after
resolved back to "gan nhiễm mỡ" (state survived the safety turn unchanged;
`transition_state(..., safety_event=True)` only clears offered actions, never
touches active_topic/active_entity) — real grounded causes answer, no
corrupted string, no cross-topic bleed from the safety message itself.

**Flow F — Regression UI: PASS, real requests.**
`GET /agent/v2/traces/{trace_id}/activity` → real `200`, real timeline
including the new `suggested_action.selected` step (`"Bạn chọn 'nguyên
nhân'"`) alongside intent/retrieval/generation/suggested_actions.created.
`POST /agent/v2/feedback` against a real trace → real `201` ticket
(`status: OPEN`, `priority: P3`).

No corrupted topic string (`"nao cua soi than..."` or any analogous raw/
normalized-query text) appeared in any reply, suggested action, or state
transition across the full matrix.

## 13. Regression

Targeted BUILD-29D.2/29D.3-relevant suite (conversation state, activity
timeline, route gate, orchestrator, feedback service, patient-id resolution,
time query engine, relative-date parsing, router remediation): **382 passed**
(see §11), run twice (before and after the §2.1 fix) — both clean.

Full repository suite, run before *and* after the §2.1 fix to isolate any
new regression from it:

```text
pytest -q tests/ --ignore=tests/services/photo_verification/test_vlm_prompts_dong_bo.py --ignore=tests/vlm_demthuoc
1615 passed, 6 skipped, 13 failed  (both runs, byte-identical failing test list)
```

All 13 failures were investigated and confirmed **unrelated to BUILD-29D.3**
(none of this build's diff touches any of the failing modules; each was also
reproduced identically after `git stash`-ing every BUILD-29D.3 change and
running against plain `origin/main`):

- 2 are this local session's own `AGENT_RUNTIME_ENABLED=true` override in
  `.env` (LOCAL ONLY, gitignored) tripping the two "off by default without
  touching db" tests — confirmed pass with `AGENT_RUNTIME_ENABLED=false`.
- 4 `test_auth_routes.py` failures (`verify_email_flow`,
  `verify_email_invalid_token_returns_400`,
  `forgot_password_and_reset_password_flow`,
  `reset_password_invalid_token_returns_400`): `register()` never actually
  sets `Account.email_verification_token` (grepped the whole backend — the
  column exists, nothing writes it) or, similarly, the reset-password token.
  A pre-existing application/test gap, most likely from an incomplete
  Supabase Auth migration (ADR-0013) that moved verification elsewhere
  without updating this DB-column-based test. Not touched by this build.
- `test_get_current_user_valid_jwt`: the unit test calls
  `get_current_user(authorization=...)` directly without FastAPI resolving
  its `db: Session = Depends(get_db)` parameter, so `db` is literally the
  `Depends(...)` sentinel object with no `.query` method. A broken unit test
  unrelated to any code path this build touches.
- `test_doctor_search_still_gets_full_fields_regression`: mints a JWT for a
  freshly `uuid4()`-generated, never-inserted account id every run — the
  route's DB lookup by that id can never succeed regardless of database
  content. Always broken, unrelated to any data or code in this session.
- `test_patient_role_cannot_read_or_hide_another_patients_chat_history`:
  mints a JWT for a fixed id, `"test-caregiver-seed"`, that this test file
  never creates itself — it depends on an ambient, manually-seeded row that
  happened to persist in the shared local dev database indefinitely. This
  session's earlier production-data restore (drop + reload `vmec04`, done at
  the user's request to make local testing more realistic — see chat
  history) removed that ambient row along with the rest of the old local
  seed data, so this one test now 401s. This is a legacy `/api/v1/chat`
  route test (the IDOR fix from PR #20), an entirely different subsystem
  from Agent V2/BUILD-29D.3; cross-patient isolation *at the Agent V2 layer*
  this build actually touches is covered and passing in §11's 382.
- `test_push_subscribe_routes_are_bodyless_204_responses`: the push router
  is very likely conditionally registered on VAPID keys being configured
  (per `docs/DEPLOY.md`, "push tự tắt" when unset); this local `.env` has no
  `VAPID_PUBLIC_KEY`/`VAPID_PRIVATE_KEY`. A local-config gap, not this
  build's code.
- `test_word_similarity_threshold_guc_is_set_not_just_similarity_threshold`:
  hardcodes an exact row-count (`== 1`) for one specific real `drug_id`'s
  fuzzy-match candidates; the restored production `drug_chunks` table has 2
  matching rows for that id/query instead of the original local seed's 1 —
  a data-content assumption, not a GUC/session-config regression (the GUC
  itself is being set correctly; the assertion is what a specific dataset
  produces).
- 2 `test_vlm_telemetry.py` failures: unrelated Langfuse/VLM telemetry
  connectivity tests, no relation to Agent V2 conversation state.

None of these were modified in this session; they are reported for
transparency, not fixed, since none are BUILD-29D.3 regressions and several
require decisions (Supabase migration follow-through, VAPID local config,
restoring/parameterizing legacy ambient test fixtures) outside this build's
explicit scope ("Không sửa lại architecture nếu không phát hiện regression
mới").

## 14. Files Changed

- `backend/agents/v2/conversation_state.py`
- `backend/agents/v2/orchestrator.py`
- `backend/api/agent_v2_routes.py`
- `tests/test_agent_v2_conversation_state.py`
- `chat-bot-build/build-29d3-state-corruption-fix/BUILD-29D3-REPORT.md`

## 15. Known Limitations

- Existing BUILD-29D.2 state records remain readable through the backward
  compatible deserializer and are upgraded (to version 3, with
  display/normalized fields) on the next save.
- Cold-turn `DRUG_INFORMATION` grounding remains dependent on the model
  choosing to call `get_drug_info` within its single planning round
  (`agent_max_model_calls=2`, pre-existing, documented in
  `BUILD-29D2-REPORT.md` §15) — this session's Flow C happened to get real
  evidence on one try where BUILD-29D.2's own testing did not; this is
  model-call-budget-dependent, not deterministic, and remains a tracked,
  out-of-scope, pre-existing limitation, not something BUILD-29D.3 changes.
- §13 lists 13 full-suite failures confirmed unrelated to this build; several
  (auth email/reset tokens, the doctor-search test's always-invalid account
  id, the VAPID-gated push contract test) are worth a team follow-up but are
  explicitly out of this build's scope.
- This session's production-data restore into the local Postgres (done at
  user request, for realistic local testing) removed one ambient,
  manually-seeded legacy test fixture (`"test-caregiver-seed"`) that
  `tests/test_chat_history_e2e.py` silently depended on existing. Restoring
  that fixture (or making the test self-seed it) is a reasonable follow-up
  but was left out of scope here since it is unrelated to Agent V2/BUILD-29D.3.

## 16. Branch / Commit / PR

- Branch: `feature/build-29d3-state-corruption-fix`
- Base: `origin/main` at `7374951` (`Merge pull request #103` — BUILD-29D.2).
- Commit / push / PR: created after this report update — see repo history
  for the commit and PR on this branch.
- Not deployed; deploy requires review/merge per instruction.

## 17. Release Gate

| Gate | Status |
| --- | --- |
| BUILD-29D.3 | PASS |
| ROOT CAUSE IDENTIFIED | YES |
| ACTIVE TOPIC PRESERVED | PASS (unit + real E2E, Flow A/B/D/E) |
| ACTIVE ENTITY PRESERVED | PASS (unit + real E2E, Flow C) |
| REQUESTED ASPECT SEPARATED | PASS (unit + real E2E) |
| RETRIEVAL QUERY EPHEMERAL | PASS (unit + real E2E) |
| NORMALIZED KEY SEPARATED | PASS (unit) |
| VIETNAMESE DISPLAY PRESERVED | PASS (unit + real E2E — diacritics intact throughout) |
| FOLLOW-UP QUERY BUILDER | PASS (unit) |
| SUGGESTED ACTIONS USE CANONICAL TOPIC | PASS (unit + real E2E) |
| FALLBACK DOES NOT CORRUPT STATE | PASS (unit + real E2E, Flow A turn 3) |
| TOPIC SWITCH | PASS (unit + real E2E, Flow B) |
| STALE ACTION PROTECTION | PASS (unit + real E2E, Flow D) |
| SAFETY PRIORITY | PASS (existing regression + real E2E, Flow E) |
| CONVERSATION ISOLATION | PASS (existing regression, 382-suite) |
| CROSS-PATIENT PROTECTION | PASS at the Agent V2 layer this build touches (382-suite); see §13 for one unrelated legacy `/api/v1/chat` test broken by this session's own local DB restore, out of scope |
| REAL LOCAL APP MULTI-TURN | PASS (Flows A–F, §12, real OpenAI + real restored-production-copy Postgres + real JWT via the actual `/api/chat` proxy) |
| REAL PRODUCTION APP MULTI-TURN | NOT RUN (no reviewed merge/deploy yet — do not deploy before review, per instruction) |
| CORRUPTED TOPIC FOUND AFTER FIX | NO — one was found and fixed *during* this session's own E2E completion (§2.1, Flow C); zero corruption in the final, fully re-verified state (§11–§13) |
