# TASK-V2.5-002: Follow-up "các ngày còn lại thì sao" (range anaphora)

**Domain:** Agent V2 read-only schedule/evidence — capability context/follow-up
**Owner:** Dyo31122005 + AI
**Sprint:** V2.5 timebox — chưa gán sprint chung
**Status:** In Progress — CP1 gần xong; còn chờ quyết định branch (xem mục CP1) trước khi sang CP2

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
`active_topic`/`active_entity` — không có field nào lưu range/thời điểm đã
hỏi ở lượt trước.

## Quyết định thiết kế đã chốt (owner, 2026-09-01)

**Phương án A: `active_schedule_range` durable trên `ConversationState`.**
Không cần migration DB — state đã nằm trong `AgentRun.metadata_json`
(`backend/services/agent_conversation_state.py`), thêm field chỉ là thêm key
JSON. Bump `as_dict()`/`from_dict()` **version 5 → 6**, theo đúng convention
đã có cho `answerability_attempt_count` (BUILD-42): field mới đọc `None`/thiếu
trên state cũ mà không lỗi, không suy ra giá trị giả (`conversation_state.py:224-237`).

**Shape lưu (tối giản, do backend tạo — không lưu raw message):**

```python
active_schedule_range: tuple[date, date] | None  # (start_date, end_date)
```

**Không lưu `last_served_through_date`.** Xác nhận bằng code:
`_build_schedule_reply` (`orchestrator.py:1404-1485`) luôn trả **toàn bộ**
`time_range` trong một lần — khi số dose ≤ `_MAX_DETAIL_ROWS` (30) liệt kê
từng dose, khi vượt thì gộp theo ngày (dòng 1462-1484), nhưng **không ngày
nào trong range bị bỏ sót hay để dành cho lượt sau**. Ground-truth sheet
(STT 111) cũng viết "'các ngày còn lại' = phần còn lại **của khung** tuần
sau", tức trong phạm vi range đã lập, không phải phần "chưa được trả".
**Nghĩa của "còn lại":** follow-up chỉ cần re-resolve đúng
`active_schedule_range` đã lưu và gọi lại `_schedule_reply` với range đó —
hàm này đã tự tính due/upcoming theo `now` hiện tại (dòng 1433-1451), nên nếu
có thời gian trôi qua giữa hai lượt, câu trả lời tự nhiên đã phản ánh đúng
"còn lại" mà không cần thêm state.

**Staleness (an toàn theo mặc định) — `active_schedule_range` chỉ hợp lệ cho
đúng lượt kế tiếp:**
- Set khi một lượt schedule đa ngày (TODAY_DOSES/UPCOMING_DOSES/
  MEDICATION_HISTORY với range > 1 ngày) resolve xong.
- **Consume** (dùng rồi xoá) ngay khi lượt kế tiếp là follow-up "phần còn
  lại" hợp lệ.
- **Overwrite** khi lượt kế tiếp là một câu hỏi schedule mới (range mới thay
  thế range cũ).
- **Clear** (không dùng, không giữ) khi lượt kế tiếp là: đổi chủ đề
  (`TOPIC_SWITCH`/entity mới), có safety trigger hoặc handoff, hoặc bất kỳ
  intent nào không phải follow-up lịch.
- Tổng quát: không có state nào sống quá một lượt kế tiếp, dù lượt đó có
  dùng tới nó hay không.

**Khi không có `active_schedule_range` hợp lệ:** trả `NEED_MORE_INFO` qua
Answerability Gate (`answerability.py`) — **không** rơi vào
`GENERAL_MEDICAL_INFORMATION` như hiện tại.

## Acceptance Criteria (AC)

- [ ] Test tái tạo chính xác baseline ở trên như một red test trước khi sửa.
- [ ] Thêm field `active_schedule_range: tuple[date, date] | None` vào
  `ConversationState`; bump `as_dict`/`from_dict` lên version 6.
- [ ] **Test đọc ngược state version 5** (không có field mới) qua
  `from_dict`: phải trả về `active_schedule_range=None`, không lỗi, không
  suy ra giá trị giả — theo đúng convention `answerability_attempt_count`
  đã có, nhưng đây là test mới (chưa có test tương đương cho field này trong
  `tests/test_agent_v2_conversation_state.py`).
- [ ] `classify_follow_up`/`classify_intent` nhận diện được câu chỉ tham
  chiếu "phần còn lại" của một range lịch đã hỏi (không tự nêu lại
  ngày/tuần) khi `active_schedule_range` còn hợp lệ.
- [ ] Khi có range hợp lệ: re-resolve đúng `active_schedule_range` đó và gọi
  lại `_schedule_reply`/`get_doses_for_range` — không suy đoán ngày mới,
  không tự bịa range, không cần `last_served_through_date`.
- [ ] Khi không có range hợp lệ: `NEED_MORE_INFO` qua Answerability Gate —
  không mặc định thành `GENERAL_MEDICAL_INFORMATION`.
- [ ] Cài đúng 4 quy tắc staleness ở trên (consume/overwrite/clear theo đổi
  chủ đề-safety-handoff/clear theo intent khác) bằng unit test riêng cho
  từng trường hợp.
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

## CP1 — Sẵn sàng implementation (theo `CHECKPOINT.md`, áp cho đúng shape Task 02)

Task 02 không đụng renderer/`ResponsePolicy`/`RenderableFactSlots` (đó là
Task 04), nên một số mục CP1 gốc không áp dụng nguyên văn — ghi rõ N/A kèm lý
do thay vì bỏ qua im lặng.

- **Branch:** _chưa tạo — xem mục "Quyết định cần bạn xác nhận" bên dưới,
  có rủi ro stacked-branch cần quyết trước khi tạo._
- **Liên kết task/ADR/pain point/source:** đã có — `CP0-ADR-BASELINE-TASK01.md`
  mục 1.3a + Pain point 3, `TASK-V2.5-001` (lý do tách task), và source
  `time_query_engine.py`/`follow_up.py`/`conversation_state.py`/
  `orchestrator.py` (đã liệt kê ở mục Context bên dưới).
- **`ResponsePolicy`/`RenderableFactSlots`/audit metadata tách biệt:** N/A —
  Task 02 không tạo prose tự do, không gọi renderer. Phần tương đương duy
  nhất: `active_schedule_range` (chỉ `start_date`/`end_date`) là dữ liệu nội
  bộ trong `ConversationState`/`AgentRun.metadata_json`, cùng lớp riêng tư
  với `active_topic`/`active_entity` đã có — không phải audit/telemetry mới,
  không chứa raw message, không chứa PHI ngoài phạm vi ngày tháng đã chấp
  nhận từ trước.
- **Fact nhạy cảm phải backend-render:** vẫn đúng nguyên tắc nhưng không có
  gì mới — lịch/liều tiếp tục được compose bởi `_build_schedule_reply`
  (deterministic, đã có từ BUILD-28), Task 02 chỉ đổi ROUTE tới đúng range,
  không đổi cách render fact.
- **Deterministic fallback:** không có renderer nên không có
  "timeout/invalid renderer output". Fallback tương đương của Task 02: nếu
  `active_schedule_range` không hợp lệ/hết hạn → `NEED_MORE_INFO` (đã định
  nghĩa ở AC); nếu tool `get_doses_for_range` raise `ToolExecutionError` khi
  re-resolve → dùng lại đúng path `_fail_closed(..., "DOSE_SCHEDULE_UNAVAILABLE", ...)`
  đã có ở `_schedule_reply`, không tạo path fail-closed mới.
- **Test plan** (thay cho yêu cầu "prose tự do" — N/A vì không có renderer):
  - Unit: `classify_follow_up`/hàm nhận diện mới cho pattern "còn lại của
    range đã lập" — case dương (có range hợp lệ) và âm (không có/hết hạn).
  - Unit: 4 nhánh staleness — consume-after-use, overwrite-by-new-query,
    clear-on-topic-switch, clear-on-safety-or-handoff, clear-on-other-intent
    (5 test, không phải 4, vì "đổi chủ đề" và "safety/handoff" là hai
    nguyên nhân riêng dù cùng hành vi clear).
  - Unit: `ConversationState.from_dict` đọc state version 5 (thiếu
    `active_schedule_range`) → trả `None`, không lỗi (test mới, xem AC).
  - Golden/regression: case TR01 lượt 8→9 ("tuần tới..." → "các ngày còn lại
    thì sao") thêm vào golden set V2.5; chạy lại
    `tests/test_agent_v2_time_aware_schedule.py` (36/36),
    `tests/test_agent_v2_conversation_state.py` (14/14), và golden
    `--deterministic-only` (15/15) — baseline "trước" đã chốt ở dưới.
  - Local E2E: replay đúng chuỗi TR01 lượt 5→9 bằng dữ liệu tổng hợp
    (không PHI) qua orchestrator thật.
- **Baseline local (trước khi code Task 02), commit `a75b0c8`:**
  - `python scripts/agent_v2/run_golden_evaluation.py --deterministic-only`
    → 15/15 PASS, artifact `scripts/agent_v2/golden/runs/20260901T062931Z.json`.
  - `python -m pytest tests/test_agent_v2_time_aware_schedule.py -q` →
    36/36 PASS.
  - `python -m pytest tests/test_agent_v2_conversation_state.py -q` →
    14/14 PASS (baseline cho phần `ConversationState` version bump).
  - Environment: local; model/config: N/A (toàn bộ case deterministic, không
    gọi model thật).
  - **Chưa ghi vào tab V2.5 của golden sheet** (CHECKPOINT.md CP1, mục ghi
    baseline) — tôi không có quyền ghi Google Sheets từ phiên này; nội dung
    dòng cần dán nằm ở cuối mục này, bạn tự dán hoặc cho tôi biết cách ghi
    trực tiếp nếu có.
- **Capability flag:** `AGENT_V2_5_FOLLOWUP_ENABLED`, mặc định `false`, owner
  Dyo31122005, cohort rỗng (chưa canary) — khai báo tên/mặc định ở đây; thêm
  thật vào `backend/config.py`/`.env.example` là việc của CP2 (build), không
  phải CP1.
- **Rollback:** revert PR Task 02; tắt `AGENT_V2_5_FOLLOWUP_ENABLED` nếu đã
  kịp bật ở bất kỳ đâu (chưa, vì chưa build). Không đổi Railway config.

**Dòng dán vào tab V2.5 golden sheet (theo cấu trúc tab 15/08/2026):**

```
timestamp: 2026-09-01T06:29:31Z
commit: a75b0c8dc38cb398f6f4b92d25ce1fd8e1ea4a0f
environment: local
config/model version: N/A (deterministic-only, không gọi model)
golden-set version: scripts/agent_v2/golden/golden_set_v2.json (deterministic subset, 15/15) + tests/test_agent_v2_time_aware_schedule.py (36/36) + tests/test_agent_v2_conversation_state.py (14/14)
exact command: python scripts/agent_v2/run_golden_evaluation.py --deterministic-only ; python -m pytest tests/test_agent_v2_time_aware_schedule.py tests/test_agent_v2_conversation_state.py -q
pass/fail aggregate: 15/15 + 36/36 + 14/14, tất cả PASS
notes: baseline "trước" cho TASK-V2.5-002 (active_schedule_range), trước khi có runtime change nào
```

### Quyết định cần bạn xác nhận trước khi tạo branch

Nhánh hiện tại (`feature/TASK-V2.5-001-schedule-tool-contract`) chứa các
commit đóng Task 01 + ADR delta Task 02, **chưa push/merge vào `main`**. Nếu
tạo branch Task 02 từ đây, nó sẽ "stacked" trên một branch chưa merge — rủi
ro thật đã gặp trước đây trong dự án này (branch base merge sau branch con
không tự retarget). Hai lựa chọn:

1. **Merge/PR nhánh Task 01 trước** (chỉ chứa doc/governance, không đổi
   runtime code — rủi ro review thấp), rồi tạo branch Task 02 từ `main` mới.
2. **Tạo branch Task 02 ngay từ nhánh hiện tại**, chấp nhận phải verify bằng
   `git merge-base --is-ancestor` sau khi Task 01 merge, trước khi tự tin
   Task 02 đã "chứa main mới nhất".

Tôi chưa push hay mở PR nào — cần bạn quyết trước khi tôi tạo branch mới.

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

- [ ] Viết red test tái tạo baseline.
- [ ] Thêm `active_schedule_range` vào `ConversationState` (v5→v6), cùng
  test đọc ngược state v5.
- [ ] Implement nhận diện follow-up "còn lại" + 4 quy tắc staleness
  (consume/overwrite/clear-topic-safety-handoff/clear-other-intent).
- [ ] Re-resolve qua `_schedule_reply` với range đã lưu (không đổi domain
  semantics của `get_doses_for_range`).
- [ ] Thêm case NEED_MORE_INFO khi không có range hợp lệ.
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
