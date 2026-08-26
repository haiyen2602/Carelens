# DRUG IMAGE B-04 — VISUAL RETRIEVAL BASELINE REPORT

**Status:** PASS — local-only visual candidate retrieval baseline.
**Date:** 2026-08-26
**Scope:** Reference/synthetic images only. This is not production recognition, a confidence gate, patient upload flow, chatbot integration, or deployment.

## 1. Executive Summary

B-04 implements the bounded pipeline:

```text
reference/query image → OpenCLIP embedding → L2 normalization → exact cosine search → Top-K product candidates
```

It persists a versioned `DrugImageEmbedding` beside the B-03 `DrugImage` provenance model and returns ranked **candidates only**. It never identifies a drug automatically, applies a score threshold, rejects an unknown drug, or changes product ownership.

The local full run embedded **3,543 / 3,543** validated references with zero failures. A second run resumed all 3,543 and created no duplicates. Controlled synthetic queries achieved perfect retrieval on this limited web-reference evaluation; that result must not be represented as phone-photo or patient-drug recognition accuracy.

## 2. Parallel Workstream Safety and Baseline

| Check | Result | Evidence |
|---|---|---|
| B-04 branch/worktree | PASS | `feature/drug-image-b04-visual-retrieval`, `H:/Vin AI/P-067-drug-image-b04` |
| Baseline | PASS | `832f9c66f3d867730df6b34c7001fcf994153d9e` — PR #129/B-03 merged |
| B-03 fix reachable | PASS | `7f42e93` reachable from baseline |
| Alembic before B-04 | PASS | single head `0052` |
| Refreshed parallel audit | PASS | later `origin/main` BUILD-43 commits contain no migration, `DrugImage`, or vector-index change |
| Track A | PASS | not modified |
| Production/runtime isolation | PASS | no deploy, chatbot, public endpoint, patient upload, or runtime model call |

## 3. Existing Vector Infrastructure Audit

The repository already standardizes on PostgreSQL + pgvector (ADR-0008); local Docker uses `pgvector/pgvector:pg16`. Validation confirmed extension `vector` version `0.8.6`. Text RAG uses `text-embedding-3-small` and its own `DrugChunk`/RAG lifecycle, which is not suitable for images and was left untouched.

No second vector store was added. B-04 adds only a dedicated visual embedding table and uses exact cosine ranking. At 3,543 rows the measured exact-search P95 was acceptable, so no HNSW or IVFFlat index was created (`ann_indexes=0`).

## 4. Model Candidate Audit and Selection

| Candidate | Audit outcome |
|---|---|
| OpenCLIP ViT-B/32, LAION-2B checkpoint | **Selected.** Purpose-built image embedding, 512 dimensions, batchable, deterministic preprocessing, locally cacheable, and practical on the available CPU. |
| OpenCLIP ViT-B/16 | Considered but not run as a second full experiment: it increases patch-level compute on the CPU-only validation environment without an approved quality corpus to justify that cost. |
| SigLIP-family | Considered but not selected: no existing repository/runtime dependency or local checkpoint; adding a second large framework/model would not improve the evidence quality of the same synthetic-only query set. |
| Generative multimodal LLM | Rejected: not an embedding encoder and outside B-04 scope. |

Selected identity:

```text
embedding_model: open_clip/ViT-B-32
embedding_version: open_clip_torch-2.26.1:laion2b_s34b_b79k
embedding_dimension: 512
device: CPU
batch_size: 16
```

The dependency pins live in `requirements-drug-image-vision.txt`, separate from production `requirements.txt`. This prevents the API/chatbot runtime from acquiring vision inference dependencies. A second full model comparison is deferred until an independently collected phone-photo/golden corpus exists.

## 5. Preprocessing and Persistence Contract

`openclip-rgb-exif-transpose-center-crop-224-v1` is persisted with every embedding. The encoder applies EXIF orientation normalization, RGB conversion, OpenCLIP-required resize/center crop/normalization, then L2 normalization. B-04 does not OCR, remove backgrounds, heuristically crop packages, or generatively enhance reference or query images.

Migration `0053_drug_image_embeddings` is additive and reversible. `DrugImageEmbedding` has:

- a non-null FK to `DrugImage`;
- model/version/dimension/preprocessing version and creation time;
- `Vector(512)` embedding plus a check that the persisted dimension is 512;
- unique `(drug_image_id, embedding_model, embedding_version)` identity.

Migration validation on an isolated local database passed `0052 → 0053 → 0052 → 0053`.

## 6. Full Embedding Run and Idempotency

The B-03 importer first reproduced the validated reference corpus in an isolated database/storage directory:

```json
{"TOTAL_MANIFEST":3545,"VALIDATED_INPUT":3543,"INVALID_INPUT":2,
 "PRODUCT_NOT_FOUND":0,"IMAGE_FILE_MISSING":0,"CHECKSUM_MISMATCH":0,
 "WOULD_SKIP":3543,"FAILED":0}
```

The first B-04 encoder run took **4m48s** wall clock, or approximately **81.3 ms/reference** including model setup and database batches:

```json
{"TOTAL":3543,"EMBEDDED":3543,"RESUMED":0,"FAILED":0,"SKIPPED":0}
```

The rerun proved resumability/idempotency:

```json
{"TOTAL":3543,"EMBEDDED":0,"RESUMED":3543,"FAILED":0,"SKIPPED":0}
```

Each successful batch commits before the next batch. Decoder/model failures are retried singly and emitted to an explicit JSONL failure queue; no failed row existed in this run.

## 7. Evaluation Dataset and Results

`data/drug-images/eval/visual_retrieval_v1.jsonl` is a committed, metadata-only artifact with 256 deterministic cases, including one representative from each of the three duplicate-content ambiguity groups. It stores query ID, reference image ID, expected product set, transformation type, seed, and ambiguity status; it stores no duplicate query binary.

Synthetic transforms are deterministic JPEG resize/compression, brightness shift, small rotation, crop-with-padding, and mild blur. The query bytes are not the indexed reference bytes.

| Mode | Queries | Top-1 | Recall@3 | Recall@5 | Recall@10 | MRR | P50 | P95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SELF_RETRIEVAL (sanity only) | 256 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 79.5 ms | 106.4 ms |
| SYNTHETIC_QUERY (controlled web transforms) | 256 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 79.8 ms | 181.7 ms |

The self result is index/pipeline consistency only. The synthetic result is explicitly `SYNTHETIC_QUERY_EVALUATION`; it is not evidence of real camera, occlusion, glare, damaged packaging, or patient-photo performance.

## 8. Duplicate Ambiguity, Unknowns, and Multi-view

The complete corpus contains **3 duplicate-content checksum groups spanning 10 products**. Evaluation records use an acceptable product set for those groups (`AMBIGUOUS_REFERENCE`), so an identical image mapped to another valid owner is not arbitrarily scored wrong. Search results retain ownership and deduplicate the outward candidate list by `drug_product_id` for future multi-view support.

- `UNKNOWN_REJECTION: NOT_AVAILABLE` — nearest-neighbor search always returns something; there is no unknown-drug corpus or calibrated threshold.
- `MULTI_VIEW_REFERENCE: NOT_AVAILABLE / DEFERRED` — B-02 validated primary views only. No gallery crawl was started.
- `NO_CONFIDENCE_THRESHOLD: PASS` — raw similarity is returned only; no HIGH/MEDIUM/LOW band exists.

## 9. Tests and Known Limitations

Targeted service tests cover deterministic 512-dimensional persistence, model/version/preprocessing persistence, idempotent resume, corrupt/missing reference failure isolation, Top-K exact correctness, product-level deduplication, duplicate ambiguity scoring, and deterministic non-identical synthetic transforms. Targeted suite: **13 passed**. Ruff and `git diff --check` passed.

Known limitations:

- no patient-photo, unknown-drug, or independently photographed golden set;
- no calibrated confidence, rejection, OCR, text fusion, barcode, manufacturer, or reranking;
- only one model ran full corpus; a fair model comparison needs the same future realistic corpus;
- retrieval remains an internal offline service with no API/UI/chatbot integration.

## 10. Release Gate

| Gate | Result |
|---|---|
| DRUG IMAGE B-04 | PASS |
| PARALLEL WORKTREE / TRACK A ISOLATION | PASS |
| B-03 MERGED BASELINE | PASS |
| MODEL / PREPROCESSING VERSIONED | PASS |
| REFERENCE IMAGES / EMBEDDINGS | `3543 / 3543` |
| EMBEDDING IDEMPOTENCY | PASS |
| EXACT VECTOR SEARCH / TOP-K PRODUCT RETRIEVAL | PASS |
| DUPLICATE / AMBIGUITY HANDLING | PASS |
| UNKNOWN REJECTION | NOT_AVAILABLE |
| MULTI-VIEW | NOT_AVAILABLE / DEFERRED |
| NO CONFIDENCE / OCR / RERANKING | PASS |
| NO CHATBOT / UI / PRODUCTION DEPLOY | PASS |
| B-05 READY | PARTIAL — realistic query corpus and unknown policy are required |
| READY FOR PR | YES |

**Stop condition:** B-04 ends here. Do not merge/deploy, start B-05, add a confidence gate, or integrate retrieval into the chatbot from this task.
