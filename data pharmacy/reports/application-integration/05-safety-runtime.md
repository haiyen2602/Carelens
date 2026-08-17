# APP-5 - Safety Runtime Integration

Date: 2026-08-17
Scope: connect V2 patient-dose `MISSED` and `DELAYED` transitions to the audited DB-4H/DB-4I safety domains. No Agent, Railway, provider delivery, production scheduler, or public safety API change.

## Runtime boundary

`SAFETY_RUNTIME_MODE` is a server-side, fail-safe feature flag:

- `legacy` (default): APP-5 does not run V2 safety processing; legacy runtime behavior remains unchanged.
- `shadow`: after each V2 grouped-dose transition to `MISSED` or `DELAYED`, the adapter invokes the APP-5 runtime bridge in the existing transaction.

The bridge contains no risk, clinical, recipient, or escalation inference. It calls the approved services in sequence:

```text
V2 MISSED / DELAYED occurrence
  -> assess_dose_safety
  -> missed_dose_assessment + SAFETY_ASSESSMENT_CREATED
  -> safety_event
  -> process_safety_escalation
  -> SAFETY_ESCALATION_DECIDED + eligible notification_job outbox
```

The V2 dose state domain still exclusively owns the transition itself and immutable occurrence events. The runtime bridge owns only orchestration after a terminal state; it never updates tables directly. Cancellation remains excluded from this path, so edit/stop cancellation cannot trigger safety processing.

## Safety and escalation guards

Policy resolution remains exactly `DRUG_PRODUCT -> INGREDIENT -> CATEGORY -> SYSTEM_DEFAULT`.

- A reviewed policy with eligible provenance may keep its approved action and create an idempotent outbox row.
- `CATEGORY + LEGACY_UNREVIEWED`, missing policy, ambiguous identity, ambiguous ingredient policy, and review-required provenance create auditable fail-closed assessments/decisions with `REQUIRE_MEDICAL_REVIEW`.
- Those fail-closed outcomes create no patient/caregiver/clinician notification job and never produce dose/catch-up clinical advice.
- The outbox is persistence only. No notification provider, recipient resolution, legacy escalation table, API/UI clinical decision, or Agent is called.

All services flush but do not commit. A failed state/safety/escalation command rolls back its occurrence change, assessment, dose-event logs, safety events, and queued job as one caller-owned transaction.

## Validation

A disposable `pgvector/pgvector:pg16` PostgreSQL container was created on port 5433 with no mounted or reused volume.

- `alembic upgrade head` reached `0027`.
- Canonical Drug Identity import created `3556` products, `3556` maps, `1406` ingredients, and `5287` valid product/ingredient links. Its re-run created `0` rows.
- The Final Canonical V2 manifest hashes were identical before and after both imports.
- Legacy category policy seed created `49` rows and its re-run created `0` rows.
- Focused APP-3 through APP-5 clean-PostgreSQL suite: `82 passed`.
- The suite covers reviewed escalation/outbox, legacy-unreviewed and unknown-identity fail-closed outcomes, retry/idempotency, caller rollback, V2 grouped-dose integration, duplicate prevention, and two-session PostgreSQL row locking. The concurrency gate verifies exactly one assessment, two safety events (assessment and decision), one notification outbox job, and two safety dose-event logs for concurrent processing of one occurrence.
- `ruff check` and `git diff --check` passed.

## Compatibility and limits

The default remains `SAFETY_RUNTIME_MODE=legacy`; existing legacy dose, chat, escalation, and frontend/API DTO paths are unchanged. In `shadow`, the V2 patient-dose endpoint keeps its current grouped response and only adds durable internal V2 audit/outbox effects.

The current integration point is the APP-4 V2 patient-dose adapter. A future production scheduler must call the same `process_dose_safety_runtime` bridge after it transitions an occurrence to `MISSED`; it must not reimplement policy logic. Scheduler production remains explicitly out of scope.

## Conclusion

APP-5: PASS

SAFETY ASSESSMENT: PASS - V2 `MISSED`/`DELAYED` transitions invoke the audited resolver and persist an idempotent assessment and safety event in shadow mode.

ESCALATION: PASS - the DB-4I decision service creates an outbox job only for eligible reviewed provenance; no provider is invoked.

FAIL-CLOSED: PASS - unknown/ambiguous identity and unreviewed legacy policy resolve to `REQUIRE_MEDICAL_REVIEW` without clinical advice or automatic escalation.

COMPATIBILITY: PASS - default runtime remains legacy; no frontend/API DTO, legacy escalation, chat, or notification-provider behavior changed.

IDEMPOTENCY/CONCURRENCY: PASS - retry, transaction rollback, unique keys, and two-session PostgreSQL locking passed.

P0/P1:

- P0: none.
- P1: wire any future scheduler's automatic `MISSED` transition through the same runtime bridge before enabling a scheduler; it must not call safety tables or policy logic directly.
- P1: recipient resolution and provider dispatch remain later, separate operational gates. Outbox persistence is not notification delivery.
- P1: legacy chat/photo/escalation flows remain separate compatibility paths pending APP-6 shadow comparison; they are not implicitly switched to V2 safety.

READY FOR APP-6: YES
