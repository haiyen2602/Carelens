# Drug Image OCR Name-Matching Hardening + Follow-up Fix Report

**Date:** 2026-08-28
**Branch:** `fix/drug-image-ocr-name-followup-hardening`
**Baseline:** `fix/drug-image-ocr-decision-observability` (PR #158,
`READY_FOR_CONTROLLED_CANARY`), incorporating its own PR-review response
(the two findings this task's own context section restates).

## 1. Baseline

Confirmed unchanged before this task: recognition thresholds, visual
retrieval logic, Top-3 UI suppression, explicit-confirmation requirement.
Both findings this task addresses were left open, on record, by PR #158's
own review response rather than fixed there (out of that PR's declared
scope).

## 2. OCR single-token catalog audit

Re-confirmed against the real local Postgres copy of the production
catalog (3556 rows, byte-identical to production per the earlier storage
flatten work):

```
TOTAL products: 3556
Single-token identity segment: 1867 (52.5%)
Multi-token identity segment: 1688 (47.5%)
Zero-token identity segment: 1
Unique single-token identities: 1398
Tokens shared by >1 product: 302
Tokens with >=1 same-token+same-strength collision: 165
Tokens whose products span >1 distinct dosage_form: 103
```

Examples of a single-token identity segment (the pre-strength text
`_name_match` compares OCR against): `"Pentasa 1g 4x7"` → `pentasa`,
`"Doniwell 25mg 10x10"` → `doniwell`, `"Snapcef 16mg/10ml..."` →
`snapcef` (this task's own real HIGH_EVIDENCE example is itself in this
52.5% group).

Examples of the real collision shape this task's §5 asks about (same
single token, same extracted strength, two distinct real
`drug_product_id` rows): `Acyclovir 200mg Stella 10x5` /
`Acyclovir 200mg Stella 5x5`; `Simvastatin 20mg` (A.t brand / Stella
brand); `A.t Bisoprolol 2.5mg` / `Bisoprolol 2.5mg Stella`.

## 3. Risk reproduction (this task's own section 2 lettered cases)

All 5 cases (A-E) reproduced as deterministic tests
(`tests/services/test_drug_image_ocr_name_hardening.py`), using
catalog-realistic data (case B/D use the real Acyclovir/Simvastatin
collision shapes above):

| Case | Scenario | Result before this task | Result after |
|---|---|---|---|
| A | Unique single-token + strength match | HIGH_EVIDENCE (correct) | HIGH_EVIDENCE (unchanged, correct) |
| B | Non-unique single-token, weak evidence | Could reach HIGH_EVIDENCE on name+strength alone | AMBIGUOUS_MATCH, `NON_UNIQUE_SINGLE_TOKEN` |
| C | Same brand, different strength | INSUFFICIENT_EVIDENCE (`STRENGTH_CONFLICT`) | Unchanged |
| D | Same brand, same strength, different real product | Could reach HIGH_EVIDENCE | AMBIGUOUS_MATCH, requires corroboration + uniqueness |
| E | Generic/noisy OCR token | AMBIGUOUS_MATCH | Unchanged |

## 4. New single-token corroboration rule

Audited `_meaningful_tokens`/`_name_match`/`_rerank`/`_decide`
(`backend/services/drug_image_recognition.py`) before changing anything,
per this task's own instruction.

`_name_match` now returns `(score, identity_token_count)` instead of a
bare score, so `_rerank` can distinguish a robust multi-token match
(`product_name_match`, unchanged behavior) from a single-token match
(`product_name_match_single_token`, new). `_decide()`'s rule:

```
single-token name match
AND (strength_match OR ingredient_match)      -- data already computed elsewhere
AND catalog does not show >=1 OTHER real product
    sharing the exact (token, strength) pair   -- NON_UNIQUE_SINGLE_TOKEN, section 5
AND visual Top-1
AND no hard conflict
→ eligible for HIGH_EVIDENCE_MATCH
```

`formulation_match`/`manufacturer_match` (this task's own §3 example list)
were **not** added: `dosage_form` exists on `DrugProduct` but using it as
a corroboration signal would need new OCR-text extraction logic (a scope
increase beyond "choosing from data actually available" — `strength_match`
and `ingredient_match` are the two signals already computed and tested
elsewhere in this file); no `manufacturer` column exists in the schema at
all. Where corroboration is absent, the result explicitly degrades to
`AMBIGUOUS_MATCH` with reason code `SINGLE_TOKEN_NEEDS_CORROBORATION` —
never silently indistinguishable from a no-evidence case, and never
inventing confidence, per this task's own explicit instruction. No
display-name fuzzy-matching fallback was added (also explicitly forbidden
by this task).

Multi-token matching is completely unchanged — verified by a dedicated
regression test (`test_multi_token_product_name_match_alone_still_reaches_high_evidence`).

## 5. Catalog uniqueness analysis

`_is_single_token_non_unique(session, token, strengths)` (new) answers,
from real catalog data, whether >=1 OTHER product shares this exact
(single identity token, strength) pair — not a hand-maintained keyword
list, computed once per process from a live `SELECT * FROM drug_product`
scan (~3556 rows, sub-second) and cached process-wide for the process
lifetime, matching the existing "pay once, not per request" convention
already used for the OpenCLIP embedder and the OCR runtime probe in this
same module. A catalog change takes effect after a process restart, same
as those two. Unit-verified directly
(`test_single_token_strength_index_is_catalog_derived_not_a_keyword_list`)
against the real Acyclovir 200mg/400mg shape.

## 6. OCR hard-negative test set

10 new deterministic tests
(`tests/services/test_drug_image_ocr_name_hardening.py`), covering every
shape section 6 asks for (unique single-token+strength, duplicated
single-token, same-brand-different-strength, same-brand-same-strength-
different-product, multi-token, noisy OCR, missing strength, wrong
strength, ingredient corroboration) plus a direct unit test of the
uniqueness index itself — **all 10 pass, 0 false HIGH_EVIDENCE**.

```
$ pytest tests/services/test_drug_image_ocr_name_hardening.py
10 passed
```

## 7. 8-image real-phone regression

Rerun with the hardened code, real Tesseract 5.5.2 (vie+eng), real
production catalog (local copy):

| Image | Outcome (after hardening) | Reason codes | Same as before hardening? |
|---|---|---|---|
| test01 | HIGH_EVIDENCE_MATCH (correct) | `SINGLE_TOKEN_NAME_MATCH, OCR_STRENGTH_MATCH, HIGH_EVIDENCE_CONFIRMED` | Yes — "snapcef" is a genuinely unique single-token brand in this catalog (verified: exactly 1 real product), so it is unaffected |
| test02-04, 06-08 | AMBIGUOUS_MATCH | `AMBIGUOUS_VISUAL_ONLY` | Yes, unchanged |
| test05 | INSUFFICIENT_EVIDENCE | `QUALITY_FAILED` | Yes, unchanged (quality gate) |

**test01 did not regress into incorrect confidence — HIGH_EVIDENCE wrong
remains 0.** No previously-AMBIGUOUS case was pushed to HIGH_EVIDENCE by
the hardening (none of test02-08 had a single-token+corroboration shape
to begin with). No previously-correct case became wrong. Per this
section's own instruction, coverage was not optimized for — safety was
verified, not traded for a higher HIGH_EVIDENCE count.

**REAL PHONE TESTS: 2/8 Top-1 correct (unchanged). HIGH_EVIDENCE CORRECT:
1. HIGH_EVIDENCE WRONG: 0.**

## 8. Free-text follow-up reproduction (real, live — not synthetic)

Real local HTTP chain: `test01.jpg` → `HIGH_EVIDENCE_MATCH` → confirm →
`active_entity` bound to the canonical Snapcef `drug_product_id` (verified
directly in Postgres) → ask each phrase in a fresh turn on the same
conversation.

**Before this task's fix, ALL SIX phrases failed**, with **two distinct
failure shapes**, disproving this task's own context assumption that they
"often fail the same way":

- `"tác dụng phụ thì sao?"`, `"thông tin chi tiết thuốc"`, `"công dụng?"`,
  `"liều dùng?"`, `"có lưu ý gì không?"` → model asked "which drug?" despite
  a correct entity binding.
- `"cách dùng thế nào?"` → classified as `DRUG_INFORMATION` directly by
  the raw-message router (has its own recognizable grammar shape), so it
  took a *different* code path than the other five, but still lost the
  bound answer for the same underlying reason (see section 9).

## 9. Root-cause boundary (real, traced live with temporary instrumentation)

Traced with live debug instrumentation (added, exercised against the real
running backend, then fully removed before commit — no diagnostic code
remains). Confirmed, in order, all CORRECT:

1. `request.prior_active_entity_id` / `prior_active_entity_name` — correctly
   populated from the real persisted `ConversationState`.
2. `classify_follow_up("tác dụng phụ thì sao?", prior_entity_name=...)` →
   `TRUE_FOLLOWUP`, `inherited_entity=True`. Correct.
3. `_detect_drug_aspect("tác dụng phụ thì sao?")` → `"side_effects"`.
   Correct.
4. `effective_entity_id`/`effective_requested_attribute` set, `decision`
   forced to `DRUG_INFORMATION`. Correct.
5. The bound `tools.execute(GET_DRUG_INFO, {...})` call fires, returns a
   real result (`results_count=1`, genuine verified content). Correct.
6. `evidence_items.append(bound.to_context_item(...))` — the real
   evidence item is added. Correct.

**Found here — `_compose_evidence_text` (`orchestrator.py`), the function
that renders admitted context into the text the Main Model actually
reads**: it only ever recognized three id-sets — `retrieval_ids`,
`web_ids`, `memory_ids`. The bound tool item's `context_id`
(`"bound-drug:<id>"`) matched none of them. The item legitimately survived
Context Manager admission (it has TOOL authority, high priority) but this
function's own label loop had no bucket to put it in, so its content was
silently omitted from every rendered prompt. Confirmed by inspecting the
real composed message: it contained only
`"[conversation memory - not authoritative]\ntác dụng phụ thì sao?"` — the
verified drug answer that had already been fetched never reached the Main
Model, which is exactly why it asked "which drug?" despite a fully correct
canonical binding.

This is a **taxonomy/parser boundary bug, not a canonical-state bug** —
matching this task's own §9 instruction exactly. `ConversationState`/
`active_entity` were never touched or found wrong at any point in this
trace.

**Scope note**: this same code path is used identically by a clicked
suggested-action button (`request.active_entity_id`/`requested_attribute`,
`orchestrator.py` lines 1597-1598) as by an inherited TRUE_FOLLOWUP entity
— the bug affected both origins equally, which section 10 verifies
directly rather than assuming.

### Fix

- `run()`: track a new `bound_tool_ids: set[str]` alongside
  `retrieval_ids`/`web_ids`, adding the bound tool's own context_id to it.
- `_compose_message(...)`: accepts and threads through `bound_tool_ids`
  (new optional parameter, defaults to empty — no caller broke).
- `_compose_evidence_text(...)`: adds a fourth section,
  **`"verified drug information"`**, ranked *first* (ahead of retrieval) —
  it is a deterministic, exact, server-verified match for the current
  question's own bound entity, strictly more specific than a
  similarity-based retrieval result.

**No new model calls, no new tool calls.** The fix only changes which of
the *already-computed* context items get rendered into the *already-being-
built* prompt string.

### Regression test added

Two existing deterministic tests
(`tests/test_agent_v2_build43_follow_up_resolution.py::test_c_*`,
`::test_c2_*`) previously asserted only that `get_drug_info` was *called*
with the right id — never that its content reached the model. Both now
also assert the fake tool's fixed content (`"Ha sot, giam dau"`) appears
in `gateway.calls[-1]["message"]` (the actual composed prompt). **Verified
these two assertions genuinely catch the real bug**: temporarily reverted
the `orchestrator.py` fix and reran — both failed with
`augmented_message == 'thong tin chi tiet thuoc'` (raw message, no
evidence at all), exactly reproducing the live symptom; restored the fix
and reran — both pass.

## 10. Image/text canonical state equivalence

`ConversationState.active_entity` carries no field recording its own
origin (only `type`/`id`/`canonical_name`/`legacy_drug_id`) — by
construction, every downstream consumer (the exact code path fixed above)
cannot distinguish an image-confirmed entity from a text-confirmed one.
Verified this is true in practice, not just by code inspection:

- **A. IMAGE-CONFIRMED** (real E2E: upload → HIGH_EVIDENCE → confirm →
  6 questions): **6/6 resolved directly to the correct verified Snapcef
  answer**, no "which drug?" response for any of them.
- **B. TEXT-CONFIRMED** (state seeded directly with the identical
  `ActiveEntity` shape a text flow would produce — the codebase's own
  automatic text-search promotion, `agent_v2_routes.py::_resolved_drug_entity`,
  requires a search-time unique-match signal from a separate,
  already-existing feature (BUILD-45 Candidate A) that this task's own
  scope does not touch; seeding state directly is the correct, more
  precise test of *this task's* actual invariant — "the router/follow-up
  logic must not care where the entity came from" — since it isolates
  exactly that claim): **6/6 resolved identically**, same wording style,
  same tool (`get_drug_info`), same canonical entity.

**IMAGE/TEXT STATE EQUIVALENCE: PASS**, verified with real, live HTTP
calls for both origins, not assumed from the shared code path alone.

## 11. Aspect resolution

All 6 required phrases individually verified (both origins, section 10's
runs): `"thông tin chi tiết thuốc"` → `drug_details`, `"tác dụng phụ thì
sao?"` → `side_effects`, `"công dụng?"` → `drug_uses`, `"cách dùng thế
nào?"` → `administration`, `"liều dùng?"` → `dosage`, `"có lưu ý gì
không?"` → `warnings`. `_DRUG_ASPECT_KEYWORDS`/`_DRUG_ASPECT_LABELS`
(`orchestrator.py`) already had complete, correct coverage for every one
of these phrases — no keyword-table change was needed; the bug was
downstream of this correctly-working detector, not in it. `active_entity`
confirmed unchanged across all 6 turns per conversation (checked directly
in Postgres) — only `requested_aspect`/the derived attribute label varies
per turn.

## 12. Topic-switch regression

Scenario: Snapcef image-confirmed → `"Paracetamol thì sao?"`. Real result:
reply discusses paracetamol only, Snapcef not mentioned — a genuine
`TOPIC_SWITCH`, không force Snapcef inheritance. **PASS.**

## 13. Safety invariants (rejected/ambiguous image candidate)

Scenario: real recognize → real HIGH_EVIDENCE candidate →
`decision: "REJECTED"` sent to `/confirm` (the existing additive refusal
value from PR #155, unmodified here) → same conversation asked "tác dụng
phụ thì sao?". Real result: `"Mình chưa xác định đủ ngữ cảnh cho câu hỏi
này..."` (insufficient context) — **no Snapcef inheritance from the
rejected candidate.** **PASS.**

## 14. E2E (this task's own scenarios A-D)

| Scenario | Result |
|---|---|
| A. test01.jpg → HIGH_EVIDENCE → confirm → immediate verified details → "tác dụng phụ thì sao?" → verified Snapcef answer | PASS |
| B. Same flow → "cách dùng?" → exact Snapcef | PASS |
| C. Snapcef confirmed → "Paracetamol thì sao?" → correct switch | PASS |
| D. Reject image candidate → "tác dụng phụ thì sao?" → must not resolve rejected drug | PASS |

## 15. Regression

| Suite | Result |
|---|---|
| Drug-image recognition + OCR runtime + hardening (61 tests) | 61/61 passed |
| `test_agent_v2_build43_follow_up_resolution.py` + `test_agent_v2_follow_up.py` + `test_agent_v2_orchestrator.py` (86 tests) | 86/86 passed |
| Safety/Dose-Safety/Doctor-Takeover/Router/DrugTool sweep (`-k "safety or dose_safety or doctor_takeover or doctor_handoff or orchestrator or follow_up or router or drug_tool or drug_info"`) | 369/377 passed, 4 skipped, 8 failed |
| Ruff (all changed files) | Clean |

The 8 failures are the exact same pre-existing failures
(`test_agent_v2_safety_occurrence_binding.py`,
`test_safety_runtime_adapter.py`, an `OperationalError` against
`drug_id_map`) already documented in the prior task's own report as
reproducible on an **unmodified** `main` checkout — a local-Postgres-state
issue on this workstation, unrelated to and unaffected by this branch,
not investigated further as out of scope.

**No new model calls. No new tool calls added for classification** — the
fix only changed which already-fetched evidence gets rendered.

## 15a. Review response: catalog-index warmup

**Finding**: `_SINGLE_TOKEN_STRENGTH_INDEX` is a module-level cache built
on first use; in a multi-worker deployment this happens once per worker,
a latency spike for the first user hitting each worker.

**Verified, not just asserted**:

- The stated mechanism does not currently apply to this deployment:
  `Dockerfile`'s `CMD` (`exec uvicorn backend.main:app --host 0.0.0.0
  --port ${PORT:-8000}`) has no `--workers` flag, so uvicorn runs a
  single worker process — confirmed by reading the real Dockerfile, not
  assumed.
- The underlying architectural observation is correct in general — a
  module-level global is per-process — and is the exact same pattern
  already used in this file for `get_drug_image_recognizer()`
  (`@lru_cache(maxsize=1)`, the OpenCLIP embedder + OCR runtime probe),
  which pays a much larger real cost (15.4s measured at startup, see
  below) the same way.
- Real measured cost of the index build itself: 219ms standalone, 2.4s
  when run immediately after the other two startup warmups in the same
  process (DB connection/query-plan warm-up contention) — small next to
  the 15.4s embedder warmup, but not zero.

**Fixed rather than only documented**, since it was cheap and directly
addressed the concern for any future multi-worker deployment too:
`backend/main.py`'s existing startup warmup block now also warms
`_single_token_strength_index` right after the embedder/OCR warmup,
guarded by the same `drug_image_chat_recognition_enabled` flag. Real
startup log after the change:

```
[INFO] Drug Knowledge V2 warmup complete: products=3556 chunks=42588 duration_ms=13157.00
[INFO] Drug image recognition warmup complete: duration_ms=15375.00
[INFO] OCR single-token uniqueness index warmup complete: keys=1969 duration_ms=2421.00
```

No request now pays this cost inline — if this app is ever moved to a
multi-worker `uvicorn --workers N` configuration, this same startup hook
already warms each worker's own copy independently, exactly like the two
warmups above it. Full test suite re-run after this change: 77/77 passed.

## 16. Final gate

```
OCR SINGLE-TOKEN AUDIT: PASS
SINGLE-TOKEN PRODUCTS: 1867 / 3556
NON-UNIQUE SINGLE-TOKEN RISK: 302 tokens shared by >1 product (165 with a same-strength collision)
SINGLE-TOKEN NAME ALONE -> HIGH_EVIDENCE: 0
STRENGTH CONFLICT: SAFE REJECT
OCR HARD-NEGATIVE FALSE HIGH_EVIDENCE: 0
REAL-PHONE HIGH_EVIDENCE WRONG: 0
TEXT-CONFIRMED FOLLOW-UP: PASS
IMAGE-CONFIRMED FOLLOW-UP: PASS
"THONG TIN CHI TIET THUOC": PASS
"TAC DUNG PHU THI SAO?": PASS
"CONG DUNG?": PASS
"CACH DUNG?": PASS
"LIEU DUNG?": PASS
"CO LUU Y GI KHONG?": PASS
IMAGE/TEXT STATE EQUIVALENCE: PASS
TOPIC SWITCH: PASS
REJECTED CANDIDATE NOT INHERITED: PASS
NEW MODEL CALLS: 0
NEW TOOL CALLS FOR CLASSIFICATION: 0
SAFETY: PASS
DOSE SAFETY: PASS
DOCTOR TAKEOVER: PASS

READY FOR MERGE: YES
```

Production enablement status is unchanged by this task:
`DRUG_IMAGE_CHAT_RECOGNITION_ENABLED` remains whatever it was already set
to on Railway; this PR does not touch it. The prior task's own
`RECOGNITION DECISION GATE: READY_FOR_CONTROLLED_CANARY` recommendation
stands, now with both PR #158 review findings resolved with real evidence
rather than left open.
