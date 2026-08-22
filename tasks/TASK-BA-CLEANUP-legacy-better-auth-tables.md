# TASK — Legacy Better Auth (`ba_*`) table cleanup

**Status:** LEGACY TABLES INTENTIONALLY RETAINED as of BUILD-24R
(2026-08-22). Not blocking, not urgent — a deliberate follow-up, not
something folded into BUILD-24R's own deploy.

## Background

Migration `0031_remove_better_auth_and_add_supabase_uid.py` (from
`origin/main`, ADR-0013 Supabase auth migration) is supposed to `DROP TABLE
IF EXISTS ba_verification, ba_account, ba_session, ba_user CASCADE`. In
production, `alembic_version` reached "0031" via an auto-heal stamp-only
repair (see report 52-build-24q, migrations/env.py's transaction bug) --
not via the migration's `upgrade()` actually running. The DROP never
executed. Confirmed via BUILD-24R's own dependency audit
(`scripts/agent_v2/ba_tables_dependency_audit.sql`):

```
FK: only internal (ba_session.userId -> ba_user.id, ba_account.userId -> ba_user.id) -- no external table references either direction
Views/Triggers/Functions referencing ba_*: 0
Application code (models/routes/services) referencing ba_*: 0 (grepped the full reconciled working tree)
Row counts: ba_user=15, ba_account=15 (dormant historical data), ba_session=0, ba_verification=0
```

## Decision (BUILD-24R)

Retained as-is, not dropped, for this deploy. Reasoning: dropping tables is
destructive and irreversible without a restore; it was not required for
BUILD-24R's actual goal (restore the 17 missing routes + keep Agent V2 at
100%); and a deliberate, separately-approved cleanup is safer than folding
a DROP TABLE into an already-complex reconciliation deploy.

`alembic stamp 0036` was used (metadata-only, zero DDL) rather than running
migration 0031's `upgrade()` for real -- so this task exists specifically
because the stamp does not perform the drop the migration was originally
meant to do.

## Follow-up (not scheduled, do when convenient)

1. Re-confirm zero dependencies right before acting (this audit is a
   snapshot, not a permanent guarantee -- re-run
   `scripts/agent_v2/ba_tables_dependency_audit.sql` if meaningful time has
   passed or new code has shipped).
2. Take a fresh production backup first (same pattern as every other
   production DB change in this project).
3. Either: (a) write a new migration (0037+) that explicitly drops the 4
   tables, keeping the migration history honest about when it actually
   happened, or (b) a one-off manual `DROP TABLE IF EXISTS ... CASCADE`
   documented the same way BUILD-24O/24R's stamps were.
4. Verify `/health=200` and a normal auth smoke test (login, register)
   afterward -- these tables are unrelated to the current auth path but
   confirm nothing regressed anyway.
