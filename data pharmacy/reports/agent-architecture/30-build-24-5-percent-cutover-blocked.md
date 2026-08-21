# BUILD-24 — 5% Production Cutover (BLOCKED at pre-flight)

**Scope:** turn on Agent V2 for 5% of production traffic. **Per this
build's own explicit instruction, a pre-flight failure on either the
OpenAI key rotation or the DB backup/PITR check means STOP and report the
blocker — do not enable 5%.** That is exactly what happened.

**Environment:** Railway production (`VMEC-04/BE`, `VMEC-04/Postgres`).

---

## Pre-flight results

| Check | Result |
|---|---|
| OpenAI key rotated since BUILD-23's incident | **FAIL — not rotated** |
| DB backup / PITR enabled | **UNCONFIRMED — cannot verify with available tooling** |
| Migrations = 0034 | PASS |
| V2 data/corpus identity | PASS |
| Model/pricing config | PASS |
| Legacy chat healthy | PASS |
| Rollback / kill-switch ready | PASS (starting state: `AGENT_RUNTIME_ENABLED=false`) |

### OpenAI key: confirmed still the pre-incident key

Checked safely this time — only the value's **length** and **last 4
characters** were read into memory and compared, never printed or
re-derived in full. Production `OPENAI_API_KEY` is still 164 characters
ending `...7WQA`, which matches the exact key that leaked into this
session's transcript during BUILD-23 (see report `29-build-23`, Section 7).
**It has not been rotated.** Per this build's instruction, this alone is
sufficient to stop.

### DB backup / PITR: still not independently verifiable

Same finding as BUILD-23: the Railway CLI available in this environment
has no `backup`/`snapshot`/PITR subcommand (checked again this build,
confirmed absent), and no Postgres client tooling (`pg_dump`) is installed
locally to take a manual one. This can only be resolved by checking the
Railway dashboard (Settings → Backups on the Postgres service) directly, or
by running a scripted `pg_dump` from an environment that has the tooling —
neither of which this session can do on its own.

### Everything else genuinely re-verified, not assumed

Re-checked live rather than trusted from memory:
- `alembic_version = 0034` (matches repo head).
- `drug_chunks`: 14,447 legacy / 14,423 other / 28,870 total — unchanged
  since BUILD-21, confirming no drift or accidental mixing since the last
  check.
- `drug_product` = 3,556 (V2 catalog intact).
- `medication_safety_policy` — exactly 1 row with `review_status=REVIEWED`
  (the BUILD-22C Vitamin C policy, unchanged).
- `/health` → `200 {"status":"ok"}`; `/api/v1/chat` → `401` for an
  unauthenticated request (healthy, not a 5xx crash).
- `AGENT_RUNTIME_ENABLED=false` — the correct starting position for a
  rollback-ready pre-flight.

---

## What did NOT happen

- `AGENT_RUNTIME_ENABLED` was **not** set to `true`.
- `AGENT_ROLLOUT_PERCENTAGE` was **not** set to `5`.
- No production traffic was routed to Agent V2. No monitoring data exists
  for this build because nothing was turned on to monitor.
- No legacy data was touched.

---

## Action items before BUILD-24 can be re-attempted

1. **Actually rotate `OPENAI_API_KEY`** (OpenAI dashboard → revoke the
   current key → create a new one → `railway variable set
   "OPENAI_API_KEY=<new key>" --service "VMEC-04/BE" --environment
   production --skip-deploys` → redeploy). Check whether staging shares the
   same key or has its own, and rotate that reference too if shared.
2. **Confirm DB backup/PITR status** via the Railway dashboard, or set up a
   scripted backup if none exists, and report back which is true.

Once both are confirmed, re-run this same pre-flight (all the
independently-re-verifiable items already pass) and proceed to the actual
5% rollout in a follow-up build.

---

## Closeout

```
BUILD-24: FAIL
OPENAI KEY ROTATED: NO
DB BACKUP/PITR: FAIL (unconfirmed with available tooling -- see report body)
5% ROLLOUT: NOT_STARTED
SAMPLE SIZE: 0 (nothing was turned on)
OBSERVATION DURATION: 0
ERROR RATE: N/A
EMPTY REPLY RATE: N/A
P95/P99: N/A
AVG COST/REQUEST: N/A
SAFETY: N/A (not exercised this build)
HANDOFF: N/A (not exercised this build)
AUTHORIZATION: N/A (not exercised this build)
IDEMPOTENCY: N/A (not exercised this build)
RAG: N/A (not exercised this build)
VINMEC WEB: DEGRADED (unchanged carry-forward status, not re-tested -- rollout never started)
P0/P1: P0=0; P1=1 open -- production OpenAI API key known-exposed and not yet rotated (see report 29-build-23 Section 7 and this report); DB backup/PITR status unknown is a P1-severity gap for a production cutover decision until confirmed either way
LEGACY FALLBACK: PASS (legacy chat confirmed healthy; nothing changed for it)
READY FOR 20%: NO
READY TO DELETE LEGACY DATA: NO
```
