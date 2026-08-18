# 03 Target Schema

Scope: Database Architecture V2, Phase DB-2. This document proposes the target relational schema and compatibility constraints. It is a design document only.

## 1. Naming And Types

Recommended baseline:

- Primary keys: UUID or existing project string UUID convention. Choose one before migration DDL.
- Timestamps: `timestamptz` in UTC for event times and system timestamps.
- Dates: `date` for prescription calendar boundaries.
- JSON metadata: `jsonb`.
- Enum/status: Postgres enum or check constraints. If enum churn is expected, use text plus check constraints in early additive migrations.
- Soft lifecycle: avoid hard delete for medical/audit records.

## 2. Existing Tables To Keep During Migration

Do not drop in DB-3:

- `drug`
- `drug_chunks`
- `patient`
- `prescription`
- current MVP `dose_event`
- `photo_verification`
- `escalation`
- `chat_messages`
- `hourly_conversation_summaries`
- `audit_log`
- `account`
- `pending_drug_confirmation`
- `caregiver_link`

Because current `dose_event` has different semantics from V2 immutable `dose_event`, migration design must choose either:

- create `dose_occurrence` first and keep legacy `dose_event` until cutover, then rename/split later; or
- create V2 immutable event table under a temporary name such as `dose_event_v2` until legacy table is retired.

DB-2 target name is still `dose_event`, but DB-3 should avoid name collision.

## 3. Drug Reference Tables

Operational V2 references Drug Knowledge V2 through `drug_product_id`. If Drug Knowledge remains file-backed, `drug_product_id` can be stored without local FK at first. If Drug Knowledge is imported into DB, use the following tables.

### `drug_product`

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | uuid/text | no | Canonical V2 product ID |
| `legacy_drug_id` | text | yes | Public legacy slug |
| `display_name` | text | no | Current display name |
| `dosage_form` | text | yes | Normalized form |
| `route` | text | yes | Normalized route |
| `strength_text` | text | yes | Display strength |
| `category_id` | text | yes | Drug category reference |
| `status` | text | no | `ACTIVE`, `RETIRED`, `MERGED` |
| `created_at` | timestamptz | no |  |
| `updated_at` | timestamptz | no |  |

Constraints/indexes:

- PK: `drug_product(id)`
- Unique nullable: `drug_product(legacy_drug_id)`
- Check: `status in ('ACTIVE','RETIRED','MERGED')`
- Index: `drug_product(display_name)`
- Index: `drug_product(category_id)`

### `drug_id_map`

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | uuid/text | no |  |
| `legacy_drug_id` | text | no | Public API slug |
| `drug_product_id` | uuid/text | no | Canonical V2 ID |
| `mapping_status` | text | no | `ACTIVE`, `AMBIGUOUS`, `RETIRED` |
| `source_manifest_version` | text | yes | V2 artifact provenance |
| `created_at` | timestamptz | no |  |
| `updated_at` | timestamptz | no |  |

Constraints/indexes:

- PK: `drug_id_map(id)`
- Unique: `drug_id_map(legacy_drug_id, mapping_status)` where `mapping_status='ACTIVE'`
- FK: `drug_id_map.drug_product_id -> drug_product.id` when local `drug_product` exists
- Index: `drug_id_map(drug_product_id)`

## 4. Patient

### `patient`

Target additions/shape:

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | uuid/text | no | Existing patient ID |
| `user_id` | uuid/text | yes then no | FK to `account.id` after cleanup |
| `display_name` | text | no | Migrated from `full_name` |
| `date_of_birth` | date | yes | Prefer over `year_of_birth` |
| `sex` | text | yes | `MALE`, `FEMALE`, `OTHER`, `UNKNOWN` |
| `timezone` | text | no | Default `Asia/Ho_Chi_Minh` during backfill |
| `status` | text | no | `ACTIVE`, `INACTIVE`, `ARCHIVED` |
| `created_at` | timestamptz | no | Existing |
| `updated_at` | timestamptz | no | Existing |

Constraints/indexes:

- PK: `patient(id)`
- FK after cleanup: `patient.user_id -> account.id`
- Check: status enum
- Check: sex enum
- Index: `patient(user_id)`

## 5. Prescription

### `prescription`

Target columns:

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | uuid/text | no | Existing |
| `patient_id` | uuid/text | no | FK target |
| `status` | text | no | V2 lifecycle |
| `prescribed_by` | uuid/text | yes | Account/doctor ID |
| `prescribed_at` | timestamptz | yes | Clinical prescription time |
| `start_date` | date | yes | Existing |
| `end_date` | date | yes | Derived from duration when possible |
| `notes` | text | yes | Existing note |
| `source_type` | text | no | `MANUAL`, `IMPORT`, `AGENT_DRAFT` |
| `created_at` | timestamptz | no | Existing |
| `updated_at` | timestamptz | no | Existing |

Constraints/indexes:

- PK: `prescription(id)`
- FK: `prescription.patient_id -> patient.id`
- Check: `status in ('DRAFT','ACTIVE','COMPLETED','CANCELLED','SUPERSEDED')`
- Check: `source_type in ('MANUAL','IMPORT','AGENT_DRAFT')`
- Check: `end_date is null or start_date is null or end_date >= start_date`
- Index: `prescription(patient_id, status)`
- Index: `prescription(prescribed_by)`

Compatibility:

- Keep current `items` JSON column until DB-7 cutover.
- Keep current `doctor_id`, `approved_by`, `approved_at`, and `duration_days` until mapped.

## 6. Prescription Item

### `prescription_item`

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | uuid/text | no |  |
| `prescription_id` | uuid/text | no | Parent |
| `patient_id` | uuid/text | no | Denormalized for query/FK checks |
| `drug_product_id` | uuid/text | yes | Nullable until backfill complete |
| `legacy_drug_id` | text | yes | Legacy public slug |
| `drug_display_name` | text | no | Snapshot for display/backfill |
| `dose_text` | text | yes | Raw dose |
| `dose_value` | numeric | yes | Structured dose if reliable |
| `dose_unit` | text | yes | mg, vien, ml, etc. |
| `route` | text | yes | oral, topical, etc. |
| `frequency_text` | text | yes | Raw frequency |
| `instructions` | text | yes | Raw instructions |
| `start_date` | date | yes | Item-specific start |
| `end_date` | date | yes | Item-specific end |
| `status` | text | no | Item lifecycle |
| `created_at` | timestamptz | no |  |
| `updated_at` | timestamptz | no |  |

Constraints/indexes:

- PK: `prescription_item(id)`
- FK: `prescription_item.prescription_id -> prescription.id`
- FK: `prescription_item.patient_id -> patient.id`
- FK optional after Drug DB import: `prescription_item.drug_product_id -> drug_product.id`
- Check: `status in ('DRAFT','ACTIVE','STOPPED','CANCELLED','SUPERSEDED')`
- Check: `dose_value is null or dose_value > 0`
- Check: `end_date is null or start_date is null or end_date >= start_date`
- Index: `prescription_item(prescription_id)`
- Index: `prescription_item(patient_id, status)`
- Index: `prescription_item(drug_product_id)`
- Index: `prescription_item(legacy_drug_id)`

## 7. Medication Plan

### `medication_plan`

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | uuid/text | no |  |
| `patient_id` | uuid/text | no | Owner |
| `prescription_item_id` | uuid/text | yes | Nullable for non-prescription plans later |
| `drug_product_id` | uuid/text | yes | Nullable until backfill complete |
| `legacy_drug_id` | text | yes | Compatibility |
| `status` | text | no | Plan lifecycle |
| `timezone` | text | no | IANA timezone |
| `start_at` | timestamptz | no | UTC instant |
| `end_at` | timestamptz | yes | UTC instant |
| `instructions` | text | yes | Plan instructions |
| `created_at` | timestamptz | no |  |
| `updated_at` | timestamptz | no |  |

Constraints/indexes:

- PK: `medication_plan(id)`
- FK: `medication_plan.patient_id -> patient.id`
- FK: `medication_plan.prescription_item_id -> prescription_item.id`
- FK optional after Drug DB import: `medication_plan.drug_product_id -> drug_product.id`
- Check: `status in ('DRAFT','ACTIVE','PAUSED','COMPLETED','CANCELLED','SUPERSEDED')`
- Check: `end_at is null or end_at >= start_at`
- Unique recommended after cleanup: one active plan per active prescription item: partial unique `(prescription_item_id)` where status in `('ACTIVE','PAUSED')`
- Index: `medication_plan(patient_id, status)`
- Index: `medication_plan(prescription_item_id)`
- Index: `medication_plan(drug_product_id)`

## 8. Schedule Rule

### `schedule_rule`

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | uuid/text | no |  |
| `medication_plan_id` | uuid/text | no | Parent |
| `rule_type` | text | no | Rule class |
| `frequency` | integer | yes | Times per interval |
| `interval_value` | integer | yes | Every N units |
| `interval_unit` | text | yes | `HOUR`, `DAY`, `WEEK`, `MONTH` |
| `times_of_day` | jsonb | yes | Local times, e.g. `["08:00","20:00"]` |
| `days_of_week` | jsonb | yes | 1-7 or names |
| `day_of_month` | integer | yes | Monthly support |
| `start_at` | timestamptz | no | UTC instant |
| `end_at` | timestamptz | yes | UTC instant |
| `timezone` | text | no | IANA timezone |
| `status` | text | no | Rule lifecycle |
| `created_at` | timestamptz | no |  |
| `updated_at` | timestamptz | no |  |

Constraints/indexes:

- PK: `schedule_rule(id)`
- FK: `schedule_rule.medication_plan_id -> medication_plan.id`
- Check: `rule_type in ('DAILY','INTERVAL','WEEKLY','MONTHLY','CUSTOM')`
- Check: `status in ('ACTIVE','PAUSED','CANCELLED','SUPERSEDED')`
- Check: `frequency is null or frequency > 0`
- Check: `interval_value is null or interval_value > 0`
- Check: `interval_unit is null or interval_unit in ('HOUR','DAY','WEEK','MONTH')`
- Check: `end_at is null or end_at >= start_at`
- Index: `schedule_rule(medication_plan_id, status)`

## 9. Dose Occurrence

### `dose_occurrence`

One row equals one medicine / one scheduled dose.

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | uuid/text | no |  |
| `medication_plan_id` | uuid/text | no | Parent plan |
| `prescription_item_id` | uuid/text | yes | Denormalized trace |
| `patient_id` | uuid/text | no | Query owner |
| `drug_product_id` | uuid/text | yes | Nullable until backfill complete |
| `legacy_drug_id` | text | yes | Compatibility |
| `schedule_rule_id` | uuid/text | yes | Generator source |
| `scheduled_at` | timestamptz | no | Expected time |
| `due_at` | timestamptz | no | Reminder due time |
| `window_start` | timestamptz | yes | Acceptable early boundary |
| `window_end` | timestamptz | yes | Acceptable late boundary |
| `grace_until` | timestamptz | yes | Missed evaluation boundary |
| `status` | text | no | Current state |
| `status_reason` | text | yes | Machine-readable reason |
| `taken_at` | timestamptz | yes | Actual intake time |
| `generation_key` | text | no | Idempotency for generator |
| `created_at` | timestamptz | no |  |
| `updated_at` | timestamptz | no |  |

Constraints/indexes:

- PK: `dose_occurrence(id)`
- FK: `dose_occurrence.medication_plan_id -> medication_plan.id`
- FK: `dose_occurrence.prescription_item_id -> prescription_item.id`
- FK: `dose_occurrence.patient_id -> patient.id`
- FK: `dose_occurrence.schedule_rule_id -> schedule_rule.id`
- FK optional after Drug DB import: `dose_occurrence.drug_product_id -> drug_product.id`
- Check: `status in ('SCHEDULED','DUE','TAKEN','MISSED','SKIPPED','DELAYED','CANCELLED','AWAITING_REVIEW')`
- Check: `window_end is null or window_start is null or window_end >= window_start`
- Check: `grace_until is null or window_end is null or grace_until >= window_end`
- Check: `taken_at is null or status in ('TAKEN','DELAYED')`
- Unique: `dose_occurrence(generation_key)`
- Unique fallback: `(schedule_rule_id, medication_plan_id, scheduled_at)` where `schedule_rule_id is not null`
- Index: `dose_occurrence(medication_plan_id, scheduled_at)`
- Index: `dose_occurrence(patient_id, scheduled_at)`
- Index: `dose_occurrence(status, scheduled_at)`
- Index: `dose_occurrence(patient_id, status, scheduled_at)`
- Index: `dose_occurrence(drug_product_id)`

## 10. Immutable Dose Event

### `dose_event`

Target immutable table. In additive migration, use a non-conflicting physical name until the legacy MVP `dose_event` is retired.

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | uuid/text | no |  |
| `dose_occurrence_id` | uuid/text | no | Target occurrence |
| `patient_id` | uuid/text | no | Query owner |
| `medication_plan_id` | uuid/text | no | Denormalized trace |
| `drug_product_id` | uuid/text | yes | Nullable until backfill complete |
| `event_type` | text | no | Immutable action |
| `event_at` | timestamptz | no | When action happened |
| `source` | text | no | Source system |
| `actor_type` | text | no | Actor category |
| `actor_id` | uuid/text | yes | Account/patient/system ID |
| `idempotency_key` | text | yes | Idempotent event writes |
| `metadata` | jsonb | no | Default `{}` |
| `created_at` | timestamptz | no | Insert time |

Constraints/indexes:

- PK: `dose_event(id)`
- FK: `dose_event.dose_occurrence_id -> dose_occurrence.id`
- FK: `dose_event.patient_id -> patient.id`
- FK: `dose_event.medication_plan_id -> medication_plan.id`
- FK optional after Drug DB import: `dose_event.drug_product_id -> drug_product.id`
- Check: `event_type in ('TAKEN','SKIPPED','SNOOZED','MISSED_CONFIRMED','MISSED_AUTO_MARKED','DELAYED_CONFIRMED','MANUAL_CORRECTION','PHOTO_CONFIRMED','PHOTO_REJECTED','STATUS_ROLLBACK')`
- Check: `source in ('PATIENT_APP','CAREGIVER_APP','CLINICIAN_APP','PHOTO_VERIFICATION','SCHEDULER','AGENT','SYSTEM')`
- Check: `actor_type in ('PATIENT','CAREGIVER','CLINICIAN','SYSTEM','AGENT')`
- Unique nullable: `dose_event(idempotency_key)` where not null
- Index: `dose_event(dose_occurrence_id, created_at)`
- Index: `dose_event(patient_id, event_at)`
- Index: `dose_event(event_type, event_at)`

Append-only enforcement:

- Application must not update/delete rows.
- DB trigger can reject UPDATE/DELETE in a later hardening phase.

## 11. Notification Job

### `notification_job`

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | uuid/text | no |  |
| `patient_id` | uuid/text | no | Recipient patient context |
| `dose_occurrence_id` | uuid/text | yes | Nullable for non-dose safety alerts |
| `notification_type` | text | no | Type |
| `recipient_type` | text | no | Patient/caregiver/clinician |
| `recipient_id` | uuid/text | yes | Account ID when available |
| `scheduled_at` | timestamptz | no | Dispatch time |
| `status` | text | no | Queue status |
| `attempt_count` | integer | no | Default 0 |
| `last_attempt_at` | timestamptz | yes |  |
| `sent_at` | timestamptz | yes |  |
| `provider` | text | yes | SMS/push/email/provider |
| `provider_message_id` | text | yes | Provider trace |
| `idempotency_key` | text | no | Dispatch dedupe |
| `payload` | jsonb | no | Default `{}` |
| `created_at` | timestamptz | no |  |
| `updated_at` | timestamptz | no |  |

Constraints/indexes:

- PK: `notification_job(id)`
- FK: `notification_job.patient_id -> patient.id`
- FK: `notification_job.dose_occurrence_id -> dose_occurrence.id`
- Check: `notification_type in ('DOSE_REMINDER','MISSED_DOSE_FOLLOWUP','CAREGIVER_ESCALATION','CLINICIAN_ESCALATION','SAFETY_ALERT')`
- Check: `recipient_type in ('PATIENT','CAREGIVER','CLINICIAN','SYSTEM')`
- Check: `status in ('PENDING','CLAIMED','SENT','FAILED','CANCELLED','EXPIRED')`
- Check: `attempt_count >= 0`
- Unique: `notification_job(idempotency_key)`
- Index: `notification_job(status, scheduled_at)`
- Index: `notification_job(patient_id, scheduled_at)`
- Index: `notification_job(dose_occurrence_id)`
- Index: `notification_job(provider, provider_message_id)`

## 12. Medication Safety Policy

### `medication_safety_policy`

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | uuid/text | no |  |
| `scope_type` | text | no | Drug product, ingredient, category |
| `scope_id` | text | no | Scope identifier |
| `risk_type` | text | no | Missed/delayed/etc. |
| `risk_level` | text | no | Risk level |
| `action_policy` | text | no | App action |
| `source_type` | text | no | Provenance |
| `source_reference` | text | yes | Document/rule/version |
| `review_status` | text | no | Clinical review state |
| `policy_version` | integer | no | Starts at 1 |
| `valid_from` | timestamptz | no |  |
| `valid_to` | timestamptz | yes |  |
| `created_by` | uuid/text | yes | Account/system |
| `reviewed_by` | uuid/text | yes | Account/system |
| `reviewed_at` | timestamptz | yes |  |
| `created_at` | timestamptz | no |  |
| `updated_at` | timestamptz | no |  |

Constraints/indexes:

- PK: `medication_safety_policy(id)`
- Check: `scope_type in ('DRUG_PRODUCT','INGREDIENT','CATEGORY')`
- Check: `risk_type in ('MISSED_DOSE','DELAYED_DOSE','INTERACTION','CONTRAINDICATION','PREGNANCY')`
- Check: `risk_level in ('LOW','MODERATE','HIGH','CRITICAL','UNKNOWN')`
- Check: `action_policy in ('LOG_ONLY','REMIND','WARN','ESCALATE_CAREGIVER','ESCALATE_CLINICIAN','REQUIRE_MEDICAL_REVIEW')`
- Check: `source_type in ('CLINICAL_REVIEW','DRUG_LABEL','GUIDELINE','LEGACY_CATEGORY_RULE','SYSTEM_DEFAULT')`
- Check: `review_status in ('LEGACY_UNREVIEWED','REVIEW_REQUIRED','REVIEWED','REJECTED','RETIRED')`
- Check: `policy_version > 0`
- Check: `valid_to is null or valid_to > valid_from`
- Unique active policy: `(scope_type, scope_id, risk_type, policy_version)`
- Index: `medication_safety_policy(scope_type, scope_id, risk_type)`
- Index: `medication_safety_policy(risk_type, review_status)`
- Index: `medication_safety_policy(valid_from, valid_to)`

Legacy severity guard:

- Add check or application rule: if `source_type='LEGACY_CATEGORY_RULE'`, then `scope_type='CATEGORY'` and `review_status='LEGACY_UNREVIEWED'`.

## 13. Missed Dose Assessment

### `missed_dose_assessment`

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | uuid/text | no |  |
| `patient_id` | uuid/text | no |  |
| `dose_occurrence_id` | uuid/text | no |  |
| `medication_plan_id` | uuid/text | no |  |
| `drug_product_id` | uuid/text | yes | Nullable until backfill complete |
| `risk_type` | text | no | Usually missed/delayed |
| `risk_level` | text | no | Resolved level |
| `recommended_action` | text | no | App action |
| `policy_id` | uuid/text | yes | Matched policy |
| `reason_code` | text | no | Why this action |
| `assessment_version` | text | no | Evaluator version |
| `evaluator` | text | no | `POLICY_ENGINE`, etc. |
| `evaluated_at` | timestamptz | no |  |
| `created_at` | timestamptz | no |  |

Constraints/indexes:

- PK: `missed_dose_assessment(id)`
- FK: `missed_dose_assessment.patient_id -> patient.id`
- FK: `missed_dose_assessment.dose_occurrence_id -> dose_occurrence.id`
- FK: `missed_dose_assessment.medication_plan_id -> medication_plan.id`
- FK: `missed_dose_assessment.policy_id -> medication_safety_policy.id`
- FK optional after Drug DB import: `missed_dose_assessment.drug_product_id -> drug_product.id`
- Check: risk/action enums match policy enums
- Check: `reason_code in ('POLICY_DRUG_PRODUCT_MATCH','POLICY_INGREDIENT_MATCH','POLICY_CATEGORY_FALLBACK','NO_POLICY_SAFE_FALLBACK','AMBIGUOUS_DRUG_ID','POLICY_REVIEW_REQUIRED','LEGACY_UNREVIEWED_FALLBACK')`
- Index: `missed_dose_assessment(dose_occurrence_id, evaluated_at)`
- Index: `missed_dose_assessment(patient_id, evaluated_at)`
- Index: `missed_dose_assessment(policy_id)`

## 14. Safety Event

### `safety_event`

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | uuid/text | no |  |
| `patient_id` | uuid/text | no |  |
| `conversation_id` | uuid/text | yes | Nullable for scheduler events |
| `dose_occurrence_id` | uuid/text | yes | Nullable for non-dose events |
| `drug_product_id` | uuid/text | yes | Nullable |
| `missed_dose_assessment_id` | uuid/text | yes | Nullable |
| `event_type` | text | no | Event class |
| `severity` | text | no | Severity |
| `decision` | text | no | App decision |
| `reason` | text | yes | Human-readable summary |
| `source` | text | no | Origin |
| `metadata` | jsonb | no | Default `{}` |
| `created_at` | timestamptz | no |  |

Constraints/indexes:

- PK: `safety_event(id)`
- FK: `safety_event.patient_id -> patient.id`
- FK: `safety_event.conversation_id -> conversation.id`
- FK: `safety_event.dose_occurrence_id -> dose_occurrence.id`
- FK: `safety_event.missed_dose_assessment_id -> missed_dose_assessment.id`
- FK optional after Drug DB import: `safety_event.drug_product_id -> drug_product.id`
- Check: `event_type in ('MISSED_HIGH_RISK_DOSE','DELAYED_HIGH_RISK_DOSE','RED_FLAG_SYMPTOM','DRUG_INTERACTION_WARNING','AMBIGUOUS_DRUG','PHOTO_MISMATCH_REVIEW','CAREGIVER_ESCALATION_CREATED','CLINICIAN_ESCALATION_CREATED')`
- Check: `severity in ('INFO','LOW','MODERATE','HIGH','CRITICAL')`
- Check: `source in ('POLICY_ENGINE','AGENT','PHOTO_VERIFICATION','SCHEDULER','USER_REPORT','SYSTEM')`
- Index: `safety_event(patient_id, created_at)`
- Index: `safety_event(event_type, created_at)`
- Index: `safety_event(dose_occurrence_id)`
- Index: `safety_event(missed_dose_assessment_id)`

## 15. Conversation And Agent Audit

### `conversation`

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | uuid/text | no |  |
| `patient_id` | uuid/text | no |  |
| `status` | text | no | `ACTIVE`, `CLOSED`, `ARCHIVED` |
| `started_at` | timestamptz | no |  |
| `last_message_at` | timestamptz | yes |  |
| `created_at` | timestamptz | no |  |

Indexes:

- `conversation(patient_id, started_at)`
- `conversation(status, last_message_at)`

### `message`

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | uuid/text | no |  |
| `conversation_id` | uuid/text | no |  |
| `role` | text | no | `USER`, `ASSISTANT`, `SYSTEM`, `TOOL` |
| `content` | text | no | Display content |
| `metadata` | jsonb | no | Default `{}` |
| `created_at` | timestamptz | no |  |

Indexes:

- `message(conversation_id, created_at)`

### `agent_run`

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | uuid/text | no |  |
| `conversation_id` | uuid/text | yes | Nullable for non-chat runs |
| `patient_id` | uuid/text | yes |  |
| `request_id` | text | yes | Trace/idempotency |
| `intent` | text | yes | Classified intent |
| `status` | text | no | `STARTED`, `SUCCEEDED`, `FAILED`, `CANCELLED` |
| `started_at` | timestamptz | no |  |
| `completed_at` | timestamptz | yes |  |
| `metadata` | jsonb | no | No chain-of-thought |
| `created_at` | timestamptz | no |  |

Indexes:

- `agent_run(conversation_id, started_at)`
- `agent_run(patient_id, started_at)`
- `agent_run(request_id)`

### `agent_tool_event`

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | uuid/text | no |  |
| `agent_run_id` | uuid/text | no |  |
| `tool_name` | text | no |  |
| `input_reference` | text/jsonb | yes | Sanitized reference or summary |
| `output_reference` | text/jsonb | yes | Sanitized reference or summary |
| `status` | text | no | `STARTED`, `SUCCEEDED`, `FAILED`, `SKIPPED` |
| `latency_ms` | integer | yes |  |
| `created_at` | timestamptz | no |  |

Indexes:

- `agent_tool_event(agent_run_id, created_at)`
- `agent_tool_event(tool_name, created_at)`

## 16. Generic Audit Log

### `audit_log`

Target generic shape:

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | uuid/text | no |  |
| `actor_type` | text | no |  |
| `actor_id` | uuid/text | yes |  |
| `entity_type` | text | no |  |
| `entity_id` | uuid/text | no |  |
| `action` | text | no |  |
| `before_snapshot` | jsonb | yes |  |
| `after_snapshot` | jsonb | yes |  |
| `request_id` | text | yes |  |
| `created_at` | timestamptz | no |  |

Compatibility:

- Existing `audit_log` can be retained as `agent_audit_log` semantics or migrated into the generic table later.
- Do not lose existing utterance/trace/final_response data during design.

## 17. Compatibility Views / Adapter Outputs

Design target read projections before public API cutover:

### Prescription DTO

V2 source:

```text
prescription
+ prescription_item[]
+ drug display via facade
```

Legacy response:

```text
prescription.items[] with legacy drug_id
```

### Dose DTO

V2 source:

```text
dose_occurrence rows grouped by patient local time
```

Legacy response:

```text
one grouped item with expected_items[]
```

### Photo DTO

V2 source:

```text
photo_verification
+ one or more dose_occurrence mappings
+ dose_event rows
```

Legacy response:

```text
current dose photo status shape
```

## 18. Constraint Rollout Strategy

Because DB-1 found dirty-data risk, enforce constraints in stages:

1. Add nullable columns and new tables.
2. Backfill with validation reports.
3. Add indexes concurrently where supported.
4. Add FKs as nullable or `NOT VALID` first.
5. Validate FKs after cleanup.
6. Add stricter `NOT NULL` and enum checks.
7. Retire legacy columns/tables only after stabilization and rollback window.

## 19. Required Index Summary

High-priority operational indexes:

- `prescription(patient_id, status)`
- `prescription_item(patient_id, status)`
- `medication_plan(patient_id, status)`
- `schedule_rule(medication_plan_id, status)`
- `dose_occurrence(medication_plan_id, scheduled_at)`
- `dose_occurrence(patient_id, scheduled_at)`
- `dose_occurrence(status, scheduled_at)`
- `dose_occurrence(patient_id, status, scheduled_at)`
- `dose_event(dose_occurrence_id, created_at)`
- `dose_event(patient_id, event_at)`
- `notification_job(status, scheduled_at)`
- `notification_job(patient_id, scheduled_at)`
- `medication_safety_policy(scope_type, scope_id, risk_type)`
- `missed_dose_assessment(dose_occurrence_id, evaluated_at)`
- `safety_event(patient_id, created_at)`
- `conversation(patient_id, started_at)`
- `message(conversation_id, created_at)`
- `agent_run(patient_id, started_at)`

## 20. Schema Design Readiness

This target schema is ready for DB-3 migration design after the team confirms:

- physical naming strategy for legacy MVP `dose_event` vs V2 immutable `dose_event`
- UUID/text primary-key standard
- local DB import timing for Drug Knowledge V2 tables
- compatibility DTO adapter scope
- FK rollout tolerance for existing dev/demo data

