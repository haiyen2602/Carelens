# TASK-TELEGRAM-BOT: Bot Telegram làm trợ lý đầy đủ + kênh thông báo

**Domain:** Notifications / Agent V2 / Telegram
**Owner:** Nguyễn Hải Yến + AI
**Sprint:** To be assigned
**Status:** In Progress

## Mục tiêu (Goal)

Bot Telegram có hai chức năng chính:

1. **Trợ lý** — trả lời được đúng những gì chatbot trên production trả lời được.
2. **Kênh thông báo** — nhắc uống thuốc, cảnh báo, tin nhắn từ bác sĩ và người thân.

Quy tắc kiến trúc đã chốt ngày 2026-08-28:

- **Bot KHÔNG có bộ não riêng.** Web và Telegram gọi cùng một Agent V2
  (`backend/api/agent_v2_routes.py::run_agent_orchestration`). Mọi luật an toàn, guardrail,
  rate limit và doctor-takeover tự động áp dụng cho cả hai — không có đường vòng nào lách qua.
- **Cả bệnh nhân lẫn người thân** đều chat được. Phân quyền dùng lại
  `require_agent_patient_access()` đã có, không xây lớp mới.
- **Production dùng webhook, máy dev dùng polling với bot RIÊNG.** Hai cơ chế loại trừ nhau
  (Telegram trả 409 nếu gọi `getUpdates` khi đã đặt webhook), nên phải tách bot.

## Acceptance Criteria (AC)

### Đợt 1 — Nền tảng

- [ ] `TELEGRAM_UPDATE_MODE` chọn `polling` (mặc định, cho dev) hoặc `webhook` (production).
- [ ] Route `POST /api/v1/telegram/webhook` xác thực bằng `X-Telegram-Bot-Api-Secret-Token`;
      thiếu/sai secret → 403 và KHÔNG xử lý update.
- [ ] Chế độ `webhook` KHÔNG đăng ký job `telegram_updates`; chế độ `polling` KHÔNG mở route
      webhook. Hai bên dùng CHUNG một hàm xử lý update, không copy hai bản.
- [ ] Polling ở dev chạy đủ nhanh để chat được (mặc định 3 giây, cấu hình được).
- [ ] Sửa lỗi dual-role ở `require_agent_patient_access()`: suy vai trò người thân từ
      `caregiver_link` chứ không từ `Account.role`.
- [ ] Lớp "đang hỏi về ai": tài khoản có nhiều hơn một đối tượng thì bot hỏi chọn, nhớ lựa
      chọn theo `chat_id`, có lệnh `/doi` để đổi. Ai chỉ có một vai trò thì không thấy bước này.

### Đợt 2 — Chatbot văn bản

- [ ] Tin nhắn thường → Agent V2 → trả lời trong Telegram, giữ `conversation_id` theo `chat_id`.
- [ ] `suggested_actions` render thành inline keyboard; bấm nút gửi lại đúng `selected_action`.
- [ ] Câu trả lời có nguồn tham khảo khi Agent trả về citations.
- [ ] Dấu hiệu nguy hiểm → tin cảnh báo nổi bật kèm nút gọi 115.
- [ ] Guardrail và rate limit áp dụng y như web.

### Đợt 3 — Ảnh, giọng nói, bác sĩ

- [ ] Ảnh viên thuốc → tải từ Telegram → nhận diện qua đường đã có → trả kết quả + nút xác nhận.
- [ ] Tin thoại → speech-to-text → xử lý như tin văn bản.
- [ ] Bác sĩ tiếp quản: bot im, tin bệnh nhân chuyển cho bác sĩ, tin bác sĩ đẩy về Telegram.

### Đợt 4 — Thông báo

- [ ] Nhắc nhẹ từ người thân (`Nudge`) đẩy sang Telegram bệnh nhân.
- [ ] Tin nhắn bác sĩ đẩy sang Telegram bệnh nhân.
- [ ] Xác nhận uống thuốc + điểm thưởng.
- [ ] Báo cáo tuân thủ hằng tuần cho người thân (backend CHƯA có, phải xây mới).

## Ràng buộc & rủi ro

- **Chi phí LLM tăng.** Mỗi tin Telegram là một lượt Agent V2 y như web. Bot dễ nhắn hơn mở app
  nên lưu lượng nhiều khả năng tăng — rate limit theo `patient_id` đã có sẽ chặn phần lạm dụng.
- **Quyền riêng tư.** Người thân hỏi được về người họ theo dõi là CÓ CHỦ ĐÍCH, đã xác nhận với
  chủ dự án. Chỉ liên kết `accepted` mới được tính (dòng `pending` là lời mời chưa đồng ý).
- **Một tài khoản Telegram = một tài khoản CapyMedi** (`telegram_link.chat_id` UNIQUE). Người
  chăm nhiều bệnh nhân dùng lớp "đang hỏi về ai" để chuyển đối tượng, không cần nhiều Telegram.

## Liên quan

- `backend/services/telegram.py` — tầng gửi/nhận, ghép tài khoản (migration 0057–0060)
- `backend/services/agent_authorization.py` — phân quyền, có lỗi dual-role cần sửa
- `docs/DEPLOY.md` §Telegram bot — hướng dẫn tạo bot và cấu hình
