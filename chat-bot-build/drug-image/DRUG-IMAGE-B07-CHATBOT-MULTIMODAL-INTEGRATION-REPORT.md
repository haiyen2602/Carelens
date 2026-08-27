# Drug Image B-07 — Chatbot Multimodal Integration Report

## Executive summary

Status: **PASS FOR PR REVIEW**. B-07 adds a narrow package-image flow:

```text
patient image -> B-05 candidates -> explicit server-issued confirmation
              -> canonical drug_product_id -> existing Drug Tool
```

An unconfirmed candidate is never `ConversationState.active_entity` and never produces medication facts. Production recognition approval remains **NO**: the B-05 model/catalog must be exercised in the deployment-equivalent private environment before enabling this for production traffic.

## Scope and isolation

- Baseline is merged B-06 PR #135, commit `5824e50bf82a068a602579d118e82c9da40a2617`.
- Work was performed only in `feature/drug-image-b07-chatbot-multimodal` at `H:/Vin AI/P-067-drug-image-b07`.
- No Track A source was changed. BUILD-44 is integrated only through its existing takeover/domain interfaces; its takeover policy is unchanged.
- Alembic head is now `0055`.

## Implementation

### Durable attempt and confirmation

Migration `0055_drug_recognition_attempt.py` adds `DrugRecognitionAttempt`. It persists scope, outcome/version, an allowlisted server-issued action ID, canonical candidate snapshot, requested aspect, expiry/supersession and final selection. It never stores raw image bytes, a source path, OCR text, embedding or model internals.

The lifecycle is `AWAITING_CONFIRMATION` -> `CONFIRMED`, with `INSUFFICIENT_EVIDENCE`, `FAILED`, `EXPIRED` and `SUPERSEDED` terminal states. A newer pending attempt for the same actor/patient/conversation supersedes the older one. Confirmation is scoped to exactly that actor, patient, conversation, latest attempt and opaque action ID. Same valid replay is idempotent; forged, cross-patient, expired and superseded actions are rejected.

Only after confirmation is the canonical `drug_product_id` promoted into `ConversationState.active_entity`. The trusted active `DrugIdMap` mapping is used when available to call the existing read-only Drug Tool. No fuzzy lookup of the display name is performed after canonical binding.

### API and safety

- `POST /api/v1/agent/v2/drug-images/recognize` is multipart and additive; existing JSON chat remains unchanged.
- `POST /api/v1/agent/v2/drug-images/confirm` accepts only attempt ID and an opaque server action ID. It never accepts a client-selected product ID.
- JPEG, PNG and WebP must agree between declared MIME and Pillow decoder; size, dimensions, pixels, corrupt payloads and Pillow bomb warnings are rejected before B-05.
- Acute danger, possible overdose, medication-dose safety, missed-dose and delayed-dose text delegates to the existing Agent V2 safety path before B-05.
- B-05 `DrugImageRecognizer`, its existing optional OCR and deterministic rerank are reused directly. There is no second recognizer and no generative vision call.
- Admission is bounded to one recognition per worker. A 30-second response deadline prevents an overrun from creating a recognition attempt.

`HIGH_EVIDENCE_MATCH` still requires confirmation; ambiguous results show at most three candidates. Insufficient evidence returns only retake/manual-name guidance and does not mutate active context or call the Drug Tool.

### Private media and doctor takeover

Normal recognition writes only to `drug_image_chat_temp_dir` and unlinks its private temp file in `finally`, on both success and failure. No raw media is placed in AgentRun metadata, browser chat persistence, telemetry, logs, Judge input or catalog/dose-photo storage.

During an ACTIVE BUILD-44 takeover, B-05, OCR, Agent V2 model/tool flow and normal chat state are skipped. The upload is MIME/decoder-validated and stored only as an opaque key in the new `DoctorReviewImageAttachment` table, linked to a patient `DoctorReviewMessage`. The binary is in the separate `drug_image_chat_doctor_storage_dir`, expires after 24 hours by default, and is deleted by a daily scheduler job (as well as opportunistically on later private uploads). Only the real active doctor assigned to that handoff can retrieve it through the doctor-review attachment endpoint. Patient handoff status does not expose its attachment ID.

## Frontend and contract

The existing patient assistant now supports file attachment, preview/removal, upload state and safe errors; it renders candidate cards and explicit confirmation, with retake/manual-name guidance. It does not display a canonical product ID before confirmation. Next.js proxy routes keep the frontend's auth boundary intact. `specs/api-contracts.md` documents the additive endpoints and safe response fields.

The requested aspect is stored as a bounded semantic value (`side_effects`, `drug_uses`, `dosage`, `warnings`, etc.), not raw patient text. On confirmation the existing Drug Tool receives that aspect, so the user does not need to repeat the question.

## Observability and retention

Events use only safe IDs/outcome/version/count/latency/error code: `DRUG_IMAGE_UPLOAD_ACCEPTED`, `DRUG_IMAGE_UPLOAD_REJECTED`, `DRUG_RECOGNITION_STARTED`, `DRUG_RECOGNITION_RESULT` and `DRUG_CANDIDATE_CONFIRMED`. No raw image, OCR, path or patient message is logged. Normal input is immediately deleted; doctor-takeover input is private and has a 24-hour expiry policy.

## Verification

Completed locally:

- `ruff check` on all B-07 backend changes: pass.
- B-07 lifecycle/security tests: 6 passed (MIME spoof, corrupt payload, oversized payload, decompression bomb, forged/cross-patient/expired/stale confirmation, replay/idempotency, no raw persistence, private expiry cleanup).
- Targeted regression: 69 passed across B-05 recognition/retrieval, B-06 storage/delivery, BUILD-44 takeover, Agent V2 Safety, Dose Safety and ConversationState.
- `alembic heads`: `0055 (head)`.
- Frontend `npm run build`: pass.
- Frontend `npm run lint`: pass.
- Local SQLite durability pilot exercised creation, supersession, confirmation, replay and private-takeover attachment lifecycle. B-05 itself remains covered by its existing targeted recognition/retrieval suite.

Performance pilot (50 synthetic 100x100 PNG validations on this Windows worktree): validation P50 **0.086 ms**, P95 **0.133 ms**. End-to-end B-05 embedding/retrieval/OCR P50/P95 is intentionally **not claimed** because this worktree does not contain an approved representative private catalog/model pilot. No production SLA is implied.

## Release gate

| Gate | Result |
| --- | --- |
| B-06 merged baseline / Track A isolation | PASS / PASS |
| Upload validation / temp cleanup / raw image logging | PASS / PASS / NONE |
| B-05 reused / duplicate recognizer / generative recognition calls | PASS / NO / 0 |
| Unconfirmed candidate -> active entity | NO |
| Server-issued, forged, stale, superseded, idempotent confirmation | PASS / REJECTED / REJECTED / REJECTED / PASS |
| Canonical product and Drug Tool after confirmation | PASS |
| Drug Tool before confirmation / medical facts from vision or OCR | NONE / NONE |
| Requested-aspect carry-forward | PASS |
| Safety and Dose Safety precedence | PASS |
| Doctor ACTIVE suppression / model calls / recognition calls | PASS / 0 / 0 |
| Doctor private attachment authorization | PASS (assigned active doctor only) |
| Frontend upload/candidate UI / auth isolation / security tests | PASS / PASS / PASS |
| Local functional E2E pilot | PASS |
| Production recognition approved | NO |
| B-08 ready | NO (not started) |
| Ready for PR review | YES |

Known limitation: the response deadline cannot forcibly interrupt a third-party synchronous GPU/CPU call, but it prevents a late result from creating a confirmation attempt and admission is acquired before reading the request payload, preventing an in-process backlog of max-size image buffers.
