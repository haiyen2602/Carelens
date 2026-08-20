# TASK-019: Admin RAG Database-backed Drug View

**Domain:** `drug-knowledge` + `reporting` (Admin UI)
**Owner:** Nguyễn Minh Đạt + AI
**Sprint:** Chưa phân Sprint
**Status:** In Review
**Ưu tiên:** P0

## Mục tiêu (Goal)

Thay dữ liệu thuốc mock trên màn hình Admin RAG bằng dữ liệu đọc thật từ các bảng
canonical V2 trong PostgreSQL. Màn hình chỉ đọc, hiển thị cả thuốc canonical và
các mapping theo trạng thái.

## Acceptance Criteria (AC)

- [x] `GET /api/v1/admin/drugs` trả dữ liệu từ `drug_product`,
      `drug_product_ingredient`, `ingredient`, `drug_id_map`, không dùng mock.
- [x] `GET /api/v1/admin/drugs/{drug_product_id}` trả chi tiết thuốc, hoạt chất
      và toàn bộ mapping.
- [x] API hỗ trợ tìm kiếm, lọc `ACTIVE`/`AMBIGUOUS`/`RETIRED`/`UNMAPPED`, phân
      trang và sắp xếp ổn định.
- [x] API kiểm tra quyền admin theo convention hiện có.
- [x] Frontend Admin RAG hiển thị dữ liệu API với loading/error/empty states,
      tìm kiếm/lọc/phân trang và không còn `admin-mock` cho dữ liệu thuốc.
- [x] Không còn cảnh báo “Dữ liệu minh hoạ (mock)” hoặc nút/cột “Index lại”.
- [x] Không có endpoint reindex, thay đổi dữ liệu, migration ngoài phạm vi hoặc
      thay đổi `DRUG_KNOWLEDGE_BACKEND`/runtime RAG.
- [ ] Backend và frontend tests cover các AC chính; lint/build liên quan pass.
- [x] API contract được cập nhật và ghi lịch sử thay đổi.

## Verification (2026-08-19)

- PASS: `.venv\\Scripts\\python.exe -m pytest -q tests/test_admin_drug_schemas.py tests/test_admin_drugs_service.py tests/test_admin_drug_routes.py` — `27 passed`.
- PASS: `frontend\\npm run test:admin-drugs` — `admin-drugs frontend contract checks passed`.
- PASS: `frontend\\npx eslint src/app/admin/medicines/page.tsx src/lib/admin-drugs.ts` — no errors.
- PASS: `frontend\\npm run build` — Next.js production build completed successfully.
- PASS: stale search/filter/page requests are aborted during effect cleanup; regression check added in `frontend/tests/admin-drugs.test.mjs`.
- PASS: `rg -n "Dữ liệu minh hoạ|Index lại|simulateImport|reindex|MEDICINES" frontend/src/app/admin/medicines frontend/src/lib/admin-drugs.ts` — no matches.
- PASS: `git diff --check` — no whitespace errors.
- BLOCKED: `.venv\\Scripts\\python.exe -m pytest -q` — collection fails because environment lacks `cv2` and `numpy` for unrelated VLM tests.
- BLOCKED: `frontend\\npm run lint` — existing repository-wide CRLF/Prettier errors across unrelated files; scoped TASK-019 files pass ESLint.

The final AC remains unchecked until the environment-wide backend suite and frontend lint gate are green.

## Context bắt buộc phải đọc trước khi làm

- [ ] `AGENTS.md`
- [ ] `specs/domains.md`
- [ ] `specs/business-rules.md`
- [ ] `specs/api-contracts.md`
- [ ] `adrs/0002-domain-split.md`
- [ ] `adrs/0003-api-contract-first.md`
- [ ] `adrs/0004-project-structure-and-coding-convention.md`
- [ ] `adrs/0005-definition-of-done.md`
- [ ] `adrs/0012-drug-data-v2-compatibility-and-provenance.md`
- [ ] `backend/db/models.py`
- [ ] `docs/superpowers/specs/2026-08-19-admin-rag-database-design.md`

## Gợi ý chia subtask

- [ ] Cập nhật contract admin drug list/detail và schema response.
- [ ] Implement service/routes với query canonical và authorization.
- [ ] Thay mock data trên frontend bằng API và hoàn thiện states/filter/pagination.
- [ ] Viết test backend/frontend, lint/build và kiểm tra không còn reindex/mock UI.

## Definition of Done

Áp dụng checklist chuẩn tại `adrs/0005-definition-of-done.md`. Không deploy hoặc
merge trực tiếp vào `main`; reviewer domain cần được chỉ định theo `TEAM.md`.

## Ngoài phạm vi

Indexing, reindex, worker, chỉnh sửa mapping, prescription/dose backfill, migration
schema và cutover runtime RAG.
