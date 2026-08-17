# TASK-014: DB-4E — Scheduling Domain / Doctor Write Path

**Domain:** `prescription` / `scheduling`
**Status:** Done
**Priority:** P0

## Goal

Persist doctor prescription form intent atomically into the approved V2
scheduling schema without generating occurrences or changing the legacy
runtime schedule generator.

## Acceptance Criteria

- [ ] Persist idempotent `prescription_item`, `medication_plan`,
  `schedule_rule`, normalized times, and optional cycle rows.
- [ ] Validate identity, dose frequency/times, inclusive date range, and
  cycle values; uncertain rows remain `REVIEW_REQUIRED`.
- [ ] Only activate valid, canonically resolved V2 plans/rules through the
  existing doctor approval path.
- [ ] Preserve legacy request compatibility with optional additive fields.
- [ ] Verify rollback, idempotency, legacy regression, and clean Docker DB.
- [ ] Write the DB-4E report.

## Out of Scope

- `dose_occurrence` generation, reminders/safety policy, Railway, and a
  runtime cutover away from the legacy prescription/dose-event path.
