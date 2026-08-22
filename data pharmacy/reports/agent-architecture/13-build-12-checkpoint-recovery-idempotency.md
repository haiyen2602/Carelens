# BUILD-12 — Checkpoint, Recovery, and Idempotency

Date: 2026-08-18  
Scope: durable Agent V2 execution checkpoints. `AGENT_RUNTIME_ENABLED=false`
remains unchanged. No production runtime, notification, Agent write action, or
legacy-chat modification was enabled.

## Durable checkpoint boundary

Alembic revision `0033` adds the additive `agent_run_checkpoint` table beside
the existing `agent_run` audit record. There is exactly one checkpoint per
`agent_run_id`, protected by a unique index. The checkpoint stores only the
approved execution state:

- run ID, step number, workflow state, pending action, revision, lease, and
  terminal status;
- completed tool name, deterministic idempotency key, and provenance;
- resolved entity IDs and verified context reference IDs/provenance;
- Safety disposition; and
- created/updated timestamps.

It deliberately excludes message/prompt text, model chain-of-thought, model
output, tool arguments/results, token data, secrets, and unnecessary PII/PHI.
The service validates persisted JSON against strict identifier/provenance-only
schemas before use, so malformed or extra persisted fields fail closed.

## Resume, retries, and duplicate prevention

`claim_resume` locks the checkpoint row and issues an optimistic lease. A
second worker waits on PostgreSQL row locking and then receives a safe busy
result; it cannot execute the same run concurrently. A lease abandoned after a
crash can be reclaimed after its configured maximum age. An unleased stale
checkpoint is closed as `TIMEOUT` rather than resumed with potentially stale
context.

Before a tool action begins, its pending state and stable key are persisted.
The key is based on run, unchanged step, and tool name. Therefore a crash after
a side effect but before `complete_tool` resumes with the identical key. A
completed tool is recorded only with provenance/references; the
`CheckpointedToolGateway` rejects replay and never persists its query or raw
result. Outer transaction rollback removes both `agent_run` and checkpoint.

## Safety, Doctor Handoff, and terminal integration

- `CheckpointedSafetyGateway` records only an authoritative Safety Domain
  outcome plus required verified Safety provenance. `SAFETY_BLOCKED` closes the
  run; `HANDOFF_REQUIRED` creates a Handoff-only pending state.
- `CheckpointedDoctorHandoffGateway` obtains a stable
  `agent-run:<id>:handoff` key only from that Safety-authorized state, supplies
  it to the BUILD-10 Doctor Handoff Gateway, and records `HANDOFF_CREATED`
  only after a handoff ID exists.
- The generic terminal recorder handles `COMPLETED`, `FAILED`,
  `BUDGET_EXCEEDED`, `TIMEOUT`, `SAFETY_BLOCKED`, `HANDOFF_REQUIRED`, and
  `CANCELLED`. It deliberately refuses generic `HANDOFF_CREATED`; that state
  can only come through the Doctor Handoff adapter.

Every public runtime terminal state is durable and a terminal checkpoint cannot
be resumed or mutated.

## Validation

- Migration: local PostgreSQL `alembic upgrade head` and `alembic current`:
  **PASS at `0033`**.
- Unit validation: checkpoint create/idempotency, crash before tool, crash
  after tool, stable retry key, replay prevention, stale handling, lease busy
  behavior, Safety/Handoff integration, all terminal states, sanitized fields,
  and outer transaction rollback: **6 passed**.
- PostgreSQL two-session row-lock validation: second resume blocked until the
  first transaction commits, then safely returned busy; one checkpoint row and
  one lease remained: **1 passed**. Test uses synthetic IDs and deletes them.
- Full Agent V2 regression: **98 passed, 2 skipped**. The two skips are opt-in
  PostgreSQL tests when their disposable-DB environment variables are absent.
- Ruff for changed files and `git diff --check`: **PASS**.

## P0/P1

- **P0: none.** Checkpointing fails closed for malformed/stale state, prevents
  concurrent resumes, and does not expose stored execution internals.
- **P1: checkpoint operational policy.** Before enabling Agent V2, set and
  review production lease/staleness duration, retention/deletion, monitoring
  for stranded checkpoints, and encrypted backup/access controls for the
  operational database.
- **P1: future write tools.** Any future write tool must adopt the same
  checkpoint-before-effect and domain idempotency-key contract; no generic tool
  output persistence is allowed.

## Conclusion

BUILD-12: PASS

CHECKPOINT: PASS

RESUME: PASS

IDEMPOTENCY: PASS

DUPLICATE PREVENTION: PASS

SAFETY/HANDOFF INTEGRATION: PASS

REGRESSION: PASS

READY FOR BUILD-13: YES
