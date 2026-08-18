# 02 Domain Model

Scope: Database Architecture V2, Phase DB-2. This document designs the target domain model only. No code, migration, schema deployment, or Railway deploy is included.

Inputs:

- `docs/data/database_architecture_v2_plan.md`
- `data pharmacy/reports/database-architecture/01-current-db-audit.md`

## 1. Architecture Principle

Database V2 separates four domain areas:

```text
Drug Knowledge
  -> Patient / Prescription
  -> Medication Scheduling
  -> Safety / Agent / Notification
```

Operational patient tables reference Drug Knowledge by ID. They do not copy the full drug knowledge payload.

During migration, public/API `drug_id` remains the legacy slug. New operational tables prepare `drug_product_id` as the canonical reference to Drug Knowledge V2.

## 2. Domain Boundaries

### Drug Knowledge

Owns canonical medicine identity and knowledge:

- `drug_product`
- `ingredient`
- `drug_product_ingredient`
- `drug_knowledge`
- `drug_id_map`

DB-2 does not redesign Final Canonical Drug V2 content. It only defines how operational data references it.

### Patient / Prescription

Owns the clinician-entered intent:

- `patient`
- `prescription`
- `prescription_item`

Prescription data is not a reminder log. It should express what was prescribed, including raw text when structured parsing is uncertain.

### Medication Scheduling

Owns the patient's actionable medication plan:

- `medication_plan`
- `schedule_rule`
- `dose_occurrence`
- immutable `dose_event`

This domain is the source of truth for due doses and dose status.

### Notification

Owns dispatch attempts and reminder jobs:

- `notification_job`

Notification does not own dose status. It references `dose_occurrence` and records dispatch state only.

### Safety

Owns missed/delayed dose policy and auditable safety decisions:

- `medication_safety_policy`
- `missed_dose_assessment`
- `safety_event`

Safety policy must never treat legacy category severity as clinical truth.

### Conversation / Agent Audit

Owns conversation and agent observability:

- `conversation`
- `message`
- `agent_run`
- `agent_tool_event`
- generic `audit_log`

Conversation history is context, not a medical source of truth. Important decisions must be stored in domain tables.

## 3. Core Decision: Dose Occurrence Granularity

`dose_occurrence` is one medicine / one scheduled dose.

That means:

- If a patient has 3 medicines at 08:00, V2 stores 3 `dose_occurrence` rows.
- The UI may group them into one visual "08:00 medication group".
- Photo verification may accept one uploaded image for a UI group, but backend must map the result to individual occurrences.
- Safety assessment is per medicine occurrence because risk depends on the drug/ingredient/policy.

This replaces the current MVP behavior where multiple drugs at the same hour are grouped into one mutable `dose_event.expected_items` JSON row.

## 4. Patient

### Entity

`patient` represents the care subject.

Target fields:

- `id`
- `user_id`
- `display_name`
- `date_of_birth`
- `sex`
- `timezone`
- `status`
- `created_at`
- `updated_at`

### Status

- `ACTIVE`
- `INACTIVE`
- `ARCHIVED`

### Invariants

- `timezone` is required for all scheduling decisions.
- `user_id` links the patient profile to the auth/account domain where applicable.
- Medical operational rows should reference `patient.id`, not account-specific identifiers.

### Compatibility Notes

Current `patient.full_name`, `year_of_birth`, `gender`, `height_cm`, `weight_kg`, `doctor_id`, `note`, and `watch` can remain during migration. V2 should not drop them in additive phases.

## 5. Prescription

### Entity

`prescription` is the prescription header.

It represents clinician intent and lifecycle, not generated reminders.

Target fields:

- `id`
- `patient_id`
- `status`
- `prescribed_by`
- `prescribed_at`
- `start_date`
- `end_date`
- `notes`
- `source_type`
- `created_at`
- `updated_at`

### Status

- `DRAFT`
- `ACTIVE`
- `COMPLETED`
- `CANCELLED`
- `SUPERSEDED`

### Invariants

- A prescription belongs to exactly one patient.
- Active prescriptions must have at least one active `prescription_item`.
- Date ranges are calendar-date concepts; generated occurrences use timezone-aware timestamps.

### Compatibility Notes

The current `prescription.items` JSON is kept during the compatibility phase and projected into `prescription_item` by an adapter/backfill. Public API responses can continue returning the current `items` shape until the frontend is updated.

## 6. Prescription Item

### Entity

`prescription_item` is one medication line in a prescription.

Target fields:

- `id`
- `prescription_id`
- `drug_product_id`
- `legacy_drug_id`
- `drug_display_name`
- `dose_text`
- `dose_value`
- `dose_unit`
- `route`
- `frequency_text`
- `instructions`
- `start_date`
- `end_date`
- `status`
- `created_at`
- `updated_at`

### Status

- `DRAFT`
- `ACTIVE`
- `STOPPED`
- `CANCELLED`
- `SUPERSEDED`

### Invariants

- `dose_text` preserves the raw prescribed dose.
- Structured dose fields are nullable and used only when parsing is reliable.
- `drug_product_id` is the target reference.
- `legacy_drug_id` is kept for API compatibility and backfill traceability.
- `drug_display_name` is a display snapshot, not canonical knowledge.

## 7. Medication Plan

### Entity

`medication_plan` is the actionable plan for one prescribed medicine.

Target fields:

- `id`
- `patient_id`
- `prescription_item_id`
- `drug_product_id`
- `legacy_drug_id`
- `status`
- `timezone`
- `start_at`
- `end_at`
- `instructions`
- `created_at`
- `updated_at`

### Status

- `DRAFT`
- `ACTIVE`
- `PAUSED`
- `COMPLETED`
- `CANCELLED`
- `SUPERSEDED`

### Invariants

- One medication plan references one medication.
- A plan may be derived from one prescription item.
- A plan can be paused or superseded without mutating historical occurrences/events.
- `timezone` is required and copied from patient timezone at creation unless explicitly overridden.

### Compatibility Notes

During migration, each legacy `prescription.items[]` should generally create one `prescription_item` and one `medication_plan`.

## 8. Schedule Rule

### Entity

`schedule_rule` describes how dose occurrences are generated.

Target fields:

- `id`
- `medication_plan_id`
- `rule_type`
- `frequency`
- `interval_value`
- `interval_unit`
- `times_of_day`
- `days_of_week`
- `day_of_month`
- `start_at`
- `end_at`
- `timezone`
- `status`
- `created_at`
- `updated_at`

### Rule Type

- `DAILY`
- `INTERVAL`
- `WEEKLY`
- `MONTHLY`
- `CUSTOM`

### Status

- `ACTIVE`
- `PAUSED`
- `CANCELLED`
- `SUPERSEDED`

### Invariants

- Rules generate occurrences; they do not record patient behavior.
- Ambiguous prescriptions must stay draft or require human review. Agent/LLM must not invent clinical schedules.
- Rule timezone is explicit.

## 9. Dose Occurrence

### Entity

`dose_occurrence` is one scheduled dose for one medication plan.

Target fields:

- `id`
- `medication_plan_id`
- `prescription_item_id`
- `patient_id`
- `drug_product_id`
- `legacy_drug_id`
- `schedule_rule_id`
- `scheduled_at`
- `due_at`
- `window_start`
- `window_end`
- `grace_until`
- `status`
- `status_reason`
- `taken_at`
- `created_at`
- `updated_at`

### Status

- `SCHEDULED`
- `DUE`
- `TAKEN`
- `MISSED`
- `SKIPPED`
- `DELAYED`
- `CANCELLED`
- `AWAITING_REVIEW`

### Invariants

- One row is one drug/one dose. Never group multiple medicines into one row.
- `scheduled_at`, `due_at`, window fields, and `grace_until` are UTC timestamps.
- `taken_at` is nullable and set only when final status represents actual intake.
- Current state lives here.
- History lives in immutable `dose_event`.

### UI Grouping

UI grouping can be a query/projection:

```text
patient_id + local_date + local_time_bucket
```

The group is not a persisted medical entity unless later needed for photo workflows. Even then, it should be a separate UX/evidence entity, not a replacement for per-drug occurrences.

## 10. Immutable Dose Event

### Entity

`dose_event` is append-only patient/action history.

Target fields:

- `id`
- `dose_occurrence_id`
- `patient_id`
- `medication_plan_id`
- `drug_product_id`
- `event_type`
- `event_at`
- `source`
- `actor_type`
- `actor_id`
- `idempotency_key`
- `metadata`
- `created_at`

### Event Type

- `TAKEN`
- `SKIPPED`
- `SNOOZED`
- `MISSED_CONFIRMED`
- `MISSED_AUTO_MARKED`
- `DELAYED_CONFIRMED`
- `MANUAL_CORRECTION`
- `PHOTO_CONFIRMED`
- `PHOTO_REJECTED`
- `STATUS_ROLLBACK`

### Source

- `PATIENT_APP`
- `CAREGIVER_APP`
- `CLINICIAN_APP`
- `PHOTO_VERIFICATION`
- `SCHEDULER`
- `AGENT`
- `SYSTEM`

### Invariants

- Rows are immutable after insertion.
- Events can update `dose_occurrence.status` in the same transaction.
- Event metadata may reference photo verification IDs, assessment IDs, request IDs, or UI group IDs.
- No chain-of-thought is stored.

## 11. Notification Job

### Entity

`notification_job` stores planned and attempted notifications.

Target fields:

- `id`
- `patient_id`
- `dose_occurrence_id`
- `notification_type`
- `recipient_type`
- `recipient_id`
- `scheduled_at`
- `status`
- `attempt_count`
- `last_attempt_at`
- `sent_at`
- `provider`
- `provider_message_id`
- `idempotency_key`
- `payload`
- `created_at`
- `updated_at`

### Notification Type

- `DOSE_REMINDER`
- `MISSED_DOSE_FOLLOWUP`
- `CAREGIVER_ESCALATION`
- `CLINICIAN_ESCALATION`
- `SAFETY_ALERT`

### Status

- `PENDING`
- `CLAIMED`
- `SENT`
- `FAILED`
- `CANCELLED`
- `EXPIRED`

### Invariants

- Notification jobs do not determine dose status.
- Cancelling a dose should cancel future pending notification jobs for that occurrence.
- Provider callbacks must use idempotency.

## 12. Medication Safety Policy

### Entity

`medication_safety_policy` defines auditable, versioned safety behavior.

Target fields:

- `id`
- `scope_type`
- `scope_id`
- `risk_type`
- `risk_level`
- `action_policy`
- `source_type`
- `source_reference`
- `review_status`
- `policy_version`
- `valid_from`
- `valid_to`
- `created_by`
- `reviewed_by`
- `reviewed_at`
- `created_at`
- `updated_at`

### Scope Type

- `DRUG_PRODUCT`
- `INGREDIENT`
- `CATEGORY`

### Risk Type

- `MISSED_DOSE`
- `DELAYED_DOSE`
- `INTERACTION`
- `CONTRAINDICATION`
- `PREGNANCY`

### Risk Level

- `LOW`
- `MODERATE`
- `HIGH`
- `CRITICAL`
- `UNKNOWN`

### Action Policy

- `LOG_ONLY`
- `REMIND`
- `WARN`
- `ESCALATE_CAREGIVER`
- `ESCALATE_CLINICIAN`
- `REQUIRE_MEDICAL_REVIEW`

### Review Status

- `LEGACY_UNREVIEWED`
- `REVIEW_REQUIRED`
- `REVIEWED`
- `REJECTED`
- `RETIRED`

### Source Type

- `CLINICAL_REVIEW`
- `DRUG_LABEL`
- `GUIDELINE`
- `LEGACY_CATEGORY_RULE`
- `SYSTEM_DEFAULT`

### Invariants

- `muc_nghiem_trong` may only enter this table as `scope_type=CATEGORY`, `source_type=LEGACY_CATEGORY_RULE`, `review_status=LEGACY_UNREVIEWED`.
- Category fallback never overrides ingredient or drug-product policy.
- Unknown or unreviewed policy must produce conservative behavior, not specific medical dosing instructions.

## 13. Missed Dose Assessment

### Entity

`missed_dose_assessment` stores the evaluator output when a dose is late, missed, delayed, or safety-relevant.

Target fields:

- `id`
- `patient_id`
- `dose_occurrence_id`
- `medication_plan_id`
- `drug_product_id`
- `risk_type`
- `risk_level`
- `recommended_action`
- `policy_id`
- `reason_code`
- `assessment_version`
- `evaluator`
- `evaluated_at`
- `created_at`

### Reason Code

- `POLICY_DRUG_PRODUCT_MATCH`
- `POLICY_INGREDIENT_MATCH`
- `POLICY_CATEGORY_FALLBACK`
- `NO_POLICY_SAFE_FALLBACK`
- `AMBIGUOUS_DRUG_ID`
- `POLICY_REVIEW_REQUIRED`
- `LEGACY_UNREVIEWED_FALLBACK`

### Invariants

- Assessment is a durable record of the decision basis.
- Assessment does not overwrite policy.
- Recommended action cannot include specific clinical catch-up instructions unless backed by reviewed policy.

## 14. Safety Event

### Entity

`safety_event` stores safety-relevant events and decisions for audit/escalation.

Target fields:

- `id`
- `patient_id`
- `conversation_id`
- `dose_occurrence_id`
- `drug_product_id`
- `missed_dose_assessment_id`
- `event_type`
- `severity`
- `decision`
- `reason`
- `source`
- `metadata`
- `created_at`

### Event Type

- `MISSED_HIGH_RISK_DOSE`
- `DELAYED_HIGH_RISK_DOSE`
- `RED_FLAG_SYMPTOM`
- `DRUG_INTERACTION_WARNING`
- `AMBIGUOUS_DRUG`
- `PHOTO_MISMATCH_REVIEW`
- `CAREGIVER_ESCALATION_CREATED`
- `CLINICIAN_ESCALATION_CREATED`

### Severity

- `INFO`
- `LOW`
- `MODERATE`
- `HIGH`
- `CRITICAL`

### Invariants

- Safety events are append-only.
- They can reference dose/assessment/conversation but must remain understandable without reading chat history.
- Existing `escalation` rows can be mapped to safety events plus notification jobs later.

## 15. Compatibility Model

### Legacy API Compatibility

During DB-3/DB-4:

- Public `drug_id` remains legacy slug.
- Prescription create/update/list/get can continue accepting/returning `items` JSON.
- Dose list can keep returning UI grouped times by grouping V2 `dose_occurrence` rows.
- Photo upload can accept the existing dose identifier during a transition, but the adapter must map it to one or more V2 occurrences.

### Internal V2 Read Model

The compatibility adapter should expose:

- `PrescriptionWithItems`
- `MedicationPlanView`
- `DoseGroupView`
- `DoseOccurrenceView`
- `SafetyAssessmentView`

### Drug Identity

All new operational rows should store both:

- `drug_product_id` nullable during migration, required after backfill/stabilization.
- `legacy_drug_id` retained for public API compatibility and traceability.

## 16. Transaction Boundaries

Create prescription:

```text
prescription
+ prescription_item[]
+ audit_log
```

Activate medication plan:

```text
prescription.status = ACTIVE
+ prescription_item.status = ACTIVE
+ medication_plan[]
+ schedule_rule[]
+ initial dose_occurrence[]
+ audit_log
```

Generate occurrences:

```text
schedule_rule
+ dose_occurrence[]
+ idempotency key enforcement
```

Mark dose taken:

```text
dose_event(TAKEN or PHOTO_CONFIRMED)
+ dose_occurrence.status = TAKEN
+ cancel pending notification_job
+ optional safety_event
```

Mark missed/delayed:

```text
dose_event(MISSED_AUTO_MARKED or DELAYED_CONFIRMED)
+ dose_occurrence.status
+ missed_dose_assessment
+ safety_event if needed
+ notification_job if needed
```

Safety escalation:

```text
missed_dose_assessment
+ safety_event
+ notification_job
+ legacy escalation adapter during migration
```

## 17. Idempotency Model

Idempotency keys are needed for:

- dose occurrence generation
- dose event writes
- notification dispatch
- provider callbacks
- background photo verification completion
- escalation creation

Recommended key patterns:

- Occurrence generation: `schedule_rule_id + scheduled_at + drug_product_id`
- Dose event write: caller-supplied request ID or `dose_occurrence_id + event_type + source + external_event_id`
- Notification: `dose_occurrence_id + notification_type + recipient_type + recipient_id + scheduled_at`
- Photo callback: `photo_verification_id + attempt + result_version`

## 18. Read Models

### Today's UI Schedule

Query V2 `dose_occurrence` by patient/date/status, then group by local time in service/UI.

### Caregiver Dashboard

Query pending safety events, notification jobs, and dose occurrence statuses, not legacy `dose_event.expected_items`.

### Agent Personal Schedule Tool

Read `dose_occurrence` + `medication_plan` + `prescription_item` and resolve display names through the drug facade.

### Adherence Report

Use `dose_occurrence` status for current snapshot and `dose_event` for explanation/history.

## 19. Non-Goals

- No Alembic migration in DB-2.
- No runtime code implementation.
- No Railway deployment.
- No modification to Final Canonical Drug V2 artifacts.
- No clinical review of legacy severity.
- No LangSmith design in this phase.

