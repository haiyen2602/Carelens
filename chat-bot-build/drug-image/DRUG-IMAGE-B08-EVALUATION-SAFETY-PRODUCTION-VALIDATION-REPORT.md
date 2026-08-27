# B-08 — Evaluation, Safety, and Production Validation Audit

**Date:** 2026-08-27  
**Task:** B-08 — Evaluation, Safety, and Production Validation  
**Audit scope:** Track B drug-image recognition only  
**Decision:** `PRODUCTION RECOGNITION: NOT_APPROVED`

## 1. Executive Summary

B-08 is complete as an evidence audit. It is not a production-quality
validation pass. The repository contains useful implementation and synthetic
baseline evidence, and the merged B-07 baseline has evidence for the specified
safety boundaries. It does not contain an approved, independent real-phone
photo evaluation dataset or access to a deployment-equivalent environment.

Consequently, no production accuracy, false-accept, OCR accuracy, latency,
memory, or concurrency result is reported here. B-04/B-05 synthetic and
self-derived results are deliberately not extrapolated into production claims.
No calibration was run, no threshold was created, no recognition architecture
was changed, and no production feature was enabled or deployed.

**B-08: PASS AS AUDIT / FAIL AS PRODUCTION VALIDATION.**

## 2. Baseline / Version Freeze

| Item | Frozen evidence |
| --- | --- |
| Audit branch baseline | `origin/main` `bdf0eb3f96ab97dca915e0859991b320db82fe47` — Merge PR #141 |
| B-07 merged baseline | `e1a2bdda744d70f3ef1bc7b565b00f5d8b1acf62` — B-07 is an ancestor of the audit baseline |
| B-04 merged baseline | `fa581ca` (PR #132) |
| B-05 merged baseline | `3c27d6f` (PR #133) |
| Schema head observed | Alembic `0055 (head)`; no migration was created or changed by B-08 |
| Retrieval model declaration | `open_clip/ViT-B-32`, pretrained `laion2b_s34b_b79k` |
| Retrieval package declaration | `open_clip_torch==2.26.1`; isolated vision requirements pin CPU Torch `2.5.1+cpu` and torchvision `0.20.1+cpu` |
| Embedding contract | dimension `512`; version `open_clip_torch-2.26.1:laion2b_s34b_b79k`; preprocessing `openclip-rgb-exif-transpose-center-crop-224-v1` |
| Recognition policy declaration | `deterministic-baseline-heuristic-v1`; not a calibrated production threshold policy |
| OCR declaration | optional Tesseract, default languages `vie+eng`; actual production availability is not verified |

This is a source and repository freeze, not proof that the same model,
checkpoint, image catalog, embeddings, OCR executable, storage, or hardware is
present in a production-equivalent deployment.

## 3. Existing Dataset Inventory

The committed evaluation inventory was enumerated from `data/drug-images/eval`.
There are two JSONL manifests and no committed approved real-phone-photo,
hard-negative/lookalike, or OCR-ground-truth evaluation artifact.

| Artifact | Records | Classification | What it is | Production qualification |
| --- | ---: | --- | --- | --- |
| `visual_retrieval_v1.jsonl` | 256 | `SYNTHETIC` | Deterministic transformed queries derived from collection/reference images | Not independent; not real-phone evidence |
| `drug_recognition_v1.jsonl` | 8 | `SYNTHETIC` | `CONTROLLED_SYNTHETIC_REFERENCE` records | Not independent; not real-phone evidence |
| `drug_recognition_v1.jsonl` | 2 | `UNKNOWN_SYNTHETIC` | `SYNTHETIC_UNKNOWN` records | Too small and synthetic; insufficient unknown evidence |
| Committed real-phone evaluation cases | 0 | `REAL_PHONE` | No approved artifact found | Not available |
| Committed self-match evaluation cases | 0 distinct cases | `SELF_MATCH` | B-04 reports self-retrieval execution against the same reference corpus, not a separate independent dataset | Not qualifying |

For avoidance of doubt, B-04's 256 transformed-query runs include
self-derived/reference-corpus behavior. They are useful engineering regression
fixtures, but are not counted as a distinct or independent `SELF_MATCH`
production test set.

## 4. Dataset Provenance Audit

The available manifests establish deterministic fixture inputs and labels, but
do not establish the provenance required for a production evaluation claim:

- no approved data owner, consent/privacy basis, collection protocol, or
  independent curator is recorded for real user phone photos;
- no documented split between approved calibration and held-out final test
  sets;
- no independent unknown/out-of-catalog collection with source and truth
  labels;
- no hard-negative/lookalike set covering packaging similarity, formulation,
  strength, manufacturer, and Vietnamese labeling confusions; and
- no approved Vietnamese OCR benchmark with transcription ground truth.

Synthetic augmentation is not a substitute for any of these missing sources.

## 5. Dataset Qualification Result

| Required evaluation asset | Result |
| --- | --- |
| Independent real-phone-photo in-catalog set | `NOT_AVAILABLE` |
| Approved calibration set | `NOT_AVAILABLE` |
| Approved final held-out test set | `NOT_AVAILABLE` |
| Unknown / out-of-catalog set | `INSUFFICIENT` |
| Hard-negative / lookalike set | `NOT_AVAILABLE` |
| Vietnamese OCR benchmark | `NOT_AVAILABLE` |
| Dataset provenance / approval | `INSUFFICIENT` |

No calibration or threshold selection was performed. The existing
synthetic/self-derived data must not be repurposed as calibration evidence or
as a substitute for real-phone-photo evaluation.

## 6. Missing Evaluation Evidence

Production validation is blocked by the absence of all of the following:

1. An approved independent real-phone-photo dataset with canonical product,
   strength, formulation, and capture-condition truth labels.
2. A documented, reproducible separation of calibration data from a final,
   independently held-out test set.
3. An approved unknown/out-of-catalog test set representative of expected
   non-matches and confusing consumer uploads.
4. An approved hard-negative/lookalike benchmark, including same-name,
   same-brand/different-strength, similar packaging, and near-identical
   Vietnamese-label cases.
5. A Vietnamese OCR benchmark with approved ground-truth transcriptions and
   capture-condition metadata.
6. A pre-specified evaluation protocol, acceptance criteria, and ownership
   approval for the resulting metrics.

## 7. Deployment-Equivalent Environment Audit

No deployment-equivalent environment, deployment credentials, production
catalog snapshot, or operational telemetry was available to this audit. The
following items are therefore not verified:

| Environment item | Result |
| --- | --- |
| Deployment-equivalent environment | `NOT_AVAILABLE` |
| Production model/checkpoint runtime | `NOT_VERIFIED` |
| Production catalog / embedding readiness | `NOT_VERIFIED` |
| Production OCR | `NOT_VERIFIED` |
| Production storage persistence | `NOT_VERIFIED` |
| CPU/GPU memory behavior | Required evidence unavailable |
| End-to-end recognition latency | Required evidence unavailable |
| Concurrency and timeout behavior | Required evidence unavailable |

The code's local declarations and checked-in storage/cleanup paths do not
prove mounted-volume persistence, scheduler operation, model availability, or
resource limits in a production deployment.

## 8. Existing B-04/B-05 Evidence and Why It Is Insufficient for Production Claims

B-04 provides a deterministic visual-retrieval baseline over 3,543 validated
reference embeddings and 256 synthetic transformed queries. B-05 provides a
deterministic multi-signal reranking baseline over 8 controlled synthetic
reference cases and 2 synthetic unknown cases, with optional OCR behavior.
These are useful for implementation regression and for documenting the
baseline, but are not independent production evaluation data.

In particular:

- B-04 transformations originate from the reference corpus and do not model
  independently collected phone photographs.
- B-05's controlled/synthetic fixtures do not establish generalization to real
  packaging, lighting, blur, reflections, occlusion, or user capture behavior.
- the B-05 policy is explicitly heuristic and uncalibrated; it has no approved
  confidence threshold.
- B-05 recorded optional OCR availability in its local environment, not an
  approved Vietnamese OCR accuracy benchmark or production OCR verification.
- neither artifact provides an approved, independent unknown or lookalike
  benchmark.

Accordingly, no B-04 or B-05 result is used here to state production accuracy,
false-confident rate, unknown rejection rate, OCR accuracy, latency, or any
other production performance claim.

## 9. B-07 Safety Invariant Verification

The B-07 baseline is merged. The following findings are based on its merged
code paths and existing B-07 test evidence, not on a production invocation.

| Invariant | Evidence reviewed | Result |
| --- | --- | --- |
| Unconfirmed candidate is not an active entity | `DrugRecognitionAttempt` holds the recognition snapshot. Only the confirmation path creates/binds the canonical active entity; confirmation is scoped to actor, patient, conversation, candidate, and expiry. | `UNCONFIRMED → ACTIVE_ENTITY: NO — VERIFIED FROM B-07` |
| Drug Tool only after confirmation | The confirmation route invokes the Drug Tool only after successful `confirm_attempt` and active-entity binding. Recognition alone returns a candidate/attempt, not a medication action. | `DRUG TOOL BEFORE CONFIRM: NONE — VERIFIED FROM B-07` |
| Safety precedence | Acute, possible-overdose, medication-dose, and missed/delayed safety intents are handled before image recognition/tool progression. | `SAFETY PRECEDENCE: PASS — EXISTING B-07 EVIDENCE` |
| Dose safety | The canonical dose-safety paths remain ahead of medication information flow and use canonical knowledge after confirmation. | `DOSE SAFETY: PASS — EXISTING B-07 EVIDENCE` |
| Doctor takeover suppression | An active doctor takeover takes the private delivery path before B-05/OCR/model invocation. | `DOCTOR TAKEOVER MODEL CALLS: 0 — EXISTING B-07 EVIDENCE` and `DOCTOR TAKEOVER RECOGNITION CALLS: 0 — EXISTING B-07 EVIDENCE` |

### Current local regression evidence

- Targeted B-07/backend regression: **68 passed**. One HTTP dose-safety test
  could not complete its fixture setup because local PostgreSQL at
  `localhost:5432` refused the connection; this was an environment prerequisite
  failure, not a failed assertion. It does not create production evidence.
- Ruff over the B-07 safety, recognition, retrieval, scheduler, and associated
  test modules: **passed**.
- Frontend `npm run build`: **passed** locally.
- Full frontend `npm run lint`: blocked by pre-existing CRLF versus Prettier-LF
  configuration across the Windows checkout (`32,377` CRLF errors). B-08 did
  not modify frontend source or normalize unrelated files; this baseline lint
  condition is not represented as a B-08 code regression.

## 10. Privacy / Retention Review

The reviewed B-07 design separates normal recognition uploads from doctor
takeover attachments:

- normal recognition uses a bounded upload and a temporary path with cleanup
  in the request lifecycle; recognition attempts store audit metadata rather
  than raw image bytes, OCR text, or embedding vectors;
- active doctor takeover bypasses recognition and persists an explicitly
  private attachment tied to the handoff/review message;
- the B-07 post-review baseline uses uniquely created temporary files, promotes
  them atomically, and avoids unlinking the temporary name after promotion;
- private attachments have an expiry and a scheduled cleanup path, with
  request-failure cleanup for promoted files where the database transaction
  fails.

This is code and test evidence for the policy boundary. It is not verification
that a production filesystem is persistent, that a deployed scheduler runs, or
that crash-orphan cleanup and access controls have been exercised in a
deployment-equivalent environment.

## 11. Metrics That Could Not Validly Be Measured

| Required production metric | Result |
| --- | --- |
| Top-1 production accuracy | `NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE` |
| False-confident identification | `NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE` |
| Unknown high-evidence false accept | `NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE` |
| Wrong-strength high-evidence identification | `NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE` |
| Unknown rejection production rate | `NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE` |
| OCR accuracy | `NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE` |
| Model memory | `NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE` |
| End-to-end latency (including P50/P95) | `NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE` |
| Concurrency / timeout behavior | `NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE` |

No zero values, surrogate synthetic values, or `N/A` labels are used for these
required-but-blocked metrics.

## 12. Required Evidence for Future Re-evaluation

Production approval may be reconsidered only after all of the following are
available and approved:

1. Independent, consented real-phone-photo evaluation data with an auditable
   provenance record and canonical product/strength/formulation labels.
2. Independently held-out calibration and final-test splits, fixed before
   tuning, with an approved evaluation protocol and acceptance criteria.
3. Representative independent unknown/out-of-catalog and hard-negative/
   lookalike cohorts, including wrong-strength and close-package cases.
4. A Vietnamese OCR benchmark with approved transcription truth and defined
   scoring.
5. A deployment-equivalent environment containing the proposed model/checkpoint,
   catalog images and embeddings, OCR runtime, persistent storage, scheduled
   cleanup, production-like CPU/GPU, and configured timeouts/concurrency.
6. Reproducible measurements in that environment for the required quality,
   unknown-safety, wrong-strength, OCR, memory, latency, concurrency, timeout,
   persistence, and failure-recovery behaviors.
7. Human approval of the evidence and, only after that approval, an authorized
   canary plan with monitoring and rollback. No canary was run in B-08.

## 13. Production Approval Decision

`PRODUCTION RECOGNITION: NOT_APPROVED`

**Reason:** `INSUFFICIENT INDEPENDENT QUALITY EVIDENCE` and
`DEPLOYMENT-EQUIVALENT ENVIRONMENT UNAVAILABLE`.

This decision does not assert that the implementation is unsafe or inaccurate;
it states that the required independent evidence to make a production claim is
absent. Recognition remains disabled for production. B-08 made no deployment,
no production enablement, no runtime/schema change, and no Track A change.

## 14. Release Gate

| Gate | Result |
| --- | --- |
| B-08 | `PASS AS AUDIT / FAIL AS PRODUCTION VALIDATION` |
| B-07 merged baseline | `PASS` |
| REAL PHONE PHOTO DATASET | `NOT_AVAILABLE` |
| APPROVED CALIBRATION SET | `NOT_AVAILABLE` |
| APPROVED FINAL TEST SET | `NOT_AVAILABLE` |
| UNKNOWN / OUT-OF-CATALOG SET | `INSUFFICIENT` |
| HARD NEGATIVE / LOOKALIKE SET | `NOT_AVAILABLE` |
| OCR BENCHMARK | `NOT_AVAILABLE` |
| DATASET PROVENANCE / APPROVAL | `INSUFFICIENT` |
| DEPLOYMENT-EQUIVALENT ENVIRONMENT | `NOT_AVAILABLE` |
| PRODUCTION CATALOG / EMBEDDING READINESS | `NOT_VERIFIED` |
| PRODUCTION OCR | `NOT_VERIFIED` |
| PRODUCTION STORAGE PERSISTENCE | `NOT_VERIFIED` |
| MODEL MEMORY | `NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE` |
| END-TO-END LATENCY | `NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE` |
| CONCURRENCY | `NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE` |
| FALSE CONFIDENT IDENTIFICATION | `NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE` |
| UNKNOWN HIGH_EVIDENCE FALSE ACCEPT | `NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE` |
| WRONG-STRENGTH HIGH_EVIDENCE | `NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE` |
| OCR ACCURACY | `NOT_MEASURED — REQUIRED EVIDENCE UNAVAILABLE` |
| UNCONFIRMED → ACTIVE_ENTITY | `NO — VERIFIED FROM B-07` |
| DRUG TOOL BEFORE CONFIRM | `NONE — VERIFIED FROM B-07` |
| SAFETY PRECEDENCE | `PASS — EXISTING B-07 EVIDENCE` |
| DOSE SAFETY | `PASS — EXISTING B-07 EVIDENCE` |
| DOCTOR TAKEOVER MODEL CALLS | `0 — EXISTING B-07 EVIDENCE` |
| DOCTOR TAKEOVER RECOGNITION CALLS | `0 — EXISTING B-07 EVIDENCE` |
| PRODUCTION CANARY | `NOT_RUN` |
| PRODUCTION RECOGNITION | `NOT_APPROVED` |
| READY TO ENABLE PRODUCTION | `NO` |
| READY TO CLOSE TRACK B AS PRODUCTION-READY | `NO` |
| READY TO CLOSE CURRENT B-08 AUDIT TASK | `YES` |
| FOLLOW-UP REQUIRED | `YES — obtain approved independent evaluation dataset and deployment-equivalent environment, then rerun B-08 validation.` |

**Final release decision:** do not merge this audit as a production-enablement
change, do not deploy, and do not enable recognition. Re-open B-08 only when
the listed evidence is available for an independent rerun.
