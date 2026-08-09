# TASK-003: Skeleton FastAPI + docker-compose (Postgres + pgvector) + CI xanh

**Domain:** `infra`
**Owner:** Trương Quốc Trường + AI
**Sprint:** sprint-02
**Status:** To Do
**Ưu tiên:** P0 · **Backlog item:** [`INFRA-01`](../planning/backlog.md)

## Mục tiêu (Goal)

Dựng xong nền móng kỹ thuật để Sprint 03 code feature được ngay: một service FastAPI chạy được bằng `docker compose up`, có Postgres + pgvector kèm theo, cấu trúc thư mục đúng ADR-0004, và CI xanh trên `main`. Đây cũng là cách xử lý rủi ro "hết Sprint mà vẫn không có code nào được commit".

## Acceptance Criteria (AC)

- [ ] `docker compose up` khởi động được **cả 2 service**: `backend` (FastAPI) và `db` (Postgres có extension `pgvector`) — hiện `docker-compose.yml` **chỉ có `backend`**, thiếu hẳn database.
- [ ] `GET /health` trả **200** và cho biết trạng thái kết nối DB (không chỉ `{"status":"ok"}` tĩnh như hiện tại).
- [ ] Extension `vector` được tạo tự động khi container DB khởi động lần đầu (init script), không phải bước thủ công.
- [ ] Cấu trúc thư mục `src/` khớp [ADR-0004](../adrs/0004-project-structure-and-coding-convention.md) và ranh giới domain trong [`/specs/domains.md`](../specs/domains.md).
- [ ] **Dọn sạch phần boilerplate còn sót của template** — `src/main.py` đang khai báo `title="AI20K Agent"`, không phải tên dự án VMEC-04.
- [ ] Có thư mục `tests/` với ít nhất **1 test thật** (`/health` trả 200) — CI hiện chạy `pytest tests/` nhưng **thư mục `tests/` chưa tồn tại**.
- [ ] `ruff check` sạch trên `src/` và `tests/`.
- [ ] CI **xanh trên `main`**, chạy đủ: ruff → pytest. Badge/kết quả CI xem được.
- [ ] `.env.example` đủ mọi biến cần để chạy local; `.env` thật **không** được commit (kiểm tra `.gitignore`).
- [ ] `README.md` có mục "Chạy local trong 3 lệnh" mà người mới clone làm theo được, không cần hỏi ai.

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [ ] [`/adrs/0004-project-structure-and-coding-convention.md`](../adrs/0004-project-structure-and-coding-convention.md)
- [ ] [`/adrs/0006-tech-stack.md`](../adrs/0006-tech-stack.md)
- [ ] [`/adrs/0008-vector-store-pgvector.md`](../adrs/0008-vector-store-pgvector.md)
- [ ] [`/adrs/0002-domain-split.md`](../adrs/0002-domain-split.md) — modular monolith, ranh giới module
- [ ] [`/specs/domains.md`](../specs/domains.md) — bảng module code dự kiến của từng domain
- [ ] [`/specs/api-contracts.md`](../specs/api-contracts.md)
- [ ] [`AGENTS.md`](../AGENTS.md)

## Gợi ý chia subtask (AI tự cập nhật khi bắt đầu)

- [ ] Thêm service `db` (image có sẵn pgvector) vào `docker-compose.yml` + volume dữ liệu + healthcheck + `depends_on` từ `backend`
- [ ] Init script SQL tạo `CREATE EXTENSION IF NOT EXISTS vector;`
- [ ] Cấu hình kết nối DB qua `src/config.py` (đọc từ env, không hardcode)
- [ ] Nâng `/health` thành health check thật (ping DB), giữ nguyên đường dẫn `/health`
- [ ] Đổi metadata app trong `src/main.py` sang VMEC-04, bỏ mô tả boilerplate
- [ ] Tạo `tests/` + test `/health` + `conftest.py` (test không được phụ thuộc DB thật đang chạy)
- [ ] Tạo khung thư mục rỗng theo domain (`src/api/`, `src/services/<domain>/`, `src/agents/`) kèm `__init__.py`
- [ ] Chạy `ruff` + `pytest` local, sửa hết lỗi
- [ ] Mở PR, xác nhận CI xanh, cập nhật `README.md`

## Definition of Done

Áp dụng checklist chuẩn ở [`ADR-0005`](../adrs/0005-definition-of-done.md). Tiêu chí riêng của task này:

- [ ] Một thành viên **khác** clone repo sạch, chạy theo README và lên được `/health` 200 — có người xác nhận, không phải "máy tôi chạy được"
- [ ] CI xanh trên nhánh `main` sau khi merge, không chỉ trên nhánh feature

## Ghi chú / trao đổi thêm

- **Đây là task chặn nhiều thứ nhất trong sprint.** Rủi ro đã ghi: hết ngày 4 mà `src/` vẫn rỗng thì đẩy task tài liệu xuống, ưu tiên task này lên trước.
- Alembic migration + schema DB đầy đủ **không** thuộc task này — đó là `INFRA-02`, Sprint 03. Task này chỉ cần DB chạy được và có pgvector.
- Không implement business logic của bất kỳ domain nào ở đây; chỉ dựng khung.
- `[CẦN CHỐT]` Model LLM + provider (ADR-0006 đang để trống) ảnh hưởng tới biến env cần thiết trong `.env.example` — Nguyễn Minh Đạt chốt, xem việc quản trị team trong [sprint-02](../planning/sprints/sprint-02.md).

---
**Điều hướng:** [Sprint 02](../planning/sprints/sprint-02.md) · [Backlog](../planning/backlog.md) · [Tasks](./)
