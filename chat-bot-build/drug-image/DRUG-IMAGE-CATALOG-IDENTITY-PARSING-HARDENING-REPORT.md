# DRUG IMAGE — CATALOG IDENTITY PARSING HARDENING REPORT

Task: `chat-bot-build/drug-image/Fix_drug_OCR_3.md`
Branch: `fix/drug-image-catalog-identity-parsing` (based directly on `origin/main`, not stacked on another PR branch — see the PR-stacking lesson from the previous task)
Worktree: `H:\Vin AI\P-067-catalog-identity-parsing`

---

## 1. LONG HUYẾT reproduction

**Real production trace** (already gathered from live `DRUG_RECOGNITION_EVIDENCE` logs during the earlier investigation that prompted this task — the user's screenshot of test13.jpg / "LONG HUYẾT P/H"):

- Visual retrieval correctly found the real LONG Huyết PH product as internal Top-1 in **3 of 4** real upload attempts (scores 0.62–0.77).
- OCR read text from the box (`ocr_status=OCR_AVAILABLE`).
- Outcome was `INSUFFICIENT_EVIDENCE` every time — "Ảnh hiện tại chưa đủ thông tin để nhận diện thuốc..."

**Exact source path**: `backend/services/drug_image_recognition.py`
`DrugImageRecognizer.recognize()` → `_rerank()` computes `name_match` via `_name_match()` → `_name_match()` compared OCR text against `_identity_segment_tokens()`, which (pre-fix) was "everything before the first strength-pattern match, or the whole `display_name` if none" → `_decide()` requires that match (plus strength/ingredient corroboration for single-token) before `HIGH_EVIDENCE_MATCH`.

**Root cause, confirmed by direct computation against the real catalog row** (`drug_product.display_name = "LONG Huyết PH 2x12 - TAN BẦM TÍM GIẢM PHÙ NỀ"`, no `mg/ml/g/%` pattern anywhere in the name):

| | OLD (pre-fix) identity tokens | matched against real OCR text |
|---|---|---|
| Pre-fix | `('long','huyet','2x12','tan','bam','tim','giam','phu')` — 8 tokens (whole name, since no strength pattern exists to cut on) | 5/8 = 62.5% (needs ≥75% for len≥2) → **no match** |
| **NEW** (this task) | `('long','huyet','ph')` — 3 tokens (pack + descriptive suffix correctly excluded) | **3/3 = 100% → match** |

Confirms the pre-fix diagnosis exactly: because this product has no machine-parseable strength, the old parser fell back to treating almost the entire `display_name` — including pack info (`2x12`) and pure marketing text (`TAN BẦM TÍM GIẢM PHÙ NỀ`) — as "identity," so `_name_match()` could never be satisfied by a real photo that (correctly) only shows the brand and a differently-worded tagline.

## 2. Catalog name-shape audit

Full audit of all **3556** production `drug_product` rows (`scripts` not committed — ad hoc audit script, real local Postgres mirror of the production catalog):

| Shape | Count | % |
|---|---|---|
| Has standard strength pattern (`mg/ml/g/%`) | 2659 | 74.8% |
| Has NxM pack pattern (e.g. `2x12`) | 2296 | 64.6% |
| Has pack-unit-word pattern (e.g. `10 viên`, `20 ống`) | 569 | 16.0% |
| Has any delimiter (`- / ( ) , :`) | 609 | 17.1% |
| Has `dosage_form` column populated | 3556 | 100.0% |
| **Neither strength nor any pack pattern found** | 21 | 0.6% |
| Contains a preserve-list token (P/H, Plus, Forte, Extra, XR, CR, SR) | 94 | — |

The "neither strength nor pack" 0.6% residual (21 products, e.g. `Diprospan INJ (5+2)mg/ml`, `Botox ... 100 Units`, foreign/parenthetical dose notation) is a genuinely hard bucket — see section 12 "Remaining catalog-data issues." (The audit script's own simplified pack regex slightly undercounts vs. the real `_PACK_PATTERN` in the shipped module — e.g. it misses `"Bilomag 6x10v"`, which the real parser correctly catches, per `test_abbreviated_pack_count_is_recognized`. Noted so the 0.6% figure isn't over-read as more precise than it is.)

**Collision risk after proposed parsing**: see section 5.

## 3. Parser design

New `CatalogIdentity` dataclass (`identity_text`, `strength_text`, `pack_text`, `descriptive_text`) built by `parse_catalog_identity(display_name)` in `backend/services/drug_image_recognition.py`. Does **not** modify stored `display_name` (section 16) — pure function, recognition-time only.

**Leftmost-cut strategy**: `identity_text` = everything **before** whichever structural marker occurs **earliest** in the string — strength match, pack match, a real descriptive delimiter, or a trailing parenthetical.

An earlier candidate strategy — "remove each matched span (strength/pack/etc.), keep whatever remains as identity" — was tried first and **rejected after it caused a real regression**: it corrupted Snapcef's identity into `"Snapcef /10ml HẢI Dương"` because the manufacturer text sitting *after* the strength/pack leaked into the kept remainder. Leftmost-cut avoids this by construction (nothing after the first marker is ever kept), and was verified correct for both Snapcef (unchanged) and LONG Huyết (correctly separated).

## 4. Identity/pack/description extraction

Real examples (from `test_drug_image_catalog_identity_parsing.py`, computed by the actual shipped `parse_catalog_identity`):

```
"LONG Huyết PH 2x12 - TAN BẦM TÍM GIẢM PHÙ NỀ"
  identity_text    = "LONG Huyết PH"
  pack_text         = "2x12"
  strength_text     = None
  descriptive_text  = "TAN BẦM TÍM GIẢM PHÙ NỀ"

"Snapcef 16mg/10ml HẢI Dương 20 ỐNG X 10ml"
  identity_text    = "Snapcef"
  strength_text     = "16mg/10ml"
  (pack/manufacturer text follows, correctly excluded from identity_text)
```

Supporting rules, each with a dedicated audit/test:

- **Pack parser** (`_PACK_PATTERN`): NxM (`2x12`), unit-prefixed (`chai 100ml`, `lọ 60 viên`), number+unit (`10 viên`), and the **abbreviated "Nv" form** (`3v`, `40v`, `6x10v`) — added after the audit first found 92 products (2.6%) with neither strength nor pack; almost all were abbreviated-viên shorthand. With it, only 21 (0.6%) remain genuinely hard.
- **Descriptive-suffix delimiter** (`_DESCRIPTIVE_SPLIT_PATTERN = \s[-,:]\s`): only a hyphen/comma/colon **surrounded by whitespace** counts as a real suffix separator. A bare hyphen with no surrounding space (`"Agi-neurin"`, `"Agilosart-h"`) is a compound brand token, not a delimiter — confirmed via real catalog audit and covered by `test_bare_hyphen_compound_brand_token_is_not_split`.
- **Abbreviation-join** (`_ABBREVIATION_JOIN_PATTERN`): joins `"P/H"` / `"P.H."` → `"PH"` before generic normalization (otherwise "P/H" splits into two orphaned 1-character fragments, both dropped by the 3-char minimum). `_PRESERVE_SHORT_TOKENS = {"ph","xr","cr","sr"}` exempts these from the general 3-character minimum.

## 5. Collision analysis

Full-catalog comparison, OLD vs. NEW identity parsing, all 3556 products (§12's own required check, run **before** wiring the parser in):

| | Collision groups | Products involved |
|---|---|---|
| OLD | 389 | 972 |
| **NEW** | **419** | **1034** |
| Newly-colliding (collide under NEW, did not under OLD) | 30 groups | — |
| Newly-separated (collided under OLD, no longer under NEW) | 2 | — |

This is a **real, expected increase**, not a defect: most of the 30 newly-colliding groups are the same real brand collapsing correctly across pack-size variants that previously looked like different identities only because unrelated pack/manufacturer text leaked into the old comparison (e.g. `"B Complex C Vidipha 2x10"` / `"...3x10"` / `"...100v"`, `"Fluotin 20 Stella 10x10"` / `"...2x10"`, `"Nasrix DAVI 4x7"` / `"...6x10"`). This is exactly the semantic improvement section 3 asks for — but it does mean multi-token identity matches, which previously had **no** catalog-uniqueness gate at all, now need one too (section 8, below).

One genuine parsing imperfection found by this same audit and **not fixed** (documented per section 12's "risky shortened identities" + section 16's "report catalog-data errors separately," not silently patched with a special case): `"Magnesi - b6 Khapharco 10x10"` / `"Magnesi - b6 Stella Tablet 10x10"` — the real identity-relevant qualifier `"b6"` sits right after a whitespace-hyphen, so the general descriptive-suffix rule (correctly, in the common case — see `"BAR Pharmedic 180v - Thuốc LỢI GAN MẬT"` right below it in the same audit output, a genuine positive split) also swallows it here, reducing this pair's identity to just `("magnesi",)`. **Safety is not compromised** — this collision is caught by the same section 8 uniqueness gate as any other (needs corroboration, cannot alone reach `HIGH_EVIDENCE_MATCH`) — but match quality for this specific product pair is reduced versus a hypothetical smarter split. Not fixed in this task: fixing it generically (distinguishing "real manufacturer/pack text after a hyphen" from "real marketing description after a hyphen") is a nontrivial, separately-scoped linguistic heuristic, and the task's own stop rule forbids product-specific hacks.

## 6. OCR name-matching changes

`_name_match()` now compares OCR text against `_identity_segment_tokens()`, itself now `_meaningful_tokens(parse_catalog_identity(display_name).identity_text)` — i.e. the **parsed** identity only, never `pack_text`/`descriptive_text`. Preserved unchanged from Fix_drug_OCR_2.md:

- single-token vs. multi-token distinction (`identity_token_count`)
- strength corroboration / ingredient corroboration
- hard strength conflict (`STRENGTH_CONFLICT`)
- visual Top-1 requirement
- explicit user confirmation (never auto-confirmed)

**A real, previously-undetected bug was found and fixed while validating this section** (not part of the original plan — found because `test_p_slash_h_abbreviation_normalizes_consistently_with_dotted_form` and the LONG-Huyết reconstruction test both failed on first run): `_ABBREVIATION_JOIN_PATTERN`'s trailing `\B` assertion only matched when another word character immediately followed the abbreviation (e.g. `"P/Hz"`) — the *common* real case, `"P/H"` at the end of a line or before whitespace/punctuation (exactly how it's printed on the real LONG Huyết box), **never joined at all**. Separately, the join was only ever applied to the *catalog* side (inside `_meaningful_tokens`) — the raw OCR-observed text was normalized through a different path (`extract_structured_signals` → `normalize_for_match`) that never called the join at all, so even a correctly-joined catalog token `"ph"` had nothing to match against on the OCR side. Both are fixed: the boundary condition is now `(?!\w)` (correct for end-of-string/whitespace/punctuation), and the join now lives inside `normalize_for_match()` itself so both the catalog-identity path and the OCR-signal-extraction path apply it identically.

## 7. Hard-negative tests (section 11, cases A–G)

New file `tests/services/test_drug_image_catalog_identity_parsing.py`, full-recognizer level (real SQLite catalog + fake embedder/OCR), one test per lettered case — the single-token equivalents of most of these were already covered by `test_drug_image_ocr_name_hardening.py` (Fix_drug_OCR_2.md) and are not repeated:

| Case | Scenario | Result |
|---|---|---|
| A | Same multi-token identity, different strength | `STRENGTH_CONFLICT`, not `HIGH_EVIDENCE_MATCH` |
| B | Same multi-token identity, no strength, 2 real products (`"B Complex C Vidipha"` pack variants) | `AMBIGUOUS_MATCH` + `CATALOG_IDENTITY_NON_UNIQUE` |
| C | Identity differs only by a preserved suffix (`"Pruzena"` vs `"Pruzena Forte"`) | not `HIGH_EVIDENCE_MATCH` when OCR doesn't read "Forte" |
| D | Two different real brands sharing identical descriptive/marketing text | not `HIGH_EVIDENCE_MATCH` from descriptive text alone |
| E | Same leading token(s) (`"Agi"`), different real brand | full-identity match required, not a first-N-words shortcut |
| F | Same identity + strength, pack suffix differs, 2 real products | `AMBIGUOUS_MATCH` + `CATALOG_IDENTITY_NON_UNIQUE` |
| G | Descriptive suffix differs (real LONG Huyết reproduction) | reaches `HIGH_EVIDENCE_MATCH`, `DESCRIPTION_IGNORED_FOR_IDENTITY` fires, no `OCR_HARD_CONFLICT` |

**Result: 0 false `HIGH_EVIDENCE_MATCH` across all 7 hard negatives** — required by section 11, confirmed by a real (not fabricated) run: 15/15 tests pass in this file; 11/11 in the updated `test_drug_image_ocr_name_hardening.py` (renamed to the generalized symbols, one assertion corrected — see section 12).

## 8. Snapcef regression (real photos)

Reran `test01.jpg`–`test08.jpg` through the full pipeline (real OpenCLIP embedder + real Tesseract OCR, local Postgres mirror of the real 3543-row production catalog+embeddings) — identical harness to the one used in the prior task, only the recognizer module changed:

| Metric | Before this task | After this task |
|---|---|---|
| Outcome distribution | `HIGH_EVIDENCE_MATCH=1, AMBIGUOUS_MATCH=6, INSUFFICIENT_EVIDENCE=1` | **unchanged** |
| Top-1 correct product | 2/8 | **unchanged** (2/8 — limited by visual retrieval on 6/8 blurry/off-angle photos, out of this task's scope; see prior task's report) |
| `HIGH_EVIDENCE_MATCH` but WRONG | 0 | **0 — no regression** |

**No safety regression.** test01.jpg still correctly reaches `HIGH_EVIDENCE_MATCH` via `SINGLE_TOKEN_NAME_MATCH` + `CATALOG_IDENTITY_MATCH` + `OCR_STRENGTH_MATCH`, `identity_unique=True`, `identity_strength_unique=True`.

## 9. LONG Huyết regression

**test13.jpg's raw file is not available locally** (only the real production trace data gathered during the original investigation) — checked explicitly (a filesystem search across the whole repo tree and every known local drug-image storage location found nothing named `test13`/`long_huyet`). This is reported honestly rather than fabricating a substitute photo.

In place of a literal image rerun, two independent, non-fabricated checks were used, both against the **real, unmodified** production catalog row and the **real** OCR text pattern from the original trace ("LONG HUYẾT P/H" plus differing marketing lines):

1. **Direct computation** (section 1 table): parsed identity tokens change from 8 (62.5% match, fails the ≥75% bar) to 3 (100% match).
2. **`test_g_descriptive_mismatch_does_not_block_an_otherwise_unique_corroborated_match`**: runs the actual `DrugImageRecognizer.recognize()` (real module code, not mocked business logic) against the real catalog display_name, with the real observed OCR text shape (`"LONG HUYẾT P/H\nTan bam tim\nMau lanh vet thuong"`) via a deterministic `StaticOcr` stub (only the OCR *extraction* step is stubbed — everything downstream is real). Result: `HIGH_EVIDENCE_MATCH`, `DESCRIPTION_IGNORED_FOR_IDENTITY` present, `OCR_HARD_CONFLICT` absent.

Visual retrieval itself was not touched by this task (out of scope per the task's own stop rule) — its real behavior (Top-1 correct in 3/4 real attempts) is unchanged.

## 10. Observability

`RecognitionObservability` (and the `DRUG_RECOGNITION_EVIDENCE` structured log line in `backend/api/drug_image_chat_routes.py`) gained, per section 14:

- `parsed_identity_token_count` (int, never the raw identity string)
- `pack_detected` / `description_suffix_detected` (bool)
- `identity_unique` / `identity_strength_unique` (bool) — the latter generalizes and **replaces** Fix_drug_OCR_2.md's single-token-only `ocr_single_token_non_unique` field (same underlying value, inverted and renamed; nothing outside this module and its own tests referenced the old field name)

New decision reason codes (all additive — every pre-existing code from Fix_drug_OCR_2.md is unchanged): `CATALOG_IDENTITY_MATCH`, `CATALOG_IDENTITY_NON_UNIQUE`, `PACK_TEXT_MATCH`, `DESCRIPTION_IGNORED_FOR_IDENTITY`, `IDENTITY_PARSE_AMBIGUOUS`. No raw OCR text or raw identity string is ever logged.

`PACK_TEXT_MATCH` is honestly a low-yield signal in practice: pack text frequently reduces to only dosage-form words already filtered out as noise (e.g. Snapcef's `"20 ống x 10ml"` → the meaningful-token filter drops "ống" as a dosage word and "20"/"x" as sub-3-char — leaving no comparable pack tokens at all), so it did not fire on any of the 8 real Snapcef photos. It remains correctly wired (never decision-affecting) and does fire for pack strings that keep a real word (verified at the unit level); its main value today is future-proofing plus increasing the audit trail's completeness, not routinely stronger evidence.

## 11. Performance

`_identity_uniqueness_index()` (renamed/generalized from `_single_token_strength_index`) is still a module-level, process-lifetime cache — one full `drug_product` table scan (~3556 rows), same shape and same real measured cost class (~220ms) as its single-token-only predecessor, warmed once at startup in `backend/main.py` alongside the OpenCLIP/OCR warmup. No new per-request full-catalog scans. `backend/main.py`'s warmup call site was updated to the renamed function.

## 12. Remaining catalog-data issues

Per section 16 ("report catalog-data errors separately," never mass-edit `display_name`):

1. **21 products (0.6%) with neither a strength nor a pack pattern** — parenthetical combo-strength (`"(5+2)mg/ml"`), foreign units (`"100 Units"`), or bare brand+manufacturer with no structured info at all. Identity parsing still works for these (falls back to the whole cleaned name), but there is nothing to corroborate a single-/multi-token match against beyond name text itself.
2. **`"Magnesi - b6 ..."` shape** (section 5) — a real identity-relevant qualifier can be swept into `descriptive_text` when it directly follows a whitespace-hyphen that also (correctly, in the common case) marks real marketing text. Safety-gated, not fixed.
3. Not a catalog-data issue but adjacent: this task also fixed a real bug in the OCR-normalization pipeline unrelated to catalog parsing per se (section 6) — the P/H abbreviation join.

## Test suite update note

`tests/services/test_drug_image_ocr_name_hardening.py` was updated in place (renamed symbols only — `_SINGLE_TOKEN_STRENGTH_INDEX`→`_IDENTITY_COUNT_INDEX`/`_IDENTITY_STRENGTH_COUNT_INDEX`, `_is_single_token_non_unique`→`_is_identity_non_unique`, `single_token_non_unique`→`identity_non_unique` field, `"NON_UNIQUE_SINGLE_TOKEN"`→`"CATALOG_IDENTITY_NON_UNIQUE"`). One assertion was corrected, not just renamed, and is called out explicitly since it is a real behavior change worth being honest about: `_is_identity_non_unique(session, ("acyclovir",), set())` now returns `True` (was `False` under the old single-token-only function) when the catalog shows a real collision and OCR read **no** strength at all. This does not change any single-token `_decide()` outcome (that path is independently gated by the pre-existing corroboration requirement either way) — it is a deliberate strengthening needed specifically for the **new** multi-token path, which has no separate corroboration requirement when the identity is unique, so an unresolvable multi-token collision with zero OCR strength signal must not slip through this check.

A **pre-existing, unrelated** test-isolation issue was found (not caused by this task): `test_drug_image_ocr_name_hardening.py` sets `INTERNAL_AUTH_SECRET`/`JWT_SECRET` at module import time; in one specific narrow file-subset pytest invocation (that file + `tests/test_v2_dose_safety_http.py` run together, nothing else), this caused a spurious 401 in the dose-safety HTTP test. Confirmed pre-existing by reproducing it with the OCR hardening file completely unmodified (`git stash` equivalent — this task's own added file was not even present). Does not reproduce in the full regression run order actually used below. Not fixed (out of scope for this task).

Separately, local Postgres was found 4 migrations behind `origin/main`'s head (`0056` vs `0060`) at the start of this task's regression pass — unrelated local-environment staleness from earlier in this session, not a code defect. Applied `alembic upgrade head` (dev DB only) before the final regression run below.

## 13. Final gate

```
CATALOG PRODUCTS AUDITED:
3556 / PASS

IDENTITY PARSER:
PASS

PACK PARSER:
PASS

DESCRIPTION EXCLUDED FROM IDENTITY:
PASS

OLD IDENTITY COLLISIONS:
389 groups / 972 products

NEW IDENTITY COLLISIONS:
419 groups / 1034 products

UNSAFE NEW COLLISIONS:
0 / 30 (all 30 newly-colliding groups gated by the generalized
        catalog-uniqueness check; cases B and F directly test this)

SINGLE-TOKEN HARDENING PRESERVED:
PASS (11/11 tests in test_drug_image_ocr_name_hardening.py)

STRENGTH CONFLICT PRESERVED:
PASS

OCR HARD-NEGATIVE FALSE HIGH_EVIDENCE:
0 / 7 (cases A-G, test_drug_image_catalog_identity_parsing.py)

SNAPCEF HIGH_EVIDENCE WRONG:
0 / 8 real photos (unchanged from before this task)

LONG HUYET VISUAL TOP-1:
PASS (real production trace, unaffected by this task -- visual
      retrieval not modified)

LONG HUYET IDENTITY MATCH:
PASS (direct computation + test_g, real catalog row + real OCR
      text shape; raw test13.jpg unavailable locally -- see section 9)

LONG HUYET NO LONGER BLOCKED BY DESCRIPTION:
PASS

LONG HUYET OUTCOME:
HIGH_EVIDENCE (via reconstruction test -- section 9; not a literal
               live photo rerun, source file unavailable)

CONFIRMATION:
NOT_APPLICABLE (confirmation mechanism itself unchanged and
                regression-tested -- tests/test_drug_confirmation_*
                pass; no LONG-Huyết-specific live E2E was run,
                source photo unavailable)

FOLLOW-UP:
NOT_APPLICABLE (same reasoning as CONFIRMATION above --
                tests/test_agent_v2_follow_up.py and
                test_agent_v2_build43_follow_up_resolution.py pass
                unchanged)

NEW MODEL CALLS:
0

NEW TOOL CALLS:
0

SAFETY:
PASS (tests/test_safety.py, tests/test_agent_v2_safety.py)

DOSE SAFETY:
PASS (tests/test_v2_dose_safety_http.py + dose test files, 48/48;
      local Postgres migrated to head first -- see test suite update note)

DOCTOR TAKEOVER:
PASS (tests/test_agent_v2_doctor_takeover.py)

READY FOR MERGE:
YES, pending human review and explicit approval to open/merge the
PR (per this session's standing process -- no auto-merge/deploy).
```

**Full regression run** (253 tests, single combined pytest invocation, local Postgres at head): drug-image recognition/chat/OCR/retrieval services and API routes, drug confirmation dispatch + E2E, agent-v2 follow-up (general + BUILD-43), agent-v2 safety, safety, doctor takeover, dose confirmation/push-reminder/status/summary, dose-safety HTTP, pending-confirmation-cleared-on-redflag — **253/253 passed**. `ruff check` clean on every changed/new file (`backend/services/drug_image_recognition.py`, `backend/api/drug_image_chat_routes.py`, `backend/main.py`, `tests/services/test_drug_image_ocr_name_hardening.py`, `tests/services/test_drug_image_catalog_identity_parsing.py`).

---

**Not done in this task** (per its own stop rule): no global OCR threshold change, no LONG-Huyết special case, no first-N-words shortcut, no weakening of single-token hardening or strength conflict, no Top-3 UI restore, no auto-confirm, no mass-edit of production catalog names, no changes outside drug-image recognition (confirmed via `git diff --stat`: 3 modified files + 1 new test file, all inside `backend/services/drug_image_recognition.py`, `backend/api/drug_image_chat_routes.py`, `backend/main.py`, and `tests/`).

**Next step**: create the PR from `fix/drug-image-catalog-identity-parsing` → `main` and stop for review, per this session's established process.
