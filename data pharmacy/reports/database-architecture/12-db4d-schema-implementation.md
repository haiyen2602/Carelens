# 12 DB-4D Schema Implementation

Scope: Database Architecture V2 DB-4D implementation following
`11-dose-schedule-schema-design.md`. This change is schema and ORM only: it
does not change the prescription API/form, runtime backend selection,
scheduler/reminder behavior, Railway, or create any `dose_occurrence` rows.

## Implemented additive migration

Alembic revision `0026` (parent `0025`) adds only the approved structures:

| Target | Implemented schema | Compatibility / safety boundary |
|---|---|---|
| `prescription_item` | Nullable `doses_per_day`, `meal_instruction_code`, and `meal_instruction_text` | Existing raw `dose_text`, `frequency_text`, and dates remain unchanged. |
| `schedule_rule_time` | `id` primary key, non-null `schedule_rule_id`, non-null SQL `time` `local_time`, audit timestamps, and unique `(schedule_rule_id, local_time)` | No parent FK or validation check is introduced. The unique key supplies the rule/time lookup index. |
| `schedule_rule_cycle` | One-to-one `schedule_rule_id` primary key, `anchor_date`, `on_days`, `off_days`, and audit timestamps | No parent FK or cycle-value check is introduced. The primary key supplies the rule lookup index. |
| `dose_occurrence` | Nullable `scheduled_local_date`, `scheduled_local_time`, `timezone`, plus index `(patient_id, scheduled_local_date, scheduled_local_time)` | No occurrence is generated or updated. |

`schedule_rule.times_of_day` remains a JSON column and was not changed. New
future writes can use `schedule_rule_time`; compatibility/backfill readers can
continue using the JSON field until a separately approved write-path change.

## Inclusive clinical date semantics

`prescription_item.end_date` is now documented in the ORM and DB-4C helper as
an **inclusive local clinical calendar date**. A duration of seven days
beginning 2026-08-17 therefore ends on 2026-08-23. The available operational
legacy source contains no prescriptions/items, so no stored patient row needed
conversion. This task does not alter the column type or add a date-range check.

## ORM and deferred hardening

The SQLAlchemy models cover every column/table introduced by revision `0026`.
The intentionally deferred items are exactly those called out by the approved
design: foreign keys, `NOT NULL` rollout for pre-existing rows, status/meal
enums, check constraints for dates and cycle values, and a partial unique
active-plan rule. These require operational validation and are not silently
hardened here.

## Clean PostgreSQL validation

A fresh disposable Docker PostgreSQL 16 + pgvector database, with no reused
volume or prior application data, was used for the migration lifecycle:

1. `alembic upgrade head` completed at `0026 (head)`.
2. Catalog inspection confirmed all three nullable `dose_occurrence` context
   columns; the three nullable `prescription_item` fields; both normalized
   tables; `uq_schedule_rule_time_local_time`; and
   `ix_dose_occurrence_patient_local_schedule`.
3. `alembic downgrade 0025` removed the DB-4D columns/tables/index while
   retaining legacy `prescription`, `dose_event`, and JSON `times_of_day`.
4. A second `alembic upgrade head` completed at `0026 (head)`.
5. The clean database contained `0` `dose_occurrence` rows throughout; no
   scheduler or generator was invoked.

Focused automated validation passed:

```text
python -m pytest --noconftest tests/data_v2/test_import_drug_identity_v2.py \
  tests/data_v2/test_backfill_prescription_v2.py \
  tests/data_v2/test_db4d_schedule_schema.py -q
17 passed

ruff check backend/db/models.py scripts/data_v2/backfill_prescription_v2.py \
  tests/data_v2/test_backfill_prescription_v2.py \
  tests/data_v2/test_db4d_schedule_schema.py \
  migrations/versions/0026_db4d_schedule_schema.py
All checks passed
```

The test run emitted one pre-existing local pytest-cache warning (`WinError
183`) while attempting to write `.pytest_cache`; test results and validation
were unaffected.

## DB-4D IMPLEMENTATION: PASS

## MIGRATION: PASS

Additive Alembic revision `0026`, reversible to `0025`.

## ORM: PASS

Models and focused schema tests match the migration.

## CLEAN UPGRADE: PASS

## DOWNGRADE/RE-UPGRADE: PASS

## LEGACY REGRESSION: PASS

Legacy tables and `schedule_rule.times_of_day` JSON survived the full cycle;
no API/runtime or dose-generation behavior was changed.

## P0/P1:

- P0: None.
- P1: Operational validation before adding FKs, check constraints, enum/
  status enforcement, non-null hardening, or active-plan uniqueness; approved
  write-path/scheduler work remains a later task.

## READY FOR SCHEDULING DOMAIN IMPLEMENTATION: YES

The required persistence schema is available. A subsequent task must still
define and approve clinician-facing write validation and scheduling behavior
before any occurrence generation.
