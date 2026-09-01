# TASK-006: Làm rõ & chốt workflow hệ thống xuyên suốt

**Domain:** `docs`
**Owner:** Cả team (chủ trì: Nguyễn Minh Đạt — Architect · điều phối: Nguyễn Hải Yến — PM)
**Sprint:** sprint-02
**Status:** To Do
**Ưu tiên:** P1

## Mục tiêu (Goal)

Chốt **một** luồng hoạt động xuyên suốt mà cả 4 thành viên hiểu giống nhau: từ lúc bác sĩ duyệt phác đồ → nhắc thuốc → bệnh nhân trả lời/chụp ảnh → phân loại → escalation → dashboard. Hiện mỗi người đang hiểu một phần khác nhau, đây là nguồn rework lớn nhất khi bắt đầu code feature ở Sprint 03.

## Acceptance Criteria (AC)

- [ ] Có **sơ đồ luồng end-to-end** (Mermaid, trong repo — không phải ảnh rời) đi hết từ `prescription approved` → `dose_event` → nhắc 3 cấp → phản hồi bệnh nhân → phân loại → escalation → notification → reporting.
- [ ] Mỗi bước ghi rõ **4 điều**: ai/domain nào chịu trách nhiệm · input · output · contract/event dùng để nói chuyện với bước sau.
- [ ] Vẽ được **các nhánh xấu**, không chỉ happy path: bệnh nhân không trả lời · ảnh không khớp sau 2 lần · safety redflag cắt luồng · RAG không có thông tin về thuốc.
- [ ] Sơ đồ **khớp** với [`/specs/domains.md`](../specs/domains.md) (bảng ranh giới domain + sơ đồ phụ thuộc) và [`/specs/api-contracts.md`](../specs/api-contracts.md) — mâu thuẫn nào tìm thấy phải sửa vào file gốc, không để hai bản khác nhau tồn tại song song.
- [ ] Thể hiện đúng ràng buộc: `safety` **chạy song song** với `conversation` (không nối tiếp), `scheduling` chỉ sinh liều từ phác đồ `approved`.
- [ ] Toàn bộ ô `[CẦN CHỐT]` **chặn Sprint 03** được trả lời và ghi vào [`business-rules.md`](../specs/business-rules.md) — cụ thể tối thiểu: mốc nhắc cấp 2/3, ngưỡng confidence phân loại, SLA escalate MEDIUM, xử lý khi người thân quá SLA 1 giờ.
- [ ] Có **buổi review cả team**, biên bản ghi lại quyết định + người chốt + ngày.
- [ ] Cập nhật [`docs/architecture.md`](../docs/architecture.md) để không còn bản mô tả cũ mâu thuẫn.

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [ ] [`/specs/domains.md`](../specs/domains.md) — ranh giới & sơ đồ phụ thuộc
- [ ] [`/specs/api-contracts.md`](../specs/api-contracts.md) — DTO & event
- [ ] [`/specs/business-rules.md`](../specs/business-rules.md) — mọi ô `[CẦN CHỐT]`
- [ ] [`/specs/features.md`](../specs/features.md) — FEAT-001 → FEAT-011
- [ ] [`/adrs/0007-scheduler-cron-dose-event.md`](../adrs/0007-scheduler-cron-dose-event.md), [`0009`](../adrs/0009-safety-layer-dual-classifier.md), [`0010`](../adrs/0010-human-in-the-loop.md), [`0011`](../adrs/0011-photo-verification-fallback.md)
- [ ] [`docs/architecture.md`](../docs/architecture.md)

## Gợi ý chia subtask (AI tự cập nhật khi bắt đầu)

- [ ] Dựng bản nháp sơ đồ end-to-end từ các file specs/ADR hiện có
- [ ] Lập **danh sách mâu thuẫn** phát hiện được giữa các file (specs vs ADR vs ARCHITECTURE.md)
- [ ] Lập danh sách `[CẦN CHỐT]` chặn Sprint 03, kèm đề xuất sẵn cho từng ô để buổi họp quyết nhanh
- [ ] Vẽ các nhánh xấu
- [ ] Họp team review — chốt từng ô, ghi biên bản
- [ ] Cập nhật `business-rules.md`, `domains.md`, `api-contracts.md`, `ARCHITECTURE.md` theo kết quả chốt
- [ ] Cập nhật `JOURNAL.md` Week 2 với các quyết định

## Definition of Done

Áp dụng checklist chuẩn ở [`ADR-0005`](../adrs/0005-definition-of-done.md). Tiêu chí riêng của task này:

- [ ] **Cả 4 thành viên** xác nhận đã đọc và đồng ý (ghi tên + ngày trong biên bản) — không phải chỉ Architect viết ra rồi coi là chốt
- [ ] Không còn `[CẦN CHỐT]` nào thuộc phạm vi Sprint 03 bị bỏ trống
- [ ] Nếu một quyết định làm đổi ADR đã Accepted → tạo ADR mới thay thế, **không sửa lịch sử** ADR cũ

## Ghi chú / trao đổi thêm

- Đây là task tài liệu nhưng **chặn code**: mỗi ô `[CẦN CHỐT]` còn trống là một chỗ Sprint 03 sẽ phải dừng lại hỏi hoặc đoán sai.
- Rủi ro của sprint có ghi: nếu hết ngày 4 mà `src/` vẫn rỗng thì **đẩy task tài liệu xuống** để ưu tiên [`TASK-003`](./TASK-003-skeleton-fastapi-docker-ci.md). Nếu phải hoãn, vẫn giữ lại phần quyết `[CẦN CHỐT]` — phần này rẻ và chặn nhiều nhất.
- Không mở rộng phạm vi sản phẩm ở task này. Những gì đã cắt khỏi v1 (xem [`backlog.md`](../planning/backlog.md) §"Đã cắt khỏi phạm vi v1") **không** được đưa lại vào sơ đồ.

---
**Điều hướng:** [Sprint 02](../planning/sprints/sprint-02.md) · [Backlog](../planning/backlog.md) · [Tasks](./)
