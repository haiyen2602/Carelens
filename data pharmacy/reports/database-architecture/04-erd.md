# 04 ERD

Scope: Database Architecture V2, Phase DB-2. This ERD is a target design artifact only. It does not create or modify database schema.

## 1. Core ERD

```mermaid
erDiagram
    ACCOUNT ||--o| PATIENT : "user_id"

    PATIENT ||--o{ PRESCRIPTION : owns
    PRESCRIPTION ||--o{ PRESCRIPTION_ITEM : contains

    DRUG_PRODUCT ||--o{ PRESCRIPTION_ITEM : referenced_by
    DRUG_PRODUCT ||--o{ MEDICATION_PLAN : referenced_by
    DRUG_PRODUCT ||--o{ DOSE_OCCURRENCE : referenced_by
    DRUG_PRODUCT ||--o{ DOSE_EVENT : referenced_by

    PRESCRIPTION_ITEM ||--o{ MEDICATION_PLAN : creates
    MEDICATION_PLAN ||--o{ SCHEDULE_RULE : has
    MEDICATION_PLAN ||--o{ DOSE_OCCURRENCE : generates
    SCHEDULE_RULE ||--o{ DOSE_OCCURRENCE : generates

    DOSE_OCCURRENCE ||--o{ DOSE_EVENT : records
    DOSE_OCCURRENCE ||--o{ NOTIFICATION_JOB : schedules
    DOSE_OCCURRENCE ||--o{ MISSED_DOSE_ASSESSMENT : assessed_by

    MEDICATION_SAFETY_POLICY ||--o{ MISSED_DOSE_ASSESSMENT : applied_by
    MISSED_DOSE_ASSESSMENT ||--o{ SAFETY_EVENT : produces

    PATIENT ||--o{ CONVERSATION : has
    CONVERSATION ||--o{ MESSAGE : contains
    CONVERSATION ||--o{ AGENT_RUN : traces
    AGENT_RUN ||--o{ AGENT_TOOL_EVENT : contains

    PATIENT ||--o{ SAFETY_EVENT : has
    PATIENT ||--o{ NOTIFICATION_JOB : receives_context
```

## 2. Safety Policy ERD

`medication_safety_policy.scope_id` is polymorphic by design. The resolver chooses the most specific matching policy.

```mermaid
erDiagram
    DRUG_CATEGORY ||--o{ MEDICATION_SAFETY_POLICY : category_scope
    INGREDIENT ||--o{ MEDICATION_SAFETY_POLICY : ingredient_scope
    DRUG_PRODUCT ||--o{ MEDICATION_SAFETY_POLICY : product_scope

    DRUG_PRODUCT ||--o{ DRUG_PRODUCT_INGREDIENT : has
    INGREDIENT ||--o{ DRUG_PRODUCT_INGREDIENT : appears_in

    MEDICATION_SAFETY_POLICY ||--o{ MISSED_DOSE_ASSESSMENT : selected_for
    MISSED_DOSE_ASSESSMENT ||--o{ SAFETY_EVENT : may_create
```

Resolution priority:

```text
DRUG_PRODUCT policy
  -> INGREDIENT policy
  -> CATEGORY fallback policy
  -> UNKNOWN / safe fallback
```

Category fallback must never override drug-product or ingredient policy.

## 3. Dose Occurrence Granularity

Target:

```text
Patient takes 3 medicines at 08:00

UI group: 08:00
  - dose_occurrence A: drug 1, one dose
  - dose_occurrence B: drug 2, one dose
  - dose_occurrence C: drug 3, one dose
```

ERD consequence:

- `dose_occurrence` belongs to one `medication_plan`.
- `dose_occurrence` references one `drug_product_id` when known.
- Grouping by same local time is a projection, not a persisted replacement for occurrences.

## 4. Prescription To Schedule Flow

```mermaid
flowchart TD
    A[Prescription] --> B[Prescription Item]
    B --> C[Medication Plan]
    C --> D[Schedule Rule]
    D --> E[Dose Occurrence]
    E --> F[Notification Job]
    E --> G[Immutable Dose Event]
    E --> H[Missed Dose Assessment]
    H --> I[Safety Event]
```

Important split:

- `prescription_item` records what was prescribed.
- `medication_plan` records the actionable patient plan.
- `schedule_rule` records generation logic.
- `dose_occurrence` records current expected dose state.
- `dose_event` records immutable behavior/history.

## 5. Legacy Compatibility ERD

During additive migration:

```mermaid
erDiagram
    LEGACY_PRESCRIPTION ||--o{ LEGACY_DOSE_EVENT : generated
    LEGACY_PRESCRIPTION {
        text id
        jsonb items
    }
    LEGACY_DOSE_EVENT {
        text id
        jsonb expected_items
        text status
    }

    PRESCRIPTION ||--o{ PRESCRIPTION_ITEM : contains
    PRESCRIPTION_ITEM ||--o{ MEDICATION_PLAN : creates
    MEDICATION_PLAN ||--o{ DOSE_OCCURRENCE : generates

    LEGACY_PRESCRIPTION ||..o{ PRESCRIPTION_ITEM : "backfill/adapter"
    LEGACY_DOSE_EVENT ||..o{ DOSE_OCCURRENCE : "backfill/adapter"
```

Compatibility rules:

- Legacy `prescription.items[]` maps to `prescription_item`.
- Legacy grouped `dose_event.expected_items[]` maps to multiple `dose_occurrence` rows.
- Public `drug_id` remains `legacy_drug_id`.
- New internal references use nullable `drug_product_id` until backfill is complete.

## 6. Cardinality Notes

Patient:

- One `account` may link to one `patient` for patient users.
- One `patient` has many prescriptions, medication plans, occurrences, notifications, safety events, conversations.

Prescription:

- One `prescription` has many `prescription_item` rows.
- One `prescription_item` generally creates one `medication_plan`, but future revisions may allow multiple plans if a medicine has split phases.

Medication scheduling:

- One `medication_plan` has one or more `schedule_rule` rows.
- One `schedule_rule` generates many `dose_occurrence` rows.
- One `dose_occurrence` has many immutable `dose_event` rows.

Notification:

- One `dose_occurrence` may have many notification jobs.
- A notification job may be unrelated to a dose only for general safety alerts.

Safety:

- One `missed_dose_assessment` references at most one selected policy.
- One assessment may create zero or more safety events.
- One safety event may reference a conversation, dose occurrence, assessment, and drug product, but should be understandable even if some references are absent.

Agent:

- One conversation has many messages.
- One conversation may have many agent runs.
- One agent run has many agent tool events.

## 7. Delete And Retention Model

Recommended:

- No hard delete for prescriptions, prescription items, medication plans, dose occurrences, dose events, safety events, assessments, or audit logs.
- Use lifecycle statuses such as `CANCELLED`, `SUPERSEDED`, `ARCHIVED`.
- Medication Safety Policy versions should be retired by `valid_to` or `review_status=RETIRED`, not overwritten.

## 8. ERD Risks

- The physical table name `dose_event` collides with the current MVP table. Migration design must handle this explicitly.
- Polymorphic `medication_safety_policy.scope_id` is flexible but cannot enforce all FKs at DB level unless separate scoped tables or nullable scope columns are used.
- Compatibility UI grouping must be implemented carefully so grouped display does not leak back into domain storage.

