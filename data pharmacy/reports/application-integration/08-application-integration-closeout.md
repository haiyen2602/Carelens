# APP-8 - Application Integration V2 Closeout

Date: 2026-08-18
Scope: closeout review of APP-1 through APP-7. No feature implementation, Railway deployment, Agent integration, production scheduler, notification provider, or runtime cutover was performed.

## Phase outcome

Application Integration V2 is complete for the approved local, incremental integration boundary. The application preserves legacy public contracts and has verified V2 paths behind explicit feature flags. The outcome does not authorize a production cutover.

## Final runtime map

| Flow | Integrated V2 boundary | Local validated mode | Public compatibility source |
| --- | --- | --- | --- |
| Drug search/select | Canonical V2 catalog and active identity resolution | `DRUG_KNOWLEDGE_BACKEND=v2` | Existing legacy-compatible drug DTO (`drug_id` remains the public value) |
| Doctor prescription | Atomic legacy prescription plus deterministic V2 item/plan/rule/time/cycle sidecar | `PRESCRIPTION_V2_MODE=shadow` | Legacy `Prescription` payload and lifecycle response |
| Dose/schedule | Bounded per-drug V2 occurrence generation, grouped-dose adapter, state domain | `DOSE_RUNTIME_MODE=shadow` | Legacy grouped `DoseEvent` DTO/read path |
| Safety/escalation | V2 assessment, provenance-gated decision, durable event and outbox | `SAFETY_RUNTIME_MODE=shadow` for V2 terminal-state validation | Legacy chat/photo/escalation UI/API remains separate |

The V2 model remains one `dose_occurrence` per medicine and intended time. The legacy grouped dose card is an adapter projection only; it is not the V2 source of truth.

## Completed integration evidence

### Doctor Prescription V2

- Doctor create, edit, approve, and stop commands use the application service transaction that preserves legacy behavior and synchronizes deterministic V2 scheduling intent.
- The sidecar chain is `prescription_item -> medication_plan -> schedule_rule -> schedule_rule_time -> optional schedule_rule_cycle`.
- Canonical identity must resolve before a V2 plan/rule can become active. Uncertain drug identity or schedule remains `REVIEW_REQUIRED`; no schedule is guessed.
- `end_date` is inclusive; doses/day, meal, distinct times, date range, cycle, and timezone are validated at the V2 boundary.
- Edit/stop after generated occurrences cancel/supersede only future scheduled work; terminal occurrence history remains immutable and cancellation cannot trigger safety.

### Dose/Schedule runtime

- ACTIVE, fully resolved V2 plans create bounded, timezone-aware occurrences with deterministic generation keys.
- V2 state transitions are routed through the audited state machine: `SCHEDULED -> DUE -> TAKEN / DELAYED / MISSED / SKIPPED`.
- Same-time medicines are grouped only for the compatibility DTO while retaining independent occurrences and state/event history.
- Retries, transactions, locking, DST/timezone, cycles, inclusive date bounds, edit/stop, and cancellation were validated on disposable PostgreSQL.

### Safety runtime

- V2 `MISSED`/`DELAYED` events call `assess_dose_safety` and then `process_safety_escalation` in the same caller-owned transaction.
- Reviewed, eligible policy provenance may create an idempotent notification outbox row. The outbox is not provider delivery.
- Ambiguous identity, unknown policy, and legacy-unreviewed category policy fail closed as `REQUIRE_MEDICAL_REVIEW`; they do not create clinical advice or automatic escalation.

### Shadow, compatibility, and rollback

- Legacy API/DTO shape, legacy reads, photo verification, chat, and existing escalation paths remain available.
- The clean PostgreSQL shadow comparison found and corrected one V2 same-time item-order defect; no unresolved V2 bug or canonical-artifact mismatch remained.
- Rollback is flag-based for new traffic: retain deterministic V2 rows for traceability and return to legacy/shadow behavior. There is no destructive data rollback.

## Feature flags and safe defaults

| Setting | Default | Validated local setting | Rollback boundary |
| --- | --- | --- | --- |
| `DRUG_KNOWLEDGE_BACKEND` | `v2` | `v2` | Explicit `v1` or catalog `shadow` |
| `PRESCRIPTION_V2_MODE` | `legacy` | `shadow` | `legacy` preserves V2 trace rows but stops new sidecar writes |
| `DOSE_RUNTIME_MODE` | `legacy` | `shadow` | `legacy`; do not enable full `v2` patient UI without a photo bridge |
| `SAFETY_RUNTIME_MODE` | `legacy` | `shadow` | `legacy`; no provider delivery is implied by either mode |

No flag silently falls back after an uncertain write. Invalid/unresolved clinical data is handled as an explicit review-required disposition rather than an inferred mapping.

## Local E2E and manual acceptance

- Disposable PostgreSQL reached Alembic revision `0027`.
- Final Canonical V2 import created `3556 / 3556 / 1406 / 5287` target rows; the second import created zero rows and artifact hashes were unchanged.
- The legacy category safety seed created 49 rows and its re-run created zero rows.
- APP-7 automated matrix: 89 passed, 3 conditional skips, 0 failures; catalog/prescription regression after the autocomplete correction: 3 passed.
- Manual frontend acceptance: PASS. Doctor flow manual: PASS. Patient dose flow manual: PASS. The local tester reported no 5xx, duplicate, or material user-visible regression in the completed session.
- Browser automation was not added; manual acceptance is recorded evidence, not a replacement claim for a browser-E2E suite.

## Remaining P0/P1

- P0: none identified for the approved local integration scope.
- P1: design and validate the V2 photo-verification bridge before enabling `DOSE_RUNTIME_MODE=v2` for the complete patient UI.
- P1: add separately approved browser E2E automation; current frontend acceptance is manual only.
- P1: define reviewed shared clinical-policy and recipient-resolution semantics before asserting equivalence between legacy chat/photo escalation and V2 missed-dose safety.
- P1: replace the current V2 grouped-dose lookup scan with a direct indexed lookup before high-volume runtime use.
- P1: production scheduler, recipient resolution, and provider delivery require their own operational, safety, and deployment gates.

## Explicitly outside Application Integration V2

- Agent/LLM runtime integration and clinical behavior;
- production scheduler activation;
- caregiver/clinician recipient resolution;
- push, SMS, email, or other notification-provider delivery;
- Railway deployment, production database cutover, and legacy retirement/deletion.

## Conclusion

APPLICATION INTEGRATION V2: COMPLETE

P0:

- None for local integration closeout.

P1:

- V2 photo bridge, browser E2E automation, reviewed shared safety/recipient semantics, indexed group lookup, and separate production scheduler/provider gates.

DOCTOR PRESCRIPTION V2: PASS - atomic V2 scheduling sidecar is integrated with the doctor flow while preserving legacy DTOs and review-required safety.

DOSE RUNTIME V2: PASS - bounded generation, compatibility grouping, audited state transitions, future-work cancellation, retry, and locking passed locally behind explicit modes.

SAFETY RUNTIME V2: PASS - V2 terminal states reach fail-closed assessment, escalation decision, durable audit, and outbox-only behavior.

LOCAL E2E: PASS - clean PostgreSQL, manifest-verified artifacts, import/seed idempotency, and automated application matrix passed.

MANUAL FRONTEND ACCEPTANCE: PASS - doctor and patient-dose local flows were accepted by the tester; no 5xx, duplicate, or material user-visible regression was reported.

LEGACY FALLBACK AVAILABLE: YES - explicit `legacy`/`shadow` modes and unchanged legacy public DTO/read paths remain available.

READY FOR AGENT ARCHITECTURE: YES - a separate Agent phase may begin against these audited boundaries; it is not authorized to make clinical decisions or bypass policy domains.

READY FOR PRODUCTION SCHEDULER: NO - scheduler operation, recipient resolution, delivery provider, and production safety gates are not in this phase.

READY FOR RAILWAY DEPLOYMENT: NO - this closeout does not authorize deployment or production cutover.
