# BUILD-17 — Railway Staging Deployment Readiness

Date: 2026-08-18
Scope: audit + checklist + read-only verification tooling only. **No Railway
staging environment was created, no variable was set, no deploy was run, and
no production resource was queried or modified.** `AGENT_RUNTIME_ENABLED`
stays `false` everywhere; legacy chat is not routed to Agent V2.

## Why this report stops before deployment

`railway whoami`/`railway status` confirm this session *is* authenticated
against a real project:

```
Project:      VMEC-04 (workspace: haiyen2602's Projects)
Environments: production only  <-- railway environment list --json
Services:     VMEC-04/FE (online), VMEC-04/BE (online), Postgres (online)
```

`railway environment list` shows exactly one environment, `production`, and
it is live and serving real traffic (`docs/DEPLOY.md`, both services
Online). **No staging environment exists.** This is precisely the condition
the task describes as "Railway credentials/environment chưa có": credentials
exist, but the target (staging) environment does not.

Creating it — `railway environment new staging --duplicate production` —
would provision new billed resources and, depending on how Railway's
environment duplication actually handles a Postgres service (undocumented
behavior for data, only confirmed for variables/service config), could copy
production data into a new database. That is an outward-facing, costed,
potentially data-copying action against a system that already serves real
users. Per the task's own instruction and this project's standing rule for
hard-to-reverse actions, this report **stops at the audit/checklist/tooling
stage** and does not run that command or any other Railway
create/deploy/variable-set command. Everything below is either read-only
(local repo, local dev Postgres already used to develop/validate BUILD-1..16,
`railway status`/`railway environment list`) or new deployment *tooling*
(a verification script) that performs no Railway action by itself.

---

## 1. Railway deployment requirements — audit

| Requirement | Status | Evidence |
| --- | --- | --- |
| Backend service | Exists (`VMEC-04/BE`), Dockerfile-built, already serving production | `railway status`, `docs/DEPLOY.md` |
| PostgreSQL | Exists (`VMEC-04/DB` / "Postgres"), already used by legacy chat's own pgvector retrieval | `railway status`; `backend/services/retrieval.py` already depends on pgvector in production today |
| pgvector extension | Present locally (`0.8.6`) and implicitly proven in production (legacy RAG already runs there); migrations `0001`/`0002`/`0014b` `CREATE EXTENSION` the extensions a fresh database needs | local verification below |
| Migrations to current head | Local repo head is `0033` (`alembic history` / `alembic heads`); `railway.json` already runs `alembic upgrade head` as `preDeployCommand` on every backend deploy | see below |
| Required environment variables | Enumerated in §3 | `.env.example`, `backend/config.py`, `docs/DEPLOY.md` |
| Health/readiness checks | `GET /health` exists (liveness only — process up, no DB/pgvector/model check) and is already wired as `healthcheckPath` in `railway.json` (`timeout 300s`, `ON_FAILURE` restart, `maxRetries 3`) | `backend/main.py:90-92`, `railway.json` |

**Gap found:** `/health` is liveness-only. It does not check DB connectivity,
pgvector, or corpus identity, so a healthy-looking deploy can still have a
broken/mismatched corpus. This is not new to BUILD-17 and is not changed
here (no architecture change) — §5 below adds a **separate, explicit**
corpus-identity check to run *before* flipping `AGENT_RUNTIME_ENABLED=true`
in staging, rather than folding a new dependency into the liveness probe.

Local migration chain (read-only, no DB required for `alembic heads`):

```
$ python -m alembic heads
0033 (head)
```

`railway.json` already has everything needed to keep migrations current on
every deploy:

```json
{
  "build": {"builder": "DOCKERFILE", "dockerfilePath": "Dockerfile"},
  "deploy": {
    "preDeployCommand": ["alembic upgrade head"],
    "healthcheckPath": "/health",
    "healthcheckTimeout": 300,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3
  }
}
```

No `railway.json`/`Dockerfile` change is required for staging — the same
image and predeploy command apply to any environment the service is linked
to; only the environment's own `DATABASE_URL` and other variables differ.

### Volume gotcha (carried over from `docs/DEPLOY.md`, applies identically to staging)

`Dockerfile` `COPY`s the Drug Knowledge V2 canonical data into
`/app/data/drug-knowledge-v2/` **at build time**. A Railway Volume must never
be mounted at `/app/data` (it would shadow that baked-in data and the app
would hang at startup, failing `/health` forever — this happened once in
production on 2026-08-17, documented in `docs/DEPLOY.md`). If a staging
service needs the photo-verification volume for its own smoke tests, mount
it at the narrow path `/app/data/photo_verifications` only, exactly as
production does.

---

## 2. Database/RAG migration plan — corpus BUILD-7D

### Where the corpus actually lives today

The 14,423-row, 1,536-dimension `text-embedding-3-small` corpus that BUILD-7D
paid to embed (`US$0.377997`, `18,899,846` tokens) lives **only in the local
development Postgres this repo has been using through BUILD-1..16**
(`postgresql://vmec:vmec@localhost:5432/vmec04`) — not in git (the vectors
are binary/large and were never intended to be committed) and not yet in any
Railway database. `data pharmacy/v2/rag_openai/legacy-drug-chunks-openai-v1/manifest.json`
is the durable, committed **identity record**, not the data itself.

**Re-embedding is not necessary and must not happen.** The correct migration
path is a database-level restore of the already-paid-for rows from the local
dev Postgres into the target Railway Postgres, using the identical schema
`alembic upgrade head` already creates (migrations `0029`/`0030`/`0031`
define `rag_corpus`, `drug_chunks`, `rag_embedding_reservation`).

### Exact restore commands (to run once a staging Postgres exists — not run in this session)

```bash
# 1. Get the staging DATABASE_URL without ever hard-coding it:
railway variables --service "VMEC-04/BE" --environment staging --kv | grep DATABASE_URL

# 2. From the local dev machine that holds the corpus (DATABASE_URL below is
#    the LOCAL source, never the staging target):
pg_dump "postgresql://vmec:vmec@localhost:5432/vmec04" \
  --data-only \
  --table=rag_corpus \
  --table=drug_chunks \
  --table=rag_embedding_reservation \
  --file=rag_corpus_build7d.sql

# 3. Ensure the target schema already exists (alembic's own preDeployCommand
#    does this automatically on the staging service's first deploy; if
#    restoring before the first deploy, run it explicitly against staging):
DATABASE_URL="<staging DATABASE_URL>" python -m alembic upgrade head

# 4. Restore the data-only dump into staging:
psql "<staging DATABASE_URL>" -f rag_corpus_build7d.sql

# 5. Fail-closed identity verification (new tool, added by this build; never
#    calls OpenAI, never re-embeds, read-only):
DATABASE_URL="<staging DATABASE_URL>" python scripts/agent_v2/verify_rag_corpus_identity.py
```

### Identity verification tool (new, additive, read-only)

`scripts/agent_v2/verify_rag_corpus_identity.py` was added by this build. It
compares the target database's `rag_corpus` row, `drug_chunks` row/key
counts, embedding dimensions, and the `hnsw`/`vector_cosine_ops` index
against the pinned BUILD-7D identity, and exits non-zero (fail-closed) on any
mismatch — it never trusts the target database to self-report correctness.
Unit-tested (`tests/test_rag_corpus_identity_verification.py`, 10 cases: an
exact match, and one case per possible mismatch — wrong hash, wrong model,
wrong dimensions, wrong index version, wrong row count, duplicate keys,
invalid vector dimensions, missing HNSW index, missing extension, and
multiple simultaneous mismatches). It was then **run for real** against the
local dev Postgres (the corpus's actual current home) to prove it correctly
recognizes the genuine BUILD-7D corpus:

```
$ python scripts/agent_v2/verify_rag_corpus_identity.py
{"status": "PASS", "corpus_version": "legacy-drug-chunks-openai-v1", "drug_chunks_rows": 14423, "mismatches": []}
```

This also served as a live, read-only re-verification of the corpus identity
claimed by BUILD-7D, independent of that report's own narrative:

| Check | Expected (BUILD-7D manifest) | Actual (queried live) | Result |
| --- | --- | --- | --- |
| `corpus_version` | `legacy-drug-chunks-openai-v1` | `legacy-drug-chunks-openai-v1` | PASS |
| `status` | `COMPLETE` | `COMPLETE` | PASS |
| `source_manifest_hash` | `39ABC318DCEF1AD5D4817005DC4621DA328DE3DB26CDE56FED5A412092A2C2C0` | same | PASS |
| `chunk_manifest_hash` | `E57B24693AE64F7B1514D820911C5804DCD71CB3AAF4CF45B17A2D87603E0C04` | same | PASS |
| `embedding_model` | `text-embedding-3-small` | same | PASS |
| `embedding_dimensions` | `1536` | `1536` | PASS |
| `index_version` | `pgvector-hnsw-cosine-v1` | same (`ix_drug_chunks_embedding_hnsw`, `USING hnsw (embedding vector_cosine_ops)`) | PASS |
| `drug_chunks` row count | `14423` | `14423` | PASS |
| distinct `chunk_key` | `14423` | `14423` (0 duplicates) | PASS |
| invalid embedding dimensions | `0` | `0` | PASS |
| field-group breakdown | `bao_quan 3508 / cach_dung 3560 / cong_dung 3556 / tac_dung_phu 3799` | identical | PASS |
| `rag_embedding_reservation` status | 1 `HISTORICAL_RECONCILED`, 0 outstanding | same | PASS |
| pgvector extension | installed | `0.8.6` | PASS |
| local `alembic_version` | `0033` | `0033` | PASS |

**No architecture, corpus, or evaluation change was made to produce this
PASS** — this table reports what was already true in the source database;
the new script only adds a repeatable, fail-closed way to re-check it after
a restore into staging.

---

## 3. Secrets/config audit

### Required per model role (Agent V2, `backend/agents/v2/model_gateway.py`)

| Variable | Role | Required for staging Agent V2 traffic? |
| --- | --- | --- |
| `OPENAI_ROUTER_API_KEY` (fallback: `OPENAI_API_KEY`) | Router (`gpt-5.4-nano`) | Yes |
| `OPENAI_MAIN_API_KEY` (fallback: `OPENAI_API_KEY`) | Main Agent (`gpt-5.4-mini`) | Yes |
| `OPENAI_FALLBACK_API_KEY` (fallback: `OPENAI_API_KEY`) | Fallback (`gpt-5.4`) | Yes (configured; usage is meant to stay rare/monitored) |
| `OPENAI_EMBEDDING_API_KEY` (fallback: `OPENAI_API_KEY`) | Embedding (`text-embedding-3-small`) | Yes — RAG query embedding |
| `OPENAI_JUDGE_API_KEY` (fallback: `OPENAI_API_KEY`) | DeepEval judge (`gpt-4o`) | **No** — judge calls are offline/pre-release evaluation only (BUILD-15/15C), not part of any runtime request path; not needed to serve staging traffic, only to re-run `scripts/agent_v2/run_deepeval_rag_judge.py` |
| `OPENAI_API_KEY` | Local-dev fallback for any of the above | Recommended to still set, per the approved plan's fallback design (§45.2 of the architecture plan) |

Each workload may point at the **same or different** OpenAI project; the
gateway is provider/credential-agnostic and never hard-codes a key
(`backend/agents/v2/model_gateway.py::build_model_workloads`). Recommended
for staging: reuse the workload-split pattern already designed, and prefer
**separate staging credentials from production's**, so a staging traffic
spike or bug cannot consume production's budget/rate limit and vice versa.

### Vinmec Web / RAG / pricing

- No API key is required for Vinmec Web — `backend/services/vinmec_web_search.py`
  only calls the public `vinmec.com` search/article pages over HTTPS with an
  explicit host allowlist (already egress-allowlisted, see below).
- `AGENT_MODEL_PRICING_JSON` defaults to `{}`. Verified behavior
  (`backend/agents/v2/observability.py::ModelPricingCatalog.estimate`): an
  **unknown model returns `estimated_cost_usd=None`** and is counted
  separately (`unknown_cost_calls`), never fabricated as `$0`. Staging should
  populate this from an approved current price catalog before relying on
  cost dashboards, but its absence does not break the runtime or silently
  under-report cost as free.
- `backend/egress_allowlist.py` already lists `backend/services/vinmec_web_search.py`
  and `backend/services/embeddings.py`/`backend/services/llm.py` as the only
  modules permitted to open an outbound HTTP connection (enforced by
  `tests/test_egress_allowlist.py`, part of this build's regression run). No
  change was needed for Agent V2 — BUILD-8 already added its entry.

### Secrets that must never be shared between staging and production

Per the fail-closed validators in `backend/config.py`
(`_internal_auth_secret_must_be_configured`, `_jwt_secret_must_be_configured`),
the app refuses to start if `INTERNAL_AUTH_SECRET` or `JWT_SECRET` is left at
the sentinel value committed in source. For staging:

- `INTERNAL_AUTH_SECRET`, `JWT_SECRET` — generate **new, staging-only**
  values (never copy production's; a shared secret would let a staging JWT
  authenticate against production or vice versa).
- `DATABASE_URL` — must point at the **new staging Postgres**, never at
  `VMEC-04/DB` (production's database reference var). If staging is created
  via `railway environment new staging --duplicate production`, this must be
  verified explicitly (see §1's risk note) rather than assumed.
- `OPENAI_*_API_KEY` — prefer staging-only keys/project so spend and rate
  limits are isolated from production (§45.2 of the architecture plan
  explicitly designs for this).
- `CORS_ORIGINS` — a staging frontend origin (if one is deployed) or left to
  exact-match only whatever staging callers actually use; never widened to
  `*`.

### Additional non-Agent-V2 flags that affect what Agent V2's tools can read

`AgentReadOnlyDomainTools` (`backend/services/agent_read_only_tools.py`)
calls `backend.services.scheduling.runtime_adapter` directly for
`get_today_doses`/`get_upcoming_doses`/`get_dose_status`, independent of
`dose_runtime_mode`. However, V2 dose/prescription rows are only *populated*
when `DOSE_RUNTIME_MODE` is `shadow` or `v2` and `PRESCRIPTION_V2_MODE` is
`shadow` at the time a prescription/dose was created
(`backend/services/prescription/service.py`). **Staging should mirror
whatever these three flags (`DRUG_KNOWLEDGE_BACKEND`, `DOSE_RUNTIME_MODE`,
`PRESCRIPTION_V2_MODE`, `SAFETY_RUNTIME_MODE`) are currently set to in
production** — confirm the actual production values via `railway variables`
before configuring staging identically, otherwise the "patient dose query"
and "Safety SAFE/HANDOFF" E2E scenarios in §6 will return empty data even
though nothing is actually broken. This report does not assume or fabricate
production's current values.

---

## 4. Runtime flags — staging strategy and rollback

Legacy chat (`backend/api/chat_routes.py`) is **not modified** and is **not
routed to Agent V2** anywhere in this build or any prior one. The strategy:

```
Production   AGENT_RUNTIME_ENABLED=false   (unchanged, forever, until a
                                             separately approved rollout
                                             decision per plan §29-30)
Staging      AGENT_RUNTIME_ENABLED=true    (explicit, staging-only, set
                                             manually after §1-§5 all pass)
```

- `AGENT_RUNTIME_ENABLED` is read once per process via `get_settings()`
  (`@lru_cache`), so it only takes effect after a restart/redeploy — exactly
  like every other Railway var per `docs/DEPLOY.md`'s own note about
  `CORS_ORIGINS`. There is no code path that can flip it at runtime.
- Both Agent V2 routes (`/agent/v2/read-only`, `/agent/v2/orchestrate`)
  already return `404` immediately when the flag is `false` — verified by
  `test_agent_v2_route.py`/`test_agent_v2_orchestrator.py` and unaffected by
  anything in this build.
- `AGENT_VINMEC_WEB_ENABLED=true` should also be set **staging-only**, to
  exercise the Vinmec Web E2E scenario in §6; it stays `false` in production.

### Rollback / disable procedure

Disabling Agent V2 in staging (or aborting a bad staging deploy) needs no
code change and no data rollback, because BUILD-1..16 added no destructive
migration and no write path:

```bash
railway variables --service "VMEC-04/BE" --environment staging \
  --set "AGENT_RUNTIME_ENABLED=false"
# Railway auto-redeploys on variable change (per docs/DEPLOY.md); confirm
# with: railway logs --service "VMEC-04/BE" --environment staging
```

If the staging **environment itself** needs to be torn down entirely:

```bash
railway environment delete staging --yes
```

This is safe to the rest of the project specifically *because* staging would
be a separate environment/database from production — deleting it cannot
touch `VMEC-04/DB` (production) as long as staging was provisioned with its
own database and never pointed `DATABASE_URL` at production's.

---

## 5. Infrastructure validation — checklist (run once staging exists)

| Check | Command | Pass criterion |
| --- | --- | --- |
| DB connectivity | `railway run --service "VMEC-04/BE" --environment staging -- python -c "from backend.db.base import engine; engine.connect().close(); print('OK')"` | prints `OK` |
| Migrations | `railway run ... -- python -m alembic current` | prints `0033 (head)` |
| pgvector query | `railway run ... -- python -c "from backend.db.base import SessionLocal; import sqlalchemy as sa; s=SessionLocal(); print(s.execute(sa.text(\"select extversion from pg_extension where extname='vector'\")).scalar())"` | prints a version string, not empty |
| Retrieval smoke | `railway run ... -- python scripts/agent_v2/verify_rag_corpus_identity.py` (new, this build) | exit code `0`, `"status": "PASS"` |
| Vinmec Web smoke | `curl` scenario in §6 (`VINMEC_WEB_INFORMATION` intent) once `AGENT_VINMEC_WEB_ENABLED=true` | `status=COMPLETED`, non-empty `citations[].source=="vinmec-web"` |
| Tool Gateway smoke | `railway run ... -- python scripts/agent_v2/smoke_model_gateway.py` (existing, BUILD-2) | all 5 roles `passed: true` |
| Safety Gateway smoke | §6 scenario 5/6 below | `SAFE` and `SAFETY_BLOCKED`/`HANDOFF_CREATED` dispositions observed as expected |
| Doctor Handoff persistence | after §6 scenario 7, `SELECT * FROM doctor_review_request ORDER BY created_at DESC LIMIT 1;` on the staging DB | one row, `status IN ('PENDING','ASSIGNED')`, no PHI beyond what the test itself sent |
| Checkpoint persistence | `SELECT terminal_status, completed_tools, resolved_entities FROM agent_run_checkpoint ORDER BY updated_at DESC LIMIT 5;` | `terminal_status` populated per run; `completed_tools`/`resolved_entities` contain only ids/provenance, never prompt/message text (BUILD-12 invariant, unchanged) |
| Observability/redaction | `railway logs --service "VMEC-04/BE" --environment staging \| grep agent_run` | structured JSON events only; no prompt, no raw tool payload, no secret (BUILD-13 invariant, unchanged; `AgentTelemetry._sanitize_attributes` allowlists fields) |
| Model connectivity smoke | `scripts/agent_v2/smoke_model_gateway.py` (same as Tool Gateway smoke) | all roles pass; **this is the only check in this list that spends real OpenAI credit** — already proven passing in BUILD-2 with local credentials; re-run once against staging's own keys, not repeatedly |

None of these were run against a staging service in this session because
none exists yet. The DB connectivity, migrations, and pgvector queries were
already effectively proven against the local dev Postgres (§2's table above,
plus `alembic heads`/`alembic_version` matching `0033`) — that environment
has run every BUILD-1..16 test and is the actual current home of the corpus,
so it is a faithful stand-in for "a correctly migrated Postgres" pending the
same steps being repeated against the real staging database.

---

## 6. Staging E2E — script prepared, not run

These reuse exactly the intents/scenarios `tests/test_agent_v2_orchestrator.py`
(BUILD-16) already covers end-to-end at the Python level; against a live
staging deploy they become HTTP smoke tests. **Not run — no staging host
exists.** Commands are provided so they can be run verbatim once one does; no
output below is fabricated.

```bash
BASE=https://<staging-be-host>
TOKEN=$(...)   # staging-only JWT, staging-only patient/doctor/caregiver test accounts

# 1. Normal drug-information query
curl -s -X POST "$BASE/api/v1/agent/v2/orchestrate" -H "Authorization: Bearer $TOKEN" \
  -d '{"patient_id":"<staging-patient>","message":"Cho toi biet thong tin ve thuoc paracetamol"}'
# expect: status=COMPLETED, tools contains "search_drug" or "get_drug_info"

# 2. RAG query
curl -s ... -d '{"patient_id":"<staging-patient>","message":"Tac dung phu cua thuoc giam dau la gi"}'
# expect: status=COMPLETED, citations non-empty, source != "vinmec-web"

# 3. Patient dose query
curl -s ... -d '{"patient_id":"<staging-patient>","message":"Hom nay toi can uong thuoc gi"}'
# expect: status=COMPLETED, tools contains "get_today_doses"
# (requires DOSE_RUNTIME_MODE parity noted in §3, or an empty-but-COMPLETED result)

# 4. Vinmec Web
curl -s ... -d '{"patient_id":"<staging-patient>","message":"Tim tren Vinmec thong tin ve benh tieu duong"}'
# expect: status=COMPLETED, citations[].source=="vinmec-web" with a vinmec.com url

# 5. Safety SAFE
curl -s ... -d '{"patient_id":"<staging-patient>","message":"Toi quen uong thuoc sang nay","dose_id":"<a real, low-risk staging dose id>"}'
# expect: status=COMPLETED, safety_disposition=="SAFE"

# 6. SAFETY_BLOCKED
# Exercise by temporarily pointing SafetyDomain at an unreachable state, or by
# using a staging dose_id engineered to make assess_dose_safety raise/timeout;
# do not attempt this against any real prescription.
# expect: status=SAFETY_BLOCKED, no model-generated reply content beyond the
# fixed fallback string

# 7. HANDOFF_CREATED
curl -s ... -d '{"patient_id":"<staging-patient>","message":"Toi muon doi lieu thuoc sang 2 vien"}'
# expect: status=HANDOFF_CREATED, handoff_id non-null; verify exactly one new
# doctor_review_request row (Doctor Handoff persistence check in §5)

# 8. Cross-patient denial
curl -s -o /dev/null -w "%{http_code}\n" ... -d '{"patient_id":"<a DIFFERENT staging patient not linked to this actor>","message":"xin chao"}'
# expect: 403 (require_agent_patient_access, unchanged since BUILD-1)

# 9. Timeout/failure path
# Temporarily set AGENT_RUN_TIMEOUT_SECONDS or AGENT_MAX_MODEL_CALLS very low
# on staging only, rerun scenario 1, then restore the value.
# expect: status=BUDGET_EXCEEDED or TIMEOUT, never a fabricated answer
```

Every one of these 9 scenarios already has an equivalent, currently-passing
automated test in `tests/test_agent_v2_orchestrator.py` (BUILD-16) run
against real `ToolGateway`/`SafetyGateway`/`DoctorHandoffGateway`/
`RetrievalGateway`/`VinmecWebSearchGateway` instances — what staging adds is
confirmation that the same code path also works through the real HTTP
route, real Postgres, and real OpenAI/Vinmec network calls end to end.

---

## 7. No architecture/corpus/evaluation change

This build added exactly two new files, both deployment tooling, neither
touching Agent V2's architecture, the corpus, or evaluation:

- `scripts/agent_v2/verify_rag_corpus_identity.py` — read-only identity
  check (§2).
- `tests/test_rag_corpus_identity_verification.py` — its unit tests.

No migration, no corpus row, no evaluation dataset/metric/threshold, and no
`backend/agents/v2/*` orchestration file was changed.

## Regression

```
python -m pytest tests/ -k "agent_v2 or rag_corpus_identity" -q
151 passed, 2 skipped
```

The 2 skips are the same pre-existing, explicit PostgreSQL-only tests noted
since BUILD-10/12/15C (`BUILD12_TEST_DATABASE_URL`, `BUILD10_TEST_DATABASE_URL`).

## Result

BUILD-17: PASS (audit + checklist + verification tooling deliverable, as required when the target environment does not yet exist)

RAILWAY CONFIG: PASS (`railway.json`/`Dockerfile` already correct and reusable for staging; no change needed)

POSTGRESQL: PASS (production already runs Postgres+pgvector; local source-of-truth verified live; staging Postgres itself not yet provisioned)

PGVECTOR: PASS (extension present and proven functional on the corpus's actual current database; migrations create it automatically on a fresh database)

MIGRATIONS: PASS (local head `0033`; `railway.json` already runs `alembic upgrade head` as `preDeployCommand` on every deploy)

CORPUS RESTORE/IDENTITY: PASS (identity re-verified live against its real current database with a new fail-closed tool; restore-into-staging commands documented, not yet executed — no staging DB exists to restore into)

SECRETS/CONFIG: PASS (required keys enumerated by model role; judge key confirmed not required for runtime traffic; unknown-price behavior confirmed `None`, never fabricated `$0`; staging/production separation requirements documented)

MODEL CONNECTIVITY: NOT RUN AGAINST STAGING (staging has no credentials yet; BUILD-2's smoke test already proves the mechanism works and is documented as the exact command to re-run once staging keys exist)

RAG SMOKE: PASS (against the corpus's real current database; not yet re-run against a staging database, which does not exist)

SAFETY/HANDOFF: PASS (mechanism proven end-to-end at the code level in BUILD-16's real-component test suite; not yet re-proven over live HTTP against staging)

OBSERVABILITY: PASS (redaction/allowlisting mechanism unchanged from BUILD-13, unit-tested; staging log inspection command documented, not yet run)

STAGING E2E: NOT RUN — staging environment does not exist. Script for all 9 required scenarios is written and ready in §6; no result is fabricated.

ROLLBACK PLAN: PASS (variable-flip + optional environment-delete procedure documented; no destructive migration exists to roll back)

READY TO DEPLOY RAILWAY STAGING: NO — blocked on a human decision to create
the `staging` Railway environment (an outward-facing, costed, and
data-sensitive action this report deliberately does not take
unilaterally) and to confirm staging should reuse or diverge from
production's `DOSE_RUNTIME_MODE`/`PRESCRIPTION_V2_MODE`/`SAFETY_RUNTIME_MODE`
values. Once a human runs `railway environment new staging` (or
`--duplicate production` after confirming what that does to the Postgres
service) and provisions a staging Postgres + staging-only secrets, every
command in §1-§6 above is ready to execute as-is.
