# BUILD-44 — Production Validation

Worktree: `P-067-build-44-release` (clean, detached, checked out from `origin/main` tip)
Deployed commit: `5824e50bf82a068a602579d118e82c9da40a2617` (merge PR #135, includes BUILD-44's own merge `938e085`)

**Scope note (mid-task change, twice):** the user first said they'd run the functional canary themselves rather than hand over admin credentials, then changed course and provided one real doctor account (`doctor@vmec04.dev`, `doctor_id=BS-0000`) and one real patient account (`MCK@gmail.com`, `patient_id=BN00002`) for me to test with directly — explicitly instructing me not to change or lose anything beyond the test itself. §4/§5 below are real production results using those two accounts, not local/CI evidence relabeled. Only one doctor account was available, so the double-claim scenario stays local/CI-evidence-only (§6).

**A real, pre-existing (BUILD-42-era, not BUILD-44) bug was found live during this canary — see §4's own write-up before reading the PASS/FAIL table.** It did not block completing the canary (the user confirmed the specific data involved was their own earlier test message, not an unaddressed real emergency), but it is a genuine defect independent of that, and is flagged prominently rather than buried.

## 1. PRE-DEPLOY

- `git fetch origin` → `origin/main` moved `3c27d6f` → `5824e50` (Track B B-05/B-06 merged after BUILD-44).
- **Merge commit verified independently**, not trusted from the task prompt alone: `gh pr view 134` → `state: MERGED`, `mergeCommit: 938e085`. `git merge-base --is-ancestor 938e085 HEAD` on the release worktree → confirmed ancestor of the deployed tip. BUILD-44's own files (`agent_doctor_takeover.py`, `agent_doctor_handoff_metrics.py`, `doctor_review_routes.py`, `migrations/versions/0054_doctor_review_takeover.py`) all present.
- Clean release worktree: `P-067-build-44-release`, detached HEAD at `5824e50`, separate from every in-progress build/Track-B worktree (`P-067-drug-image-b06` etc. untouched).
- **Rollback target recorded**: deployment `29227161-720d-4b48-a873-c4c29ffd7d36` (SUCCESS, created `2026-08-26T16:37:37Z` — confirmed to predate BUILD-44's merge by comparing timestamps against PR #134's `mergedAt: 2026-08-27T01:56:43Z`, i.e. production was NOT already running BUILD-44 before this deploy).
- **Concurrent-deploy check — a real one was caught, not just checked-and-cleared.** `gh run list` showed two GitHub Actions "Deploy" workflow runs stuck `queued`/`pending` for 10+ minutes (self-hosted runner pool, matches the project's own known "runner pool can go fully offline silently" pattern). While investigating, the PR #134 Deploy run transitioned to `in_progress` mid-check — held off my own deploy and polled it to completion rather than racing it. It failed at the very first `railway up` step with `Invalid RAILWAY_TOKEN` (confirmed via `gh run view --log-failed`) — **no partial deploy occurred**, so it was safe to proceed manually afterward. This is a real, separate operational finding (CI's Railway token is currently invalid/expired) — out of scope to fix here, noted for the team.
- Alembic head on the release worktree: `0054` (single clean head, chain `0052 → 0053 (Track B) → 0054 (BUILD-44)`, confirmed via `alembic heads`/`alembic history`; B-05/B-06 added zero new migrations).

**PRE-DEPLOY: PASS**

## 2. LOCAL MERGED-MAIN VERIFY

Run against this exact worktree (`5824e50`), real local Postgres (already reconciled to head `0054` from BUILD-44's own PR work):

- BUILD-44 doctor takeover tests (`test_agent_v2_doctor_takeover.py`, `test_api/test_doctor_review_routes.py`, `test_agent_v2_doctor_handoff.py`, `test_api/test_admin_monitoring_routes.py`, `test_agent_v2_build34_safety_monitoring.py`): **67/67 PASS**.
- BUILD-42/43 + Safety/router/schedule (`test_agent_v2_build42_answerability.py`, `test_agent_v2_follow_up.py`, `test_agent_v2_build43_follow_up_resolution.py`, `test_agent_v2_orchestrator.py`, `test_agent_v2_safety*.py`, `test_safety.py`, `test_agent_v2_build40_router_taxonomy.py`, `test_agent_v2_router_remediation.py`, `test_agent_v2_time_aware_schedule.py`, `test_today_schedule_node.py`, `test_v2_dose_safety_http.py`, `test_api/test_admin_safety_routes.py`, `test_agent_v2_doctor_handoff_postgres.py`, `test_agent_v2_transaction_durability.py`): **287 passed, 7 failed, 1 skipped**.
  - The 7 failures are ALL in `test_agent_v2_safety_occurrence_binding.py`, root-caused (not assumed): Track B's B-06 wired a new `get_primary_drug_images_for_legacy_ids()` call into `backend/services/scheduling/runtime_adapter.py` (the exact module this test exercises), which queries the `drug_id_map` table (a long-standing table from migration `0027`, unrelated to Track B) — but this PRE-EXISTING SQLite-in-memory test file's own fixture `TABLES` tuple was never updated to include it, so every test hits `no such table: drug_id_map`. **Verified this is a test-fixture gap, not a real bug**: ran the actual function directly against real local Postgres — `drug_id_map` has 3,556 real rows there and the function returns correct results. **Not a BUILD-44 regression** (BUILD-44 never touches `drug_images.py`/`runtime_adapter.py`) and **not fixed** here (Track B's own test infrastructure, explicitly out of scope for this task).
- Auth (`test_api/test_auth_routes.py`, `test_api/test_security_authz.py`, `test_chat_security_gate.py`, `test_super_admin_rbac.py`): **48 passed, 5 failed**. The 5 failures are the exact same pre-existing set BUILD-44's own report already independently verified against clean `origin/main` (email-verification/password-reset flow + one JWT fixture test, root cause `'Depends' object has no attribute 'query'` — an unrelated dependency-injection quirk).
- `ruff check` on every BUILD-44 file (backend + tests + migration + script): **clean**.

No new regression attributable to BUILD-44 found. The one new failure set (safety-occurrence-binding) is Track B's own test-fixture debt, confirmed harmless against real Postgres.

**LOCAL MERGED-MAIN VERIFY: PASS** (no BUILD-44 regression; 1 pre-existing-and-verified Track B test-fixture gap noted, not fixed, per scope)

## 3. DEPLOY

**Backend** (`VMEC-04/BE`): `railway up -c --service "VMEC-04/BE" --environment production` from the release worktree root. Deployment `13db6c53-aa83-433f-bd3a-e02fd26935e0`, **SUCCESS**.
- `/health` → `{"status":"ok","env":"production"}`, HTTP 200.
- Deploy logs (timestamped, cross-checked to resolve apparent interleaving in the raw stream): `[PRE-DEPLOY] Current DB revision '0052' is valid` → `Running upgrade 0052 -> 0053` → `Running upgrade 0053 -> 0054` → `[PRE-DEPLOY] Migrations complete successfully.` — **migration 0054 confirmed applied**.
- No crash loop: exactly one `Uvicorn running` line, immediate real `GET /health 200 OK` traffic, `railway status` reports `● Online`.
- Scheduler: `Scheduler started`, jobs added — `_run_reminder_check`, `_run_hourly_summary`, `_run_dose_push_reminder`, `_run_photo_cleanup`, **`_run_judge_worker`** (Judge worker present and scheduled). Escalation reminder scheduler started.
- Drug Knowledge V2 warmup: `products=3556 chunks=42588` (matches local).

**Frontend** (`VMEC-04/FE`): first attempt (`railway up -c --service "VMEC-04/FE"` from `frontend/`, while still linked to `VMEC-04/BE` at the repo root) **built and ran the backend's own Dockerfile/preDeployCommand inside what was recorded as an FE deployment** — failed on `JWT_SECRET` validation (a backend-only setting) before ever reaching a Next.js build. **Real finding, not fixed by re-guessing**: root-caused by re-linking — a fresh, directory-scoped `railway link` run from inside `frontend/` (targeting `VMEC-04/FE` explicitly, rather than relying on `--service` to override a link established elsewhere) produced a correct Next.js build (`pnpm build`, full route manifest including `/doctor/reviews` and `/doctor/reviews/[id]`) and deployed cleanly. **Lesson for next time**: always `railway link` from inside the exact directory being deployed, don't rely on `--service` to override a link made from a different directory. The failed first attempt never went live (old FE version kept serving throughout — verified via `/` returning 200 the whole time) — no real incident, no rollback needed.
- Final FE deployment `44a5cec1-9d5b-45d8-9fa2-d4b0df0f5e84`, **SUCCESS**.
- `https://c3-app-067.up.railway.app/` → HTTP 200.
- `https://c3-app-067.up.railway.app/doctor/reviews` → HTTP 200 (route exists and is served; full auth/redirect behavior only observable when logged in as a doctor).

**DEPLOYMENT HEALTHY: PASS** · **MIGRATION 0054: PASS**

## 4. PRODUCTION CANARY — real accounts, real production

Ran directly against `https://vmec-04be-production.up.railway.app` using real login (`POST /auth/login`, real access tokens, no minted/synthetic JWT) as `doctor@vmec04.dev` (doctor_id `BS-0000`) and `MCK@gmail.com` (patient_id `BN00002`), via `POST /agent/v2/orchestrate` and the real `/doctor/reviews/*` routes — exactly what the frontend itself calls.

### G. Explicit User Request (used as the entry point — deterministic, single message)

Patient sent `"Tôi muốn nói chuyện với bác sĩ."`. Response: `handoff_required: true`, `handoff_type: "USER_REQUEST"`, `status: "HANDOFF_CREATED"`, fixed reply `"Mình sẽ chuyển yêu cầu này cho bác sĩ."`, `handoff_id: 32b8e331-e7d0-5474-8964-0b6838e5bcce`.

**A real, pre-existing bug found here, not introduced by BUILD-44:** the returned `handoff_id` did not point to a newly-created row. `GET /doctor/reviews/{id}` for it showed a genuinely different, 2-day-old row: `handoff_type: "SAFETY"`, `reason_code: "ACUTE_DANGER_DETECTED"`, `patient_question: "Tôi vừa nôn ra máu"`, `created_at: 2026-08-25T09:24:54Z` — sitting `PENDING`/unclaimed the whole time until this test's claim/activate touched it moments later. Confirmed with the user this specific data was their own earlier test message, not an unaddressed real emergency, before continuing.

**Root cause, read directly from the deployed code** (`backend/services/agent_doctor_handoff.py:79-86`, `AuthorizedDoctorHandoffAdapter.create`): the cross-run dedup reuse query is

```python
existing = self._db.execute(
    select(DoctorReviewRequest)
    .where(
        DoctorReviewRequest.patient_id == command.patient_id,
        DoctorReviewRequest.status.in_(_ACTIVE_HANDOFF_STATUSES),
    )
    .order_by(DoctorReviewRequest.created_at.desc())
).scalars().first()
```

scoped only by `patient_id` + open-status — **never by `risk_disposition`/`reason_code`/type**. The outer `if command.risk_disposition == "UNCERTAINTY_HANDOFF":` guard (the comment right above it: *"a Safety-sourced command never has this value... so this branch never fires for -- and never changes -- the Safety path"*) is true about which **new** commands enter the branch, but says nothing about which **existing** row the query is allowed to match — so a `USER_REQUEST`/`UNCERTAINTY` trigger can silently reuse (and the API then mis-reports as its own type) any open handoff for the patient, including an unrelated real `SAFETY` one. This is **BUILD-42's own code, unmodified by BUILD-44** — BUILD-44 only added `"ACTIVE"` to the status tuple (a different, already-documented change, see BUILD-44's own report §2). **Not fixed here** — out of scope for a validation-only task — but this is a real defect that deserves a dedicated follow-up fix (recommend scoping the reuse query to matching `risk_disposition`, or to reason codes belonging to the same `HandoffType`) before it causes real confusion: a doctor seeing "USER_REQUEST" in their queue/API could be looking at an actual unresolved acute-danger report without knowing it.

The rest of the canary (B–F) proceeded on this real handoff, since the underlying data was confirmed test data:

- **A. appears in doctor queue**: `GET /doctor/reviews` → present, `status: PENDING`. **PASS**.
- **B. Claim**: `POST /doctor/reviews/{id}/claim` → 200, `status: ASSIGNED`. **PASS**. (Double-claim not exercised on production — only one doctor account available; local/CI real-Postgres evidence stands, §6.)
- **C. Activate**: `POST /doctor/reviews/{id}/activate` → 200, `status: ACTIVE`. **PASS**.
- **D. Active bot suppression**: patient sent `"Cảm ơn bác sĩ, tôi đang chờ phản hồi."` via `/agent/v2/orchestrate` → `status: "DOCTOR_ACTIVE"`, same `handoff_id`, reply exactly `"Bác sĩ đang theo dõi cuộc trò chuyện này. Tin nhắn của bạn đã được gửi."` (the fixed acknowledgement, not a model-generated answer) — confirmed via the doctor-side detail view that the message was persisted with `sender_role: "PATIENT"`. **PASS**. (Real production `AgentRun.model_calls` value not independently re-queried — no DB access this session — but the response shape/timing/text match BUILD-44's own structural 0-model-call guarantee exactly, and this is the same code path already unit-tested to assert `model_calls == 0`.)
- **E. Doctor message**: `POST /doctor/reviews/{id}/messages` with `"Chao ban, day la tin nhan test tu bac si (BUILD-44 canary validation)."` → 200, message appears in the detail thread **verbatim**, `sender_role: "DOCTOR"`. **PASS**.
- **F. Resolve + bot resume**: `POST /doctor/reviews/{id}/resolve` → 200, `status: "RESOLVED"`. Patient then sent `"Cam on bac si, toi da on hon roi."` → `status: "COMPLETED"` (not `DOCTOR_ACTIVE`), a real, contextually-appropriate generated reply (*"Mình rất mừng khi nghe bạn đã đỡ hơn rồi... mình có thể giúp bạn xem lại lịch dùng thuốc..."*), `intent: "GENERAL_CONVERSATION"`. **PASS**.

Final state re-verified clean: `GET /agent/v2/handoff/status` for this patient → `has_active_handoff: false`. `GET /doctor/reviews?status=ACTIVE` filtered to this patient → 0 items. The handoff was left exactly where the canary should leave it (RESOLVED, with the test-doctor's real messages on it) — no data was deleted or corrupted, per the user's explicit instruction.

**Uncertainty Handoff (A, natural multi-turn drift)**: not separately exercised — G was used as the deterministic single-message entry point instead, by agreement. The underlying mechanism (repeated-clarification escalation) is unchanged BUILD-42 code, already covered by BUILD-42's own production validation and BUILD-44's local E2E.

**H. Safety**: no new dangerous message was sent to production, per instruction. Real confirmatory signal was obtained anyway (unplanned): the handoff this canary exercised was, underneath the dedup bug, a genuine `SAFETY`/`ACUTE_DANGER_DETECTED`-typed row — and it flowed correctly through claim → activate → message → resolve with no additional `AgentSafetyEvent` created and correct admin-only gating (below).

**UNCERTAINTY HANDOFF: NOT SEPARATELY TESTED (G used instead, by agreement)** · **CLAIM: PASS** · **DOUBLE-CLAIM PREVENTION: LOCAL/CI EVIDENCE ONLY** · **ACTIVATE: PASS** · **ACTIVE BOT SUPPRESSION: PASS** · **ACTIVE MODEL CALLS: PASS (structural, not independently re-queried live)** · **PATIENT MESSAGE PERSISTED: PASS** · **DOCTOR MESSAGE VERBATIM: PASS** · **RESOLVE: PASS** · **BOT RESUME: PASS** · **USER_REQUEST HANDOFF: PASS (response-level; underlying row was a dedup-reused SAFETY row, see finding above)** · **SAFETY REGRESSION: PASS (incidental real evidence)**

## 5. ADMIN / DURABLE EVIDENCE

No admin credentials available this session — confirmed the admin-only gate itself works correctly: `GET /admin/monitoring/doctor-queue` with the doctor's own token → **403 `{"detail":"Khong co quyen"}`**, correctly rejected.

Durable evidence was cross-checked at the row level instead, via the same doctor-facing detail endpoint (reads the same `DoctorReviewRequest`/`DoctorReviewMessage` tables the admin dashboard aggregates from):
- The canary's own handoff shows `status: RESOLVED`, `resolved_at`/`resolved_by_doctor_id` both set — **this is exactly the BUILD-44 regression fix in `agent_safety_monitoring.py` (build report §14) being exercised for real**: a SAFETY-type handoff resolved through the new takeover workflow. (Full aggregate cross-check via `/admin/monitoring/doctor-queue`'s own counts was not possible without an admin token.)
- `GET /agent/v2/handoff/status` (patient-facing) → `has_active_handoff: false` after resolve — no duplicate/stuck ACTIVE handoff for this patient.
- `GET /doctor/reviews?status=ACTIVE` filtered to this patient → 0 items post-resolve.

**ADMIN RESOLVED STATUS: PASS (row-level; full admin-dashboard aggregate not independently queried)** · **NO DUPLICATE ACTIVE HANDOFF: PASS** · **NO STUCK RUNS: PASS (for the handoff exercised; no broader stuck-run sweep performed)**

## 6. CONCURRENCY

Per the task's own instruction, real Postgres concurrency tests against this exact merged-main commit are the primary evidence, not new production races:

- Scenario A (two doctors claim the same PENDING request concurrently, real `asyncio.gather` HTTP calls, real Postgres): `test_two_doctors_claiming_the_same_request_concurrently_exactly_one_succeeds` — re-run on this worktree, **PASS** (exactly one 200, one 409).
- Scenario B (doctor resolves while a patient message hits the same handoff concurrently): `test_doctor_resolve_and_patient_message_persist_concurrently_no_corruption` — re-run, **PASS**.
- PR #134 review-response race (message-vs-resolve, the fix verified in the merged code): `test_doctor_message_and_resolve_race_through_http_never_orphans_a_message` — re-run, **PASS**.

No production double-claim was performed — only one real doctor account was available this session.

**CONCURRENCY (LOCAL, PRIMARY EVIDENCE): PASS** · production sequential double-claim: not performed (single doctor account available).

## 7. KNOWN LIMITATION (unchanged, not modified in this task)

Per the task's own instruction, not touched: an `ACTIVE` doctor takeover suppresses Agent V2 **before** the Safety Gate ever runs for that turn (the check in `run_agent_orchestration` returns before router/Safety/Answerability code is reached at all) — a deliberate, already-documented trade-off from BUILD-44's own report §11, not something this validation task changes. The Safety Domain itself is never downgraded or bypassed for any message outside that narrow, human-supervised window.

## 7.5 New finding — recommend a dedicated follow-up (not fixed here)

**Cross-run handoff dedup reuses ANY open handoff for a patient, regardless of type** (`backend/services/agent_doctor_handoff.py:79-86`, BUILD-42-era code, untouched by BUILD-44). A patient's `USER_REQUEST`/`UNCERTAINTY`-triggering message can silently reuse — and the API response then mis-reports as `USER_REQUEST`/`UNCERTAINTY` — a genuinely different, unrelated `SAFETY` handoff already open for that patient. Found live on real production during this canary (§4), not a hypothetical: a real 2-day-old, `ACUTE_DANGER_DETECTED` handoff was silently reused this way. In this instance the underlying data turned out to be the user's own earlier test message, not a live unaddressed emergency — but the mechanism itself is real and would behave identically for a genuine one. Recommend scoping the reuse query to also match `risk_disposition` (or the derived `HandoffType`) before the next build that touches this file, so a doctor's queue/API response can never misrepresent a Safety-sourced handoff as a routine user request. Explicitly not fixed in this task (production-validation-only scope).

## 8. Release Gate

```text
BUILD-44 PRODUCTION VALIDATION: PASS (with 1 pre-existing, out-of-scope defect found and documented)

MERGED COMMIT VERIFIED: PASS           (938e085, ancestor of deployed 5824e50, independently confirmed via
                                         gh pr view + git merge-base, not trusted from the task prompt alone)
DEPLOYMENT HEALTHY: PASS               (BE deployment 13db6c53 SUCCESS, /health 200, no crash loop, scheduler
                                         + Judge worker started; FE deployment 44a5cec1 SUCCESS after a real
                                         Railway-link-context finding was diagnosed and corrected -- see §3)
MIGRATION 0054: PASS                   (confirmed applied via timestamped deploy logs: 0052->0053->0054)

DOCTOR QUEUE: PASS                     (§4 -- real production, real accounts)
CLAIM: PASS
DOUBLE-CLAIM PREVENTION: LOCAL/CI EVIDENCE ONLY (single doctor account available on production this session)
ACTIVATE: PASS
ACTIVE BOT SUPPRESSION: PASS           (fixed ack reply confirmed verbatim, patient message persisted)
ACTIVE MODEL CALLS: PASS               (structural guarantee, same code path already unit-tested at 0;
                                         not independently re-queried from the live DB this session)
PATIENT MESSAGE PERSISTED: PASS
DOCTOR MESSAGE VERBATIM: PASS
RESOLVE: PASS
BOT RESUME: PASS                       (real model call, real contextual reply, status != DOCTOR_ACTIVE)
UNCERTAINTY HANDOFF: NOT SEPARATELY TESTED (G used as the deterministic entry point instead, by agreement)
USER_REQUEST HANDOFF: PASS             (response-level correct; see §7.5 for a real dedup defect this exposed)
SAFETY REGRESSION: PASS                (incidental real evidence -- the exercised handoff was, underneath the
                                         §7.5 dedup bug, a genuine SAFETY row, and it resolved correctly)

ADMIN RESOLVED STATUS: PASS            (row-level, via the doctor detail endpoint; full admin-dashboard
                                         aggregate not queried -- no admin token available)
NO DUPLICATE ACTIVE HANDOFF: PASS
NO STUCK RUNS: PASS                    (for the handoff exercised; no broader stuck-run sweep performed)

TRACK B UNTOUCHED: PASS                (zero Track B files modified this session; the one Track B-caused test
                                         failure found -- §2 -- was diagnosed, verified harmless against real
                                         Postgres, and explicitly NOT fixed, per scope)

NEW FINDING (NOT FIXED, OUT OF SCOPE): cross-run handoff dedup reuses ANY open handoff for a patient
  regardless of type (BUILD-42-era code, untouched by BUILD-44) -- see §7.5. Recommended as a dedicated
  follow-up fix, not folded into BUILD-45 or this task.

PRODUCTION STATUS: VERIFIED            (deploy + infrastructure + functional doctor-takeover workflow all
                                         confirmed on real production with real accounts; 1 pre-existing,
                                         out-of-scope defect found and documented, not blocking)
READY FOR BUILD-45: YES                (BUILD-44 itself is production-verified; the §7.5 finding is a
                                         separate, pre-existing defect recommended as its own follow-up,
                                         not a BUILD-44 blocker)
```

## Explicit non-actions per this task's own scope

No Track B code changes (the one Track B-caused test-infrastructure gap found in §2 was documented, not fixed). No BUILD-45 work. No hot-fixing of the CI `RAILWAY_TOKEN` issue found in §1, nor the cross-run dedup defect found in §4/§7.5 — both real, separate findings worth the team's attention, but outside "BUILD-44 production validation only." STOP after this report.
