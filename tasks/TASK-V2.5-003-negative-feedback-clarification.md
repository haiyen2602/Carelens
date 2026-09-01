# TASK-V2.5-003: Phục hồi tự nhiên khi người dùng phủ định câu trả lời ("Không đúng")

**Domain:** Agent V2 conversation context — capability clarification
**Owner:** Dyo31122005 + AI
**Sprint:** V2.5 timebox — chưa gán sprint chung
**Status:** CP2 hoàn tất (local) — chưa PR/merge/deploy

## Mục tiêu

Khi bệnh nhân trả lời phủ định một câu trả lời trước đó (vd "Không đúng",
"Sai rồi", "Không phải vậy") mà **không nêu lại chủ đề/thực thể nào mới**,
Agent V2 hiện hiểu nhầm đây là chuyển sang một chủ đề/thực thể khác
(`TOPIC_SWITCH`) — xoá mất ngữ cảnh đang có thay vì hỏi lại tự nhiên "sai ở
chỗ nào".

## Baseline / reproduction (đã xác nhận thật, 2026-09-01, không dựa vào sheet cũ)

```python
from backend.agents.v2.follow_up import classify_follow_up, _strip_evidence_markers, _ascii_fold, _has_named_subject

classify_follow_up("Không đúng", prior_topic=None, prior_entity_name="Vitamin C")
# -> FollowUpCategory.TOPIC_SWITCH, reason=NAMED_SUBJECT_DIFFERS_FROM_PRIOR (SAI)

_strip_evidence_markers(_ascii_fold("Không đúng"))  # -> "dung"
_has_named_subject("dung")  # -> True (sai — "đúng" không phải chủ đề)
```

**Cơ chế lỗi (đã trace):** `_ascii_fold("Không đúng")` = `"khong dung"`.
`_strip_evidence_markers` loại `"khong"` vì nó nằm trong `_QUESTION_PARTICLES`,
nhưng `"dung"` (đúng) không nằm trong bất kỳ danh sách filler nào ở
`follow_up.py` (không phải deictic, không phải attribute keyword, không
phải question particle) → sống sót sau strip → `_has_named_subject` đọc
nhầm thành "tên chủ đề mới" → vì khác thực thể trước đó (Vitamin C) →
`TOPIC_SWITCH`. Route xuống `classify_intent("Không đúng")` cũng cho
`UNKNOWN_OR_AMBIGUOUS` (không khớp keyword nào) — không tự nó gây lỗi
route, nhưng phối hợp với `TOPIC_SWITCH` ở tầng follow-up khiến
`agent_v2_routes.py` xoá `active_topic`/`active_entity` (theo đúng logic
invariant #7 hiện có), nên ngữ cảnh mất thật.

## Không thuộc phạm vi task này (tách riêng, không gộp)

**Case sửa nguyên nhân triệu chứng** (vd bệnh nhân nói "đau bụng sau khi
uống thuốc" rồi tự sửa "sau khi ăn xiên nướng") — reproduce thật cho thấy
đây là **một lỗi khác hẳn**: `classify_intent("Mình bị từ hôm qua sau khi ăn
xiên nướng")` trả về `MEDICATION_HISTORY` vì câu chứa "hôm qua" khớp
`resolve_time_query` **trước khi** logic triệu chứng/follow-up có cơ hội
xét — đây là vấn đề **thứ tự ưu tiên trong router** (time-phrase đè lên
symptom-correction), không phải vấn đề "hỏi lại tự nhiên khi phủ định".
Ghi nhận backlog riêng cho capability context/follow-up (cùng nhóm với
entity-ellipsis TR02/TR15 chưa làm), **không xử lý trong Task 03**.

## Quyết định thiết kế đã chốt (owner, 2026-09-01)

**Flag riêng, không dùng chung Task 02:** `AGENT_V2_5_CLARIFICATION_ENABLED=false`
(mặc định off). Lý do owner: Task 02 chỉ xử lý schedule-range; Task 03 đổi
cách hiểu/phản hồi khi phủ định — cần canary/metric/stop-condition/rollback
độc lập, dùng chung flag sẽ không tắt riêng được nếu clarification lỗi.

**Rủi ro va chạm mới phát hiện, đã xác nhận bằng code — "đúng" và "dùng"
ascii-fold về CÙNG một chuỗi:**

```python
_ascii_fold("không đúng")  # -> "khong dung"
_ascii_fold("không dùng")  # -> "khong dung"  <-- giống hệt
```

Nếu match theo substring "khong dung" ở bất kỳ đâu trong câu, "Tôi không
dùng thuốc này nữa" (thông báo ngừng dùng thuốc — nghĩa hoàn toàn khác) sẽ
bị bắt nhầm thành phản hồi phủ định. **Giải pháp: chỉ nhận diện khi toàn bộ
`remainder` (sau khi strip filler y hệt Case 2 hiện có) CHỈ CÒN LẠI từ phủ
định, không còn token nào khác** — không phải substring match trên câu gốc.
Với "Tôi không dùng thuốc này nữa": sau strip, phần còn lại vẫn có
"thuoc"/"nay" (không phải toàn bộ đều là từ phủ định) → không khớp, xử lý
bình thường như trước (không đổi hành vi).

### 5 guard bắt buộc (owner yêu cầu, ghi rõ để không quên khi code)

1. **Marker chỉ bắt phủ định hẹp khi có context hợp lệ; không bắt mọi câu
   có "không".** → thực hiện bằng "toàn bộ remainder chỉ là từ phủ định"
   (xem trên), không phải substring; và chỉ áp dụng khi
   `prior_context_exists` (có `prior_topic` hoặc `prior_entity_name`) — nếu
   không có gì để giữ, rơi về `AMBIGUOUS_FRAGMENT` như logic hiện có, không
   tạo nhánh mới cho trường hợp này.
2. **Safety/triage và explicit time/entity mới luôn được xét trước marker
   này.** → đã đúng theo kiến trúc hiện có, không cần thêm gì: `classify_follow_up`
   chỉ được gọi (orchestrator.py dòng ~1773) SAU KHI `classify_intent` đã
   loại acute-danger/safety/schedule/personal-symptom/dose-safety ở các
   nhánh sớm hơn trong `run()`. Trong `classify_follow_up`, check phủ định
   mới đặt SAU Case 1 (`explicit_topic`) — nếu câu vừa phủ định vừa nêu chủ
   đề mới ("Không đúng, tôi muốn hỏi Paracetamol"), `remainder` còn lại
   "paracetamol" (không phải toàn từ phủ định) → không khớp, xử lý như
   Case 2 hiện có (đúng, vì có chủ đề thật).
3. **Khi flag off, giữ nguyên legacy behavior (kể cả bug).** → thêm tham số
   `recognize_negative_feedback: bool = False` vào `classify_follow_up`
   (mirror đúng cách `has_dose_id`/`now` đã là optional param của
   `classify_intent`). Mặc định `False` → nhánh mới không chạy, hành vi y
   hệt hôm nay (kể cả bug `TOPIC_SWITCH` sai). Orchestrator truyền
   `request.clarification_capability_enabled` vào đây.
4. **Khi marker match, giữ context nhưng không suy đoán "sai chỗ nào"; trả
   clarification deterministic ngắn.** → reason code mới không rơi vào
   nhánh `TRUE_FOLLOWUP` hiện có (nếu vậy sẽ bị xử lý như "hỏi tiếp về
   Vitamin C", tức đoán sai). Cần một nhánh xử lý RIÊNG ở orchestrator.py
   trả câu cố định, không phải model-generated.
5. **Case "sau khi ăn xiên nướng" giữ backlog context/follow-up riêng,
   không đưa vào Task 03.** → đã ghi ở mục "Không thuộc phạm vi" trên,
   không đổi.

## Quyết định thiết kế đề xuất (đã chốt ở trên — phần dưới là chi tiết implementation)

**Đề xuất: thêm marker nhận diện phủ định hẹp + reason code mới dưới
`FollowUpCategory` đã có, không tạo category mới.** Lý do: phủ định
("không đúng"/"sai rồi") khi có ngữ cảnh trước đó về bản chất là một dạng
follow-up phụ thuộc ngữ cảnh (giống `TRUE_FOLLOWUP` hiện có) — chỉ khác ở
chỗ NỘI DUNG câu hỏi lại phải khác (hỏi "sai chỗ nào" thay vì diễn giải
tiếp chủ đề cũ). Mirror đúng cách Task 02 xử lý `MISSING_SCHEDULE_CONTEXT`
(thêm reason code hẹp, không thêm khái niệm route mới).

- Thêm `_NEGATIVE_FEEDBACK_MARKERS` (narrow, evidence-based, theo đúng
  convention `_DEICTIC_MARKERS`/`_ATTRIBUTE_KEYWORDS` đã có): "khong dung",
  "sai roi", "khong phai vay", "khong phai the", "nham roi".
- Trong `classify_follow_up`: nếu message CHỈ chứa marker phủ định (không
  còn subject nào khác sau khi strip) → trả `TRUE_FOLLOWUP` (nếu có
  `prior_context_exists`) với `FollowUpReasonCode.NEGATIVE_FEEDBACK_WITH_PRIOR_CONTEXT`
  mới, hoặc `AMBIGUOUS_FRAGMENT` với `NEGATIVE_FEEDBACK_NO_PRIOR_CONTEXT`
  nếu không có gì để giữ. **Không đi vào nhánh named-subject/TOPIC_SWITCH.**
- Ở `agent_v2_routes.py`/`orchestrator.py`: khi reason code là
  `NEGATIVE_FEEDBACK_WITH_PRIOR_CONTEXT`, **giữ nguyên** `active_topic`/
  `active_entity` (không xoá như invariant #7 vẫn làm cho TOPIC_SWITCH
  thật), và trả một câu hỏi lại tự nhiên xin lỗi + hỏi cụ thể sai ở đâu,
  thay vì lặp lại y hệt câu trả lời cũ hoặc rơi vào
  `UNKNOWN_OR_AMBIGUOUS`/honest-decline chung chung.

## Acceptance Criteria (AC)

- [ ] Red test tái tạo đúng baseline ở trên (`TOPIC_SWITCH` sai) trước khi
  sửa.
- [ ] Thêm `_NEGATIVE_FEEDBACK_MARKERS` + 2 `FollowUpReasonCode` mới; sửa
  `classify_follow_up` để nhận diện đúng, không đi vào named-subject khi
  message chỉ là phủ định thuần tuý.
- [ ] Khi có prior context: giữ nguyên `active_topic`/`active_entity`
  (không bị invariant #7 xoá nhầm), trả câu hỏi lại tự nhiên hỏi cụ thể sai
  ở đâu.
- [ ] Khi không có prior context: `AMBIGUOUS_FRAGMENT`/clarification hiện
  có xử lý (không cần logic mới).
- [ ] Không đổi ý nghĩa `TOPIC_SWITCH`/`NAMED_SUBJECT_DIFFERS_FROM_PRIOR`
  cho bất kỳ message nào KHÔNG phải phủ định thuần tuý (regression:
  `tests/test_agent_v2_build48_context_retention.py` và
  `tests/test_agent_v2_conversation_state.py` không suy giảm).
- [ ] Golden case mới (chạy thật với flag ON/OFF như Task 02 đã làm) cho
  đúng kịch bản "hỏi về Vitamin C → Không đúng".
- [ ] Capability flag riêng hoặc dùng chung `AGENT_V2_5_FOLLOWUP_ENABLED`?
  — **cần quyết định**: đây vẫn là capability "clarification" theo
  V2.5-DESIGN.md, nhưng cơ chế nằm trong `follow_up.py` (context/follow-up
  module). Đề xuất: flag riêng `AGENT_V2_5_CLARIFICATION_ENABLED` (đã đặt
  tên sẵn ở CP0 doc mục 1.7) để tách rollback độc lập với Task 02, dù code
  nằm cạnh nhau.

## Context bắt buộc phải đọc trước khi làm

- [ ] `AGENTS.md`
- [ ] `chat-bot-build/chatbot-v2_5/V2.5-DESIGN.md` (mục 9, capability
  clarification)
- [ ] `chat-bot-build/chatbot-v2_5/CP0-ADR-BASELINE-TASK01.md` (Pain point 2)
- [ ] `backend/agents/v2/follow_up.py` (đặc biệt `_strip_evidence_markers`,
  `_has_named_subject`, `classify_follow_up`)
- [ ] `backend/api/agent_v2_routes.py` (`is_topic_switch`/invariant #7,
  dòng ~1101-1106)
- [ ] `tasks/TASK-V2.5-002-schedule-range-followup.md` (mẫu quy trình
  CP0→CP4 đã áp dụng)

## Definition of Done

Theo [ADR-0005](../adrs/0005-definition-of-done.md): TDD (red trước), test
suite hiện có không suy giảm, golden case chạy thật với cả hai trạng thái
flag, capability flag mặc định off, rollback = tắt flag/revert PR.

## Ghi chú / trao đổi thêm

Case sửa nguyên nhân triệu chứng (router ưu tiên sai giữa time-phrase và
symptom-correction) được ghi nhận backlog riêng, không phải một phần AC của
task này — xem mục "Không thuộc phạm vi" ở trên.

## Bằng chứng CP2 (2026-09-01) — TDD: RED trước, GREEN sau

**RED (trước khi code):** 6 test `classify_follow_up` +  2 test orchestrator
— toàn bộ FAIL đúng lý do (`recognize_negative_feedback` chưa tồn tại,
`FollowUpReasonCode.NEGATIVE_FEEDBACK_WITH_PRIOR_CONTEXT` chưa tồn tại).

**GREEN (sau khi implement):**
- `pytest tests/test_agent_v2_follow_up.py` → 25/25 PASS (6 test mới, xác
  nhận cả 5 guard bằng thực nghiệm: flag off giữ nguyên bug cũ, flag on
  nhận diện đúng cả hai loại context, không tạo nhánh mới cho case không
  context, **không va chạm với "không dùng"** (đã verify:
  `_ascii_fold("không đúng") == _ascii_fold("không dùng") == "khong dung"`
  nhưng remainder của câu dài hơn còn "thuoc"/"nay" nên không khớp), không
  đè lên chủ đề mới thật trong cùng câu.
- `pytest tests/test_agent_v2_build43_follow_up_resolution.py` → phải sửa 1
  test khoá signature (`test_k_...`) vì nó assert đúng-3-tham-số thay vì chỉ
  assert "không có `retrieval_query`" — cập nhật để giữ đúng ý bảo vệ gốc
  (BUILD-43 #5) trong khi chấp nhận tham số flag hợp lệ mới. Sau sửa: PASS.
- `pytest tests/test_agent_v2_orchestrator.py` → 53/53 PASS (2 test mới:
  flag-on trả clarification cố định + giữ entity, flag-off giữ nguyên hành
  vi cũ).
- Regression rộng (agent_v2/conversation_state/follow_up/time_aware/
  time_query, loại vlm_demthuoc/photo_verification): **1157 passed**, 18
  fail — **cùng đúng 18 fail pre-existing** đã xác nhận ở Task 02 (không
  chạy lại git-stash vì đã xác nhận không đổi kể từ đó, cùng nguyên nhân
  `chat_messages` table).
- `ruff check` trên toàn bộ file đã sửa: sạch.
- `git diff --check`: sạch.

**Golden E2E thật (flag ON/OFF), giới hạn trung thực cần ghi rõ:**

Case `GOLD-V25-NEGFEEDBACK-001` (`golden_set_v2_5.json`): lượt 1 "Paracetamol
dùng để làm gì" (câu đã xác nhận route đúng `DRUG_INFORMATION` — thử "Thông
tin thuốc Vitamin C"/"Thông tin thuốc Paracetamol" trước đó đều SAI route
hoặc timeout, không phải lỗi Task 03), lượt 2 "Không đúng".

- Chạy với `AGENT_V2_5_CLARIFICATION_ENABLED=true`: 1/1 PASS.
- Chạy với flag mặc định false: **cũng 1/1 PASS** — **không phân biệt được
  hành vi flag ON/OFF qua case này**, khác Task 02. Nguyên nhân xác nhận
  bằng query DB thật: lượt 1 (trả lời qua `search_drug`, không gọi
  `get_drug_info` cho một ID cụ thể) **không bind `active_entity`** —
  `AgentRun.metadata_json.conversation_state.active_entity` là `None` sau
  cả hai lượt. Vì không có prior context, lượt 2 rơi vào nhánh "không có gì
  để giữ" ở cả hai phía flag — nhánh mới (guard 1: fallback về
  `AMBIGUOUS_FRAGMENT`) và nhánh cũ (`NAMED_SUBJECT_NO_PRIOR_CONTEXT`) tình
  cờ cho cùng `execution_path=GENERAL_MODEL`.
- **Bằng chứng thật cho "giữ context khi có" nằm ở tầng orchestrator**
  (`test_negative_feedback_with_flag_on_asks_what_was_wrong_and_preserves_entity`,
  dùng `prior_active_entity_id`/`prior_active_entity_name` truyền thẳng vào
  request — không phụ thuộc việc model có tự bind entity hay không), không
  phải ở golden case này. Không tiếp tục đốt thêm lượt gọi model thật để cố
  ép một câu hỏi tự nhiên bind entity — chi phí/lợi ích không hợp lý so với
  bằng chứng đã có.
- Golden legacy (`--deterministic-only`) vẫn 15/15, không suy giảm.

**Capability flag:** `AGENT_V2_5_CLARIFICATION_ENABLED`, mặc định `false`,
thêm thật vào `backend/config.py`/`.env.example`, độc lập hoàn toàn với
`AGENT_V2_5_FOLLOWUP_ENABLED` của Task 02 (đúng yêu cầu owner).

**Chưa làm (không chặn CP2, giống pattern Task 02):**
- Append golden sheet — vẫn chưa có quyền ghi.
- Chưa push/PR — chờ xác nhận trước khi mở PR.
