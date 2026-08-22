# BUILD-10 â€” Doctor Handoff

Date: 2026-08-18  
Scope: durable Agent V2 Doctor Handoff domain only. `AGENT_RUNTIME_ENABLED=false`
remains unchanged. No notification provider, legacy escalation replacement,
frontend/API cutover, or automatic clinical reply was added.

## Handoff domain and lifecycle

Alembic revision `0032` adds additive `doctor_review_request` persistence.
The typed lifecycle is:

```text
PENDING â†’ ASSIGNED â†’ ANSWERED
   â””â”€â”€â”€â”€â”€â”€â”€â†’ CANCELLED
ASSIGNED â†’ CANCELLED
```

Only valid server-side transitions are permitted. Only the assigned doctor may
write an answer; terminal requests cannot be cancelled or answered again. The
table records the patient question separately as a patient claim, Safety reason
and disposition, request actor, optional conversation/source-message IDs,
assignment/timestamps, immutable reference/provenance snapshots, and a unique
idempotency key. It is transaction-owned by the caller; the service never
commits independently.

`agent_summary` is deliberately deterministic rather than model-authored. It
contains only the Safety disposition/reason and identifiers of verified
references. The original patient question is not copied into the summary, and
no unverified clinical fact can enter this field through the Agent bridge.

## Doctor resolution and authorization

Automatic assignment uses exactly one relationship: `Patient.doctor_id` must
match exactly one active `Account(role=doctor, doctor_id=...)`. This is the
current explicit responsible-doctor relationship.

`DoctorWatch` is intentionally excluded: existing behavior creates watches
for all doctors for alert visibility, so using it as a routing pool would make
assignment effectively arbitrary. If the responsible doctor is missing,
inactive, ambiguous, or not represented by an active account, a durable
`PENDING` request is created with no assignee. It is never silently routed to
another doctor.

`AuthorizedDoctorHandoffAdapter` first applies the BUILD-1 server-side
actor/patient authorization before it creates a request. An actor mismatch or
cross-patient request fails closed. Doctor answer/assignment transitions also
verify the approved responsible-doctor identity.

## Safety and runtime integration

`DoctorHandoffGateway` accepts creation only when the BUILD-9 `SafetyGateway`
returns `HANDOFF_REQUIRED`. It copies Safety reason/disposition and injects a
mandatory `SAFETY_DOMAIN` reference with the assessment/reason ID and
provenance; `SAFE` or `SAFETY_BLOCKED` cannot create a handoff.

After an authorized domain result exists, `ReadOnlyAgentRuntime` maps it to
the existing terminal state `HANDOFF_CREATED` before any model plan or tool
execution. The generic response says the request was recorded for doctor
review; it does not claim assignment if the request is `PENDING`. There is no
provider job, notification delivery, or automatic doctor selection.

## Idempotency, transaction, and concurrency

The request ID is deterministic from the server-provided idempotency key and a
unique database index protects retries across processes. The create path uses
a transaction savepoint: a concurrent winning insert is re-read as the same
authorized request, while reuse of a key for a different patient/actor is
rejected. No duplicate handoff is created.

Validation used a disposable Docker PostgreSQL database:

```text
clean upgrade: 0001 â†’ 0032
downgrade:     0032 â†’ 0031
re-upgrade:    0031 â†’ 0032
```

Two simultaneous PostgreSQL sessions using the same idempotency key were
verified: the second session waited for the first transaction, then returned
the existing request (`created=false`); one durable row remained.

## Validation

- Lifecycle: auto-assignment, PENDING missing-doctor behavior, assignment,
  answer, cancellation, invalid transitions, and outer transaction rollback.
- Authorization: patient self access succeeds; cross-patient access and
  non-assigned doctor answers fail closed.
- Safety: only `HANDOFF_REQUIRED` creates a request; Safety provenance is
  mandatory; runtime reaches `HANDOFF_CREATED` without invoking model/tools.
- Idempotency: retry returns existing row; conflicting authorized context is
  rejected; real PostgreSQL two-session serialization passed.
- PostgreSQL migration upgrade, downgrade/re-upgrade, revision check: PASS at
  `0032`.
- Focused Agent V2, Safety Domain, and legacy-safety regression: **110
  passed**; PostgreSQL concurrency test: **1 passed**.
- Ruff and `git diff --check`: PASS.

## P0/P1

- **P0: none.** There is no fallback to broad `DoctorWatch`, no client/model
  doctor selection, and no provider side effect.
- **P1: approved care-team/routing model.** The current schema has only the
  responsible doctor relationship suitable for automatic assignment. A real
  care-team/rota model needs its own reviewed contract before it can be used.
- **P1: operational orchestration/UI.** The Agent V2 endpoint remains OFF and
  does not yet resolve an authenticated dose/message into a Handoff Gateway
  call. BUILD-11/12 must retain this authorization and idempotency boundary
  when orchestration/checkpointing is introduced.
- **P1: notification and recipient delivery.** Intentionally out of scope;
  `PENDING`/`ASSIGNED` handoffs do not send a provider message.

## Conclusion

BUILD-10: PASS

HANDOFF DOMAIN: PASS

DOCTOR RESOLUTION: PASS

AUTHORIZATION: PASS

IDEMPOTENCY/CONCURRENCY: PASS

SAFETY INTEGRATION: PASS

PROVENANCE: PASS

REGRESSION: PASS

READY FOR BUILD-11: YES
