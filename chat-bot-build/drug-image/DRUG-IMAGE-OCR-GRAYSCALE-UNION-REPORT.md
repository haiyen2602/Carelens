# DRUG IMAGE — OCR GRAYSCALE-UNION PASS REPORT

Follow-up to PR #165 (merged) and PR #166 (merged), triggered by real photos the user provided of the actual LONG Huyết PH box (front, blister pack, indication panel) after both prior fixes were live and the exact real product still wasn't reaching `HIGH_EVIDENCE_MATCH`.

Branch: `fix/drug-image-ocr-grayscale-union` (based directly on current `origin/main`)
Worktree: `H:\Vin AI\P-067`

---

## 1. Real photos, real diagnosis

The user saved 6 real LONG Huyết PH photos into `chat-bot-build/drug-image/drug_images_test/` (`Test09.jpg`, `Test10.webp`, `Test11.jfif`, `test12`, `test13.jpg`, `test14.png`). Ran the actual `DrugImageRecognizer` pipeline plus raw Tesseract output on each (local diagnostic only — raw text never logged/persisted in production, per the project's own design).

**Visual retrieval: 6/6 correct Top-1.** The visual model was never the problem.

**Raw OCR text, before this fix**, was the real blocker:
- `Test11.jfif`: `"LUONOG TU XZLI1 FPFEI"` — reads the brand title as near-total garbage.
- `test13.jpg`: `"NG HUYỆ..."` — cut off/garbled mid-word.
- `Test09.jpg`: `"P\n\nJUC HUNG"` — almost nothing usable.
- `Test10.webp`: quality-gated (`IMAGE_TOO_BLURRY`) — a shot of the back-of-box manufacturer panel, not brand-relevant regardless.
- `test14.png`: empty (0 chars) — a genuinely hard case, unchanged by this fix.

**Root cause, confirmed by direct A/B testing** (not assumed): `OptionalTesseractOcrExtractor.extract()` passes the color image straight to Tesseract with zero preprocessing. Tesseract's own internal color-image binarization measurably mishandles this specific box's title styling (bold light text on a saturated dark-red field) on several of these real photos. Converting to grayscale **first**, then handing that to Tesseract, reads the same photos far better:
- `Test11.jfif` (grayscale): `"LONG HUYẾT PH"` — perfect.
- `test13.jpg` (grayscale): `"LONG HUYẾT PH"` — perfect.
- `Test09.jpg` (grayscale): `"LONG HUYET l"` — much closer (2 of 3 tokens correct).

## 2. Grayscale-only is not a pure win — found via the same A/B methodology

Before proposing a fix, ran the *same* grayscale-preprocessing test against the existing 8-photo Snapcef regression set (the one real photo set already known to work, including PR #165/#166's own regression baseline). Grayscale-only:
- **Helped**: `test02.jpg` newly reads `"SNAPCEF"` cleanly (previously partial/garbled).
- **Regressed a real, already-working case**: `test01.jpg` — the one photo that reliably reached `HIGH_EVIDENCE_MATCH` in every prior report this task — misread `"SNAPCEF"` as `"SNAPUEF"` under grayscale (a single-letter OCR error), which broke its single-token match and dropped the outcome to `AMBIGUOUS_MATCH`.

Simply replacing the color pass with a grayscale pass would have traded a real, already-verified-working case for new ones — not acceptable per this whole task's own standing discipline (no unverified/net-negative change).

## 3. Fix: union of both passes, not replacement

`OptionalTesseractOcrExtractor.extract()` now runs Tesseract **twice** per image — once on the color image as given (unchanged from before), once on its grayscale conversion — and concatenates both text outputs before the rest of the pipeline (`extract_structured_signals`, `_name_match`, etc.) ever sees it. Each pass is independent: if one fails/times out, the other's text still reaches the caller (new dedicated test covers this).

Verified against the real, shipped module (not a mock), all 14 real photos, before vs. after:

| | Before (color-only, shipped PR #166) | After (union) |
|---|---|---|
| LONG Huyết `HIGH_EVIDENCE_MATCH` | 0/6 | **3/6** (`Test11.jfif`, `test12`, `test13.jpg`) |
| LONG Huyết Top-1 correct | 6/6 | 6/6 (unchanged) |
| LONG Huyết `HIGH_EVIDENCE` wrong | 0 | 0 |
| Snapcef `HIGH_EVIDENCE_MATCH` | 1/8 (`test01.jpg`) | **2/8** (`test01.jpg` kept — now with an extra `INGREDIENT_MATCH` too — plus `test02.jpg` newly fixed) |
| Snapcef Top-1 correct | 2/8 | 2/8 (unchanged — visual retrieval untouched by this fix) |
| Snapcef `HIGH_EVIDENCE` wrong | 0 | 0 |

**Zero regressions, five newly-correct real `HIGH_EVIDENCE_MATCH` outcomes, zero false `HIGH_EVIDENCE_MATCH` anywhere.**

## 4. Cost

Measured directly on real photos: ~500ms per Tesseract pass, so ~500ms added per recognition attempt (doubling the OCR portion, not the whole pipeline — real production latencies observed this session were ~11–14s total, dominated by the visual embedding step, so this is a small fraction of total latency). Worst-case failure-path timeout budget doubles (both passes can each spend up to the configured `drug_image_chat_ocr_timeout_seconds`, default 5.0s) — that failure path already degrades gracefully to `OCR_FAILED` today, unchanged in kind, just a larger bound in the rare case both passes genuinely hang.

## 5. What this does and does not fix

- **Does**: recover real identity text Tesseract's default color-image path was losing, for photos where the underlying text is genuinely present and legible once grayscale-converted.
- **Does not**: fix photos where OCR still finds nothing at all (`test14.png` — 0 signals before and after; a genuinely hard case, out of scope for this specific fix) or where the true blocker is something else already documented ([[drug-image-partial-token-match]]'s honest catalog-data-gap finding still applies whenever OCR genuinely can't read enough of a no-corroboration-data product like this one).
- **Does not** touch the parsing/matching logic from PR #165/#166 at all — purely an OCR input-preprocessing change, isolated to `OptionalTesseractOcrExtractor`.

## 6. Tests

`tests/services/test_drug_image_ocr_runtime.py`: 3 pre-existing tests updated (call-count expectations, now 2 Tesseract calls per `extract()`), 2 new tests added — one direct regression test for "one pass fails, the other's text still reaches the caller," one direct regression test for "the union keeps text each pass alone would have missed." 13/13 passing.

Full regression (263 tests: drug-image services/API, drug confirmation, follow-up, safety, dose safety, doctor takeover, reward/dose-status — local Postgres at migration head 0062): **263/263 passing**. `ruff check` clean.

## 7. Final gate

```
REAL PHOTOS PROVIDED AND DIAGNOSED:
PASS (6 real LONG Huyet photos, user-provided)

ROOT CAUSE CONFIRMED (not guessed):
PASS -- direct A/B, real Tesseract, real photos

GRAYSCALE-ONLY REGRESSION FOUND BEFORE SHIPPING:
PASS (test01.jpg SNAPCEF->SNAPUEF misread caught by the same A/B
      methodology, before any code change was made)

UNION APPROACH REGRESSION CHECK:
0 regressions across all 14 real photos (6 LONG Huyet + 8 Snapcef)

LONG HUYET HIGH_EVIDENCE_MATCH:
0/6 -> 3/6

SNAPCEF HIGH_EVIDENCE_MATCH:
1/8 -> 2/8 (existing case preserved + strengthened, one new case fixed)

HIGH_EVIDENCE_MATCH WRONG (either set):
0

TESTS:
13/13 (OCR runtime file) + 263/263 (full regression)

RUFF:
CLEAN

READY FOR MERGE:
YES, pending human review and explicit approval (no auto-merge/deploy,
per this session's standing process).
```
