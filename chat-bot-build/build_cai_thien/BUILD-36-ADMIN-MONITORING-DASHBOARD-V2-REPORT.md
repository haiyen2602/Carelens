# BUILD-36 — Admin Monitoring Dashboard V2 — Report

Status: **IMPLEMENTED, LOCAL-VERIFIED (real Postgres, real model, real
Judge provider, real frontend build)**. Audit (mục 1) + information
architecture đề xuất hoàn thành trước khi viết code (plan mode, người dùng
đã duyệt). Xây trên dữ liệu durable BUILD-32/33/34/35 đã có — không tạo
persistence song song, không sửa runtime Agent V2.

---

## 1. Audit trước khi code

Audit đầy đủ (2 Explore pass song song + đọc trực tiếp) được ghi lại toàn
bộ trong plan đã duyệt. Tóm tắt các phát hiện quan trọng nhất:

### 1.1 Ring buffer vẫn là nguồn CHÍNH cho nội dung — hạn chế kiến trúc thật, không phải bug

`backend.services.telemetry.get_local_traces()` (buffer 200 mục, reset khi
restart/deploy) vẫn được **kiểm tra TRƯỚC** durable table cho nội dung câu
hỏi/trả lời — `agent_feedback.py:234-244` ghi rõ đây là chủ ý: durable
`AgentRunSpan` không bao giờ mang raw tool output/final reply text (quyết
định privacy-minimization từ build trước). Đây là **giới hạn kiến trúc
vĩnh viễn**, không phải thứ build này "sửa" được — Trace/Session Explorer
hiển thị nội dung thật khi trace còn trong buffer, và honest "không còn
lưu tạm" khi không còn — không bao giờ fabricate/tái tạo. Metric (status,
execution_path, token, cost, span, error_code, safety, Judge) luôn có sẵn
durable bất kể trạng thái buffer — chỉ raw text mới phụ thuộc buffer.

### 1.2 `rag_monitoring_routes.py` (896 dòng, 8 endpoint) — giữ nguyên, không đụng

Legacy RAG-only surface, trộn ring-buffer-primary với durable overlay một
phần. `/traces` **không có pagination thật** — cap cứng
(`local_traces[-100:]`, trần 150 dòng). Build này KHÔNG sửa file này (trừ
`_safe_agent_v2_safety_summary` đã có sẵn, không đụng) — giữ làm legacy RAG
surface riêng biệt.

### 1.3 Ticket ↔ trace correlation (BUILD-29) — Judge đã tính nhưng chưa render, Evaluation/Safety hoàn toàn thiếu

`judge_result_out()` đã tính Judge data vào `AgentFeedbackTicketDetailOut.judge`
từ BUILD-33 — **backend đã trả về, nhưng type TypeScript không khai báo
field này nên bị âm thầm bỏ qua** (`frontend/src/lib/feedback-tickets.ts:61-64`,
`page.tsx:142`). Link thiếu thật (xác nhận vắng mặt, không chỉ chưa render):
ticket → `AgentRunEvaluation`, ticket → `AgentSafetyEvent` (chỉ có status
suy luận thô từ `AgentRun.status`, chưa bao giờ đọc row thật). Không có
index trên `trace_id`/`agent_run_id` của `agent_feedback_ticket` dù cả 2 bị
query trực tiếp.

### 1.4 Pagination — 4 kiểu ad hoc khác nhau, không có helper dùng chung

Kiểu tốt nhất đã có: `agent_safety_monitoring.list_safety_events`'s
`select(func.count()).select_from(stmt.subquery())` (COUNT SQL thật). Kiểu
tệ nhất: `admin_feedback_routes.list_tickets`'s `len(db.execute(stmt).scalars().all())`
(load hết kết quả chỉ để đếm).

### 1.5 Canonical error taxonomy — xác nhận từng mã bằng literal string thật

`BUDGET_EXCEEDED`, `MODEL_ERROR`, `MODEL_TIMEOUT`, `REQUEST_TIMEOUT`,
`TOOL_ERROR`/`RETRIEVAL_ERROR` (cùng nhánh `_fail_closed_error_code`),
`EMPTY_REPLY`, `GROUNDING_FAILURE`, `HANDOFF_FAILURE`, `INTERNAL_ERROR` —
tất cả xác nhận bằng cách đọc call site thật. **`TOOL_TIMEOUT`/`RETRIEVAL_TIMEOUT`
không bao giờ được phát ra** — comment thật trong `runtime.py:31-35`: không
có deadline riêng cho tool/retrieval khác với timeout tổng thể của run,
nên phân biệt sẽ là metric bịa. Errors section phải hiện 2 mã này ở mức 0
cố định kèm giải thích, không được âm thầm bỏ qua.

### 1.6 Không có endpoint tổng hợp Judge nào tồn tại

Grep xác nhận zero — score distribution, đếm pending/completed/failed,
low-score list đều là backend mới hoàn toàn.

### 1.7 Không có persistence cho golden run — quyết định kiến trúc thật

BUILD-35's runner chỉ ghi file JSON/MD local, gitignored. Dashboard sống
không thể query file local chỉ tồn tại trên máy đã chạy lần cuối. **Quyết
định**: thêm bảng durable `AgentGoldenRun`/`AgentGoldenRunCase` tối giản +
1 flag `--persist` mới trên chính runner đó, ghi CÙNG dữ liệu đã tính (bổ
sung, không thay thế output JSON/MD).

### 1.8 Frontend — không có component dùng chung nào thực sự được dùng

Xác nhận: `components/ui/{card,badge,tabs,table,chart,skeleton}.tsx` không
được import ở đâu trong `app/`. Mọi trang admin tự viết `surface-card` div
+ raw `<table>` + `recharts` trực tiếp. Không có helper `adminFetch` dùng
chung. Filter là filter thật (query param → backend, không phải bug cosmetic
BUILD-25). Auth gate 1 lần ở `app/admin/layout.tsx` — trang mới dưới
`/admin/` tự động được bảo vệ.

---

## 2. Information Architecture (đã duyệt qua plan mode)

- **`/admin/monitoring`** — 1 trang tab (giống UX `/admin/rag` đã có): Tổng
  quan · Chất lượng · Retrieval · Safety & Handoff (dùng lại
  `/admin/safety/*` có sẵn, không nhân bản backend) · Hiệu năng · Token &
  Chi phí · Lỗi · Judge · Golden Evaluation · So sánh Version.
- **`/admin/monitoring/traces`** — Trace Explorer phân trang/filter thật
  (thay thế popup `alert()` cũ).
- **`/admin/monitoring/traces/[traceId]`** — chi tiết trace (điểm drill-down
  từ mọi section, từ ticket, từ safety event).
- **`/admin/monitoring/sessions/[conversationId]`** — chi tiết phiên hội
  thoại.
- **Tickets**: nâng cấp trang `/admin/tickets/[id]` có sẵn tại chỗ (render
  panel Judge đã tính sẵn, thêm panel Evaluation V2 + Safety) — không tạo
  trang "Tickets" song song trong dashboard mới.

---

## 3-11. Overview / Quality / Retrieval / Safety / Performance / Cost / Errors / Judge / Golden

Tất cả implement thật trong `backend/services/agent_monitoring_metrics.py`
(1 `MonitoringFilters` dataclass dùng chung + 1 hàm/section, mọi rate trả
`{value, numerator, denominator, sample_count, status}` — `status` là
`AVAILABLE`/`NOT_APPLICABLE`/`NOT_AVAILABLE`, không bao giờ float trần,
không bao giờ 0 bịa). Chi tiết per-metric source of truth:

| Metric | Nguồn | Loại |
|---|---|---|
| success/fallback/error/timeout/empty_reply rate | `AgentRun` (status/error_code/timeout/empty_reply) | LIVE |
| P50/P95 latency | `AgentRun.duration_ms` (percentile tính bằng Python, sorted+index — portable SQLite/Postgres, dữ liệu ở scale dashboard-filtered, không phải toàn bảng) | LIVE |
| token/cost per query, daily cost | `AgentRun.total_tokens`/`total_cost_usd`/`cost_status` | LIVE |
| ticket rate | JOIN `AgentFeedbackTicket.agent_run_id` | LIVE |
| safety trigger/handoff rate | `agent_safety_monitoring.safety_metrics_summary` (tái dùng nguyên hàm BUILD-34, chỉ áp date range — xem mục 12 hạng mục "răng cưa filter") | LIVE |
| judged rate | JOIN `AgentRunJudge.agent_run_id` | LIVE |
| RAG faithfulness/answer_relevance | ring buffer (chưa bao giờ được BUILD-32 làm durable số thật, chỉ có status/disposition) | HEURISTIC, `scope: ring_buffer` |
| Golden HitRate/MRR/NDCG/Precision@10 (live VÀ golden) | luôn `NOT_APPLICABLE`, lý do `no_stable_retrieval_id_contract` | GOLDEN |
| Judge overall score | `AgentRunJudge.overall_score` (JUDGE_COMPLETED only) | LLM_JUDGE |
| Golden pass rate / regression gate | `AgentGoldenRun` (latest run) | GOLDEN |
| per-step latency | `AgentRunSpan.duration_ms` theo `span_type` (span thật BUILD-32, không fabricate) | LIVE |
| Agent Cost vs Judge Cost vs Total | `AgentRun.total_cost_usd` (AVAILABLE only) tách riêng `AgentRunJudge.cost_usd` | LIVE |
| error breakdown | `AgentRun.error_code` theo canonical taxonomy, +2 dòng cố định 0 cho TOOL_TIMEOUT/RETRIEVAL_TIMEOUT | LIVE |
| Judge pending/completed/failed, score distribution, low-score list | `AgentRunJudge` | LIVE |
| Golden latest run, category breakdown, failed case, comparisons | `AgentGoldenRun`/`AgentGoldenRunCase` | GOLDEN |

Mỗi hàm section có try/except riêng, degrade về `{"available": false,
"reason": ...}` — không bao giờ 500 cả dashboard vì 1 section lỗi (áp dụng
trực tiếp bài học BUILD-32 post-merge incident, không chỉ trích dẫn).

**Safety & Handoff tab**: không nhân bản backend — dùng thẳng
`/admin/safety/*` đã có từ BUILD-34.

---

## 12. Version Filters + So sánh Version

`GET /admin/monitoring/versions/filters` — trả **giá trị distinct thật**
từ DB (`SELECT DISTINCT`), không phải danh sách `<option>` hardcode.

`GET /admin/monitoring/versions/compare?section=...&before_*&after_*` —
gọi ĐÚNG 1 hàm section 2 lần (1 lần/filter set) rồi diff — không có logic
compare thứ 2 nào tồn tại độc lập, tránh 2 cách tính cùng 1 metric có thể
lệch nhau. Delta tính cho cả field dạng `{value: ...}` VÀ field số trần
(vd `total_requests`) — bug thật tự bắt: bản đầu chỉ diff được field dạng
rate dict, field số trần bị bỏ `delta: null` dù có thể tính được, sửa +
verify lại bằng lệnh gọi thật.

`prompt_version`/`retrieval_version` **thêm cột durable mới trên
`AgentRun`** (`_persist_durable_trace` stamp từ `settings.rag_prompt_version`/
`rag_retriever_version`) — quyết định thật: 2 field này là hằng số toàn
deployment (app không có override theo từng request), nhưng chính vì vậy
so sánh CHÉO 2 deployment (trước/sau đổi prompt/retrieval) là đúng use
case thật — nếu không có cột này, filter sẽ là filter giả (bug lớp BUILD-25
spec cảnh báo), nên thêm cột thay vì offer filter không tác động gì.

---

## 13. Trace Explorer / Session Explorer

`/admin/monitoring/traces` — phân trang/filter thật qua `LIMIT`/`OFFSET` +
`func.count()` (thay cap cứng của `/admin/rag/traces` cũ). Trace detail có
đủ: summary, trace_id, agent_run_id, conversation_id, execution_path,
intent, status, start/complete, duration, span timeline thật, tool names,
citation, token/cost, error/timeout, Evaluation V2, Judge, Safety/Handoff,
ticket — **không** chain-of-thought/system prompt/JWT/secret (durable table
BUILD-32 chưa bao giờ mang các field đó). Nội dung câu hỏi/trả lời chỉ có
khi `content_available=true` (còn trong ring buffer) — degrade rõ ràng khi
không, không fabricate.

Session Explorer dùng lại `agent_feedback.session_messages` (đã có từ
BUILD-29, dùng cho `GET /admin/tickets/{id}/session`) — không viết logic
merge buffer+durable lần 2.

---

## 14. Ticket Integration

`agent_feedback.py` thêm `evaluation_result_out()`/`safety_result_out()`
(mới), wire vào `AgentFeedbackTicketDetailOut` cùng `judge_result_out()`
(đã có, giờ mới thật sự lên tới frontend). `safety_result_out` tái dùng
`agent_safety_monitoring.safety_event_for_agent_run()` (hàm mới, cùng
live-join logic `safety_event_detail` đã dùng, hướng ngược lại) — không có
implementation Safety thứ 2. Frontend: sửa type `FeedbackTicketDetail`
thêm `judge`/`evaluation`/`safety`, render 3 panel mới trong
`/admin/tickets/[id]`.

---

## 15. Backend API — server-side, không fetch hết rồi lọc client

Mọi list endpoint mới (`/traces`) dùng `paginate()` (helper mới, đúng kiểu
`func.count()`-over-subquery đã audit là kiểu tốt nhất trong 4 kiểu cũ) —
không thêm kiểu ad hoc thứ 5.

**Index mới** (migration `0045`, additive, idempotent-guarded):
- `agent_feedback_ticket.trace_id`, `agent_feedback_ticket.agent_run_id` —
  lý do: cả 2 bị `judge_result_out`/`safety_event_for_agent_run` query trực
  tiếp, trước đây không có index nào.
- `agent_run.prompt_version`, `agent_run.retrieval_version` — lý do: cột
  mới, cần index để filter/compare theo version không full-scan.

Không benchmark trước/sau bằng công cụ chuyên dụng (ngoài khả năng thực tế
của phiên làm việc này) — nhưng mọi filter mới đều verify bằng test thật
(`test_..._actually_filters`) xác nhận filter tác động query, không chỉ
verify HTTP 200.

---

## 16. Metric Semantics UX

Mỗi `MetricCard` (frontend) nhận `help` (tooltip) + hiện badge loại metric
(`LIVE`/`GOLDEN`/`HEURISTIC`/`LLM_JUDGE`/`DETERMINISTIC`). `N/A` render
đúng chữ "N/A" (`formatMetric()` kiểm `status !== "AVAILABLE"` trước khi
format số) — không bao giờ "0%"/"0.00" cho case N/A.

---

## 17. Frontend States

Mỗi tab xử lý loading (spinner)/empty (bảng rỗng có thông báo)/N/A (đã nêu
trên)/backend error (banner đỏ, không phải console-only như `/admin/rag`
cũ) — theo pattern TỐT HƠN trong 2 pattern có sẵn (tickets page's 3-state
handling), không phải pattern RAG page's console-swallow.

Mọi endpoint mới đều degrade `{"available": false}` khi durable-read lỗi —
verify bằng cách đọc code (try/except bọc từng hàm section), không giả vờ
đã test lỗi DB thật (không có cách an toàn để giả lập DB down trên máy dev
đang chạy migration/test khác).

---

## 18. Authorization

`require_role("admin")` trên MỌI route mới, cùng pattern
`admin_safety_routes.py`. Verify thật qua HTTP (không chỉ đọc code):
admin 200, patient/doctor/caregiver 403 trên toàn bộ 10 route +
trace/session detail riêng. Không cross-patient leak — trace/session detail
đọc theo `trace_id`/`conversation_id` thật, không có patient_id nào từ
client được tin tưởng.

---

## 19. Local traffic (spec §21, A–K) — verify bằng expected count thật

`scripts/agent_v2/build36_admin_monitoring_local_e2e.py` — chạy thật A-K:

```text
[A-RAG] status=COMPLETED intent=GENERAL_MEDICAL_INFORMATION
[B-SCHEDULE] status=COMPLETED
[C-DRUG] status=COMPLETED
[D-TRIAGE] status=COMPLETED
[E-DOSE] status=COMPLETED
[F-SAFETY] status=HANDOFF_CREATED safety_disposition=HANDOFF_REQUIRED
[G-FALLBACK] skipped -- yêu cầu fault injection tầng runtime, không trigger
             được chỉ bằng nội dung tin nhắn (cùng giới hạn BUILD-35 đã ghi)
[H/I-JUDGE] scored 1 pending row(s)
[J-TICKET] ticket_id=606d5abd-8a53-4389-83fd-9f730cbce378
[K-GOLDEN] exit_code=0

Dashboard verification (real durable query, fresh session):
  overview.total_requests=743 (>= 6 expected from A-F)
  traces: all 6 real runs present in list: True
  retrieval.rag_query_volume=49 (>= 1 expected)
  judge.total_judged=30 (>= 1 expected)
  golden.has_run=True (True expected)
  performance.end_to_end_p50_ms.status=AVAILABLE (AVAILABLE expected)
  errors: TOOL_TIMEOUT/RETRIEVAL_TIMEOUT correctly always-zero-with-note: True
  versions/filters.available=True

ALL CHECKS OK
```

Không chỉ kiểm HTTP 200 — mỗi bước đối chiếu trace/ticket/safety event thật
có xuất hiện trong dashboard đúng như kỳ vọng (vd `test_admin_traces_list_shows_real_markers_through_http`
seed 1 ticket + 1 safety event trên CÙNG 1 run, xác nhận dashboard đánh
dấu đúng cả 2 trên đúng run đó).

---

## 20. Required Tests

- `tests/test_agent_v2_build36_admin_monitoring.py` — 31 test pure (SQLite):
  aggregate correctness, denominator correctness, N/A semantics, filter
  hiệu quả thật, error breakdown (kể cả 2 dòng never-emitted), latency
  percentile, token/cost, Judge/Golden metrics, pagination, trace/session
  drill-down.
- `tests/test_api/test_admin_monitoring_routes.py` — 9 test HTTP thật
  (Postgres): auth (admin 200, patient/doctor/caregiver 403 toàn bộ 10
  route + trace/session detail), correlation thật qua HTTP, ticket detail
  giờ có đủ `judge`/`evaluation`/`safety`.
- Frontend: `eslint`, `tsc --noEmit`, `next build` — 3 gate cụ thể spec
  liệt kê, không phát minh hạ tầng unit-test component mới (repo hiện chỉ
  có 1 script `.mjs` thủ công, không có component-testing nào) — tránh mở
  rộng phạm vi ngoài những gì spec thật sự yêu cầu.

Tổng 40 test backend mới, tất cả pass. `ruff` clean trên toàn bộ file build
này (4 finding `datetime.UTC` alias trong `admin_feedback_routes.py` là
pre-existing, xác nhận giống hệt trên `origin/main`, không phải code build
này — xem mục 22).

---

## 21. Sự cố thật phát hiện khi build (không giấu)

1. **Bug thật trong chính model mới**: `AgentGoldenRun.created_at` vừa có
   `index=True` trên cột vừa khai báo `Index("ix_agent_golden_run_created_at", ...)`
   TRÙNG TÊN trong `__table_args__` — SQLAlchemy tạo 2 lần cùng 1 index,
   fail thẳng khi `create_table()` (kể cả SQLite lẫn migration thật nếu
   chạy đường khác). `AgentGoldenRunCase.run_id` bị lỗi y hệt. Phát hiện
   khi chính unit test SQLite mới viết fail lúc setup fixture (không phải
   khi chạy assertion) — sửa bằng cách bỏ `index=True` (giữ 1 khai báo duy
   nhất), verify lại: 31/31 test pass, migration thật trên Postgres re-check
   vẫn ở head, không bị ảnh hưởng (vì migration dùng raw DDL riêng, không
   qua `index=True` của ORM).
2. **Bug thật trong `retrieval_metrics`, tự bắt bằng smoke-test thủ công
   trước khi build tiếp**: bản đầu tính `empty_retrieval_rate` bằng
   `grounding_failures / rag_volume` — nhưng `evaluation_v2.dispatch_
   evaluation` yêu cầu citation thật mới được gán path RAG, nên 1 run
   KHÔNG BAO GIỜ vừa là RAG vừa là GROUNDING_FAILURE cùng lúc (2 tập rời
   nhau theo thiết kế). Ghép sai làm rate lên tới 85% — vô lý. Suy nghĩ lại:
   `GROUNDING_FAILURE` áp cho NHIỀU intent (drug info, prescription,
   schedule/dose, general medical — BUILD-24F), không riêng RAG, nên kể cả
   ghép `rag_volume + grounding_failures` làm mẫu số cũng không sạch. Quyết
   định: giữ metric HONEST — `empty_retrieval_rate` = `NOT_APPLICABLE` với
   lý do rõ ràng, chỉ `grounding_failure_rate` (mẫu số = toàn bộ run đã
   filter) là metric sạch, verify bằng test hồi quy mới.
3. **Bug thật trong `_diff`/`compare_metrics`**: bản đầu chỉ tính delta cho
   field dạng `{value: ...}`, field số trần như `total_requests` bị bỏ
   `delta: null` dù tính được — sửa, verify lại bằng lệnh gọi thật
   (`total_requests: {before: 706, after: 706, delta: 0}`).
4. **Regression thật từ chính fix của BUILD-35, phát hiện khi test `--persist` mới**:
   `run_golden_evaluation.py`'s `if __name__ == "__main__":` set
   `AGENT_RUNTIME_ENABLED` ở CUỐI file — nhưng `backend.db.base` gọi
   `get_settings()` ở module level, bị kéo vào TRƯỚC đó qua chính import
   chain của file này (`from backend.api.agent_v2_routes import ...`) —
   nghĩa là cache `lru_cache` đã "đóng băng" giá trị False trước khi dòng
   set env var kịp chạy. CLI trần (`python scripts/agent_v2/
   run_golden_evaluation.py ...`) — không phải khi được import từ E2E script
   khác — luôn thất bại với "Agent V2 chưa được kích hoạt" kể từ fix
   BUILD-35. BUILD-35's E2E script tự nó không bị vì nó set env var TRƯỚC
   khi import module này. Sửa: dời check `if __name__ == "__main__":` lên
   NGAY sau `sys.path.insert`, trước mọi import nặng — verify lại: CLI trần
   chạy thật OK, VÀ chạy lại đúng 2 test đã phát hiện bug rò rỉ env var gốc
   ở BUILD-35 (`test_agent_v2_orchestrate_route_is_off_by_default_...`) để
   xác nhận fix mới không tái tạo lại vấn đề cũ.
5. **Bug thật trong chính test fixture mới viết** (không phải code thật):
   `real_run_ticket_and_safety_event` tạo `AgentSafetyEvent`/`AgentFeedbackTicket`
   với `trace_id` thật nhưng quên gán `AgentRun.trace_id` tương ứng —
   `trace_detail()` tra theo `AgentRun.trace_id` nên trả 404 dù dữ liệu
   liên quan đã có. Sửa fixture, verify lại: 9/9 test pass.

---

## 22. Known Limitations

- **Ring buffer vẫn là nguồn duy nhất cho nội dung câu hỏi/trả lời/citation**
  — giới hạn kiến trúc từ trước BUILD-36, không sửa được trong phạm vi
  build này (đổi cần thêm cột durable mới cho raw text, một quyết định
  privacy/scope lớn hơn 1 build).
- **`empty_retrieval_rate` là `NOT_APPLICABLE`** — xem mục 21.2, không có
  cách tách sạch "RAG-only grounding attempt" khỏi các intent grounding-
  required khác hôm nay.
- **RAG faithfulness/answer_relevance chỉ tính trên buffer hiện tại** — số
  thật nhưng KHÔNG PHẢI date-range aggregate thật (không filter theo ngày
  được, vì buffer chỉ có 200 mục gần nhất của process).
- **`safety_trigger_rate`/`handoff_rate` ở Overview chỉ filter theo ngày**
  — không áp được filter model/prompt_version (hàm `safety_metrics_summary`
  tái dùng từ BUILD-34 chỉ nhận date range) — response có `scope_note` rõ
  ràng khi filter khác đang bật, không âm thầm.
- **Performance percentile tính bằng Python** (sort + index), không phải
  SQL `percentile_cont` — portable SQLite/Postgres, đủ nhanh ở scale
  dashboard-filtered hôm nay; scale lớn hơn là việc tối ưu riêng sau này.
- **CI job cho `--deterministic-only --persist`** — build này KHÔNG thêm
  bước CI mới (không nằm trong spec §22/§25 của BUILD-36) — nếu muốn dữ
  liệu Golden luôn mới trên dashboard, cần chạy `--persist` thủ công/CI
  riêng, out of scope ở đây.
- **Không có screenshot** — repo không có Playwright/Puppeteer/browser-
  automation nào (đã kiểm `frontend/package.json`) — verify bằng HTTP thật
  + `npm run build` thật, không giả lập ảnh chụp màn hình.
- **4 finding `datetime.UTC` alias trong `admin_feedback_routes.py`** —
  pre-existing, xác nhận giống hệt `origin/main`, không phải phạm vi build
  này.

---

## 23. Architecture (cập nhật)

```text
Agent V2
  ↓
Durable Observability BUILD-32
  ├─ AgentRun (+ prompt_version/retrieval_version mới BUILD-36)
  ├─ AgentRunSpan
  └─ AgentRunEvaluation
  ↓
Judge BUILD-33 (AgentRunJudge)
  ↓
Safety/Handoff BUILD-34 (AgentSafetyEvent)
  ↓
Golden Evaluation BUILD-35 (+ AgentGoldenRun/AgentGoldenRunCase mới BUILD-36,
  ghi qua --persist)
  ↓
backend/services/agent_monitoring_metrics.py (mới, BUILD-36)
  ↓
backend/api/admin_monitoring_routes.py (mới, BUILD-36)
  ↓
Admin Dashboard V2 (/admin/monitoring)
  ├─ Overview · Quality · Retrieval · Performance · Cost · Errors · Judge
  ├─ Golden Evaluation · Versions (filters + compare)
  ├─ Safety & Handoff (link ra /admin/safety/* có sẵn, không nhân bản)
  ├─ Trace Explorer (/admin/monitoring/traces[/[traceId]])
  ├─ Session Explorer (/admin/monitoring/sessions/[conversationId])
  └─ Tickets (/admin/tickets/[id] nâng cấp tại chỗ: +Judge/+Evaluation/+Safety panel)
```

---

## 24. Regression

Không sửa `orchestrator.py`/`safety.py`/`runtime.py`/router behavior/RAG
threshold/model-call budget — xác nhận bằng `git diff --name-only`. Duy
nhất `agent_v2_routes.py` bị đụng, và CHỈ ở `_persist_durable_trace` (2
dòng stamp `prompt_version`/`retrieval_version` — cùng shape các dòng
stamp `model`/`evaluation_version` đã có từ BUILD-32, không phải logic
routing/safety/response).

```text
pytest -q tests/test_agent_v2_build36_admin_monitoring.py tests/test_api/test_admin_monitoring_routes.py
40 passed

pytest -q tests/ --ignore=tests/services/photo_verification --ignore=tests/vlm_demthuoc
11 failed, 1727 passed, 20 skipped, 586 warnings in 327.50s (nhánh build này)

pytest -q tests/ (git worktree origin/main, cùng máy, cùng .env/Postgres, tuần tự không song song)
11 failed, 1687 passed, 20 skipped, 496 warnings in 284.42s (baseline)
```

**11 lỗi FAIL giống hệt, byte-for-byte, giữa nhánh build này và
`origin/main`** — **0 lỗi mới**. 1727 − 1687 = 40, khớp chính xác với 40
test mới của build này (31 unit + 9 API) — đối chiếu số học chính xác.

**Sự cố methodology thật phát hiện khi đo regression lần này**: nhánh build
này lần đầu cho ra 11 lỗi thay vì 8 lỗi đã biết từ baseline BUILD-35 — 3
lỗi lạ trong `tests/test_agent_v2_long_term_memory.py` (không liên quan gì
đến code build này đụng vào). **Không giả định là lỗi mới do build này gây
ra** — verify bằng cách chạy đúng 3 test đó trên 1 worktree `origin/main`
sạch (không có bất kỳ thay đổi nào của build này) — **cả 3 vẫn fail y hệt**.
Kết luận: đây là 3 lỗi có sẵn trên chính `origin/main` (xuất hiện sau khi
BUILD-35's baseline 8-lỗi được ghi nhận, không liên quan build này), không
phải lỗi build này gây ra — baseline thật hiện tại là 11, không phải 8, và
nhánh build này khớp đúng 11/11 với baseline thật đó.

---

## 25. Production Smoke

Chưa thực hiện — theo đúng quy trình dự án: chỉ sau PR → review → merge →
deploy. Không tạo tin nhắn nguy hiểm giả trên production chỉ để test
Safety (không cần thiết — đã verify đầy đủ ở local).

---

## 26. Files Changed

**Mới:**
- `backend/api/admin_monitoring_routes.py`
- `backend/services/agent_monitoring_metrics.py`
- `migrations/versions/0045_agent_golden_run.py`
- `scripts/agent_v2/build36_admin_monitoring_local_e2e.py`
- `tests/test_agent_v2_build36_admin_monitoring.py`
- `tests/test_api/test_admin_monitoring_routes.py`
- `frontend/src/lib/admin-monitoring.ts`
- `frontend/src/app/admin/monitoring/page.tsx`
- `frontend/src/app/admin/monitoring/traces/page.tsx`
- `frontend/src/app/admin/monitoring/traces/[traceId]/page.tsx`
- `frontend/src/app/admin/monitoring/sessions/[conversationId]/page.tsx`
- `chat-bot-build/build_cai_thien/BUILD-36-ADMIN-MONITORING-DASHBOARD-V2-REPORT.md`

**Sửa:**
- `backend/db/models.py` (`AgentGoldenRun`/`AgentGoldenRunCase` mới,
  `AgentRun.prompt_version`/`retrieval_version` mới, 2 index mới trên
  `AgentFeedbackTicket`)
- `backend/api/agent_v2_routes.py` (2 dòng stamp trong `_persist_durable_trace`)
- `backend/api/admin_feedback_routes.py` (wire `evaluation`/`safety` vào
  ticket detail)
- `backend/services/agent_feedback.py` (`evaluation_result_out`/`safety_result_out` mới)
- `backend/services/agent_safety_monitoring.py` (`safety_event_for_agent_run` mới)
- `backend/models/schemas.py` (`AgentFeedbackEvaluationOut`/`AgentFeedbackSafetyOut` mới)
- `backend/main.py` (đăng ký `admin_monitoring_router`)
- `scripts/agent_v2/run_golden_evaluation.py` (`--persist` flag mới + fix
  thứ tự set env var thật, xem mục 21.4)
- `frontend/src/app/admin/layout.tsx` (nav entry mới)
- `frontend/src/app/admin/tickets/[id]/page.tsx` (render 3 panel mới)
- `frontend/src/lib/feedback-tickets.ts` (type đủ `judge`/`evaluation`/`safety`)

**Không đụng**: `backend/agents/v2/orchestrator.py`, `safety.py`, `handoff.py`,
`runtime.py`, `evaluation_v2.py`, `retrieval_eval.py`, `rag_monitoring_routes.py`.

---

## 27. Branch / Commit / PR

- Branch: `feature/build-36-admin-monitoring-dashboard-v2`, tách từ
  `origin/main` sau khi xác nhận BUILD-35 (PR #115) đã merge thật.
- Chưa deploy — theo đúng nguyên tắc chương trình.

---

## 28. Release Gate

```text
BUILD-36: PASS

ADMIN DATA AUDIT: PASS
OVERVIEW: PASS
QUALITY: PASS
RETRIEVAL: PASS
SAFETY/HANDOFF: PASS               (dùng lại /admin/safety/* BUILD-34)
PERFORMANCE: PASS
TOKEN/COST: PASS
ERRORS: PASS
JUDGE: PASS
GOLDEN EVALUATION: PASS
TICKETS: PASS
TRACE EXPLORER: PASS
SESSION EXPLORER: PASS

VERSION FILTERS: PASS
FILTER BACKEND EFFECTIVE: PASS     (verify bằng test thật, không chỉ HTTP 200)
N/A SEMANTICS: PASS
METRIC PROVENANCE: PASS            (metric_type badge + tooltip mỗi card)
DENOMINATORS: PASS
PAGINATION: PASS

ADMIN AUTHORIZATION: PASS          (verify HTTP thật: admin 200, 3 role khác 403)
CROSS-PATIENT PROTECTION: PASS
NO COT EXPOSURE: PASS
DEGRADE-SAFE: PASS

FRONTEND LINT: PASS                (0 finding thật, CRLF pre-existing toàn repo)
FRONTEND TYPECHECK: PASS           (tsc --noEmit sạch)
FRONTEND BUILD: PASS               (next build thật thành công, mọi route mới xuất hiện)

LOCAL EXPECTED-COUNT E2E: PASS     (A-K, đối chiếu đúng số lượng, không chỉ 200)
REGRESSION: PASS                  (11 lỗi giống hệt origin/main, 0 lỗi mới,
                                    1727−1687=40 khớp đúng 40 test mới)

READY FOR PR: YES
```
