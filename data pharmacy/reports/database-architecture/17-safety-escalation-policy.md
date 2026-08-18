# 17 Safety Escalation Policy (DB-4I)

Scope: DB-4I adds a V2 escalation-decision and notification-outbox boundary
after a DB-4H `missed_dose_assessment`. It does not send a provider message,
resolve caregiver/clinician accounts, integrate an Agent, alter legacy
`escalation` runtime/API behavior, generate dose advice, or deploy Railway.

## Implemented boundary

`backend/services/safety_policy_domain/escalation.py` exposes
`process_safety_escalation`. In the caller transaction it locks the assessment
and occurrence, verifies assessment provenance against the current policy, and
writes an immutable `safety_event`, an immutable `dose_event_log`, and, only
when permitted, a queued `notification_job` outbox row.

The safety event type is `SAFETY_ESCALATION_DECIDED`. It records the decision,
not delivery. The notification job is an outbox only: no provider call or
recipient-account lookup occurs. Patient jobs use the patient ID; caregiver
and clinician jobs retain the role only, avoiding unsafe legacy-data inference.

IDs and idempotency keys are deterministic from the assessment plus
`DB4I_ESCALATION_V1`. Existing V2 schema has the necessary tables, indexes and
unique keys, so no migration is required. This boundary intentionally never
writes the legacy `escalation` table.

## Escalation policy matrix

Automatic delivery requires both the assessment snapshot and current policy to
be `REVIEWED` with source `CLINICAL_REVIEW`, `DRUG_LABEL`, or `GUIDELINE`.

| Risk level | Permitted automatic actions |
| --- | --- |
| `LOW` | `LOG_ONLY`, `REMIND`, `WARN` |
| `MODERATE` | `LOG_ONLY`, `REMIND`, `WARN`, `ESCALATE_CAREGIVER` |
| `HIGH` / `CRITICAL` | `LOG_ONLY`, `REMIND`, `WARN`, `ESCALATE_CAREGIVER`, `ESCALATE_CLINICIAN` |
| `UNKNOWN` | `REQUIRE_MEDICAL_REVIEW` only |

`LOG_ONLY` has no job. `REMIND`/`WARN` create patient jobs; the two escalation
actions create role-targeted jobs. Unsupported risk/action pairs, missing or
superseded policy, unknown risk, and `REQUIRE_MEDICAL_REVIEW` fail closed to
`REQUIRE_MEDICAL_REVIEW` without a notification job.

## Legacy guard

`CATEGORY + LEGACY_CATEGORY_RULE + LEGACY_UNREVIEWED` cannot pass the automatic
delivery gate. It is recorded as `REQUIRE_MEDICAL_REVIEW`, with no outbox job,
even if stale input requests caregiver or clinician escalation. This does not
promote legacy `muc_nghiem_trong` into clinical advice or strong escalation.

## Validation completed

- Focused SQLite tests: 16 passed for DB-4H regression and the DB-4I action
  matrix, caregiver/clinician routing, legacy guard, rerun, and rollback.
- `ruff check backend/services/safety_policy_domain
  tests/services/safety_policy_domain` and `git diff --check`: passed.
- Fresh PostgreSQL 16 + pgvector Docker on port `5434`, with no mounted volume:
  `alembic upgrade head` reached `0027 (head)`.
- PostgreSQL-specific tests: 2 passed. They verified one reviewed high-risk
  clinician decision yields exactly one event, dose log, and job; the second
  session blocks on the assessment row lock and writes no duplicate after the
  first transaction commits.
- PostgreSQL rollback left zero event/log/job rows. Rerunning an unreviewed
  legacy assessment gave `REQUIRE_MEDICAL_REVIEW` with no job.
- Root pytest collection remains independently blocked by the pre-existing
  FastAPI assertion for a `204` route with a response body in
  `backend/api/caregiver_routes.py`; DB-4I did not modify that route.

## DB-4I: PASS

## ESCALATION POLICY: PASS

The reviewed-policy provenance gate and conservative risk/action matrix are
implemented without unapproved clinical guidance.

## LEGACY GUARD: PASS

An unreviewed legacy category rule cannot automatically create caregiver or
clinician escalation.

## NOTIFICATION JOB: PASS

The idempotent V2 outbox is created only for permitted automatic actions; it
does not deliver a notification.

## IDEMPOTENCY: PASS

Rerun returns the existing V2 event/job and creates zero rows.

## CONCURRENCY: PASS

The clean-PostgreSQL two-session test verified assessment row-lock
serialization and one final event, log, and job.

## FAIL-CLOSED: PASS

Unclear policy/identity provenance, unsupported risk/action pairs and unknown
risk produce `REQUIRE_MEDICAL_REVIEW` with no notification job.

## P0/P1:

- P0: None.
- P1: The unrelated root pytest FastAPI `204` collection issue remains.
- P1: Recipient resolution and delivery are intentionally deferred; a
  role-targeted job is not provider delivery.

## READY FOR AGENT INTEGRATION: YES

An Agent may later invoke only this audited V2 boundary; it must not write
policies, bypass provenance, or turn legacy fallback into medical advice.
