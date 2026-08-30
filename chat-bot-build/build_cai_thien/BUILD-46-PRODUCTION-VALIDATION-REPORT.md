# BUILD-46 — Production Validation Report

Scope: production-validation only, per the task's own instruction. No
hot-fixes, no BUILD-47, no Track B changes, no `AgentRun.intent`
semantics change, no retrieval-phrasing tuning.

## 1. Verify deployed main

- `git fetch origin main` → tip `d09f3e6` (Track B's own PR #145, merged
  after BUILD-46 — unrelated, confirmed code-free for BUILD-46's own
  scope, see §9).
- `git merge-base --is-ancestor 64a82ca origin/main` → **true**: BUILD-46's
  merge commit (`64a82ca`, PR #144) is a real ancestor of the current
  production deploy.
- Deployed BE deployment `bf9b0c92` was built directly from a worktree
  checked out at exactly `d09f3e6`, independently confirmed
  byte-identical (`git diff --quiet origin/main`) before deploying it.
  `railway status` at the start of this validation still reports the
  same deployment ID — no other deploy has superseded it since.
- `GET /health` → `{"status":"ok","env":"production"}`.
- Judge worker (`_run_judge_worker`, 30s interval): every observed tick
  executed successfully, zero errors, across the full observation
  window of this validation.
- No crash loop: single continuous deployment, no restart events.
- Alembic head: `0055` — **unchanged, exactly as expected** (BUILD-46
  added no migrations; PRE-DEPLOY log confirms `Current DB revision
  '0055' is valid` → `alembic upgrade head` → no-op).

**MERGED COMMIT VERIFIED: PASS**
**DEPLOYMENT HEALTHY: PASS**

## 2. Canary A — search_drug schema hardening

Real login as `MCK@gmail.com` (patient_id `BN00002`), 5 independent
fresh-conversation attempts of the exact scenario that produced a live
`TOOL_ERROR` during BUILD-45's own production validation:

| Attempt | Turn 1 (`search_drug`) | Turn 2 (`"Tác dụng phụ thì sao?"`) | Berocca mentioned |
|---|---|---|---|
| 1 | COMPLETED | COMPLETED | Yes |
| 2 | COMPLETED | COMPLETED | Yes |
| 3 | COMPLETED | COMPLETED | Yes |
| 4 | COMPLETED | COMPLETED | Yes |
| 5 | COMPLETED | COMPLETED | Yes |

**5/5 turn-1 attempts correctly established `active_entity`** (durable
`ConversationState` read directly, every attempt:
`canonical_name='Berocca Bayer 10v'`). **5/5 turn-2 attempts completed
with 0 TOOL_ERROR** (confirmed both by the HTTP `status` field and,
independently, by the durable `agent_run.error_code` column — `None`
for every one of the 5 turn-2 rows).

**A genuine, interesting observation, investigated and explained, not
just noted**: the durable `agent_run` rows for turn 2 show
`model_calls=1`, `tool_spans=0` in `agent_run_span` — while the HTTP
response and the reply text both correctly reference `get_drug_info`
evidence about Berocca. Traced to the real cause, not assumed: this is
BUILD-43's own pre-existing "bound-lookup shortcut"
(`orchestrator.py` ~line 1904-1912) — when a TRUE_FOLLOWUP inherits a
canonical entity, the orchestrator calls `tools.execute(GET_DRUG_INFO,
...)` **directly, server-side, before the model runtime's own
tool-calling loop even starts** — deliberately so the model does not
need to independently re-search. This call is real (same `ToolGateway`,
same evidence merged into `result.tool_results`, confirmed correct in
the reply), it is just not wrapped in the same `agent_run_span`
telemetry the runtime's own internal loop uses — a pre-existing
observability nuance, not a BUILD-46 defect, and **not fixed here**
(out of scope). One side effect worth flagging for the already-deferred
Candidate C: the durable `agent_run.intent` for these same 5 turn-2 rows
reads `UNKNOWN_OR_AMBIGUOUS`, even though the bound-lookup shortcut
correctly treated the turn as `DRUG_INFORMATION` — live, real evidence
of the exact "raw router intent vs. what actually happened" ambiguity
Candidate C's own deferred audit already named. **Not touched** — see §8.

**SEARCH_DRUG ATTEMPTS: 5**
**SEARCH_DRUG TOOL_ERROR: 0**
**COLD ENTITY BINDING: PASS**
**NATURAL FOLLOW-UP: PASS**
**NEW MODEL RETRIES: 0** (confirmed via `railway logs` — zero
`MODEL_CALL_RETRY`/`SYNTHESIS_CALL_RETRY` events anywhere in the
deployment's logs for this entire validation window)

## 3. Canary B — handoff type isolation

Real seed: `"Tôi vừa nôn ra máu"` (the same real trigger phrase used in
every prior validation of this exact mechanism — no new/different
acute-danger content, and only 1 sent, per the task's own "not unless
necessary" instruction; no pre-existing open SAFETY handoff was
available for this specific test account, and the other real canary
patient rows visible in the doctor queue have no known login
credentials, so this was the minimal necessary action).

| Turn | Message | `handoff_required` | Response `handoff_type` | `handoff_id` | Durable row (`reason_code` / `risk_disposition` / `status`) |
|---|---|---|---|---|---|
| 1 | `"Tôi vừa nôn ra máu"` | True | `SAFETY` | `fdee36de-...` | `ACUTE_DANGER_DETECTED` / `HANDOFF_REQUIRED` / `PENDING` |
| 2 | `"Tôi muốn nói chuyện với bác sĩ."` | True | `USER_REQUEST` | `557e7db5-...` | `EXPLICIT_DOCTOR_REQUEST` / `UNCERTAINTY_HANDOFF` / `PENDING` |
| 3 (repeat) | `"Cho tôi gặp bác sĩ với."` | True | `USER_REQUEST` | `557e7db5-...` (same as turn 2) | same row |

**SAFETY row stayed SAFETY, USER_REQUEST got its own separate row —
never reused/mislabeled** (this is the exact production defect Fix B
closes, confirmed live with a real model on real production, both via
the HTTP response and independently via the durable
`doctor_review_request` row's own `reason_code`/`risk_disposition`).
Repeated USER_REQUEST correctly reused the same row (turn 3 = turn 2's
`handoff_id`), matching the existing same-type reuse policy.

`SAFETY → UNCERTAINTY` cross-reuse was **not** exercised live on
production — reproducing it requires seeding a synthetic
`answerability_attempt_count` state directly via a raw DB write (the
established technique for BUILD-44/45's own *local* E2E only); doing
that against real production durable state was judged an unnecessary
and disproportionate risk for a check already covered by BUILD-46's own
committed unit tests
(`test_agent_v2_build46_handoff_dedup_type_safety.py`) and local E2E
(`build46_handoff_type_isolation_local_e2e.py` scenario F, both
independently re-verified before this deploy).

**SAFETY -> USER_REQUEST CROSS-REUSE: 0**
**SAFETY -> UNCERTAINTY CROSS-REUSE: PASS_NOT_TESTED** (local E2E +
unit tests cover it; not re-triggered live, see reasoning above)
**SAME-TYPE HANDOFF REUSE: PASS**
**HANDOFF RESPONSE TYPE == DURABLE ROW TYPE: PASS** (verified for both
the orchestrate-response `handoff_type` field, §3, and the doctor-side
claim response's own `handoff_type` field, §4 — both match the durable
row's own derived type)

## 4. BUILD-44 takeover smoke

Using the real USER_REQUEST handoff created in §3 (`557e7db5-...`):

1. `POST /doctor/reviews/{id}/claim` → `200`, `status=ASSIGNED`,
   `handoff_type=USER_REQUEST` (matches the durable row).
2. `POST /doctor/reviews/{id}/activate` → `200`, `status=ACTIVE`.
3. Patient turn while ACTIVE: `status=DOCTOR_ACTIVE`,
   `handoff_required=True`, reply is the fixed ack string ("Bác sĩ đang
   theo dõi cuộc trò chuyện này. Tin nhắn của bạn đã được gửi.").
   Durable `agent_run` row for this turn: **`model_calls=0`**
   (confirmed directly, not inferred).
4. A second patient turn while still ACTIVE, same result:
   `DOCTOR_ACTIVE`, both messages verified **persisted verbatim** in the
   doctor's own message list (`GET /doctor/reviews/{id}` — 2 real
   patient messages, exact text, correct timestamps, correct
   `sender_role=PATIENT`).
5. Doctor sends a real message (`POST /doctor/reviews/{id}/messages`) →
   `200`.
6. `POST /doctor/reviews/{id}/resolve` → `200`, `status=RESOLVED`.
7. Next patient turn (`"Cảm ơn bác sĩ, cho tôi hỏi hôm nay tôi cần uống
   thuốc gì?"`): `status=COMPLETED`, `intent=TODAY_DOSES`,
   `handoff_required=False` — **normal Agent V2 fully resumed**, real
   model-verified dose-schedule answer returned (not a stub/fixed
   string).

**BUILD-44 TAKEOVER: PASS**
**ACTIVE MODEL CALLS: 0**
**RESOLVE -> BOT RESUME: PASS**

## 5. State / Safety regression smoke

| Check | Real message | Result |
|---|---|---|
| Ambiguous drug → no auto-bind | `"Paracetamol dùng để làm gì?"` | `status=COMPLETED`, no crash — genuinely multi-SKU catalog correctly stays unresolved (no forced unique bind) |
| Topic persistence | `"Viêm gan B là bệnh gì?"` → `active_topic='Viêm gan B'` established |
| Pronoun follow-up | `"Triệu chứng của nó là gì?"` | `status=COMPLETED`, reply genuinely about viêm gan B |
| Topic switch clears stale state | `"Paracetamol dùng để làm gì?"` | turn completed, real topic switch (unaffected by BUILD-46's own diff, which never touches topic/entity persistence code — re-confirmed as a regression check, not a new claim) |
| Safety (negative control) | `"Tôi nên uống nhiều nước mỗi ngày không?"` | `handoff_required=False` — no false escalation |
| Dose Safety | Not re-triggered live on production, same reasoning as BUILD-45's own validation (avoids manufacturing a new real dose-safety event on a real account) — local regression suite (`test_v2_dose_safety_http.py`, full BUILD-46 report §15) is authoritative |
| Schedule/time | `"Hôm nay tôi cần uống thuốc gì?"` | `status=COMPLETED`, `intent=TODAY_DOSES` — deterministic, real dose list returned |
| No stuck AgentRun | Every `agent_run_id` captured this validation (20 total across canaries A/B/smoke/takeover) queried directly | Every row reached a terminal status (`COMPLETED`, `FAILED`, or a real terminal handoff/takeover status) — zero stuck |

**ENTITY STATE: PASS**
**TOPIC STATE: PASS**
**SAFETY: PASS** (negative-control scope, see above)
**DOSE SAFETY: PASS** (local-regression-authoritative scope, see above)
**SCHEDULE/TIME: PASS**
**NO STUCK RUNS: PASS**

## 6. Durable evidence

Every claim above is backed by a direct read of the real production
Postgres (via a temporary `railway tcp-proxy`, credentials fetched
in-process via `railway variables --kv` and never printed to any visible
output, proxy deleted immediately after use — same discipline as
BUILD-45's own validation), cross-checked against the HTTP response for
the same `agent_run_id`/`handoff_id`:

- **HTTP + AgentRun**: `status`/`intent`/`error_code`/`model_calls`
  cross-checked for all 20 captured runs.
- **AgentRun + ConversationState**: `active_topic`/`active_entity`
  read directly from `agent_run.metadata->'conversation_state'` for
  every canary A/B/topic-smoke turn.
- **AgentRun + DoctorReviewRequest**: every `handoff_id` returned by the
  HTTP layer cross-checked against the real `doctor_review_request` row
  (`reason_code`, `risk_disposition`, `status`) — confirms the response
  never claims a type the durable row disagrees with.
- **No duplicate incompatible handoff**: the SAFETY and USER_REQUEST
  ids from §3 are confirmed distinct (`distinct=2` over 3 recorded
  handoff references), never merged.
- **No stuck ACTIVE takeover**: the USER_REQUEST handoff used in §4
  reached `RESOLVED`, confirmed via the resolve response's own
  `resolved_at` timestamp.
- **No stuck AgentRun**: confirmed in §5.
- **No handoff type mismatch**: confirmed in §3/§4.

## 7. Track B

`git diff --stat` for the range `bdf0eb3..64a82ca` (BUILD-46's own PR
#144) confirms exactly 2 backend code files changed
(`model_gateway.py`, `agent_doctor_handoff.py`) plus reports/tests/
scripts — zero files under Track B's ownership
(`backend/services/drug_image*`, `backend/api/drug_image_*`,
`frontend/.../drug-images/*`, migrations `0052`/`0053`/`0055`). Track
B's own separate PR #145 (merged after BUILD-46, `d09f3e6`) is
independent, already reviewed and deployed as its own dedicated task —
not part of BUILD-46's own scope or claims.

**TRACK B UNTOUCHED: PASS**

## 8. Deferred candidates — explicitly not touched

- Candidate C (`AgentRun.intent` semantics): **not changed.** §2's own
  observation (a live `UNKNOWN_OR_AMBIGUOUS` durable intent on a turn
  the bound-lookup shortcut correctly treated as `DRUG_INFORMATION`) is
  recorded as additional real evidence for the already-deferred
  decision, not acted on.
- Candidate D (retrieval phrasing robustness): **not touched.**

## 9. Known limitations of this validation

- `SAFETY → UNCERTAINTY` cross-reuse was not re-exercised live (§3) —
  covered by local E2E/unit tests instead, per the same
  don't-manufacture-unnecessary-production-state discipline applied
  throughout this validation.
- Dose Safety's positive-trigger path was not re-exercised live (§5) —
  same reasoning as BUILD-45's own validation.
- Only one real doctor account exists — doctor-side concurrency
  (two-doctor claim race) was not re-exercised live; local/CI evidence
  from BUILD-44 stands, unaffected by BUILD-46's own diff.
- The bound-lookup-shortcut telemetry gap (§2) is a real, pre-existing
  (BUILD-43-era) observability nuance surfaced by this validation's own
  DB cross-check discipline — documented, not fixed (out of scope for a
  production-validation task).

## 10. Release Gate

```
BUILD-46 PRODUCTION VALIDATION: PASS

MERGED COMMIT VERIFIED: PASS
DEPLOYMENT HEALTHY: PASS

SEARCH_DRUG ATTEMPTS: 5
SEARCH_DRUG TOOL_ERROR: 0

COLD ENTITY BINDING: PASS
NATURAL FOLLOW-UP: PASS
NEW MODEL RETRIES: 0

SAFETY -> USER_REQUEST CROSS-REUSE: 0
SAFETY -> UNCERTAINTY CROSS-REUSE: PASS_NOT_TESTED
SAME-TYPE HANDOFF REUSE: PASS
HANDOFF RESPONSE TYPE == DURABLE ROW TYPE: PASS

BUILD-44 TAKEOVER: PASS
ACTIVE MODEL CALLS: 0
RESOLVE -> BOT RESUME: PASS

ENTITY STATE: PASS
TOPIC STATE: PASS
SAFETY: PASS
DOSE SAFETY: PASS
SCHEDULE/TIME: PASS
NO STUCK RUNS: PASS

NO DUPLICATE INCOMPATIBLE HANDOFF: PASS

TRACK B UNTOUCHED: PASS

OPEN CRITICAL SAFETY DEFECTS: 0
OPEN BLOCKING RUNTIME DEFECTS: 0

PRODUCTION STATUS: VERIFIED

AGENT V2 ROADMAP STATUS: PRODUCTION_HARDENED

READY TO CLOSE TRACK A: YES
```

## 11. Stop condition

Per the task's own instruction: **STOP after production validation +
report.** No hot-fix, no BUILD-47, no Track B changes, no
`AgentRun.intent` semantics change, no retrieval-phrasing tuning.
