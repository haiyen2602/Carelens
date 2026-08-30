# TASK-DOCTOR-REVIEW-UX: Tối ưu hàng đợi và workspace tư vấn bác sĩ

**Domain:** Frontend bác sĩ / Doctor Handoff
**Owner:** Nguyễn Hải Yến + AI
**Sprint:** To be assigned
**Status:** In Progress

## Mục tiêu (Goal)

Sắp xếp lại hai màn hình BUILD-44 để bác sĩ nhận ca, đọc đúng ngữ cảnh, trao đổi và kết thúc
handoff nhanh hơn mà không thay đổi chính sách an toàn hay phân công hiện có.

Quy tắc sản phẩm đã được PM xác nhận ngày 2026-08-27:

- Hộp cảnh báo/chuông thông báo tiếp tục lọc theo `DoctorWatch`.
- Handoff chatbot ưu tiên bác sĩ phụ trách; khi không xác định được bác sĩ phụ trách thì vào hàng
  đợi chung để một bác sĩ đang hoạt động nhận.

## Acceptance Criteria (AC)

- [x] Hàng đợi phân biệt rõ loại handoff, trạng thái, ca của tôi và ca chung; không tạo thêm đánh
  giá y khoa ở frontend.
- [x] Bác sĩ có thao tác theo state machine: nhận ca, bắt đầu trao đổi, kết thúc hoặc huỷ ca; mọi
  thao tác kết thúc đều yêu cầu xác nhận.
- [x] Hàng đợi có lọc đầy đủ trạng thái terminal và sắp xếp Ưu tiên an toàn/Mới nhất/Cũ nhất.
- [x] Bộ lọc có nhãn truy cập được, có tìm kiếm, trạng thái tải/lỗi/rỗng rõ ràng và thao tác nhận ca
  đưa bác sĩ thẳng vào workspace.
- [x] Polling nền khi `ACTIVE` không thay toàn bộ trang bằng loading, không làm mất focus hoặc nội
  dung bác sĩ đang soạn.
- [x] Workspace có luồng tin nhắn dễ đọc, tự cuộn có kiểm soát, composer cố định và không gửi nhầm
  khi bộ gõ tiếng Việt đang composition.
- [x] “Kết thúc trao đổi” có xác nhận và giải thích rằng chatbot sẽ tiếp tục hỗ trợ ở lượt sau.
- [x] Ảnh riêng tư đã có trong contract BUILD-44/B-07 được hiển thị qua proxy có Authorization;
  không dùng URL công khai hoặc bỏ qua kiểm tra bác sĩ được phân công.
- [x] Giao diện responsive, có trạng thái focus/aria phù hợp và dùng design token/component hiện có.
- [ ] Có frontend contract test cho các hành vi quan trọng; ESLint, TypeScript và Next build pass.
  - Contract test, lint các file thay đổi, TypeScript và Next build: pass.
  - `npm run lint` toàn dự án: blocked bởi 31,747 lỗi CRLF tồn tại trên file ngoài scope task.
- [x] Bộ test backend Doctor Handoff liên quan vẫn pass, không đổi contract hoặc chính sách
  `DoctorWatch`/Safety.

## Context bắt buộc phải đọc trước khi làm

- [x] `AGENTS.md`
- [x] `/specs/product-vision.md`
- [x] `/specs/user-roles.md`
- [x] `/specs/business-rules.md`
- [x] `/specs/api-contracts.md`
- [x] `/adrs/0004-project-structure-and-coding-convention.md`
- [x] `/adrs/0005-definition-of-done.md`
- [x] `/adrs/0010-human-in-the-loop.md`
- [x] `chat-bot-build/build_cai_thien/BUILD-44-DOCTOR-CHAT-QUEUE-TAKEOVER-REPORT.md`
- [x] `CONVENTIONAL-COMMITS-CHEATSHEET.md`

## Subtask

- [x] Audit code, contract, phân quyền và test hiện có.
- [x] Thiết kế lại trang hàng đợi.
- [x] Thiết kế lại workspace và xử lý polling/composer.
- [x] Bổ sung thao tác huỷ ca, trạng thái terminal và sắp xếp hàng đợi.
- [x] Nối hiển thị ảnh riêng tư.
- [x] Viết frontend contract test, chạy scoped lint, TypeScript, Next build và regression backend.

## Definition of Done

Áp dụng checklist chuẩn ở [`ADR-0005`](../adrs/0005-definition-of-done.md). Không merge hoặc deploy
trong task này; reviewer frontend bắt buộc là Nguyễn Hải Yến.

## Ghi chú

- Browser trong ứng dụng không khả dụng ở đầu task; phải ghi rõ nếu visual click/screenshot vẫn
  không thể chạy ở quality gate cuối.
- Worktree có thay đổi AI-log từ trước; task này chỉ sửa các file doctor review, proxy/test liên quan
  và file task này.
- Kiểm thử 2026-08-27: `npm run test:doctor-reviews` pass; scoped ESLint pass; `tsc --noEmit`
  pass; `npm run build` pass; 27 regression Doctor Handoff pass trong container backend.
- Cập nhật 2026-08-27: contract test, scoped ESLint và `tsc --noEmit` tiếp tục pass sau khi thêm
  thao tác huỷ ca và sắp xếp. Next build đang bị khoá bởi một tiến trình build khác trong môi trường.
