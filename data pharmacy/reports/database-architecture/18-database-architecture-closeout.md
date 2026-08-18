# 18 Database Architecture V2 Closeout

Scope: closeout review of Database Architecture V2, DB-1 through DB-4I. This
report records the implemented repository boundary and its validation evidence;
it does not activate runtime paths, deploy infrastructure, or introduce a new
feature.

## Review basis

Reviewed reports `01-current-db-audit.md` through
`17-safety-escalation-policy.md`, the current Alembic chain, V2 SQLAlchemy
models/services/import scripts, Final Canonical V2 manifest/artifacts, and the
current branch state. The current repository checks passed:

- `alembic heads` reports only `0027 (head)`.
- Drug Identity importer dry-run re-verified the manifest and all five
  import inputs without database access: `3,556` products/maps, `1,406`
  ingredients, and `5,287` importable links; `491` unresolved ingredient
  links and one duplicate valid pair remain explicitly excluded.
- Legacy-category policy seed dry-run re-verified the manifest and found `49`
  categories.
- Focused DB-domain regression suite: `48 passed, 2 skipped` (the two
  PostgreSQL opt-in tests are skipped without a disposable DB URL).
- Root pytest collection is still blocked before collection by the unrelated
  FastAPI `204` response-body assertion in `backend/api/caregiver_routes.py`.

The previous DB-4B through DB-4I reports provide clean Docker/PostgreSQL
upgrade/import/locking evidence. No existing local Docker volume or patient
data was used for this closeout review.

## Final V2 architecture

V2 is additive beside the legacy operational schema. It preserves public
legacy IDs and runtime behavior while creating an internal canonical identity
and normalized operational path.

| Area | Final V2 boundary |
| --- | --- |
| Drug identity | `drug_product`, `drug_id_map`, `ingredient`, and `drug_product_ingredient`; public `drug_id` remains the legacy slug, while `drug_product_id` is the internal canonical ID. |
| Prescription | `prescription_item` retains raw dose/frequency/instructions and migration traceability; `medication_plan` models one patient/product plan. |
| Scheduling | `schedule_rule` retains compatible JSON `times_of_day`; `schedule_rule_time` normalizes local times and `schedule_rule_cycle` models on/off cycles. End date is inclusive. |
| Occurrences | One `dose_occurrence` represents one drug at one scheduled local date/time; it persists UTC time, local date/time, timezone, and deterministic generation key. |
| State/history | `dose_occurrence` stores current state. `dose_event_log` is the append-only V2 history and deliberately does not collide with legacy `dose_event`. |
| Notifications | `notification_job` is an idempotent outbox/state record, not a provider integration or truth source for dose state. |
| Safety | `medication_safety_policy` resolves `DRUG_PRODUCT -> INGREDIENT -> CATEGORY -> SYSTEM_DEFAULT`; `missed_dose_assessment` stores immutable provenance snapshots; `safety_event` records decisions. |
| Escalation | DB-4I records an auditable V2 decision and permitted outbox job only for matching reviewed policy provenance. Legacy category fallback is never promoted to automatic clinical escalation. |

V2 write and generation boundaries are transaction-safe and use deterministic
keys/unique indexes. They fail closed to `REVIEW_REQUIRED` or
`REQUIRE_MEDICAL_REVIEW` when identity, schedule, policy provenance, or
risk/action conditions are unclear.

## Migration chain `0023 -> 0027`

The revision numbers require an explicit closeout note: the originally drafted
DB-4A migration was renumbered because `0023` and `0024` were already occupied
by merged legacy migrations. Therefore the Database Architecture V2 additive
schema is `0025`, not the current `0023`.

| Revision | Contents | Closeout status |
| --- | --- | --- |
| `0023` | Legacy patient profile fields (`phone`, `address`, `date_of_birth`, `profile_completed`). | Retained, reversible. |
| `0024` | Legacy `doctor_watch` table; replaces shared patient watch flag. | Retained, reversible. |
| `0025` | DB-4A additive V2 schema: canonical identity, prescription/schedule/occurrence, immutable event log, notification, safety, and V2 audit tables; nullable migration fields and no legacy table redefinition. | PASS. |
| `0026` | DB-4D normalized time/cycle schedule schema and local occurrence context. | PASS; reversible to `0025`. |
| `0027` | DB-4H nullable policy source/review snapshots on `missed_dose_assessment`. | PASS; current head. |

No V2 FK, strict `NOT NULL`, enum/check hardening, or legacy-table deletion was
introduced. That is intentional compatibility staging, not an omitted
migration.

## Drug identity and compatibility

Final Canonical V2 is repository-tracked and manifest-verified at
`canonical-v2-final-2026-08-16` (`quality_status=PASS`, `rag_status=PASS`).
The importer is identity/reference-only, local-PostgreSQL guarded, idempotent,
and does not mutate artifacts or change `DRUG_KNOWLEDGE_BACKEND`.

DB-4B clean-database validation imported `3,556` products, `3,556` active
maps, `1,406` ingredients, and `5,287` valid links with zero orphans and zero
duplicate active legacy mappings. It deliberately did not infer the remaining
`491` unresolved ingredient relationships or one duplicate valid pair.

Legacy API/runtime compatibility remains in place:

- legacy `drug_id`, `prescription.items[]`, `dose_event`, and legacy
  `escalation` continue unchanged;
- V2 does not cut over Drug Knowledge/Search/RAG;
- V2 `dose_event_log` avoids collision with legacy `dose_event`;
- no prescription/dose backfill was invented for the confirmed empty legacy
  operational source.

## Prescription, scheduling, occurrence, and reminder gates

- DB-4C importer and controlled-corpus tests passed. Real local/dev legacy
  source reconciliation found `0` prescriptions and `0` items, so operational
  backfill is correctly **NO-OP / NOT APPLICABLE**, not a fabricated dataset.
- DB-4D normalized time/cycle schema, upgrade/downgrade/re-upgrade and legacy
  compatibility checks passed.
- DB-4E doctor write path atomically creates the V2 chain and activates only
  fully resolved valid schedules; uncertain inputs stay `REVIEW_REQUIRED`.
- DB-4F bounded occurrence generation enforces inclusive dates, cycle,
  timezone/DST handling, deterministic keys, and one-drug/one-time granularity.
- DB-4G enforces the V2 state graph and immutable event/outbox records with
  PostgreSQL row-lock/idempotency coverage. It does not run a scheduler or send
  notifications.

## Safety policy and escalation gates

DB-4H persisted idempotent safety assessment/event/log records with product,
ingredient, category, then fail-closed default policy resolution. The only
legacy seed shape is `CATEGORY + MISSED_DOSE + LEGACY_CATEGORY_RULE +
LEGACY_UNREVIEWED`; the manifest-verified seed has 49 categories.

DB-4I permits notification-outbox escalation only for matching `REVIEWED`
policy provenance from approved sources and a conservative risk/action matrix.
Unreviewed legacy fallback, unknown identity/risk, missing/superseded policy,
and unsupported actions become `REQUIRE_MEDICAL_REVIEW` with no job. DB-4I
clean PostgreSQL tests covered idempotency, rollback and two-session row locks.

## Reproducible clean-local-DB checklist

This creates a disposable local database only. Do not point any command below
at Railway, a shared database, or a local volume containing patient data.

1. Check out the required commit and confirm only intended changes exist:

   ```powershell
   git checkout feature/database-architecture-v2
   git pull --ff-only
   git status --short
   ```

2. Install the repository's normal Python dependencies, then verify the
   tracked canonical artifacts before DB access:

   ```powershell
   $env:PYTHONPATH='.'
   python scripts/data_v2/import_drug_identity_v2.py --dry-run
   python scripts/data_v2/seed_legacy_category_safety_policies.py --dry-run
   ```

   Both commands must report the manifest version above and unchanged hashes.
   Stop if either reports a mismatch.

3. Start a disposable pgvector PostgreSQL 16 container with no volume (choose
   an unused local port):

   ```powershell
   docker run -d --rm --name p067-db-v2-closeout `
     -e POSTGRES_USER=vmec -e POSTGRES_PASSWORD=vmec -e POSTGRES_DB=vmec04 `
     -p 5434:5432 pgvector/pgvector:pg16
   $env:DATABASE_URL='postgresql://vmec:vmec@localhost:5434/vmec04'
   ```

4. Build the schema from repository migrations and confirm the only head:

   ```powershell
   alembic upgrade head
   alembic current
   alembic heads
   ```

   Expected current/head revision: `0027`.

5. Import canonical identity twice, then seed the conservative legacy category
   policies twice. The second run of each must create zero duplicate rows:

   ```powershell
   python scripts/data_v2/import_drug_identity_v2.py --database-url $env:DATABASE_URL
   python scripts/data_v2/import_drug_identity_v2.py --database-url $env:DATABASE_URL
   python scripts/data_v2/seed_legacy_category_safety_policies.py --database-url $env:DATABASE_URL
   python scripts/data_v2/seed_legacy_category_safety_policies.py --database-url $env:DATABASE_URL
   ```

6. Run focused DB-domain tests. For the two PostgreSQL locking tests, set
   `DB4I_TEST_DATABASE_URL` to the same disposable URL:

   ```powershell
   $env:DB4I_TEST_DATABASE_URL=$env:DATABASE_URL
   pytest tests/data_v2/test_import_drug_identity_v2.py `
     tests/data_v2/test_backfill_prescription_v2.py `
     tests/services/scheduling/test_write_path.py `
     tests/services/scheduling/test_occurrence_generator.py `
     tests/services/scheduling/test_dose_state.py `
     tests/services/safety_policy_domain/test_service.py `
     tests/services/safety_policy_domain/test_escalation.py `
     tests/services/safety_policy_domain/test_escalation_postgres.py --noconftest -q
   ```

7. Stop the disposable container when finished:

   ```powershell
   docker stop p067-db-v2-closeout
   ```

The canonical artifacts are committed and contain no patient records. Real
legacy prescription data must never be copied into Git; if a non-empty source
appears later, it must use the DB-4C privacy-safe reconciliation gate before
backfill.

## Gates and remaining debt

All Database Architecture task gates through DB-4I are PASS within the stated
additive, local-validation scope. No P0 blocker was found in this closeout
review.

P1 technical debt and follow-up gates:

- Repository-wide pytest collection is blocked by the existing FastAPI `204`
  route response-body assertion; it is outside the V2 database domain but
  should be fixed before asserting a full repository test gate.
- Legacy Alembic metadata/index drift remains; it needs a separate metadata
  hygiene task.
- FK, `NOT NULL`, enum/check, and active-plan uniqueness hardening remain
  deliberately deferred until non-empty operational data is validated.
- Final Canonical V2 retains 491 unresolved ingredient links and one duplicate
  valid product/ingredient pair; they require a provenance/canonical decision,
  not automatic mapping.
- A future non-empty legacy prescription source still needs a privacy-safe
  snapshot/reconciliation run; the currently observed source is empty.
- ADR-0012 remains `Proposed`; its compatibility/provenance governance needs
  formal approval before any runtime cutover or production use.

## Explicitly outside Database Architecture V2

The following are next-phase work and are not completed or authorized by this
closeout:

- Agent integration;
- production scheduler invocation/window ownership;
- caregiver/clinician recipient resolution;
- notification-provider delivery and callbacks;
- Railway deployment, runtime cutover, dual-write, or legacy retirement.

## DATABASE ARCHITECTURE V2: COMPLETE

## FINAL ALEMBIC HEAD: `0027`

## P0: None found within the reviewed Database Architecture scope.

## P1: Listed in "Gates and remaining debt"; none authorizes bypassing a
validation, provenance, or legacy-compatibility gate.

## REPRODUCIBLE LOCAL DB: YES

## RAILWAY DEPLOYED: NO

## READY FOR NEXT ARCHITECTURE PHASE: YES

The next phase must choose and approve its own runtime/cutover scope. It must
not treat this closeout as authorization to deploy, send notifications, or
allow an Agent to make clinical or policy decisions.
