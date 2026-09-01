# TASK-V2.5-004: Natural renderer có grounding (capability renderer)

**Domain:** Agent V2 model gateway / response rendering — capability renderer
**Owner:** Dyo31122005 + AI
**Sprint:** V2.5 timebox — chưa gán sprint chung
**Status:** CP1 — **correction pending**. Benchmark/contract đã chốt nhưng
owner yêu cầu sửa chính xác hợp đồng (style_profile, backend assembly
`free_prose`/protected fact, golden dương, test timeout/EmptySynthesisError,
`AGENT_MAX_MODEL_CALLS`) trước khi coi CP1 là final. CP1 chỉ thật sự đóng
sau khi PR sửa lỗi này (`docs/task04-cp1-corrections`) merge — CP2 chưa
được bắt đầu cho tới lúc đó. Chưa code runtime (đúng chỉ đạo trước và sau
sửa lỗi này).

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
