# DRUG IMAGE — PARTIAL-TOKEN MATCH FOLLOW-UP REPORT

Follow-up to `chat-bot-build/drug-image/Fix_drug_OCR_3.md` (PR #165, merged), triggered by a **real production finding** discovered while verifying PR #165 live: a real user tested LONG Huyết PH again after the fix shipped, and it still did not reach `HIGH_EVIDENCE_MATCH`.

Branch: `fix/drug-image-partial-token-match` (based directly on current `origin/main`, i.e. `origin/main` **after** PR #165's merge — not stacked on PR #165's own now-dead branch, per the PR-stacking lesson from earlier this session)
Worktree: `H:\Vin AI\P-067-partial-token-match`

---

## 1. Real production reproduction

Pulled real `DRUG_RECOGNITION_EVIDENCE` logs from production (`railway logs --service VMEC-04/BE`) for a live test session immediately after PR #165 deployed. 4 real attempts, 2 real products involved (looked up via a temporary read-only tcp-proxy against the production catalog, deleted immediately after use):

| Attempt | Product | `ocr_signal_count` | visual Top-1 score | `ocr_name_match` | Outcome |
|---|---|---|---|---|---|
| 1 | Silvirin 20g SP (tuýp) | 5 | 0.622 | False | `INSUFFICIENT_VISUAL_EVIDENCE` |
| 2 | **LONG Huyết PH 2x12 - TAN BẦM TÍM GIẢM PHÙ NỀ** | 0 | 0.757 | False | `AMBIGUOUS_MATCH` |
| 3 | LONG Huyết PH (same) | 2 | 0.719 | False | `INSUFFICIENT_VISUAL_EVIDENCE` |
| 4 | LONG Huyết PH (same) | 2 | 0.766 | False | `INSUFFICIENT_VISUAL_EVIDENCE` |

Visual retrieval correctly found LONG Huyết PH as Top-1 in all 3 of the attempts where it was the true product, with reasonable scores (0.72–0.77) — but `ocr_name_match=False` every single time. `parsed_identity_token_count=3` (`long`, `huyet`, `ph`) confirms PR #165's parser is working as designed; the blocker is that `_name_match`'s ≥75% bar for a 3-token identity requires **all 3** tokens (2/3 = 66.7% < 75%), so OCR missing even one token — plausible for real photos of small/stylized text like "PH" — fails the whole match. This is a genuine gap PR #165 did not close: it fixed the *parsing* (what counts as identity), but the *matching* threshold still has no tolerance for a single missed token on 3+-token identities.

## 2. Considered and rejected: global threshold reduction

The user initially asked to lower the global OCR match threshold from 75% to 60%. Declined, with reasoning given directly to the user and confirmed via `AskUserQuestion`:

- `Fix_drug_OCR_3.md`'s own stop rule explicitly forbids this ("lower global OCR threshold"), twice.
- A global reduction would weaken matching for **all 3556 catalog products**, not just the one case motivating the request — increasing false-suggestion risk across the whole catalog, including cases with no such OCR problem.
- Confirmation-before-binding (already in place, unchanged) reduces but does not eliminate the real-world risk of a wrong suggestion being rubber-stamped by a user in a hurry — a known UX-safety pattern in medical software, not a purely theoretical concern.

User chose instead: **scoped partial-match tolerance requiring additional corroboration**, mirroring the existing single-token corroboration mechanism rather than a blanket threshold change.

## 3. Design: partial-match tier

`_name_match()` gains a third score tier (0.5, alongside the existing 1.0/0.0): identities with **≥3 tokens**, missing **exactly one**. Deliberately excludes 2-token identities dropping to 1 match — that shape is indistinguishable from the single-token case, which this project already treats as high-risk for a documented, real reason (the Forte/Plus/XR/SR/CR hard-negative case from PR #165's own test suite: "Pruzena" vs "Pruzena Forte" — a missing token there is a *different real product*, not OCR noise).

`_decide()` treats a partial match at least as strictly as single-token: it is never independently sufficient, always requires strength or ingredient corroboration, and is additionally gated by catalog uniqueness (existing `_is_identity_non_unique`, generalized in PR #165).

### New safety gate: matched-subset collision

A partial match has a risk single-token matches don't: the **specific missing token** might itself be genuinely distinguishing rather than noise (exactly the Forte case, generalized to 3+ tokens). Before wiring in the partial tier, audited the real production catalog for this exact risk:

```
3+-token products: 704
Products where SOME drop-one-token subset collides with
another product's full identity: 39 (5.5%)
```

Real examples found: `"Clazic SR United 10x10"` (dropping "SR" collides with a real `"...United"`-only identity), `"Clopalvix PLUS Boston 3x10"` (dropping "PLUS" collides with `"...Boston"`), `"Codiovan 160/25 Novartis"` (dropping the strength-shaped token collides with `"Codiovan Novartis"`). This confirmed the risk is real, not hypothetical, and sized it precisely (5.5%, not "some").

New function `_matched_subset_collides_with_other_identity()`: checks whether the OCR-matched subset of tokens is itself the *complete* identity of some other real catalog product (reusing the existing catalog identity-count index — no new full-table scan). When true, `RecognitionCandidate.partial_subset_ambiguous=True` blocks `HIGH_EVIDENCE_MATCH` for that candidate **regardless of corroboration** — new reason code `PARTIAL_MATCH_SUBSET_AMBIGUOUS`.

## 4. New reason codes / observability

- `PARTIAL_TOKEN_NAME_MATCH` — positive path, mirrors `SINGLE_TOKEN_NAME_MATCH`.
- `PARTIAL_TOKEN_NEEDS_CORROBORATION` — degrade path, no strength/ingredient signal.
- `PARTIAL_MATCH_SUBSET_AMBIGUOUS` — degrade path, matched subset collides with another product.
- `RecognitionObservability.ocr_partial_token_name_match: bool` (new field, mirrors `ocr_single_token_name_match`).
- `text_evidence` field `"product_name_match_partial"` added to the existing duplicate-content-ambiguity resolution set (consistent with how single-token match is already treated there).

## 5. Tests (real, run, all passing)

`tests/services/test_drug_image_catalog_identity_parsing.py`, 5 new tests added to the 15 already there (20/20 pass):

1. Partial match + ingredient corroboration + unambiguous subset → `HIGH_EVIDENCE_MATCH`.
2. Partial match, no corroboration → `AMBIGUOUS_MATCH` / `PARTIAL_TOKEN_NEEDS_CORROBORATION`.
3. Partial match + corroboration, but matched subset collides with another real product's full identity (mirrors the real `"Clazic SR United"` finding) → still blocked, `PARTIAL_MATCH_SUBSET_AMBIGUOUS`.
4. Direct `_name_match()` unit test: a 2-token identity missing 1 token does **not** get the partial tier (score stays 0.0) — the deliberate scope boundary.
5. **`test_long_huyet_real_production_gap_partial_match_alone_insufficient`** — see section 6 below; locks in the honest current limitation as a regression test rather than letting it silently drift.

Full regression (258 tests: drug-image services/API, drug confirmation, follow-up, safety, dose safety, doctor takeover) — 258/258 passing, local Postgres at migration head. Snapcef 8-real-photo regression rerun, unchanged (2/8 top-1 correct, 0 wrong `HIGH_EVIDENCE_MATCH`). `ruff check` clean.

## 6. Honest limitation: this fix does not (yet) fully resolve the real user's case

Checked directly against the real production catalog row for the specific product the user tested (`b983cc89-23b2-50bd-bb94-36a88f6a9866`, via the same temporary read-only tcp-proxy, deleted immediately after):

```
id: b983cc89-23b2-50bd-bb94-36a88f6a9866
display_name: LONG Huyết PH 2x12 - TAN BẦM TÍM GIẢM PHÙ NỀ
strength_text: None
dosage_form: Viên nang cứng
ingredients: None (no drug_product_ingredient rows)
```

**This specific product has no strength_text and no registered ingredient data in the catalog.** Even with the partial-match tier now in place, `identity_eligible` still requires `strength_matched or ingredient_matched` — and for this exact product, neither signal can ever be produced, regardless of how well OCR reads the box. If OCR misses "PH" on a future real photo of this exact product, it will still degrade to `AMBIGUOUS_MATCH` (test #5 above locks this in), not reach `HIGH_EVIDENCE_MATCH`.

This is a **catalog-data gap, not a code defect** — `dosage_form` is populated ("Viên nang cứng") and was named as an acceptable corroboration type in the original task spec (`Fix_drug_OCR_3.md` section 8: "strength / ingredient / dosage form / other reliable structured signal"), but no OCR-side dosage-form signal extraction exists yet to make use of it, and building one is a larger, separately-scoped effort (would need a new structured-signal extractor plus its own validation against real photos, not a small addition). Not attempted in this follow-up — flagged honestly instead of silently left out.

`AMBIGUOUS_MATCH` is not a failure state: the real product is still offered as the (first-ranked) candidate for the user to select — the user does not need to type the name from scratch, just pick from a short list instead of a single yes/no confirm. This is the current, correct, safe behavior given the catalog's actual data, not a regression from this fix.

## 7. Final gate

```
REAL PRODUCTION FAILURE REPRODUCED:
PASS (4 real attempts pulled from production logs, root-caused precisely)

GLOBAL THRESHOLD REDUCTION:
NOT DONE (user informed of risk, chose scoped alternative instead)

PARTIAL-MATCH TIER SCOPE:
3+ token identities only, missing exactly 1 token (PASS -- verified via
dedicated unit test that 2-token identities are excluded)

SUBSET-COLLISION SAFETY GATE:
PASS (real catalog audit: 5.5% of 3+-token products, 39/704, have this
risk; new test reproduces the exact real shape found -- "Clazic SR
United")

FORTE-STYLE HARD NEGATIVE (PR #165's own test) STILL PASSING:
PASS (no regression)

NEW REASON CODES WIRED (observability + decision):
PASS

TESTS:
20/20 (catalog identity parsing file) + 258/258 (full regression)

RUFF:
CLEAN

REAL USER'S EXACT CASE (LONG Huyết PH) NOW REACHES HIGH_EVIDENCE:
NO -- catalog-data gap (no strength_text, no ingredient data for this
specific product), documented honestly, locked in as a test, not
silently claimed fixed. AMBIGUOUS_MATCH with the correct product still
offered remains the current, safe outcome for this specific product.

READY FOR MERGE:
YES, pending human review and explicit approval (no auto-merge/deploy,
per this session's standing process).
```
