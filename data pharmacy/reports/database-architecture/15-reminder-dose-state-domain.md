# 15 Reminder & Dose State Domain (DB-4G)

Scope: DB-4G adds the V2 persistence-domain logic for a single
`dose_occurrence`. It does not alter legacy `dose_event`, wire a cron/API,
send a provider notification, create safety assessments, or deploy Railway.
The existing additive V2 schema at Alembic `0026` already contained
`dose_occurrence`, immutable `dose_event_log`, and `notification_job`, so no
schema migration is required.

## Domain boundary

`backend/services/scheduling/dose_state.py` separates three concerns:

- `dose_occurrence` is the current state of one drug at one intended time.
- `dose_event_log` is append-only history. State changes, reminder enqueue,
  cancellation, delivery attempt, retry scheduling, and completion each append
  a deterministic immutable event; the implementation never updates/deletes
  event rows.
- `notification_job` is a delivery outbox. It has an independent lifecycle
  (`QUEUED`, `PROCESSING`, `RETRY`, `SENT`, `CANCELLED`) and cannot be the
  source of truth for the dose state.

All public operations leave commit/rollback ownership to their caller.

## State machine and window

Only these transitions are permitted:

```text
SCHEDULED -> DUE -> TAKEN | DELAYED | MISSED | SKIPPED
```

The approved dose window is initialized as `scheduled_at ± 30 minutes` when a
V2 occurrence first enters the domain. `TAKEN` must be inside that window.
`DELAYED` must be after `window_end` and remain on the same stored local day;
`MISSED` is permitted only after the window. The clock scan records `DUE` then
`MISSED` when it discovers an already-expired scheduled occurrence, preserving
the full state history without sending a stale reminder.

Repeated same-target commands return an unchanged result and write no duplicate
event. A different target from a terminal/current-incompatible state is
rejected.

## Reminder and notification design

`advance_dose_occurrences(db, now, reminder_offsets)` transitions eligible
occurrences and creates one idempotent job per explicit offset. Its key is the
occurrence ID plus offset; `dose_event_log` uses the corresponding deterministic
action key. A rerun therefore observes the existing job/event rather than
creating another one.

The only approved timing value is the ±30-minute window. The documented
T+15/T+30 reminder levels are still marked as a PM proposal in
`specs/business-rules.md`; DB-4G intentionally does not hard-code them. A
future scheduler must pass an approved list (for example, an explicit T+0
offset) and every offset is validated to lie within the window.

`claim_notification_job` serializes a due `QUEUED`/`RETRY` job under locks.
`complete_notification_job` records `SENT` or accepts a caller-supplied retry
time—no unapproved backoff is invented. All worker flows lock the occurrence
before the job. If a dose closes while a job is `PROCESSING`, completion changes
the job to `CANCELLED` instead of delivering a stale reminder.

## Concurrency and transaction safety

State transitions use `SELECT ... FOR UPDATE` on the occurrence. Notification
claim/completion follows the same occurrence-first lock order, then locks its
job, avoiding competing transition/delivery deadlocks. Unique idempotency keys
remain a database-level second barrier. Terminal transitions cancel pending
`QUEUED`/`RETRY` jobs in the same transaction.

No missed-dose severity, safety event, clinical recommendation, escalation, or
notification-provider behavior is present.

## Validation evidence

- Focused suite: `14 passed` — due/taken/delayed/skipped/missed boundaries,
  immutable history, offset-job rerun, invalid and duplicate transition
  rejection, retry/claim/send lifecycle, stale in-flight cancellation, and
  transaction rollback. The DB-4F generator regression tests run in the same
  command.
- `ruff check` passed for the added scheduling domain and tests.
- Fresh disposable PostgreSQL 16 + pgvector container (no mounted volume) was
  upgraded with `alembic upgrade head` to `0026 (head)`.
- On that database, two reminder jobs were queued on the first scan and zero
  duplicates on the second. A second concurrent session attempting `SKIPPED`
  waited on the occurrence row lock; after the first committed `TAKEN`, the
  competing transition was rejected. The resulting occurrence had six immutable
  events and two cancelled jobs.
- The regular root `pytest` collection remains blocked before DB-4G tests by
  an existing FastAPI assertion in `backend/api/caregiver_routes.py`: a
  `204` route declares a response body. Focused scheduling tests were run with
  that unrelated root conftest excluded; no change was made outside DB-4G.

## DB-4G: PASS

## STATE MACHINE: PASS

The allowed V2 graph is enforced with window and local-date validation.

## EVENT LOG: PASS

Every implemented occurrence/reminder action appends an idempotent immutable
`dose_event_log` row.

## REMINDER: PASS

The domain owns the ±30-minute window and idempotent outbox lifecycle; it does
not enable a scheduler, API, provider, or clinical action.

## NOTIFICATION IDEMPOTENCY: PASS

Occurrence-plus-offset job keys and action-event keys make retries/reruns add
zero duplicate jobs or history.

## CONCURRENCY: PASS

Occurrence-first PostgreSQL row locking and unique keys serialize competing
state/notification operations. A clean-database two-session race was verified.

## P0/P1:

- P0: None.
- P1: PM must approve the production reminder-offset cadence before scheduler
  wiring; current code intentionally requires it explicitly.
- P1: Root-suite collection has the pre-existing FastAPI `204` response-body
  assertion noted above; it is outside this task's domain and was not changed.

## READY FOR SAFETY POLICY DOMAIN: YES

The V2 domain now produces auditable `MISSED`/other terminal state events for a
future Safety Policy task. Scheduler/provider activation still requires the
approved reminder cadence and is out of scope here.
