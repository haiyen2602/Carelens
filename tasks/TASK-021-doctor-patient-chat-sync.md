# TASK-021: Đồng bộ hội thoại bác sĩ - bệnh nhân

**Domain:** `conversation`, `notification`
**Owner:** Unassigned + AI
**Sprint:** Unplanned hotfix (không sửa retrospective Sprint 02 đã kết thúc)
**Status:** In Review

## Mục tiêu (Goal)

Hoàn thiện luồng tiếp nhận hội thoại để bác sĩ và bệnh nhân xem cùng một thread
trong lúc bác sĩ đang phụ trách. Bệnh nhân có thể chủ động dừng; hệ thống cũng
tự dừng phiên sau 10 phút không có tin nhắn mới từ bệnh nhân.

## Acceptance Criteria (AC)

- [ ] Khi handoff `ACTIVE`, tin nhắn của bệnh nhân và bác sĩ được lưu một lần,
  trả về đúng thứ tự thời gian, và hiện ở cả hai giao diện mà không cần tải lại
  trang thủ công.
- [ ] Bác sĩ xem được lịch sử câu hỏi và phản hồi của chatbot thuộc đúng
  `conversation_id` của handoff, theo thứ tự thời gian, trước và trong khi trao
  đổi trực tiếp với bệnh nhân.
- [ ] Bệnh nhân thấy nút **"Dừng trò chuyện"** khi handoff `ACTIVE`; chỉ chính
  bệnh nhân của handoff được dừng, thao tác lặp lại an toàn. Khi bác sĩ dừng,
  cả hai giao diện hiện **"Bác sĩ xin dừng cuộc trò chuyện tại đây"**; khi bệnh
  nhân dừng, cả hai giao diện hiện **"Bệnh nhân xin dừng cuộc trò chuyện tại đây"**.
- [ ] Một handoff `ACTIVE` tự dừng sau 10 phút kể từ tin nhắn bệnh nhân gần
  nhất. Tác vụ quét có thể chạy lặp lại mà không tạo thông báo dừng trùng.
- [ ] Mọi endpoint mới kiểm tra xác thực, role và quan hệ với bệnh nhân; không
  lộ thread hay lịch sử chatbot của người khác.
- [ ] Có test API/service/frontend cần thiết cho đồng bộ hai chiều, lịch sử
  chatbot, bệnh nhân dừng và timeout 10 phút.

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [x] `AGENTS.md`
- [x] `/specs/features.md`, `/specs/user-roles.md`, `/specs/business-rules.md`, `/specs/domains.md`
- [x] `/specs/api-contracts.md`
- [x] `/adrs/0001-test-strategy.md`, `/adrs/0002-domain-split.md`, `/adrs/0003-api-contract-first.md`, `/adrs/0004-project-structure-and-coding-convention.md`, `/adrs/0005-definition-of-done.md`, `/adrs/0006-tech-stack.md`

## Gợi ý chia subtask

- [ ] Chốt contract và mô hình dữ liệu/timeout của handoff.
- [ ] Bổ sung backend: history an toàn, bệnh nhân dừng, timeout idempotent.
- [ ] Đồng bộ giao diện bác sĩ và bệnh nhân; hiển thị lịch sử chatbot cho bác sĩ.
- [ ] Viết/rà test, lint và build.

## Definition of Done

Áp dụng checklist chuẩn ở [`ADR-0005`](../adrs/0005-definition-of-done.md).

- [ ] Contract và lịch sử thay đổi được cập nhật, có reviewer domain.
- [ ] Không thay đổi production, không merge và không commit dữ liệu bệnh nhân.

## Ghi chú / trao đổi thêm

Task được người dùng cho phép tạo ngày 2026-08-30 để xử lý lỗi production.
Repository chỉ còn file Sprint 01/02 mang tính lịch sử, nên task được đánh dấu
unplanned hotfix thay vì sửa retrospective của Sprint 02.
