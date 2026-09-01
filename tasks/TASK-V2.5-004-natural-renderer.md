# TASK-V2.5-004: Natural renderer có grounding (capability renderer)

**Domain:** Agent V2 model gateway / response rendering — capability renderer
**Owner:** Dyo31122005 + AI
**Sprint:** V2.5 timebox — chưa gán sprint chung
**Status:** CP1 đã đóng (PR #191, corrective, merged commit
`81f56950999b9697fb8a46ced913c8ea7e4c1e29`). **CP2 core mechanism đã code +
test thật qua 3 vòng sửa (bản 1 draft → bản 2 sửa theo owner review → bản 3
sửa theo owner review lần 2), trên branch
`feature/TASK-V2.5-004-renderer-cp2`, sẵn sàng mở PR với nhãn "core
mechanism"** — flag `AGENT_V2_5_RENDERER_ENABLED` mặc định `false` VÀ bị
giữ inert cứng ở route layer (mục "Tiến độ CP2 thực (bản 3)") cho tới khi
có PR wiring riêng theo response-type. Đây KHÔNG phải patient-facing
renderer — `RendererContext` còn tối giản, chỉ đủ cho structural safety
guarantee. Xem "Tiến độ CP2 thực (bản 1/2/3)" bên dưới cho toàn bộ chi
tiết đã làm/chưa làm.

## Mục tiêu

Dùng `gpt-5.6-luna` để diễn đạt lại các fact đã được backend xác minh (drug
info, schedule, suggested actions) thành câu trả lời tự nhiên hơn — đây là
capability trực tiếp giải quyết "quá máy móc" đã nêu từ đầu chương trình
V2.5. **Không** trao cho model quyền quyết định fact/route/safety — chỉ
diễn đạt trong boundary `ResponsePolicy`/`RenderableFactSlots` backend cấp.

Theo đúng chỉ đạo: task này dừng ở **CP1 (contract + benchmark)**, không
viết code runtime. CP2 (implementation) là task/PR riêng, chỉ bắt đầu sau
khi CP1 này được duyệt.

## 1. Benchmark thật `gpt-5.6-luna` (2026-09-01) — đã đạt renderer-release benchmark

Khác với "availability smoke" ở CP0 (4 lần gọi), đây là benchmark N=30 thật,
3 kịch bản renderer-shaped khác nhau xoay vòng, input tổng hợp không PHI:

| Chỉ số | Giá trị thật |
|---|---|
| Số lần gọi | 30/30 thành công, 0 lỗi |
| Output rỗng | 0/30 |
| Nghi ngờ không phải tiếng Việt | 0/30 |
| Latency min / P50 / P95 / max | 1251ms / 2303ms / **11267ms** / 12326ms |
| Token input trung bình | 160.3 |
| Token output trung bình | 85.7 |

**Nhận xét rủi ro cần ghi nhận:** P95 (11.3s) và max (12.3s) đều **trong**
`AGENT_MODEL_TIMEOUT_SECONDS=15` hiện tại nhưng biên độ không rộng — có đuôi
latency dài (P50 chỉ 2.3s, P95 gấp gần 5 lần). Nếu renderer thay thế lệnh
gọi `synthesize_read_only` hiện có (vốn dùng `gpt-5.4-mini`, chưa benchmark
so sánh latency), cần theo dõi tỷ lệ chạm ngưỡng timeout ở canary thật, không
giả định P95 phòng thí nghiệm này đại diện đúng tải production.

**Giá thật** (tra từ `developers.openai.com/api/docs/pricing`, chưa có trong
`AGENT_MODEL_PRICING_JSON` hiện tại — **rẻ hơn** `gpt-5.4-mini`):

| Model | Input/1M | Cached input/1M | Output/1M |
|---|---|---|---|
| `gpt-5.6-luna` (mới, cần thêm) | $0.20 | $0.02 | $1.20 |
| `gpt-5.4-mini` (đang dùng cho MAIN) | $0.75 | $0.075 | $4.50 |

Chi phí trung bình 1 lượt renderer (từ token benchmark thật):
`(160.3/1e6)×0.20 + (85.7/1e6)×1.20 ≈ $0.000135/lượt` — rẻ hơn đáng kể so
với `gpt-5.4-mini` ở cùng khối lượng token.

**Kết luận benchmark: PASS, đủ điều kiện coi là renderer-release benchmark**
(khác "availability smoke" ở CP0) — điều kiện còn thiếu trước đây
("P95 ≥30 lần gọi thật", "giá thật") nay đã có.

## 2. `ModelRole.RENDERER` — contract chốt (chưa code)

Đúng theo ADR delta 1.3a/1.4a (`CP0-ADR-BASELINE-TASK01.md`), chốt cụ thể để
CP2 code thẳng, không phải thiết kế lại:

```python
# backend/agents/v2/model_gateway.py
class ModelRole(StrEnum):
    ROUTER = "router"
    MAIN = "main"
    FALLBACK = "fallback"
    EMBEDDING = "embedding"
    JUDGE = "judge"
    RENDERER = "renderer"          # MỚI

# backend/config.py — theo đúng pattern agent_main_model/openai_main_api_key
agent_renderer_model: str = "gpt-5.6-luna"
openai_renderer_api_key: str = ""
# .env.example: AGENT_RENDERER_MODEL, OPENAI_RENDERER_API_KEY
```

`build_model_workloads()` thêm entry `(ModelRole.RENDERER, "agent_renderer_model",
"openai_renderer_api_key", "OPENAI_RENDERER_API_KEY")` — copy nguyên pattern
đã có cho MAIN, không phát minh cơ chế mới.

`OpenAIModelGateway.synthesize_read_only` đổi `workload = self._workloads[ModelRole.MAIN]`
→ `self._workloads[ModelRole.RENDERER]`. `plan_read_only` **giữ nguyên**
`ModelRole.MAIN` — không đổi. `runtime.py`: lượt synthesis đổi
`role=ModelRole.MAIN` → `role=ModelRole.RENDERER` trong `record_model(...)`
và span attribute, dùng đúng model name của workload renderer (không phải
`self._model_name`, vẫn là model của planner).

**Vì sao không tạo renderer mới:** `synthesize_read_only` đã đúng hình dạng
(verified evidence → Vietnamese reply, không có quyền gọi tool ở turn này),
đã có fail-closed path (`EmptySynthesisError`) — quyết định này đã chốt từ
CP0 (mục 1.2), nhắc lại ở đây để CP2 không phải tra ngược.

## 3. Pricing/accounting — contract chốt (chưa code)

```json
// AGENT_MODEL_PRICING_JSON, thêm entry (giữ nguyên các entry cũ)
"gpt-5.6-luna": {"input_per_million": 0.20, "cached_input_per_million": 0.02, "output_per_million": 1.20}
```

Theo đúng ADR delta 1.4a điểm 7: `AgentRunSpan` model events là nguồn
breakdown theo từng call (`model_role`, `model`, token, latency, estimated
cost). Khi một `AgentRun` dùng hơn một model (planner=`gpt-5.4-mini` +
renderer=`gpt-5.6-luna` trong cùng run), `AgentRun.model` ghi `MULTI_MODEL`;
tổng cost = tổng `CostEstimate` theo từng call/role, không lấy aggregate
`RunMetrics` rồi áp giá một model. Admin Monitoring đọc breakdown theo
`AgentRunSpan` khi filter/báo cáo model.

**Việc CP2 cần làm cụ thể ở đây** (chưa làm trong CP1 này):
- Thêm entry JSON trên vào `.env.example`/Railway config thật.
- Audit `runtime.py`/`observability.py` nơi `AgentRun.model` được set — sửa
  logic phát hiện multi-model, không giả định "cả run một model" như hiện
  tại (kiểm tra đã có sẵn chỗ set `AgentRun.model` = model MAIN cho toàn bộ
  run hay chưa, cần đọc code thật trước khi sửa — **chưa audit trong CP1
  này**, ghi nhận là việc CP2 phải làm trước khi coi capability này sẵn sàng
  canary).

## 4. `RenderableFactSlots` — contract chốt (chưa code)

Tối giản, chỉ đủ dùng cho `synthesize_read_only`, không import contract V3
(đúng ranh giới đã chốt ở CP0 mục 1.3/6):

```python
# backend/agents/v2/response_policy.py (module MỚI, chưa tạo)
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum


class Answerability(StrEnum):
    ANSWERABLE = "ANSWERABLE"
    NEED_MORE_INFO = "NEED_MORE_INFO"
    NEED_DOCTOR = "NEED_DOCTOR"


@dataclass(frozen=True)
class ResponsePolicy:
    """Backend-owned: quyền nói gì/cấm gì. Không tự mang fact value (V2.5-
    DESIGN.md mục 5) -- không chứa raw tool payload, patient ID, actor ID,
    raw conversation history, hay prompt instruction từ client."""
    route_category: str
    answerability: Answerability
    allowed_fact_refs: tuple[str, ...]
    prohibited_claim_categories: tuple[str, ...]
    clarification_target: str | None
    handoff_state: str | None
    suggested_action_refs: tuple[str, ...]
    style_profile: str = "soul-v3"  # soul_v3.md, reuse trực tiếp (CP0 mục 1.3)


@dataclass(frozen=True)
class RenderableFactSlots:
    """Fact value ĐÃ RENDER SẴN, dạng chuỗi verbatim-safe -- không phải dữ
    liệu thô đưa cho model tự diễn giải. Các field ứng với "protected fact"
    (mục 4a) PHẢI được backend/template render nguyên văn trước khi tới đây;
    model không bao giờ tạo lại chính các chuỗi này. KHÔNG được copy nguyên
    trạng vào log/trace/audit metadata (V2.5-DESIGN.md mục 5). Field tối
    giản cho phạm vi CP2 đầu (drug info + schedule) -- mở rộng thêm field
    khi có capability mới cần, không suy đoán trước."""
    drug_name: str | None = None
    drug_allowed_claims: tuple[str, ...] = ()
    dose_schedule_summary: str | None = None   # đã format sẵn, KHÔNG phải raw DB row
    dose_status_summary: str | None = None
    provenance: str = ""
```

**Câu hỏi thiết kế đã chốt:** `RenderableFactSlots` sống trong REQUEST
BOUNDARY (tham số truyền vào `synthesize_read_only`, không phải field trên
`OrchestrationRequest`/`ConversationState` — không cần durable, không cần
version bump kiểu Task 02). Adapter mỏng quanh `synthesize_read_only` (hàm
mới `_build_renderable_fact_slots(evidence: tuple[SynthesisEvidence, ...]) ->
RenderableFactSlots`) chuyển `SynthesisEvidence` hiện có (đã tồn tại, đang
dùng cho prompt tự do) thành slots có cấu trúc — **đây là phần CP2 cần code
thật**, CP1 chỉ chốt shape.

### 4a. Backend assembly contract — Luna chỉ tạo `free_prose`, không tự viết lại protected fact

**Sửa chính xác so với bản CP1 gốc:** bản gốc mô tả renderer trả về "câu trả
lời tự nhiên" như một khối text duy nhất, dựa vào prompt instruction để model
không đổi fact — đây là bảo đảm YẾU (phụ thuộc model tuân thủ), không phải
bảo đảm cấu trúc. Chốt lại theo đúng yêu cầu: model không bao giờ output
chính văn bản của một protected fact.

- **Protected fact** = mọi field trên `RenderableFactSlots` ứng với claim
  nhạy cảm (`drug_name`, `dose_schedule_summary`, `dose_status_summary`,
  bất kỳ field tương lai nào cùng lớp) — các chuỗi này do **backend/template
  render nguyên văn**, không đi qua Luna dưới bất kỳ hình thức nào.
- **Luna chỉ tạo `free_prose`** — một trường mới, riêng biệt, chỉ chứa câu
  dẫn/chuyển ý/empathy/cấu trúc trong phạm vi `ResponsePolicy` cho phép.
  `ModelSynthesis`/hàm renderer CP2 trả về kiểu có trường `free_prose: str`
  (đổi tên/tách khỏi `response: str` hiện tại của `ModelSynthesis`), không
  còn là "toàn bộ câu trả lời cuối".
- **Backend lắp ráp (assembly), không phải model:** một hàm mới
  `_assemble_reply(policy, fact_slots, free_prose) -> str` ghép `free_prose`
  với các chuỗi protected fact đã render sẵn theo vị trí cố định (vd
  `free_prose` mở đầu/dẫn dắt, theo sau là khối fact verbatim) — đây là
  string composition tất định ở backend, không phải model tự chèn lại fact
  vào câu nó sinh ra. Vì Luna chưa từng nhìn thấy/tạo lại chuỗi fact, nó
  **không có khả năng** rewrite/paraphrase/bỏ sót fact — đây là bảo đảm cấu
  trúc, không phải bảo đảm hành vi model.
- Đây là phần **CP2 phải code thật** (đổi contract `synthesize_read_only`,
  thêm `_assemble_reply`); CP1 chỉ chốt hợp đồng ở trên.

## 5. Fallback — contract chốt (không đổi cơ chế, bổ sung test plan cụ thể)

Không đổi cơ chế so với ADR delta 1.5: timeout/invalid renderer output đi
qua path fail-closed đã có (`EmptySynthesisError` → `RunStatus.FAILED` với
safe fallback text, `runtime.py`). CP2 chỉ mở rộng input/output shape của
lệnh gọi (nhận `ResponsePolicy`+`RenderableFactSlots`, trả `free_prose`
thay vì prompt string tự do/toàn bộ reply), không đổi cơ chế fail-closed
này.

**Bổ sung: evidence kế hoạch/test cụ thể cho timeout và `EmptySynthesisError`
ở ROLE RENDERER (CP1 chốt kế hoạch, CP2 viết/chạy thật):**

1. Test: client cho `ModelRole.RENDERER` raise timeout (giả lập, không gọi
   API thật) → `synthesize_read_only` (hoặc hàm CP2 kế thừa nó) phải để lỗi
   này đi qua đúng path đã có, kết quả cuối là `RunStatus.FAILED` với fixed
   fallback text — không phải `free_prose` rỗng lọt qua `_assemble_reply`.
2. Test: `free_prose` rỗng/whitespace-only → raise `EmptySynthesisError`
   (đúng hành vi hiện tại của `synthesize_read_only` với `response` rỗng,
   áp dụng y hệt cho `free_prose` rỗng) → cùng path fail-closed ở trên.
3. Test: `_assemble_reply` không bao giờ được gọi khi lượt renderer
   FAILED/timeout — protected fact không được rò rỉ ra ngoài qua một đường
   khác khi model call chính thất bại.
4. Không tăng số lượt gọi khi retry: **`AGENT_MAX_MODEL_CALLS` vẫn giữ
   nguyên giá trị mặc định hiện tại là `2`** (`backend/config.py:435`,
   xác nhận thật, không đổi bởi task này) — renderer thay thế đúng lượt
   synthesis đã có trong ngân sách này, không thêm lượt gọi mới, không tăng
   retry để "cứu" một free_prose rỗng.

## 6. Golden suite "prose tự do" — thiết kế case (chưa viết test thật)

Đúng yêu cầu bắt buộc từ CHECKPOINT.md CP1 và V2.5-DESIGN.md mục 8 điểm 6 —
đây là **đảm bảo kỹ thuật quan trọng nhất của V2.5**. Thiết kế 4 nhóm case
tối thiểu cho CP2 (mỗi case: đưa renderer một `RenderableFactSlots` KHÔNG
chứa field X, rồi kiểm tra output KHÔNG chứa claim thuộc loại X ở đâu cả,
kể cả trong câu dẫn/chuyển ý):

1. **Không chèn liều/giờ ngoài field:** `dose_schedule_summary=None` (không
   có lịch nào được cấp) → output không được tự bịa ra bất kỳ giờ/liều nào,
   kể cả "có thể bạn nên uống vào buổi sáng".
2. **Không chèn dose status ngoài field:** `dose_status_summary=None` →
   output không được nói "bạn đã uống"/"bạn chưa uống" dưới bất kỳ hình
   thức nào.
3. **Không chèn medication identity chưa xác nhận:** `drug_name=None`
   nhưng evidence gốc (SynthesisEvidence) có nhắc một tên thuốc mơ hồ →
   output không được khẳng định đây là thuốc cụ thể nào.
4. **Không chèn handoff state tự tạo:** không có `handoff_state` nào được
   cấp → output không được nói "mình đã chuyển cho bác sĩ"/"bác sĩ sẽ liên
   hệ" dưới bất kỳ hình thức nào.

**Bổ sung — nhóm dương (positive), bắt buộc song song với 4 nhóm âm ở
trên, không thay thế:** khi một slot CÓ giá trị, chuỗi đó phải xuất hiện
**nguyên văn** trong reply cuối cùng (`_assemble_reply`'s output) — không bị
model diễn giải lại/rewrite/paraphrase. Vì kiến trúc mục 4a (Luna không bao
giờ tạo lại chính chuỗi fact) đảm bảo điều này BẰNG CẤU TRÚC, test dương ở
đây thực chất là test hồi quy cho chính cơ chế `_assemble_reply` (fact
verbatim có mặt đúng vị trí, không bị cắt/nuốt khi ghép với `free_prose`),
không phải test hành vi model. Viết tối thiểu 1 case dương cho mỗi trong 4
nhóm trên (case gương: cùng field đó CÓ giá trị thay vì `None`).

**Cách kiểm (CP2 phải làm thật, không phải mô tả suông):** vì đây là prose
tự do, không thể check bằng string match đơn giản cho mọi biến thể — CP2
cần định nghĩa danh sách cụm từ/regex cấm cho từng nhóm (vd nhóm 2: "đã
uống", "chưa uống", "uống rồi", "bỏ lỡ" xuất hiện mà không có
`dose_status_summary`) làm bộ lọc tất định tối thiểu, **không phải LLM-judge
duy nhất** (theo đúng V2.5-DESIGN.md mục 8: "V2.5 không hứa semantic
validation cho mọi claim trong prose tự do" — bộ lọc regex là backstop hẹp,
không phải bảo đảm ngữ nghĩa đầy đủ).

## Acceptance Criteria cho CP2 (chưa làm — liệt kê để bàn giao)

- [ ] Thêm `ModelRole.RENDERER` + settings + `build_model_workloads` entry.
- [ ] Đổi `synthesize_read_only` sang dùng workload RENDERER; `runtime.py`
  ghi đúng role/model cho lượt synthesis.
- [ ] Audit + sửa `AgentRun.model`/`MULTI_MODEL` logic (mục 3 ở trên).
- [ ] Thêm entry pricing JSON cho `gpt-5.6-luna`.
- [ ] Tạo module `response_policy.py` với `ResponsePolicy`/`RenderableFactSlots`
  đúng shape ở mục 4; adapter `_build_renderable_fact_slots`.
- [ ] `synthesize_read_only` nhận `ResponsePolicy`+`RenderableFactSlots`,
  trả `free_prose` (không phải toàn bộ reply) — vẫn không có `tools=` (giữ
  nguyên bảo đảm "không gọi tool ở turn này").
- [ ] Thêm `_assemble_reply(policy, fact_slots, free_prose) -> str` (mục 4a)
  — backend ghép protected fact verbatim với `free_prose`, model không bao
  giờ output chính chuỗi fact.
- [ ] Golden suite "prose tự do": 4 nhóm âm + 4 nhóm dương tương ứng ở mục 6
  viết thật, chạy thật.
- [ ] Test timeout/`EmptySynthesisError` cho role RENDERER (4 case ở mục 5)
  viết thật, chạy thật.
- [ ] Xác nhận `AGENT_MAX_MODEL_CALLS` không đổi (vẫn 2) sau khi wiring
  xong — regression test nếu có sẵn cơ chế đếm model calls trong test suite.
- [ ] Capability flag `AGENT_V2_5_RENDERER_ENABLED`, mặc định `false`, độc
  lập với Task 02/03.
- [ ] Bắt đầu áp dụng cho đúng nhóm response type "Ưu tiên natural renderer"
  theo bảng V2.5-DESIGN.md mục 7 (follow-up/clarification/grounding-decline/
  out-of-scope/drug-info low-risk) — **không** áp dụng cho
  emergency/safety/handoff/timeout theo đúng bảng đó.

## Tiến độ CP2 thực (bản 1) — draft đầu, cập nhật khi code, không phải kế hoạch

**Đã làm, có test thật (TDD: RED xác nhận trước, GREEN sau), branch
`feature/TASK-V2.5-004-renderer-cp2`:**

- `ModelRole.RENDERER` (`backend/agents/v2/model_gateway.py`) + settings
  `agent_renderer_model`/`openai_renderer_api_key` (`backend/config.py`,
  `.env.example`) + `build_model_workloads()` entry — `tests/
  test_agent_v2_model_gateway.py`.
- Pricing JSON entry `gpt-5.6-luna` trong `.env.example`'s
  `AGENT_MODEL_PRICING_JSON` mẫu.
- Module mới `backend/agents/v2/response_policy.py`: `Answerability`,
  `ResponsePolicy` (`style_profile="soul-v3"`), `RenderableFactSlots`,
  `assemble_reply(policy, fact_slots, free_prose) -> str`,
  `build_renderable_fact_slots(evidence) -> RenderableFactSlots` — `tests/
  test_agent_v2_response_policy.py`, gồm đủ golden suite "prose tự do" 4
  nhóm âm + 4 nhóm dương ở mục 6 (viết thật dưới dạng unit test tất định
  chống lại `assemble_reply`, đúng tinh thần mục 6: đây là test hồi quy cho
  cơ chế backend assembly, không phải LLM-judge).
- `ModelSynthesis.response` đổi tên thành `ModelSynthesis.free_prose` (đúng
  mục 4a) — rà toàn bộ 15 file test + 2 file backend dùng field này, xác
  nhận hành vi không đổi khi không có protected fact (assemble_reply là
  passthrough).
- `OpenAIModelGateway.synthesize_read_only` opt-in `policy`/`fact_slots`
  (`None` mặc định) chuyển hẳn sang workload `RENDERER`; `plan_read_only`
  không đổi (`MAIN`) — `tests/test_agent_v2_model_gateway.py`.
- `runtime.py` (`ReadOnlyAgentRuntime`): tham số mới `renderer_enabled`/
  `renderer_model_name`; khi bật, build `RenderableFactSlots` từ evidence
  thật, gọi `assemble_reply` để tạo final text, ghi đúng
  `role=ModelRole.RENDERER` + model renderer vào span/`record_model` (khi
  tắt, hành vi giống hệt trước task này — có test non-regression khóa việc
  này) — `tests/test_agent_v2_runtime.py`.
- Test timeout/`EmptySynthesisError` ở role RENDERER (4 case mục 5, bao gồm
  test trực tiếp bằng cách "poison" `assemble_reply` để chứng minh nó không
  bao giờ được gọi khi lượt renderer FAILED) + test khóa
  `AGENT_MAX_MODEL_CALLS` vẫn là `2` — `tests/test_agent_v2_runtime.py`.
- Audit + sửa `AgentRun.model`/`MULTI_MODEL` (mục 3, việc CP1 ghi rõ CHƯA
  làm): `_persist_durable_trace` giờ suy ra model/cost từ chính các
  `agent_model.completed` event thật của run đó (không còn áp giá 1 model
  lên tổng token toàn run) — model khác nhau giữa các lượt gọi → ghi
  `"MULTI_MODEL"`; buffer mất/evict dù `model_calls>0` → suy thoái trung
  thực về `NOT_AVAILABLE` (không bịa model/giá) — `tests/
  test_agent_v2_task004_multi_model_cost.py` (case 2 model thật, 1 model
  thật, buffer mất, model không có giá, 0 lượt gọi không đổi).
- Wiring 2 route thật (`/agent/v2/read-only`, `/agent/v2/orchestrate` —
  route sau là entry point production) đọc `AGENT_V2_5_RENDERER_ENABLED`/
  `AGENT_RENDERER_MODEL` từ settings thật, không phải giá trị cứng.
- Xác nhận không hồi quy: toàn bộ file test agent_v2 liên quan
  (~1194 test qua `pytest -k "agent_v2 or response_policy"`) xanh; 18 lỗi
  còn lại đã xác nhận từ trước là pre-existing (`chat_messages`/Postgres
  không chạy local), re-xác nhận qua `git stash` không đổi. Lint (`ruff
  check`) sạch trên toàn bộ file trong diff.

**Sai lệch "additive full evidence" đã bị owner bác bỏ — sửa lại đúng
hướng trước PR:**

Bản nháp CP2 đầu tiên cho `synthesize_read_only` nhận thêm `policy`/
`fact_slots` (optional, mặc định `None`) NHƯNG vẫn giữ nguyên `evidence`
thô đầy đủ trong prompt gửi Luna "để giữ ngữ cảnh". Owner chỉ ra đúng: đây
là lỗi thật, không phải điều chỉnh an toàn — nếu Luna vẫn thấy `evidence`
thô (bao gồm chính giá trị `drug_name`/tên thuốc trong `search_drug`/
`get_drug_info`), thì bảo đảm "model chưa từng nhìn thấy chuỗi fact nên
không thể viết lại nó" (mục 4a) chỉ còn là lý thuyết — model vẫn hoàn toàn
có khả năng paraphrase/restate fact ngay từ evidence thô, chỉ là được
*yêu cầu* đừng làm vậy qua prompt instruction (đúng loại bảo đảm YẾU mà
mục 4a đã minh định phải loại bỏ). Quyết định đã sửa:

1. **Loại bỏ `evidence` khỏi input của lượt renderer hoàn toàn.** Thay bằng
   `RendererContext` — allowlist tối giản, chỉ chứa tín hiệu low-risk
   không tự nó cấu thành claim nào (vd `has_findings: bool`) — không một
   giá trị cụ thể nào (tên thuốc, giờ, trạng thái liều) lọt vào prompt, kể
   cả khi slot tương ứng CÓ giá trị. `build_renderer_context(evidence) ->
   RendererContext` là adapter allowlist (khai báo field nào an toàn, một
   field mới mặc định KHÔNG được đưa vào cho tới khi xác nhận rõ ràng là
   an toàn) — không phải denylist trên `evidence`.
2. **Thêm `validate_free_prose(policy, fact_slots, free_prose)` làm
   regex-backstop thật**, chạy trên chính output của Luna trước khi cho
   phép `assemble_reply` chạy: nếu `free_prose` chứa dấu hiệu thuộc bất kỳ
   category nào trong `policy.prohibited_claim_categories` (dose_time,
   dose_status, medication_identity, handoff_state) thì FAIL-CLOSED —
   không gọi `assemble_reply`, đi qua đúng path fail-closed đã có (raise
   lỗi mới, phân loại như `EmptySynthesisError`). Đây là backstop tất định
   thứ hai, độc lập với việc RendererContext không rò rỉ fact ở input —
   phòng trường hợp model tự "đoán"/hallucinate một claim nhạy cảm dù
   không được cấp dữ liệu.
3. **`ResponsePolicy.prohibited_claim_categories` trở thành input được
   thực thi thật** — `validate_free_prose` tra cứu chính xác các category
   trong field này (không hardcode trong hàm), nên một `ResponsePolicy`
   khác trong tương lai có thể hợp lệ hoá bớt/thêm category mà không cần
   sửa `validate_free_prose`. `_default_response_policy()` (nhánh tool-loop
   chung, CP2 này) chốt cả 4 category luôn bị cấm — free_prose theo thiết
   kế không bao giờ cần nói tới bất kỳ category nào trong 4 category đó.
4. **`search_drug` mơ hồ (nhiều `items`, không có `unique_match_legacy_
   drug_id` khớp duy nhất) không được tạo `drug_name`.** Bản nháp đầu đọc
   sai field (`data.get("name")` trên toàn bộ payload `search_drug`, trong
   khi shape thật là `{items: [...], unique_match_legacy_drug_id}` —
   `backend/agents/v2/tools.py::SearchDrugOutput`) — sửa lại đọc đúng
   `unique_match_legacy_drug_id`, chỉ set `drug_name` khi field này khớp
   đúng một `item`. Các tên ứng viên bị loại được giữ ở
   `RenderableFactSlots.rejected_identity_candidates` (không đưa vào
   `RendererContext`, chỉ dùng nội bộ cho `validate_free_prose` đối chiếu
   hậu kiểm).

## Tiến độ CP2 thực (bản 2) — sau khi owner bác bỏ sai lệch "additive full evidence"

**Code thật + test thật (RED xác nhận trước, GREEN sau), cùng branch
`feature/TASK-V2.5-004-renderer-cp2`:**

- `RendererContext(has_findings: bool = False)` (module mới trong
  `response_policy.py`) + `build_renderer_context(evidence) ->
  RendererContext` — allowlist thật, không phải denylist trên `evidence`;
  field duy nhất hiện tại (`has_findings`) không tự nó cấu thành claim nào.
  Có test khóa cấu trúc: không field nào trên `RendererContext` được trùng
  tên với field protected trên `RenderableFactSlots`.
- `RenderableFactSlots.rejected_identity_candidates: tuple[str, ...] = ()`
  field mới — không bao giờ vào `RendererContext`/prompt, chỉ dùng nội bộ
  cho `validate_free_prose`.
- `build_renderable_fact_slots` sửa lại đọc đúng shape thật của
  `search_drug` (`items`/`unique_match_legacy_drug_id` —
  `backend/agents/v2/tools.py::SearchDrugOutput`), không còn đọc nhầm field
  `name` phẳng không tồn tại trên payload thật; ambiguous result (nhiều
  `items`, không có `unique_match_legacy_drug_id` khớp, hoặc match id không
  ứng với item nào) không bao giờ set `drug_name`.
- `validate_free_prose(policy, fact_slots, free_prose) -> (bool,
  violated_categories)` (module mới trong `response_policy.py`) — regex
  backstop cho `dose_time`/`dose_status`/`handoff_state`, đối chiếu chuỗi
  cho `medication_identity` (so với `rejected_identity_candidates`); CHỈ
  kiểm category có trong `policy.prohibited_claim_categories` (input được
  thực thi thật, không hardcode).
- `OpenAIModelGateway._synthesize_free_prose` viết lại hoàn toàn: prompt gửi
  Luna giờ chỉ chứa `RendererContext.has_findings` +
  `policy.route_category`/`policy.answerability` — không còn evidence thô,
  không còn "known_facts" rút từ fact_slots. Sau khi nhận `free_prose`, gọi
  `validate_free_prose` trước khi trả kết quả; vi phạm → raise
  `ProhibitedClaimLeakError` (class mới, sibling của `EmptySynthesisError`,
  không kế thừa để giữ phân loại lỗi tách biệt).
- `runtime.py`: `_default_response_policy()` giờ chốt cả 4
  `prohibited_claim_categories` luôn bật; thêm `ERROR_CODE_PROHIBITED_CLAIM_
  LEAK` + nhánh phân loại `isinstance(exc, ProhibitedClaimLeakError)` trong
  `_synthesize_with_limits`, đi qua đúng path fail-closed có sẵn (không
  thêm cơ chế mới).
- Test thật cho toàn bộ 4 invariant owner yêu cầu:
  1. Prompt Luna không chứa sentinel `drug_name`/`dose_schedule_summary`/
     `dose_status_summary`/`handoff_state` — kể cả khi slot CÓ giá trị
     (4 test riêng, mỗi test 1 category, `tests/test_agent_v2_model_
     gateway.py`).
  2. Model giả trả claim nhạy cảm khi không được cấp dữ liệu → bị reject ở
     cả 2 tầng: `validate_free_prose` (unit, `tests/
     test_agent_v2_response_policy.py`) và toàn bộ runtime end-to-end
     (`tests/test_agent_v2_model_gateway.py`,
     `tests/test_agent_v2_runtime.py` — bao gồm test "poison
     `assemble_reply`" chứng minh nó không được gọi khi leak xảy ra).
  3. `search_drug.items` mơ hồ không tạo `drug_name` (2 test: nhiều item
     không match, và match id không tồn tại trong items — `tests/
     test_agent_v2_response_policy.py`).
  4. `ResponsePolicy.prohibited_claim_categories` là input được thực thi
     thật: test khóa `_default_response_policy()` liệt kê đủ 4 category,
     cộng 1 test chứng minh policy rỗng category thì `validate_free_prose`
     không reject gì (chứng minh field này thực sự được đọc, không phải
     hardcode trong hàm).
- Sửa fixture cũ dùng sai shape `search_drug` (test giả lập `{"name":
  "Paracetamol"}` phẳng, không đúng payload thật) ở
  `tests/test_agent_v2_runtime.py` và `tests/test_agent_v2_response_
  policy.py` — cùng gốc lỗi owner chỉ ra ở mục 4 trên.

**Bằng chứng thật đã chạy (sau bản 2):**

- `tests/test_agent_v2_response_policy.py` + `tests/
  test_agent_v2_model_gateway.py` + `tests/test_agent_v2_runtime.py`:
  77/77 pass.
- Toàn bộ `pytest -k "agent_v2 or response_policy"`: 1214/1214 pass (không
  tính 18 lỗi pre-existing đã re-xác nhận qua `git stash`, và 5 test
  Postgres-only skip do không có DB local).
- Golden `--deterministic-only` (15 case, 0 lượt gọi model — schedule/
  triage/safety/out-of-scope/auth): **15/15 PASS**, regression gate PASS —
  chạy thật sau toàn bộ sửa đổi trên, xác nhận các nhánh tất định không bị
  ảnh hưởng.
- `ruff check` sạch trên toàn bộ file backend + test trong phạm vi sửa đổi
  của cả 2 vòng (draft đầu + bản sửa theo yêu cầu owner).

## Tiến độ CP2 thực (bản 3) — 3 sửa owner yêu cầu trước PR

**1. Regex `dose_time` quá rộng, đã sửa.** Bản 2 dùng
`\b(giờ|sáng|trưa|chiều|tối|liều)\b` — một từ chỉ buổi trong ngày đơn thuần
(vd "Chúc bạn một buổi tối tốt lành") bị reject sai, sẽ khiến renderer fail
với câu tiếng Việt hoàn toàn bình thường. Sửa: `dose_time` giờ chỉ bắt (a)
giờ đồng hồ cụ thể (`\d{1,2}\s*(giờ|h)\b`, vd "8 giờ", "20h") HOẶC (b) một
từ chỉ buổi trong ngày xuất hiện GẦN (trong 30 ký tự) một động từ liều
thuốc (uống/dùng thuốc) — "liều" đứng một mình vẫn luôn bị bắt (từ đủ đặc
thù, không phổ biến trong prose thông thường). Test mới: 1 test khẳng định
câu benign PASS, 3 test khẳng định các dạng leak thật (giờ+uống gần nhau
không có số, giờ đồng hồ trần không có "uống" gần đó, "liều" đứng một
mình) vẫn bị reject — `tests/test_agent_v2_response_policy.py`.

**2. `medication_identity` giờ chặn cả `fact_slots.drug_name` đã xác
nhận, không chỉ candidate mơ hồ.** Rủi ro thật owner chỉ ra: dù
`RendererContext` không đưa `drug_name` vào input model, prompt vẫn giữ
nguyên văn tin nhắn gốc của người dùng ("Original request: {message}") —
nếu người dùng đã gõ tên thuốc, model vẫn có thể đọc thấy và lặp lại trong
`free_prose`. Sửa `validate_free_prose`: category `medication_identity`
giờ đối chiếu `free_prose` với CẢ `fact_slots.drug_name` (đã xác nhận) LẪN
`fact_slots.rejected_identity_candidates` (chưa xác nhận) — model không
bao giờ được phép tự nói tên thuốc, xác nhận hay chưa. Test adversarial
mới: model lặp lại đúng `drug_name` đã xác nhận → bị reject; test âm đi
kèm: prose không nhắc tên nào (xác nhận hay ứng viên) thì không bị flag —
`tests/test_agent_v2_response_policy.py`.

**3. Flag renderer giờ luôn inert ở cả 2 route production, bất kể giá trị
`AGENT_V2_5_RENDERER_ENABLED`.** Rủi ro thật owner chỉ ra: cơ chế
`ReadOnlyAgentRuntime.renderer_enabled` áp dụng cho TOÀN BỘ nhánh tool-loop
chung (mọi câu trả lời có gọi tool: drug info, đơn thuốc, dose status...),
rộng hơn nhiều so với phạm vi đã duyệt (chỉ các response-type cụ thể ở
V2.5-DESIGN.md mục 7). Nếu bật `AGENT_V2_5_RENDERER_ENABLED=true` trên
Railway lúc này (trước khi có eligibility gate theo response-type), nó sẽ
đổi hành vi rộng hơn phạm vi đã review. Sửa: thêm hàm
`_renderer_runtime_kwargs(settings)` (`backend/api/agent_v2_routes.py`) —
LUÔN trả `renderer_enabled=False` bất kể `settings.agent_v2_5_renderer_
enabled`, dùng ở cả `/agent/v2/read-only` và `/agent/v2/orchestrate` thay
cho việc đọc flag trực tiếp. `renderer_model_name` vẫn đọc từ settings
thật (vô hại khi `renderer_enabled=False` — runtime không bao giờ đọc tới)
để không phải nối dây lại khi eligibility gate được thêm sau này. Test:
`_renderer_runtime_kwargs` luôn trả `renderer_enabled=False` dù flag
settings là `True` hay `False` — `tests/test_agent_v2_route.py`. Từ đây,
việc bật `AGENT_V2_5_RENDERER_ENABLED` trên Railway (dù vô tình hay cố ý)
không có bất kỳ tác dụng nào tới hành vi thật cho tới khi một PR wiring
riêng thêm eligibility gate và bỏ hardcode `False` này.

**4. `medication_identity` chuyển sang so khớp Unicode-normalized +
casefold, không còn case-sensitive.** Rủi ro thật owner chỉ ra: `drug_name=
"Paracetamol"` nhưng Luna viết "paracetamol" (chữ thường) sẽ lọt qua phép
so khớp `in` case-sensitive cũ, dù đây vẫn đúng là model tự nhắc identity
từ tin nhắn gốc người dùng. Sửa: thêm `_normalize_for_identity_match(text)`
(`unicodedata.normalize("NFC", text).casefold()`) áp dụng cho cả
`free_prose` và từng candidate (`drug_name`/`rejected_identity_candidates`)
trước khi so khớp substring — không đổi kiến trúc, không mở rộng scope,
chỉ sửa chính phép so khớp. Test adversarial mới: model viết thường hoàn
toàn ("paracetamol"/"vitamin b1") vẫn bị reject — `tests/
test_agent_v2_response_policy.py`.

**Ghi chú phạm vi PR (owner đã nêu rõ):** `RendererContext(has_findings)`
hiện tại chỉ đủ cho cơ chế an toàn cốt lõi (structural no-fact-leak
guarantee) — CHƯA đủ để renderer diễn giải drug-info một cách hữu ích cho
người dùng thật (không có thông tin gì ngoài "có tìm thấy hay không"). Vì
vậy PR cho CP2 này được gắn nhãn **"core mechanism"**, KHÔNG phải
"patient-facing renderer" — chưa sẵn sàng để bật cho người dùng thật kể cả
khi flag được set true (vì còn bị giữ inert ở mục 3, và vì `RendererContext`
còn quá tối giản để tạo prose hữu ích ở mục này). Response-type wiring
(mở rộng `RendererContext`, thêm eligibility gate, áp dụng đúng bảng mục 7)
là **increment tiếp theo**, sau khi core mechanism này được review/merge —
không gộp chung vào PR này.

**Bằng chứng thật đã chạy (sau bản 3):**

- `tests/test_agent_v2_response_policy.py`: 38/38 pass.
- `tests/test_agent_v2_route.py`: 20/20 pass (3 test mới cho
  `_renderer_runtime_kwargs`).
- Toàn bộ `pytest -k "agent_v2 or response_policy"`: 1222/1222 pass (cùng
  18 lỗi pre-existing, cùng 5 skip Postgres-only — không đổi).
- Golden `--deterministic-only`: 15/15 PASS lần nữa sau bản 3.
- `ruff check` sạch trên `backend/agents/v2/response_policy.py`,
  `backend/api/agent_v2_routes.py`, `tests/test_agent_v2_response_policy.py`,
  `tests/test_agent_v2_route.py`.

**Bằng chứng thật đã chạy (sau bản 4 — sửa case-sensitivity, sửa cuối
trước PR):**

- `tests/test_agent_v2_response_policy.py`: 40/40 pass.
- Toàn bộ `pytest -k "agent_v2 or response_policy"`: 1224/1224 pass (cùng
  18 lỗi pre-existing, cùng 5 skip Postgres-only — không đổi).
- Golden `--deterministic-only`: 15/15 PASS lần nữa sau bản 4.
- `ruff check` sạch trên `backend/agents/v2/response_policy.py` +
  `tests/test_agent_v2_response_policy.py`.

## Tiến độ CP2 thực (bản 5) — phản hồi PR #193 review

Sau khi mở PR #193, bot review nêu 2 điểm cho `response_policy.py`:

**1. `_CLOCK_TIME_MARKER` quá rộng (finding thật, đã sửa).** Bot chỉ đúng:
`\b\d{1,2}\s*(giờ|h)\b` bắt luôn cả câu hoàn toàn bình thường không liên
quan liều thuốc (vd "Hẹn gặp bạn lúc 8 giờ nhé", "cách đây 2h", "đợi 1
giờ") — cùng loại lỗi over-broad đã sửa ở bản 3 cho từ chỉ buổi trong
ngày, chỉ khác là lần này áp dụng cho pattern giờ đồng hồ. Sửa: thống nhất
`_dose_time_leak_detected` — giờ đồng hồ VÀ từ chỉ buổi trong ngày đều
cùng một luật: chỉ tính là leak khi nằm GẦN (30 ký tự) một động từ liều
thuốc (uống/dùng thuốc); "liều" vẫn là marker độc lập không cần ngữ cảnh.
Đổi 1 test cũ (giờ đồng hồ trần → giờ PASS, không còn reject sai) + thêm 1
test khẳng định giờ đồng hồ CÓ ngữ cảnh liều thuốc vẫn bị reject đúng —
`tests/test_agent_v2_response_policy.py`.

**2. `re.IGNORECASE` vs `casefold()` không nhất quán (đã kiểm chứng thật:
không phải bug đang tồn tại cho tiếng Việt, nhưng đã hardening cho nhất
quán).** Kiểm chứng thực nghiệm trực tiếp (`python3` REPL) trước khi sửa:
`re.IGNORECASE` của Python 3 đã xử lý đúng Unicode case-folding cho MỌI tổ
hợp hoa/thường của các chữ cái tiếng Việt đã test (đ/Đ, ư/Ư, ố/Ố, ệ/Ệ và
các câu "ĐÃ UỐNG"/"CHƯA UỐNG" viết hoa toàn bộ) — `.lower()` và
`.casefold()` cho kết quả GIỐNG HỆT nhau trên mọi ký tự tiếng Việt đã thử,
không có phân kỳ kiểu tiếng Đức (ß→ss) mà `casefold()` mới xử lý đúng còn
`re.IGNORECASE` thì không. Claim "có thể bypass" của bot **không đúng
thực nghiệm cho tiếng Việt** — không có bypass sống hiện tại. Vẫn hardening
theo hướng bot gợi ý vì rẻ và giúp nhất quán: gộp toàn bộ `validate_free_
prose` về DÙNG CHUNG một cơ chế (`_normalize_for_match` — đổi tên từ
`_normalize_for_identity_match`, không còn riêng cho medication_identity)
— chuẩn hoá `free_prose` một lần duy nhất ở đầu hàm, bỏ hết `re.IGNORECASE`
khỏi mọi pattern (dose_time/dose_status/handoff_state), so khớp thẳng trên
văn bản đã chuẩn hoá. Thêm 2 test khẳng định dose_status/handoff_state vẫn
bắt đúng khi model viết hoa toàn bộ hoặc hoa/thường lẫn lộn (đã pass NGAY
CẢ TRƯỚC khi refactor — test khoá hành vi, không phải fix bug) —
`tests/test_agent_v2_response_policy.py`.

**Bằng chứng thật đã chạy (sau bản 5):**

- `tests/test_agent_v2_response_policy.py`: 43/43 pass.
- Toàn bộ `pytest -k "agent_v2 or response_policy"`: 1227/1227 pass (cùng
  18 lỗi pre-existing, cùng 5 skip Postgres-only — không đổi).
- Golden `--deterministic-only`: 15/15 PASS lần nữa sau bản 5.
- `ruff check` sạch trên `backend/agents/v2/response_policy.py` +
  `tests/test_agent_v2_response_policy.py`.

**Chưa làm (còn lại của AC checklist CP2, chưa động tới ranh giới nào
khác):**

- **Chưa** áp dụng renderer cho các loại phản hồi "Ưu tiên natural
  renderer" theo bảng V2.5-DESIGN.md mục 7 (follow-up/clarification/
  grounding-decline/out-of-scope/drug-info low-risk) — các route này hiện
  trả lời tất định (0 lượt gọi model, ví dụ schedule/clarification) hoặc đi
  qua nhánh tool-loop chung mà CP2 này đã wiring. Đưa renderer vào ĐÚNG các
  nhánh đó là một khối việc riêng, kích thước tương đương một task con —
  chưa bắt đầu, không tự ý coi là xong.
- Canary/CP3/CP4/CP5 cho capability này — chưa mở, đúng như mọi flag khác
  của V2.5 hiện tại.

## Không thuộc phạm vi (task này = CP1, không phải CP2)

- Không code bất kỳ thay đổi runtime nào ở trên — đây là hợp đồng cho CP2.
- Không đổi Safety Domain/doctor takeover/authorization.
- Không đụng Task 02/03 — flag/canary của chúng không đổi bởi task này.
- Không mở canary cho Task 02/03 (owner đã nói rõ: chờ đánh giá người dùng
  riêng, chưa bật hàng loạt).

## Context bắt buộc phải đọc trước khi làm CP2

- `chat-bot-build/chatbot-v2_5/V2.5-DESIGN.md` (mục 3, 5, 6, 7, 8 — ranh
  giới renderer/soul/sensitive-fact guard)
- `chat-bot-build/chatbot-v2_5/CP0-ADR-BASELINE-TASK01.md` (mục 1.2, 1.3,
  1.3a, 1.4, 1.4a — mọi quyết định ADR renderer đã chốt từ trước)
- `chat-bot-v3/docs/soul_v3.md` (reuse trực tiếp theo đã chốt)
- `backend/agents/v2/model_gateway.py` (`synthesize_read_only`, `ModelRole`)
- `backend/agents/v2/runtime.py` (lượt synthesis, `record_model`)
- `backend/agents/v2/observability.py` (`ModelPricingCatalog`, `CostEstimate`)

## Definition of Done cho CP1 (task này)

Benchmark thật + pricing thật + contract cụ thể đủ để CP2 code thẳng không
phải thiết kế lại. Không có diff runtime code trong task này hay trong PR
sửa lỗi này. **CP1 chỉ coi là đạt sau khi PR sửa lỗi (6 điểm ở Status) được
merge** — không cần ADR mới, đây là sửa chính xác hợp đồng đã có.
