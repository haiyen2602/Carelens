-- BUILD-24Q reconciliation prerequisite: full read-only ground-truth snapshot
-- of production schema, to plan migration renumbering between the two
-- diverged branches (feature/agent-architecture-v2 vs origin/main). Every
-- statement is SELECT/information_schema/pg_catalog only -- no writes.

\pset pager off
\pset format aligned
\timing off

SELECT 'ALEMBIC_VERSION' AS section, version_num FROM alembic_version;

SELECT 'ALL_PUBLIC_TABLES' AS section, table_name
FROM information_schema.tables
WHERE table_schema='public'
ORDER BY table_name;

-- main's 0030 (nudge)
SELECT 'NUDGE_TABLE_EXISTS' AS section, to_regclass('public.nudge') IS NOT NULL AS exists;

-- main's 0031 (drop ba_*, add account.supabase_uid)
SELECT 'BA_USER_EXISTS' AS section, to_regclass('public.ba_user') IS NOT NULL AS exists;
SELECT 'BA_SESSION_EXISTS' AS section, to_regclass('public.ba_session') IS NOT NULL AS exists;
SELECT 'BA_ACCOUNT_EXISTS' AS section, to_regclass('public.ba_account') IS NOT NULL AS exists;
SELECT 'BA_VERIFICATION_EXISTS' AS section, to_regclass('public.ba_verification') IS NOT NULL AS exists;
SELECT 'ACCOUNT_SUPABASE_UID_COLUMN' AS section, column_name, data_type
FROM information_schema.columns
WHERE table_name='account' AND column_name='supabase_uid';
SELECT 'ACCOUNT_SUPABASE_UID_INDEX' AS section, indexname
FROM pg_indexes WHERE tablename='account' AND indexname='ix_account_supabase_uid';

-- my branch's 0030-0034 (already confirmed present once before, reconfirm)
SELECT 'MY_DRUG_CHUNKS_COLUMNS' AS section, column_name
FROM information_schema.columns
WHERE table_name='drug_chunks' AND column_name IN ('corpus_version','chunk_key','embedding_model','embedding_dimensions')
ORDER BY column_name;
SELECT 'MY_TABLES_EXIST' AS section, table_name
FROM information_schema.tables
WHERE table_schema='public' AND table_name IN (
  'rag_corpus','rag_corpus_checkpoint','rag_embedding_reservation',
  'doctor_review_request','agent_run_checkpoint','agent_idempotency_key'
)
ORDER BY table_name;

-- row counts for the tables both branches care about, to catch any data loss
SELECT 'ROWCOUNT_account' AS section, count(*)::text FROM account;
SELECT 'ROWCOUNT_nudge' AS section,
  (CASE WHEN to_regclass('public.nudge') IS NOT NULL THEN (SELECT count(*)::text FROM nudge) ELSE 'N/A' END);
SELECT 'ROWCOUNT_agent_run_checkpoint' AS section, count(*)::text FROM agent_run_checkpoint;
SELECT 'ROWCOUNT_doctor_review_request' AS section, count(*)::text FROM doctor_review_request;
SELECT 'ROWCOUNT_agent_idempotency_key' AS section, count(*)::text FROM agent_idempotency_key;
SELECT 'ROWCOUNT_drug_chunks_total' AS section, count(*)::text FROM drug_chunks;
