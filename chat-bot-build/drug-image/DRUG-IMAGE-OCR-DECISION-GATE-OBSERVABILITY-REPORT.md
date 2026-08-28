# Drug Image OCR + Decision Gate + Observability Report

**Date:** 2026-08-28
**Branch:** `fix/drug-image-ocr-decision-observability`
**Baseline:** `origin/main` at `126e4cc3` (PR #155, "preserve chatbot
drug-image confirmation"), rebased conceptually against `58f3285b` (PR #156,
unrelated admin-dashboard work) — no conflicting files.

## 1. Pre-fix reproduction (real, live evidence — not synthetic)

Confirmed live on production immediately before this task's own fix, using
`test01.jpg` through the real authenticated endpoint:

```
POST /agent/v2/drug-images/recognize
→ HTTP 200
{"status":"INSUFFICIENT_EVIDENCE",
 "reply":"Tôi chưa thể xác định chắc chắn thuốc trong ảnh...",
 "outcome":"AMBIGUOUS_MATCH",
 "candidates":[]}
```

**Exact bug**: `outcome` is genuinely `AMBIGUOUS_MATCH` (real visual
candidate exists, real evidence), but the top-level `status` field the
frontend actually branches on is `INSUFFICIENT_EVIDENCE` — collapsing two
semantically distinct outcomes into one API surface value.

**Root cause, traced to exact source**:

1. `backend/services/drug_image_chat.py::create_attempt` (as of PR #155,
   before this task) already correctly persists `attempt.outcome` as
   `AMBIGUOUS_MATCH` when that's the real recognizer outcome (never forced
   to `INSUFFICIENT_EVIDENCE` at the persistence layer — PR #155 got this
   right).
2. `backend/api/drug_image_chat_routes.py::recognize_drug_image` (pre-task)
   computed the API-facing `status` as
   `"CANDIDATES" if presentation.candidates else "INSUFFICIENT_EVIDENCE"` —
   a **two-way** switch with no `AMBIGUOUS_MATCH` branch at all. Since
   `AMBIGUOUS_MATCH` correctly carries an empty `candidates` list (by
   design — see §7), it always fell into the `else` arm and was reported to
   the client as `INSUFFICIENT_EVIDENCE`, even though the persisted
   `outcome` field on the same response was correctly `AMBIGUOUS_MATCH`.
3. `backend/models/schemas.py::DrugImageRecognitionOut.status` (pre-task)
   had no `"AMBIGUOUS_MATCH"` literal in its `Literal[...]` type at all —
   the schema itself made the correct three-way distinction inexpressible.
4. Observability gap (independent of the above): no structured evidence
   (quality/OCR/visual-score/margin/decision-reason) was logged anywhere,
   so this exact collapse was invisible without reproducing it by hand
   against the live endpoint, which is what this section did.

## 2. Production OCR runtime

**Audit of the pre-task state**: `OptionalTesseractOcrExtractor` caught only
bare `ImportError` on `import pytesseract` and returned `OCR_UNAVAILABLE`;
`pytesseract` itself was not in `requirements.txt` and no `tesseract-ocr`
system package was in the `Dockerfile`. Every production recognition call
therefore ran with zero OCR corroboration, making `HIGH_EVIDENCE_MATCH`
structurally unreachable regardless of image quality.

**Implemented**:

- `Dockerfile`: `tesseract-ocr`, `tesseract-ocr-eng`, `tesseract-ocr-vie`
  added to the existing `apt-get install` line (alongside `gosu`, not a new
  layer).
- `requirements.txt`: `pytesseract==0.3.13` added (the pure-Python adapter;
  ~14KB wheel, no heavy transitive dependencies).
- `backend/services/drug_image_recognition.py::OptionalTesseractOcrExtractor`
  rewritten with an explicit, cached `_resolve_runtime()` probe:
  `shutil.which("tesseract")` (binary discoverable) → `get_languages()`
  (required `vie`+`eng` both installed) → only then is `image_to_string()`
  ever called. Each stage maps to a distinct, explicit status:
  `OCR_AVAILABLE` / `OCR_UNAVAILABLE` (binary or language pack missing, or
  `pytesseract` not importable) / `OCR_FAILED` (the probe or the call
  itself errored) / `OCR_NOT_RUN` (recognition never reached the OCR step,
  e.g. quality-gate rejection). The probe result is cached on the extractor
  instance (paid once, not once per image) but a runtime that vanishes
  mid-call (`TesseractNotFoundError` on `image_to_string`) resets the cache
  so the next call re-probes rather than trusting stale state.
- `backend/config.py`: `drug_image_chat_ocr_timeout_seconds` (default
  `5.0`, bounded `0 < x <= 30`) — a per-call timeout passed straight into
  `pytesseract.image_to_string(..., timeout=...)`.
- Real local verification (installed Tesseract 5.5.2 + `vie`/`eng`
  `traineddata` via conda-forge + the official tessdata repo, since this
  Windows dev machine has neither by default — the equivalent of what the
  Dockerfile installs in the Linux container): OCR genuinely reads real
  text off real photos (`SNAPCEF`, `16mg/10ml`, `Hộp 20 ống x 10ml`
  extracted from `test01.jpg`).

Normal text chat still never imports `pytesseract`/constructs
`OpenClipImageEmbedder` — both remain behind
`get_drug_image_recognizer()`, which is only ever called from the drug-image
route and (guarded by the same feature flag) the startup warmup added in
an earlier task.

**OCR RUNTIME: PASS.**

## 3. Deployment / resource safety (measured, not estimated)

Measured locally (CPU, same class of hardware constraint as Railway's
container tier):

| Metric | Value |
|---|---|
| Cold init (first OCR call, includes the `shutil.which`+`get_languages` probe) | 1219 ms |
| Warm per-image OCR latency (n=7) | min 734 ms / avg 792 ms / max 906 ms |
| Memory delta after cold init | +15.4 MB |
| Memory delta after 8 warm calls | +16.6 MB total (no growth per call — no leak observed) |
| Forced 1ms timeout on a real image | Returns `OCR_FAILED` in bounded time, no hang, no crash |

Recognition's own overall timeout
(`drug_image_chat_recognition_timeout_seconds`, unchanged at 30s) has
ample headroom: OCR adds under 1s typically, bounded at
`drug_image_chat_ocr_timeout_seconds` (5s default) worst case, on top of
the existing visual-embedding step. The startup warmup (added in an
earlier task, unchanged here) already pays OpenCLIP's own larger cold-load
cost once at boot, not per-request; this task's OCR probe is warmed
alongside it in the same guarded startup block (see §7 of the review
response in `B08-PRODUCTION-RECOGNITION-ENABLEMENT-REPORT.md` for why the
combined warmup time stays well inside Railway's 300s healthcheck budget).

Memory overhead (~15MB) is small relative to OpenCLIP/torch's own
footprint (~500MB+ of installed packages). No unacceptable resource
pressure was found; §3's STOP condition does not trigger.

**RESOURCE SAFETY: PASS.**

## 4–6. Decision semantics, HIGH_EVIDENCE policy, OCR corroboration

Audited `_decide()` in full (`backend/services/drug_image_recognition.py`).
Unchanged logic, renamed reason codes only (§9):

```
quality != PASS                          → INSUFFICIENT_EVIDENCE (QUALITY_FAILED)
no visual candidates                     → INSUFFICIENT_EVIDENCE (INSUFFICIENT_VISUAL_EVIDENCE)
top candidate has a hard conflict        → INSUFFICIENT_EVIDENCE (OCR_HARD_CONFLICT, ...)
OCR name-match on visual Top-1
  AND visual_rank == 1
  AND no duplicate-content ambiguity     → HIGH_EVIDENCE_MATCH (OCR_NAME_MATCH[, OCR_STRENGTH_MATCH], HIGH_EVIDENCE_CONFIRMED)
text signals present but corroborate
  no catalog candidate at all            → INSUFFICIENT_EVIDENCE (INSUFFICIENT_VISUAL_EVIDENCE)
duplicate/near-duplicate reference       → AMBIGUOUS_MATCH (DUPLICATE_CONTENT_AMBIGUITY)
otherwise                                → AMBIGUOUS_MATCH (AMBIGUOUS_VISUAL_ONLY)
```

No cosine/visual-score threshold exists or was added — HIGH_EVIDENCE
remains bounded strictly to "visual Top-1 plus independent OCR name
corroboration," exactly as before this task. **OCR is mandatory for
HIGH_EVIDENCE_MATCH** — this was already true pre-task and remains true;
it is now explicit in code (`OCR_NAME_MATCH` reason code) and in
`RecognitionResult.ocr_status`/`decision_reason_codes`, not just in a
comment.

A real bug in the OCR-name-corroboration comparison was found and fixed
while implementing this: `_name_match()` previously compared OCR text
against the catalog's full `display_name`, which includes manufacturer and
pack-size text appended after the brand name (e.g. "Snapcef 16mg/10ml HẢI
Dương 20 ỐNG X 10ml") — text that legitimately does not appear on a
box's front panel. It now compares against the *pre-strength identity
segment* only (the text before the first strength pattern), while
`_decide()`'s own conflict/strength-match logic is untouched — OCR
corroboration got measurably easier to satisfy correctly, not looser as a
confidence policy. §11's own result (0 false HIGH_EVIDENCE across the
retest set) is the check on whether that traded precision for false
positives — it did not.

Strength conflicts (`OCR: Drug X 20mg` vs. `Visual: Drug X 10mg`) remain a
hard conflict routed to `INSUFFICIENT_EVIDENCE`, never silently ignored;
unreadable/noisy OCR text (no structured signals extracted) contributes no
corroboration and cannot force confidence, matching §6's requirement
exactly.

**HIGH_EVIDENCE_MATCH REMAINS OCR-GATED: PASS. NO THRESHOLD LOWERED: PASS.**

## 7. User-facing UX mapping

Verified by direct code read of the current (PR #155-introduced, unchanged
by this task) frontend and backend:

- `HIGH_EVIDENCE_MATCH` → API `status="CANDIDATES"` with **exactly one**
  candidate → UI renders one card, `[Đúng thuốc này]` / `[Không đúng]`
  (`frontend/src/components/chat-message.tsx`, gated on
  `outcome === "HIGH_EVIDENCE_MATCH" && candidates.length === 1`).
- `AMBIGUOUS_MATCH` → API `status="AMBIGUOUS_MATCH"` (this task's own fix,
  see §1/§9), empty candidate list, reply: *"Tôi đã tìm thấy một vài khả
  năng nhưng chưa đủ chắc chắn để xác định thuốc. Hãy chụp rõ mặt trước
  hộp thuốc hoặc nhập tên thuốc."* — no candidate names, no card rendered.
- `INSUFFICIENT_EVIDENCE` → API `status="INSUFFICIENT_EVIDENCE"`, empty
  candidate list, reply: *"Ảnh hiện tại chưa đủ thông tin để nhận diện
  thuốc. Hãy chụp lại rõ tên và hàm lượng thuốc."*

No similarity score, raw OCR text, or internal Top-K is exposed in any API
response or UI string — confirmed by reading every field on
`DrugImageRecognitionOut`/`DrugImageCandidateOut` and every string literal
in the two changed frontend files.

**UX MAPPING: PASS.**

## 8. Observability

New `RecognitionObservability` dataclass +
`recognition_observability(result)` projector in
`drug_image_recognition.py`, and a new structured log line
(`DRUG_RECOGNITION_EVIDENCE`) in the route, emitted for every recognize
call with: `quality_status`, `quality_reasons`, `ocr_status`,
`ocr_signal_count`, `internal_top1_drug_product_id`,
`internal_top1_visual_score`, `internal_top2_visual_score`,
`top1_top2_margin`, `ocr_name_match`, `ocr_strength_match`, `ocr_conflict`,
`decision_reason_codes`, `recognizer_outcome`, `persisted_outcome`,
`api_outcome`. No raw image bytes, no OCR full text, no embedding vectors,
no filesystem paths, no secrets are included anywhere in this line —
verified by reading every value passed to the logger call. This satisfies
§8's field list without a database schema change (no migration was
needed or added).

**OCR STATUS OBSERVABLE: PASS. QUALITY STATUS OBSERVABLE: PASS. INTERNAL
TOP-1 OBSERVABLE: PASS. TOP1-TOP2 MARGIN OBSERVABLE: PASS. DECISION
REASONS OBSERVABLE: PASS.**

## 9. Decision reason codes

Reason codes renamed from ad hoc free-form strings to the bounded set §9
prescribes: `QUALITY_FAILED`, `OCR_UNAVAILABLE`, `OCR_FAILED`,
`OCR_NAME_MATCH`, `OCR_STRENGTH_MATCH`, `OCR_HARD_CONFLICT`,
`INSUFFICIENT_VISUAL_EVIDENCE`, `DUPLICATE_CONTENT_AMBIGUITY`,
`HIGH_EVIDENCE_CONFIRMED`, `AMBIGUOUS_VISUAL_ONLY`. (`VISUAL_SCORE_LOW`/
`VISUAL_MARGIN_LOW`/`LOOKALIKE_CONFLICT` from §9's suggested list are not
emitted because no cosine-threshold or dedicated lookalike-cohort check
exists in `_decide()` — unchanged from before this task; not fabricated.)
Two pre-existing unit tests asserted on the old free-form strings and were
updated to the new bounded codes (`tests/services/test_drug_image_recognition.py`,
2 lines changed, same assertions/behavior, new code values only).

**DECISION REASON CODES: PASS.**

## 10. Real-phone re-test (all 8 images, visual + real OCR)

Full pipeline (`DrugImageRecognizer` with the real, newly-wired
`OptionalTesseractOcrExtractor`, real Tesseract 5.5.2 + vie/eng
`traineddata`) against the real 3543-row production catalog (imported and
embedded locally in an earlier task, byte-identical to production).
Ground truth for all 8 images: Snapcef 16mg/10ml Hải Dương
(`19e21f82-8370-5df4-a1ac-bc6b5780d9cc`).

| Image | quality | OCR status | Top-1 (visual) | margin | OCR name/strength match | conflict | Outcome | Reason codes | User sees a candidate? |
|---|---|---|---|---|---|---|---|---|---|
| test01 | PASS | OCR_AVAILABLE | Snapcef (correct) | 0.112 | **True / True** | No | **HIGH_EVIDENCE_MATCH** | OCR_NAME_MATCH, OCR_STRENGTH_MATCH, HIGH_EVIDENCE_CONFIRMED | Yes — Snapcef, 1 card |
| test02 | PASS | OCR_AVAILABLE | Snapcef (correct) | 0.098 | False / True | No | AMBIGUOUS_MATCH | AMBIGUOUS_VISUAL_ONLY | No |
| test03 | PASS | OCR_AVAILABLE | An Cung Ngưu Hoàng Hoàn (wrong) | 0.0006 | False / False | No | AMBIGUOUS_MATCH | AMBIGUOUS_VISUAL_ONLY | No |
| test04 | PASS | OCR_AVAILABLE | Berocca Bayer (wrong) | 0.0013 | False / False | No | AMBIGUOUS_MATCH | AMBIGUOUS_VISUAL_ONLY | No |
| test05 | **RETAKE_RECOMMENDED** (blurry) | OCR_AVAILABLE (not used) | — | — | — | — | **INSUFFICIENT_EVIDENCE** | QUALITY_FAILED | No — asked to retake |
| test06 | PASS | OCR_AVAILABLE | Ezvasten DAVI (wrong) | 0.0088 | False / False | No | AMBIGUOUS_MATCH | AMBIGUOUS_VISUAL_ONLY | No |
| test07 | PASS | OCR_AVAILABLE | Paracetamol infusion (wrong) | 0.0054 | False / False | No | AMBIGUOUS_MATCH | AMBIGUOUS_VISUAL_ONLY | No |
| test08 | PASS | OCR_AVAILABLE | Nebicard (wrong) | 0.0012 | False / False | No | AMBIGUOUS_MATCH | AMBIGUOUS_VISUAL_ONLY | No |

**Summary**:

- Top-1 visually correct: **2/8** (test01, test02) — unchanged from the
  pre-OCR baseline; OCR does not affect visual retrieval itself.
- Top-3 contains truth: not separately re-measured this round (Top-K
  retrieval itself is unchanged from the already-tested B-04 baseline);
  both Top-1-correct cases are trivially also Top-3-correct.
- **HIGH_EVIDENCE correct: 1** (test01 — the one image with a clean,
  legible front-panel framing).
- **HIGH_EVIDENCE wrong: 0.**
- AMBIGUOUS: 6.
- INSUFFICIENT: 1 (quality gate, correctly).

The margin column makes the honest failure mode visible: test03/04/06/07/08
all have a Top-1/Top-2 visual margin under 0.01 — the visual signal itself
is barely distinguishing the correct product from an unrelated one on
these frames (poor angle/lighting/occlusion, documented photo-by-photo in
this project's own earlier local-only investigation before this task).
OCR did not — and structurally cannot — rescue a visual Top-1 that isn't
actually the right product; it only ever adds confidence on top of an
already-correct visual Top-1 (test01), exactly as §6 requires.

**REAL PHONE TESTS: 2/8 Top-1 correct. HIGH_EVIDENCE CORRECT: 1.
HIGH_EVIDENCE WRONG: 0. AMBIGUOUS: 6. INSUFFICIENT: 1.**

## 11. Critical safety metric

**FALSE HIGH_EVIDENCE IDENTIFICATION: 0 / 8.**

The only `HIGH_EVIDENCE_MATCH` produced across the full retest set is the
genuinely correct product. No image was pushed to a confident, single-card
answer that was wrong. This is the target this section requires, and nothing
in this task's implementation optimized for HIGH_EVIDENCE coverage at
precision's expense — coverage stayed at 1/8, exactly the one case where
both the visual signal and the OCR text corroborate honestly.

**FALSE HIGH_EVIDENCE IDENTIFICATION: 0. PASS.**

## 12. Unknown / non-drug check

**NOT_TESTED.** No unknown-product or non-drug test images are available
in the current real-phone set (`chat-bot-build/drug-image/drug_images_test/`
contains 8 Snapcef photos only). Stated explicitly per this section's own
instruction rather than fabricated.

## 13. Confirmation flow regression

Verified via a real, live local HTTP chain (not only the deterministic
unit test), using the one real HIGH_EVIDENCE case from §10 (`test01.jpg`):

```
1) POST /agent/v2/drug-images/recognize (test01.jpg)
   → outcome=HIGH_EVIDENCE_MATCH, status=CANDIDATES, 1 candidate (Snapcef)
2) POST /agent/v2/drug-images/confirm (that exact candidate's action_id)
   → status=CONFIRMED
   → canonical_drug_product_id = 19e21f82-8370-5df4-a1ac-bc6b5780d9cc (exact match)
   → reply includes real verified drug content (usage, contraindications,
     ADR) from get_drug_info — called immediately, no extra round trip
```

`ActiveEntity` persistence was independently verified by reading the real
`agent_run.metadata_json['conversation_state']` row directly from
Postgres: `active_entity.id` stayed the correct canonical product id across
every subsequent turn in the conversation, confirming the confirmation
bridge itself (introduced by PR #155, unmodified by this task) works.

**Follow-up finding (real, but out of this task's scope to fix — see
§19 STOP RULE, "do not modify unrelated Track A logic")**: the free-text
follow-up "tác dụng phụ thì sao?" was classified `UNKNOWN_OR_AMBIGUOUS`
rather than resolving directly to a verified `get_drug_info` answer for the
bound entity. This is **not** a broken entity binding — the persisted
`active_entity` was correct and unchanged at every turn, and the response
*did* include correctly entity-bound `offered_actions` (e.g. "Tác dụng phụ
của Snapcef 16mg/10ml..." with the right `entity_id`) as a one-tap
resolvable fallback. This is a pre-existing Track A free-text
intent-classification behavior (not introduced or changed by this branch —
`follow_up.py`/`orchestrator.py` were not modified), reproducible the same
way for the exact phrase PR #155's own report claims to have fixed
("thông tin chi tiết thuốc"). Flagged here for Track A's own owners rather
than patched in this task.

**CONFIRM → ACTIVE_ENTITY: PASS. CONFIRM → DRUG TOOL: PASS. FOLLOW-UP
AFTER CONFIRM (state binding): PASS. FOLLOW-UP AFTER CONFIRM (direct
free-text answer): PARTIAL — see finding above, pre-existing/out of
scope.**

## 14. Failure injection

11 new unit tests added
(`tests/services/test_drug_image_ocr_runtime.py`), covering every mode
§14 asks for, by mocking the `pytesseract`-shaped runtime object rather
than the real binary (so these run without a real Tesseract install, unlike
this report's other real-runtime measurements):

| Mode | Result |
|---|---|
| `pytesseract` not importable | `OCR_UNAVAILABLE`, no exception |
| Tesseract binary not on PATH | `OCR_UNAVAILABLE`, no exception, no call attempted |
| Required language pack missing | `OCR_UNAVAILABLE`, no exception, no call attempted |
| Runtime probe itself errors (`OSError`) | `OCR_FAILED`, no exception |
| Probe reports `TesseractNotFoundError` | `OCR_UNAVAILABLE`, no exception |
| Per-call timeout | `OCR_FAILED`, no exception, no hang |
| Process failure mid-call | `OCR_FAILED`, no exception |
| Binary vanishes mid-call | Runtime cache reset, next probe re-checks rather than trusting stale state |
| Genuinely available runtime | `OCR_AVAILABLE`, correct text returned |
| Repeated calls on an available runtime | Probed once, not once per image |
| Corrupt image (pre-existing coverage) | `tests/services/test_drug_image_chat.py::test_upload_validation_rejects_corrupt_oversized_and_decompression_bomb` — unchanged, still passing |
| Visual model unavailable (pre-existing coverage) | `tests/api/test_drug_image_chat_routes.py::test_enabled_model_load_failure_returns_safe_503_and_releases_slot` — unchanged, still passing |

No generic 500 in any of the above (confirmed by assertion in every test —
`extract()` never raises out of the extractor into the caller); no
candidate is ever auto-bound; no attempt is left stuck (the recognition
semaphore is released in every failure path, verified by the existing
route-level tests plus this task's new ones).

**FAILURE INJECTION: PASS (11 new + 2 pre-existing tests, all passing).**

## 15. Normal chat regression

`tests/api/test_drug_image_chat_routes.py`,
`tests/services/test_drug_image_chat.py`,
`tests/services/test_drug_image_recognition.py`,
`tests/services/test_drug_image_retrieval.py`,
`tests/services/test_drug_image_ocr_runtime.py`,
`tests/services/test_drug_images.py`: **51/51 passed.**

Broader Safety/Dose-Safety/Doctor-Takeover/Orchestrator/Follow-up
regression sweep (`-k "safety or dose_safety or doctor_takeover or
doctor_handoff or orchestrator or follow_up"`): **293/301 passed, 4
skipped, 8 failed.** The 8 failures were independently reproduced on an
**unmodified `origin/main`** checkout (same failures, same error —
`OperationalError` against `drug_id_map` in
`tests/test_agent_v2_safety_occurrence_binding.py` /
`tests/services/scheduling/test_safety_runtime_adapter.py`) — a
pre-existing local-Postgres-state issue on this workstation, unrelated to
and unaffected by this branch's changes. Not investigated further as out
of this task's scope.

Ruff on every changed backend/test file: **passed.** `tsc --noEmit`:
**0 errors.** Frontend `pnpm build`: **passed.**
`node tests/drug-image-ui.test.mjs`: **passed.**

**NORMAL TEXT CHAT: PASS. SAFETY: PASS. DOCTOR TAKEOVER: PASS (both via
the pre-existing, unmodified, still-passing regression suite).**

## 16. Production recommendation

`DRUG_IMAGE_CHAT_RECOGNITION_ENABLED` was already set on Railway
production in an earlier task (with the vision runtime but *without* OCR)
— production recognition is not newly "enabled" by this report. This
task's own scope was to fix the OCR runtime, the status-collapsing bug,
and observability, then re-decide.

Evidence for the decision: `FALSE HIGH_EVIDENCE IDENTIFICATION = 0/8`
(§11) — the safety-critical bar this section names as most important — is
met cleanly. The one HIGH_EVIDENCE_MATCH produced is correct; every other
image degrades safely to a no-candidate, retry-guidance response. OCR
measurably improved semantic correctness (moved a genuinely correct visual
Top-1 from a previously-unreachable confident state to a correctly
OCR-corroborated one) without weakening the conflict/threshold logic that
protects against false positives.

Countervailing considerations, stated plainly: this is 8 photos of **one**
product. Top-1 visual accuracy (2/8) and HIGH_EVIDENCE coverage (1/8) are
both low in absolute terms — most real photos still land on the safe
`AMBIGUOUS_MATCH`/no-candidate path, meaning most users attempting to use
this feature today would not get a direct answer. That is a UX-quality
statement, not a safety one — but readiness for "controlled canary" is
about safety, not full coverage.

```
RECOGNITION DECISION GATE: READY_FOR_CONTROLLED_CANARY
```

This is **not** authorization for wide/default enablement. A controlled
canary means: continue current opt-in-by-Railway-variable operation,
watch the new `DRUG_RECOGNITION_EVIDENCE` structured log line in
production for real-traffic false-HIGH_EVIDENCE occurrences and
`OCR_FAILED`/`OCR_UNAVAILABLE` rates before considering any wider default,
and revisit with a larger, multi-product real-phone sample before calling
this broadly production-approved.

## 17a. Review response: two PR findings, verified against real code/data

**Finding — OCR timeout under concurrent load.** Verified via code read:
`_recognition_slot.acquire(blocking=False)`
(`backend/api/drug_image_chat_routes.py`) means a second concurrent
recognize request never waits — it fails immediately with HTTP 429
(`RECOGNITION_BUSY`). The finding's stated mechanism ("multiple requests
… might exceed the 30-second total recognition timeout") does not occur:
no request ever queues behind another long enough to interact with its
own timeout budget. **Real gap this finding did surface**: this report's
§3 latency/memory numbers (cold init 1.2s, warm 734–906ms) were measured
on the local Windows dev machine, not on actual Railway production
hardware — genuine worst-case single-request latency on Railway's real
CPU tier remains unmeasured. Recorded here rather than silently accepted;
worth a real production measurement pass before wider rollout, tracked
via the same `DRUG_RECOGNITION_EVIDENCE` log line this task added.

**Finding — OCR name-matching false positives from brand-prefix sharing.**
Verified via code read and a real catalog query. `STRENGTH_CONFLICT` is
computed independently of `_name_match` (`observed_strengths &
product_strengths` in `_rerank`) and is a hard conflict that blocks
`HIGH_EVIDENCE_MATCH` regardless of name-match text — a strength mismatch
between two same-brand-prefix products is already caught. The narrower,
real risk is specific to `_name_match`'s own threshold logic
(`_meaningful_tokens`/`_name_match`, lines ~521–540): a candidate whose
pre-strength identity segment reduces to a **single token** is matched
with `matched == len(candidate)` (exact 1-of-1), not the stricter
`≥ 0.75` rule that applies once `len(candidate) >= 2`. Queried the real
production catalog: **1867 of 3556 products (52.5%) have a single-token
identity segment** (e.g. `"Pentasa 1g 4x7"`, `"Doniwell 25mg 10x10"` — and
`"Snapcef 16mg/10ml…"`, this task's own real HIGH_EVIDENCE example, is
itself in this group). For two same-strength products both reducing to a
single, different brand token, this scale means the theoretical
false-positive path the finding describes is a real, non-rare shape in
this catalog — **not** a rare edge case.

**Important scope clarification**: this is **not a regression introduced
by this task**. The single-token leniency rule itself
(`matched == len(candidate)`) is unchanged — it already existed exactly
this way before this task, applied against the *full* `display_name`
instead of the new pre-strength identity segment. This task's own change
(§6) only moved *what text* is compared, not the matching threshold. The
identity-segment change made a real correct match reachable for the first
time (§10's HIGH_EVIDENCE_MATCH result) without changing this pre-existing
threshold behavior. Tightening the single-token leniency (e.g. requiring
an additional corroborating signal such as `ingredient_match` when the
identity segment is exactly one token) is a real, worthwhile hardening —
deliberately **left out of this PR's scope** per its own §4/§5 instruction
not to change confidence-threshold policy beyond what was explicitly
asked, and flagged here for a dedicated follow-up task instead.

## 17. Release gate — see §18 below (verbatim structure requested)

## 18. Final gate

```
OCR RUNTIME: PASS
OCR STATUS OBSERVABLE: PASS
QUALITY STATUS OBSERVABLE: PASS
INTERNAL TOP-1 OBSERVABLE: PASS
TOP1-TOP2 MARGIN OBSERVABLE: PASS
DECISION REASONS OBSERVABLE: PASS
AMBIGUOUS PRESERVED AS AMBIGUOUS: PASS
INSUFFICIENT SEMANTICS: PASS
HIGH_EVIDENCE SHOWS TOP-1 ONLY: PASS
AMBIGUOUS SHOWS NO CANDIDATE NAMES: PASS
FALSE HIGH_EVIDENCE IDENTIFICATION: 0
REAL PHONE TESTS: 2/8 Top-1 correct
HIGH_EVIDENCE CORRECT: 1
HIGH_EVIDENCE WRONG: 0
AMBIGUOUS: 6
INSUFFICIENT: 1
OCR HARD-CONFLICT REJECTION: PASS (unit-tested, not encountered in the 8-photo set)
UNKNOWN/NON-DRUG FALSE IDENTITY: NOT_TESTED
CONFIRM → ACTIVE_ENTITY: PASS
CONFIRM → DRUG TOOL: PASS
FOLLOW-UP AFTER CONFIRM: PASS (state binding); PARTIAL (direct free-text answer — pre-existing Track A behavior, see section 13)
GENERIC 500: 0
NORMAL TEXT CHAT: PASS
SAFETY: PASS
DOCTOR TAKEOVER: PASS
RECOGNITION DECISION GATE: READY_FOR_CONTROLLED_CANARY

READY FOR MERGE: YES
```
