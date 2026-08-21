# ADR-0013: Chuyển đổi từ Better Auth sang Supabase Auth

**Status:** Accepted  
**Ngày:** 2026-08-21  
**Người đề xuất:** AI Agent (Antigravity)  
**Người duyệt:** Đội ngũ phát triển VMEC-04 / User  

---

## Bối cảnh (Context)

Trước đây, dự án sử dụng Better Auth (`1.6.29`) chạy trên frontend Next.js kết hợp kết nối PostgreSQL trực tiếp (`pg` pool) để xử lý luồng Google OAuth (migration `0025_better_auth_tables.py`).
Tuy nhiên, việc duy trì Better Auth phát sinh một số hạn chế:
1. Yêu cầu tạo và quản lý riêng 4 bảng phụ (`ba_user`, `ba_session`, `ba_account`, `ba_verification`) trong cơ sở dữ liệu chính.
2. Frontend Next.js phải mở connection pool trực tiếp tới PostgreSQL (`DATABASE_URL`), gây lãng phí connection pool và tiềm ẩn rủi ro khi deploy trên môi trường serverless/edge.
3. Supabase Auth cung cấp hệ sinh thái Auth IdP hoàn thiện hơn, hỗ trợ sẵn quản lý OAuth providers, email authentication, PKCE flow, và dễ dàng mở rộng sang các dịch vụ đám mây khác.

---

## Quyết định (Decision)

1. **Thay thế Better Auth bằng Supabase Auth** trên cả Frontend (Next.js) và Backend (FastAPI).
2. **Vai trò của Supabase Auth:**
   - Làm Identity Provider (IdP) và môi giới OAuth (Google Sign-In, Email/Password, Auth callbacks).
   - Xử lý các luồng cấp phép, xác thực người dùng ngoài biên (edge/client).
3. **Giữ nguyên Kiến trúc Domain RBAC & Y tế tại Backend FastAPI:**
   - Nguồn sự thật về danh tính, phân quyền y tế (`role`: doctor, patient, caregiver, admin), quan hệ bệnh nhân (`patient_id`), bác sĩ (`doctor_id`), và trạng thái khóa tài khoản (`status == "active"`) **vẫn nằm hoàn toàn tại bảng `account` của backend FastAPI**.
   - Supabase User ID (`supabase_uid`) được liên kết vào bảng `account`.
   - Endpoint `POST /api/v1/auth/oauth/google` tiếp tục đóng vai trò chuyển đổi định danh đã xác thực từ Supabase thành JWT token chính thức của hệ thống có ký quyền hạn.
4. **Dọn dẹp DB:** Drop 4 bảng `ba_*` của Better Auth thông qua migration mới (`0028_remove_better_auth_tables.py`).

---

## Vì sao (Rationale)

- Giảm thiểu độ phức tạp schema của Database (loại bỏ hoàn toàn các bảng `ba_*`).
- Frontend Next.js không còn cần duy trì `node-postgres (pg)` pool chỉ để phục vụ Better Auth.
- Tận dụng SDK chính thức của Supabase (`@supabase/supabase-js`, `@supabase/ssr`) với luồng PKCE chuẩn bảo mật cao.
- Không làm xáo trộn ~40 API endpoints và toàn bộ hệ thống phân quyền y tế nghiêm ngặt đã xây dựng và kiểm thử trong backend FastAPI.

---

## Hệ quả (Consequences)

**Tích cực:**
- Kiến trúc gọn gàng, giảm bớt tài nguyên kết nối DB từ Next.js.
- Cấu hình OAuth đơn giản và chuẩn hóa qua Supabase Dashboard.

**Cần lưu ý:**
- Cần cung cấp các biến môi trường `NEXT_PUBLIC_SUPABASE_URL` và `NEXT_PUBLIC_SUPABASE_ANON_KEY` trong `.env` và `frontend/.env.local`.

---

## Câu chốt

> Dùng Supabase Auth làm IdP/OAuth bên ngoài, giữ vững Domain RBAC và bảo mật y tế bên trong Backend FastAPI.
