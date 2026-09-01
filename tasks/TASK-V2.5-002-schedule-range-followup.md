# TASK-V2.5-002: Follow-up "các ngày còn lại thì sao" (range anaphora)

**Domain:** Agent V2 read-only schedule/evidence — capability context/follow-up
**Owner:** Dyo31122005 + AI
**Sprint:** V2.5 timebox — chưa gán sprint chung
**Status:** CP2 hoàn tất (local) — chưa PR/merge/deploy; xem "Bằng chứng CP2"

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

## Acceptance Criteria (AC) — CP2 hoàn tất, evidence ở cuối file

- [x] Test tái tạo chính xác baseline ở trên như một red test trước khi sửa
  (chạy RED trước khi code bất kỳ dòng implementation nào — xem "Bằng chứng
  CP2" bên dưới).
- [x] Thêm field `active_schedule_range: tuple[date, date] | None` vào
  `ConversationState`; bump `as_dict`/`from_dict` lên version 6.
- [x] **Test đọc ngược state version 5** (không có field mới) qua
  `from_dict`: trả về `active_schedule_range=None`, không lỗi.
- [x] Nhận diện "các ngày còn lại thì sao" (narrow regex
  `_is_schedule_range_remainder_followup`, orchestrator.py) khi
  `active_schedule_range` còn hợp lệ — đặt ở `run()`, không đụng
  `classify_intent`/`classify_follow_up` (tránh phải luồn tham số state qua
  6 call site của `classify_intent`; xem "Ghi chú thiết kế" bên dưới).
- [x] Khi có range hợp lệ: re-resolve đúng `active_schedule_range` đó qua
  `range_from_dates` (hàm mới, time_query_engine.py) rồi tái dùng
  `_schedule_reply`/`get_doses_for_range` nguyên trạng — không suy đoán ngày
  mới, không tự bịa range, không cần `last_served_through_date`.
- [x] Khi không có range hợp lệ: `NEED_MORE_INFO` qua
  `AnswerabilityReasonCode.MISSING_SCHEDULE_CONTEXT` (mới) — không mặc định
  thành `GENERAL_MEDICAL_INFORMATION`.
- [x] Cài đúng 5 nhánh staleness (`transition_state`) bằng unit test riêng
  cho từng trường hợp.
- [x] Entity chưa xác minh không được promote thành truth — không áp dụng
  thêm gì mới, `active_schedule_range` chỉ chứa ngày, không phải entity.
- [x] Golden/regression: thêm case `GOLD-V25-RANGE-FOLLOWUP-001` (TR01 lượt
  8→9 thật) vào file mới `scripts/agent_v2/golden/golden_set_v2_5.json`,
  chạy thật với `AGENT_V2_5_FOLLOWUP_ENABLED=true` (PASS) và xác nhận nó
  thật sự phụ thuộc flag bằng cách chạy lại với flag mặc định false (FAIL —
  rơi về model thật, đúng hành vi cũ). Golden legacy
  (`golden_set_v2.json --deterministic-only`) chạy lại với flag mặc định
  false: vẫn 15/15, không suy giảm. `tests/test_agent_v2_time_aware_schedule.py`
  36→39/39. Chi tiết lệnh/artifact ở "Bằng chứng CP2" bên dưới.
- [x] Capability flag `AGENT_V2_5_FOLLOWUP_ENABLED`, mặc định **off**, thêm
  thật vào `backend/config.py`/`.env.example`; có test riêng xác nhận flag
  off giữ nguyên hành vi cũ (misroute) không đổi.

## CP1 — Sẵn sàng implementation (theo `CHECKPOINT.md`, áp cho đúng shape Task 02)

Task 02 không đụng renderer/`ResponsePolicy`/`RenderableFactSlots` (đó là
Task 04), nên một số mục CP1 gốc không áp dụng nguyên văn — ghi rõ N/A kèm lý
do thay vì bỏ qua im lặng.

- **Branch:** `feature/TASK-V2.5-002-schedule-range-followup`, tạo từ
  `main` sau khi PR #182 (Task 01 + CP0 governance) merge (`d19cf69e`) —
  không stacked, đã verify bằng `git merge-base --is-ancestor`.
- **Kiểm tra concurrent merge (bắt buộc vì `main` đã đi trước 9 commit khi
  branch này được tạo):** một PR khác (#176, BUILD-47/48/49, "retain
  conversation context across follow-up turns") đổi đúng
  `conversation_state.py`/`follow_up.py` trong lúc CP1 này đang diễn ra. Đã
  đối chiếu: (1) thay đổi ở `conversation_state.py` là
  `DRUG_CANDIDATE_ACTION_PREFIX`/`is_drug_candidate_action` — không liên
  quan schedule/time-range, **không đổi version (vẫn 5)**; (2) fix ở
  `follow_up.py`/`_has_named_subject` đã có sẵn trong code tôi test từ đầu
  task này, không phải thay đổi mới phát sinh; (3) re-test trực tiếp
  `classify_intent("các ngày còn lại thì sao", ...)` trên branch mới →
  vẫn `GENERAL_MEDICAL_INFORMATION`, kết luận không đổi. An toàn để tiếp tục.
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
- **Baseline local (trước khi code Task 02), commit `d19cf69e` — branch point
  thật sau khi merge PR #182 (số liệu từ `a75b0c8` re-run lại, không đổi):**
  - `python scripts/agent_v2/run_golden_evaluation.py --deterministic-only`
    → 15/15 PASS, artifact `scripts/agent_v2/golden/runs/20260901T063720Z.json`.
  - `python -m pytest tests/test_agent_v2_time_aware_schedule.py tests/test_agent_v2_conversation_state.py -q`
    → 50/50 PASS (36 time-aware-schedule + 14 conversation-state).
  - Migration head vẫn `0063`, DB local khớp — không có migration mới nào
    trong 9 commit vừa merge.
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
timestamp: 2026-09-01T06:37:20Z
commit: d19cf69e1eb1f8c435edc808a528e3abf8b2af72
environment: local
config/model version: N/A (deterministic-only, không gọi model)
golden-set version: scripts/agent_v2/golden/golden_set_v2.json (deterministic subset, 15/15) + tests/test_agent_v2_time_aware_schedule.py (36/36) + tests/test_agent_v2_conversation_state.py (14/14)
exact command: python scripts/agent_v2/run_golden_evaluation.py --deterministic-only ; python -m pytest tests/test_agent_v2_time_aware_schedule.py tests/test_agent_v2_conversation_state.py -q
pass/fail aggregate: 15/15 + 36/36 + 14/14, tất cả PASS
notes: baseline "trước" cho TASK-V2.5-002 (active_schedule_range), branch point sau khi merge PR #182 (Task 01 + CP0 governance). Concurrent PR #176 (BUILD-47/48/49) cũng merge cùng lúc, đã đối chiếu không ảnh hưởng scope task này (xem mục "Kiểm tra concurrent merge" ở CP1).
```

**Đã xử lý (2026-09-01):** PR #182 (Task 01 + CP0 governance) đã merge vào
`main` (`d19cf69e`, xác nhận bằng `git merge-base --is-ancestor`), branch
`feature/TASK-V2.5-002-schedule-range-followup` đã tạo sạch từ `main` mới —
không stacked.

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

## Ghi chú thiết kế (CP2)

**Vì sao không đổi `classify_intent`/`classify_follow_up`:** `classify_intent`
là hàm thuần (message, has_dose_id, now) và được gọi ở **6 call site** khác
nhau trong `orchestrator.py`/`run()`. Luồn thêm tham số state qua tất cả 6
chỗ đó chỉ để một pattern hẹp là rủi ro/diff lớn không cần thiết. Thay vào
đó, `_is_schedule_range_remainder_followup` là một check độc lập, đặt ngay
cạnh check `_SCHEDULE_INTENTS` hiện có trong `run()` (cùng vị trí "early
return trước memory recall/Safety" như `_out_of_scope_reply`/`_schedule_reply`
đã làm) — không đổi chữ ký `classify_intent`, không đổi 6 call site, không
đổi test hiện có của nó.

**Vì sao tái dùng `_schedule_reply` thay vì viết composer mới:** case "có
range hợp lệ" chỉ khác case schedule bình thường ở chỗ range đến từ state
thay vì từ `resolve_time_query`. Dựng một `RouterDecision` tổng hợp với
`time_range = range_from_dates(...)` rồi gọi thẳng `_schedule_reply` tái
dùng nguyên contract cũ (tool, composer, fail-closed path) — không có logic
DB/reply-building nào bị nhân đôi. Tham số mới `record_range` trên
`_schedule_reply` chỉ để phân biệt "lượt này lập range mới" (ghi vào
`OrchestrationResult.resolved_schedule_range`) và "lượt này tiêu thụ range
cũ" (không ghi lại) — đúng cơ chế consume-by-omission ở `transition_state`.

## Bằng chứng CP2 (2026-09-01)

Thứ tự làm đúng như đã thống nhất: RED cho cả 4 nhóm trước, rồi mới
implement `active_schedule_range`/v6/router-state-transition/flag.

**RED (trước khi code):** 10 test conversation_state (field, version 6,
round-trip, đọc ngược v5, 5 nhánh staleness) + 2 test orchestrator
(recognition, NEED_MORE_INFO) — toàn bộ FAIL đúng lý do (field/param/behavior
chưa tồn tại), xem lịch sử tool call trong phiên làm việc.

**GREEN (sau khi implement):**
- `pytest tests/test_agent_v2_conversation_state.py` → 24/24 PASS.
- `pytest tests/test_agent_v2_time_aware_schedule.py` → 39/39 PASS (36 cũ +
  3 mới: recognition, NEED_MORE_INFO, flag-off-is-inert).
- `pytest tests/test_agent_v2_orchestrator.py` → 51/51 PASS (không suy giảm).
- `python scripts/agent_v2/run_golden_evaluation.py --deterministic-only` →
  15/15 PASS.
- Regression rộng: `pytest tests/ -k "agent_v2 or conversation_state or
  time_aware or time_query" --ignore=tests/vlm_demthuoc
  --ignore=tests/services/photo_verification` → 1149 passed, 18 failed.
  **Cả 18 failed đã xác nhận pre-existing** (chạy lại y hệt trên
  `git stash` tại branch point `4aa0c95`, cùng test, cùng lỗi
  `sqlite3.OperationalError: no such table: chat_messages` — không liên
  quan tới thay đổi của task này).
- **Lint (chính xác phạm vi, không gọi "toàn bộ suite sạch"):** `ruff check`
  trên đúng các file đã thay đổi trong diff của task này — PASS, không có
  lỗi mới. Hai loại lỗi tồn tại trong repo nhưng **không** thuộc phạm vi
  task này, không sửa: (1) 1 lỗi unused-import (`resolve_time_query`,
  `test_agent_v2_time_aware_schedule.py`) — pre-existing, xác nhận bằng
  `git diff` không chạm dòng đó; (2) 18 lỗi `chat_messages`
  (`test_agent_v2_transaction_durability.py`,
  `test_agent_v2_safety_occurrence_binding.py`,
  `test_agent_v2_long_term_memory.py`) — pre-existing baseline, xác nhận
  bằng `git stash` chạy lại y hệt tại branch point.
- `git diff --check`: sạch, không lỗi whitespace.

**Golden V2.5 case (commit `5f657f01`, sau khi thêm file golden mới):**

| Chạy | Lệnh | Kết quả | Artifact |
|---|---|---|---|
| Case mới, flag ON | `AGENT_V2_5_FOLLOWUP_ENABLED=true python scripts/agent_v2/run_golden_evaluation.py --dataset scripts/agent_v2/golden/golden_set_v2_5.json` | 1/1 PASS (271ms) | `scripts/agent_v2/golden/runs/20260901T072145Z.json/.md` |
| Case mới, flag OFF (mặc định) | `python scripts/agent_v2/run_golden_evaluation.py --dataset scripts/agent_v2/golden/golden_set_v2_5.json` | 0/1 **FAIL** (21383ms — rơi về model thật, đúng hành vi cũ trước khi có Task 02) | `scripts/agent_v2/golden/runs/20260901T072202Z.json/.md` |
| Golden legacy, flag OFF (mặc định) | `python scripts/agent_v2/run_golden_evaluation.py --deterministic-only` | 15/15 PASS | `scripts/agent_v2/golden/runs/20260901T072241Z.json/.md` |

Chạy case mới với flag OFF **có chủ đích FAIL** — đây là bằng chứng case
này thật sự phụ thuộc capability flag (không phải false positive sẽ pass
bất kể flag), đúng yêu cầu "chỉ thêm JSON nhưng runner vẫn chạy flag false
thì chưa chứng minh hành vi mới".

**Chưa làm (không chặn CP2/CP3, theo đúng chỉ đạo):**
- Append kết quả baseline vào tab V2.5 golden sheet — vẫn chưa có quyền ghi
  Google Sheets từ phiên này.

## Phản hồi review PR #183

1. **Potential KeyError** (`_schedule_range_followup_reply`, dict-lookup
   theo `time_range.relation`) — xác nhận: `TimeRelation` hiện đúng 3 thành
   viên và `range_from_dates`/`_relation_for_range` exhaustive trên cả 3, nên
   không thể KeyError với code hiện tại. Vẫn sửa vì rẻ và đúng phong cách
   fail-loud của project: đổi sang `_SCHEDULE_RANGE_RELATION_INTENT.get(...)`
   + `assert intent is not None` với message rõ ràng, thay vì dict-lookup
   trần. 114 test liên quan + golden 15/15 + golden V2.5 (flag ON) 1/1 vẫn
   PASS sau khi sửa.
2. **Strict Range Parsing** (`_parse_schedule_range`, yêu cầu đúng 2 phần
   tử) — **không sửa**, đây là lựa chọn thiết kế có chủ đích, không phải sơ
   sót: (a) "thiếu" và "sai định dạng" có cùng một xử lý ở mọi nơi gọi hàm
   này (không có range hợp lệ → NEED_MORE_INFO), nên tách biệt hai trường
   hợp không có ai tiêu thụ; (b) `as_dict` chỉ bao giờ ghi đúng cặp
   `(start_date, end_date)` đóng, không có nhu cầu range mở-đầu trong scope
   Task 02 — thêm linh hoạt cho một shape chưa ai cần là suy đoán trước,
   không phải fix bug. Đã viết rõ lý do này vào docstring của hàm để review
   sau không hỏi lại.

Commit riêng cho phản hồi review, chưa merge — chờ xác nhận trước khi sang
CP3/push tiếp.

### Round 2 (phoenix-mentor bot, sau commit 8c244dc)

**Potential Assertion Failure** trên chính dòng vừa sửa ở round 1
(`assert intent is not None`) — đúng một phần, đã kiểm chứng cụ thể:

- `assert` bị compiled-out hoàn toàn dưới `python -O`/`PYTHONOPTIMIZE=1`
  (`python -O -c "print(__debug__)"` → `False`). `Dockerfile` project chạy
  thẳng `uvicorn backend.main:app`, không có `-O` ở đâu — rủi ro không xảy
  ra thật hôm nay, nhưng phụ thuộc vào một cờ interpreter không ai đảm bảo
  giữ nguyên mãi mãi.
- Bot phóng đại một chỗ: `agent_v2_routes.py:1028` đã có
  `except Exception: ... raise` bọc quanh `orchestrator.run()`, nên dù là
  `KeyError` (bản gốc), `AssertionError` (round 1), hay bất kỳ exception
  nào, request đều "crash" giống hệt nhau ở tầng route — không phải riêng
  `assert` mới gây crash mà cái khác thì không.
- Rủi ro thật, hẹp hơn bot mô tả: nếu `-O` được bật sau này, `assert` biến
  mất, `intent=None` sẽ **chảy tiếp** vào `RouterDecision` thay vì dừng lại
  — sai âm thầm, không phải crash rõ ràng.
- **Đã sửa:** đổi `assert` thành `if intent is None: raise ValueError(...)`
  — luôn thực thi bất kể cờ interpreter, hành vi hôm nay không đổi (vì `-O`
  chưa bật), loại bỏ hẳn phụ thuộc ẩn. Không đụng `assert
  decision.time_range is not None` có sẵn trong `_schedule_reply` (cùng
  pattern, nhưng nằm ngoài diff/scope của Task 02).
- Evidence sau sửa: 114 test PASS, golden `--deterministic-only` 15/15,
  golden V2.5 (flag ON) 1/1.

## Hoàn thiện CP2 — 4 mục còn thiếu (2026-09-01, sau khi merge PR #183)

Owner yêu cầu soát lại đúng 8 mục CP2 trong `CHECKPOINT.md` thay vì tự nhận
đã xong. 4 mục sau chưa đủ bằng chứng, nay bổ sung bằng dữ liệu thật (query
DB thật, không suy đoán):

### 1. Regression doctor takeover/handoff + missed/delayed dose (đích danh, không chỉ suy ra từ filter rộng)

`pytest tests/test_agent_v2_doctor_handoff.py tests/test_agent_v2_doctor_takeover.py tests/test_doctor_takeover_timeout.py tests/test_agent_v2_safety.py tests/test_agent_v2_acute_danger.py -q`
→ **73/73 PASS**. `test_doctor_takeover_timeout.py` không khớp filter
`-k "agent_v2 or..."` trước đó nên chưa từng được xác nhận riêng — giờ đã
chạy đích danh.

### 2. Model/config/version/budget cho lượt gọi model thật (golden flag-OFF, artifact `20260901T072202Z.json`)

Lượt 2 của case `GOLD-V25-RANGE-FOLLOWUP-001` khi flag OFF thật sự rơi vào
model (`execution_path=RAG`, `model_calls=1`). Tra thẳng `AgentRun` DB row
(`agent_run_id=708828f6-a874-4ed0-8300-7166c3c757a9`):

- Model: `gpt-5.4-mini` (đúng `agent_main_model` mặc định).
- Token: input 887, cached 0, output 119, tổng 1006.
- `cost_status=NOT_AVAILABLE` (pricing chưa cấu hình ở local) — chi phí ước
  tính theo bảng giá công khai đã ghi trong `.env.example`
  (`AGENT_MODEL_PRICING_JSON`): 887/1e6×$0.75 + 119/1e6×$4.50 ≈ **$0.0012**.
- `provider_request_id`: `req_ed387595ad6a4d9686892640ca4243c6` (chỉ để đối
  chiếu, không phải dữ liệu nhạy cảm).
- Phát hiện phụ xác nhận đúng mức độ hỏng của hành vi cũ: state sau lượt
  này có `active_topic.canonical_name = "các ngày còn lại"` và
  `citation_titles: ["taptiqom-5mg-ml-santen..."]` — router cũ coi cụm từ
  này là một "chủ đề y khoa" thật và trích dẫn một sản phẩm hoàn toàn không
  liên quan.

### 3. So sánh candidate vs baseline (tổng hợp từ dữ liệu đã đo, không đo lại)

| Chiều | Baseline (flag OFF) | Candidate (flag ON) |
|---|---|---|
| Safety outcome | Không đổi — Task 02 không đụng Safety Domain | Không đổi (73/73 regression trên) |
| Grounding/clarification quality | Sai: coi "các ngày còn lại" là chủ đề y khoa, trích dẫn sản phẩm không liên quan (`taptiqom...`), pollute `active_topic` | Đúng: resolve đúng range đã lưu, không có claim/citation ngoài phạm vi |
| Error rate | Case mới: 0/1 (FAIL có chủ đích); golden legacy 15/15 không đổi | Case mới: 1/1 PASS; golden legacy vẫn 15/15 |
| Latency (lượt 2) | ~21.4s tổng (`retrieve` span 17754ms + `model_call` span 3231ms, telemetry thật) | 4.69ms (`schedule_reply` span, telemetry thật) — nhanh hơn ~4500 lần |
| Cost (lượt 2) | ~$0.0012 (887 in + 119 out token, gpt-5.4-mini) | $0 (`model_calls=0`) |

### 4. Xác minh telemetry/durable state không leak PHI/raw data (query DB thật, không chỉ suy luận ADR)

- **Span telemetry** (`AgentRunSpan`, cả path cũ lẫn mới): chỉ chứa
  `operation`, `model_role`/`model`, `latency_ms`, `input_tokens`/
  `output_tokens`, `outcome`, `provider_request_id` — không có raw message,
  không PHI. Path mới (`_schedule_range_followup_reply` qua
  `_schedule_reply`) tạo đúng span `TIME_QUERY/schedule_reply` với
  `{"operation": "schedule_reply", "outcome": "OK", "latency_ms": ...}` —
  giống hệt shape path lịch cũ, không có field mới nào bị lộ.
- **Durable `AgentRun.metadata_json`** (lớp audit, không phải telemetry —
  được phép giữ context nhiều hơn theo đúng "ba lớp dữ liệu" của
  V2.5-DESIGN.md): tra 2 lượt thật của case flag-ON —
  - Lượt 1 (lập range): `active_schedule_range: ["2026-09-07", "2026-09-13"]`
    — đúng 2 chuỗi ngày ISO, không có gì khác.
  - Lượt 2 (tiêu thụ range): `active_schedule_range: null` — **xác nhận
    thật** cơ chế "hết hạn sau đúng 1 lượt" hoạt động end-to-end trên một
    run thật, không chỉ đúng ở unit test.

### Build ở local

`uvicorn backend.main:app --host 0.0.0.0 --port 8123` trên đúng code đã
merge — khởi động sạch (`Application startup complete`, warmup Drug
Knowledge V2 3556 products/42588 chunks), `GET /health` → `200
{"status":"ok","env":"development","runtime_profile":"v2_only"}`. Dừng
process sau khi xác nhận.

**Kết luận: cả 8 mục CP2 trong `CHECKPOINT.md` đã có bằng chứng đầy đủ.**

## CP3 — soát theo đúng 6 mục trong CHECKPOINT.md (2026-09-01)

- [x] Cập nhật task status/docs/ADR: task file này, `CHECKPOINT.md` (bảng
  theo dõi + trạng thái khởi động), ADR delta 1.3a trong
  `CP0-ADR-BASELINE-TASK01.md` — đều đã cập nhật xuyên suốt quá trình, không
  phải dồn vào cuối.
- [x] Commit nhỏ theo convention `TASK-V2.5-002: <động từ mô tả ngắn>` —
  toàn bộ 5 commit (implement, review round 1, review round 2, golden
  evidence, CP2 completion) đều theo đúng convention.
- [x] Push branch chỉ sau khi CP2 pass — đúng, và CP2 còn được hoàn thiện
  đầy đủ (8/8 mục) trước khi coi nhánh sẵn sàng.
- [~] PR có đủ: linked task ✓, baseline comparison ✓, test evidence ✓,
  config/flag default ✓, owner/cohort ✓, rollback ✓ — nhưng **thiếu
  "metric query" và "stop condition" tường minh** trong body PR #183 gốc.
  Vì PR đã merge, không sửa lại body được — bổ sung chính thức vào đây làm
  nguồn tham chiếu cho CP4:

  **Metric query (khi CP4 mở canary bật `AGENT_V2_5_FOLLOWUP_ENABLED`):**
  - Tỷ lệ turn khớp `_is_schedule_range_remainder_followup` có
    `execution_path=DETERMINISTIC_SCHEDULE` (đúng) so với
    `MISSING_SCHEDULE_CONTEXT`/NEED_MORE_INFO (không có range — chấp nhận
    được) so với vẫn rơi về `GENERAL_MEDICAL_INFORMATION`/RAG (bug tái xuất
    hiện — phải luôn bằng 0 khi flag on). Nguồn: `AgentRun.intent` +
    `follow_up_category`/reason code (cột đã có từ BUILD-47), join theo
    `conversation_id`.
  - Chênh lệch latency/cost giữa nhánh `DETERMINISTIC_SCHEDULE` (gần như
    miễn phí, xem bảng so sánh CP2) và nhánh RAG cũ — theo dõi cost có giảm
    đúng kỳ vọng khi canary mở.
  - Tỷ lệ false-positive của regex nhận diện (turn khớp pattern nhưng ý
    người dùng thực ra không phải hỏi lại lịch) — cần fixture/feedback thật
    từ canary vì hiện chỉ có 1 case golden.

  **Stop condition:**
  - Bất kỳ regression nào ở schedule/dose-status/safety/handoff suite hiện
    có (73+15+39+24+51 test đã dùng làm baseline ở CP2).
  - `active_schedule_range` xuất hiện raw text/PHI ở bất kỳ đâu ngoài đúng
    2 chuỗi ngày ISO (đã audit ở CP2, nhưng cần re-check định kỳ khi có
    thay đổi liên quan).
  - Tỷ lệ `MISSING_SCHEDULE_CONTEXT` tăng bất thường so với baseline canary
    ban đầu (dấu hiệu regex bắt nhầm câu không liên quan tới lịch).
- [~] Reviewer kiểm tra code/test/privacy/contract compatibility/scope
  V2.5-V3 — thực hiện qua bot review `phoenix-mentor` (2 vòng, cả hai đều
  đã phản hồi và sửa/giải thích rõ, xem 2 mục review ở trên) + owner tự
  merge sau khi xem xét. Không có review viết tay từ một reviewer người
  khác chỉ định theo `TEAM.md` — ghi nhận đúng thực tế, không tự nhận đã có
  bước này nếu không có.
- [ ] **CI chưa thực sự chạy xong.** Cả `lint-and-test` và `golden-smoke`
  (workflow `CI`, self-hosted runner `[self-hosted, linux, x64, cohort3]`)
  của **cả PR #183 lẫn PR #184** bị kẹt ở trạng thái `QUEUED` nhiều chục
  phút, không job nào pickup — dấu hiệu runner pool cohort3 đang offline
  (đúng vấn đề đã biết, xem `railway-deploy-no-ci.md`/memory: "Runner pool
  có thể offline hoàn toàn mà không báo"). PR vẫn được merge dựa trên bằng
  chứng local (pytest/golden/ruff/build tôi tự chạy và owner tự xem xét),
  **không phải CI pipeline của repo tự xác nhận**. Đây là gap thật, không
  che giấu: gate "đạt CI trước merge" của CP3 không được thoả bằng chính CI
  của repo cho cả hai PR. Không tự sửa (không có quyền/không phải phạm vi
  Task 02 để khởi động lại self-hosted runner) — ghi nhận để owner quyết
  định có cần chạy lại CI thủ công (`gh run rerun`) khi runner online trở
  lại hay chấp nhận bằng chứng local là đủ.

**Tổng kết CP3:** 3/6 mục đạt đầy đủ, 2/6 đạt với ghi chú (bổ sung tài liệu
sau khi PR đã merge; review chỉ qua bot + owner, không có reviewer người
riêng), 1/6 **không đạt theo đúng chữ** (CI chưa chạy xong do runner pool
offline) — merge đã xảy ra dựa trên quyết định của owner, không phải vì
CP3 tự nhận đã xong toàn bộ.

## CP4 — Railway release và canary có kiểm soát (2026-09-01)

### Release snapshot (mục CP4 đầu tiên)

- **Merged commit:** `bd484fac50a3c0de9e35cbec37750ece6b2907ec` (main, sau PR
  #182/#183/#184/#185).
- **Deploy/config snapshot:** BE service `VMEC-04/BE`, project `VMEC-04`,
  environment `production`. `AGENT_V2_5_FOLLOWUP_ENABLED` chưa có trong
  Railway env vars → dùng default `false` từ `backend/config.py`.
- **Flag:** `AGENT_V2_5_FOLLOWUP_ENABLED=false` (mặc định, chưa set gì
  trên Railway).
- **Owner:** Dyo31122005. **Cohort:** chưa có — chưa mở canary.

### Phát hiện chặn deploy, đã xử lý

Auto-deploy (`Deploy` workflow, GitHub Actions, cùng self-hosted runner pool
`cohort3` với CI đã kẹt ở CP3) **không chạy được cho bất kỳ merge nào hôm
nay** — verify bằng `gh run list --workflow=deploy.yml`: PR #182/#183/#184
đều `cancelled`, PR #185 kẹt `queued`; một deploy từ hôm trước còn `queued`
sau 12+ giờ. Verify bằng `railway status --json`: deployment production
thật trước khi tôi can thiệp là từ `2026-08-31T15:06:44Z` — **trước toàn bộ
merge hôm nay**, tức production chưa chạy code nào của Task 01/Task 02.

Owner chọn hướng: deploy thủ công qua `railway up`. Lần đầu fail
`Access is denied (os error 5)` ở bước Indexing — nguyên nhân: nhiều thư
mục local phát sinh sau ngày tạo `.railwayignore` (`.venv-drug-image/`,
`.worktrees/`, `_prod_import_staging*/`, `local_drug_image_storage/`,
`data/drug_images|photo_verifications|rag-eval/`) không nằm trong
`.gitignore` lẫn `.railwayignore` (xác nhận bằng `git check-ignore -v`,
không có output nghĩa là không bị ignore ở đâu cả). Đã sửa `.railwayignore`
([PR #186](https://github.com/AI20K-Build-Phase-Cohort-3/P-067/pull/186),
chưa merge) và deploy lại thành công.

### "Deploy với flag off; kiểm tra healthcheck, route V2, authorization, doctor takeover" — đã verify thật trên production

- Deployment mới: `createdAt=2026-09-01T08:41:24Z`, instance `RUNNING`,
  instance cũ `REMOVED` (cutover sạch).
- `GET https://vmec-04be-production.up.railway.app/health` →
  `200 {"status":"ok","env":"production","runtime_profile":"v2_only"}`.
- Log khởi động sạch: migration `alembic upgrade head` no-op (đã ở `0063`),
  warmup Drug Knowledge V2 + drug image recognition + OCR index đều
  complete, scheduler start đủ 9 job (kể cả `_run_doctor_takeover_timeout`)
  — chạy thành công lần đầu ngay sau deploy.
- Traffic thật đã quay lại bình thường ngay sau deploy: `GET
  /api/v1/nudges/unseen` → 200, `GET /api/v1/doses?patient_id=...` → 200 —
  xác nhận route V2 hiện hữu không bị ảnh hưởng.
- Không test riêng "authorization" bằng request giả trên production (không
  tạo request có patient/actor giả trên hệ thống thật) — dựa vào traffic
  thật đang chạy đúng làm bằng chứng gián tiếp; không có gì trong diff
  Task 02 đụng tới authorization.

### Còn lại của CP4 — CHƯA làm, cần quyết định riêng

- [ ] Observe-only/shadow — ADR của capability này không yêu cầu, bỏ qua có
  căn cứ.
- [ ] **Bật internal allowlist rồi small canary** — đây là bước đổi hành vi
  thật cho người dùng thật (dù chỉ một allowlist nhỏ), **cần owner xác nhận
  riêng, không suy ra từ "tiếp tục CP4"**. Chưa làm.
- [ ] Theo dõi metric query đã định nghĩa ở CP3 — chỉ có ý nghĩa sau khi
  canary mở.
- [ ] Ghi quyết định tiếp tục/rollback/ramp — chưa tới bước này.
- [ ] Ramp — chưa tới bước này.

**Trạng thái CP4: phần "deploy với flag off" đã xong và verify thật trên
production. Phần "canary" (đổi hành vi patient-facing) chưa bắt đầu, chờ
quyết định riêng của owner.**
