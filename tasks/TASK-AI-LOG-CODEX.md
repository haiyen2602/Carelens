# TASK-AI-LOG-CODEX: Ghi nhận và gửi AI log của Codex

**Domain:** `infra`
**Owner:** Nguyễn Hải Yến + AI
**Sprint:** Maintenance — 2026-08-27
**Status:** In Progress

## Mục tiêu (Goal)

Cấu hình Codex ghi nhận prompt và hoạt động công cụ vào luồng `.ai-log` hiện có,
sau đó gửi log mới lên grading server khi `git push`. Lịch sử chat có trước thời
điểm kích hoạt phải được giữ cục bộ và không được gửi lên server.

## Acceptance Criteria (AC)

- [x] Codex tự động ghi `UserPromptSubmit`, `PostToolUse` và `Stop` theo schema hook hiện hành.
- [x] Chỉ các bản ghi có thời gian từ mốc kích hoạt trở đi mới đủ điều kiện gửi lên server.
- [x] Các bản ghi cũ hơn mốc kích hoạt không xuất hiện trong payload HTTP và vẫn được lưu trong archive cục bộ.
- [x] API key/token/password phổ biến được che trước khi ghi log.
- [x] `git push` tiếp tục kích hoạt submit qua pre-push hook và không bị chặn khi server log lỗi.
- [x] Có test tự động cho payload Codex, redaction và ranh giới log cũ/mới; test không gọi server thật.

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [x] `AGENTS.md`
- [x] `/specs/`
- [x] `/adrs/0004-project-structure-and-coding-convention.md`
- [x] `/adrs/0005-definition-of-done.md`
- [x] `/specs/api-contracts.md` (đối chiếu; task không thay đổi API sản phẩm)
- [x] `CONVENTIONAL-COMMITS-CHEATSHEET.md`
- [x] Tài liệu OpenAI chính thức về Codex hooks

## Gợi ý chia subtask (AI tự cập nhật khi bắt đầu)

- [x] Chuẩn hóa `.codex/hooks.json` theo schema Codex hiện hành.
- [x] Bổ sung redaction và payload `PostToolUse` cho Codex.
- [x] Thêm mốc kích hoạt cục bộ và lọc submit theo mốc.
- [x] Cập nhật setup/docs và cài hook local.
- [x] Viết, chạy test và kiểm tra không có secret/log cũ trong payload.

## Definition of Done

Áp dụng checklist chuẩn ở [`ADR-0005`](../adrs/0005-definition-of-done.md).

- [x] Không gọi grading server thật trong quá trình kiểm thử.
- [x] Không sửa hoặc xoá archive log lịch sử hiện có.
- [x] Người dùng đã được hướng dẫn trust hook Codex sau khi cấu hình thay đổi.

## Ghi chú / trao đổi thêm

- Người dùng xác nhận AC ngày 2026-08-27.
- Mốc loại trừ lịch sử là state cục bộ trong `.ai-log/`, không commit vào Git.
- Đây là thay đổi tooling cục bộ, không thay đổi kiến trúc sản phẩm hoặc API contract.
- Kiểm tra local: 119 entry cũ, 0 entry đủ điều kiện upload sau khi đặt cutoff.
- Sau khi reset extension, hook Windows lỗi do gọi PowerShell lồng nhau làm `$root` bị
  khai triển sớm; `commandWindows` đã được đổi thành lệnh PowerShell trực tiếp.
- Đã trust lại bằng giao diện `/hooks` của Codex; cả 3 hook đều ở trạng thái `Active`.
- Kiểm tra đầu-cuối không bypass trust ghi đủ `UserPromptSubmit`, `PostToolUse` và `Stop`
  cho session `01a04279-439c-7c12-8d53-09328d118d2a` ngày 2026-08-27.
- `ruff check`, `ruff format --check` và 6 test AI logging đều pass.
