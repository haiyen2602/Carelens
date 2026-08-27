# B-08 Production Recognition Re-validation Report

**Date:** 2026-08-27  
**Decision:** `PRODUCTION RECOGNITION = NOT_APPROVED`  
**Feature flag:** `FALSE` (Railway variable is unset; source default is `false`)

## 1. Baseline

| Item | Observation |
| --- | --- |
| `MAIN_COMMIT` | `cba7511ee603587643a420b748146a8739fa5765` (`Merge pull request #150`) |
| BE deployment | `ab4bf37d-82ca-4ba3-bbcf-bdf6d82b15c8`, online, Railway production, SFO |
| Recognition flag | `DRUG_IMAGE_CHAT_RECOGNITION_ENABLED=<UNSET>`; source default is `false` |
| Current endpoint | The task reports authenticated production requests return HTTP 200 / `RECOGNITION_UNAVAILABLE`; no safe authenticated token was available for an independent repeat. |
| Catalog count | Task reports 3,543 validated production artifacts. Direct DB counting from this workstation is unavailable because Railway exposes `postgres.railway.internal` only inside its private network. |

Railway status currently exposes one BE persistent volume at
`/app/data/photo_verifications`; it does not independently show a catalog-media
mount. Catalog binary persistence and embedding count remain unverified here.

## 2. Runtime audit

The B-05/B-07 stack is unchanged: EXIF-normalized RGB quality gate; OpenCLIP
ViT-B/32 (`laion2b_s34b_b79k`, package `2.26.1`); deterministic center-crop
224 preprocessing; normalized 512-dimensional embeddings; exact cosine search
over validated product-distinct catalog vectors (`top_k=10`); optional
Tesseract `vie+eng` OCR corroboration; and deterministic reranking.

HIGH evidence requires visual rank 1, independent product-name text
corroboration, no conflict, and no duplicate-reference ambiguity. Quality
failure/conflict/no candidate is insufficient; other candidates are ambiguous.
All candidate presentation remains bounded to three and requires confirmation.

## 3. Production dependency plan

`requirements-drug-image-vision.txt` pins CPU-only `torch==2.5.1+cpu`,
`torchvision==0.20.1+cpu`, and `open_clip_torch==2.26.1`; they are absent from
production `requirements.txt`. The local environment has no `open_clip`,
`torch`, or `pytesseract`. There is no approved plan for model-weight cache,
disk footprint, OCR binary/language packs, CPU-memory reservation, or cold
start. The safe plan is no runtime change and lazy construction behind the
false flag.

## 4. Resource benchmark

No deployment-equivalent vision runtime exists and none was installed. Model
cold/warm load, memory, preprocessing/embedding/retrieval/OCR/rerank latency,
p50, p95, peak memory and concurrency (1/2/4) are all:
`NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE`.

## 5. Evaluation dataset

| Artifact | Cases | Qualification |
| --- | ---: | --- |
| `visual_retrieval_v1.jsonl` | 256 | Synthetic transforms of catalog references; not independent or real-phone |
| `drug_recognition_v1.jsonl` | 10 | Controlled synthetic references/unknown fixtures; not real-world unknown evidence |
| Approved `REAL_PHONE` cases | 0 | Not available |

## 6. Dataset provenance

No consent/provenance record, independent curator, canonical real-photo truth,
approved calibration split, held-out final-test split, hard-negative/lookalike
set, or Vietnamese OCR transcription benchmark exists. Synthetic fixtures are
regression-only and are not used for thresholds or production claims.

## 7. Retrieval metrics

Top-1, Top-3, Top-5 and MRR on an approved real-phone held-out set are:
`NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE`.

## 8. Unknown and hard-negative metrics

False-confident identification, unknown rejection, wrong-strength
high-evidence error, duplicate/near-duplicate and hard-negative performance:
`NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE`.

## 9. Lookalike analysis

No approved same-brand, similar-packaging, formulation or wrong-strength cohort
is available. `LOOKALIKE CONFUSION: NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE`.

## 10. OCR evaluation

OCR is corroborating only and cannot establish canonical identity. There is no
approved Vietnamese OCR benchmark or deployment-ready Tesseract/language-pack
verification. `OCR: NOT_READY`; all OCR quality metrics are
`NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE`.

## 11. Threshold analysis

No threshold was changed or tuned. The deterministic rule is fail-closed for
weak/conflicting evidence, but real-photo HIGH evidence precision and coverage
are `NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE`.

## 12. B-07 safety invariants

`28` targeted B-04/B-05/B-07 tests pass and changed paths pass Ruff. They
confirm validation before enabled-path recognition; safety/dose-safety before
runtime; doctor takeover before recognition; no active entity before explicit
opaque-action confirmation; and rejection of forged, cross-patient, expired,
superseded and invalid replay confirmation. Responses omit raw image, OCR text,
query embeddings and storage paths. Disabled recognition constructs no runtime
and creates no attempt.

## 13. End-to-end test

No enabled staging/deployment-equivalent runtime and no approved real-phone
data exist. Known, lookalike, unknown, non-drug, camera and canary E2E cases
are `NOT_RUN`. Normal text chat is unchanged.

## 14. Failure injection

Local tests cover corrupt/oversized upload validation, optional OCR
unavailability, quality rejection, disabled mode, safety/takeover precedence,
and injected model-load failure. The latter returns HTTP 503 and releases the
semaphore. Runtime timeout/load, storage, retrieval, malformed output and DB
persistence failures in deployment-equivalent conditions are
`NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE`.

## 15. Cost, latency and capacity

Railway resource-tier impact, package/weight disk cost, cold-start impact,
safe requests-per-minute and p50/p95 are
`NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE`. No new cost was introduced.

## 16. Approval decision

`PRODUCTION RECOGNITION = NOT_APPROVED`

Blockers: approved independent real-phone data; unknown and lookalike
evaluation; false-confident measurement; Vietnamese OCR evidence;
deployment-equivalent runtime/model-weight/storage verification; and measured
memory, latency, concurrency and failure behavior.

## 17. Production enablement

Not performed. No vision dependency, model weight, OCR runtime, configuration
setting or deployment was changed. The flag remains effectively `false`.

## 18. Production canary

`NOT_RUN`. A canary is prohibited until the approval decision changes.

## 19. Rollback

The one-step safe rollback is `DRUG_IMAGE_CHAT_RECOGNITION_ENABLED=false`.
The current unset variable already resolves to this state and returns
`RECOGNITION_UNAVAILABLE`.

## 20. Final gate

| Gate | Result |
| --- | --- |
| UPLOAD PIPELINE | `PASS` (task-reported production unavailable state; B-07 regression pass) |
| REAL PHONE DATASET | `FAIL` |
| KNOWN PRODUCT SAMPLES | `0 approved real-phone` |
| LOOKALIKE SAMPLES | `0 approved` |
| UNKNOWN/NON-DRUG SAMPLES | `0 approved independent` |
| TOP-1 / TOP-3 / TOP-5 | `NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE` |
| HIGH_EVIDENCE PRECISION / COVERAGE | `NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE` |
| FALSE CONFIDENT / UNKNOWN REJECTION / LOOKALIKE CONFUSION | `NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE` |
| OCR | `NOT_READY` |
| MODEL COLD LOAD / P50 / P95 / PEAK MEMORY | `NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE` |
| CONCURRENCY | `FAIL — not measured on deployment-equivalent runtime` |
| SAFETY PRECEDENCE / DOCTOR TAKEOVER | `PASS` |
| UNCONFIRMED CANDIDATE != ACTIVE_ENTITY / EXPLICIT CONFIRMATION | `PASS` |
| FAILURE INJECTION | `PARTIAL PASS — local only` |
| NORMAL TEXT CHAT REGRESSION | `PASS — unchanged path` |
| GENERIC 500 | `NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE` in production canary; local model-load failure maps to 503 |
| PRODUCTION RECOGNITION | `NOT_APPROVED` |
| FEATURE FLAG | `FALSE` |
| PRODUCTION CANARY | `NOT_RUN` |
| READY FOR PATIENT IMAGE RECOGNITION | `NO` |

No synthetic result is presented as production evidence. Re-open B-08 only
when the required approved data and deployment-equivalent evidence exist.
