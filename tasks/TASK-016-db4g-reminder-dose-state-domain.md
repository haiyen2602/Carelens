# TASK-016: DB-4G — Reminder & Dose State Domain

**Domain:** `scheduling`  
**Status:** Done  
**Priority:** P0

## Goal

Implement the V2 dose-occurrence state domain and an idempotent notification
outbox. This task does not send notifications or apply any safety policy.

## Acceptance Criteria

- [ ] Permit only `SCHEDULED → DUE → TAKEN | DELAYED | MISSED | SKIPPED`.
- [ ] Append every state and notification action to immutable `dose_event_log`.
- [ ] Apply the approved ±30 minute dose window and require explicit reminder
  offsets because follow-up reminder timing remains pending PM approval.
- [ ] Make transitions and outbox jobs idempotent and safe under concurrent
  PostgreSQL workers.
- [ ] Verify state timing, retry, duplicate, rollback, race, and clean Docker.
- [ ] Write the DB-4G report.

## Out of Scope

- Notification-provider delivery, API/cron wiring, Safety Policy/escalation,
  legacy `dose_event` changes, Railway, and runtime cutover.
