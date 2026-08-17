# 14 Dose Occurrence Generator (DB-4F)

Scope: DB-4F creates V2 `dose_occurrence` rows only. It does not wire a cron,
reminder, notification, missed-dose/state/safety workflow, Railway, or alter
the legacy `dose_event` runtime.

## Generation design

`backend/services/scheduling/occurrence_generator.py` exposes
`generate_dose_occurrences(db, window_start, window_end)`. The local-date
window is mandatory and has no default: even a plan with `end_date = NULL`
can only generate within the explicit finite request window. The function does
not commit; callers own the surrounding transaction.

It processes only a complete chain with all of the following:

- `medication_plan`, `prescription_item`, and `schedule_rule` are `ACTIVE`;
- canonical product identity is present and `drug_product.status = ACTIVE`;
- plan/item product IDs agree, rule is `DAILY_AT_TIMES` with a daily interval,
  plan/rule timezones agree, and normalized time-row count equals
  `doses_per_day`;
- item date range is valid, and an optional cycle has valid values/anchor.

Any failed condition skips the whole rule and increments its invalid-rule
count. No schedule is guessed from JSON compatibility data.

For each qualifying local date and normalized `schedule_rule_time`, the
generator writes one occurrence with:

- UTC `scheduled_at`;
- immutable `scheduled_local_date`, `scheduled_local_time`, and `timezone`;
- lineage to plan/item/rule/product; and
- deterministic `generation_key` and UUIDv5 row ID.

The generator clips each rule to the intersection of its inclusive item date
range and the requested window. A cycle applies only on its `on_days` dates;
dates before its anchor do not infer a cycle position.

## Timezone and DST safety

Wall-clock conversion round-trips through UTC. A nonexistent DST time has no
valid round trip and an overlap has two UTC instants; both are fail-closed by
skipping that complete local date rather than selecting an arbitrary fold.
This preserves one-dose/one-intended-time semantics without medical guessing.

## Validation evidence

- Focused test suite: `13 passed` — normal UTC/local mapping, inclusive
  boundary clipping, open-ended bounded window, cycle on/off dates, DST normal
  conversion, DST gap/overlap fail-closed behavior, unresolved chain rejection,
  retry idempotency, and caller rollback.
- `ruff check`, `py_compile`, and `git diff --check` passed.
- Fresh disposable PostgreSQL 16 + pgvector Docker database upgraded to
  `0026 (head)`. A two-time active plan with no end date generated six rows in
  a requested three-day window, saved `08:00 Asia/Ho_Chi_Minh` as
  `01:00 UTC`, and re-run added zero rows (six existing keys).

## DB-4F: PASS

## GENERATION: PASS

One drug/rule/local-time/date produces one V2 occurrence. The service is not
connected to a scheduler or reminder job.

## TIMEZONE/DST: PASS

UTC and local context are persisted; DST gaps and overlaps are fail-closed.

## CYCLE: PASS

Inclusive dates and optional on/off cycles are applied before insert.

## IDEMPOTENCY: PASS

Deterministic unique generation keys make a re-run create zero duplicates.

## BOUNDARY TESTS: PASS

Explicit finite window, inclusive end date, no-end-date plan, invalid window,
timezone/DST, cycle, and rollback behavior are covered.

## P0/P1:

- P0: None.
- P1: Provide an approved scheduler invocation/window policy before automatic
  background generation; expose clinician review for DST-skipped dates; retain
  DB-4E's pending Architect/PM review of optional write-path contract fields.

## READY FOR REMINDER/DOSE STATE DOMAIN: YES

The V2 occurrence persistence boundary is ready. A later task must define
reminder windows, notification delivery, dose-state transitions, safety/audit
policy, and operational scheduling before any runtime activation.
