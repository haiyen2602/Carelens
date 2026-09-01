# CP0 — ADR ngắn + Baseline report + Task 01 (gộp một PR nhỏ)

> Nguồn thiết kế: [V2.5-DESIGN.md](./V2.5-DESIGN.md). Runbook: [CHECKPOINT.md](./CHECKPOINT.md) (CP0).
> Owner / Reviewer: **Dyo31122005 (một mình, kiêm PM/Architect/Release owner)**.
> Trạng thái: **Approved — CP0 exit đạt; Task 01 đã đóng (discovery closure,
> không runtime change); Task 02 (context/follow-up, range anaphora) đang ở
> CP1.**

---

## Phần 1 — ADR ngắn: boundary và rollout V2.5

### 1.1 Scope canary đầu

Đúng **ba capability production**, timebox tối đa hai sprint:

```text
renderer → context/follow-up → clarification
```

`ResponsePolicy` là hạ tầng dùng chung cho cả ba, **không** phải capability
thứ tư, không có flag/canary/cohort/rollback riêng của chính nó.

**Đề xuất thứ tự build** (dựa trên baseline evidence ở Phần 2 — xem để duyệt):

1. **Task 01 — ĐÃ ĐÓNG, dạng discovery closure, không có runtime change.**
   Reproduction thật trên code hiện tại cho thấy bug gốc (row ~108, "hai lượt
   mâu thuẫn") **đã được BUILD-27B/28 sửa từ trước** — có regression test sẵn
   (`tests/test_agent_v2_time_aware_schedule.py:89`), 36/36 pass, golden
   baseline 15/15 pass. Không viết code cho bug không còn tồn tại. Chi tiết:
   [TASK-V2.5-001](../../../tasks/TASK-V2.5-001-schedule-tool-contract.md).
2. **Task 02 — context/follow-up, bắt đầu từ phát hiện mới:** "các ngày còn
   lại thì sao" (anaphora về phần còn lại của một range đã hỏi trước đó) hiện
   misroute thành `GENERAL_MEDICAL_INFORMATION` thay vì kế thừa range cũ —
   phát hiện trong lúc reproduce Task 01, không phải giả định từ sheet. Chi
   tiết: [TASK-V2.5-002](../../../tasks/TASK-V2.5-002-schedule-range-followup.md).
3. **Task 03 — clarification.**
4. **Task 04 — renderer** (cần `gpt-5.6-luna` availability smoke PASS — xem
   1.4 — **và** `ModelRole.RENDERER` tách khỏi `ModelRole.MAIN` đã code hoá
   — xem 1.4a — **và** định nghĩa `RenderableFactSlots` thật, vì đây là nơi
   nó có consumer đầu tiên. `RenderableFactSlots` **không** được dựng như
   abstraction độc lập ở Task 01/02/03 — tránh tạo contract chưa ai dùng
   trong timebox hai sprint).

### 1.2 Renderer ownership

**Quyết định: tái sử dụng `synthesize_read_only`** (`backend/agents/v2/model_gateway.py`),
không tạo component mới. Lý do: nó đã đúng hình dạng cần (verified evidence →
Vietnamese natural reply, không có quyền gọi tool ở turn này), đã có sẵn
fail-closed path (`EmptySynthesisError`), và tránh có hai renderer cùng sở
hữu patient-facing prose. V2.5 mở rộng nó để nhận `ResponsePolicy` +
`RenderableFactSlots` làm input có cấu trúc thay vì prompt string tự do như
hiện nay, không thay chữ ký/luồng gọi.

### 1.3 Ranh giới tái sử dụng V3

- `chat-bot-v3/docs/soul_v3.md` → **reuse trực tiếp** cho renderer.
- **Phát hiện thêm cần ghi vào ADR:** repo đã có sẵn `chat-bot-build/soul.md`
  (124 dòng) — bản soul.md *khác*, viết cho một hệ thống/vòng build cũ hơn
  Agent V2 (nhắc tới `UNPARSEABLE_YES_NO_MESSAGE`, "vòng 2/3/4", xác thực ảnh
  uống thuốc — không khớp kiến trúc Agent V2 hiện tại). Nội dung persona của
  nó (mục 2, 4, 7: "không máy móc", "trung thực khi không chắc", câu ví dụ
  "Dạ, mình chưa hiểu rõ ý của bạn ạ...") **trùng tinh thần với `soul_v3.md`**
  nhưng đã có sẵn bằng tiếng Việt, viết riêng cho use case chatbot thuốc này.
- ResponseAST/FactSlot (`response_ast_contract_v3.md`) → **chỉ tham chiếu**,
  không import/wire. V2.5 tự định nghĩa `RenderableFactSlots` tối giản
  **ở Task 04** (nơi nó có consumer thật đầu tiên — renderer) và bọc
  `synthesize_read_only` bằng adapter mỏng. Không dựng contract này sớm hơn
  ở Task 01/02/03 khi chưa có nơi dùng thật.

**Chốt (không còn treo):** `chat-bot-build/soul.md` (bản cũ, 124 dòng) là
**legacy/historical reference** — viết cho một hệ thống/vòng build trước
Agent V2, không khớp kiến trúc hiện tại. **Không được load vào bất kỳ
production path nào của V2.5.** Giữ nguyên file (không xoá) vì có giá trị
lịch sử/tham chiếu, nhưng `soul_v3.md` là **nguồn voice duy nhất** cho
renderer V2.5 — không dùng song song hai bản soul để tránh trôi dạt.

### 1.3a — ADR delta (2026-09-01): `active_schedule_range` durable trên `ConversationState`

Bổ sung cho Task 02 (context/follow-up, xem
[TASK-V2.5-002](../../../tasks/TASK-V2.5-002-schedule-range-followup.md)):
chốt Phương án A thay vì short-term memory (in-process, không sống sót qua
restart/nhiều worker — xem lý do đầy đủ ở lịch sử trao đổi task đó).

- Field mới `active_schedule_range: tuple[date, date] | None` trên
  `ConversationState`. Không cần migration DB — state đã nằm trong
  `AgentRun.metadata_json` sẵn có. Bump `as_dict`/`from_dict` version 5→6,
  cùng test đọc ngược state v5 (thiếu field mới) không lỗi/không suy ra giá
  trị giả — theo đúng convention đã dùng cho `answerability_attempt_count`.
- Không lưu `last_served_through_date` — `_schedule_reply` luôn trả toàn bộ
  range trong một lần (không có khái niệm "phần chưa trả"), nên "còn lại"
  chỉ cần re-resolve đúng range đã lưu.
- Staleness: hợp lệ đúng một lượt kế tiếp — consume khi dùng, overwrite khi
  có schedule query mới, clear khi đổi chủ đề/safety/handoff/intent khác.
- Không có range hợp lệ → `NEED_MORE_INFO` (Answerability Gate), không rơi
  về `GENERAL_MEDICAL_INFORMATION`.

### 1.4 Model-call budget và availability smoke test `gpt-5.6-luna`

**Availability smoke test đã chạy thật** (2026-09-01, input tổng hợp không
PHI, script lưu tại scratchpad phiên này, không commit vào repo vì chỉ là
smoke script dùng một lần). Đổi tên từ "preflight PASS" → **"availability
smoke PASS"**: 4 lần gọi chứng minh model khả dụng và trả lời đúng hình dạng
mong đợi, nhưng **chưa đạt mức renderer-release benchmark** (cần P95 ≥30 lần
gọi thật + pricing/cost xác nhận — xem dưới). Không dùng kết quả này để mở
canary renderer thật.

| Vòng | Prompt | Kết quả | Latency | Ghi chú |
|---|---|---|---|---|
| 1 | "Reply with the single word OK." | PASS | 6.48s | in=13/out=5 tokens |
| 2 (renderer-shaped, x3) | Prompt giống thật `synthesize_read_only` (evidence JSON tổng hợp, hỏi công dụng thuốc test) | PASS x3 | 4.12s / 4.88s / 3.12s | in=160 tokens mỗi lần; out=125–185 tokens; trả lời tiếng Việt tự nhiên, đúng giọng, và ở 1/3 lần còn tự nhận "dữ liệu hiện có chưa..." thay vì bịa — dấu hiệu tốt cho grounding |

**Kết luận: availability smoke PASS.** `gpt-5.6-luna` khả dụng thật với
credential hiện tại, latency 4 lần gọi nằm trong ngân sách
(`AGENT_MODEL_TIMEOUT_SECONDS=15`, `AGENT_RUN_TIMEOUT_SECONDS=30`). Đây là
thông tin **mới, ngược với suy đoán ban đầu** (model không có trong
`AGENT_MODEL_PRICING_JSON` của `.env.example`, vốn mới audit giá thật ngày
2026-08-19) — absence khỏi bảng giá không đồng nghĩa model không gọi được,
chỉ là chưa được đưa vào vai trò production nào.

**Còn thiếu trước khi coi là renderer-release benchmark PASS (block Task 04,
không block Task 01/02/03):**
- Cập nhật `AGENT_MODEL_PRICING_JSON` với giá thật của `gpt-5.6-luna` (chưa
  tra được trong phiên này — cần owner lấy từ trang giá OpenAI hiện hành).
- Test khối lượng lớn hơn (P95 qua ≥30 lần gọi thật, không chỉ 4 lần smoke).
- Test hành vi khi lỗi/timeout thật (không chỉ happy path).

**Budget:** renderer dự kiến thay thế đúng lệnh gọi `synthesize_read_only`
đã có (không thêm lượt gọi) → nằm trong `AGENT_MAX_MODEL_CALLS=2` hiện tại.
Nhưng "thay model của lượt synthesis mà không đổi model của lượt planning"
**chưa thực hiện được với code hiện tại** — xem 1.4a, đây là blocker phải
chốt trước khi Task 04 được coi là có thể bắt đầu.

### 1.4a — Blocker mới: `synthesize_read_only` và `plan_read_only` dùng chung `ModelRole.MAIN`

**Xác nhận bằng code, không phải giả thuyết:**

- `backend/agents/v2/model_gateway.py:405` (`plan_read_only`) và `:478`
  (`synthesize_read_only`) đều lấy `workload = self._workloads[ModelRole.MAIN]`
  — cùng một workload, cùng một model.
- `backend/agents/v2/runtime.py:385-390` (lượt planning) và `:483-491`
  (lượt synthesis) đều gọi `self._telemetry.record_model(..., role=ModelRole.MAIN,
  model=self._model_name, ...)` — cùng `role`, cùng `self._model_name` (một
  thuộc tính duy nhất của cả runtime instance) cho cả hai lượt.

**Hệ quả:** nếu chỉ đổi `agent_main_model` sang `gpt-5.6-luna` để "renderer
dùng Luna", lượt planning (chọn tool, không cần giọng văn tự nhiên, không
cần grounding renderer) cũng đổi theo — không có cách tách hai lượt bằng
config hiện tại. Telemetry/cost cũng đang ghi toàn bộ run dưới một
`ModelRole.MAIN`/`model` duy nhất, nên sau này không tách được chi phí
planning vs renderer theo role.

**Quyết định ADR (chốt ngay, code hoá ở Task 04):**

1. Thêm `ModelRole.RENDERER` vào `StrEnum` `ModelRole` (`model_gateway.py`).
2. Thêm settings riêng theo đúng pattern đã có của MAIN/FALLBACK
   (`backend/config.py`, `build_model_workloads()`):
   `agent_renderer_model` (mặc định giữ nguyên hành vi hiện tại, ví dụ trỏ
   về giá trị của `agent_main_model` cho tới khi Task 04 đổi thật),
   `openai_renderer_api_key`, env var `OPENAI_RENDERER_API_KEY`
   (`AGENT_RENDERER_MODEL` trong `.env.example`).
3. `OpenAIModelGateway.synthesize_read_only` đổi sang
   `self._workloads[ModelRole.RENDERER]`; `plan_read_only` **giữ nguyên**
   `ModelRole.MAIN` — không đổi.
4. `runtime.py`: lượt synthesis đổi `role=ModelRole.MAIN` →
   `role=ModelRole.RENDERER` và dùng đúng model name của workload renderer
   (không phải `self._model_name`, vốn vẫn là model của planner) khi ghi
   `record_model(...)` và span attribute `attributes={"model_role": ..., "model": ...}`.
5. `AGENT_MODEL_PRICING_JSON`/cost-estimation (`observability.py`
   `PricingTable.estimate(model=, model_role=, usage=)`) phải có entry cho
   `gpt-5.6-luna` và được audit để chắc `model_role=ModelRole.RENDERER` được
   tính giá đúng, không rơi vào nhánh mặc định sai.
6. Không tăng `AGENT_MAX_MODEL_CALLS` — vẫn đúng 2 lượt gọi (planning +
   renderer), chỉ tách model/role của lượt thứ hai.
7. **Durable model/cost accounting:** `AgentRunSpan` model events là nguồn
   breakdown đã được sanitize theo từng call (`model_role`, `model`, token,
   latency, estimated cost). Task 04 phải tính tổng token/cost của `AgentRun`
   bằng tổng các `CostEstimate` theo từng call/role, không lấy aggregate
   `RunMetrics` rồi áp giá của một `agent_main_model`. Nếu một run dùng hơn
   một model, `AgentRun.model` ghi `MULTI_MODEL`; Admin Monitoring phải đọc
   breakdown theo `AgentRunSpan` khi filter/báo cáo model, thay vì gán toàn bộ
   run cho planner. Không được thêm prompt, response, raw fact hay PHI vào
   span/audit metadata.

Không có quyết định này thì câu "renderer Luna thay thế lệnh gọi hiện có,
không tăng budget" trong 1.4 **chưa thực hiện đúng được** — đây là điều kiện
tiên quyết của Task 04, không phải chi tiết implementation có thể để sau.

### 1.5 Fallback

Timeout/invalid renderer output đi qua path fail-closed đã có
(`EmptySynthesisError` → `RunStatus.FAILED` với safe fallback text, xem
`backend/agents/v2/runtime.py`). Task 02–04 chỉ mở rộng input/output shape
của lệnh gọi, không thay cơ chế fail-closed này.

### 1.6 Durable audit vs telemetry

Tái dùng convention đã có trong `backend/agents/v2/observability.py`
(`TraceComponent`, safe-reference only) và `_safe_error()` trong
`model_gateway.py` (type + status, không log prompt/response). Không thêm
field PHI mới.

### 1.7 Capability rollout (đề xuất, chờ Task 02+ hiện thực hoá trong config.py)

Naming đề xuất, chưa tồn tại trong `backend/config.py` — Task 02 sẽ thêm
thật khi build:

```text
AGENT_V2_5_FOLLOWUP_ENABLED=false      (Task 02)
AGENT_V2_5_CLARIFICATION_ENABLED=false (Task 03)
AGENT_V2_5_RENDERER_ENABLED=false      (Task 04)

# Task 04 cũng cần cấu hình model riêng cho renderer (xem 1.4a) — KHÔNG
# dùng chung agent_main_model:
AGENT_RENDERER_MODEL=gpt-5.6-luna
OPENAI_RENDERER_API_KEY=
```

`CHAT_RUNTIME=legacy` giữ nguyên vai trò emergency rollback, không phải
feature gate của các flag trên.

**Quyết định owner đã ghi nhận:** duyệt thứ tự `Task 01 → Task 02 → Task 03
→ Task 04`, ba tên capability flag ở trên, cùng `ModelRole.RENDERER`,
`AGENT_RENDERER_MODEL` và `OPENAI_RENDERER_API_KEY`. Task 01 là bugfix nền
tảng không có capability flag; Task 02–04 mới có flag/canary/rollback riêng.

---

## Phần 2 — Baseline report de-identified

**Nguồn evidence:** golden test dataset thật, **177 case** (đếm chính xác từ
CSV export thô ngày 2026-09-01, không qua model tóm tắt trung gian — số 178
ghi ở bản trước là sai), cột `Ky vong dau ra / Tieu chi dung` đã gắn nhãn kết
quả chạy ở local cho các version V1/V2
([link sheet](https://docs.google.com/spreadsheets/d/1wv-9p4oTuJ_0ErPCij4gh9eENLmd-qzbjMr8mWSOE3Y/edit?gid=0#gid=0)).
Toàn bộ trích dẫn dưới đây là câu hỏi tổng hợp/kiểm thử, không phải dữ liệu
bệnh nhân thật — an toàn để đưa vào baseline de-identified.

**Sửa lỗi phương pháp (2026-09-01):** bản trước trích xuất qua `WebFetch`
(model tóm tắt trung gian), gây hai lỗi cụ thể đã xác nhận bằng cách tải
CSV thô và đếm trực tiếp: (1) tổng case sai 178→177; (2) danh sách
`GROUNDING_FAILURE` lẫn 2 dòng không có thật (110, 124, 132) — số đúng là
**đúng 11 dòng**: 112, 120, 123, 129, 130, 136, 138, 139, 140, 141, 156.
`FAILED/TOOL_ERROR` đúng 3 dòng: 105, 111, **135** (dòng 135 — "các khả năng
là gì", chưa có chủ đề nào được lập — chưa từng được nêu riêng trước đây, ghi
nhận backlog cho Task 02/03).

**Window và vai trò baseline đã chốt:** tab `15/08/2026` là lần owner tự chạy
trên **production V1**. Nó là evidence lịch sử hữu ích, nhưng không phải
baseline định lượng cho V2/V2.5. Các kết quả V1/V2 local trong sheet cũng chỉ
dùng để chọn pain point và reproduction ban đầu. Baseline chính thức của
V2.5 là một lần chạy lại toàn bộ golden suite trên **V2 hiện tại ở local**
ngay khi bắt đầu Task 01; report phải ghi commit SHA, config/model version,
golden-set version, exact command, timestamp và kết quả. Cùng bộ đánh giá
được chạy lại sau mỗi task ở local để so sánh trước/sau. Không có kết quả V2
production nào bị suy diễn từ tab V1.

**Tổng quan nhãn lỗi (đếm chính xác từ CSV thô, đã verify — thay cho số ước
lượng ±1 dòng của bản trước):**

- `V2: GROUNDING_FAILURE`: đúng **11 case** — STT 112, 120, 123, 129, 130,
  136, 138, 139, 140, 141, 156.
- `V2: FAILED/TOOL_ERROR`: đúng **3 case** — STT 105, 111, 135.
- Toàn bộ nhãn lỗi tập trung trong cụm multi-turn (TR01/TR02/TR03/TR05/TR07/
  TR08/TR09/TR14), tức đúng nhóm hội thoại nhiều lượt/follow-up — không rải
  rác ngẫu nhiên khắp 177 case.
- **Lưu ý quan trọng:** không phải mọi dòng mô tả một kịch bản "khó" đều có
  nhãn `V2: ...` — một số dòng (vd STT 108) chỉ ghi **tiêu chí đạt kỳ vọng**
  của test case, không phải kết quả V2 đã chạy và fail. Chỉ dòng có nhãn
  `V2: GROUNDING_FAILURE`/`V2: FAILED/TOOL_ERROR` tường minh mới là bằng
  chứng về một lỗi đã quan sát được.

### Pain point 1 — Ellipsis/tham chiếu thực thể bị mất hoặc bị gộp sai (→ capability context/follow-up)

**Evidence (TR02, TR15):** sau khi hỏi "Thông tin thuốc Snapcef" rồi hỏi tiếp
"Thông tin chi tiết" / "Dạng bào chế" / "tác dụng phụ" (không nêu lại tên
thuốc), kỳ vọng bám đúng Snapcef — thực thể active duy nhất. Khi người dùng
phản hồi "Không đúng" ở cuối cụm, nhãn thật là `V2: GROUNDING_FAILURE`. Cụm
TR15 khó hơn: giữ **hai** sản phẩm Vitamin C 500mg cạnh tranh (Khapharco vs
Mekophar) cùng lúc, kỳ vọng hỏi lại "sản phẩm nào" thay vì âm thầm chọn một —
đúng loại lỗi "quá máy móc" bạn mô tả ban đầu (chọn liều/thấy gì trước đó
dùng nấy, thay vì hỏi lại tự nhiên).

**Golden/regression coverage hiện có:** case này đã nằm sẵn trong sheet trên,
chưa có bản đối chiếu trong `scripts/agent_v2/golden/golden_set_v2.json`
(chưa kiểm tra khớp 1:1 — cần làm ở Task 02).

**Safety impact:** thấp — đây là câu hỏi thông tin thuốc/tra cứu, không phải
route an toàn (missed dose/overdose/emergency).

**Latency/cost:** không đổi ở pain point này (lỗi là logic phân giải thực
thể, không phải model call).

**Tiêu chí đo sau thay đổi:** % case TR02/TR15-shaped trong golden suite đạt
đúng "giữ/entity" hoặc "hỏi lại khi có ≥2 candidate", so với baseline hiện
tại (GROUNDING_FAILURE trên ít nhất case 120 và toàn bộ case TR15 mơ hồ).

### Pain point 2 — Không phục hồi tự nhiên khi người dùng phủ định hoặc sửa lại thông tin (→ capability clarification)

**Evidence — hai cụm riêng biệt (đã sửa: bản trước ghi nhầm dòng 120 thuộc
TR12; dòng 120 thực ra thuộc TR02):**
- STT 120 (TR02, lượt 8): người dùng nói "Không đúng" sau câu trả lời Vitamin
  C ở lượt 7 → `V2: GROUNDING_FAILURE` (hệ thống không biết hỏi lại đã sai
  chỗ nào).
- TR12 (STT 149-151, cụm riêng): bệnh nhân báo đau bụng "sau khi uống
  thuốc", rồi tự sửa lại "sau khi ăn xiên nướng" — kỳ vọng cập nhật giả
  thuyết nguyên nhân (không giữ "do thuốc"), không coi là triệu chứng mới.

**Golden/regression coverage:** chưa thấy case dạng "phủ định/sửa lại" trong
golden suite hiện có (`golden_evaluation.py`) ngoài sheet trên — cần thêm khi
build Task 03.

**Safety impact:** trung bình — TR12 có yếu tố triệu chứng (đau bụng), nhưng
route hiện tại là `PERSONAL_SYMPTOM`/`GENERAL_MEDICAL_INFORMATION`, không
phải Safety Domain redflag; không đổi Safety Domain ở pain point này.

**Tiêu chí đo sau thay đổi:** case "Không đúng" và case sửa nguyên nhân đạt
`TRUE_FOLLOWUP`/clarification tự nhiên thay vì lặp lại câu cũ hoặc bỏ qua
thông tin sửa.

### Pain point 3 — ĐÃ ĐIỀU TRA: không còn là bug tool/evidence, tách thành hai kết luận khác nhau

**Evidence gốc (TR01, sheet, đối chiếu lại nguyên văn từ CSV thô):**
- STT 108, "Ngày 30 tháng 8 tôi cần uống thuốc gì" (lượt 6, sau lượt 5 hỏi
  "hôm nay", với ghi chú "30/08 CHÍNH LÀ ngày hôm nay của phiên"): cột kỳ
  vọng ghi *"Phải cho kết quả TRÙNG KHỚP lượt 5... Hai lượt mâu thuẫn nhau
  là lỗi nhất quán."* — **đây là tiêu chí đạt của test case, KHÔNG có nhãn
  `V2: ...` nào** — sheet không ghi nhận V2 đã thực sự fail case này. Bản
  trước của tài liệu này trình bày nhầm dòng này như một lỗi đã quan sát
  được; đây là lỗi đọc, đã sửa.
- STT 111, "các ngày còn lại thì sao" (tham chiếu phần còn lại của khung
  "tuần sau" đã hỏi ở lượt 8) → `V2: FAILED/TOOL_ERROR` (nhãn thật, xác nhận).
- STT 112, "Tôi đã hỏi những vấn đề gì" (yêu cầu bot tự thuật lại hội thoại)
  → `V2: GROUNDING_FAILURE` (nhãn thật, xác nhận).
- STT 105, "Năm ngoái tôi uống thuốc gì" (ngoài phạm vi dữ liệu) →
  `V2: FAILED/TOOL_ERROR` — "sập tool là không chấp nhận được"; chưa có
  reproduction/task riêng, ghi nhận backlog.
- STT 135, "các khả năng là gì" (tham chiếu mơ hồ, chưa có chủ đề nào được
  lập trước đó) → `V2: FAILED/TOOL_ERROR` — kỳ vọng hỏi lại, không được sập;
  phát hiện mới, chưa có reproduction/task riêng, ghi nhận backlog.

**Kết quả reproduction thật trên code hiện tại (không phải version sheet mô
tả) — xem [TASK-V2.5-001](../../../tasks/TASK-V2.5-001-schedule-tool-contract.md)
để có evidence đầy đủ:**

1. **Mâu thuẫn lượt 5/6: không tái hiện được.** `resolve_time_query`/
   `_schedule_reply`/`get_doses_for_range` đã đúng; test
   `test_time_phrases_route_and_bound_correctly` đã có sẵn case tương đương
   và pass; 36/36 test trong file pass. Đã được BUILD-27B/28 sửa từ trước.
   **Không viết lại code cho bug không tồn tại.**
2. **"các ngày còn lại thì sao": vẫn là gap thật, nhưng khác bản chất label.**
   Route thực tế hiện tại là `GENERAL_MEDICAL_INFORMATION` (không phải crash
   `TOOL_ERROR`) — router không có cơ chế kế thừa range đã hỏi trước đó để
   tính "phần còn lại". Đây là lỗi **follow-up/context**, chuyển thành
   baseline cho [TASK-V2.5-002](../../../tasks/TASK-V2.5-002-schedule-range-followup.md)
   (capability context/follow-up), không thuộc Task 01/Phase 1 nữa.
3. **"Tôi đã hỏi những vấn đề gì": không phải bug.** Route
   `UNKNOWN_OR_AMBIGUOUS`/honest-decline là đúng boundary — Agent V2 không có
   tool đọc lại lịch sử hội thoại trong danh sách 6 tool cho phép. Giới hạn
   năng lực có chủ đích, không tạo thành requirement mới.

**Safety impact:** thấp — mục 1 không còn là vấn đề; mục 2 là route thông
tin/lịch, không phải Safety Domain; mục 3 là hành vi decline an toàn.

**Tiêu chí đo sau thay đổi:** không áp dụng cho mục 1 (đã đóng). Mục 2 dùng
tiêu chí baseline riêng ở TASK-V2.5-002.

### Phát hiện tách riêng khỏi 3 pain point trên — không thuộc lane V2.5

**Row ~123: "Tôi vừa nôn mửa, tiêu chảy kèm sốt cao"** — sheet tự gắn nhãn
**"ca hỏng nghiêm trọng nhất"** (`V2: GROUNDING_FAILURE`). Đây là mô tả triệu
chứng cấp tính, sát ranh giới `PERSONAL_SYMPTOM`/triage/Safety Domain.
**Chốt (không còn treo): mở investigation an toàn độc lập ngay, ngoài phạm
vi V2.5 — không sửa trong Task 01–04, không để canary renderer chạm vào
nhóm triệu chứng này trước khi investigation kết luận.** Chi tiết ở Phần 4.

Ngoài ra còn một cụm case row ~129–141/156 (câu hỏi y khoa chung/triage:
"Tôi bị cảm...", "Dấu hiệu cần đi khám ngay", "Cần theo dõi gì?") cũng có
nhiều `GROUNDING_FAILURE` — không đưa vào 3 pain point cap của V2.5, ghi nhận
là backlog cho Task 02/03 mở rộng nếu còn thời gian trong timebox, hoặc
chuyển V3 nếu không kịp.

---

## Phần 3 — Safety investigation độc lập: "nôn mửa + tiêu chảy + sốt cao" (ưu tiên ngay, ngoài phạm vi V2.5)

**Không phải task V2.5.** Không dùng flag/canary/rollout của V2.5. Không
chờ CP0 đóng để bắt đầu — nên chạy song song, càng sớm càng tốt.

1. **Reproduce** bằng input de-identified tương đương "Tôi vừa nôn mửa, tiêu
   chảy kèm sốt cao" trên runtime tương đương production (staging hoặc local
   với cùng router/Safety Domain hiện tại) — không dùng dữ liệu bệnh nhân
   thật.
2. **Ghi lại:** route thực tế đi qua (`classify_intent` → intent nào —
   `PERSONAL_SYMPTOM`? có bị `_detect_acute_danger`/triage red-flag bỏ sót
   không, vì "sốt cao" + "tiêu chảy" không nằm trong `_TRIAGE_RED_FLAG_MARKERS`
   hiện tại ở `orchestrator.py`), safety outcome thực tế, và so với kỳ vọng
   (có nên trigger triage clarification nghiêm túc hơn không).
3. **Thêm regression test** cho case này vào bộ test Safety/triage hiện có,
   bất kể kết quả reproduce là gì (để không lặp lại mù thông tin).
4. **Nếu tái hiện được lỗi:** tạo ADR/task Safety riêng (không phải V2.5) —
   có thể là hotfix nếu đơn giản (ví dụ bổ sung "sốt cao" vào
   `_TRIAGE_RED_FLAG_MARKERS`), hoặc task lớn hơn nếu cần đổi
   route/Safety Domain logic.
5. **Nếu không tái hiện được** (case cũ, đã fix ở build sau, hoặc do lỗi ghi
   nhận trong sheet): ghi rõ trong investigation report, đóng lại, không cần
   ADR.
6. **Ràng buộc cứng cho V2.5 trong lúc investigation chưa xong:** Task 02/03
   (context/follow-up, clarification) không được coi nhóm triệu chứng cấp
   tính dạng này là "low-risk conversational" — nếu golden suite V2.5 vô tình
   chứa input tương tự, phải loại khỏi phạm vi canary renderer/clarification
   cho tới khi có kết luận investigation.

---

## Phần 4 — Task 01 discovery closure & bàn giao sang Task 02

**Task 01 đóng dưới dạng discovery closure — không có diff runtime code.**
Toàn bộ AC/DoD, evidence (golden run 15/15, pytest 36/36, migration drift đã
xử lý) và lý do đổi AC gốc nằm trong
[TASK-V2.5-001](../../../tasks/TASK-V2.5-001-schedule-tool-contract.md) —
không lặp lại ở đây để tránh hai nguồn sự thật lệch nhau theo thời gian.

**Bàn giao sang Task 02:** phát hiện "các ngày còn lại thì sao" misroute
thành `GENERAL_MEDICAL_INFORMATION` trở thành baseline mở đầu cho capability
context/follow-up. AC/DoD, capability flag, câu hỏi thiết kế còn mở (có cần
thêm field durable mới vào `ConversationState` để nhớ range đã hỏi hay
không) nằm trong
[TASK-V2.5-002](../../../tasks/TASK-V2.5-002-schedule-range-followup.md).

---

## Quyết định CP0 đã chốt

**Đã chốt (không còn treo):**
- ~~`chat-bot-build/soul.md` cũ~~ → legacy/historical reference, không load
  vào V2.5 production; `soul_v3.md` là nguồn voice duy nhất (mục 1.3).
- ~~Case row ~123 (triệu chứng cấp tính)~~ → mở investigation an toàn độc
  lập ngay, ngoài phạm vi V2.5, không chờ CP0 đóng (Phần 3).
- ~~Model role của renderer~~ → thêm `ModelRole.RENDERER` +
  `AGENT_RENDERER_MODEL`/`OPENAI_RENDERER_API_KEY` riêng, tách khỏi
  `ModelRole.MAIN`; code hoá ở Task 04 (mục 1.4a).
- "Preflight PASS" → đổi thành "availability smoke PASS", chưa phải
  renderer-release benchmark (mục 1.4).
- Tab production V1 ngày 15/08/2026 và các số trích xuất tự động từ sheet là
  evidence lịch sử/định tính; baseline số liệu V2.5 sẽ được tạo lại ở local
  trong Task 01, nên không còn phụ thuộc vào việc suy diễn timestamp hay STT
  từ sheet.
- Đã duyệt thứ tự Task 01→04, naming capability flags, `ModelRole.RENDERER`
  và accounting theo per-call/role (mục 1.4a).

**CP0 exit:** đạt. Có thể mở branch
`feature/TASK-V2.5-001-schedule-tool-contract` cho CP1. Investigation an toàn
ở Phần 3 chạy độc lập, không phải điều kiện chặn CP0; mọi canary V2.5 vẫn phải
tuân thủ ràng buộc triệu chứng cấp tính ở Phần 3.
