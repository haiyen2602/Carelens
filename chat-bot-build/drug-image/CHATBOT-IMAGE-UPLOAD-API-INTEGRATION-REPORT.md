# Chatbot Image Upload API Integration Report

## Scope and decision

This change repairs the B-07 image-upload integration without adding another
recognition API or enabling production recognition. B-08 remains authoritative:
`PRODUCTION RECOGNITION = NOT_APPROVED`.

## Current 500 root cause

The frontend already built a real `FormData` payload with the required
`patient_id`, `conversation_id`, `message`, and `file` fields, and the Next.js
route forwarded that multipart body and Bearer authorization. The backend route,
however, declared `get_drug_image_recognizer` as a FastAPI dependency. FastAPI
therefore constructed `OpenClipImageEmbedder` before entering the route handler.

The production runtime intentionally does not include the offline-only packages
in `requirements-drug-image-vision.txt`; B-08 also found no approved
deployment-equivalent recognition runtime. A construction failure at dependency
resolution is outside the handler's existing safe exception mapping and becomes
an HTTP 500. No production traceback was available in the queried logs, so this
is recorded as the source/deployment mismatch evidenced by the requirements and
dependency ordering, not as a fabricated exact traceback.

## Implemented fix

- The recognizer is no longer a FastAPI dependency. It is constructed only after
  authorization, safety precedence, upload validation, and doctor-takeover
  handling.
- `DRUG_IMAGE_CHAT_RECOGNITION_ENABLED` defaults to `false`. When disabled,
  the endpoint returns `RECOGNITION_UNAVAILABLE` and a patient-safe reply; it
  does not construct the vision runtime or create a recognition attempt.
- Doctor takeover remains ahead of the recognition gate and still receives the
  private upload. Safety/dose-safety remains ahead of upload processing and
  recognition.
- The Next.js proxy preserves multipart bytes, filename/MIME, and Authorization,
  never sets a multipart boundary itself, and maps malformed multipart to 400
  and unavailable upstream to 503 instead of an unhandled Next.js 500.
- The chat UI shows a local preview and `Đang phân tích ảnh...`; it appends the
  user upload turn only after the API accepts the request. On failure it keeps
  the selected image and draft text for retry.

## Contract and safety verification

| Gate | Result | Evidence |
|---|---|---|
| Frontend multipart | PASS | `FormData` uses exact B-07 fields and the actual `File` object. |
| Next proxy | PASS | `request.formData()` is forwarded as `body: form`; no JSON conversion or explicit multipart Content-Type. |
| Auth forwarding | PASS | Bearer value is forwarded unchanged by the proxy. |
| Backend B-07 endpoint | PASS | Existing endpoint retained; recognizer construction made policy-bound. |
| Upload image / camera capture | PASS (code/build) | Both picker and `CameraCapture` use `recognizeDrugImage`. |
| Valid JPEG, PNG, WebP | PASS | Validation regression test covers all three decoder formats. |
| No expected generic 500 | PASS (code/test) | Disabled policy returns bounded status; proxy returns 400/503 for expected parser/upstream failures. |
| Candidate flow | PRESERVED | Enabled path still creates server-issued attempts and returns bounded candidates. |
| Explicit confirmation | PRESERVED | Confirmation endpoint, opaque action IDs, and canonical promotion unchanged. |
| Unconfirmed candidate != active entity | PASS | Unavailable response has no attempt/candidates; existing confirmation is the only promotion path. |
| Safety and dose-safety precedence | PASS | New route regression test verifies safety branch does not invoke the runtime. |
| Doctor takeover suppression | PASS | New route regression test verifies takeover wins while recognition is disabled. |
| Normal text chat | UNCHANGED | No normal-chat code path changed. |
| Production recognition policy | PRESERVED | Default remains disabled; no runtime dependency added and no deployment setting changed. |

## Verification run

- `pytest -p no:cacheprovider tests/api/test_drug_image_chat_routes.py tests/services/test_drug_image_chat.py -q` — **12 passed**.
- `ruff check --no-cache ...` for changed backend/tests — **passed**.
- `npm run test:drug-image-ui` — **passed**.
- Next.js production build — **passed**, including TypeScript and
  `/api/drug-images/recognize` route compilation.

The repository-wide frontend ESLint command is currently blocked by a pre-existing
line-ending configuration mismatch: the checkout has CRLF while the Prettier
rule requires LF, producing 32,419 baseline `Delete CR` errors across unrelated
files. No repository-wide formatting was performed because that would be an
unrelated bulk change. The production build provides type/build validation for
the changed frontend code.

## Release gate

`CURRENT 500 ROOT CAUSE: FIXED IN CODE — optional vision runtime was resolved
before handler policy/error mapping.`

`FRONTEND MULTIPART: PASS`  
`NEXT PROXY: PASS`  
`AUTH FORWARDING: PASS`  
`BACKEND B-07 ENDPOINT: PASS`  
`UPLOAD IMAGE: PASS (LOCAL)`  
`CAMERA CAPTURE: PASS (CODE/BUILD)`  
`VALID JPEG: PASS`  
`VALID PNG: PASS`  
`VALID WEBP: PASS`  
`NO GENERIC 500: PASS (EXPECTED POLICY/INFRA PATHS)`  
`CANDIDATE FLOW: PRESERVED`  
`EXPLICIT CONFIRMATION: PRESERVED`  
`UNCONFIRMED CANDIDATE != ACTIVE_ENTITY: PASS`  
`NORMAL TEXT CHAT: UNCHANGED`  
`PRODUCTION RECOGNITION POLICY: PRESERVED`

`READY FOR PRODUCTION UI USE: NO — pending reviewed merge, deployment, and
browser/production verification. Recognition itself remains NOT_APPROVED and
must continue to return the graceful unavailable state until B-08 requirements
are satisfied.`

No production recognition was enabled, deployed, or evaluated by this task.
