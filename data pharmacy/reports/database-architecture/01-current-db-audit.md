# 01 Current DB Audit

Scope: Phase DB-1 of Database Architecture V2. This report audits the current repository state only. No schema migration, data migration, Railway deploy, or code implementation was performed.

Reference target: `docs/data/database_architecture_v2_plan.md`.

## 1. Context Read

Files and areas reviewed:

- Governance and architecture: `AGENTS.md`, `specs/api-contracts.md`, `adrs/0004-project-structure-and-coding-convention.md`, `adrs/0005-definition-of-done.md`, `adrs/0012-drug-data-v2-compatibility-and-provenance.md`.
- DB setup and ORM: `backend/db/base.py`, `backend/db/models.py`.
- Alembic migrations: `migrations/env.py`, `migrations/versions/0001_initial_schema.py` through `0022_hourly_conversation_summaries.py`.
- Prescription/scheduling: `backend/services/prescription/service.py`, `backend/services/scheduling/generator.py`, `backend/api/prescription_routes.py`, `backend/api/dose_routes.py`.
- Conversation/Agent DB access: `backend/api/chat_routes.py`, `backend/agents/orchestrator.py`, `backend/agents/tools/*.py`, `backend/agents/nodes/*.py`.
- Safety/escalation/reminder/photo: `backend/services/escalation.py`, `backend/services/escalation_reminder.py`, `backend/services/escalation_scheduler.py`, `backend/services/photo_verification/verifier.py`, `backend/api/photo_routes.py`.
- User/patient/caregiver/reporting/auth: `backend/api/security.py`, `backend/api/auth_routes.py`, `backend/api/account_routes.py`, `backend/api/patient_routes.py`, `backend/api/caregiver_routes.py`, `backend/api/reporting_routes.py`.
- Drug Knowledge V1/V2: `backend/services/retrieval.py`, `backend/services/drug_knowledge/__init__.py`, `backend/services/drug_knowledge/resolver.py`, `backend/services/drug_knowledge/v2_agent.py`, `data pharmacy/data_rebuild_v2_agent_plan.md`, existing V2 JSONL/report artifacts.

## 2. Current Database Stack

- Runtime DB is PostgreSQL via SQLAlchemy, configured in `backend/db/base.py`.
- pgvector, pg_trgm, and unaccent are installed by migration `0001`.
- `backend/db/base.py` sets `hnsw.ef_search` on each DB connection.
- Alembic uses `backend.config.get_settings().database_url`.
- Alembic revision chain is linear: `0001 -> ... -> 0014 -> 0014b -> 0015 -> ... -> 0022`.
- `migrations/env.py` imports only `AuditLog` and `DrugChunk`, but because it imports from `backend.db.models`, all model classes are still evaluated. The comment is stale and should be cleaned later.

## 3. Current Tables

Current ORM models in `backend/db/models.py`:

| Table | Current purpose | Main fields |
|---|---|---|
| `drug_chunks` | V1 DB-backed RAG chunks | `drug_id`, `ten_thuoc`, `danh_muc`, `muc_nghiem_trong`, `field_group`, `noi_dung`, `embedding` |
| `drug` | V1-style catalog for prescription search/form fill | `id`, `ten_thuoc`, `dang_thuoc`, `duong_dung`, `ham_luong`, `danh_muc`, `muc_nghiem_trong` |
| `audit_log` | Per-chat-run audit trace | `patient_id`, `dose_event_id`, `utterance`, `trace`, `final_response`, `total_duration_ms` |
| `patient` | Patient profile, separate from auth account | `id`, `full_name`, `year_of_birth`, `doctor_id`, `note`, `watch`, `gender`, `height_cm`, `weight_kg` |
| `prescription` | MVP prescription/phac do | `patient_id`, `doctor_id`, `status`, `items` JSON, `start_date`, `duration_days`, `note`, `approved_by`, `approved_at` |
| `dose_event` | Current scheduled dose row and mutable status | `prescription_id`, `patient_id`, `scheduled_at`, `window_start`, `window_end`, `status`, `expected_items` JSON |
| `escalation` | Safety/photo/dose escalation queue | `patient_id`, `dose_event_id`, `severity`, `trigger`, `reason`, `status`, `notified`, reminder fields |
| `chat_messages` | Display chat history | `patient_id`, `role`, `content`, `created_at`, `hidden` |
| `hourly_conversation_summaries` | Long-term conversation recap | `patient_id`, `hour_bucket`, `summary_text`, `message_count`, `hidden` |
| `photo_verification` | One photo verification attempt | `dose_event_id`, `patient_id`, `attempt`, expected/detected JSON, `ket_qua`, `image_path` |
| `account` | Auth account for roles | `email`, `password_hash`, `role`, `patient_id`, `doctor_id`, status/token fields |
| `pending_drug_confirmation` | Agent state machine between chat requests | `patient_id` PK, `candidates`, `stage`, `original_query`, `retry_count` |
| `caregiver_link` | Caregiver-to-patient relationship | `caregiver_account_id`, `patient_id`, `relationship`, `status` |

No current DB tables exist for V2 target entities:

- `prescription_item`
- `medication_plan`
- `schedule_rule`
- `dose_occurrence`
- immutable V2-style `dose_event`
- `notification_job`
- `medication_safety_policy`
- `missed_dose_assessment`
- `safety_event`
- `conversation`
- `message`
- `agent_run`
- `agent_tool_event`
- DB-native `drug_product`, `ingredient`, `drug_product_ingredient`, `drug_knowledge`, `drug_id_map`

Drug Data V2 exists as file artifacts under `data pharmacy/v2/final_canonical/`, not as runtime relational DB tables.

## 4. Constraints, Indexes, And Referential Integrity

Current constraints are minimal.

Primary keys:

- Single-column string primary keys on most tables.
- `pending_drug_confirmation.patient_id` is the primary key, enforcing at most one pending confirmation per patient.

Unique constraints:

- `account.email` is unique/indexed.
- `hourly_conversation_summaries(patient_id, hour_bucket)` is unique.

Indexes:

- `drug_chunks(drug_id)`, `drug_chunks(drug_id, field_group)`.
- HNSW vector index on `drug_chunks.embedding`.
- GIN trigram indexes on `drug_chunks.noi_dung_unaccent` and `drug_chunks.ten_thuoc_unaccent`.
- `drug(ten_thuoc)`, `drug(dang_thuoc)`.
- `audit_log(patient_id)`.
- `prescription(patient_id)`.
- `dose_event(prescription_id)`, `dose_event(patient_id)`.
- `escalation(patient_id)`.
- `photo_verification(dose_event_id)`, `photo_verification(patient_id)`.
- `chat_messages(patient_id)`, `chat_messages(created_at)`, `chat_messages(patient_id, created_at)`.
- `account(email)`, `account(patient_id)`, `account(doctor_id)`, token indexes.
- `caregiver_link(caregiver_account_id)`, `caregiver_link(patient_id)`.
- `hourly_conversation_summaries(patient_id)`, `hourly_conversation_summaries(hour_bucket)`.

Missing or weak constraints:

- No foreign keys between `prescription.patient_id`, `dose_event.patient_id`, `dose_event.prescription_id`, `photo_verification.dose_event_id`, `escalation.dose_event_id`, `audit_log.dose_event_id`, `caregiver_link.patient_id`, `caregiver_link.caregiver_account_id`, and their parent tables.
- No check constraints for enum-like fields: prescription status, dose status, escalation status/trigger/severity, account role/status, chat role, photo verification status, caregiver link status.
- No unique constraint/idempotency key preventing duplicate dose rows for the same prescription and scheduled time.
- No explicit DB-level append-only enforcement for `audit_log`; comments say append-only, but DB permits update/delete.
- Several medically meaningful relationships are represented as free-form strings and JSON, not relational references.

The current model intentionally avoided FK enforcement for team/dev-data compatibility. That is understandable for MVP, but it is not sufficient for Database Architecture V2.

## 5. Prescription And Reminder Flow

Current flow:

1. `POST /api/v1/prescriptions` calls `tao_phac_do()`.
2. `prescription` is created with `status="draft"`.
3. Items are stored as one JSON array in `prescription.items`.
4. Each item may include `drug_id`, `ten_thuoc`, `lieu_dung`, `thoi_diem_dung`, `so_vien_moi_lan`, `gio_nhac`, and optional per-item date range.
5. `drug_id`, when present, is resolved through `backend.services.drug_knowledge.lay_thuoc()` so backend does not trust frontend `dang_thuoc`/`duong_dung`.
6. `POST /prescriptions/{id}/approve` calls `duyet_phac_do()`.
7. `duyet_phac_do()` sets prescription to `active`, records `approved_by/approved_at`, and calls `sinh_dose_event()` in the same DB transaction.
8. `sinh_dose_event()` generates rows in `dose_event`.
9. Multiple drugs at the same hour are grouped into one `dose_event.expected_items` JSON list.
10. Editing an active prescription deletes future `PENDING` dose rows and regenerates them; closed rows are preserved.
11. Stopping a prescription marks future `PENDING` rows as `CANCELLED`.

Current reminder/scheduler:

- There is no general reminder queue/table.
- There is no worker that transitions `PENDING -> MISSED` when `window_end` passes.
- APScheduler is used only for escalation reminders and hourly conversation summaries.
- `SQLAlchemyJobStore` persists scheduler jobs to Postgres, but it is not represented in ORM models or in the domain model.
- Escalation reminder state is stored directly on `escalation` through `reminder_count` and `last_reminder_at`.

Fit vs target:

- The current `dose_event` table is closer to target `dose_occurrence` than target `dose_event`.
- Current `dose_event.expected_items` stores expected schedule content, not immutable patient action events.
- Target V2 needs `dose_occurrence` as mutable current state and `dose_event` as append-only history.

## 6. Dose Confirmation And Photo Verification

Manual dose update:

- `PATCH /api/v1/doses/{dose_id}` mutates `DoseEvent.status` directly.
- Authorization is partially implemented: patient can update own dose; doctor can update any dose with an existing patient; caregiver requires accepted `CaregiverLink`.
- No append-only event row is written for manual status changes.

Photo flow:

- `POST /doses/{dose_id}/photo` creates `photo_verification` with `ket_qua="dang_xu_ly"`.
- The uploaded image path is stored in DB; image bytes are stored on disk.
- Background task `hoan_tat_xac_minh()` opens a new DB session, calls VLM, updates `photo_verification`, and mutates `dose_event.status` to `TAKEN`, `DELAYED`, or `AWAITING_CAREGIVER`.
- If repeated mismatch reaches caregiver-review threshold, it creates/updates `escalation` through `trigger_emergency_escalation()`.

Gaps vs target:

- No immutable `dose_event(TAKEN/SKIPPED/SNOOZED/MANUAL_CORRECTION)` table.
- No atomic transaction boundary covering `dose_event` append, `dose_occurrence.status`, and notification cancellation, because those entities do not exist yet.
- Photo attempts are auditable, but dose status changes are not captured as event history.
- No idempotency key for photo completion or duplicate callback/retry handling.

## 7. User, Patient, Caregiver, Conversation

Current user/patient model:

- `account` stores auth identity, role, password hash, and optional `patient_id`/`doctor_id`.
- `patient` stores profile data and `doctor_id`.
- There is no FK from `patient.user_id` to account; target V2 explicitly expects `patient.user_id`.
- `auth/register` creates an `Account` and, for role `patient`, also creates a `Patient` with the same UUID.
- Admin-created accounts can carry arbitrary text `patient_id`/`doctor_id`.
- `caregiver_link` provides accepted/pending caregiver-to-patient links but has no FK/unique constraint.

Current conversation model:

- There is no `conversation` table.
- There is no target-style `message` table keyed by `conversation_id`.
- Current `chat_messages` stores patient-level display history only.
- `hourly_conversation_summaries` stores patient/hour summaries for long-term lookup.
- `audit_log` stores per-request agent trace and final response.

Fit vs target:

- `chat_messages` and `hourly_conversation_summaries` are reusable concepts, but need migration/mapping into target `conversation`/`message` if conversation sessions become first-class.
- `audit_log` contains agent trace but does not match target generic audit shape (`actor_type`, `entity_type`, snapshots, `request_id`).
- No `agent_run` or `agent_tool_event` exists.

## 8. Agent And Tools DB Access

DB reads/writes by Agent/API:

- `chat_routes.py`
  - Reads `pending_drug_confirmation`.
  - Writes `audit_log`.
  - Writes `chat_messages`.
  - Clears `pending_drug_confirmation` on redflag.
  - Builds DB-backed escalation function.
- `personal_tools.py`
  - Reads `dose_event` for personal schedule.
  - Reads `prescription.items` JSON for active prescription drug lookup.
- `conversation_nodes.py`
  - Reads `patient` for greeting personalization.
  - Reads `dose_event` via personal tools for today's schedule.
  - Reads prescription info for drug schedule answers.
  - Reads `chat_messages`/`hourly_conversation_summaries`.
- `dose_confirmation_nodes.py`
  - Reads `dose_event.expected_items` for severity context.
  - Calls escalation creation for medium/high cases.
- `drug_confirmation_nodes.py`
  - Reads active prescription items.
  - Writes/updates/deletes `pending_drug_confirmation`.
  - Uses V2 file-backed drug identity/knowledge by default.
- `side_effect_audit_nodes.py`
  - Reads active prescription drug IDs.
  - Reads V2 file-backed adverse-effect knowledge by default.
- `orchestrator.py`
  - Calls escalation on safety redflag.
- `escalation.py`
  - Writes `escalation`.
- `escalation_reminder.py`
  - Reads and mutates `escalation`.
- `photo_verification/verifier.py`
  - Reads `dose_event`.
  - Writes/mutates `photo_verification`.
  - Mutates `dose_event.status`.
  - Writes `escalation`.

The Agent currently has useful isolation patterns: personal queries filter by `patient_id`, and safety redflag escalation is centralized. However, state transitions are still direct table mutations rather than explicit domain commands with audit/event rows.

## 9. Drug ID And V1/V2 Compatibility

Current public `drug_id`:

- Public/API-facing `drug_id` is still the legacy slug.
- `prescription.items[].drug_id` stores the legacy slug.
- `dose_event.expected_items[].drug_id` stores the legacy slug.
- `drug.id` and `drug_chunks.drug_id` use the same legacy slug space.

Current V2 compatibility:

- ADR-0012 says public `drug_id` remains legacy slug during migration; internal V2 uses UUID `drug_product.id`.
- File artifacts under `data pharmacy/v2/final_canonical/` include `drug_product.jsonl`, `drug_id_map.jsonl`, `drug_product_ingredient.jsonl`, `drug_knowledge.jsonl`, and `manifest.json`.
- `backend/services/drug_knowledge/v2_agent.py` reads V2 JSONL files and resolves `legacy_drug_id -> drug_product_id`.
- `DRUG_KNOWLEDGE_BACKEND=v1|v2|shadow` selects runtime behavior.
- Default config is `drug_knowledge_backend="v2"`.
- V2 facade returns `DrugCatalogItem.drug_id` as legacy slug for API compatibility.

Gap:

- There is no relational `drug_product` table in operational DB.
- There is no `drug_id_map` table in operational DB.
- Prescription and dose rows do not store `drug_product_id`.
- Target V2 says operational tables should reference `drug_product_id` and keep `legacy_drug_id` for migration; current DB cannot do that yet.

## 10. `muc_nghiem_trong` Audit

Current locations:

- `drug_chunks.muc_nghiem_trong`
- `drug.muc_nghiem_trong`
- `DrugInfoResult.muc_nghiem_trong`
- V2 file metadata: `drug_product.legacy_metadata.legacy_missed_dose_risk` with `legacy_missed_dose_risk_status = NOT_CLINICALLY_REVIEWED`

Current usage:

- Legacy importer explicitly preserves `muc_nghiem_trong` as `legacy_missed_dose_risk`, not as canonical knowledge.
- `v2_agent.py` returns empty `muc_nghiem_trong` for V2 knowledge results.
- `get_severity_source()` in V2 mode returns `SAFE_DEFAULT_SEVERITY` with `status="REVIEW_REQUIRED"`; it does not promote legacy risk metadata to clinical truth.
- In V1 mode, `get_severity_source()` still uses legacy chunks and may use `muc_nghiem_trong` as fallback severity.
- `scripts/classify_severity.py` generated `muc_nghiem_trong` by category/rule mapping.
- Prior reports already state `muc_nghiem_trong` is heuristic/category-derived, not a per-drug medical fact.

Audit conclusion:

- Do not migrate or rewrite `muc_nghiem_trong` in DB-1.
- In future DB-6, it should only become category-level fallback `medication_safety_policy` metadata:
  - `scope_type = CATEGORY`
  - `risk_type = MISSED_DOSE`
  - `source_type = LEGACY_CATEGORY_RULE`
  - `review_status = LEGACY_UNREVIEWED` or equivalent agreed enum
- It must not become reviewed `DRUG_PRODUCT` or `INGREDIENT` policy without clinical review.

## 11. What Can Be Kept

- PostgreSQL + SQLAlchemy + Alembic stack.
- Existing migration chain and additive-migration practice.
- pgvector/pg_trgm/unaccent setup for legacy RAG and searchable catalog.
- Drug V2 facade and feature flag `DRUG_KNOWLEDGE_BACKEND`.
- Public legacy slug compatibility approach from ADR-0012.
- Prescription service boundary and route/service separation.
- Atomic approve flow pattern: prescription status update and dose generation in one transaction.
- Existing `patient`, `account`, and `caregiver_link` concepts, with stricter FK/constraint design later.
- Existing `photo_verification` as an audit-friendly attempt log, likely mapped to target evidence or dose-event metadata.
- Existing `escalation` behavior can inform `safety_event` and notification design.
- Existing `audit_log.trace` content is useful as source material for future `agent_run`/`agent_tool_event`, even if the table shape changes.
- APScheduler + SQLAlchemyJobStore decision can be reused for background jobs, but not as the source-of-truth for notifications.

## 12. Technical Debt

- `prescription.items` is a JSON array instead of normalized `prescription_item`.
- `dose_event.expected_items` duplicates drug/form/route data and groups multiple drugs into one scheduled row.
- `dose_event` mixes planned occurrence, current status, and partial action history.
- No `medication_plan` or `schedule_rule`; scheduling logic is implicit in prescription item JSON and generation code.
- No `notification_job`; reminder/escalation notification state is fragmented.
- No safety policy table; severity decisions are in code/config/V2 file metadata rather than auditable policy rows.
- Missing FK/check constraints and many free-form enum strings.
- Direct mutation of medically important state lacks immutable event rows.
- `audit_log` stores PHI-like utterance/final response and trace in one table but is not target generic audit.
- Several implemented endpoints are documented in code as not yet in `api-contracts.md`.
- Some comments are stale after auth/V2 work, especially references saying auth is not built.
- Manual seed/test scripts delete rows directly and rely on lack of FK; future FK work will need script cleanup.

## 13. Mixed Responsibilities

- `dose_event` is both schedule and status. Target wants `dose_occurrence` as mutable state and `dose_event` as immutable patient action log.
- `prescription` is both prescription header and line-item store because `items` is JSON.
- `prescription.items` stores schedule inputs, drug identity, dosage text, and photo-verification helper fields.
- `drug` mixes V1 catalog, missed-dose legacy risk, and operational prescription validation.
- `drug_chunks` mixes knowledge retrieval with legacy safety severity metadata.
- `escalation` mixes safety event, notification target list, and reminder job state.
- `chat_messages` is display history, while `audit_log` is agent run audit; there is no first-class conversation/session boundary.
- `account.patient_id` and `patient.id` are linked by convention, not by schema.

## 14. Breaking Change Risks

- Public API and frontend expect legacy slug `drug_id`; switching directly to UUID would break prescription, dose, frontend, tests, eval, and V2 facade assumptions.
- Splitting `prescription.items` into `prescription_item` will affect prescription create/update/list/get payloads unless an adapter preserves current DTO shape.
- Renaming/redefining current `dose_event` to target immutable event semantics would break dose list, photo upload, reporting, caregiver dashboard, adherence calculation, and Agent tools.
- Adding FK constraints immediately can fail existing dev/demo data because current code intentionally allows free-form IDs.
- Adding strict enum check constraints can fail rows with older status values such as `approved`, `active`, `stopped`, `rejected`, `AWAITING_CAREGIVER`, and Vietnamese photo statuses.
- Adding `conversation`/`message` may require chat API compatibility for current patient-level history endpoints.
- Introducing `notification_job` may duplicate existing escalation reminder behavior unless responsibilities are clearly split.
- Making `drug_product_id` required before backfill would break existing prescriptions/dose events that only have legacy slug.

## 15. Migration Risks

- Duplicate dose generation: current idempotency deletes future pending rows, but there is no DB uniqueness/idempotency key.
- Data loss risk when normalizing JSON arrays: existing prescriptions and dose rows contain nested JSON that must be mapped carefully.
- Historical semantics risk: current closed `dose_event` rows represent both occurrence and final status; converting them into `dose_occurrence` plus event history will require inferred events and clear provenance.
- Timezone risk: scheduling currently interprets doctor-entered `gio_nhac` as Asia/Ho_Chi_Minh and stores UTC datetimes. Target needs explicit patient/plan timezone.
- Backfill risk: manually created prescriptions may have empty/missing `drug_id`, invalid `gio_nhac`, or stale `dang_thuoc`/`duong_dung`.
- FK adoption risk: existing rows may reference missing patient/account/prescription/dose/drug records.
- Safety migration risk: legacy `muc_nghiem_trong` can be misread as clinical fact if not explicitly tagged as legacy fallback.
- Operational risk: current photo background task and escalation scheduler write live tables; migration must avoid double writes or skipped writes during cutover.
- Rollback risk: once services start writing V2 tables, a compatibility adapter is needed so old endpoints can still read coherent state.

## 16. Target V2 Gap Analysis

Medication plan:

- Missing entirely.
- Current equivalent is implicit: `prescription` plus JSON items plus generated `dose_event`.
- Need explicit `medication_plan(patient_id, prescription_item_id, drug_product_id, status, timezone, start_at, end_at, instructions)`.

Schedule rule:

- Missing entirely.
- Current rules are `items[].gio_nhac`, item date range, prescription start/duration, and Python generation logic.
- Need explicit `schedule_rule` rows before generating occurrences.

Dose occurrence:

- Missing as named table.
- Current `dose_event` is functionally closest but wrong semantics and grouped by hour.
- Need clear decision whether V2 occurrence is per medication item or grouped patient-taking event. The target says one row equals one dose the patient should take; current implementation groups all meds at same time into one row for photo UX.

Immutable dose event:

- Missing.
- Current status changes mutate `dose_event.status`.
- Need append-only rows for `TAKEN`, `SKIPPED`, `SNOOZED`, `MISSED_CONFIRMED`, `MANUAL_CORRECTION`, including source and metadata.

Notification:

- Missing `notification_job`.
- Escalation reminders store state on `escalation`; regular dose reminders are not modeled.
- Need source-of-truth separation: notification job should not define dose status.

Safety policy:

- Missing.
- Current safety is code + LLM + legacy metadata + V2 `REVIEW_REQUIRED`.
- Need `medication_safety_policy` with scoped fallback, versioning, source, review status, and resolution priority.

Missed dose assessment:

- Missing.
- Current severity assessment is trace-only in `audit_log` and escalation side effects.
- Need durable `missed_dose_assessment` rows.

Safety event:

- Missing target table.
- Current `escalation` can represent some safety events, but not all audit/security decisions.
- Need `safety_event` for redflags, ambiguous drug, interactions, missed high-risk dose, etc.

Agent audit:

- Missing `agent_run` and `agent_tool_event`.
- Current `audit_log.trace` is useful but not normalized and lacks request/entity actor fields.

## 17. Recommended DB-2 Inputs

Before target schema design, define:

- Canonical mapping from current `dose_event` rows to target `dose_occurrence` and immutable `dose_event`.
- Whether V2 `dose_occurrence` is per drug product or per grouped intake time.
- Compatibility adapter shape that keeps current public DTOs while reading V2.
- Backfill rules for `prescription.items[] -> prescription_item`.
- Backfill rules for `expected_items[] -> medication_plan/schedule_rule/dose_occurrence`.
- Enum mapping for prescription/dose/escalation/photo/chat/account statuses.
- FK rollout sequence: audit invalid references first, then add nullable FKs or validation-only constraints, then enforce.
- Idempotency keys for dose generation, notification dispatch, dose-event writes, and external callbacks.
- Safety policy review workflow and exact enum names for legacy fallback status.

## DB AUDIT RESULT

STATUS:

DB-1 audit complete. Current implementation is an MVP schema with useful operational behavior but not yet aligned with Database Architecture V2.

CURRENT ARCHITECTURE:

PostgreSQL + SQLAlchemy + Alembic. Drug Knowledge is split between V1 DB tables (`drug`, `drug_chunks`) and V2 file-backed canonical artifacts. Operational patient data uses `patient`, `account`, `prescription`, `dose_event`, `photo_verification`, `escalation`, `chat_messages`, `audit_log`, `pending_drug_confirmation`, and `caregiver_link`. Prescription items and expected dose contents are JSON, not normalized.

MAJOR ISSUES:

- `dose_event` has incorrect target semantics: mutable occurrence/status, not immutable event log.
- No `prescription_item`, `medication_plan`, `schedule_rule`, `dose_occurrence`, `notification_job`, `medication_safety_policy`, `missed_dose_assessment`, `safety_event`, `agent_run`, or `agent_tool_event`.
- Minimal FK/check constraints.
- Safety policy is not a DB domain.
- Public/operational tables do not store `drug_product_id`.
- Dose status changes are direct mutations without append-only domain event history.

REUSABLE COMPONENTS:

- PostgreSQL/Alembic foundation.
- Drug V2 facade and legacy slug compatibility.
- Prescription service transaction pattern.
- Existing patient/account/caregiver concepts.
- Photo verification attempt log.
- Escalation/reminder logic as behavioral input for `safety_event`/`notification_job`.
- Current audit traces as source material for agent audit design.

MIGRATION RISKS:

- JSON-to-relational backfill complexity.
- Duplicate dose rows without DB idempotency.
- Missing FK references in existing data.
- Timezone conversion and patient timezone gaps.
- Breaking frontend/API if `drug_id` or dose DTO changes too early.
- Misclassifying legacy `muc_nghiem_trong` as clinical fact.
- Cutover can double-write or lose writes unless compatibility adapter is designed first.

SAFETY POLICY GAPS:

- No policy table, versioning, review status, scope hierarchy, or risk resolution.
- `muc_nghiem_trong` exists only as legacy heuristic metadata and V1 fallback.
- Missed/delayed dose assessments are not durable domain records.
- Safety escalations are stored, but broader safety events and decisions are not normalized.

BREAKING CHANGE RISKS:

- Direct `drug_id` UUID migration would break current contract.
- Direct replacement of `dose_event` semantics would break dose/photo/reporting/agent flows.
- Strict FK/check constraints can break dirty demo/dev data.
- Normalizing prescriptions without adapter would break current API DTOs and frontend.

READY FOR TARGET SCHEMA DESIGN:

YES, with conditions: DB-2 can start, but it must design an additive schema plus compatibility adapter first. Do not implement migrations until the team reviews the mapping for `prescription.items`, current `dose_event`, legacy `drug_id`, and `muc_nghiem_trong` fallback policy.
