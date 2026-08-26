# DRUG-IMAGE-B05 — Multi-Signal Drug Recognition V1 Report

## Executive summary

B-05 adds an internal, deterministic candidate-recognition service: quality
gate → B-04 OpenCLIP Top-10 candidates → optional visible-text OCR →
normalization/extraction → explainable rerank → semantic outcome. It never
identifies a drug, calls the Drug Tool, exposes an upload API, persists query
images/OCR/query vectors, or produces medical facts.

It is ready for PR as a bounded safety baseline. It is not production approval
for phone-photo recognition: no local Vietnamese OCR engine, independent
phone-photo corpus, or defensible real-world unknown corpus was available.

## Parallel workstream safety and baseline

- Dedicated branch/worktree: `feature/drug-image-b05-multisignal-recognition`.
- Baseline: `fa581ca37e4fd7b78156354d218dac9cff28bf87` (B-04 PR #132 merge).
- B-04 was confirmed merged and reachable from `origin/main` before B-05.
- No migration, schema, production DB, Track A, B-06, B-07, chatbot, or
  reminder files were changed.

## B-04 audit and compatibility

`DrugImageEmbedding` remains B-04 OpenCLIP ViT-B/32, 512-dimension,
versioned-preprocessing embedding. Candidate generation calls existing exact
cosine `search_similar_drug_images` for product-deduplicated Top-10 results;
B-05 neither regenerates nor changes embeddings.

The isolated B-04 validation DB contained 3,556 products, 3,543 validated
`DrugImage` rows and 3,543 corresponding embeddings. It also confirmed three
normalized-checksum groups spanning ten products. An unresolved group is
`AMBIGUOUS_MATCH`, never a forced product identity.

## Runtime metadata audit

| Field | Status | B-05 use |
| --- | --- | --- |
| Product display name | RUNTIME_STRUCTURED | Name corroboration/reranking |
| `strength_text` | RUNTIME_STRUCTURED but sparse | Strength corroboration/conflict when present |
| Dosage form | RUNTIME_STRUCTURED | Returned metadata only; not a confidence signal |
| Ingredient relation | RUNTIME_STRUCTURED | Optional text corroboration |
| Source product ID/page URL | SOURCE_ONLY | Provenance only; not fused |
| Registration number | MISSING at runtime | OCR may extract it, but it is not fused |
| Manufacturer/producer | MISSING at runtime | OCR may extract it, but it is not fused |
| Package text/SKU/normalized names | MISSING or unreliable | Not fused; no SKU-to-barcode inference |

## OCR, normalization, and privacy

The environment audit found no Tesseract executable and no `pytesseract`,
EasyOCR, or PaddleOCR package. B-05 provides an offline optional Tesseract
adapter configured for `vie+eng`, plus a no-op adapter. It returns
`OCR_UNAVAILABLE`/`OCR_NOT_CONFIGURED` rather than inventing text. OCR is
**PARTIAL**: the adapter and deterministic fixture coverage pass, but Vietnamese
package accuracy is not demonstrated.

Raw OCR text is transient inside the service. The result exposes bounded,
structured observations only. Normalization uses Unicode NFKC, casefolding,
whitespace/punctuation cleanup, and a diacritic-aware comparison form while
preserving `500 mg`, `250mg`, `10 ml`, `5%`, `XR`, `SR`, and `CR`.

## Quality gate and recognition decision

The deterministic gate emits `PASS`, `RETAKE_RECOMMENDED`, or `REJECT` with
explicit unreadable, too-small, extreme-aspect, too-dark, too-bright, and
too-blurry reasons. It is not a drug-confidence score. `REJECT` stops retrieval.
`RETAKE_RECOMMENDED` may retain candidates for inspection but forces
`INSUFFICIENT_EVIDENCE`, so it can never yield high evidence.

Reranking is explicitly a baseline heuristic, not a learned confidence model:
visual score + name corroboration (0.20) + strength (0.08) + ingredient (0.12),
with a -1.0 hard-conflict penalty. These are labeled
`deterministic-baseline-heuristic-v1`, not calibrated clinical thresholds.
Components, conflicts, visual rank, and fused score remain inspectable.

`NAME_CONFLICT` and `STRENGTH_CONFLICT` cannot be overridden by visual
similarity. Registration/manufacturer conflicts are not fabricated because the
catalog fields are absent. `HIGH_EVIDENCE_MATCH` requires visual Top-1, visible
product-name corroboration, no hard conflict, and no duplicate-content ambiguity.
There is no cosine confidence threshold. Every outcome requires user
confirmation wording.

`Top-1 candidate` is not an identified drug; `HIGH_EVIDENCE_MATCH` is not a
confirmed drug; confirmation is an explicit future user action.

## Evaluation dataset, gallery, and realistic-query limits

`data/drug-images/eval/drug_recognition_v1.jsonl` is a versioned,
metadata-only safety/evaluation manifest. It records controlled B-04-derived
queries and blank/non-catalog-text fixtures with expected products, quality,
ambiguity, and unknown flags. It contains no patient images, OCR payloads, or
image binaries.

The B-02 audit found only validated `primary.webp` front views in retained local
collection (`view_type: front`). No independently validated gallery set remains
to sample safely. Thus `GALLERY_PRODUCTS_SAMPLED=0`,
`VALID_PRODUCT_VIEWS=0`, `DUPLICATES=0`, `NON_PRODUCT_IMAGES=0`, `INVALID=0`;
multi-view is **DEFERRED** and B-05 did not crawl or bulk-ingest gallery URLs.

There are no independent phone photos. Controlled transforms prove pipeline
compatibility only, not camera performance, glare, occlusion, side angle, damaged
packaging, clutter, or visual look-alike discrimination.

## Local E2E pilot and metrics

The read-only pilot used persisted 3,543 B-04 embeddings/storage, without
re-embedding or DB writes. Eight B-04 controlled queries (crop, brightness,
rotation, JPEG resize, blur, duplicate cases) ran quality → OpenCLIP → exact
search → no-op OCR → normalization → rerank → result on local Windows CPU.

| Metric | Visual-only | Multi-signal |
| --- | ---: | ---: |
| Top-1 | 1.000 | 1.000 |
| Recall@3 | 1.000 | 1.000 |
| Recall@5 | 1.000 | 1.000 |
| MRR | 1.000 | 1.000 |

OCR was unavailable, so this is an ablation: visual-only and multi-signal are
identical and do not prove text-fusion improvement. Outcomes were five
`AMBIGUOUS_MATCH` and three `INSUFFICIENT_EVIDENCE`; none was high evidence.

- False confident identification rate: `0.0` (0 high-evidence results).
- High-evidence precision: `N/A` (no high-evidence results).
- Ambiguous rate: `0.625`; insufficient-evidence rate: `0.375`.
- End-to-end latency: P50 `620.5 ms`, P95 `1232.6 ms` on local CPU and
  Docker/Postgres; not a production SLA.
- Generative-model calls: `0`.

Blank and non-catalog-text fixtures exercise low-evidence routing to
`INSUFFICIENT_EVIDENCE`. Unknown evaluation is **PARTIAL**: blank is
reject/retake-routed and unmatched text is insufficient, but no independent
unknown-image distribution exists. No unknown-rejection percentage is claimed.

## Failure coverage and tests

Targeted local result: **21 passed**; Ruff lint and format pass. Coverage
includes quality reasons, normalization/strength parsing, product and ingredient
matching, B-04 candidate generation/product deduplication, deterministic output
and versioning, duplicate ambiguity, hard visual/text conflict, unknown text,
no OCR text, no forced Top-1, high-evidence corroboration, no medical facts, and
no query persistence. The E2E pilot additionally covers controlled crop/blur.

## B-06, B-07, and B-08 boundaries

- B-06: **PARTIAL**. A future confirmed `drug_product_id` can consume existing
  primary `DrugImage`; no reminder work was added.
- B-07: **NO** integration. A safe internal result/confirmation contract exists,
  but there is no chatbot upload, persistence, route, button, or auto Drug Tool.
- B-08 requirements: independent approved phone photos; reproducible Vietnamese
  + Latin OCR benchmark; held-out calibration; real unknown set; validated
  gallery/multi-view protocol; safety review of false-confident rate.

## Release gate

| Gate | Result |
| --- | --- |
| B-05 / B-04 merged / Track A untouched | PASS / PASS / PASS |
| Quality / normalization / visual retrieval / reranking | PASS / PASS / PASS / PASS |
| OCR / structured extraction | PARTIAL / PARTIAL |
| Hard conflicts / duplicate ambiguity / no forced Top-1 | PASS / PASS / PASS |
| High needs corroboration / confirmation required | PASS / PASS |
| Unknown / phone-photo / multi-view | PARTIAL / NOT_AVAILABLE / DEFERRED |
| Medical facts / patient persistence / generative calls | NONE / NONE / 0 |
| Chatbot / reminder UI / production deploy | NONE / NONE / NONE |
| Local E2E / ready for PR | PASS / YES |

Production drug recognition remains **not approved** by B-05 completion.
