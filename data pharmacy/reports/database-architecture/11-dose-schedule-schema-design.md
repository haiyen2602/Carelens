# 11 Dose Schedule Schema Design

Scope: Database Architecture V2, DB-4D design/review only. No migration,
scheduler, reminder, `dose_occurrence`, API/runtime switch, Railway action, or
patient data was created or changed.

## Inputs and design boundary

- The doctor prescription form in `frontend/src/app/doctor/prescribe/page.tsx`
  captures one row per drug: raw dose, doses/day, meal instruction, explicit
  local times, per-drug start/end dates, and optional repeating on/off cycle.
- `PrescriptionItemIn` already accepts `drug_id`, raw dose, raw timing text,
  reminder times, and per-item date/duration overrides.
- DB-4A/DB-4B created additive `prescription_item`, `medication_plan`,
  `schedule_rule`, and `dose_occurrence` tables, but did not yet model cycle
  periods or normalize reminder times.
- DB-4C is closed as NO-OP / NOT APPLICABLE: the available operational legacy
  database has zero prescriptions and zero items. Its retained importer is not
  a reason to invent patient data.

The prescription is clinician intent; the plan/rule is executable scheduling
intent; a dose occurrence is one drug at one scheduled instant. UI grouping is
not a medical database row.

## Current-form mapping

| Doctor form/API field | Canonical target | Rule |
|---|---|---|
| selected catalog drug | `prescription_item.drug_product_id` and `medication_plan.drug_product_id` | Resolve through active `drug_id_map`; retain `legacy_drug_id` when unresolved and require review. |
| manually entered drug name | `prescription_item.drug_display_name` | Display snapshot only; never a canonical identity. |
| `lieu_dung` | `prescription_item.dose_text` | Raw prescribed text is mandatory; numeric dose fields remain nullable unless a future deterministic parser succeeds. |
| số lần/ngày | `prescription_item.doses_per_day` | Clinician-entered intended count; must agree with active daily time rows before activation. |
| `gio_nhac[]` / form times | `schedule_rule_time.local_time` rows | Strict local `time` values, one row per distinct time. |
| `thoi_diem_dung` / meal selector | `prescription_item.meal_instruction_code`, `meal_instruction_text`, plus existing `frequency_text` | Preserve raw text; code only maps the controlled form vocabulary. |
| item `start_date`, form start date | `prescription_item.start_date` | Local clinical calendar date. |
| item duration or form end date | `prescription_item.end_date` | Canonical DB-4D meaning is **inclusive** local calendar end date; `NULL` means no specified end. |
| `hasCycle`, `cycleOnDays`, `cycleOffDays` | optional `schedule_rule_cycle` | One repeating on/off pattern attached to one schedule rule. |

The existing DB-4C test-only backfill represented its computed `end_date` as an
exclusive boundary to mirror the legacy generator. Because the operational
source is empty, no real data carries that meaning. DB-4D must establish the
inclusive `end_date` meaning before any operational write; a later migration
must not mix the two interpretations.

## Proposed relationship model

```text
prescription 1 --- * prescription_item 1 --- 0..* medication_plan
                                           |
                                           +--- active plan (at most one after validation)

medication_plan 1 --- * schedule_rule 1 --- * schedule_rule_time
                                     |
                                     +--- 0..1 schedule_rule_cycle

schedule_rule 1 --- * dose_occurrence
```

`prescription_item` owns clinician-entered dose, meal, and calendar intent.
`medication_plan` owns an approved actionable version of that item; it can be
paused, cancelled, or superseded without rewriting old occurrences.
`schedule_rule` owns recurrence semantics. A plan may need multiple rules in
the future, but the current form creates one daily-times rule per plan.

## Proposed schema changes

### `prescription_item`

Keep existing identity, raw-text, date, and traceability columns. Add:

| Column | Type | Null | Meaning |
|---|---|---:|---|
| `doses_per_day` | integer | yes during migration | Intended number of doses each dosing day. |
| `meal_instruction_code` | text | yes | Controlled timing code, defined below. |
| `meal_instruction_text` | text | yes | Exact clinician-entered/display text; required when code is `OTHER`. |

`dose_text` remains the medical source text. `doses_per_day` and meal code are
schedule attributes, not a dose parser result.

### `medication_plan`

Retain current identity, patient/item/drug references, status, timezone, and
audit timestamps. One plan takes its calendar boundaries from its linked
`prescription_item`; existing `start_at`/`end_at` remain derived instants for
compatibility and are not the source of local-date semantics.

### `schedule_rule`

Use the existing table for recurrence metadata. For the current doctor form,
the canonical rule is:

```text
rule_type       = DAILY_AT_TIMES
frequency       = doses_per_day
interval_value  = 1
interval_unit   = DAY
timezone         = patient/plan timezone
status           = DRAFT until clinician-approved plan is active
```

`times_of_day` JSON is not the long-term source of truth. It may be retained
temporarily for compatibility/backfill, but new writes must use normalized
`schedule_rule_time` rows.

### New `schedule_rule_time`

| Column | Type | Null | Constraint / meaning |
|---|---|---:|---|
| `id` | text UUID | no | Primary key. |
| `schedule_rule_id` | text | no | Parent rule; FK added after validation. |
| `local_time` | SQL `time` | no | Local wall-clock time selected by clinician. |
| `created_at`, `updated_at` | timestamptz | no | Audit timestamps. |

Required unique key: `(schedule_rule_id, local_time)`. This prevents two
occurrences for the same drug/rule/time on one day without relying on JSON
deduplication. The daily count is the number of active time rows; service-level
validation initially ensures it equals `doses_per_day`.

### New `schedule_rule_cycle`

| Column | Type | Null | Constraint / meaning |
|---|---|---:|---|
| `schedule_rule_id` | text | no | Primary key and one-to-one parent relation. |
| `anchor_date` | date | no | First local calendar date of cycle position zero; normally item `start_date`. |
| `on_days` | integer | no | `> 0`; consecutive dosing days. |
| `off_days` | integer | no | `>= 0`; consecutive non-dosing days. |
| `created_at`, `updated_at` | timestamptz | no | Audit timestamps. |

No row means every date in the item date range is a dosing day. A cycle row
means that local date `d` is a dosing date only when:

```text
0 <= (d - anchor_date) mod (on_days + off_days) < on_days
```

The item date window is inclusive: generate only when
`start_date <= d <= end_date` (or no end date). Thus `on_days=5`, `off_days=2`
starts with five dosing days at `anchor_date`, pauses two days, and repeats.
The cycle table models the form's current repeated cycle; it does not infer
clinical protocol phases, dose escalation, or one-off exceptions.

### `dose_occurrence`

The current table already has the essential references, UTC scheduled time,
status, and unique `generation_key`. DB-4D requires the following design
clarifications/additions before implementation:

| Field | DB-4D meaning |
|---|---|
| `medication_plan_id`, `prescription_item_id`, `schedule_rule_id` | One plan/item/rule lineage for each occurrence. |
| `drug_product_id`, `legacy_drug_id` | Canonical identity plus compatibility traceability. |
| `scheduled_at` | UTC instant obtained from `local_date + local_time + rule timezone`. |
| `scheduled_local_date`, `scheduled_local_time`, `timezone` | New immutable generation context for stable grouping, replay, and future DST-safe auditing. |
| `generation_key` | Unique key such as `rule:{rule_id}:local-date:{date}:local-time:{time}`. |
| `status` | `SCHEDULED`, `DUE`, `TAKEN`, `MISSED`, `SKIPPED`, `DELAYED`, `CANCELLED`, or `AWAITING_REVIEW`. |

One rule with two times yields two occurrences per qualifying day. Two drugs at
08:00 yield two rows. The UI may group by
`(patient_id, scheduled_local_date, scheduled_local_time, timezone)`, but no
group identifier replaces the individual occurrence or its safety state.

## Enums and validation rules

Use text columns with application validation initially; add PostgreSQL enum or
check constraints only after the DB-4D migration and validation gate.

| Field | Values |
|---|---|
| `meal_instruction_code` | `BEFORE_MEAL`, `AFTER_MEAL`, `WITH_MEAL`, `BEDTIME`, `ANYTIME`, `OTHER`, `UNSPECIFIED` |
| `medication_plan.status` | `DRAFT`, `ACTIVE`, `PAUSED`, `COMPLETED`, `CANCELLED`, `SUPERSEDED`, `REVIEW_REQUIRED` |
| `schedule_rule.rule_type` | `DAILY_AT_TIMES`, `INTERVAL`, `WEEKLY`, `MONTHLY`, `CUSTOM` |
| `schedule_rule.status` | `DRAFT`, `ACTIVE`, `PAUSED`, `CANCELLED`, `SUPERSEDED` |
| `dose_occurrence.status` | `SCHEDULED`, `DUE`, `TAKEN`, `MISSED`, `SKIPPED`, `DELAYED`, `CANCELLED`, `AWAITING_REVIEW` |

Required future constraints/indexes:

- `doses_per_day > 0` when present; do not hard-code the UI's current maximum
  of four as a database medical rule.
- `start_date <= end_date` when both are present.
- `on_days > 0`, `off_days >= 0`, and `anchor_date` inside the item date range.
- one `schedule_rule_time` value per rule/time, plus indexes on
  `schedule_rule_time(schedule_rule_id)` and
  `schedule_rule_cycle(schedule_rule_id)`.
- after operational validation, foreign keys from plan to item, rule to plan,
  time/cycle to rule, and occurrence to plan/item/rule/product.
- after cleanup, a partial unique active-plan key for one active plan per item.

Rules are never activated from a missing/ambiguous drug identity, invalid time,
invalid date, or unreviewed change. This preserves ADR-0010 human approval and
does not let an agent infer a medical schedule.

## DB-4D implementation boundary

A later additive migration should add the columns/tables/indexes above, keep
existing nullable fields and JSON compatibility data, then introduce a
clinician-approved write path. Only after validation should it harden FKs,
`NOT NULL`, status checks, and active-plan uniqueness. Scheduler/reminder work
and occurrence generation are explicitly later phases; this design creates no
occurrences.

## Open decisions

1. Whether the UI/API should expose `meal_instruction_code` directly or map its
   current Vietnamese labels server-side while always retaining raw text.
2. Whether a future clinician workflow needs multiple cycle phases or temporary
   exceptions. The proposed one-cycle model exactly covers the current form;
   do not generalize it without product/clinical requirements.
3. The approval UX for edits to an active plan: it must supersede/replace
   future rules without mutating historical occurrences, but the exact API
   contract remains a later task.
4. The maximum UI doses/day is a product validation choice, not a schema-level
   clinical limit.

## DB-4C CLOSEOUT: PASS

The current operational legacy source is empty, so DB-4C is correctly closed
as NO-OP / NOT APPLICABLE. Its implementation and tests remain retained; no
mock data is treated as patient data.

## DB-4D SCHEMA DESIGN: PASS

The proposed model maps every field from the actual doctor form, normalizes
times and cycles, and preserves one-drug/one-dose occurrence granularity.

## SCHEMA CHANGES REQUIRED:

YES — add item schedule fields, `schedule_rule_time`, `schedule_rule_cycle`,
and immutable local generation context on `dose_occurrence`; clarify inclusive
`end_date` semantics and transition away from JSON `times_of_day` as source of
truth.

## OPEN DECISIONS:

Four non-blocking product/API decisions are listed above. They do not authorize
implementation of a scheduler or dose generation.

## MIGRATION REQUIRED:

YES — additive DB-4D migration only, with compatibility data retained and
constraint hardening deferred until validation.

## READY FOR DB-4D IMPLEMENTATION:

YES
