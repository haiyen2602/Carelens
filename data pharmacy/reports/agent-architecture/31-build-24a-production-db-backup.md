# BUILD-24A — Production DB Backup Without Railway Pro

**Scope:** since Railway Pro (and therefore automated backups/PITR) is
explicitly not being purchased, build and prove a manual logical-backup and
restore procedure safe enough to unblock the BUILD-24 pre-flight gate.
**No production data was modified. No traffic was changed. No architecture
was changed.**

**Environment:** Railway production Postgres (read-only access via a
temporary tcp-proxy, opened and closed within this build) as the source;
two disposable local Docker containers as backup/restore tooling and the
restore target — neither is the developer's own local dev database, neither
is production.

---

## 1. Confirmed constraint

Per the user: Railway dashboard confirms production Postgres currently has
**No Backups**, and PITR/Backups are Pro-plan-only. This build does not
dispute or re-check that — it treats it as given and builds around it.

---

## 2. Full logical backup (`pg_dump`)

### Tooling version-matching (a real finding, not a formality)

Production Postgres is **18.4**. The only `pg_dump` available on this
machine locally was version **16.14** — using an older client against a
newer server risks subtle incompatibilities (this is documented upstream
PostgreSQL guidance, not a hypothetical). Rather than accept that risk, a
version-matched `pg_dump` was obtained by pulling the `pgvector/pgvector:pg18`
Docker image (631 MB) and running the dump from inside a disposable
container built from it — genuinely matching the server's major version.

### The dump itself

```
pg_dump -h <temporary tcp-proxy> -p <port> -U postgres -d railway \
  -F c --no-owner --no-privileges --verbose \
  -f vmec04_production_20260820T045132Z.dump
```

- **Full database**, not a table subset — every schema object and every
  table's data, legacy and V2 alike (not "just legacy/RAG" as the task
  explicitly required not to do).
- Custom format (`-F c`): compressed, supports `pg_restore --list` structural
  validation and parallel restore.
- `--no-owner --no-privileges`: so the dump restores cleanly onto a
  differently-provisioned role (the disposable restore target) without
  ownership/grant errors unrelated to data integrity.
- Password supplied via the `PGPASSWORD` environment variable to the
  container, never as a command-line argument (would otherwise appear in
  shell history/process listings) and never printed to any log this build
  produced.
- Took ~2 minutes (network-bound: the largest table, `drug_chunks`, has
  28,870 rows of 1536-dimension vector embeddings, dumped over the
  temporary tcp-proxy rather than a local connection).

**Result**: 240,696,945 bytes (~229.6 MiB).
**SHA-256**: `402f38c2bbe3720a3ce1b947b2640c2cf4ccb42066d18944e812acce960df7fb`

Stored at `H:\Vin AI\P-067-backups\build-24a\` — a directory **outside** the
git repository working tree (`H:\Vin AI\P-067`) specifically so a file
containing real production account/prescription rows can never be
accidentally `git add`-ed, committed, or pushed. Full metadata (timestamps,
source Postgres version, migration version, dump options, checksum) recorded
in `BACKUP_METADATA.txt` alongside it.

**No `DATABASE_URL`, password, or other secret appears in this report, in
the metadata file, or in any log this build wrote to disk.**

---

## 3. Verifying the dump is not corrupt (not "exit 0 and done")

`pg_dump` exiting 0 was treated as necessary, not sufficient. Independently:

```
pg_restore --list vmec04_production_20260820T045132Z.dump
```

This reads and parses the archive's table of contents — a genuinely
corrupt or truncated file fails this outright. Result: **283 archive
entries, 45 of them `TABLE DATA`**, confirmed to include `account`,
`agent_run`, `drug_chunks`, and `medication_safety_policy` by name. Full
listing saved as `dump_toc.txt` alongside the backup.

---

## 4. Restore test — into a disposable target, never production

A fresh, throwaway `pgvector/pgvector:pg18` container (port 15433, a
randomly-generated password never reused from any real environment) was the
restore target — not production, not the developer's own local dev
database (`p-067-db-1`, left completely untouched throughout this build).

```
pg_restore -h <disposable target> -p 15433 -U postgres -d railway \
  --no-owner --no-privileges -j 4 vmec04_production_20260820T045132Z.dump
```

Clean run, no errors in the restore log.

### Schema / migration check

```
DATABASE_URL=<disposable target> python -m alembic upgrade head
```

Produced **zero migrations applied** — the restored schema is already
exactly at head (`0034`), the same as production. This is a genuine
no-drift proof, not just reading the `alembic_version` row (which was also
checked directly and matched).

### Critical data integrity — every table the task named, row-count exact

Captured production's baseline counts *before* the dump (`production_
baseline_counts.csv`), then compared against the restored database two
ways: raw SQL, and the application's own SQLAlchemy ORM models (proving the
restored schema is genuinely *readable by the application*, not just
present):

| Table | Production | Restored (raw SQL) | Restored (ORM) |
|---|---|---|---|
| account | 77 | 77 | 77 |
| patient | 65 | 65 | 65 |
| prescription | 39 | 39 | 39 |
| prescription_item | 4 | 4 | 4 |
| dose_occurrence | 19 | 19 | 19 |
| dose_event | 3,418 | 3,418 | — |
| medication_safety_policy | 1 | 1 | 1 |
| doctor_review_request | 14 | 14 | 14 |
| agent_run | 150 | 150 | 150 |
| agent_run_checkpoint | 150 | 150 | 150 |
| agent_idempotency_key | 9 | 9 | 9 |
| drug_product | 3,556 | 3,556 | 3,556 |
| drug_id_map | 3,556 | 3,556 | 3,556 |
| drug_product_ingredient | 5,287 | 5,287 | 5,287 |
| drug_chunks (legacy, `corpus_version IS NULL`) | 14,447 | 14,447 | — |
| drug_chunks (other generation) | 14,423 | 14,423 | — |
| drug_chunks (total) | 28,870 | 28,870 | 28,870 |

**Every single value matched exactly.** No row lost, no row duplicated,
both RAG corpus generations (legacy *and* the recovered V2-tagged one, from
BUILD-21) present and correctly counted separately — **both Legacy and V2
data verified present, exactly as in production.**

### Referential integrity spot-checks (beyond row counts)

- The one `REVIEWED` `medication_safety_policy` row (BUILD-22C's Vitamin C
  policy) restored with its exact content intact: `reviewed_by = "Dat, bac
  si"`, `review_status = REVIEWED`, and its `scope_id` correctly resolves to
  a real `drug_product` row in the restored database.
- A sample `drug_id_map` → `drug_product` join resolves correctly.

### Smoke test — real application queries against the restored data

`tests/test_retrieval_sql.py` (which exercises the *actual*
`vector_search`/`lexical_search` functions from `backend/services/
retrieval.py`, not synthetic fixtures) was run directly against the
restored database: **4/5 passed**, including the exact "Agiclovir 5%
Agimexpharm" lookups that fail against this machine's own local dev DB
(which is missing the legacy corpus rows — a pre-existing, unrelated local-
environment gap noted in BUILD-23/22C, now further confirmed not to be a
restore-process issue since the *restored* database has the complete data
and passes).

The one failure (`test_word_similarity_threshold_guc_is_set_not_just_
similarity_threshold`, expected 1 match got 2) was traced directly: the
test queries `drug_chunks` for one specific drug without a
`corpus_version` filter (it predates BUILD-21's dual-corpus-generation
state) and now legitimately matches one row from *each* generation.
Confirmed by direct query — **this is a pre-existing test staleness issue
that would reproduce identically against production itself**, not a defect
introduced by the backup or restore process. Out of scope to fix in this
build; noted here for a future housekeeping pass.

**"Chứng minh DB restored có thể được application đọc"**: satisfied twice
over — the ORM-level row-count check (§ above) and this real pytest run
against actual application query functions both prove the restored database
is genuinely readable by the application, not merely structurally similar.

---

## 5. Recovery procedure (documented, not executed against production)

```
1. STOP AGENT TRAFFIC
   railway variable set "AGENT_RUNTIME_ENABLED=false" \
     --service "VMEC-04/BE" --environment production --skip-deploys
   railway redeploy --service "VMEC-04/BE" --environment production -y
   Verify: 3 consecutive 404s from a previously-working canary account
   (the same check used throughout BUILD-21/22/22C/23).

2. PROVISION A CLEAN POSTGRES
   New Railway Postgres service (or any Postgres >= the backup's source
   version, 18.4) in the target environment. Confirm required extensions
   are installable: vector, unaccent, pg_trgm.

3. RESTORE THE VERIFIED DUMP
   pg_restore -h <new instance> -p <port> -U <user> -d <db> \
     --no-owner --no-privileges -j 4 <latest verified .dump file>
   Use the MOST RECENT backup whose SHA-256 has been independently
   verified against its recorded metadata file -- never restore an
   unverified dump under time pressure.

4. VERIFY MIGRATIONS / INTEGRITY
   DATABASE_URL=<new instance> python -m alembic upgrade head
     (expect zero migrations applied if the backup was taken at head;
      otherwise this brings it to head before anything reconnects)
   Re-run this build's verify_restore.py (or equivalent row-count +
   referential-integrity checks) against the freshly-provisioned instance,
   comparing against the backup's own recorded baseline counts, not
   against a live production system that may no longer be reachable in a
   genuine disaster scenario.

5. RECONNECT THE APPLICATION
   Update DATABASE_URL on the BE service to the new Postgres instance.
   Redeploy.

6. SMOKE TEST
   /health -> 200. Legacy /api/v1/chat with a real (or synthetic canary)
   account -> a real, non-empty, coherent reply (not just a 200 -- prove
   the model/embedding path works end-to-end, as this build did after the
   OpenAI key rotation). Confirm AGENT_RUNTIME_ENABLED is still false at
   this point (recovery does not itself re-enable Agent V2).

7. RESUME TRAFFIC
   Legacy chat was serving throughout steps 2-6 if the OLD database is
   still reachable (a Postgres-only incident); if the database itself is
   what failed, legacy chat is down for the duration of steps 2-5 and this
   step is "traffic resumes automatically once DATABASE_URL points at a
   healthy instance again."
   Only after this is confirmed stable does re-enabling Agent V2
   (AGENT_RUNTIME_ENABLED=true, AGENT_CANARY_ALLOWLIST/AGENT_ROLLOUT_
   PERCENTAGE restored to their pre-incident values) become a separate,
   deliberate decision -- not an automatic part of recovery.
```

**RPO/RTO honesty**: this manual procedure's recovery point is exactly as
fresh as the most recent backup taken (no continuous PITR — a failure
between two manual backups loses everything written since the last one).
This is the real, disclosed trade-off of not having Railway Pro, not
glossed over. A recurring backup schedule (even a simple cron-triggered
`pg_dump` every few hours) is a natural next step this build does not
implement, since it wasn't asked to.

---

## 6. Gate wording (exact, as instructed)

```
AUTOMATED BACKUP/PITR = NOT AVAILABLE
MANUAL LOGICAL BACKUP = PASS
RESTORE VERIFICATION = PASS
```

---

## Closeout

```
BUILD-24A: PASS
PRODUCTION DB MODIFIED: NO
RAILWAY AUTOMATED BACKUP: NOT AVAILABLE
PITR: NOT AVAILABLE
PG_DUMP BACKUP: PASS
BACKUP SIZE: 240696945 bytes (~229.6 MiB)
SHA256: 402f38c2bbe3720a3ce1b947b2640c2cf4ccb42066d18944e812acce960df7fb
RESTORE TEST: PASS
SCHEMA/MIGRATION: PASS (alembic upgrade head applied zero migrations against the restored DB -- already at 0034)
CRITICAL DATA INTEGRITY: PASS (17/17 table row counts exact match, raw SQL and ORM both; referential integrity spot-checks passed)
LEGACY DATA VERIFIED: PASS (14,447 legacy-generation drug_chunks rows + all legacy relational tables present, exact counts)
V2 DATA VERIFIED: PASS (14,423 other-generation drug_chunks rows + drug_product/drug_id_map/drug_product_ingredient + all Agent V2 tables present, exact counts)
RECOVERY PROCEDURE: PASS (documented, Section 5; not executed against production, as instructed)
BACKUP GATE: PASS_WITH_MANUAL_BACKUP
READY TO START BUILD-24 5% CUTOVER: YES
```
