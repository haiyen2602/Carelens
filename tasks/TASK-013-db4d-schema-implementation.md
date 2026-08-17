# TASK-013: DB-4D — Schedule/Dose Schema Implementation

**Domain:** `prescription` / `scheduling`
**Status:** Done
**Priority:** P0

## Goal

Implement only the additive schema approved in
`11-dose-schedule-schema-design.md`, without scheduling behavior or API/runtime
changes.

## Acceptance Criteria

- [ ] Add `prescription_item.doses_per_day`, `meal_instruction_code`, and
  `meal_instruction_text` as nullable migration-safe fields.
- [ ] Add normalized `schedule_rule_time` and `schedule_rule_cycle` tables with
  safe uniqueness/indexing but no hard FK/check rollout.
- [ ] Add nullable local-generation context to `dose_occurrence`:
  `scheduled_local_date`, `scheduled_local_time`, and `timezone`.
- [ ] Establish the DB-4D inclusive `prescription_item.end_date` meaning while
  preserving compatibility columns.
- [ ] Keep `schedule_rule.times_of_day` JSON unchanged for compatibility.
- [ ] Update ORM models and verify a clean Docker PostgreSQL upgrade,
  schema inspection, downgrade, re-upgrade, and legacy table regression.
- [ ] Write `data pharmacy/reports/database-architecture/12-db4d-schema-implementation.md`.

## Out of Scope

- Scheduler/reminder code, occurrence generation, API/form changes, backfill,
  strict FK/`NOT NULL`/check hardening, Railway, and cutover.
