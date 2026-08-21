# Admin RAG Database-backed Drug View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Admin RAG mock medicine table with a read-only, authorized API backed by canonical Drug Data V2 tables.

**Architecture:** Add a focused admin drug service/router that aggregates `drug_product`, ingredients, and mappings into stable paginated DTOs. Update the existing medicines page to fetch the API and render search/filter/pagination states; remove all mock warning/import/reindex behavior. Keep RAG runtime and canonical public contracts unchanged except for the new admin read contract.

**Tech Stack:** FastAPI, SQLAlchemy 2, Pydantic, PostgreSQL, Next.js/React, Vitest/Jest conventions already present in `frontend`, pytest.

---

### Task 1: Define and test the admin drug response contract

**Files:**
- Modify: `specs/api-contracts.md` (admin API table and history)
- Create: `backend/models/admin_drug_schemas.py`
- Test: `tests/test_admin_drug_schemas.py`

- [ ] **Step 1: Write failing schema tests** for list/detail serialization, enum statuses, pagination metadata, and nullable canonical fields.
- [ ] **Step 2: Run** `pytest tests/test_admin_drug_schemas.py -q`; expect failure because schemas do not exist.
- [ ] **Step 3: Implement** Pydantic DTOs: `AdminDrugMapping`, `AdminDrugItem`, `AdminDrugListResponse`, `AdminDrugDetailResponse`; use `Literal`/enum for `ACTIVE`, `AMBIGUOUS`, `RETIRED`, `UNMAPPED` and bounded positive pagination fields.
- [ ] **Step 4: Update** `specs/api-contracts.md` with `GET /admin/drugs`, `GET /admin/drugs/{drug_product_id}`, query parameters, response fields, admin role, and a dated history entry.
- [ ] **Step 5: Run** `pytest tests/test_admin_drug_schemas.py -q`; expect PASS.
- [ ] **Step 6: Commit** `git add backend/models/admin_drug_schemas.py tests/test_admin_drug_schemas.py specs/api-contracts.md && git commit -m "feat(admin-rag): define database drug contract"`.

### Task 2: Implement canonical database query service

**Files:**
- Create: `backend/services/admin_drugs.py`
- Test: `tests/test_admin_drugs_service.py`
- Reference: `backend/db/models.py`, `backend/db/session.py` (or repository session dependency)

- [ ] **Step 1: Write failing service tests** using an isolated SQLAlchemy test session with products, ingredients, junctions, and all mapping statuses; cover search, status filtering, stable `display_name`/`id` ordering, page boundaries, aggregation, and missing detail.
- [ ] **Step 2: Run** `pytest tests/test_admin_drugs_service.py -q`; expect failure because service functions do not exist.
- [ ] **Step 3: Implement** `list_admin_drugs(session, q, mapping_status, page, page_size)` with SQL-level filtering/count/order and deterministic aggregation. A status filter must match products having at least one mapping of that status; products without mappings remain visible only when no status filter is supplied.
- [ ] **Step 4: Implement** `get_admin_drug(session, drug_product_id)` returning `None` for missing products and never emitting orphan mappings/ingredients.
- [ ] **Step 5: Run** the focused service tests and `python -m compileall backend/services/admin_drugs.py backend/models/admin_drug_schemas.py`; expect PASS and no compile errors.
- [ ] **Step 6: Commit** `git add backend/services/admin_drugs.py tests/test_admin_drugs_service.py && git commit -m "feat(admin-rag): query canonical drug data"`.

### Task 3: Add authorized FastAPI routes

**Files:**
- Create: `backend/api/admin_drug_routes.py`
- Modify: `backend/main.py`
- Test: `tests/test_admin_drug_routes.py`
- Reference: `backend/api/security.py`, `backend/api/account_routes.py`, `backend/db/base.py`

- [ ] **Step 1: Write failing route tests** for admin success, non-admin rejection using the repository's existing auth dependency, list query forwarding, detail 404, and response shape.
- [ ] **Step 2: Run** `pytest tests/test_admin_drug_routes.py -q`; expect failure because router is absent.
- [ ] **Step 3: Implement** `admin_drug_router` with `GET /admin/drugs` and `GET /admin/drugs/{drug_product_id}`, injecting the existing DB session and admin authorization dependency; translate service `None` to 404 and invalid query values to 422.
- [ ] **Step 4: Register** the router in `backend/main.py` under the existing `/api/v1` prefix. Do not add reindex or mutation routes.
- [ ] **Step 5: Run** route tests and inspect `app.openapi()` to confirm both paths and no reindex path; expect PASS.
- [ ] **Step 6: Commit** `git add backend/api/admin_drug_routes.py backend/main.py tests/test_admin_drug_routes.py && git commit -m "feat(admin-rag): expose read-only drug endpoints"`.

### Task 4: Replace the Admin RAG mock UI

**Files:**
- Modify: `frontend/src/app/admin/medicines/page.tsx`
- Create or modify: `frontend/src/lib/admin-drugs.ts`
- Test: existing frontend test location for admin pages, or `frontend/src/app/admin/medicines/page.test.tsx` following local convention

- [ ] **Step 1: Write failing UI tests** asserting API rows render, loading/error/empty states render, mapping status filter and pagination update requests, and the page contains no mock warning, import button, or `Index lại` text/control.
- [ ] **Step 2: Run** the focused frontend test command from `frontend/package.json`; expect failure against the mock implementation.
- [ ] **Step 3: Implement** a typed API client using the configured backend base URL and auth headers; replace `MEDICINES`, timers, `simulateImport`, `reindex`, status metadata, and the action column with API-driven canonical/mapping fields.
- [ ] **Step 4: Add** debounced or submit-based search, mapping-status select, bounded pagination controls, and accessible loading/error/empty states while preserving existing visual conventions.
- [ ] **Step 5: Run** focused frontend tests, lint, and typecheck/build commands defined in `frontend/package.json`; expect PASS.
- [ ] **Step 6: Commit** `git add frontend/src/app/admin/medicines/page.tsx frontend/src/lib/admin-drugs.ts frontend/src/app/admin/medicines/page.test.tsx && git commit -m "feat(admin-rag): render canonical drugs from api"`.

### Task 5: Full verification and documentation

**Files:**
- Modify: `tasks/TASK-019-admin-rag-database-view.md` (checklist/status only)
- No production code changes unless verification exposes a scoped defect.

- [ ] **Step 1: Run** `pytest -q` and the frontend lint/typecheck/test/build commands; record exact results.
- [ ] **Step 2: Run** `rg -n "Dữ liệu minh hoạ|Index lại|simulateImport|reindex|MEDICINES" frontend/src/app/admin/medicines frontend/src/lib/admin-drugs.ts`; expect no matches for removed UI behavior (legacy mock file may remain for unrelated admin pages).
- [ ] **Step 3: Run** `git diff --check` and review the diff for forbidden runtime/RAG/schema changes.
- [ ] **Step 4: Update** TASK-019 AC checkboxes only for verified items and add test commands/results to the task notes.
- [ ] **Step 5: Commit** `git add tasks/TASK-019-admin-rag-database-view.md && git commit -m "test(admin-rag): verify database-backed drug view"`.

