-- BUILD-24R dependency audit: confirm zero FK/view/trigger/function references
-- to the 4 ba_* (Better Auth) tables before deciding to retain them as
-- legacy-intentionally-kept. Read-only.

\pset pager off
\pset format aligned

-- Foreign keys pointing FROM other tables TO ba_*, or FROM ba_* to others
SELECT 'FK_REFERENCING_BA' AS section,
       tc.table_name AS referencing_table, kcu.column_name,
       ccu.table_name AS referenced_table, ccu.column_name AS referenced_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND (ccu.table_name LIKE 'ba\_%' OR tc.table_name LIKE 'ba\_%');

-- Views that reference ba_* tables
SELECT 'VIEWS_REFERENCING_BA' AS section, viewname
FROM pg_views
WHERE definition ILIKE '%ba_user%' OR definition ILIKE '%ba_session%'
   OR definition ILIKE '%ba_account%' OR definition ILIKE '%ba_verification%';

-- Triggers on the ba_* tables themselves, or elsewhere referencing them
SELECT 'TRIGGERS_ON_BA' AS section, event_object_table, trigger_name
FROM information_schema.triggers
WHERE event_object_table LIKE 'ba\_%';

-- Functions/procedures whose body mentions ba_* tables
SELECT 'FUNCTIONS_REFERENCING_BA' AS section, proname
FROM pg_proc
WHERE prosrc ILIKE '%ba_user%' OR prosrc ILIKE '%ba_session%'
   OR prosrc ILIKE '%ba_account%' OR prosrc ILIKE '%ba_verification%';

-- Row counts (informational -- confirms whether they're actually empty/dormant)
SELECT 'ROWCOUNT_ba_user' AS section, count(*)::text FROM ba_user;
SELECT 'ROWCOUNT_ba_session' AS section, count(*)::text FROM ba_session;
SELECT 'ROWCOUNT_ba_account' AS section, count(*)::text FROM ba_account;
SELECT 'ROWCOUNT_ba_verification' AS section, count(*)::text FROM ba_verification;
