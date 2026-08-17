# APP-4 - Dose and Schedule Runtime Integration

Date: 2026-08-17
Scope: bounded V2 occurrence generation and patient dose runtime integration. No Safety APP-5 integration, notification provider, Railway, Agent work, or frontend/API DTO changes.

## Runtime boundary

`DOSE_RUNTIME_MODE` is an explicit server-side setting:

- `legacy` (default): legacy dose reads and writes remain unchanged.
- `shadow`: approved, fully resolved ACTIVE V2 plans generate/reconcile bounded V2 occurrences while patient reads remain legacy.
- `v2`: the unchanged legacy dose API DTO is served by the V2 adapter and state changes use only the V2 dose-state domain service. There is no fallback to legacy data in this mode.

On SHADOW approval, and on a valid edit, the service generates occurrences only for the prescription's ACTIVE V2 plans. Generation is finite: every eligible plan must have an inclusive `end_date`; dates before the current plan-local date are not regenerated. The generator uses the plan timezone, persists UTC `scheduled_at` together with local date/time/timezone, and includes a schedule-revision fingerprint in its deterministic `generation_key`. A retry creates no duplicates, while a changed schedule can safely create a replacement future occurrence.

## Patient dose adapter and state domain

The adapter converts V2 per-drug occurrences into the existing grouped-dose DTO shape. It groups rows by prescription, local date, local time, and timezone, so multiple drugs at the same time are presented as one existing dose group while preserving one occurrence per drug in the database. Legacy prescription item fields are used only to populate the existing `expected_items` display contract; V2 occurrence rows remain the timing/state source of truth.

The API V2 branch resolves the group and delegates all changes to the V2 domain service. Permitted public transitions are:

```text
SCHEDULED -> DUE -> TAKEN | DELAYED | MISSED | SKIPPED
```

Each transition writes the immutable `dose_event_log`. If a grouped legacy DTO contains different V2 occurrence states, the adapter fails closed because the existing group contract cannot represent a partial state safely.

## Edit and stop semantics

Before a valid active edit or stop, APP-4 locks V2 prescription items and cancels only strictly future `SCHEDULED` occurrences. It records immutable `OCCURRENCE_CANCELLED` events, changes those rows to `CANCELLED`, and cancels their queued/retry notification jobs. Terminal historical occurrences are never mutated. Cancellation neither evaluates nor emits safety events.

- Edit uses source `PRESCRIPTION_EDIT`, then writes fresh V2 intent and generates occurrences under the new revision key.
- Stop uses source `PRESCRIPTION_STOP`, then marks V2 item, plan, and rule intent `STOPPED` in the same transaction.
- Plan rows are locked during generation, serializing concurrent generators on PostgreSQL.

## Clean PostgreSQL validation

A disposable `pgvector/pgvector:pg16` PostgreSQL container was created on port 5433 without a reused volume or database state.

- `alembic upgrade head` reached revision `0027`.
- Drug Identity import first run: `drug_product=3556`, `drug_id_map=3556`, `ingredient=1406`, `drug_product_ingredient=5287`.
- The second identity import created `0` rows and source artifact hashes remained unchanged.
- The legacy category safety-policy seed created `49` rows first run and `0` rows on re-run.
- Final clean counts were `3556 | 3556 | 1406 | 5287 | 49`.

The focused clean-PostgreSQL suite passed (`58 passed`), covering legacy/shadow isolation, bounded and inclusive generation, DST/timezone and cycle boundaries, retries, rollback, deterministic duplicate prevention, two-session row locking, grouped multi-drug reads, V2 HTTP transition authorization, immutable logs, edit supersession, stop cancellation, notification cancellation, and legacy dose HTTP regression. `ruff check` and `git diff --check` also passed after the suite.

## Limits and follow-up

This is an incremental, explicitly gated runtime path. No production scheduler, notification delivery, Safety policy assessment, escalation, Railway deployment, or Agent integration was enabled. The default remains `DOSE_RUNTIME_MODE=legacy`.

## Conclusion

APP-4: PASS

OCCURRENCE GENERATION: PASS - bounded, timezone-aware, inclusive-date generation is deterministic and only runs for fully resolved ACTIVE plans.

PATIENT DOSE ADAPTER: PASS - V2 rows are grouped into the unchanged legacy DTO without losing the per-drug occurrence model.

STATE TRANSITIONS: PASS - V2 domain service exclusively owns state changes and immutable event logging in V2 mode.

EDIT/STOP/CANCELLATION: PASS - future scheduled rows and pending notification jobs are cancelled; terminal history is immutable and cancellation creates no safety event.

COMPATIBILITY: PASS - legacy default/shadow behavior and existing dose API DTO/grouping remain intact; V2 mode is explicit with no mixed fallback.

IDEMPOTENCY/CONCURRENCY: PASS - deterministic revision keys, re-run checks, transaction rollback, and PostgreSQL row-lock coverage passed.

P0/P1:

- P0: none.
- P1: `get_v2_dose_group` currently resolves a group by scanning V2 groups for the patient; replace this with a direct, indexed group lookup before high-volume rollout.
- P1: legacy photo/reporting flows still read `DoseEvent`; do not enable `DOSE_RUNTIME_MODE=v2` outside the scoped patient-dose route until their adapter/release boundary is accepted.
- P1: production scheduling and notification delivery remain deliberately out of scope.

READY FOR APP-5: YES
