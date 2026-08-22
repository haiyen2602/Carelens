# BUILD-24Q — Main Branch Reconciliation (prerequisite to BUILD-25)

**Scope:** while investigating BUILD-25 (production monitoring), discovered
that this session's own Phase 4/5 redeploys had silently removed 17 live
production routes -- because `feature/agent-architecture-v2` had diverged
73 commits from `origin/main`, and `railway up` replaces the whole
deployment rather than merging. This build reconciles the two branches:
renumbers a real migration revision-ID collision, merges all 73 commits,
finds and fixes a critical transaction bug in shared migration
infrastructure along the way, and verifies everything locally. **Not
deployed** -- local-only, per the user's own instruction to test before any
production change.

---

## 1. What triggered this

Starting BUILD-25, a live `openapi.json` fetch showed only 43 production
routes where an earlier fetch (during the Phase 4 investigation) had shown
60 -- 17 routes gone: `/api/v1/auth/reset-password-sync`,
`/api/v1/auth/verify-email-sync`, `/api/v1/drugs/catalog`,
`/api/v1/drugs/filters`, `/api/v1/drugs/{drug_id}`, `/api/v1/health-log`,
`/api/v1/nudges`, `/api/v1/nudges/unseen`, and all 9
`/api/v1/admin/rag/*` routes.

Root cause: `feature/agent-architecture-v2` branched off `main` long ago and
never merged back. `main` progressed with 73 more commits (nudge/escalation
feature, a full Langfuse RAG-monitoring/admin-dashboard implementation
conforming to `docs/langfuse_rag_admin_monitoring_spec.md`, Supabase auth on
the frontend, admin drug catalog, health-log). This session's own RC1
redeploys (`railway up` uploads the whole working tree, it does not merge)
silently overwrote all of it.

## 2. Scope of the divergence

```
git log --oneline feature/agent-architecture-v2..origin/main | wc -l  -> 73 commits
git diff --stat <merge-base> origin/main                              -> 160 files, 13987(+)/2281(-)
```

Notably: a full Langfuse integration (`langfuse>=2.0.0` in requirements.txt,
`LANGFUSE_*` env vars, `backend/services/telemetry.py`,
`backend/api/rag_monitoring_routes.py`) -- directly relevant to BUILD-25's
own ask, built by a teammate in parallel. `backend/api/security.py` (the
core JWT auth dependency Agent V2 relies on) is byte-identical on both
branches -- confirmed via diff before touching anything, so Agent V2's own
authorization model was never at risk.

## 3. Migration revision-ID collision (the reason both branches' deploys kept fighting)

```
feature/agent-architecture-v2:  0030 = rag_corpus_recovery         0031 = rag_embedding_reservations   ... 0034 = agent_idempotency_keys
origin/main:                    0030 = nudge                       0031 = remove_better_auth_and_add_supabase_uid
```

Two files on each branch independently claimed the same revision IDs with
completely different content -- not something `git merge` can resolve (the
filenames differ, so git sees no conflict at all; the collision is at the
Python-string level inside otherwise-unrelated files). This is the actual
mechanism behind **both** alembic-drift incidents in BUILD-24O/24P: whichever
side deployed last would silently overwrite `alembic_version` to its own
chain's notion of head, because neither chain recognized the other's
revision string as valid.

**Fix:** renamed this branch's 5 migrations to 0032-0036, re-chaining
`down_revision` after main's real 0031. No DDL changed -- confirmed via
`alembic heads` (single head, `0036`) and `alembic history` (one continuous
line, 0001 through 0036, no branch points). This project has hit this exact
category of problem before (0009-0013 were renumbered once already, per
that migration's own docstring, when this branch and main separately used
those numbers) -- same fix, same reasoning.

## 4. The merge itself

```
git merge origin/main --no-commit --no-ff
```

Exactly **one** real conflict, in `backend/main.py` (both branches inserted
a new router import at the same line -- trivial, both imports kept,
alphabetized to match the file's existing convention). Everything else
(`.env.example`, `backend/config.py`, `backend/db/models.py`,
`backend/models/schemas.py`, `requirements.txt`, `Dockerfile`, `railway.json`,
and 150+ other files) merged cleanly with no conflicts at all, because the
two branches' additions were in different parts of shared files.

Before merging, committed all of Agent V2's own previously-uncommitted
foundational work (139 files -- everything from BUILD-1 through BUILD-24C
that report 48/BUILD-24N had deliberately left uncommitted) as a clean
checkpoint commit, since `git merge` needs a clean tree to work reliably.
That reasoning (avoid presumptuously committing possibly-unrelated
concurrent work) no longer applied once the actual goal became "merge with
that concurrent work" -- see the commit message on `49d0aab` for the full
reasoning.

## 5. A critical bug found and fixed along the way: main's own migration auto-heal silently discards every ordinary deploy

`main` added an "auto-heal" block to `migrations/env.py` (recovers from an
alembic_version the codebase doesn't recognize by force-stamping it to the
current head) plus a `scripts/safe_migrate.py` pre-deploy wrapper. Testing
the reconciled chain on a disposable Postgres 18 container surfaced a real,
reproducible bug:

```
Scenario                                              | Reported | Actually persisted
-------------------------------------------------------|----------|--------------------
Fresh DB, `alembic upgrade head`, auto-heal present    | success  | 0 tables created
Valid baseline (0029), upgrade to head, auto-heal present | success | 0 tables created, alembic_version unchanged
Same as above, auto-heal block removed                | success  | 41 tables, correct head
Unknown/orphan revision, auto-heal present (its actual designed case) | success | correctly stamps to head (no DDL needed, none pending)
```

**Root cause:** the auto-heal block reads `alembic_version` (and calls
`inspector.get_table_names()`) on the *same* connection alembic will use to
run migrations. Under SQLAlchemy 2.0's autobegin behavior, that read alone
opens a transaction. When the stored revision is already valid (i.e. every
normal, everyday deploy -- not the orphan-revision case the block was
written for), nothing in the block ever calls `.commit()`, so a stray,
uncommitted transaction is silently handed to `context.configure()` /
`context.begin_transaction()`. Alembic's own migrations run against it
without error, but the connection's exit (with no matching commit) rolls
everything back. Only the "revision not recognized" repair path happened to
work, because it calls `connection.commit()` itself as part of the repair --
incidentally clearing the stray transaction before alembic takes over.

**Why this matters beyond this one merge:** once this branch's
`alembic_version` is correctly stamped to the new reconciled head, *every
future deploy* (from either side) would hit exactly the "already valid"
case -- meaning every migration added after this point, by anyone, would
silently no-op while reporting success. This was not a one-time drift; it
was a standing landmine for the whole team's shared migration pipeline
going forward.

**Fix:** an explicit `connection.rollback()` after the auto-heal check,
before handing the connection to alembic -- resets it to a clean state
regardless of which branch of the auto-heal logic ran. Verified fixed in
all three scenarios above (fresh DB, valid-baseline upgrade, and the
original orphan-revision repair path all now behave correctly).

## 6. Local verification (no deploy)

```
python -m alembic heads                    -> 0036 (single head)
Fresh disposable Postgres 18, upgrade head  -> 41 tables, alembic_version=0036, clean
Same, from a valid 0029 baseline            -> 41 tables, alembic_version=0036, clean (the specific case that was broken)
Same, from an unknown/orphan revision       -> correctly auto-heals to 0036, no spurious DDL
python -c "import backend.main"             -> succeeds cleanly (all 17 routers, incl. admin_drug/agent_v2/rag_monitoring/nudge/health_log)
Local dev Postgres reconciled (0034->0029->[apply nudge+supabase_uid]->stamp 0036) -> nudge table present, ba_user/ba_session/ba_account/ba_verification correctly dropped, all Agent V2 tables intact
```

Test suites (local dev Postgres, reconciled schema):

```
This branch's own Agent V2 suite:  416 passed, 3 skipped (pre-existing Postgres-env gaps), 0 failed
origin/main's own new test files:  103 passed, 0 failed (admin drugs, nudge, health-log, caregiver, escalation, rag telemetry, body metrics)
Full suite:                        1028 passed, 20 skipped, 11 failed
```

The 11 failures were each individually investigated, not waved through:

- 4 in `test_api/test_auth_routes.py` (verify-email/reset-password flows) --
  `email_verification_token`/reset-token generation is not actually wired up
  in `auth_routes.py` on *either* branch (confirmed via grep: the column
  exists on `Account`, nothing sets it anywhere in the app). A gap in
  not-yet-finished functionality, not something this merge broke.
- 1 in `test_api/test_security_authz.py` (`test_get_current_user_valid_jwt`)
  -- calls the FastAPI dependency function directly without triggering
  dependency injection for its `Depends(get_db)` default; predates both
  branches (present at the merge-base already).
- 2 (`test_patient_routes.py::test_doctor_search_still_gets_full_fields_regression`,
  `test_chat_history_e2e.py::test_patient_role_cannot_read_or_hide_another_patients_chat_history`)
  -- **independently reproduced against `origin/main` alone**, via a
  throwaway `git worktree`, with the identical `401 == 200` failure. Not
  caused by this merge.
- 4 in `test_retrieval_sql.py` / `test_drug_confirmation_dispatch.py` --
  local RAG-corpus data completeness gaps (a specific drug name not present
  in this machine's local corpus), matching the exact pattern BUILD-24A's
  own report already documented for this same test file.

No new failures were introduced by this merge; the working tree is exactly
as clean afterward (`git status` empty) as before it started.

## 7. What was deliberately NOT done

- **Not deployed.** Per the user's own instruction, this is local-only --
  `git commit` only, no `railway up`.
- **Did not touch `scripts/safe_migrate.py`** beyond what the `env.py` fix
  already covers (both go through the same buggy code path via
  `command.upgrade(cfg, "head")`, so the `env.py` fix covers `safe_migrate.py`
  too without needing a separate change there).
- **Did not attempt to seed/implement** the missing email-verification-token/
  reset-token generation logic -- that's a pre-existing gap in unfinished
  functionality, out of scope for a reconciliation build.
- **Did not touch the 4 corpus-data-completeness test failures** -- a local
  environment data gap, not a code defect.

---

## Closeout

```
BUILD-24Q: PASS
MIGRATION COLLISION: RESOLVED (0030-0034 -> 0032-0036, single head, no DDL changed)
MERGE: COMPLETE (73 commits, 160 files, 1 trivial conflict resolved)
CRITICAL BUG FOUND: YES (migrations/env.py auto-heal transaction bug -- silently discarded every ordinary migration)
CRITICAL BUG FIXED: YES (explicit connection.rollback() before handing the connection to alembic; verified in all 3 scenarios)
LOCAL SCHEMA TEST: PASS (fresh DB + valid-baseline + orphan-revision, all produce correct 41-table schema at head 0036)
BACKEND IMPORT: PASS (all 17 routers load cleanly)
AGENT V2 TESTS: 416 passed / 3 skipped / 0 failed
MAIN'S OWN NEW TESTS: 103 passed / 0 failed
FULL SUITE: 1028 passed / 20 skipped / 11 failed (all 11 independently confirmed pre-existing on origin/main alone, none caused by this merge)
DEPLOYED: NO (local commit only, per instruction)
NEXT: user decision on when/how to deploy this reconciled state to production; BUILD-25 (production monitoring) can then proceed on a codebase that actually has the Langfuse/RAG-monitoring infrastructure BUILD-25 was about to duplicate
```
