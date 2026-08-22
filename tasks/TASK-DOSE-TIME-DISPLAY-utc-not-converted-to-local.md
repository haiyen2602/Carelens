# TASK: dose reply times shown in raw UTC, not patient-local (VN) time

**Found during:** BUILD-27B (time-aware medication schedule/history) local
E2E, real `/api/chat` calls. Pre-existing since at least BUILD-27 (its own
own report already shows the same artifact -- "Hôm nay bạn có 3 lần dùng
thuốc... - **00:00** ... - **05:00** ... - **12:00**" for doses actually
scheduled at 07:00/12:00/19:00 Vietnam time) -- not introduced by BUILD-27B
and not fixed here, since it's outside that build's scope (routing/date-
bounding/history-status accuracy, not display formatting for the two
already-existing tools this affects).

## The gap

`get_today_doses`/`get_upcoming_doses` (`backend/services/agent_read_only_tools.py`)
serialize `scheduled_at.isoformat()` as a UTC datetime string. Nothing in
`model_gateway.py`'s `synthesize_read_only` prompt tells the model to
convert this to `Asia/Ho_Chi_Minh` before displaying an hour to the
patient, and the model doesn't reliably self-convert. Live example (BUILD-
27B E2E, real dose at 08:00/20:00 VN time):

```
Hôm nay bạn có 2 liều thuốc Panadol Extra: 01:00, 13:00   <- UTC hours, not 08:00/20:00 VN
```

For a query spanning a VN-midnight boundary ("Ngày mai"), this gets worse:
two doses that are BOTH tomorrow in VN time can show up split across two
different UTC calendar dates in the model's own phrasing ("01:00 ngày kế
tiếp theo UTC" -- the model visibly confusing itself trying to compensate).

This is a real, patient-facing correctness issue (a displayed dose time
that's 5-7 hours off from what the patient's clock says) -- not this
build's bug, but adjacent to exactly what BUILD-27B fixed for the NEW
`get_doses_for_range`/`_build_medication_history_reply` path (which DOES
convert to `Asia/Ho_Chi_Minh` before both bounding and displaying).

## Suggested next step

1. Either convert `scheduled_at` to `Asia/Ho_Chi_Minh` before serializing it
   in `get_today_doses`/`get_upcoming_doses`'s output (simplest, matches
   what `_build_medication_history_reply` already does), or add an explicit
   instruction + the patient's timezone to `synthesize_read_only`'s prompt
   and verify the model reliably converts every time (weaker guarantee,
   not preferred given this codebase's general bias toward deterministic
   fixes over prompt-only trust).
2. Also revisit whether `get_today_doses`'s own date-bucketing
   (`group.scheduled_at.date()`, a UTC date) has the same local-date
   mis-bucketing bug `get_doses_for_range` was written to avoid (a dose
   between 00:00-06:59 VN time buckets into the previous UTC day) -- likely
   yes, unverified here.
3. Re-run BUILD-27's and BUILD-27B's own local golden/E2E scenarios after
   the fix to confirm no regression in already-passing wording.

**Status:** open, not started.
