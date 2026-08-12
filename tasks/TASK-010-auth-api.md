# TASK-010: Xây `auth-api` thật (JWT) thay rào tạm `X-Internal-Secret`

**Domain:** `auth`
**Owner:** Nguyễn Hải Yến + AI
**Sprint:** sprint-03 (ngoài kế hoạch — chặn production, xem `chatbot-rag-design.md` mục 10 #10)
**Status:** In Progress
**Ưu tiên:** P0 · **Backlog item:** liên quan `FEAT-001` (domain `prescription, auth`)

## Mục tiêu (Goal)

Thay rào tạm `require_internal_secret` (`backend/api/security.py`) bằng đăng nhập thật: 1 bảng `account` trong Postgres, `POST /api/v1/auth/login` trả JWT, các route hiện có (`/api/v1/chat`) xác thực qua JWT thay vì shared-secret. Đúng ghi chú sẵn trong code: "XOÁ dependency này khỏi route NGAY khi auth-api thật được xây".

## Acceptance Criteria (AC)

- [x] `POST /api/v1/auth/login` — đúng request/response JSON mẫu trong `api-contracts.md` §1 (trả `access_token`, `token_type`, `expires_in`, `user: {id, full_name, role}`).
- [x] `POST /api/v1/auth/refresh`, `GET /api/v1/auth/me` hoạt động.
- [x] JWT payload chứa `sub` + `role`, khớp `api-contracts.md` mục "Nguyên tắc" (`Authorization: Bearer <JWT>`).
- [x] Bảng `account` — 1 bảng chung cho 4 role (`doctor|patient|caregiver|admin`), migration Alembic reversible.
- [x] `/api/v1/chat` không còn nhận `X-Internal-Secret` — yêu cầu Bearer JWT hợp lệ, 401 nếu thiếu/sai/hết hạn.
- [x] `get_current_patient_id()` đọc `patient_id` từ JWT đã xác thực (role=patient), không tin `request.patient_id` trong body cho patient tự gọi.
- [x] Có script tạo tài khoản admin đầu tiên (không có endpoint đăng ký công khai — đúng `user-roles.md`: chỉ admin quản lý tài khoản).
- [x] Test: sai password → 401; đúng → 200 + JWT hợp lệ; `/chat` thiếu Bearer → 401.

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [ ] `specs/api-contracts.md` §1 (`auth-api`), §1b (`account-api`)
- [ ] `specs/user-roles.md` (permission matrix + quan hệ liên kết)
- [ ] `backend/api/security.py` (rào tạm hiện tại, comment ghi rõ hướng thay thế)
- [ ] `AGENTS.md`

## Gợi ý chia subtask (AI tự cập nhật khi bắt đầu)

- [x] `passlib[bcrypt]` + `python-jose[cryptography]` vào `requirements.txt`
- [x] `JWT_SECRET` + cấu hình liên quan vào `backend/config.py` (fail-closed, theo pattern `internal_auth_secret`)
- [x] Model `Account` + migration `0012_account` (đánh số lại từ `0009` — xem "Ghi chú")
- [x] `backend/services/auth.py` (hash password, tạo/giải mã JWT)
- [x] `backend/api/auth_routes.py` (login/refresh/me) + đăng ký router trong `backend/main.py`
- [x] `get_current_user`, `require_role` trong `backend/api/security.py`; sửa `get_current_patient_id`
- [x] Gỡ `require_internal_secret` khỏi `chat_routes.py`, thay `Depends(get_current_user)`
- [x] `scripts/create_admin.py`
- [x] Test `tests/test_api` cho `/auth/login`, `/chat` (401 khi thiếu JWT)
- [x] Follow-up: `account-api` (`backend/api/account_routes.py`, migration `0013`) + wire frontend admin/doctor/patient login thật

## Definition of Done

Áp dụng checklist chuẩn ở [`ADR-0005`](../adrs/0005-definition-of-done.md).

- [x] `alembic upgrade head` rồi `alembic downgrade -1` chạy sạch, không lỗi.
- [x] `pytest tests/test_api` xanh.
- [x] Không còn route nào dùng `X-Internal-Secret` cho `/api/v1/chat` (backend) — riêng `app/api/chat/route.ts` (frontend BFF proxy) đã đổi sang forward JWT thật, xem "Ghi chú".

## Ghi chú / trao đổi thêm

- Quyết định 2026-08-12: đi theo đúng contract đã chốt trong `api-contracts.md` §1 (1 bảng account chung + 1 endpoint `/auth/login` phân biệt qua `role`) — **không** tách bảng/endpoint riêng theo role, tránh lệch khỏi contract đã Draft sẵn.
- Ngoài phạm vi task này: OTP cho patient, SSO, quản lý liên kết bác sĩ↔bệnh nhân↔người thân đầy đủ (thuộc `FEAT-001`/quản lý tài khoản của admin), đổi mật khẩu/quên mật khẩu.
- **2026-08-13 (round 2)** — chốt với PM: (1) thay hẳn luồng OTP mock trên `/` bằng email/password thật; (2) làm luôn UI `/admin/accounts` thật thay vì chỉ CLI. Kéo theo contract mới `account-api` (`specs/api-contracts.md` §1b, migration `0013_account_status`, `backend/api/account_routes.py`, cột `Account.status`, check status trong `/auth/login`). Đã test end-to-end thật (backend qua curl, frontend qua Next.js Route Handler + cookie, `npm run build` sạch).
- **2026-08-13 (round 3, deploy) — đánh số lại migration**: lúc chuẩn bị push lên Railway phát hiện `main` đã đổi cấu trúc `src/` → `backend/` (PR deploy setup #14) và đã merge thêm `0009_patient`/`0010_prescription_fields`/`0011_photo_verification`. Migration của task này được port từ `0009_account`/`0010_account_status` sang **`0012_account`/`0013_account_status`**, toàn bộ code port từ `src/` sang `backend/`. Không có xung đột nội dung (Account model chưa tồn tại trên main trước đó).
- **Phát hiện quan trọng lúc port**: `main` đã có sẵn `frontend/src/app/api/chat/route.ts` (BFF proxy cho `/api/v1/chat`, tự gắn `X-Internal-Secret`) được xây trong lúc branch này đang làm việc riêng — dùng chung giả định với rào tạm đã bị gỡ ở đây. Đã sửa `route.ts` để forward `Authorization: Bearer <JWT>` thật từ client thay vì tự gắn `X-Internal-Secret`, tránh phá luồng chat đang chạy trên production.
- **Còn lại, ngoài phạm vi**: dashboard doctor/patient vẫn 100% mock tĩnh (chỉ gate đăng nhập là thật); đăng nhập cho role `caregiver` chưa có route/dashboard nào; `admin/page.tsx` (dashboard) và các trang admin khác (`audit`, `links`, `medicines`, `profile`) vẫn dùng `admin-mock.ts`.

---
**Điều hướng:** [Backlog](../planning/backlog.md) · [Tasks](./)
