# TASK-V2.5-001: Discovery — mâu thuẫn lịch ngày cụ thể (đóng, không cần runtime change)

**Domain:** Agent V2 read-only schedule/evidence
**Owner:** Dyo31122005 + AI
**Sprint:** V2.5 timebox — chưa gán sprint chung
**Status:** Done — discovery closure, không có thay đổi runtime

## Mục tiêu

Ban đầu: tái tạo và sửa tại gốc lỗi lịch ngày cụ thể trả trùng kết quả với
"hôm nay" (evidence gốc: golden sheet, cụm TR01 row ~108). Sau khi
reproduction thật trên code hiện tại, kết luận: **bug này đã được BUILD-27B/28
sửa từ trước** — không tồn tại trên nhánh này. Task đóng dưới dạng discovery
closure: xác nhận bằng evidence, không viết code cho một bug không còn tồn
tại, và không tạo abstraction (`RenderableFactSlots`) chưa có consumer thật.

## Acceptance Criteria (đã đổi từ AC gốc — xem lý do ở "Ghi chú")

- [x] Có test/reproduction tái tạo case "hôm nay" (PRESENT) vs "ngày cụ thể
  trong tương lai" (FUTURE, dạng "ngày 30 tháng 8"/"ngày 25/08") ở cùng một
  mốc `now` cố định, xác nhận hai lượt trả **khác kết quả và đúng** — không
  còn mâu thuẫn.
- [x] Xác nhận route/contract hiện tại (`classify_intent` →
  `resolve_time_query` → `_schedule_reply` → `set_resolved_date_range` →
  `get_doses_for_range`) thread đúng `start_date`/`end_date` theo từng lượt,
  không rơi lại "hôm nay" mặc định.
- [x] Xác nhận **đã có sẵn** regression test bảo vệ đúng case này
  (`tests/test_agent_v2_time_aware_schedule.py:89`,
  `"ngày 25/08 tôi uống thuốc gì?"` → `UPCOMING_DOSES`,
  `(2026-08-25, 2026-08-25)`, khác với case "Hôm nay" ở dòng 85) — **giữ
  nguyên test này như regression bảo vệ fix cũ của BUILD-27B/28, không gắn
  nhãn nó là "fix V2.5 mới".**
- [x] Chạy toàn bộ `tests/test_agent_v2_time_aware_schedule.py`: 36/36 PASS.
- [x] Chạy baseline golden suite (`--deterministic-only`) trước khi kết
  luận: 15/15 PASS, commit `7429c32d`, artifact
  `scripts/agent_v2/golden/runs/20260901T055851Z.json`.
- [x] Xử lý và ghi nhận blocker môi trường phát hiện trong lúc chạy baseline:
  local Postgres ở migration `0062`, code cần head `0063`
  (`0063_agent_run_follow_up_observability.py`, cột
  `agent_run.follow_up_category` v.v. từ BUILD-47) — đã chạy
  `alembic upgrade head` cục bộ, không phải bug V2.5, không phải thay đổi
  schema mới do task này tạo ra.
- [ ] ~~Sửa contract mismatch tại gốc~~ — không áp dụng, bug không tồn tại.
- [ ] ~~Định nghĩa `RenderableFactSlots` tối thiểu~~ — **dời sang Task 04**
  (renderer), nơi nó có consumer thực tế đầu tiên. Không tạo abstraction
  chưa dùng trong timebox hai sprint.
- [ ] ~~"Các ngày còn lại thì sao" phải không còn `FAILED/TOOL_ERROR`~~ —
  reproduction thật cho thấy nhãn lỗi thực tế khác với sheet: route hiện tại
  là `GENERAL_MEDICAL_INFORMATION` (không phải crash `TOOL_ERROR`), vì router
  không có cơ chế kế thừa range đã hỏi trước đó. Đây là lỗi
  follow-up/context, không phải tool/evidence — **chuyển sang
  TASK-V2.5-002.**

## Context bắt buộc phải đọc trước khi làm

- [x] `AGENTS.md`
- [x] `chat-bot-build/chatbot-v2_5/V2.5-DESIGN.md`
- [x] `chat-bot-build/chatbot-v2_5/CP0-ADR-BASELINE-TASK01.md`
- [x] `backend/agents/v2/time_query_engine.py`, `backend/agents/v2/orchestrator.py`
  (`_schedule_reply`, `classify_intent`), `backend/agents/v2/tools.py`
  (`_require_resolved_date_range`), `backend/services/agent_read_only_tools.py`
  (`get_doses_for_range`)
- [x] `tests/test_agent_v2_time_aware_schedule.py`

## Definition of Done

Áp dụng [ADR-0005](../adrs/0005-definition-of-done.md) theo hình dạng discovery
closure: không có diff runtime code để review, nhưng có đủ evidence
(golden run artifact, pytest output, migration log) và task/CP0 doc đã cập
nhật trạng thái + lý do đóng. Rollback: N/A — không đổi Railway config,
không đổi capability flag, không đổi code sản xuất.

## Không thuộc phạm vi

- Không build `ModelRole.RENDERER` hay `RenderableFactSlots` — Task 04, sau
  benchmark và gate riêng.
- Không sửa emergency, triage hoặc Safety Domain. Investigation triệu chứng
  cấp tính chạy độc lập theo CP0 (Phần 3, CP0-ADR-BASELINE-TASK01.md).
- Không xử lý "các ngày còn lại thì sao" — chuyển sang TASK-V2.5-002.
- Không chọn pain point khác (vd "vitamin b1" ≥5 SKU trùng tên, row 8 sheet)
  làm mục tiêu thay thế lúc này — chưa có reproduction/evidence mới trên code
  hiện tại; để lại backlog cho task riêng nếu cần.

## Ghi chú / trao đổi thêm

**Vì sao AC gốc bị đổi:** Task này được tạo từ evidence trong một golden
sheet (Google Sheets, xem CP0 doc) gắn nhãn "V2: FAILED/TOOL_ERROR"/
"hai lượt mâu thuẫn là lỗi" cho cụm TR01. Trước khi viết code sửa, task này
tự yêu cầu reproduction trên code **hiện tại** (không phải version sheet mô
tả) — reproduction cho thấy:

1. `resolve_time_query`, `_schedule_reply`, và toàn bộ chuỗi tool-threading
   đã đúng (kiểm tra trực tiếp qua Python REPL với `today` cố định trước
   ngày explicit date được hỏi).
2. Test `test_time_phrases_route_and_bound_correctly` đã có sẵn case tương
   đương từ trước (không phải test này tự viết mới) và đang pass.
3. Do đó: **không viết lại code cho bug không còn tồn tại** — quyết định của
   owner, ưu tiên tránh sửa những gì không hỏng hơn là tạo bằng chứng "đã
   làm việc" giả.

Hai phát hiện thật còn lại từ cùng cụm TR01 được tách khỏi task này:
- "các ngày còn lại thì sao" → misroute thành `GENERAL_MEDICAL_INFORMATION`
  → chuyển thành baseline cho **TASK-V2.5-002** (context/follow-up).
- "Tôi đã hỏi những vấn đề gì" → `UNKNOWN_OR_AMBIGUOUS`/honest-decline đúng
  boundary, vì Agent V2 không có tool đọc lại lịch sử hội thoại trong danh
  sách 6 tool cho phép. **Không phải bug, không biến thành requirement mới**
  — ghi nhận là giới hạn năng lực có chủ đích, không phải lỗi cần sửa.
