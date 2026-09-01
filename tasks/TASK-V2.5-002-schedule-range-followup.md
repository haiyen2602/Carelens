# TASK-V2.5-002: Follow-up "các ngày còn lại thì sao" (range anaphora)

**Domain:** Agent V2 read-only schedule/evidence — capability context/follow-up
**Owner:** Dyo31122005 + AI
**Sprint:** V2.5 timebox — chưa gán sprint chung
**Status:** To Do — baseline chốt xong ở CP1, chưa code

## Mục tiêu

Khi người dùng đã hỏi một khoảng thời gian nhiều ngày (vd "tuần tới tôi có
lịch uống thuốc không?") rồi hỏi tiếp một câu chỉ tham chiếu phần còn lại
của khoảng đó (vd "các ngày còn lại thì sao?", không tự nêu lại ngày/tuần),
Agent V2 hiện **không kế thừa** khoảng thời gian đã hỏi trước đó — misroute
sang hỏi y khoa chung. Task này làm nó nhận đúng đây là follow-up về lịch,
không phải chủ đề y khoa mới.

Đây là task đầu tiên của capability **context/follow-up** (một trong ba
capability production của V2.5 — xem
[V2.5-DESIGN.md](../chat-bot-build/chatbot-v2_5/V2.5-DESIGN.md) mục 9). Phát
hiện trong lúc reproduce TASK-V2.5-001, không phải suy diễn từ sheet gốc.

## Baseline / reproduction (đã xác nhận, 2026-09-01)

```python
from datetime import datetime, UTC
from backend.agents.v2.orchestrator import classify_intent

now = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)
d = classify_intent("các ngày còn lại thì sao", now=now)
# Hiện tại: intent=GENERAL_MEDICAL_INFORMATION, time_range=None
# Kỳ vọng: nhận diện đây là schedule follow-up, không phải topic y khoa mới
```

`classify_intent`/`resolve_time_query` không có khái niệm "range đã hỏi ở
lượt trước" — mỗi lượt được resolve độc lập từ chính message đó. Câu này
không chứa bất kỳ time-phrase nào `resolve_time_query` nhận diện được, nên
rơi vào nhánh `_display_topic_from_raw`/`_GENERAL_MEDICAL_KEYWORDS` (câu
"X thì sao" khớp pattern topic-switch chung).

`ConversationState` (`backend/agents/v2/conversation_state.py`) hiện chỉ có
`active_topic`/`active_entity` — **không có field nào lưu range/thời điểm đã
hỏi ở lượt trước.** Đây là câu hỏi thiết kế cần chốt trước khi code (xem
"Câu hỏi cần chốt" bên dưới), không phải chi tiết nhỏ có thể tự quyết khi
code.

## Acceptance Criteria (AC)

- [ ] Câu hỏi thiết kế đã chốt: lưu "range/lượt lịch gần nhất" ở đâu — thêm
  field durable mới vào `ConversationState` (cùng vòng đời với
  `active_topic`/`active_entity`), hay dùng `ShortTermMemoryStore` (bounded,
  không durable) là đủ? Ảnh hưởng migration/schema nên phải quyết trước khi
  build, không quyết ngầm trong lúc code.
- [ ] Test tái tạo chính xác baseline ở trên như một red test trước khi sửa.
- [ ] `classify_follow_up`/`classify_intent` nhận diện được câu chỉ tham
  chiếu "phần còn lại" của một range lịch đã hỏi (không tự nêu lại
  ngày/tuần) khi có range gần nhất còn hợp lệ trong state.
- [ ] Khi có range trước đó: trả đúng phần còn lại (từ hôm nay hoặc từ ngày
  cuối đã trả lời tới hết range cũ) qua `get_doses_for_range` — không suy
  đoán ngày mới, không tự bịa range.
- [ ] Khi không có range trước đó (session mới/hết hạn): dùng
  `NEED_MORE_INFO`/clarification tự nhiên đã có (Answerability Gate,
  `answerability.py`) — không mặc định thành `GENERAL_MEDICAL_INFORMATION`.
- [ ] Entity chưa xác minh không được promote thành truth (theo Phase 2 scope
  chung, V2.5-DESIGN.md mục 9) — range cũ chỉ dùng để tính lại range mới,
  không tự ý mở rộng phạm vi ngoài những gì user đã thực sự hỏi.
- [ ] Golden/regression: thêm case này vào
  `scripts/agent_v2/golden/golden_set_v2.json` hoặc file V2.5 riêng; chạy
  lại toàn bộ `tests/test_agent_v2_time_aware_schedule.py` (36/36 hiện tại)
  và golden `--deterministic-only` (15/15 hiện tại) không suy giảm.
- [ ] Capability flag `AGENT_V2_5_FOLLOWUP_ENABLED` (đề xuất ở
  `CP0-ADR-BASELINE-TASK01.md` mục 1.7), mặc định **off**, theo đúng CP1 của
  `CHECKPOINT.md`.

## Context bắt buộc phải đọc trước khi làm

- [ ] `AGENTS.md`
- [ ] `chat-bot-build/chatbot-v2_5/V2.5-DESIGN.md` (mục 9, Phase 2)
- [ ] `chat-bot-build/chatbot-v2_5/CP0-ADR-BASELINE-TASK01.md` (Pain point 3,
  mục 1.7)
- [ ] `tasks/TASK-V2.5-001-schedule-tool-contract.md` (vì sao task này tách
  ra từ đó)
- [ ] `backend/agents/v2/time_query_engine.py`, `backend/agents/v2/follow_up.py`
  (`classify_follow_up`), `backend/agents/v2/conversation_state.py`,
  `backend/agents/v2/orchestrator.py` (`classify_intent`, `_schedule_reply`)
- [ ] `tests/test_agent_v2_time_aware_schedule.py`

## Gợi ý chia subtask

- [ ] Chốt câu hỏi thiết kế (durable field vs short-term memory) — có thể
  cần một ADR-mini riêng nếu đụng schema `ConversationState`/migration mới.
- [ ] Viết red test tái tạo baseline.
- [ ] Implement nhận diện + resolve "phần còn lại" (không đổi domain
  semantics của `get_doses_for_range`).
- [ ] Thêm case NEED_MORE_INFO khi không có range trước đó.
- [ ] Golden/regression, ruff, cập nhật task + CP0 doc + CHECKPOINT bảng theo
  dõi thực thi trước PR.

## Definition of Done

Áp dụng [ADR-0005](../adrs/0005-definition-of-done.md): local test/build
pass, golden suite không suy giảm, capability flag off theo mặc định, PR
review theo CP1–CP3 của `CHECKPOINT.md`. Rollback: tắt
`AGENT_V2_5_FOLLOWUP_ENABLED`, sau đó revert PR nếu cần.

## Không thuộc phạm vi

- Không xử lý entity-ellipsis (TR02/TR15 — "thông tin chi tiết"/"tác dụng
  phụ" không nêu lại tên thuốc, giữ 2 sản phẩm cạnh tranh) — đó là pain point
  1 riêng, có thể thành task kế tiếp trong cùng capability nhưng không gộp
  vào đây để tránh task quá rộng.
- Không build `ModelRole.RENDERER`/`RenderableFactSlots` — Task 04.
- Không sửa Safety Domain/emergency/triage.
- Không đổi domain semantics của `get_doses_for_range` (giới hạn range,
  cách bucket theo local date) — chỉ đổi cách router/state resolve range đầu
  vào cho tool này.

## Ghi chú / trao đổi thêm

Task này tách ra từ TASK-V2.5-001 sau khi reproduction cho thấy bug gốc của
task đó (mâu thuẫn lượt 5/6) không còn tồn tại, nhưng phát hiện một gap thật
khác trong cùng cụm test (TR01). Không gộp chung một task để giữ mỗi task có
thể rollback độc lập theo đúng nguyên tắc CP1 (`CHECKPOINT.md`).
