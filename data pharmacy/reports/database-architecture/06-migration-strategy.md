# 06 Migration Strategy

Scope: Database Architecture V2, Phase DB-3 design. This document defines migration strategy only. No schema/code changes, Alembic migration, data migration, or Railway deploy were performed.

Inputs:

- `data pharmacy/reports/database-architecture/01-current-db-audit.md`
- `data pharmacy/reports/database-architecture/02-domain-model.md`
- `data pharmacy/reports/database-architecture/03-target-schema.md`
- `data pharmacy/reports/database-architecture/04-erd.md`
- `data pharmacy/reports/database-architecture/05-safety-policy-model.md`

## 1. Migration Principles

- Use additive migrations first.
- Do not drop or rename current production-facing tables during DB-3.
- Keep API V1 DTO compatibility until service cutover is explicitly approved.
- Keep public `drug_id` as the legacy slug.
- Add `drug_product_id` as nullable internal reference before it becomes required.
- Treat `muc_nghiem_trong` only as category fallback with `LEGACY_UNREVIEWED` provenance.
- Make all backfills resumable and idempotent.
- Validate data before adding strict FKs, `NOT NULL`, and check constraints.
- Use feature flags for reads/writes: legacy-only, dual-write, V2-read-shadow, V2-primary, legacy-read-fallback.

## 2. Chốt Decision: `dose_event` V1/V2 Collision

Decision:

- Keep current physical table `dose_event` as legacy table through additive migration and compatibility phases.
- Create V2 immutable event table with physical name `dose_event_log`.
- Treat `dose_event_log` as the target semantic `dose_event` in DB-2 documents.
- Only after DB-8 stabilization may the team consider renaming:
  - legacy `dose_event` -> `legacy_dose_event`
  - `dose_event_log` -> `dose_event`

Why:

- Current `dose_event` powers dose list, photo upload, reporting, caregiver dashboard, and Agent tools.
- Its semantics are mutable scheduled occurrence grouped by time.
- Target V2 `dose_event` is append-only action/event history.
- Direct rename/redefinition would be a breaking change and creates rollback risk.

Compatibility implication:

- During migration, code must clearly distinguish:
  - `legacy dose_event`: old grouped mutable row
  - `dose_occurrence`: V2 one drug/one dose current state
  - `dose_event_log`: V2 immutable action history

## 3. Chốt Decision: UUID/Text ID Strategy

Decision:

- Keep existing text/string UUID primary key style for DB-3 additive migrations.
- Use application-generated UUID strings for new tables.
- Do not convert existing table IDs to native Postgres `uuid` during this migration track.
- Revisit native `uuid` only in a later dedicated hardening ADR if the team wants it.

Why:

- Current ORM models use string IDs broadly.
- Existing public IDs and references are text.
- Converting ID column types would be cross-cutting, high-risk, and unrelated to target domain design.
- String UUID keeps additive migration simpler and reduces FK rollout blast radius.

Rules:

- New IDs must be UUID-formatted strings.
- FK columns referencing current tables use text/string type.
- `drug_product_id` stores the V2 canonical ID as text/string, matching current JSONL artifact representation unless a later import proves native UUID is safe.

## 4. Chốt Decision: Drug Knowledge V2 In Postgres

Decision:

- Import minimal Drug Knowledge V2 reference tables into Postgres in the first additive migration bundle, but do not switch retrieval/RAG to DB-native V2 in DB-3.
- Keep current V2 file-backed facade as runtime source during initial rollout.
- Use Postgres `drug_product`, `drug_id_map`, `ingredient`, and `drug_product_ingredient` as operational reference/backfill tables.
- Add FKs from operational tables to `drug_product` only after validation and backfill coverage are acceptable.

Why:

- Operational V2 tables need durable `drug_product_id` references for backfill, validation, safety policy, and reporting.
- The current V2 facade already works and should not be destabilized.
- DB import creates a joinable identity layer without changing canonical knowledge behavior.

Initial DB import scope:

- `drug_product`: identity and display fields needed by operational data.
- `drug_id_map`: legacy slug to canonical product ID.
- `ingredient`: identity/name only.
- `drug_product_ingredient`: product-to-ingredient links.

Out of DB-3 runtime scope:

- Replacing retrieval over `drug_chunks`.
- Replacing V2 JSONL knowledge loading.
- Re-crawling or modifying Final Canonical Drug V2.

## 5. Migration Phases

### Phase A: Additive Schema

Create new tables without touching legacy behavior:

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

Add nullable compatibility columns where low-risk:

- `patient.user_id`
- `patient.display_name`
- `patient.date_of_birth`
- `patient.sex`
- `patient.timezone`
- `patient.status`
- `prescription.end_date`
- `prescription.prescribed_by`
- `prescription.prescribed_at`
- `prescription.source_type`

Do not:

- drop `prescription.items`
- drop legacy `dose_event.expected_items`
- rename legacy `dose_event`
- add strict `NOT NULL` to backfilled fields before validation
- enforce all FKs immediately

### Phase B: Seed Drug Identity

Load V2 identity artifacts into DB reference tables:

```text
data pharmacy/v2/final_canonical/drug_product.jsonl
data pharmacy/v2/final_canonical/drug_id_map.jsonl
data pharmacy/v2/final_canonical/ingredient.jsonl
data pharmacy/v2/final_canonical/drug_product_ingredient.jsonl
```

Expected behavior:

- Idempotent upsert by canonical ID or legacy slug.
- Store source manifest/version.
- Do not alter V2 JSONL artifacts.
- Do not change `DRUG_KNOWLEDGE_BACKEND`.

Validation:

- Every active mapping has exactly one `drug_product_id`.
- Every imported product has a display name.
- Ambiguous/retired mappings are stored but not used as automatic FK backfill.

### Phase C: Backfill Prescription Domain

Backfill:

```text
prescription.items[]
  -> prescription_item
  -> medication_plan
  -> schedule_rule
```

This phase is resumable and records deterministic generated IDs or mapping keys.

Recommended backfill control table:

```text
migration_backfill_state
  id
  migration_name
  source_table
  source_id
  source_fingerprint
  target_table
  target_id
  status
  error_code
  error_message
  created_at
  updated_at
```

If the team avoids a generic control table, each new table still needs deterministic `migration_source_*` columns or unique generation keys.

### Phase D: Backfill Dose Occurrences

Backfill:

```text
legacy dose_event row
  + expected_items[]
  -> one dose_occurrence per expected item
```

Important:

- Legacy row with 3 expected items becomes 3 `dose_occurrence` rows.
- Each occurrence keeps reference to the legacy grouped row in metadata/source columns.
- V2 UI grouping is rebuilt by query, not by storing a grouped medical row.

### Phase E: Backfill Immutable Events

Create historical `dose_event_log` rows from legacy mutable state.

Rules:

- If legacy status is pending-like, create no action event unless useful as `MIGRATED_SCHEDULED_SNAPSHOT` metadata in migration audit. Do not pretend patient took action.
- If legacy status is final, create inferred event with `source='SYSTEM'`, `event_type` mapped from final status, and metadata indicating `inferred_from_legacy_status=true`.
- For photo-confirmed rows, include `photo_verification_id` when available.

Because `dose_event_log.event_type` in DB-2 did not include `MIGRATED_SNAPSHOT`, DB-3 should avoid adding fake clinical events. Use metadata on final inferred events and separate migration audit rows.

### Phase F: Seed Safety Fallback Policies

Backfill `muc_nghiem_trong` later in this migration track only as category fallback:

```text
medication_safety_policy
  scope_type = CATEGORY
  risk_type = MISSED_DOSE
  source_type = LEGACY_CATEGORY_RULE
  review_status = LEGACY_UNREVIEWED
```

Rules:

- Scope is normalized category, not drug product.
- `source_reference` records the legacy source and manifest/report.
- Do not generate ingredient/product policy from `muc_nghiem_trong`.
- Do not produce reviewed clinical action instructions from this data.

### Phase G: Validation Before Constraints

Run validation reports:

- orphaned patient/account/prescription references
- unmapped `legacy_drug_id`
- ambiguous `drug_id_map`
- invalid prescription item JSON
- invalid or empty `gio_nhac`
- duplicate generated dose occurrence keys
- status values outside target enum maps
- timezone missing or invalid
- policy rows violating legacy guard
- count reconciliation between legacy grouped doses and V2 occurrences

### Phase H: Compatibility Adapter

Implement later, after DB-3 design approval:

- Legacy API write path can dual-write V1 and V2.
- Legacy API read path can read V2 and project old DTOs.
- Feature flags control source-of-truth selection.
- Shadow validation compares legacy DTOs against V2-projected DTOs.

### Phase I: FK And Constraint Hardening

After validation:

1. Add FK constraints as `NOT VALID` where Postgres supports it.
2. Validate FKs after orphan cleanup.
3. Add check constraints for stable status enums.
4. Make required columns `NOT NULL`.
5. Add partial unique indexes for active plans/policies.
6. Add append-only protection for `dose_event_log`.

### Phase J: Service Cutover

Order:

1. Prescription service dual-write.
2. Scheduling generator writes `dose_occurrence`.
3. Dose status commands write `dose_event_log` and update `dose_occurrence`.
4. Photo verification maps one image to multiple V2 occurrences where needed.
5. Reporting reads V2 with legacy fallback.
6. Agent tools read V2 with legacy fallback.
7. Notifications read `notification_job`.
8. Safety evaluator writes `missed_dose_assessment` and `safety_event`.

### Phase K: Stabilization And Legacy Retirement

Only after DB-8 acceptance:

- freeze legacy writes
- verify rollback window is closed
- rename or archive legacy `dose_event`
- optionally rename `dose_event_log` to `dose_event`
- deprecate `prescription.items` after API cutover

## 6. Compatibility Adapter Design

### Feature Flags

Recommended flags:

- `DB_V2_DUAL_WRITE_ENABLED`
- `DB_V2_READ_SHADOW_ENABLED`
- `DB_V2_READ_PRIMARY_ENABLED`
- `DB_V2_SAFETY_POLICY_ENABLED`
- `DB_V2_NOTIFICATION_JOB_ENABLED`
- `DB_V2_DRUG_DB_REFERENCE_ENABLED`

### Prescription Adapter

Legacy write input:

```text
PrescriptionCreate.items[]
```

Dual-write target:

```text
prescription
+ prescription_item[]
+ medication_plan[] if approved/active
+ schedule_rule[] if schedule parse is valid
```

Legacy read output:

```text
prescription.items[] reconstructed from prescription_item + schedule_rule
```

Fallback:

- If V2 rows are missing or validation fails, return legacy `prescription.items`.

### Dose Adapter

Legacy read output:

```text
legacy dose_event DTO
  id
  prescription_id
  patient_id
  scheduled_at
  window_start
  window_end
  status
  expected_items[]
```

V2 projection:

```text
group dose_occurrence rows by:
  patient_id
  local date
  local scheduled time bucket
  legacy grouped source id when present
```

Group status mapping:

- all occurrences `TAKEN` -> legacy `TAKEN`
- any occurrence `AWAITING_REVIEW` -> legacy `AWAITING_CAREGIVER`
- any occurrence `MISSED` with none pending -> legacy `MISSED`
- all occurrences `CANCELLED` -> legacy `CANCELLED`
- mixed final/pending -> legacy `PARTIAL` only if API contract is updated; otherwise use most conservative current supported status and include item-level metadata internally

Until API V1 supports partial status, avoid making V2 primary for grouped dose reads.

### Photo Adapter

Current photo endpoint accepts one legacy dose ID.

Migration behavior:

- If the ID is a legacy grouped `dose_event.id`, find mapped V2 occurrences from source metadata.
- Apply photo result per expected item/drug.
- Write one `photo_verification` legacy row for compatibility.
- Write one or more `dose_event_log` rows for V2.
- Update corresponding `dose_occurrence` rows.

### Agent Tool Adapter

Agent schedule tools should eventually read:

```text
dose_occurrence
+ medication_plan
+ prescription_item
+ drug facade
```

During migration:

- Legacy tools continue reading legacy `dose_event` unless `DB_V2_READ_PRIMARY_ENABLED`.
- Shadow mode compares answerable schedule from V1 vs V2.

## 7. Mapping: `prescription.items[]`

Current item fields observed in DB-1:

- `drug_id`
- `ten_thuoc`
- `lieu_dung`
- `thoi_diem_dung`
- `so_vien_moi_lan`
- `gio_nhac`
- optional item-level date range
- optional form/route/photo helper fields

Target mapping:

| Legacy field | Target | Notes |
|---|---|---|
| `drug_id` | `prescription_item.legacy_drug_id`, `medication_plan.legacy_drug_id` | Public slug |
| `drug_id` via `drug_id_map` | `drug_product_id` | Nullable if unresolved |
| `ten_thuoc` | `prescription_item.drug_display_name` | Snapshot |
| `lieu_dung` | `prescription_item.dose_text` | Preserve raw |
| parsed numeric dose | `dose_value`, `dose_unit` | Only if reliable |
| `thoi_diem_dung` | `frequency_text` and/or `instructions` | Raw text |
| `so_vien_moi_lan` | `dose_text` metadata or parsed dose | Do not over-parse |
| `gio_nhac` | `schedule_rule.times_of_day` | Validate HH:mm |
| item start date | `prescription_item.start_date`, plan/rule start | Else prescription start |
| item end date | `prescription_item.end_date`, plan/rule end | Else prescription end/duration |
| `dang_thuoc` | `prescription_item.route`/metadata | Trust facade over frontend when possible |
| `duong_dung` | `prescription_item.route` | Trust facade over frontend when possible |

Generated rows:

```text
one legacy item
  -> one prescription_item
  -> one medication_plan
  -> one schedule_rule when gio_nhac is valid
```

If `gio_nhac` is missing/invalid:

- Create `prescription_item`.
- Create `medication_plan` with status `DRAFT` or `AWAITING_REVIEW` equivalent if allowed.
- Do not generate `schedule_rule`/occurrences until human review.

Status mapping:

| Legacy prescription status | Target prescription status | Item/plan status |
|---|---|---|
| `draft` | `DRAFT` | `DRAFT` |
| `active` / `approved` | `ACTIVE` | `ACTIVE` |
| `stopped` | `CANCELLED` or `COMPLETED` by end date | `STOPPED`/`CANCELLED` |
| `rejected` | `CANCELLED` | `CANCELLED` |

## 8. Mapping: Grouped Legacy `dose_event.expected_items[]`

Current legacy row:

```text
dose_event
  id
  prescription_id
  patient_id
  scheduled_at
  window_start
  window_end
  status
  expected_items[]
```

Target mapping:

```text
for each expected_items[i]:
  create one dose_occurrence
```

Occurrence fields:

| Legacy source | Target |
|---|---|
| `dose_event.id` | `dose_occurrence.metadata.legacy_dose_event_id` or migration source table |
| `dose_event.prescription_id` | through mapped `prescription_item` / `medication_plan` |
| `dose_event.patient_id` | `dose_occurrence.patient_id` |
| `dose_event.scheduled_at` | `dose_occurrence.scheduled_at`, `due_at` |
| `dose_event.window_start` | `dose_occurrence.window_start` |
| `dose_event.window_end` | `dose_occurrence.window_end` |
| `dose_event.window_end + policy grace` | `dose_occurrence.grace_until` |
| `dose_event.status` | mapped target occurrence status |
| `expected_items[i].drug_id` | `legacy_drug_id` and resolved `drug_product_id` |

Deterministic generation key:

```text
legacy-dose-event:{legacy_dose_event_id}:item-index:{i}:legacy-drug:{legacy_drug_id}
```

If item order is unstable or duplicate drug IDs occur in the same expected list:

- Include a normalized item fingerprint.
- Keep item index as part of the source mapping.
- Flag duplicate ambiguity for manual validation if fingerprint collision occurs.

Legacy status mapping:

| Legacy status | V2 `dose_occurrence.status` | V2 event log |
|---|---|---|
| `PENDING` | `SCHEDULED` or `DUE` based on time | none |
| `TAKEN` | `TAKEN` | inferred `TAKEN` or `PHOTO_CONFIRMED` if photo evidence |
| `DELAYED` | `DELAYED` | inferred `DELAYED_CONFIRMED` |
| `MISSED` | `MISSED` | inferred `MISSED_CONFIRMED` or `MISSED_AUTO_MARKED` |
| `CANCELLED` | `CANCELLED` | optional no event; audit migration |
| `AWAITING_CAREGIVER` | `AWAITING_REVIEW` | `PHOTO_REJECTED` if photo mismatch evidence exists |

No legacy grouped row should become one V2 occurrence unless it has exactly one expected item.

## 9. Validation Gates

### Gate 1: Additive Schema Applies Cleanly

Required:

- New tables exist.
- Legacy tables untouched.
- Migrations are reversible at schema level where practical.
- No data rewrite in initial DDL.

### Gate 2: Drug Identity Import Valid

Required:

- Import count matches V2 manifest.
- Active legacy mappings are unique.
- No operational FK enforcement yet.
- Ambiguous/retired mappings excluded from automatic backfill.

### Gate 3: Prescription Backfill Valid

Required:

- Number of backfilled `prescription_item` rows equals sum of valid legacy items.
- Invalid items are reported with source prescription ID and error code.
- No active prescription loses all medication items.
- `legacy_drug_id` preserved.

### Gate 4: Dose Occurrence Backfill Valid

Required:

- Sum of generated occurrences equals sum of mappable `expected_items[]`.
- Every occurrence has patient ID, scheduled time, status, and source mapping.
- Duplicate generation keys are zero.
- Per-drug occurrence count reconciles with legacy grouped rows.

### Gate 5: Safety Fallback Valid

Required:

- All legacy category fallback policies have `source_type=LEGACY_CATEGORY_RULE`.
- All legacy category fallback policies have `review_status=LEGACY_UNREVIEWED`.
- No fallback policy has `scope_type=DRUG_PRODUCT` or `scope_type=INGREDIENT`.
- No reviewed clinical policy is created from `muc_nghiem_trong`.

### Gate 6: Shadow Read Valid

Required:

- Legacy API DTO from legacy tables matches V2 projection for sampled prescriptions/doses.
- Differences are categorized as expected semantic improvements or defects.
- No UI-critical status mismatch is unresolved.

### Gate 7: FK/Constraint Readiness

Required:

- Orphan count is zero or explicitly accepted for nullable fields.
- Enum/status mapping is complete.
- Backfilled required columns are non-null.
- Runtime writes are dual-writing or V2-native.

## 10. Rollback Strategy

### Before Cutover

Rollback is simple:

- Disable V2 feature flags.
- Continue using legacy tables.
- Leave new tables in place.
- Re-run or truncate/rebuild backfill tables only after approval.

### During Dual-Write

Rollback:

- Disable V2 read primary.
- Keep dual-write disabled if it causes inconsistencies.
- Preserve V2 rows for forensic comparison.
- Use backfill state to resume after fixes.

### After V2 Read Primary

Rollback requirements:

- Legacy tables must still receive writes or be reconstructable from V2.
- If V2-only writes occurred, legacy projection backfill must run before fallback.
- Do not retire legacy `dose_event` until rollback window closes.

### After Legacy Retirement

Rollback becomes a data restore/redeploy procedure, not a feature-flag flip. Legacy retirement must wait until DB-8 stabilization acceptance.

## 11. Migration Order Recommendation

1. Add reference tables and V2 operational tables.
2. Import Drug Knowledge V2 identity/reference tables.
3. Add compatibility/backfill tracking table.
4. Backfill prescriptions/items/plans/rules.
5. Backfill dose occurrences.
6. Backfill inferred immutable event logs.
7. Seed category fallback safety policies.
8. Run validation reports.
9. Implement compatibility adapter in code.
10. Enable shadow reads.
11. Enable dual-write.
12. Add FKs/check constraints gradually.
13. Make V2 read primary.
14. Stabilize.
15. Retire legacy schema only after approval.

## 12. Decisions Chốt

- `dose_event` collision: keep legacy `dose_event`; create V2 immutable table as `dose_event_log` during migration.
- ID strategy: keep text/string UUID IDs for DB-3.
- Drug Knowledge V2 timing: import minimal identity/reference tables into Postgres early, but keep current V2 file-backed facade as runtime source until later cutover.
- `dose_occurrence` granularity: one medicine/one scheduled dose; UI grouping is projection only.
- Compatibility: public `drug_id` remains legacy slug; new tables store nullable `drug_product_id`.
- Migration style: additive schema, idempotent backfill, validation gates, shadow reads, dual-write, then cutover.
- `muc_nghiem_trong`: migrate only as category-level fallback `LEGACY_UNREVIEWED`, never as reviewed clinical truth.

## 13. Blockers Còn Lại

- Need exact V2 JSONL manifest/import contract checked before writing import migration scripts.
- Need final DTO compatibility tests for grouped dose status, especially partial item status.
- Need product decision on whether API V1 may expose `PARTIAL` grouped dose status later.
- Need validation SQL/report spec before FK enforcement.
- Need service-level dual-write design before enabling V2 primary reads.
- Need photo verification mapping design for one image covering multiple per-drug occurrences.
- Need owner approval for safety wording when only `LEGACY_UNREVIEWED` fallback exists.

## 14. READY FOR ADDITIVE MIGRATION

READY FOR ADDITIVE MIGRATION: YES

Conditions:

- The first migration must be schema-additive only.
- Physical V2 immutable event table must be named `dose_event_log`, not `dose_event`.
- New IDs must follow current string UUID convention.
- Drug V2 DB import must be identity/reference only and must not replace current V2 facade yet.
- Strict FKs/checks/`NOT NULL` must wait for validation gates.
- Compatibility adapter must be designed before any V2 read-primary cutover.

