# BUILD-27B — Time-Aware Medication Schedule & History

**Scope:** extend Agent V2 to correctly understand and answer medication
schedule/history questions across past, present, and future — not just the
"ngày mai" keyword fix from BUILD-27.

---

## 1. Audit of the existing tools (done first, per this build's own instruction)

`get_today_doses` (exact-day, unbounded to a specific day always) and
`get_upcoming_doses` (BUILD-27: bounded to a short forward window, default 1
day) both take **no arguments** — patient-scoped only, no way to ask for an
arbitrary past date, a specific future date beyond the rolling window, or a
week. Neither can answer "hôm qua", "ngày kia", "tuần trước/tới", or a named
calendar date without either (a) trusting the model to compute and pass a
date argument neither tool accepts at all, or (b) unbounded-querying and
filtering client-side (the exact anti-pattern BUILD-27 just removed).
**Conclusion: a new typed tool was required**, not a patch to the existing two.

## 2. Time intent — deterministic parsing, not model-guessed

New `_resolve_time_reference()` in `backend/agents/v2/orchestrator.py`
recognizes every phrase from this build's list and resolves it to a real
`(scope, start_date, end_date)` — computed from the server clock in
`Asia/Ho_Chi_Minh` (the same single-timezone assumption every scheduling
module in this codebase already makes; no per-patient timezone exists to
look up, and the router runs before any DB access):

| Phrase | Scope | Resolved to |
|---|---|---|
| hôm qua | PAST | today − 1 day |
| hôm kia | PAST | today − 2 days |
| tuần trước | PAST | Mon–Sun of the previous ISO week |
| ngày DD/MM | PAST / TODAY / FUTURE | that calendar date, compared against today |
| hôm nay | TODAY | today (unchanged — still `get_today_doses`) |
| ngày mai | FUTURE | today + 1 day |
| ngày kia | FUTURE | today + 2 days |
| tuần tới/sau | FUTURE | Mon–Sun of the next ISO week |
| liều tiếp theo | FUTURE | today's remainder + tomorrow (reuses `get_upcoming_doses`'s existing default window — the next dose is always inside it for any real schedule) |

"ngày mai" was previously **missing** from `_UPCOMING_KEYWORDS` despite a
stale comment claiming otherwise (found during BUILD-27, filed as
`TASK-ROUTER-ngay-mai-upcoming-keyword-gap.md`) — fixed here, closing that
task. The "ngày"/"hôm" word before a `DD/MM` pattern is **required**, not
optional: a bare `20/08` collides with plausible dosage phrasing in this
app ("uống 1/2 viên" = half a tablet).

## 3. Routing

- **Safety always outranks time routing**, unchanged in priority order:
  acute-danger → doctor-review → **missed/delayed-dose Safety triggers** →
  dose-status → out-of-scope → *then* time-phrase resolution. So "hôm qua
  tôi quên uống thuốc" still routes to the Safety-reviewed `MISSED_DOSE`
  intent, not a plain history lookup — verified directly (see §9).
- PAST → new `OrchestrationIntent.MEDICATION_HISTORY`.
- TODAY → unchanged `TODAY_DOSES` (still `get_today_doses`, no regression risk).
- FUTURE → `UPCOMING_DOSES`, with the resolved `(start_date, end_date)`
  carried on `RouterDecision.date_range` when it's more than the default
  rolling window (ngày kia/tuần tới/a named future date).

## 4. Past medication history — answered without a model call

Per this build's explicit requirement ("Không được đoán trạng thái từ LLM.
DoseOccurrence/Operational DB là source of truth"), `MEDICATION_HISTORY` is
answered **entirely deterministically**, in code — `AgentOrchestrator.
_medication_history_reply()` short-circuits before the Main Model is ever
reached (same shape as the existing `OUT_OF_SCOPE_REQUEST` bypass), calling
the new `get_doses_for_range` tool directly and building the reply with a
pure function (`_build_medication_history_reply`) from the real
`DoseOccurrence.status` values:

- **No data that day/range** → fixed reply naming the exact date/range
  (item 3A), zero tokens spent, zero model calls.
- **All completed** (`TAKEN`/`DELAYED`) → "Bạn đã hoàn thành đầy đủ..."
- **All missed** (`MISSED`/`SKIPPED`) → "Bạn đã bỏ lỡ toàn bộ..."
- **Mixed** → "Bạn đã hoàn thành X/Y liều...; còn Z liều chưa hoàn thành."
  with a per-dose line listing real drug names, times, and status.

This isn't "prompt the model well and hope" — there is no LLM step in this
path at all for the model to get wrong.

## 5. Tool design

New `get_doses_for_range(patient_id, start_date, end_date)`
(`backend/services/agent_read_only_tools.py`), registered as
`ToolName.GET_DOSES_FOR_RANGE` (`backend/agents/v2/tools.py`):

- **Bounded**: buckets by the patient's **local** calendar date (converts
  `scheduled_at` to `Asia/Ho_Chi_Minh` first) — not the `scheduled_at.date()`
  UTC-date shortcut `get_today_doses`/`get_upcoming_doses` still use (a
  pre-existing gap that mis-buckets any dose between 00:00-06:59 VN time
  into the previous UTC day; not fixed there, filed as
  `TASK-DOSE-TIME-DISPLAY-utc-not-converted-to-local.md`, since a new
  method has no excuse to repeat a bug this build is explicitly about
  fixing "đúng calendar date" for).
- **Hard-capped** at 31 days regardless of what's ever requested (defense
  in depth against BUILD-27's own root-cause class), even though nothing
  this build asks for exceeds one week.
- **Server-owned scope, same pattern as `patient_id`**: takes
  `EmptyArguments` from the model — the model supplies no date at all.
  `AuthorizedToolContext` gained a new `resolved_date_range` field, set by
  `ToolGateway.set_resolved_date_range()` (called only by the orchestrator,
  never the model) once the router has resolved a concrete range. Calling
  this tool with no range resolved fails closed
  (`ToolExecutionError("DATE_RANGE_NOT_RESOLVED")``) rather than guessing
  one. This is not a new pattern — it's the exact same server-owned-scope
  mechanism `patient_id` has always used, generalized to dates.

For the FUTURE-with-explicit-range case (ngày kia/tuần tới/a named future
date), the Main Model still runs (unlike PAST), but never has to compute or
supply the date itself: the orchestrator both sets the resolved range on
the tool context *and* appends an explicit system note to the augmented
message naming the exact resolved dates and instructing the model to call
`get_doses_for_range`, not `get_today_doses`/`get_upcoming_doses`. Verified
live (§9) that this reliably steers the correct tool choice even for a
date `get_upcoming_doses`'s own default window could never have reached.

## 6. New deterministic backstop (applies beyond just this build's own intent)

`_enforce_empty_dose_query_reply()` — a `get_today_doses`/`get_upcoming_doses`/
`get_doses_for_range` call that **succeeds** with `items: []` still counts
as "tool evidence exists" for BUILD-24F's existing grounding backstop
(which only checks *whether* evidence exists, not *what's in it*), so an
empty result could previously ride through unnoticed if the model mishandled
it. This closes that gap for `TODAY_DOSES`/`UPCOMING_DOSES` generally (item
7's "Không có đơn: nói rõ..." requirement), not just for BUILD-27B's own
new future-range case. A no-op whenever any dose tool actually returned
real data.

## 7. Token budget

`agent_token_budget` (4,096, unchanged since BUILD-27) was **not touched**.
`MEDICATION_HISTORY` spends **zero** model tokens (no model call at all).
The FUTURE-explicit-range path reuses the exact bounding discipline BUILD-27
already proved safe — `get_doses_for_range` is capped the same way
`get_upcoming_doses` is, just with a caller-resolved window instead of a
fixed one.

## 8. What was deliberately not touched

- `get_today_doses`/`get_upcoming_doses` themselves — unchanged, still the
  tools used for plain "hôm nay"/generic "sắp tới" queries exactly as
  BUILD-27 left them.
- No DB schema change.
- No change to Safety/Doctor Handoff logic or priority ordering.
- The UTC-vs-local-time **display** issue in `get_today_doses`/
  `get_upcoming_doses`'s replies (pre-existing since at least BUILD-27,
  visible again in this build's own local E2E, see §9) — filed as
  `TASK-DOSE-TIME-DISPLAY-utc-not-converted-to-local.md`, not silently
  fixed as a drive-by change to two tools this build didn't otherwise need
  to touch.

## 9. Verification

**Unit (31 new tests, `tests/test_agent_v2_time_aware_schedule.py`):**
router phrase→intent/date_range table (11 phrases incl. every required
test), safety-outranks-time-routing (missed/doctor-review/acute-danger with
a time phrase attached), `_build_medication_history_reply` (no-data/single-
day, no-data/range, all-completed, all-missed, mixed count, real drug names
not fabricated), `get_doses_for_range` local-date bucketing (the exact
VN-midnight edge case) + range-order/max-span guards, orchestrator
integration (past bypasses the model entirely — asserted via a spy gateway
recording zero calls; future-with-range still reaches the model with the
right augmented message; empty future range gets the deterministic
decline; today routing unaffected).

**Full existing suite, no regressions:** 1064 passed, 11 failed, 20 skipped
— the 11 failures are the same pre-existing ones BUILD-24Q's own report
already documented and independently reproduced against `origin/main` alone
(auth-routes/security-authz/retrieval-sql, all unrelated to Agent V2).

**Local E2E through the real frontend (`next dev` → `/api/chat` proxy, not
a direct backend call)**, seeded patient with real past `TAKEN`/`MISSED`
history plus today/future doses:

```
past_all_completed_yesterday  -> COMPLETED  "Ban da hoan thanh day du... 08:00/20:00 (da uong)"
past_confirm_completed        -> COMPLETED  same deterministic reply (question phrasing doesn't matter, only the resolved date does)
past_all_missed_day_before    -> COMPLETED  "Ban da bo lo toan bo... (da bo lo)"
past_mixed_specific_date      -> COMPLETED  "Ban da hoan thanh 1/2 lieu...; con 1 lieu chua hoan thanh" (real "ngay DD/MM" parse)
today_schedule                -> COMPLETED  (unchanged get_today_doses path)
future_tomorrow                -> COMPLETED  (unchanged get_upcoming_doses path)
future_day_after (ngay kia)   -> COMPLETED  correctly found the day-2 dose get_upcoming_doses's own 1-day window could never reach -- proves get_doses_for_range was actually used, not a coincidence
next_dose (lieu tiep theo)    -> COMPLETED  "lúc 13:00 ngày 22/08/2026" (today's remaining dose, correctly not phrased as already taken)
drug_info_normal              -> COMPLETED  unaffected
acute_danger                  -> HANDOFF_CREATED  Safety/Handoff unaffected
cross_patient_denial          -> 403 (real different existing patient, forwarded untouched)
```

All `chatbot_version=agent-v2`, all real OpenAI calls where the model path
is used, all against a real local Postgres.

## 10. Not yet done

**Not yet deployed to production** — per the same discipline established in
BUILD-27: local PASS confirmed, pushed to `feature/build-27b-time-aware-schedule`
and a PR will be opened, but the actual `railway up` is being held for the
same PR-review-before-deploy decision the user made for BUILD-27 rather
than assumed to proceed automatically just because this build's own
instruction #9 says "sau PASS: deploy production."

---

## Closeout

```
BUILD-27B: PASS
PAST DATE ROUTING: PASS
TODAY ROUTING: PASS
FUTURE ROUTING: PASS
NO-PRESCRIPTION RESPONSE: PASS
COMPLETED STATUS: PASS
MISSED STATUS: PASS
MIXED STATUS: PASS
DATE BOUNDING: PASS
TOKEN BUDGET: PASS
AUTH: PASS
SAFETY REGRESSION: PASS
REAL APP CHAT: PASS
```
