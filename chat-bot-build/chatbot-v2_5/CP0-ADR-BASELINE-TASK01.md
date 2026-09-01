# CP0 — ADR ngắn + Baseline report + Task 01 (gộp một PR nhỏ)

> Nguồn thiết kế: [V2.5-DESIGN.md](./V2.5-DESIGN.md). Runbook: [CHECKPOINT.md](./CHECKPOINT.md) (CP0).
> Owner / Reviewer: **Dyo31122005 (một mình, kiêm PM/Architect/Release owner)**.
> Trạng thái: **Approved — CP0 exit đạt; Task 01 sẵn sàng mở branch.**

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

1. **Task 01 (tài liệu này):** nền tảng Phase 1 — không đổi tone/model, chỉ sửa
   một tool/evidence bug có reproduction thật + dựng skeleton
   `RenderableFactSlots` cho nhóm fact lịch/liều.
2. **Task 02 — context/follow-up:** ưu tiên trước renderer vì 14/14 case có
   nhãn lỗi trong baseline đều thuộc nhóm này (xem Phần 2).
3. **Task 03 — clarification.**
4. **Task 04 — renderer** (cần `gpt-5.6-luna` availability smoke PASS — xem
   1.4 — **và** `ModelRole.RENDERER` tách khỏi `ModelRole.MAIN` đã code hoá
   — xem 1.4a, blocker mới, phải xong trước khi Task 04 bắt đầu).

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
  (Phần 4, Task 01) và bọc `synthesize_read_only` bằng adapter mỏng.

**Chốt (không còn treo):** `chat-bot-build/soul.md` (bản cũ, 124 dòng) là
**legacy/historical reference** — viết cho một hệ thống/vòng build trước
Agent V2, không khớp kiến trúc hiện tại. **Không được load vào bất kỳ
production path nào của V2.5.** Giữ nguyên file (không xoá) vì có giá trị
lịch sử/tham chiếu, nhưng `soul_v3.md` là **nguồn voice duy nhất** cho
renderer V2.5 — không dùng song song hai bản soul để tránh trôi dạt.

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

**Nguồn evidence:** golden test dataset thật, 178 case, cột `Ky vong dau ra /
Tieu chi dung` đã gắn nhãn kết quả chạy ở local cho các version V1/V2
([link sheet](https://docs.google.com/spreadsheets/d/1wv-9p4oTuJ_0ErPCij4gh9eENLmd-qzbjMr8mWSOE3Y/edit?gid=0#gid=0)).
Toàn bộ trích dẫn dưới đây là câu hỏi tổng hợp/kiểm thử, không phải dữ liệu
bệnh nhân thật — an toàn để đưa vào baseline de-identified.

**Window và vai trò baseline đã chốt:** tab `15/08/2026` là lần owner tự chạy
trên **production V1**. Nó là evidence lịch sử hữu ích, nhưng không phải
baseline định lượng cho V2/V2.5. Các kết quả V1/V2 local trong sheet cũng chỉ
dùng để chọn pain point và reproduction ban đầu. Baseline chính thức của
V2.5 là một lần chạy lại toàn bộ golden suite trên **V2 hiện tại ở local**
ngay khi bắt đầu Task 01; report phải ghi commit SHA, config/model version,
golden-set version, exact command, timestamp và kết quả. Cùng bộ đánh giá
được chạy lại sau mỗi task ở local để so sánh trước/sau. Không có kết quả V2
production nào bị suy diễn từ tab V1.

**Tổng quan nhãn lỗi (trích xuất tự động, ±1 dòng do qua model tóm tắt —
cần đối chiếu thủ công trước khi dùng làm số liệu chính thức trong ADR):**

- `V2: GROUNDING_FAILURE`: ~11–13 case.
- `V2: FAILED/TOOL_ERROR`: ~3 case.
- Toàn bộ nhãn lỗi tập trung trong cụm multi-turn (STT ~103–156, các case
  "TR01/TR02/TR12/TR15"), tức đúng nhóm hội thoại nhiều lượt/follow-up —
  không rải rác ngẫu nhiên khắp 178 case.

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

**Evidence (row ~120, TR12):** người dùng nói "Không đúng" sau một câu trả
lời → `V2: GROUNDING_FAILURE` (hệ thống không biết hỏi lại đã sai chỗ nào).
TR12: bệnh nhân báo đau bụng "sau khi uống thuốc", rồi tự sửa lại "sau khi ăn
xiên nướng" — kỳ vọng cập nhật giả thuyết nguyên nhân (không giữ "do thuốc"),
không coi là triệu chứng mới.

**Golden/regression coverage:** chưa thấy case dạng "phủ định/sửa lại" trong
golden suite hiện có (`golden_evaluation.py`) ngoài sheet trên — cần thêm khi
build Task 03.

**Safety impact:** trung bình — TR12 có yếu tố triệu chứng (đau bụng), nhưng
route hiện tại là `PERSONAL_SYMPTOM`/`GENERAL_MEDICAL_INFORMATION`, không
phải Safety Domain redflag; không đổi Safety Domain ở pain point này.

**Tiêu chí đo sau thay đổi:** case "Không đúng" và case sửa nguyên nhân đạt
`TRUE_FOLLOWUP`/clarification tự nhiên thay vì lặp lại câu cũ hoặc bỏ qua
thông tin sửa.

### Pain point 3 — Tool/evidence mâu thuẫn và mất dấu vết hội thoại ở câu hỏi lịch/liều nhiều lượt (→ Task 01, Phase 1 nền tảng)

**Evidence (TR01, có reproduction rõ):**
- Hỏi lịch ngày 30/8 (lượt 6) trả về **kết quả trùng khớp** với lượt 5 (hỏi
  "hôm nay") — sheet ghi rõ "hai lượt mâu thuẫn là lỗi". Đây là bug tool/dữ
  liệu thật, không phải vấn đề giọng văn.
- "các ngày còn lại thì sao" (tham chiếu phạm vi còn lại của tuần) →
  `V2: FAILED/TOOL_ERROR`.
- "Tôi đã hỏi những vấn đề gì" (yêu cầu bot tự thuật lại hội thoại) →
  `V2: GROUNDING_FAILURE`.

**Vì sao chọn làm Task 01 thay vì Task 02/03:** đây là lỗi ở tầng
tool/evidence (đúng scope Phase 1 "Sửa contract mismatch có reproduction"),
**không đụng tới tone/model/renderer** — rủi ro thấp nhất, có reproduction cụ
thể nhất, và là nền cho `RenderableFactSlots` của nhóm fact lịch/liều mà cả
ba capability sau đều cần.

**Safety impact:** thấp-trung bình — đây là route lịch uống thuốc
(TODAY_DOSES/UPCOMING_DOSES/MEDICATION_HISTORY), không phải Safety Domain,
nhưng dữ liệu sai lịch có thể gây hiểu nhầm đã/chưa uống thuốc → cần regression
đầy đủ nhóm schedule/dose-status theo AC chung (mục 10, V2.5-DESIGN.md).

**Tiêu chí đo sau thay đổi:** case lượt 5 vs lượt 6 (hai ngày khác nhau) trả
kết quả khác nhau và đúng; "các ngày còn lại thì sao" không còn
`FAILED/TOOL_ERROR`.

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

## Phần 4 — Task 01: sửa tool/evidence mâu thuẫn lịch uống thuốc nhiều lượt

**AC/DoD:**
1. Reproduction: viết test tái tạo chính xác case "hôm nay" (lượt 5) vs
   "ngày 30/8" (lượt 6, một ngày cụ thể khác) trả cùng kết quả — xác định
   route nào trong `classify_intent`/`resolve_time_query`
   (`backend/agents/v2/time_query_engine.py`) gây trùng.
2. Fix contract mismatch tại gốc (không patch từng ngày cụ thể).
3. "các ngày còn lại thì sao" (tham chiếu phạm vi còn lại trong tuần đã hỏi)
   không còn trả `FAILED/TOOL_ERROR` — trả đúng phần còn lại của
   `TimeRange` đã resolve trước đó, hoặc `NEED_MORE_INFO` rõ ràng nếu không
   đủ ngữ cảnh (không phải lỗi cứng).
4. Dựng skeleton `RenderableFactSlots` cho nhóm fact lịch/liều (schedule,
   dose_status) trong request boundary — chỉ định nghĩa type, chưa cần
   renderer dùng tới (đó là Task 04).
5. Không đổi domain semantics, không clamp/retry âm thầm (theo Phase 1 scope).

**Capability flag:** không cần flag riêng — đây là bugfix + contract
skeleton nội bộ, không thay đổi hành vi patient-facing ngoài việc sửa đúng.

**Owner/cohort:** Dyo31122005; không cần cohort vì chưa bật patient-facing
change.

**Golden suite:** thêm 3 case trên (lượt 5/6 khác kết quả, "các ngày còn
lại", "tôi đã hỏi những vấn đề gì" — case cuối có thể vẫn ngoài scope Task 01
nếu thuộc conversation-history retrieval chứ không phải time-range, cần xác
nhận khi code) vào `scripts/agent_v2/golden/golden_set_v2.json` hoặc file
mới `golden_set_v2_5.json`.

**Metric query:** tỷ lệ pass 3 case golden mới; không có metric production
mới cần (chưa canary).

**Stop condition:** bất kỳ regression nào ở schedule/dose-status hiện có
(`TODAY_DOSES`/`UPCOMING_DOSES`/`MEDICATION_HISTORY` suite hiện tại) đang
pass mà sau fix lại fail.

**Rollback:** revert commit/PR của Task 01; không có Railway config nào bị
đổi (thuần code + test).

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
