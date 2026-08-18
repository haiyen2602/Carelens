# 05 Safety Policy Model

Scope: Database Architecture V2, Phase DB-2. This document defines the target medication safety policy model and final readiness notes for DB-2. It is design only: no code, migration, schema deployment, or Railway deploy.

## 1. Goal

Replace implicit legacy severity behavior with an explicit, auditable, versioned safety policy model.

The model must support:

- missed dose risk
- delayed dose risk
- future interaction/contraindication/pregnancy risk
- safety escalation decisions
- agent/tool audit without storing chain-of-thought
- compatibility with legacy `muc_nghiem_trong` as category fallback only

## 2. Non-Negotiable Rule For `muc_nghiem_trong`

`muc_nghiem_trong` is not clinical truth.

It may only be migrated later as:

```text
scope_type = CATEGORY
risk_type = MISSED_DOSE
source_type = LEGACY_CATEGORY_RULE
review_status = LEGACY_UNREVIEWED
```

It must not be migrated as:

- reviewed clinical policy
- drug-product-specific fact
- ingredient-specific fact
- instruction for what the patient should medically do after missing a dose

The safety engine may use it only as a last-resort category fallback and should communicate uncertainty conservatively.

## 3. Policy Scope

Safety policy is scoped by specificity.

### `DRUG_PRODUCT`

Most specific. Applies to one canonical V2 drug product.

Use for clinically reviewed medicine-specific missed/delayed dose behavior.

### `INGREDIENT`

Applies to active ingredient or ingredient group.

Use when policy is known at ingredient level and multiple products share it.

### `CATEGORY`

Least specific.

Use for broad fallback behavior, including legacy `muc_nghiem_trong`.

Category policy must not override ingredient or drug-product policy.

## 4. Policy Resolution

Resolver input:

- `patient_id`
- `dose_occurrence_id`
- `drug_product_id`
- `legacy_drug_id`
- `risk_type`
- `event_context`

Resolution order:

```text
1. DRUG_PRODUCT + risk_type
2. INGREDIENT + risk_type
3. CATEGORY + risk_type
4. SYSTEM_DEFAULT safe fallback
```

Tie-breakers:

- Current time must be within `valid_from` and `valid_to`.
- Prefer `review_status=REVIEWED`.
- If multiple reviewed policies match the same scope and risk, use the highest `policy_version`.
- If only `LEGACY_UNREVIEWED` or `REVIEW_REQUIRED` exists, do not produce specific clinical instructions.

## 5. Policy Table

### `medication_safety_policy`

Required fields:

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

## 6. Required Constraints

Recommended constraints:

- `scope_type in ('DRUG_PRODUCT','INGREDIENT','CATEGORY')`
- `risk_type in ('MISSED_DOSE','DELAYED_DOSE','INTERACTION','CONTRAINDICATION','PREGNANCY')`
- `risk_level in ('LOW','MODERATE','HIGH','CRITICAL','UNKNOWN')`
- `action_policy in ('LOG_ONLY','REMIND','WARN','ESCALATE_CAREGIVER','ESCALATE_CLINICIAN','REQUIRE_MEDICAL_REVIEW')`
- `source_type in ('CLINICAL_REVIEW','DRUG_LABEL','GUIDELINE','LEGACY_CATEGORY_RULE','SYSTEM_DEFAULT')`
- `review_status in ('LEGACY_UNREVIEWED','REVIEW_REQUIRED','REVIEWED','REJECTED','RETIRED')`
- `policy_version > 0`
- `valid_to is null or valid_to > valid_from`

Legacy guard:

```text
if source_type = LEGACY_CATEGORY_RULE:
  scope_type must be CATEGORY
  review_status must be LEGACY_UNREVIEWED
```

Reviewed policy guard:

```text
if review_status = REVIEWED:
  reviewed_by is not null
  reviewed_at is not null
```

## 7. Indexes

Required:

- `medication_safety_policy(scope_type, scope_id, risk_type)`
- `medication_safety_policy(risk_type, review_status)`
- `medication_safety_policy(valid_from, valid_to)`

Optional later:

- partial index for active policies where `valid_to is null`
- partial index for `review_status='REVIEWED'`
- partial index for legacy fallback policies

## 8. Missed Dose Assessment

`missed_dose_assessment` is the durable decision record produced by policy resolution.

Required fields:

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

Reason codes:

- `POLICY_DRUG_PRODUCT_MATCH`
- `POLICY_INGREDIENT_MATCH`
- `POLICY_CATEGORY_FALLBACK`
- `NO_POLICY_SAFE_FALLBACK`
- `AMBIGUOUS_DRUG_ID`
- `POLICY_REVIEW_REQUIRED`
- `LEGACY_UNREVIEWED_FALLBACK`

Evaluator examples:

- `POLICY_ENGINE`
- `SCHEDULER`
- `AGENT_SAFETY_GATE`
- `SYSTEM_DEFAULT`

Rules:

- Assessment stores what policy was applied.
- Assessment stores uncertainty.
- Assessment is append-only from a clinical audit perspective.
- Re-assessment creates a new row with a later `evaluated_at`.

## 9. Safety Event

`safety_event` is the broader event/audit/escalation record.

Required fields:

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

Event types:

- `MISSED_HIGH_RISK_DOSE`
- `DELAYED_HIGH_RISK_DOSE`
- `RED_FLAG_SYMPTOM`
- `DRUG_INTERACTION_WARNING`
- `AMBIGUOUS_DRUG`
- `PHOTO_MISMATCH_REVIEW`
- `CAREGIVER_ESCALATION_CREATED`
- `CLINICIAN_ESCALATION_CREATED`

Decisions:

- `NO_ACTION`
- `LOG_ONLY`
- `REMIND_PATIENT`
- `WARN_PATIENT`
- `ESCALATE_CAREGIVER`
- `ESCALATE_CLINICIAN`
- `REQUIRE_MEDICAL_REVIEW`

Rules:

- Safety event must be understandable without reading full chat history.
- Event may reference a conversation/message/agent run, but should summarize the decision.
- Event metadata may include request IDs, photo verification IDs, or notification job IDs.

## 10. Missed Dose Flow

```text
dose_occurrence becomes late/missed
  -> policy resolver loads drug_product_id / ingredients / category
  -> medication_safety_policy resolution
  -> missed_dose_assessment row
  -> dose_event row
  -> dose_occurrence status update
  -> optional safety_event
  -> optional notification_job
```

Atomic transaction:

```text
missed_dose_assessment
+ dose_event
+ dose_occurrence.status update
+ safety_event
+ notification_job
```

The exact transaction can be split for provider dispatch, but the decision record must be durable before notification is sent.

## 11. Delayed Dose Flow

```text
patient confirms late intake
  -> create dose_event(DELAYED_CONFIRMED)
  -> update dose_occurrence(status=DELAYED, taken_at=event_at)
  -> run delayed-dose policy if needed
  -> create missed_dose_assessment or delayed assessment record
  -> create safety_event/notification_job if policy requires
```

DB-2 keeps the table name `missed_dose_assessment`, but `risk_type=DELAYED_DOSE` allows it to cover delayed-dose assessment. A later ADR can rename it to `dose_safety_assessment` if the team wants a broader name.

## 12. Agent Safety Integration

Agent may:

- read current dose occurrences
- read safe policy summaries
- create safety events through a domain service
- trigger escalation through a domain service

Agent must not:

- write `medication_safety_policy` directly
- infer clinical policy from chat
- promote `muc_nghiem_trong` to reviewed policy
- store chain-of-thought in `agent_tool_event` or `audit_log`

Agent audit should store:

- request ID
- intent
- tool names
- sanitized input/output references
- selected policy IDs
- created assessment/event IDs

## 13. Legacy Migration Model For `muc_nghiem_trong`

Future DB-6 migration can create fallback policies from category rules.

Input:

```text
drug.danh_muc
drug.muc_nghiem_trong
drug_chunks.danh_muc
drug_chunks.muc_nghiem_trong
V2 legacy_metadata.legacy_missed_dose_risk
```

Output:

```text
medication_safety_policy
  scope_type = CATEGORY
  scope_id = normalized category
  risk_type = MISSED_DOSE
  risk_level = mapped legacy level or UNKNOWN
  action_policy = conservative default
  source_type = LEGACY_CATEGORY_RULE
  review_status = LEGACY_UNREVIEWED
  source_reference = legacy source/report identifier
```

Mapping principle:

- Do not increase specificity.
- Do not mark reviewed.
- Do not generate clinical catch-up dose instructions.
- Preserve provenance.

## 14. Safety Policy Compatibility

Current behavior:

- V2 drug knowledge returns safe default severity/review required.
- V1 may still use `muc_nghiem_trong` fallback.
- Escalation table stores some safety actions.

Compatibility during migration:

- Keep current escalation behavior.
- Add safety events in parallel only after DB-3.
- Keep legacy severity outputs for current API if needed, but annotate source internally.
- New policy engine should return source and review status with every assessment.

## 15. Testing Requirements For Later Phases

DB-2 does not implement tests, but DB-3/DB-7 should include:

- category fallback never overrides drug-product policy
- legacy policy always has `LEGACY_UNREVIEWED`
- no clinical instruction emitted for unreviewed policy
- duplicate missed-dose scheduler runs do not create duplicate assessments/events
- notification job idempotency
- timezone boundary tests
- ambiguous `legacy_drug_id` maps to safe fallback
- agent cannot write safety policy directly

## 16. OPEN DECISIONS

- Physical migration name for V2 immutable `dose_event` while the current MVP `dose_event` table still exists.
- Whether target primary keys should be DB-native UUID columns or keep the current string UUID convention.
- Whether Drug Knowledge V2 should be imported into operational Postgres in DB-3 or remain file-backed with nullable/no local FK first.
- Exact patient/account relationship: one account to one patient, or support multiple patient profiles per account later.
- Whether `missed_dose_assessment` should be renamed to broader `dose_safety_assessment` before migration.
- Exact policy author/reviewer role model.
- Whether photo verification needs a separate group/evidence table for one image covering multiple `dose_occurrence` rows.

## 17. BREAKING CHANGE RISKS

- Redefining `dose_event` directly would break existing dose/photo/reporting/agent flows.
- Making `drug_product_id` required before backfill would break existing prescriptions and generated dose rows.
- Removing legacy `drug_id` from public DTOs would break current API/frontend compatibility.
- Replacing grouped legacy dose DTOs with per-occurrence DTOs without adapter would change UI behavior.
- Enforcing FKs/check constraints before data cleanup may fail dev/demo databases.
- Treating `muc_nghiem_trong` as reviewed safety policy would create unsafe clinical semantics.

## 18. MIGRATION BLOCKERS

- Need a reviewed mapping from current `prescription.items[]` to `prescription_item`, `medication_plan`, and `schedule_rule`.
- Need a mapping from current grouped `dose_event.expected_items[]` to per-drug `dose_occurrence` rows.
- Need a collision strategy for the table name `dose_event`.
- Need validation report for orphaned `patient_id`, `prescription_id`, `dose_event_id`, account, and caregiver references before FK enforcement.
- Need drug identity backfill coverage from `legacy_drug_id` to `drug_product_id`.
- Need idempotency key design embedded in migration plan.
- Need compatibility adapter design accepted before service cutover.
- Need policy fallback mapping for category-level `muc_nghiem_trong` reviewed by product/clinical owner for wording and risk behavior.

## 19. READY FOR MIGRATION DESIGN

READY FOR MIGRATION DESIGN: YES

Conditions:

- Migration must be additive first.
- Legacy schema must stay readable/writable until the compatibility adapter is implemented.
- V2 immutable dose events must not overwrite current MVP `dose_event` semantics during DB-3.
- `dose_occurrence` must be per medicine/per dose.
- `muc_nghiem_trong` must only become `CATEGORY` fallback with `LEGACY_UNREVIEWED` provenance.
- No public API breaking change should ship without an explicit cutover plan.

