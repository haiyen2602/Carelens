# TASK-012: DB-4C — Prescription Backfill

**Domain:** `prescription` / `scheduling`
**Status:** In Progress
**Priority:** P0

## Goal

Backfill legacy `prescription.items[]` into the additive V2 prescription
domain without changing the existing API, runtime, Drug Knowledge backend, or
dose-occurrence data.

## Acceptance Criteria

- [ ] Read every legacy `prescription.items[]` record supplied to the importer.
- [ ] Backfill each item to `prescription_item` and one `medication_plan`.
- [ ] Create `schedule_rule` only when `gio_nhac` is a valid non-empty list of
  valid `HH:MM` values.
- [ ] Resolve `legacy_drug_id` through active `drug_id_map`; retain unresolved
  legacy IDs and report them without guessing a canonical product.
- [ ] Preserve raw `dose_text`, `frequency_text`, and `instructions` when
  structured parsing is uncertain.
- [ ] Create review/draft plans for missing or invalid schedules and never
  create `schedule_rule` or `dose_occurrence` for those items.
- [ ] Use deterministic IDs and source migration keys so re-runs are resumable
  and create no duplicates.
- [ ] Validate on a clean local PostgreSQL database; two runs must create zero
  new rows on the second run.
- [ ] Report source/reconciliation counts, active prescriptions with no V2
  item, unmapped IDs, invalid schedules, duplicate migration keys, orphan
  rows, date/status mapping, and source traceability.
- [ ] Write `data pharmacy/reports/database-architecture/10-prescription-backfill.md`.

## Out of Scope

- Backfilling `dose_occurrence` or `dose_event_log`.
- Dual-write, API/runtime changes, strict FK/`NOT NULL` enforcement, Railway,
  and cutover.
