# 07 Index Transaction Idempotency

Scope: Database Architecture V2, Phase DB-3 design. This document details indexes, transaction boundaries, idempotency, rollback controls, and validation gates for the migration track. It is design only.

## 1. Design Baseline

DB-3 uses:

- additive tables first
- text/string UUID IDs
- nullable `drug_product_id` during migration
- legacy `dose_event` retained
- V2 immutable events stored in `dose_event_log`
- public `drug_id` retained as `legacy_drug_id`
- `muc_nghiem_trong` migrated only as category fallback `LEGACY_UNREVIEWED`

## 2. Index Plan

Indexes should be added in the same additive migration bundle where safe, but high-volume production indexes should use concurrent creation when the migration framework allows it.

### Drug Identity

`drug_product`:

- PK: `id`
- Unique partial: `legacy_drug_id` where not null
- Index: `(category_id)`
- Index: `(display_name)`

`drug_id_map`:

- PK: `id`
- Unique partial: `(legacy_drug_id)` where `mapping_status='ACTIVE'`
- Index: `(drug_product_id)`
- Index: `(mapping_status)`

`ingredient`:

- PK: `id`
- Index: `(name)`

`drug_product_ingredient`:

- PK or unique: `(drug_product_id, ingredient_id)`
- Index: `(ingredient_id)`

### Prescription Domain

`prescription_item`:

- PK: `id`
- Index: `(prescription_id)`
- Index: `(patient_id, status)`
- Index: `(drug_product_id)`
- Index: `(legacy_drug_id)`
- Unique migration source key if used: `(migration_source, migration_source_id, migration_item_index)`

`medication_plan`:

- PK: `id`
- Index: `(patient_id, status)`
- Index: `(prescription_item_id)`
- Index: `(drug_product_id)`
- Partial unique after cleanup: `(prescription_item_id)` where `status in ('ACTIVE','PAUSED')`

`schedule_rule`:

- PK: `id`
- Index: `(medication_plan_id, status)`
- Index: `(status, start_at, end_at)`

### Dose Domain

`dose_occurrence`:

- PK: `id`
- Unique: `(generation_key)`
- Index: `(medication_plan_id, scheduled_at)`
- Index: `(patient_id, scheduled_at)`
- Index: `(status, scheduled_at)`
- Index: `(patient_id, status, scheduled_at)`
- Index: `(drug_product_id)`
- Index: `(legacy_drug_id, scheduled_at)`
- Optional migration lookup: `(legacy_dose_event_id)` if stored as a column rather than metadata

`dose_event_log`:

- PK: `id`
- Unique partial: `(idempotency_key)` where not null
- Index: `(dose_occurrence_id, created_at)`
- Index: `(patient_id, event_at)`
- Index: `(event_type, event_at)`
- Index: `(medication_plan_id, event_at)`

### Notification

`notification_job`:

- PK: `id`
- Unique: `(idempotency_key)`
- Index: `(status, scheduled_at)`
- Index: `(patient_id, scheduled_at)`
- Index: `(dose_occurrence_id)`
- Index: `(recipient_type, recipient_id, status)`
- Index: `(provider, provider_message_id)`

### Safety

`medication_safety_policy`:

- PK: `id`
- Index: `(scope_type, scope_id, risk_type)`
- Index: `(risk_type, review_status)`
- Index: `(valid_from, valid_to)`
- Partial index: `(scope_type, scope_id, risk_type, policy_version)` where `valid_to is null`
- Partial index: `(scope_type, scope_id, risk_type)` where `review_status='REVIEWED'`
- Partial index: `(scope_type, scope_id, risk_type)` where `source_type='LEGACY_CATEGORY_RULE'`

`missed_dose_assessment`:

- PK: `id`
- Index: `(dose_occurrence_id, evaluated_at)`
- Index: `(patient_id, evaluated_at)`
- Index: `(policy_id)`
- Index: `(risk_type, risk_level, evaluated_at)`

`safety_event`:

- PK: `id`
- Index: `(patient_id, created_at)`
- Index: `(event_type, created_at)`
- Index: `(severity, created_at)`
- Index: `(dose_occurrence_id)`
- Index: `(missed_dose_assessment_id)`

### Conversation / Agent

`conversation`:

- PK: `id`
- Index: `(patient_id, started_at)`
- Index: `(status, last_message_at)`

`message`:

- PK: `id`
- Index: `(conversation_id, created_at)`

`agent_run`:

- PK: `id`
- Index: `(conversation_id, started_at)`
- Index: `(patient_id, started_at)`
- Index: `(request_id)`

`agent_tool_event`:

- PK: `id`
- Index: `(agent_run_id, created_at)`
- Index: `(tool_name, created_at)`

## 3. Constraint Rollout

### Add In Initial Schema

Safe from day one:

- primary keys
- nullable FKs between new tables where backfill creates parent first
- unique idempotency keys on new writes
- simple non-controversial checks like `attempt_count >= 0`
- default `{}` JSONB metadata/payload

### Add After Validation

Delay until backfill reports pass:

- FKs from new operational tables to existing `patient`, `prescription`, `account`
- FKs to `drug_product`
- `NOT NULL` on `drug_product_id`
- strict status check constraints on migrated values
- partial unique active-plan constraints
- append-only trigger for `dose_event_log`

### Avoid Initially

Do not initially add:

- FK from legacy `dose_event` to V2 tables
- hard rename of legacy columns
- hard delete cascade on medical tables
- product/ingredient safety policy FKs if Drug Knowledge DB import is not complete

## 4. Transaction Boundaries

### Additive Schema Migration

One Alembic migration can create tables, but index creation strategy may require separate migrations if concurrent indexes are used.

Transaction expectation:

- DDL transaction where supported.
- No data rewrite.
- No service downtime expected beyond normal DDL locks.

### Drug Identity Import

Transaction:

```text
upsert drug_product
+ upsert ingredient
+ upsert drug_product_ingredient
+ upsert drug_id_map
+ write import audit/backfill state
```

Rollback:

- Feature flags still use file-backed facade.
- Imported rows can remain.
- Re-import is idempotent.

### Prescription Backfill

Per prescription transaction:

```text
read prescription
+ parse items[]
+ upsert prescription_item[]
+ upsert medication_plan[]
+ upsert schedule_rule[]
+ write migration_backfill_state rows
```

Failure:

- Roll back that prescription only.
- Record validation error.
- Continue with other prescriptions.

### Dose Occurrence Backfill

Per legacy grouped dose transaction:

```text
read legacy dose_event
+ read expected_items[]
+ map each item to prescription_item/medication_plan
+ upsert dose_occurrence per item
+ write migration_backfill_state
```

Failure:

- Roll back that legacy dose row only.
- Record source ID and item index.

### Immutable Event Backfill

Per occurrence transaction:

```text
read dose_occurrence
+ inspect legacy dose status/photo evidence
+ insert inferred dose_event_log if status is final
+ write migration_backfill_state
```

Important:

- Do not create fake action events for pending scheduled rows.
- Inferred rows must carry metadata:

```json
{
  "inferred_from_legacy": true,
  "legacy_dose_event_id": "...",
  "confidence": "STATUS_ONLY" 
}
```

### Mark Dose Taken After Cutover

Transaction:

```text
lock dose_occurrence row
+ insert dose_event_log with idempotency_key
+ update dose_occurrence.status/taken_at
+ cancel pending notification_job rows
+ insert audit_log/safety_event if needed
```

Concurrency:

- Use row lock on `dose_occurrence`.
- Unique idempotency key prevents duplicate event insert.
- If duplicate idempotency key occurs, return existing outcome.

### Photo Verification After Cutover

Transaction:

```text
read/lock photo_verification
+ map legacy grouped dose ID to V2 occurrences
+ insert dose_event_log per occurrence result
+ update dose_occurrence statuses
+ update photo_verification compatibility row
+ create safety_event/notification_job if mismatch/escalation
```

Concurrency:

- Idempotency key uses `photo_verification_id + attempt + result_version + occurrence_id`.
- Lock photo verification or enforce completion status transition.

### Missed Dose Scheduler

Transaction per occurrence:

```text
claim due dose_occurrence
+ resolve medication_safety_policy
+ insert missed_dose_assessment
+ insert dose_event_log(MISSED_AUTO_MARKED)
+ update dose_occurrence.status = MISSED
+ insert safety_event if needed
+ insert notification_job if needed
```

Concurrency:

- Select rows with status/due criteria and lock/skip locked.
- Idempotency key prevents repeated scheduler runs from duplicating rows.

### Notification Dispatch

Two-step transaction:

Claim:

```text
select pending notification_job for update skip locked
+ status = CLAIMED
+ attempt_count += 1
+ last_attempt_at = now
```

Complete:

```text
provider result
+ status = SENT or FAILED
+ sent_at/provider_message_id
+ optional safety_event/audit
```

Do not update dose status from notification result.

## 5. Idempotency Keys

### Drug Import

```text
drug-product:{manifest_version}:{drug_product_id}
drug-id-map:{manifest_version}:{legacy_drug_id}:{drug_product_id}
ingredient:{manifest_version}:{ingredient_id}
product-ingredient:{manifest_version}:{drug_product_id}:{ingredient_id}
```

### Prescription Backfill

```text
prescription-item:{prescription_id}:item-index:{i}:fingerprint:{hash}
medication-plan:{prescription_item_id}
schedule-rule:{medication_plan_id}:rule:{hash}
```

Fingerprint includes stable normalized fields:

- legacy drug ID
- drug display name
- dose text
- reminder times
- date range

### Dose Occurrence Generation

Backfill:

```text
legacy-dose-event:{legacy_dose_event_id}:item-index:{i}:fingerprint:{hash}
```

Native generation:

```text
schedule-rule:{schedule_rule_id}:drug:{drug_product_id-or-legacy}:scheduled-at:{scheduled_at_iso}
```

### Dose Event Log

Manual/API:

```text
dose-event:{request_id}:{dose_occurrence_id}:{event_type}
```

Scheduler:

```text
dose-event:scheduler:{dose_occurrence_id}:{event_type}:{scheduled_at_iso}
```

Photo:

```text
dose-event:photo:{photo_verification_id}:attempt:{attempt}:occurrence:{dose_occurrence_id}:result:{result_version}
```

Backfill inferred:

```text
dose-event:backfill:{legacy_dose_event_id}:occurrence:{dose_occurrence_id}:status:{legacy_status}
```

### Missed Dose Assessment

```text
assessment:{dose_occurrence_id}:{risk_type}:{assessment_version}:{policy_id-or-fallback}
```

If multiple assessments are intentionally allowed over time, add evaluation window:

```text
assessment:{dose_occurrence_id}:{risk_type}:{assessment_version}:{evaluation_bucket}
```

### Notification Job

```text
notification:{dose_occurrence_id}:{notification_type}:{recipient_type}:{recipient_id}:{scheduled_at_iso}
```

For non-dose safety alerts:

```text
notification:safety-event:{safety_event_id}:{notification_type}:{recipient_type}:{recipient_id}
```

### Safety Event

```text
safety-event:{source}:{source_event_id}:{event_type}
```

For policy-driven missed dose:

```text
safety-event:assessment:{missed_dose_assessment_id}:{event_type}
```

## 6. Rollback Controls

### Flags

Minimum flags:

- `DB_V2_DUAL_WRITE_ENABLED`
- `DB_V2_READ_SHADOW_ENABLED`
- `DB_V2_READ_PRIMARY_ENABLED`
- `DB_V2_SAFETY_POLICY_ENABLED`
- `DB_V2_NOTIFICATION_JOB_ENABLED`
- `DB_V2_DRUG_DB_REFERENCE_ENABLED`

### Rollback Matrix

| Stage | Rollback action | Data action |
|---|---|---|
| Additive schema only | Disable unused flags | Leave new tables |
| Drug import | Keep facade file-backed | Re-import later if needed |
| Backfill only | Continue legacy reads/writes | Re-run idempotent backfill |
| Shadow read | Disable shadow flag | Keep diff reports |
| Dual-write | Disable dual-write | Reconcile or discard V2 rows by migration state |
| V2 read primary | Disable read-primary if legacy still current | Replay V2-only writes to legacy if any |
| Legacy retired | Restore/redeploy plan required | No simple flag rollback |

## 7. Validation SQL/Report Gates

DB-3 should create report scripts later, but the gates are defined here.

### Reference Integrity

Checks:

- prescriptions with missing patient
- legacy dose rows with missing prescription or patient
- photo rows with missing legacy dose row
- escalation rows with missing patient or legacy dose row
- caregiver links with missing account or patient

### Drug Mapping

Checks:

- prescription items with `legacy_drug_id` but no active `drug_id_map`
- active `drug_id_map` duplicates
- ambiguous legacy IDs used in active prescriptions
- V2 occurrence rows with null `drug_product_id` after mapping window

### Prescription Backfill

Checks:

- legacy items count vs `prescription_item` count
- invalid JSON shape
- missing drug display name
- invalid date ranges
- missing/invalid schedule time

### Dose Backfill

Checks:

- expected item count vs occurrence count
- duplicate `generation_key`
- occurrence without medication plan
- occurrence status outside allowed enum
- grouped legacy row with mixed mapping errors

### Safety Policy

Checks:

- any legacy policy not `CATEGORY`
- any legacy policy not `LEGACY_UNREVIEWED`
- any legacy policy with `source_type` not `LEGACY_CATEGORY_RULE`
- category fallback overriding product/ingredient in resolver tests

### Compatibility Diff

Checks:

- legacy prescription DTO vs V2 projection
- legacy grouped dose DTO vs V2 projection
- adherence report result legacy vs V2
- Agent schedule answer source legacy vs V2
- caregiver dashboard row counts

## 8. Cutover Gates

### Gate A: Schema Ready

- New tables exist.
- Required indexes exist.
- Legacy tables untouched.

### Gate B: Backfill Ready

- Backfill reports pass.
- Error rows are reviewed.
- Re-run produces zero duplicates.

### Gate C: Shadow Ready

- Shadow reads enabled.
- Diffs are below agreed threshold.
- Critical DTO differences are zero.

### Gate D: Dual-Write Ready

- Dual-write transactions are atomic where needed.
- Idempotency keys are enforced.
- Rollback path tested.

### Gate E: Constraint Ready

- FK validation reports pass.
- `NOT NULL` candidates are fully populated.
- Enum/status mapping is complete.

### Gate F: Read Primary Ready

- V2 read projections match API V1.
- Frontend behavior is unchanged or approved.
- Reporting and Agent tools pass regression.

## 9. Known High-Risk Areas

- Legacy grouped dose status cannot always represent per-drug partial completion.
- Photo verification currently assumes one grouped legacy dose.
- Existing dev/demo data may have orphaned text IDs.
- Existing statuses are mixed case and not fully aligned with target enums.
- `drug_product_id` coverage depends on `drug_id_map` quality.
- `muc_nghiem_trong` can be misused if policy guards are weak.
- If V2 read-primary starts before dual-write stability, rollback may require replay.

## 10. Decisions Chốt

- Add indexes for new V2 tables early, but delay strict FK/check/`NOT NULL` hardening until validation gates pass.
- Use `generation_key` and `idempotency_key` as first-class unique controls.
- Use per-source, per-row transactions for backfills so failures do not poison the whole run.
- Use `FOR UPDATE`/claim-style locking for dose status, missed-dose scheduler, photo completion, and notification dispatch.
- Keep notification state separate from dose state.
- Use `dose_event_log` for immutable events during migration.
- Use validation reports as release gates, not nice-to-have diagnostics.

## 11. Blockers Còn Lại

- Need concrete Alembic DDL reviewed before execution.
- Need backfill implementation plan and dry-run report format.
- Need exact imported V2 JSONL field mapping.
- Need API compatibility tests for grouped dose projection and partial status.
- Need concurrency tests for scheduler/photo/notification idempotency.
- Need rollback rehearsal plan before V2 read-primary.
- Need clinical/product approval for fallback safety copy and escalation behavior.

## 12. READY FOR ADDITIVE MIGRATION

READY FOR ADDITIVE MIGRATION: YES

Conditions:

- Only additive DDL should run first.
- `dose_event_log` must be used instead of redefining legacy `dose_event`.
- New columns that depend on backfill must start nullable.
- Strict FKs/checks must be gated by validation reports.
- Backfill scripts must be idempotent and resumable before they touch shared environments.
- No Railway deploy or production cutover should happen as part of additive migration.

