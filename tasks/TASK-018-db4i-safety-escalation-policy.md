# TASK-018: DB-4I — Safety Escalation Policy

**Domain:** `safety_policy`
**Status:** Done
**Priority:** P0

## Goal

Turn a durable DB-4H assessment into an idempotent V2 escalation decision and
notification outbox record, without calling providers, legacy escalation
runtime, or an Agent.

## Acceptance Criteria

- [x] Apply the approved action vocabulary with a conservative risk/action
  matrix.
- [x] Auto-create an outbox job only for an eligible reviewed policy snapshot.
- [x] Prevent legacy/unreviewed/default policy from becoming clinical advice or
  caregiver/clinician escalation.
- [x] Persist an immutable V2 safety event and `dose_event_log` transactionally.
- [x] Verify action matrix, idempotency, rollback, concurrency, and clean
  PostgreSQL Docker.

## Out of Scope

- Provider delivery, legacy `escalation` runtime/API changes, Agent
  integration, Railway, and policy redesign.
