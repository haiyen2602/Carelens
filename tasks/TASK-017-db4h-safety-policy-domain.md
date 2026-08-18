# TASK-017: DB-4H — Safety Policy Domain

**Domain:** `safety_policy`  
**Status:** Done  
**Priority:** P0

## Goal

Resolve auditable V2 missed/delayed dose policies by product, ingredient,
category, then a fail-closed system default. Persist an idempotent assessment
and safety event without sending an escalation or clinical instruction.

## Acceptance Criteria

- [ ] Product, ingredient, category, and system-default precedence is tested.
- [ ] Legacy risk can only be seeded/used as an unreviewed category
  `MISSED_DOSE` policy.
- [ ] Assessment snapshots policy source/review status and links its policy.
- [ ] Ambiguous identity/policy and no-policy cases require medical review.
- [ ] Assessment/event/dose log are transactionally idempotent and serialized.
- [ ] Verify clean Docker PostgreSQL and document the DB-4H result.

## Out of Scope

- Safety escalation/notifications, Agent integration, Railway, changes to
  legacy safety/escalation runtime, or medical catch-up dose instructions.
