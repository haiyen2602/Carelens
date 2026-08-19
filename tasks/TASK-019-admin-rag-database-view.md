# TASK-019: Admin RAG Database-backed Drug View

**Domain:** `drug-knowledge` + `reporting` (Admin UI)
**Owner:** Nguyễn Minh Đạt + AI
**Sprint:** Chưa phân Sprint
**Status:** To Do
**Ưu tiên:** P0

## Mục tiêu (Goal)

Thay dữ liệu thuốc mock trên màn hình Admin RAG bằng dữ liệu đọc thật từ các bảng
canonical V2 trong PostgreSQL. Màn hình chỉ đọc, hiển thị cả thuốc canonical và
các mapping theo trạng thái.

## Acceptance Criteria (AC)

- [ ] `GET /api/v1/admin/drugs` trả dữ liệu từ `drug_product`,
      `drug_product_ingredient`, `ingredient`, `drug_id_map`, không dùng mock.
- [ ] `GET /api/v1/admin/drugs/{drug_product_id}` trả chi tiết thuốc, hoạt chất
      và toàn bộ mapping.
- [ ] API hỗ trợ tìm kiếm, lọc `ACTIVE`/`AMBIGUOUS`/`RETIRED`/`UNMAPPED`, phân
      trang và sắp xếp ổn định.
- [ ] API kiểm tra quyền admin theo convention hiện có.
- [ ] Frontend Admin RAG hiển thị dữ liệu API với loading/error/empty states,
      tìm kiếm/lọc/phân trang và không còn `admin-mock` cho dữ liệu thuốc.
- [ ] Không còn cảnh báo “Dữ liệu minh hoạ (mock)” hoặc nút/cột “Index lại”.
- [ ] Không có endpoint reindex, thay đổi dữ liệu, migration ngoài phạm vi hoặc
      thay đổi `DRUG_KNOWLEDGE_BACKEND`/runtime RAG.
- [ ] Backend và frontend tests cover các AC chính; lint/build liên quan pass.
- [ ] API contract được cập nhật và ghi lịch sử thay đổi.

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
