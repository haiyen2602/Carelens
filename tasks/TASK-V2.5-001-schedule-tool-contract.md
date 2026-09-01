# TASK-V2.5-001: Sửa contract lịch/liều nhiều lượt

**Domain:** Agent V2 read-only schedule/evidence
**Owner:** Dyo31122005 + AI
**Sprint:** V2.5 timebox — chưa gán sprint chung
**Status:** Ready

## Mục tiêu

Tái tạo và sửa tại gốc lỗi lịch ngày cụ thể trả trùng kết quả với “hôm nay”,
đồng thời tạo contract `RenderableFactSlots` tối thiểu cho fact lịch/liều.
Task này không thay tone, model, Safety Domain hoặc API public.

## Acceptance Criteria

- [ ] Có test tái tạo câu hỏi “hôm nay” và “ngày 30/8” ở hai lượt khác nhau,
  xác định route `classify_intent`/`resolve_time_query` gây kết quả trùng.
- [ ] Sửa contract mismatch tại gốc, không patch theo một ngày cụ thể; hai
  lượt trả đúng fact theo date/range đã được backend resolve.
- [ ] “Các ngày còn lại thì sao” trả đúng phần còn lại của `TimeRange`, hoặc
  `NEED_MORE_INFO` rõ ràng khi thiếu context; không trả `FAILED/TOOL_ERROR`.
- [ ] Định nghĩa `RenderableFactSlots` tối thiểu cho `schedule` và
  `dose_status` trong request boundary; chưa nối vào renderer.
- [ ] Không đổi domain semantics, không clamp/retry âm thầm và không đổi API
  public.
- [ ] Trước và sau thay đổi, chạy cùng golden suite ở local. Report kết quả
  baseline/candidate phải có commit SHA, timestamp, exact command,
  config/model version và golden-set version; tab production V1 15/08/2026
  chỉ là evidence lịch sử, không phải baseline V2.
- [ ] Regression schedule/dose-status (`TODAY_DOSES`, `UPCOMING_DOSES`,
  `MEDICATION_HISTORY`) không suy giảm.

## Context bắt buộc phải đọc trước khi làm

- [ ] `AGENTS.md`
- [ ] `specs/product-vision.md`, `specs/business-rules.md`,
  `specs/api-contracts.md`
- [ ] `adrs/0001-test-strategy.md`, `adrs/0003-api-contract-first.md`,
  `adrs/0004-project-structure-and-coding-convention.md`,
  `adrs/0005-definition-of-done.md`
- [ ] `chat-bot-build/chatbot-v2_5/V2.5-DESIGN.md`
- [ ] `chat-bot-build/chatbot-v2_5/CP0-ADR-BASELINE-TASK01.md`
- [ ] `backend/agents/v2/time_query_engine.py`, relevant orchestrator and
  golden-evaluation modules

## Gợi ý chia subtask

- [ ] Chạy golden suite hiện tại ở local và lưu baseline de-identified.
- [ ] Viết reproduction tests cho date/range và follow-up phạm vi còn lại.
- [ ] Sửa logic/contract tại gốc, thêm fact-slot skeleton và unit tests.
- [ ] Chạy lint, targeted tests, regression/golden suite; cập nhật report,
  task và worklog trước PR.

## Definition of Done

Áp dụng [ADR-0005](../adrs/0005-definition-of-done.md), đặc biệt local test,
`ruff`, golden evidence, privacy-safe logs, PR review và CI pass. Rollback là
revert PR Task 01; không đổi Railway config hay capability flag trong task này.

## Không thuộc phạm vi

- Không build `ModelRole.RENDERER`; đây là Task 04 sau benchmark và gate riêng.
- Không sửa emergency, triage hoặc Safety Domain. Investigation triệu chứng
  cấp tính chạy độc lập theo CP0.
- Không enable OCR/VLM hoặc deploy Railway trong Task 01.
