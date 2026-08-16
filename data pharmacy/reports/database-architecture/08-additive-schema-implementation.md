# 08 Additive Schema Implementation

Scope: Database Architecture V2, DB-4A. This report covers local additive schema implementation and validation only.

No Drug V2 import, no backfill, no dual-write, no cutover, no Railway deploy.

## Inputs

- `docs/data/database_architecture_v2_plan.md`
- `data pharmacy/reports/database-architecture/01-current-db-audit.md`
- `data pharmacy/reports/database-architecture/02-domain-model.md`
- `data pharmacy/reports/database-architecture/03-target-schema.md`
- `data pharmacy/reports/database-architecture/04-erd.md`
- `data pharmacy/reports/database-architecture/05-safety-policy-model.md`
- `data pharmacy/reports/database-architecture/06-migration-strategy.md`
- `data pharmacy/reports/database-architecture/07-index-transaction-idempotency.md`

## Implementation Summary

Code changes:

- Added V2 ORM models in `backend/db/models.py`.
- Added Alembic revision `0023_database_architecture_v2_additive_schema.py`.
- Kept legacy physical table `dose_event` unchanged.
- Added V2 immutable event table as `dose_event_log`, per DB-3 decision.
- Added nullable DB-4A columns to legacy tables:
  - `patient`: `user_id`, `display_name`, `date_of_birth`, `sex`, `timezone`, `status`
  - `prescription`: `end_date`, `prescribed_by`, `prescribed_at`, `source_type`

New V2 tables:

- `drug_product`
- `drug_id_map`
- `ingredient`
- `drug_product_ingredient`
- `prescription_item`
- `medication_plan`
- `schedule_rule`
- `dose_occurrence`
- `dose_event_log`
- `notification_job`
- `medication_safety_policy`
- `missed_dose_assessment`
- `safety_event`
- `conversation`
- `message`
- `agent_run`
- `agent_tool_event`

## DDL Review Before Apply

Command:

```powershell
alembic upgrade 0022:0023 --sql
```

Reviewed output:

- `ALTER TABLE patient ADD COLUMN ...` only for DB-3 approved nullable additive columns.
- `ALTER TABLE prescription ADD COLUMN ...` only for DB-3 approved nullable additive columns.
- `CREATE TABLE dose_event_log`, not `CREATE/ALTER TABLE dose_event` for V2 semantics.
- Created all V2 additive tables listed above.
- Added safe indexes and unique idempotency constraints:
  - `dose_occurrence.generation_key`
  - `dose_event_log.idempotency_key`
  - `notification_job.idempotency_key`
  - `missed_dose_assessment.idempotency_key`
  - `safety_event.idempotency_key`
  - partial `drug_id_map` active legacy mapping unique index
  - safety policy scope/risk indexes, including reviewed and legacy fallback partial indexes

No DDL reviewed for:

- Drug V2 import
- data backfill
- service dual-write
- public API cutover
- Railway deploy

## Local Docker/Postgres Validation

Docker service:

```text
p-067-db-1 / pgvector/pgvector:pg16 / healthy / localhost:5432
```

Validation database:

```text
vmec04_db4a_codex
```

This database was created separately so the default local dev database was not overwritten or cleaned.

## Upgrade Test

Baseline command:

```powershell
$env:DATABASE_URL='postgresql://vmec:vmec@localhost:5432/vmec04_db4a_codex'
alembic upgrade 0022
```

Result:

- Clean database upgraded through existing legacy chain to revision `0022`.

Additive upgrade command:

```powershell
$env:DATABASE_URL='postgresql://vmec:vmec@localhost:5432/vmec04_db4a_codex'
alembic upgrade head
```

Result:

- Revision upgraded `0022 -> 0023`.
- Final `alembic current`: `0023 (head)`.

## Schema Validation

Validation checks after upgrade:

```text
revision 0023
v2_table_count 17
missing_v2_tables []
dose_event_log_present True
legacy_dose_event_present True
legacy_dose_event_collision_cols []
```

Additive column checks:

```text
patient_missing_expected_cols []
prescription_missing_expected_cols []
dose_event_missing_expected_cols []
dose_event_extra_v2_collision_cols []
```

Index checks:

```text
dose_occurrence_missing_indexes []
dose_event_log_missing_indexes []
notification_job_missing_indexes []
medication_safety_policy_missing_indexes []
```

ORM registration:

```text
metadata_has_v2_tables True
metadata_v2_count 17
```

Python compile:

```text
backend/db/models.py compiled
migrations/versions/0023_database_architecture_v2_additive_schema.py compiled
```

## Downgrade / Re-Upgrade Test

Downgrade command:

```powershell
$env:DATABASE_URL='postgresql://vmec:vmec@localhost:5432/vmec04_db4a_codex'
alembic downgrade 0022
```

Downgrade validation:

```text
revision 0022
v2_tables_still_present []
patient_additive_cols_still_present []
prescription_additive_cols_still_present []
legacy_dose_event_present True
```

Re-upgrade command:

```powershell
$env:DATABASE_URL='postgresql://vmec:vmec@localhost:5432/vmec04_db4a_codex'
alembic upgrade head
```

Re-upgrade validation:

```text
revision 0023
v2_table_count 17
missing_v2_tables []
dose_event_log_present True
legacy_dose_event_present True
legacy_dose_event_collision_cols []
```

Conclusion:

- Upgrade works on a clean local Docker/Postgres database.
- Downgrade to `0022` removes DB-4A additive schema.
- Re-upgrade to `0023` works cleanly.

## Legacy Regression Check

Legacy table presence:

```text
missing_legacy_tables_excluding_scheduler []
legacy_dose_event_present True
```

Note:

- `apscheduler_jobs` was not present in the clean validation DB because the runtime scheduler was not started. This is expected; it is created by APScheduler runtime, not by the DB-4A migration.

Legacy `dose_event` collision check:

```text
dose_event_collision_columns []
dose_event_log_is_separate_table True
```

Allowed additive legacy columns:

```text
patient_additive_columns ['date_of_birth', 'display_name', 'sex', 'status', 'timezone', 'user_id']
prescription_additive_columns ['end_date', 'prescribed_at', 'prescribed_by', 'source_type']
```

Conclusion:

- Legacy schema is preserved.
- Only planned nullable additive columns were added to legacy tables.
- V2 immutable events do not redefine or alter legacy `dose_event`.

## Alembic Check

Command:

```powershell
$env:DATABASE_URL='postgresql://vmec:vmec@localhost:5432/vmec04_db4a_codex'
alembic check
```

Result:

- `alembic check` still reports metadata drift, but remaining reported items are legacy/pre-existing metadata differences:
  - raw/trigram/HNSW indexes not represented in ORM metadata
  - existing `chat_messages` composite index not represented in ORM metadata
  - existing `hourly_conversation_summaries` unique constraint vs ORM index representation

DB-4A-specific drift found during the first check:

- safety policy partial indexes were missing in ORM metadata.

Action taken:

- Updated `MedicationSafetyPolicy` ORM indexes to include the reviewed and legacy fallback partial indexes.
- Updated `DrugIdMap` ORM active legacy unique index to match the partial unique index design.

Remaining drift is classified as legacy metadata debt, not a DB-4A additive schema failure.

## P0 / P1

P0:

- None found.

P1:

- Existing Alembic autogenerate/check drift remains for legacy raw indexes and one legacy unique/index representation. This should be cleaned in a separate metadata hygiene task, not inside DB-4A.
- No FK/check/`NOT NULL` hardening was added yet. This is intentional per DB-3 and must wait for validation/backfill gates.
- `drug_product_id` is nullable and not FK-enforced yet. This is intentional until Drug Identity import and mapping validation are complete.

## DB-4A ADDITIVE SCHEMA

ALEMBIC:

Revision `0023` created and applied locally. DDL was reviewed before apply. V2 immutable dose events use `dose_event_log`; legacy `dose_event` is not redefined.

CLEAN DB UPGRADE:

PASS. Clean local Docker/Postgres validation database upgraded from empty through `0022`, then to `0023`.

DOWNGRADE/RE-UPGRADE:

PASS. Downgrade `0023 -> 0022` removed V2 additive schema and planned additive columns. Re-upgrade `0022 -> 0023` succeeded.

LEGACY REGRESSION:

PASS. Legacy tables remain present. Legacy `dose_event` has no V2 collision columns. Only approved additive nullable columns were added to `patient` and `prescription`.

SCHEMA VALIDATION:

PASS. All 17 V2 tables exist, expected indexes/idempotency constraints are present, and ORM metadata registers the V2 tables.

P0/P1:

P0: none.

P1: legacy Alembic metadata drift remains outside DB-4A scope; strict FK/check/`NOT NULL` hardening remains gated by future validation/backfill.

READY FOR DRUG IDENTITY IMPORT:

YES

Conditions:

- Drug Identity import must be idempotent and identity/reference-only.
- Do not switch runtime Drug Knowledge facade yet.
- Do not backfill prescriptions/doses in the same step.
- Do not enforce `drug_product_id` FKs or `NOT NULL` until import validation passes.

