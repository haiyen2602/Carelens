# APP-3 — Doctor Prescription Runtime Integration

Date: 2026-08-17
Scope: server-side Doctor Prescription integration only. No frontend/API DTO change, no V2_PRIMARY create, no V2 dose occurrence generation, no Railway or Agent work.

## Implemented boundary

`PRESCRIPTION_V2_MODE` is an explicit server-side setting with two allowed values:

- `legacy` (default): the existing prescription service and reads behave exactly as before; no V2 sidecar rows are written.
- `shadow`: create, edit, and approve keep the legacy transaction as the compatibility envelope and write deterministic V2 schedule intent in that same transaction. `V2_PRIMARY` is deliberately not an allowed mode.

The sidecar chain is `prescription_item -> medication_plan -> schedule_rule -> schedule_rule_time -> optional schedule_rule_cycle`. Stable UUIDv5 identifiers derived from the legacy prescription and item index make re-sync/update idempotent. Approval re-syncs before activation, including a prescription created while the server was still in `legacy` mode.

All mutable lifecycle operations lock the legacy prescription row with `SELECT ... FOR UPDATE`; V2 stop also locks its V2 items and occurrences. The SHADOW reconciliation log contains only operation, prescription ID, expected/actual item counts, mismatch flag, and aggregate sidecar statuses—no patient, dose, or instruction data.

## Validation and state rules

- Validity requires an active canonical drug mapping, valid inclusive `start_date`/`duration_days`, unique `HH:MM` times, matching positive `doses_per_day`, recognized meal instruction, valid timezone, and (when enabled) valid cycle values.
- `end_date = start_date + duration_days - 1` and is stored inclusive.
- Any unresolved or invalid input is written as `REVIEW_REQUIRED`; its plan/rule is not activated and APP-3 creates no V2 occurrence.
- Stop marks V2 schedule intent `STOPPED` only when there are zero V2 occurrences. If any exist, it raises `V2_SCHEDULE_STOP_CONFLICT` (HTTP 409 through the existing domain-error mapping) and rolls back the legacy cancellation and V2 changes.

## Clean PostgreSQL evidence

A disposable `pgvector/pgvector:pg16` PostgreSQL container was started on port 5433 with no reused volume/state, then removed after validation.

- `alembic upgrade head` reached revision `0027`.
- Drug Identity import, first run: `drug_product=3556`, `drug_id_map=3556`, `ingredient=1406`, `drug_product_ingredient=5287`.
- Identity import second run created `0` rows; artifact hashes were unchanged.
- Legacy category safety-policy seed created `49` rows first run and `0` rows second run.
- Final clean DB counts: `3556 | 3556 | 1406 | 5287 | 49` respectively.

Executed successfully against this clean database:

```text
ruff check backend/config.py backend/services/prescription/service.py \
  backend/services/scheduling/errors.py backend/services/scheduling/write_path.py \
  tests/services/prescription/test_service_db.py tests/services/scheduling/test_write_path.py

pytest tests/services/prescription/test_service_db.py \
  tests/services/scheduling/test_write_path.py \
  tests/test_v2_catalog_prescription_http.py -q
# 30 passed
```

The PostgreSQL tests cover LEGACY isolation, resolved SHADOW create/approve/stop, inclusive dates, `REVIEW_REQUIRED` for unresolved drugs, re-sync on mode change, deterministic sidecar re-run, atomic rollback when sidecar persistence fails, mismatch logging, two-session locking, stop conflict with a persisted V2 occurrence, and the existing legacy HTTP create/edit contract.

## Compatibility and limits

Legacy frontend/API DTOs and legacy read behavior remain unchanged. Existing legacy dose-event generation/cancellation remains active as before; this task neither reads from V2 for runtime behavior nor generates V2 `dose_occurrence` rows.

The current form can omit normalized meal/doses/cycle/timezone input. In SHADOW this is intentionally represented as `REVIEW_REQUIRED`, rather than guessed or activated. This is a visibility/operational-validation item, not a reason to weaken the validation gate.

## Conclusion

APP-3: PASS

LEGACY MODE: PASS — default mode writes no V2 sidecar and preserves existing behavior.

SHADOW MODE: PASS — create/edit/approve synchronize deterministic V2 intent atomically; invalid or unresolved records remain `REVIEW_REQUIRED`.

V2 SIDECAR: PASS — normalized schedule rows, inclusive dates, validation, redacted reconciliation logging, and stable identifiers verified on clean PostgreSQL.

STOP: PASS — zero-occurrence intent becomes `STOPPED`; any V2 occurrence fails closed with rollback.

COMPATIBILITY: PASS — existing prescription HTTP create/edit and legacy public `drug_id` contract passed without DTO/frontend changes.

TRANSACTION/IDEMPOTENCY: PASS — rollback, re-sync/no duplicate behavior, unique deterministic rows, and two-session row locking passed on PostgreSQL.

P0/P1:

- P0: none.
- P1: monitor the rate and causes of SHADOW `REVIEW_REQUIRED` rows before a future V2_PRIMARY decision; legacy DTOs may lack structured meal/cycle/timezone fields.
- P1: APP-4 must define the occurrence cancellation/update semantics before it permits stop after any V2 occurrence exists.

READY FOR APP-4: YES
