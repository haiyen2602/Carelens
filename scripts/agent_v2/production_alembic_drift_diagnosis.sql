-- Phase 4 STEP 1 blocker diagnosis: production alembic_version reports 0029
-- (seen during this build's `railway up` preDeployCommand failure -- alembic
-- tried "0029 -> 0030" and hit DuplicateColumn on drug_chunks.corpus_version),
-- but BUILD-24A's full pg_dump/restore test (report 31, 2026-08-20) confirmed
-- production was at head (0034) less than 24h earlier. READ-ONLY: every
-- statement below is SELECT/information_schema/pg_catalog only -- no INSERT/
-- UPDATE/DELETE/DDL, no alembic_version change. Paste the full output back for
-- analysis; do not act on any repair yourself from this alone.
--
-- Suggested run (mirrors BUILD-24A's own tcp-proxy pattern):
--   railway tcp-proxy create --service Postgres --environment production --port 5432 --json
--   PGPASSWORD="<production Postgres password>" psql -h <proxy-domain> -p <proxy-port> \
--     -U postgres -d railway -f scripts/agent_v2/production_alembic_drift_diagnosis.sql
--   railway tcp-proxy delete --service Postgres --environment production --yes <proxy-id>

\pset pager off
\pset format aligned
\timing off

SELECT 'ALEMBIC_VERSION' AS section, version_num FROM alembic_version;
SELECT 'ALEMBIC_VERSION_ROWCOUNT' AS section, count(*)::text FROM alembic_version;

SELECT 'DRUG_CHUNKS_COLUMNS' AS section, column_name, data_type
FROM information_schema.columns
WHERE table_name = 'drug_chunks' AND column_name IN ('corpus_version','chunk_key','embedding_model','embedding_dimensions')
ORDER BY column_name;

SELECT 'DRUG_CHUNKS_INDEXES' AS section, indexname
FROM pg_indexes
WHERE tablename = 'drug_chunks' AND indexname IN ('ix_drug_chunks_corpus_version','uq_drug_chunks_corpus_chunk_key');

SELECT 'TABLE_EXISTS' AS section, table_name
FROM information_schema.tables
WHERE table_schema='public' AND table_name IN (
  'rag_corpus','rag_corpus_checkpoint','rag_embedding_reservation',
  'doctor_review_request','agent_run_checkpoint','agent_idempotency_key'
)
ORDER BY table_name;

SELECT 'RAG_CORPUS_COLUMNS' AS section, column_name FROM information_schema.columns WHERE table_name='rag_corpus' ORDER BY ordinal_position;
SELECT 'RAG_CORPUS_CHECKPOINT_COLUMNS' AS section, column_name FROM information_schema.columns WHERE table_name='rag_corpus_checkpoint' ORDER BY ordinal_position;
SELECT 'RAG_EMBEDDING_RESERVATION_COLUMNS' AS section, column_name FROM information_schema.columns WHERE table_name='rag_embedding_reservation' ORDER BY ordinal_position;
SELECT 'DOCTOR_REVIEW_REQUEST_COLUMNS' AS section, column_name FROM information_schema.columns WHERE table_name='doctor_review_request' ORDER BY ordinal_position;
SELECT 'AGENT_RUN_CHECKPOINT_COLUMNS' AS section, column_name FROM information_schema.columns WHERE table_name='agent_run_checkpoint' ORDER BY ordinal_position;
SELECT 'AGENT_IDEMPOTENCY_KEY_COLUMNS' AS section, column_name FROM information_schema.columns WHERE table_name='agent_idempotency_key' ORDER BY ordinal_position;

SELECT 'INDEXES' AS section, tablename, indexname FROM pg_indexes WHERE tablename IN (
  'rag_corpus','rag_corpus_checkpoint','rag_embedding_reservation',
  'doctor_review_request','agent_run_checkpoint','agent_idempotency_key'
) ORDER BY tablename, indexname;

SELECT 'ROWCOUNT_rag_corpus' AS section, count(*)::text FROM rag_corpus;
SELECT 'ROWCOUNT_rag_corpus_checkpoint' AS section, count(*)::text FROM rag_corpus_checkpoint;
SELECT 'ROWCOUNT_rag_embedding_reservation' AS section, count(*)::text FROM rag_embedding_reservation;
SELECT 'ROWCOUNT_doctor_review_request' AS section, count(*)::text FROM doctor_review_request;
SELECT 'ROWCOUNT_agent_run_checkpoint' AS section, count(*)::text FROM agent_run_checkpoint;
SELECT 'ROWCOUNT_agent_idempotency_key' AS section, count(*)::text FROM agent_idempotency_key;

SELECT 'ROWCOUNT_drug_product' AS section, count(*)::text FROM drug_product;
SELECT 'ROWCOUNT_drug_id_map' AS section, count(*)::text FROM drug_id_map;
SELECT 'ROWCOUNT_drug_product_ingredient' AS section, count(*)::text FROM drug_product_ingredient;
SELECT 'ROWCOUNT_drug_chunks_total' AS section, count(*)::text FROM drug_chunks;
SELECT 'ROWCOUNT_drug_chunks_legacy' AS section, count(*)::text FROM drug_chunks WHERE corpus_version IS NULL;
SELECT 'ROWCOUNT_drug_chunks_v2' AS section, count(*)::text FROM drug_chunks WHERE corpus_version IS NOT NULL;
SELECT 'ROWCOUNT_account' AS section, count(*)::text FROM account;
SELECT 'ROWCOUNT_medication_safety_policy' AS section, count(*)::text FROM medication_safety_policy;
SELECT 'MSP_REVIEWED' AS section, count(*)::text FROM medication_safety_policy WHERE review_status='REVIEWED';

SELECT 'CANARY_ACCOUNTS' AS section, id, email, status FROM account WHERE id LIKE 'agent-v2-canary-%' ORDER BY id;

SELECT 'SCHEMA_MIGRATIONS_TABLE_CHECK' AS section, to_regclass('public.alembic_version') IS NOT NULL AS alembic_table_exists;
