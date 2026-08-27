# B-08 Production Recognition Enablement Report

**Date:** 2026-08-28
**Decision requested by:** user, after reviewing real-phone test evidence (see
§1) and explicitly accepting the residual risk described in §5.
**Scope:** turn `DRUG_IMAGE_CHAT_RECOGNITION_ENABLED` on for production,
add the runtime it needs, add a UI safety net for wrong/no-match
candidates, and fix a real cold-start defect found while validating this
end to end. Does **not** add OCR (see §5) and does **not** change the
recognition algorithm, thresholds, or the `/recognize` and `/confirm`
API contracts.

## 1. Real-phone evidence this decision is based on

8 real phone photos of one real product (Snapcef 16mg/10ml Hải Dương,
20 ống x 10ml) were run through the actual B-04/B-05 pipeline (local,
against the real 3543-row production catalog imported + embedded
locally) before this task began:

| Result | Count | Notes |
|---|---:|---|
| Correct Top-1 | 2/8 | Sharp, front panel, roughly straight-on |
| Wrong Top-1 (candidate list shown, correct product NOT in it) | 5/8 | Wrong panel, extreme angle, hand occlusion, harsh backlight |
| Correctly caught by the quality gate (asked to retake) | 1/8 | Severe motion blur + overexposure |

This is the first real-phone evidence this project has had (B-08's prior
revalidation, PR #151, recorded 0 approved real-phone cases). It is a
single product, 8 photos — far short of a rigorous approval dataset — but
it directly informed the decision below: the system is usable for
front-panel, reasonably-lit photos, and unreliable otherwise, with real
failure modes that are about photo framing, not random noise.

**Important correction folded into this enablement**: the "system asks
again when unsure" property the decision relied on is only true for the
1/8 quality-gate case. For the other 5/8 wrong cases, the system
confidently offered a 3-candidate list that did **not** contain the
correct product at all. §3 addresses this directly.

## 2. What changed

### 2a. Production dependencies (`requirements.txt`)

Added the same CPU-only pins already used and tested in B-04/B-05
(`requirements-drug-image-vision.txt`): `torch==2.5.1+cpu`,
`torchvision==0.20.1+cpu`, `open_clip_torch==2.26.1`. These were
previously excluded from the backend container by design. No OCR
package (`pytesseract`) was added — see §5.

### 2b. Feature flag

`DRUG_IMAGE_CHAT_RECOGNITION_ENABLED` code default stays `false`
(unchanged). Enablement is via a Railway environment variable on
`VMEC-04/BE` (`production`), consistent with how every other flag in
this project is toggled — not a code default change. **This variable
has not been set yet** — see §7, this is a report on what was built and
locally validated, not a claim that production is already live.

### 2c. New UI safety net — "not this drug"

`frontend/src/components/chat-message.tsx` / `.../patient/assistant/page.tsx`:
when recognition returns `AMBIGUOUS_MATCH` (up to 3 candidates), the
candidate list now includes an explicit extra option below the real
candidates: **"Không phải thuốc nào ở trên — nhập tên thuốc"**. Clicking
it does not call any confirm/reject API (there is nothing to cancel
server-side — an unconfirmed recognition attempt already expires on its
own TTL, unchanged); it appends a normal assistant chat turn asking the
user to type the drug name, exactly the same free-text path that was
always available but never suggested. This directly targets the 5/8
real failure mode from §1 (wrong candidate list, correct answer absent).

This does not eliminate the risk of a user mis-clicking a wrong
candidate — it makes the correct path visible and one tap away instead
of requiring the user to already know they can just type instead.

### 2d. Real defect found and fixed: cold-start timeout

`get_drug_image_recognizer()` (`backend/api/drug_image_chat_routes.py`)
is `@lru_cache(maxsize=1)` — cheap after the first call, but the first
call loads the OpenCLIP ViT-B/32 checkpoint from disk. Measured locally:

```
1st request after a fresh process start: RECOGNITION_TIMEOUT (HTTP 422)
2nd request (same process):              0.34s, HTTP 200
```

Without a fix, **the first real patient to send a photo after every
container restart/redeploy would get a hard failure**, not a
recognition result — a real, user-facing defect this task's own testing
surfaced (B-08's prior report flagged cold-start as
`NOT_MEASURED`; it is now measured and was a real problem).

**Fix**: `backend/main.py`'s `lifespan` now calls
`get_drug_image_recognizer()` once at startup, guarded by
`settings.drug_image_chat_recognition_enabled` (no cost at all when the
flag is off — matches the existing "no runtime constructed unless
policy permits" design already in this route). Measured locally:
warmup took **22.56s** at startup (real number, printed as
`[INFO] Drug image recognition warmup complete: duration_ms=...`,
following the exact convention already used for the RAG warmup line).
The first real request after this fix, on a freshly restarted process,
completed in **2.76s / HTTP 200** — no more timeout.

## 3. Local end-to-end verification (real HTTP, real DB, real auth)

Ran the actual backend locally with the new dependencies installed, the
flag enabled, and the same real local Postgres already holding the
production catalog + embeddings (built for the earlier real-phone test
in §1). A dedicated local-only test account was created, exercised, and
deleted afterward (not committed, not production).

| Check | Result |
|---|---|
| App boots with new dependencies present | PASS |
| Startup warmup runs and logs duration when flag enabled | PASS (22.56s measured) |
| First request after restart no longer times out | PASS (2.76s, was: `RECOGNITION_TIMEOUT`) |
| Real `POST /agent/v2/drug-images/recognize` (real Snapcef photo, real auth) | PASS — `AMBIGUOUS_MATCH`, Snapcef ranked #1 of 3, response shape matches what the frontend expects (`action_id`/`product_display_name`/`rank`) |
| Real `POST /agent/v2/drug-images/confirm` (confirm the top candidate) | PASS — `CONFIRMED`, `canonical_drug_product_id` matches the real Snapcef product id exactly |
| `pytest tests/api/test_drug_image_chat_routes.py tests/services/test_drug_image_chat.py tests/services/test_drug_image_recognition.py tests/services/test_drug_image_retrieval.py tests/services/test_drug_images.py` | 37/37 passed (with the new dependencies actually installed, not mocked away) |
| `ruff check backend/main.py` | passed |
| `npx tsc --noEmit` (frontend) | passed, 0 errors |
| `pnpm build` (frontend) | passed |
| Repo-wide `eslint` | blocked by a pre-existing CRLF/LF baseline mismatch unrelated to this change (documented already in PR #150's own report); not attempted to fix here, matches established precedent |

No screenshot/browser-automation tooling exists in this repo (consistent
with every prior build) — UI verification is code-review plus the
`tsc`/build gates plus the real HTTP contract above (the frontend's own
candidate-rendering code path was read directly, not just assumed).

## 4. What did NOT change

- Recognition algorithm, scoring, or `_decide()` thresholds
  (`backend/services/drug_image_recognition.py`) — untouched.
- `/recognize` and `/confirm` API request/response contracts — untouched
  (the new UI button calls neither endpoint).
- `FileSystemStorageBackend`, image storage layout, or the drug-image API
  used by the Today page — untouched.
- Safety/dose-safety precedence and doctor-takeover precedence ahead of
  recognition — untouched, still covered by the existing B-07 regression
  tests (all still pass with the real runtime present).

## 5. Explicitly known, un-closed gap: no OCR

`OptionalTesseractOcrExtractor` degrades to `OCR_UNAVAILABLE` when
`pytesseract`/the Tesseract binary is missing — true both before and
after this change, since **no OCR package or system binary was added**.
Consequence: `_decide()` requires OCR-corroborated text
(`strong_text`) together with visual top-1 to reach
`HIGH_EVIDENCE_MATCH`; without OCR this is unreachable, so **every
successful recognition in production will surface as `AMBIGUOUS_MATCH`
(a candidate list requiring explicit confirmation), never a direct,
confident answer**. This is a real behavioral consequence, not a
regression — it is, if anything, the safer of the two options (a human
always confirms), and it is why §2c's safety-net button matters for
every recognition call, not just edge cases. Adding real OCR (Tesseract
+ a Vietnamese language pack, Dockerfile changes, an actual accuracy
benchmark) was left out of this task's scope — B-08's own finding that
Vietnamese OCR is `NOT_READY` still stands unchanged.

## 6. Residual risk (explicit, not resolved by this task)

- The real-phone dataset behind this decision is 8 photos of 1 product.
  It shows a believable, diagnosable failure pattern (§1) but is not a
  statistically meaningful accuracy measurement across the real catalog
  of 3556 products, lighting conditions, and packaging styles.
- Cost/latency/memory/concurrency under real production load (multiple
  simultaneous users, Railway's actual CPU/RAM tier) remain unmeasured
  beyond this task's own single-user local timing numbers.
- The "not this drug" button reduces but does not eliminate the risk of
  a user confirming a wrong candidate — it depends on the user reading
  the options, which is a real, non-zero risk in a medication-identity
  flow.

## 7. Final gate

```
REAL-PHONE EVIDENCE GATHERED: YES (8 photos / 1 product, see §1)
"NOT THIS DRUG" SAFETY NET: PASS (added, wired, verified in local build)
COLD-START TIMEOUT DEFECT: FOUND AND FIXED (warmup added to lifespan)
VISION DEPENDENCIES IN requirements.txt: PASS
LOCAL E2E (recognize + confirm, real HTTP/DB/auth): PASS
EXISTING TEST SUITE WITH REAL RUNTIME PRESENT: 37/37 PASS
FRONTEND BUILD: PASS
OCR: STILL NOT ADDED (HIGH_EVIDENCE_MATCH unreachable, see §5 — accepted trade-off)
PRODUCTION FLAG SET: NOT YET DONE (this PR does not flip it — see §2b)
READY FOR HUMAN REVIEW AND EXPLICIT GO-LIVE DECISION: YES
DEPLOYED: NO — awaiting explicit approval to merge, deploy, and set the
Railway environment variable, per this project's standing process.
```
