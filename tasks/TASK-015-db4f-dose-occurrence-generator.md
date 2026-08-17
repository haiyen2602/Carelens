# TASK-015: DB-4F — Dose Occurrence Generator

**Domain:** `scheduling`
**Status:** Done
**Priority:** P0

## Goal

Generate idempotent V2 `dose_occurrence` rows from fully resolved active
plans/rules, without reminders, notifications, safety logic, or Railway.

## Acceptance Criteria

- [ ] Generate one occurrence per active plan/rule/local-time/date.
- [ ] Respect inclusive item dates, local timezone/DST, and optional cycle.
- [ ] Require an explicit finite local-date generation window.
- [ ] Store UTC and immutable local scheduling context with deterministic keys.
- [ ] Fail closed for incomplete, invalid, or ambiguous schedules.
- [ ] Verify boundaries, cycles, DST, rollback, retry idempotency, and clean
  Docker PostgreSQL.
- [ ] Write the DB-4F report.

## Out of Scope

- Reminder, notification, missed-dose/state/safety workflow, API/cron wiring,
  Railway, and any legacy `dose_event` runtime change.
