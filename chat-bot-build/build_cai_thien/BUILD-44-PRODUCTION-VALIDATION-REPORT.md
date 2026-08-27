# BUILD-44 — Production Validation

Worktree: `P-067-build-44-release` (clean, detached, checked out from `origin/main` tip)
Deployed commit: `5824e50bf82a068a602579d118e82c9da40a2617` (merge PR #135, includes BUILD-44's own merge `938e085`)

**Scope note (mid-task change):** the user chose to run the functional production canary walkthrough (§4) themselves rather than hand over admin credentials for me to create test doctor accounts. Everything through deploy + infrastructure verification (§1-3, §6's local half) was independently completed and verified by me against real production. §4/§5's functional/durable-evidence checks are marked **PENDING** below, not fabricated — this report will be updated once results are available, either from the user's own run or a follow-up session.

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

## 4. PRODUCTION CANARY — PENDING (user testing directly)

Not performed by me this session. The user opted to run scenarios A-H (uncertainty handoff → PENDING/queue, claim/double-claim, activate, active bot suppression, doctor message, resolve/bot-resume, explicit user request, Safety durable-evidence check) themselves on production, since it requires doctor-role test accounts and self-registration is deliberately restricted to `role="patient"` (`RegisterRequest.role: Literal["patient"]`, `backend/models/schemas.py` — doctor accounts require admin-created via `POST /accounts`, and I was not given admin credentials for this session).

What's already true and available for that testing, confirmed above: backend and frontend are both live at the exact merged-main commit, migration 0054 is applied, the doctor queue UI is reachable at `/doctor/reviews`, and every scenario A-H is already covered by real-Postgres, real-HTTP-route automated tests in BUILD-44's own test suite (§2 above, 67/67 passing on this exact commit) plus the local E2E script (`scripts/agent_v2/build44_doctor_takeover_local_e2e.py`, 32/32 checks, real model calls) run during BUILD-44's own development — this report does not repeat those as production-live evidence, since a local/CI pass is not the same claim as a live production observation.

**UNCERTAINTY HANDOFF: PENDING** · **CLAIM: PENDING** · **DOUBLE-CLAIM PREVENTION: PENDING** · **ACTIVATE: PENDING** · **ACTIVE BOT SUPPRESSION: PENDING** · **ACTIVE MODEL CALLS: PENDING** · **PATIENT MESSAGE PERSISTED: PENDING** · **DOCTOR MESSAGE VERBATIM: PENDING** · **RESOLVE: PENDING** · **BOT RESUME: PENDING** · **USER_REQUEST HANDOFF: PENDING** · **SAFETY REGRESSION: PENDING**

## 5. ADMIN / DURABLE EVIDENCE — PENDING

Depends on §4 producing real handoff rows to cross-check. Not performed. When §4 is done (by the user or in a follow-up), this section should verify via `GET /admin/monitoring/doctor-queue` + a direct DB read: PENDING/ASSIGNED/ACTIVE/RESOLVED counts match what was exercised, handoff-type breakdown (SAFETY/UNCERTAINTY/USER_REQUEST) is correct, the RESOLVED handoff from §4F shows as resolved (not stuck unresolved — this is the exact regression BUILD-44's own PR fixed in `agent_safety_monitoring.py`, §14 of the build report), no duplicate ACTIVE handoff for the same patient, no `AgentRun` stuck in a non-terminal status.

**ADMIN RESOLVED STATUS: PENDING** · **NO DUPLICATE ACTIVE HANDOFF: PENDING** · **NO STUCK RUNS: PENDING**

## 6. CONCURRENCY

Per the task's own instruction, real Postgres concurrency tests against this exact merged-main commit are the primary evidence, not new production races:

- Scenario A (two doctors claim the same PENDING request concurrently, real `asyncio.gather` HTTP calls, real Postgres): `test_two_doctors_claiming_the_same_request_concurrently_exactly_one_succeeds` — re-run on this worktree, **PASS** (exactly one 200, one 409).
- Scenario B (doctor resolves while a patient message hits the same handoff concurrently): `test_doctor_resolve_and_patient_message_persist_concurrently_no_corruption` — re-run, **PASS**.
- PR #134 review-response race (message-vs-resolve, the fix verified in the merged code): `test_doctor_message_and_resolve_race_through_http_never_orphans_a_message` — re-run, **PASS**.

No production double-claim was performed (would need the two doctor accounts from §4, not available this session).

**CONCURRENCY (LOCAL, PRIMARY EVIDENCE): PASS** · production sequential double-claim: not performed, deferred to §4.

## 7. KNOWN LIMITATION (unchanged, not modified in this task)

Per the task's own instruction, not touched: an `ACTIVE` doctor takeover suppresses Agent V2 **before** the Safety Gate ever runs for that turn (the check in `run_agent_orchestration` returns before router/Safety/Answerability code is reached at all) — a deliberate, already-documented trade-off from BUILD-44's own report §11, not something this validation task changes. The Safety Domain itself is never downgraded or bypassed for any message outside that narrow, human-supervised window.

## 8. Release Gate

```text
BUILD-44 PRODUCTION VALIDATION: PARTIAL

MERGED COMMIT VERIFIED: PASS           (938e085, ancestor of deployed 5824e50, independently confirmed via
                                         gh pr view + git merge-base, not trusted from the task prompt alone)
DEPLOYMENT HEALTHY: PASS               (BE deployment 13db6c53 SUCCESS, /health 200, no crash loop, scheduler
                                         + Judge worker started; FE deployment 44a5cec1 SUCCESS after a real
                                         Railway-link-context finding was diagnosed and corrected -- see §3)
MIGRATION 0054: PASS                   (confirmed applied via timestamped deploy logs: 0052->0053->0054)

DOCTOR QUEUE: PENDING                  (§4 -- user testing directly on production)
CLAIM: PENDING
DOUBLE-CLAIM PREVENTION: PENDING       (local real-Postgres equivalent PASS, §6; production not exercised)
ACTIVATE: PENDING
ACTIVE BOT SUPPRESSION: PENDING
ACTIVE MODEL CALLS: PENDING
PATIENT MESSAGE PERSISTED: PENDING
DOCTOR MESSAGE VERBATIM: PENDING
RESOLVE: PENDING
BOT RESUME: PENDING
UNCERTAINTY HANDOFF: PENDING
USER_REQUEST HANDOFF: PENDING
SAFETY REGRESSION: PENDING

ADMIN RESOLVED STATUS: PENDING
NO DUPLICATE ACTIVE HANDOFF: PENDING
NO STUCK RUNS: PENDING

TRACK B UNTOUCHED: PASS                (zero Track B files modified this session; the one Track B-caused test
                                         failure found -- §2 -- was diagnosed, verified harmless against real
                                         Postgres, and explicitly NOT fixed, per scope)

PRODUCTION STATUS: PARTIAL             (infrastructure/deploy layer fully verified independently; functional
                                         doctor-takeover behavior on live production not yet observed --
                                         pending the user's own canary run or a follow-up validation pass)
READY FOR BUILD-45: NO                 (pending §4/§5 completion)
```

## Explicit non-actions per this task's own scope

No Track B code changes (the one Track B-caused test-infrastructure gap found in §2 was documented, not fixed). No BUILD-45 work. No hot-fixing of the CI `RAILWAY_TOKEN` issue found in §1 (a real, separate operational finding worth the team's attention, but outside "BUILD-44 production validation only"). STOP after this report, pending §4/§5 results.
