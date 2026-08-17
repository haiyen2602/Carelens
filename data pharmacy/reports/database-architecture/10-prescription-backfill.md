# 10 Prescription Backfill

Scope: Database Architecture V2, DB-4C. This report covers only the
idempotent, local-only backfill from legacy `prescription.items` into the
additive V2 prescription domain. It does not create `dose_occurrence` or
`dose_event_log`, dual-write, change API/runtime behavior, enforce stricter
constraints, or touch Railway/shared databases.

## Baseline and source of truth

- DB-4B identity import is verified at Alembic head `0025`:
  `drug_id_map` is the only canonical resolver for
  `legacy_drug_id -> drug_product_id`.
- `06-migration-strategy.md` requires resumable per-prescription work and
  preservation of legacy data.
- `07-index-transaction-idempotency.md` defines a unique migration key on
  `(migration_source, migration_source_id, migration_item_index)` and
  deterministic V2 target IDs.
- The legacy source table remains `prescription`; its JSON `items` field is
  never updated by this backfill.

The repository contains no versioned legacy-prescription database snapshot or
dump. Consequently the clean-database run below uses a controlled legacy corpus
to prove all importer paths. It is not a claim about the number or quality of
patient prescriptions on any developer machine or shared environment.

## Backfill behavior

Added `scripts/data_v2/backfill_prescription_v2.py` and
`tests/data_v2/test_backfill_prescription_v2.py`.

For every JSON object in a legacy `prescription.items` array, the importer:

1. Creates one deterministic `prescription_item` using UUIDv5 derived from
   `(prescription_id, item_index)`, with
   `migration_source=legacy_prescription`, source ID, and index.
2. Resolves the legacy slug only via an `ACTIVE` `drug_id_map` row. An
   unresolvable slug is retained in `legacy_drug_id`, has
   `drug_product_id=NULL`, and is reported; no canonical product is guessed.
3. Creates one deterministic `medication_plan` from the item ID.
4. Creates one deterministic daily `schedule_rule` only when `gio_nhac` is a
   non-empty, duplicate-free list of strict `HH:MM` values.

`lieu_dung -> dose_text`, `thoi_diem_dung -> frequency_text`, and item
`instructions` (or the legacy prescription note) are retained as raw text.
`dose_value` and `dose_unit` are deliberately `NULL`; this backfill does not
claim a structured dose parser. `start_date` plus `duration_days` maps to the
same exclusive end boundary used by the legacy scheduler. Date boundaries and
rule timezone are explicit (`Asia/Ho_Chi_Minh`).

Legacy status mapping is `draft -> DRAFT`, `approved|active -> ACTIVE`,
`completed -> COMPLETED`, `stopped -> STOPPED`, and `rejected -> REJECTED`.
Any unknown status, missing/unmapped drug, invalid date, or invalid/missing
schedule makes the V2 plan `REVIEW_REQUIRED`. A valid schedule on such a plan
is stored as `DRAFT`, so it cannot become actionable before a later reviewed
cutover. Missing/invalid schedules create no `schedule_rule`.

Rows are upserted in a separate transaction for each legacy prescription.
Primary IDs and the source migration key make an interrupted run resumable;
the importer updates its deterministic target rather than creating another one.

## Clean local PostgreSQL validation

An ephemeral `pgvector/pgvector:pg16` container named `p067-db4c-clean` was
started on port `5434` with no mounted volume. From an empty database:

1. `alembic upgrade head` reached revision `0025`.
2. The DB-4B importer loaded and re-hashed Final Canonical V2 identity data;
   all manifest hashes remained unchanged.
3. A controlled legacy corpus of five prescriptions was inserted. It includes
   five valid JSON item objects, one malformed `items` object, two unmapped
   slugs, two invalid/missing schedules, and one invalid item date.
4. DB-4C was run twice.

| Table | Backfillable rows | Created run 1 | Created run 2 | Final rows |
|---|---:|---:|---:|---:|
| `prescription_item` | 5 | 5 | 0 | 5 |
| `medication_plan` | 5 | 5 | 0 | 5 |
| `schedule_rule` | 3 | 3 | 0 | 3 |
| `dose_occurrence` | 0 (out of scope) | 0 | 0 | 0 |
| `dose_event_log` | 0 (out of scope) | 0 | 0 | 0 |

The source counts are `legacy_prescriptions=5` and `legacy_items=5`. The
malformed JSON value is recorded separately because it is not an item array and
therefore cannot be safely converted into a medication line.

## Validation results

| Gate | Result |
|---|---:|
| Legacy valid-item count vs V2 `prescription_item` count | `5 = 5` |
| Legacy active/approved prescriptions with no backfilled item | 1, expected controlled malformed source case |
| Unmapped `drug_id` | 2, preserved for review |
| Missing/invalid `gio_nhac` | 2, no rule created for either |
| Invalid item date | 1, dates left `NULL`; plan is `REVIEW_REQUIRED` |
| Duplicate migration keys | 0 |
| Item without legacy prescription | 0 |
| Plan without prescription item | 0 |
| Rule without medication plan | 0 |
| Non-null V2 product reference without `drug_product` | 0 |
| Source traceability (`migration_source=legacy_prescription`) | 5 / 5 items |

Date/status observations from the corpus:

- A valid seven-day active item stored `start_date=2026-08-17` and the legacy
  scheduler-compatible exclusive `end_date=2026-08-24`.
- Valid mapped active item/plan/rule statuses are `ACTIVE`.
- A legacy `approved` item maps to item status `ACTIVE`, but its unmapped drug
  keeps the plan `REVIEW_REQUIRED` and its otherwise valid rule `DRAFT`.
- Draft and completed source item statuses are preserved. Invalid schedule/date
  conditions keep their plans `REVIEW_REQUIRED`.

The relevant unit suite passed `8 passed`; Ruff and bytecode compilation
passed. Root pytest collection still has the previously documented unrelated
FastAPI 204 response-body assertion, so the focused suite uses
`--noconftest`.

## DB-4C PRESCRIPTION BACKFILL

STATUS:

PASS WITH ISSUES. The importer, deterministic migration keys, per-prescription
transactions, clean-Postgres import/re-import, and all integrity gates passed.
The repository lacks an approved, reproducible snapshot of actual legacy
prescriptions, so production-like legacy counts cannot yet be reconciled.

LEGACY PRESCRIPTIONS:

`5` in the controlled clean-database corpus.

LEGACY ITEMS:

`5` valid JSON item objects; `1` additional malformed `items` JSON object was
reported rather than invented.

PRESCRIPTION ITEMS CREATED:

`5` on run 1; `0` on run 2.

MEDICATION PLANS CREATED:

`5` on run 1; `0` on run 2.

SCHEDULE RULES CREATED:

`3` on run 1; `0` on run 2.

UNMAPPED DRUG IDS:

`2`, all retained as legacy-only IDs with `drug_product_id=NULL` and plans
`REVIEW_REQUIRED`; no automatic mapping occurred.

INVALID SCHEDULES:

`2`; neither created a schedule rule or dose occurrence. `1` invalid date and
`1` malformed `items` JSON source were also recorded for review.

ORPHANS:

PASS. All item, plan, rule, and non-null product-reference orphan checks are 0.

DUPLICATES:

PASS. Duplicate migration keys are 0; the second run created no V2 rows.

IDEMPOTENCY:

PASS.

P0/P1:

- P0: none in the clean controlled validation run.
- P1: no repository-controlled legacy prescription snapshot exists, so the
  actual legacy dataset has not yet been counted/reconciled in a clean database.
- P1: real unmapped IDs, invalid schedules/dates, or malformed items must be
  reviewed before any scheduling/dose-occurrence migration.

READY FOR DOSE OCCURRENCE BACKFILL:

NO
