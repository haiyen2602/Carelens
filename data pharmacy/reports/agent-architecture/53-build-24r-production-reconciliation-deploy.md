# BUILD-24R — Production Reconciliation Deploy

**Scope:** deploy the unified codebase (Agent V2 RC1 + `origin/main`'s 73
commits, merged and verified locally in BUILD-24Q) to Railway production,
after confirming a safe, non-destructive migration reconciliation path.

---

## 1. Preflight

```
Production V2 (config): AGENT_ROLLOUT_PERCENTAGE=100, AGENT_RUNTIME_ENABLED=true -- unchanged throughout
/health: 200
alembic_version (pre-deploy): 0031 -- reached via an auto-heal stamp, not a real migration run (see §2)
Fresh backup: taken (H:\Vin AI\P-067-backups\pre-stamp-0034\, new timestamped dump, pg_dump via version-matched pgvector:pg18 Docker image)
Concurrent deploy: none -- confirmed via `railway deployment list`, same latest deployment (`e22eb247`, 16:14:36Z) as the prior check, and the user explicitly confirmed no one else deploying
```

## 2. Migration reconciliation plan (proven safe before acting)

Ground truth from a full read-only schema snapshot
(`scripts/agent_v2/production_full_schema_snapshot.sql`):

```
alembic_version: 0031
ba_user / ba_session / ba_account / ba_verification: ALL STILL PRESENT
  (contradicts what "at revision 0031" should mean -- proves the "0031" value
  came from an auto-heal stamp, never from migration 0031's upgrade() actually
  running; see BUILD-24Q's own finding about the auto-heal transaction bug)
nudge table + account.supabase_uid column/index: present
All 6 Agent V2 tables (rag_corpus, rag_corpus_checkpoint, rag_embedding_reservation,
  doctor_review_request, agent_run_checkpoint, agent_idempotency_key): present,
  with real, growing row counts (396/45/113, up from 289/26/112 in BUILD-24O --
  confirms Agent V2 genuinely served real traffic during its brief 100% window)
```

**Dependency audit on the 4 `ba_*` tables** (per the user's explicit
requirement, before deciding whether to run their DROP):

```
Foreign keys: only INTERNAL to the ba_* cluster itself (ba_session.userId -> ba_user.id,
  ba_account.userId -> ba_user.id) -- zero FKs from any other table in either direction
Views referencing ba_*: 0
Triggers on ba_*: 0
Functions/procedures referencing ba_*: 0
Application code (models/routes/services) referencing ba_*: 0 -- grepped the full
  reconciled working tree, only matches are the 2 migration files themselves (0025
  created them, 0031 drops them) and the ADR-0013 doc
Row counts: ba_user=15, ba_account=15 (dormant historical data), ba_session=0, ba_verification=0
```

**Decision: LEGACY TABLES INTENTIONALLY RETAINED.** Zero dependencies found;
migrations 0032-0036 don't reference or require their absence (confirmed via
direct content review); `alembic stamp` never invokes any migration's
`upgrade()`/`downgrade()`, so the DROP inside 0031 cannot fire via stamping,
now or on any future deploy once `alembic_version >= 0031`. Documented as a
formal follow-up: [tasks/TASK-BA-CLEANUP-legacy-better-auth-tables.md](../../../tasks/TASK-BA-CLEANUP-legacy-better-auth-tables.md).

**Action taken:** `alembic stamp 0036` only. Zero DDL executed. Zero
`alembic upgrade head` run against production at this step.

**Verified after stamping**, before deploying:

```
alembic_version: 0036 (confirmed)
Full schema snapshot re-run: byte-for-byte identical to pre-stamp, except
  the single alembic_version value -- every row count, every table, every
  ba_* table (still present) unchanged
/health: 200
```

## 3. Deploy

```
railway up --service "VMEC-04/BE" --environment production -c
```

Deployment `44afaf21-3d73-49b9-8212-e0c28f3f22d3`, SUCCESS, this session's
own `cliAgentSessionId` (no concurrent-deploy interference this time).
Deploy logs:

```
[PRE-DEPLOY] Current DB revision '0036' is valid.
[PRE-DEPLOY] Running alembic upgrade head...
[PRE-DEPLOY] Migrations complete successfully.
```

Confirms the reconciliation held exactly as planned: the merged codebase's
own `safe_migrate.py` recognized `0036` as a valid, current-head revision
and ran zero migration steps -- no re-run of existing DDL, no drift.
Container started cleanly (RAG warmup products=3556, scheduler started),
and real production traffic was already flowing within seconds
(`GET /api/v1/doses?patient_id=BN00002` -> 200, `GET /api/v1/nudges/unseen`
-> 401 unauthenticated, both expected real-user request shapes).

## 4. Verification

```
/health:                                200
alembic_version:                        0036
AGENT_ROLLOUT_PERCENTAGE:                100 (unchanged)
AGENT_RUNTIME_ENABLED:                   true (unchanged)
AGENT_CANARY_ALLOWLIST:                  unchanged, all 5 accounts
Total routes:                            62 (60 from main + 2 Agent V2 -- exact expected sum)
17 previously-missing routes:            ALL RESTORED (reset-password-sync, verify-email-sync,
                                          drugs/catalog, drugs/filters, drugs/{id}, health-log,
                                          nudges x2, admin/rag/* x9)
Agent V2 routes:                         /api/v1/agent/v2/orchestrate, /api/v1/agent/v2/read-only present
Langfuse/RAG monitoring:                 GET /api/v1/admin/rag/health -> 200 (loads correctly)
```

## 5. Regression smoke (7/7 PASS, real HTTP calls, fresh JWT, production)

| Check | Result |
|---|---|
| Drug info (query 1) | `200 COMPLETED DRUG_INFORMATION` |
| Grounding / honest decline (query 5) | `200 COMPLETED DRUG_INFORMATION` |
| Today's schedule (query 24) | `200 COMPLETED TODAY_DOSES` |
| Acute danger (query 57) | `200 HANDOFF_CREATED ACUTE_DANGER_ESCALATION` |
| Doctor Handoff (query 70) | `200 HANDOFF_CREATED DOCTOR_REVIEW` |
| Cross-patient auth denial (query 96) | `403` |
| Idempotency (fresh key, sent twice) | identical `agent_run_id` + identical reply on both calls |

No code changes made during production verification, per instruction.
Legacy data untouched throughout. Rollout never left 100%.

---

## Closeout

```
BUILD-24R: PASS
DEPLOY: PASS
ALEMBIC HEAD: 0036
17 ROUTES RESTORED: PASS
LANGFUSE/RAG MONITORING ROUTES: PASS
V2 100%: PASS
SAFETY: PASS
AUTH: PASS
HANDOFF: PASS
GROUNDING: PASS
LEGACY FALLBACK: READY (AGENT_ROLLOUT_PERCENTAGE=0 / AGENT_RUNTIME_ENABLED=false still the whole rollback action; legacy code/data untouched; ba_* legacy tables retained intentionally, tracked in TASK-BA-CLEANUP)
READY FOR BUILD-25: YES
```
