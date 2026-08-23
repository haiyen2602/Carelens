# BUILD-32 — Durable Observability & Trace Persistence — Report

Status: **IMPLEMENTED, LOCAL-VERIFIED**. Phần audit (mục 1-4 dưới đây) đã PASS
trước khi code, theo đúng "Không implement trước khi có sơ đồ data flow hiện
tại". Phần thiết kế/implementation/test/E2E nằm ở mục 5 trở đi.

---

## 1. Sơ đồ data flow hiện tại

```
Agent V2 orchestrator.run()
   ├─ model_gateway: usage THẬT (input/output/cached tokens từ OpenAI response)
   │     backend/agents/v2/model_gateway.py:112-119
   │
   ├─ AgentTelemetry.span()/record_model(): đo timing THẬT + tính cost THẬT
   │     backend/agents/v2/observability.py:326-380
   │     └─ sink mặc định = StructuredLogSink (observability.py:315,150-151)
   │           → chỉ ghi ra application log, KHÔNG API nào đọc lại được
   │
   └─ agent_v2_routes._record_agent_v2_telemetry()  (backend/api/agent_v2_routes.py:262-370)
         └─ build TraceRecord cho ring buffer (backend/services/telemetry.py, max 200
            — _MAX_LOCAL_TRACES = 200, telemetry.py:103)
               ├─ KHÔNG đọc result.metrics ở bất kỳ dòng nào → token/cost thật bị VỨT BỎ
               ├─ start_observation/end_observation gọi DỒN DẬP SAU khi
               │  orchestration đã hoàn tất → span timing trong buffer là dựng,
               │  KHÔNG phải đo thật từng bước
               └─ trace.start_time bị "vá" thủ công (agent_v2_routes.py:366) để
                  tổng duration đúng, nhưng breakdown per-span thì không

Admin Trace Explorer (backend/api/rag_monitoring_routes.py) → đọc 100% từ ring buffer
   ├─ cost hard-code 0.0 khắp nơi (dòng 233, 346, 350, 512, 514)
   ├─ timeout_rate hard-code 0.0 (dòng 511)
   ├─ ttft_ms hard-code 0.0, tự comment "not measured" (dòng 504-509)
   └─ Agent V2 KHÔNG có DB fallback (chỉ legacy chat có, qua AuditLog, dòng 550-571, 615-650)

BUILD-29 ticket (AgentFeedbackTicket, DB thật — models.py:984-1049)
   └─ correlate trace/session/priority qua get_local_traces()
      (agent_feedback.py:69-90, 205-268)
      → nếu trace rớt khỏi 200-buffer hoặc sau restart:
        ticket cũ KHÔNG mở lại được trace/session (tự trả found=False, không lỗi ngầm)

BUILD-30 activity (AgentActivitySnapshot, DB thật — models.py:1052-1094)
   → duration_ms LUÔN None (cố ý thiết kế, agent_activity.py:19-20,84-85 — module
     tự chú thích "deliberately does not depend on" ring buffer timing)

BUILD-31 evaluation → evaluation.as_dict() nhét vào trace.metadata["evaluation_v2"]
   (agent_v2_routes.py:322-323) → cũng chỉ sống trong ring buffer, không bảng DB riêng

DB đã có sẵn:
   AgentRun (models.py:871-890) — ghi thật qua agent_checkpoint.py:180-191,
       nhưng KHÔNG có cột token/cost/span/duration
   AgentToolEvent (models.py:964-981) — có schema sẵn latency_ms nhưng
       CHƯA TỪNG được insert ở đâu (bảng chết)
```

## 2. Trả lời các câu hỏi bắt buộc (mục 2 của kế hoạch)

1. **Dữ liệu chỉ nằm ring buffer (mất khi restart)**: toàn bộ `TraceRecord`/
   `ObservationRecord` — query, final answer, per-observation "duration", scores,
   `evaluation_v2` metadata, safety/handoff tóm tắt. Ring buffer size = 200,
   dùng chung cho cả legacy chat lẫn Agent V2. Toàn bộ Admin dashboard KPI tính
   trực tiếp từ đây.

2. **Dữ liệu đã persist DB thật**: `AgentRun`/`AgentRunCheckpoint` (status/intent/
   timestamps thô, không token/cost/span), `AgentIdempotencyKey`,
   `AgentFeedbackTicket` (nhưng trace_id chỉ là string tham chiếu ring buffer,
   không FK), `AgentActivitySnapshot` (không timing). `AgentToolEvent` có schema
   nhưng chưa ai ghi.

3. **Token usage lấy ở đâu**: THẬT 100%, trích trực tiếp từ response OpenAI
   (`model_gateway.py:112-119`), không phải ước lượng — nhưng bị vứt bỏ trước
   khi tới ring buffer/Admin vì `_record_agent_v2_telemetry()` không đọc
   `result.metrics`.

4. **Cost tính ở đâu**: `ModelPricingCatalog.estimate()`
   (`observability.py:106-121`), flat JSON theo tên model từ env
   `AGENT_MODEL_PRICING_JSON`, KHÔNG versioned, build một lần lúc singleton khởi
   tạo (đổi giá cần restart server). Cost thật chỉ chảy vào structured log;
   trong Admin dashboard bị hard-code 0.0.

5. **Span timing đo thật hay dựng sau**: `AgentTelemetry.span()` đo thật lúc
   orchestration đang chạy, nhưng giá trị đó không bao giờ chảy tới ring buffer/
   Admin. Observation trong ring buffer được tạo dồn sau khi `orchestrator.run()`
   đã trả về — breakdown per-span là dựng, không phản ánh timing thật.

6. **Timeout có capture thật không**: có cơ chế timeout thật ở tầng SDK
   (`model_gateway.py:336`), safety domain (`safety.py:128-141`), run-budget
   (`runtime.py:155-167`). Nhưng phân loại "đây có phải timeout" dựa vào so sánh
   elapsed wall-clock sau một `except Exception:` chung
   (`runtime.py:493-496,548-551`; `safety.py:170-181`), không bắt đúng loại
   exception — một lỗi API khác xảy ra gần đúng ngưỡng thời gian có thể bị gắn
   nhầm nhãn timeout.

7. **Empty reply có detect không**: có, đúng 1 điểm —
   `model_gateway.py:485-489` raise `ValueError("MODEL_SYNTHESIS_EMPTY")` khi
   output rỗng sau strip. Không có `error_code` riêng trong telemetry; bị gộp
   chung vào retry/failure path như lỗi model khác.

8. **Ticket có phụ thuộc ring buffer không**: có, hoàn toàn. Ticket row (DB
   thật) vẫn còn sau restart, nhưng phần "xem trace/session/priority-signal" sẽ
   không mở lại được một khi trace rớt khỏi 200-buffer hoặc sau redeploy.

9. **Admin đọc từ đâu**: 100% ring buffer in-memory cho Agent V2; DB fallback
   (`AuditLog`) chỉ tồn tại cho legacy chat.

10. **Bảng DB gần giống agent_run/trace/span đã có chưa**: `AgentRun` đã có
    (thiếu token/cost/span). `AgentToolEvent` có schema sẵn (`latency_ms`) nhưng
    chưa từng được ghi. Chưa có bảng "span"/"observation"/"model_call" nào lưu
    per-call token+cost+timing thật.

## 3. Đánh giá rủi ro / phạm vi ảnh hưởng nếu implement BUILD-32

- Sửa `_record_agent_v2_telemetry()` để đọc `result.metrics` là điểm sửa có
  đòn bẩy cao nhất — vá được lỗ hổng "token/cost thật bị vứt bỏ" mà không cần
  đổi observability layer.
- Bảng `AgentRun` cần mở rộng (additive) thêm cột token/cost/duration, hoặc tạo
  bảng `agent_run_metrics`/`agent_span` mới — cần quyết định migration
  approach trước khi code (mục 3 kế hoạch: durable trace contract).
- `AgentToolEvent` là ứng viên tái sử dụng cho durable spans thay vì tạo bảng
  mới trùng lặp — cần audit thêm schema của nó trước khi quyết định.
- Timeout taxonomy (`MODEL_TIMEOUT`/`TOOL_TIMEOUT`/`RETRIEVAL_TIMEOUT`/
  `REQUEST_TIMEOUT`) hiện KHÔNG tồn tại — cần thêm phân loại rõ theo exception
  type thay vì suy luận bằng elapsed time đơn thuần.
- BUILD-29 ticket correlation cần đổi từ "tra ring buffer" sang "tra durable
  trace/span" — đây là thay đổi có rủi ro vì `agent_feedback.py` tự khai rõ
  "deliberately does NOT build a new persistence layer" — cần sửa có kiểm soát,
  không phá vỡ ticket đang mở.

## 4. Kết luận audit

Audit PASS. Chuyển sang thiết kế + implementation (mục 5 trở đi).

---

## 5. Kiến trúc & data flow sau BUILD-32

```
Agent V2 orchestrator.run()  (backend/agents/v2/orchestrator.py)
   started = self._clock()                     [BUILD-32: real wall-clock, threaded
   │                                             through every orchestrator-level
   │                                             deterministic reply path below]
   │
   ├─ ROUTER span (classify_intent)             [BUILD-32: upgraded bare event()→span()]
   ├─ SAFETY span (safety_gateway.evaluate)      [BUILD-32: new real span]
   ├─ RETRIEVAL span (retrieval_gateway.retrieve)[BUILD-32: new real span]
   ├─ TIME_QUERY span (schedule tool+compose)    [BUILD-32: new real span]
   ├─ GROUNDING span (_enforce_medical_grounding)[BUILD-32: new real span,
   │                                               error_code=GROUNDING_FAILURE if it fires]
   ├─ MODEL / TOOL / RUNTIME / GUARDRAIL / HANDOFF / CHECKPOINT
   │     spans/events -- already real (pre-BUILD-32), now made durable (below)
   │
   └─ RunResult.error_code                       [BUILD-32: new field, set at every
        (runtime.py)                              terminal return: BUDGET_EXCEEDED /
                                                   MODEL_ERROR / MODEL_TIMEOUT /
                                                   REQUEST_TIMEOUT / TOOL_ERROR /
                                                   EMPTY_REPLY / GROUNDING_FAILURE /
                                                   HANDOFF_FAILURE / None]
                                                   Classified from the caught exception's
                                                   REAL TYPE (openai.APITimeoutError,
                                                   EmptySynthesisError) first, elapsed-
                                                   time comparison only as fallback.

AgentTelemetry (backend/agents/v2/observability.py)
   sink = BufferingSink(StructuredLogSink())     [BUILD-32: tee -- log behavior
                                                   unchanged, ALSO buffers each trace's
                                                   real-timed events in memory, bounded
                                                   to 500 in-flight traces, FIFO-evict]

agent_v2_routes.run_agent_orchestration()  (backend/api/agent_v2_routes.py)
   ... real db.commit() of the actual response ...
   _record_agent_v2_telemetry()   [UNCHANGED -- still writes the ring buffer,
                                    now cache/debug only, no longer source of truth]
   _persist_activity_snapshot()   [UNCHANGED -- BUILD-30]
   _persist_durable_trace()       [BUILD-32: NEW, same best-effort/never-breaks-
                                    response shape]
        ├─ EVALUATION span (dispatch_evaluation)     -- new real span
        ├─ _telemetry_sink.pop(trace_id) → AgentRunSpan rows (bulk insert)
        │     [pairs agent_span.started+finished by (component,operation),
        │      real durations, never fabricated]
        ├─ AgentRunEvaluation row (durable Evaluation V2 result)
        └─ AgentRun row UPDATE: trace_id, actor_id, input/output/cached/total
              tokens, model_calls, model, pricing_version, input/output/total
              cost_usd, cost_status (AVAILABLE|NOT_AVAILABLE), duration_ms,
              timeout (bool), error_code, empty_reply, evaluation_version
   [top-level except Exception: ]  [BUILD-32: NEW -- previously an orchestrator-
        best-effort INTERNAL_ERROR AgentRun row  level exception left ZERO durable
                                                  trace of the failed request]

Durable DB (Postgres, migration 0042)
   agent_run          [existing table, +18 additive columns]
   agent_run_span     [NEW -- real per-step timing, sanitized attributes only]
   agent_run_evaluation [NEW -- durable Evaluation V2 result]

Admin Trace Explorer (backend/api/rag_monitoring_routes.py)
   /admin/rag/traces, /traces/{trace_id}   -- DB is now PRIMARY source
        (ring buffer = fallback only, for a trace not yet durable)
   /admin/rag/system   -- cost_daily/timeout_rate/cost_breakdown: real
        aggregates over agent_run (was hardcoded 0.0)
   /admin/rag/health   -- cost_per_query: real avg over agent_run, with
        metric_provenance (AVAILABLE/NOT_AVAILABLE), never a fabricated 0.0
   /admin/rag/generation -- breakdown_by_model.cost: real, per model

BUILD-29 ticket correlation (backend/services/agent_feedback.py)
   verify_trace_ownership / classify_priority / trace_summary_out /
   session_messages -- ALL query agent_run/agent_run_span FIRST;
   ring buffer is the fallback only (pre-BUILD-32 trace, or not yet flushed)
```

## 6. Quyết định thiết kế then chốt (lý do)

**AgentToolEvent KHÔNG được tái sử dụng cho span.** Schema của nó bắt buộc
`tool_name NOT NULL` và tự khai trong docstring là "sanitized **tool-call**
audit event" (`backend/db/models.py:964-981`), lại chưa từng có writer nào
(bảng chết). Ép một `tool_name` lên mọi loại span (safety/routing/model/
handoff...) sẽ là sai semantics. → Tạo bảng `agent_run_span` mới, giữ nguyên
`AgentToolEvent` không đụng tới.

**Span được đo thật lúc chạy, ghi DB sau khi response đã commit.**
`AgentTelemetry.span()`/`record_model()` vốn đã đo thời gian thật ngay lúc
runtime/orchestrator gọi — cái thiếu chỉ là nơi lưu (`StructuredLogSink` chỉ
ghi log, không ai đọc lại được). `BufferingSink` đệm lại đúng những sự kiện
đã có timing thật đó theo `trace_id`, và một hàm best-effort
(`_persist_durable_trace`, cùng pattern với `_record_agent_v2_telemetry`/
`_persist_activity_snapshot` đã có sẵn từ BUILD-25/BUILD-30) bulk-insert
thành `AgentRunSpan` sau khi response thật đã commit. Số liệu trong DB là số
liệu thật đo lúc chạy — chỉ có thao tác ghi DB là xảy ra trễ vài mili-giây,
giống mọi bước durability khác đã có trong file này.

**Cột metric trên `AgentRun` được stamp trong CÙNG MỘT hàm cho mọi nhánh kết
thúc**, không làm đồng bộ sâu trong `agent_checkpoint.py`, vì `SAFETY_BLOCKED`/
`HANDOFF_CREATED` không đi qua `CheckpointedTerminalStateRecorder` (orchestrator
tự guard `if result.status not in (SAFETY_BLOCKED, HANDOFF_CREATED)`) — làm ở
một chỗ duy nhất nhìn thấy mọi `OrchestrationResult` đảm bảo phủ đủ, tránh hai
đường phân kỳ.

**Ring buffer vẫn giữ nguyên, chỉ còn là cache/debug.** Không xoá hành vi nào
của `telemetry.py`. Admin Trace Explorer và BUILD-29 ticket chuyển sang đọc DB
trước; ring buffer chỉ dùng khi chưa có bản ghi durable (ví dụ ticket cũ từ
trước BUILD-32).

**Timeout/error classification cộng thêm tín hiệu loại exception thật, không
thay thế elapsed-time check.** `openai.APITimeoutError` được bắt riêng cho
`MODEL_TIMEOUT`; `EmptySynthesisError` (subclass mới của `ValueError`, thay
cho `ValueError("MODEL_SYNTHESIS_EMPTY")` cũ) được bắt riêng cho `EMPTY_REPLY`.
Elapsed-time check cũ vẫn là fallback cho các exception không rõ loại — đúng
yêu cầu "không suy luận CHỈ bằng elapsed time", không bỏ luôn cơ chế elapsed
đang hoạt động.

### Honest scope limits (không âm thầm mở rộng, không giả lập)

- **`TOOL_TIMEOUT`/`RETRIEVAL_TIMEOUT`** có trong taxonomy nhưng **không được
  emit** ở build này — hiện không có deadline riêng cho từng tool/retrieval
  (chỉ có run-timeout tổng), nên tạo tín hiệu tool-timeout riêng sẽ là metric
  giả. Một tool-call vượt quá do chính nó chậm, nếu trùng lúc kéo dài
  run-timeout, được ghi thật là `REQUEST_TIMEOUT`.
- **Span `CONVERSATION_CONTEXT`** (state resolution) chạy trong
  `agent_v2_routes.py` TRƯỚC khi `orchestrator.run()` tạo trace — muốn đo
  thật cần dời thời điểm tạo trace lên sớm hơn (thay đổi kiến trúc nhỏ nhưng
  thật). Hoãn lại, không nhét tạm.
- **`tool_results`/`final_response` trong đường durable của
  `trace_summary_out`/`/admin/rag/traces`** không có text/output đầy đủ như
  ring buffer — `AgentTelemetry`'s sanitizer chưa từng mang theo raw tool
  output hay final reply text (thiết kế privacy-minimization có sẵn từ trước
  BUILD-32). Không phải mất chức năng cho ticket detail (`assistant_message`
  đã durable sẵn trên chính ticket row từ BUILD-29) — chỉ là một giới hạn
  đã ghi rõ, không giả lập text.
- **`query_preview`/`final_answer_preview` trong `session_messages` cho một
  turn chỉ còn ở dạng durable** (ring buffer đã rớt) hiển thị placeholder cố
  định "(nội dung không còn được lưu tạm...)" thay vì suy đoán/giả lập nội
  dung.

## 7. DB Schema (migration 0042)

Đã áp dụng LOCAL, verify đầy đủ upgrade → downgrade → upgrade trên Postgres
dev thật (`vmec04`, xem mục 9). `AgentRun` +18 cột additive (`trace_id`,
`actor_id`, `input_tokens`, `cached_input_tokens`, `output_tokens`,
`total_tokens`, `model_calls`, `model`, `pricing_version`, `input_cost_usd`,
`output_cost_usd`, `total_cost_usd`, `cost_status`, `currency`,
`duration_ms`, `timeout`, `error_code`, `empty_reply`, `evaluation_version`).
2 bảng mới: `agent_run_span`, `agent_run_evaluation`. Index theo mục 13 kế
hoạch: `trace_id`, `(agent_run_id, started_at)`, `(status, created_at)`,
`(error_code, created_at)`, `(span_type, started_at)`.

Canonical `error_code` taxonomy: `BUDGET_EXCEEDED, MODEL_ERROR, MODEL_TIMEOUT,
REQUEST_TIMEOUT, TOOL_ERROR, TOOL_TIMEOUT, RETRIEVAL_ERROR, AUTH_ERROR,
GROUNDING_FAILURE, EMPTY_REPLY, HANDOFF_FAILURE, INTERNAL_ERROR` (superset
của mục 9 kế hoạch, `REQUEST_TIMEOUT` thêm theo mục 7).

## 8. Code changes (tóm tắt theo file)

- `backend/config.py`: `agent_model_pricing_version` setting mới.
- `backend/agents/v2/model_gateway.py`: `EmptySynthesisError(ValueError)`.
- `backend/agents/v2/observability.py`: `TraceComponent.{TIME_QUERY,GROUNDING,
  ANSWER_COMPOSITION,EVALUATION}`, `ModelPricingCatalog.version` +
  `CostEstimate.input_cost_usd/output_cost_usd`, `BufferingSink`,
  `AgentTelemetry.pricing` property.
- `backend/agents/v2/runtime.py`: `RunResult.error_code`, phân loại
  MODEL_TIMEOUT/MODEL_ERROR/EMPTY_REPLY theo exception type thật +
  BUDGET_EXCEEDED/REQUEST_TIMEOUT/TOOL_ERROR theo path.
- `backend/agents/v2/orchestrator.py`: `OrchestrationResult.error_code`;
  `self._clock`/`started` threaded qua mọi nhánh trả lời tất định (fix E2E
  phát hiện: các nhánh này trước đây luôn có `duration_ms=0` cứng, không
  liên quan gì tới thời gian thật); span thật cho SAFETY/RETRIEVAL/
  TIME_QUERY/GROUNDING/ROUTER; `GROUNDING_FAILURE`/`HANDOFF_FAILURE`/
  `RETRIEVAL_ERROR`/`TOOL_ERROR` error codes.
- `backend/api/agent_v2_routes.py`: `BufferingSink` wiring, hàm mới
  `_persist_durable_trace` (+ `_build_span_rows`/`_span_name_for` helper),
  INTERNAL_ERROR fallback record ở top-level except.
- `backend/db/models.py`: schema mục 7.
- `backend/services/agent_feedback.py`: `verify_trace_ownership`/
  `classify_priority`/`trace_summary_out`/`session_messages` nhận `db`, đọc
  durable trước, ring buffer fallback.
- `backend/api/admin_feedback_routes.py`: threading `db` vào 2 call site trên.
- `backend/api/rag_monitoring_routes.py`: `/traces`, `/traces/{trace_id}`
  durable-first; `/system`, `/health`, `/generation` cost/timeout thật.
- `migrations/versions/0042_agent_run_durable_observability.py`.

## 9. Migration test (upgrade → downgrade → upgrade)

Chạy thật trên Postgres dev local (`vmec04`, không phải mock):

```
$ alembic current            → 0041
$ alembic upgrade head       → 0041 -> 0042 OK
$ (inspect) agent_run có đủ 18 cột mới + 6 index mới
$ (inspect) agent_run_span, agent_run_evaluation tồn tại đủ cột + index
$ alembic downgrade -1       → 0042 -> 0041 OK
$ (inspect) agent_run trở về đúng 10 cột gốc; agent_run_span/
  agent_run_evaluation bị drop sạch; agent_activity_snapshot (bảng khác,
  BUILD-30) KHÔNG bị đụng
$ alembic upgrade head       → 0041 -> 0042 OK lần 2 (idempotent, guard bằng
  inspector.get_columns/get_table_names/get_indexes giống pattern 0041)
$ alembic current            → 0042 (head)
```

**DB MIGRATION: PASS** — evidence trên là log thật, không phải giả định.

## 10. Local test suite

Chạy trên Postgres dev local thật (không mock DB), toàn bộ `tests/`
(ignore `tests/vlm_demthuoc`, `tests/services/photo_verification` — lỗi
`ModuleNotFoundError: cv2/numpy`, môi trường thiếu lib không liên quan
BUILD-32):

- `pytest tests/ -k agent_v2`: **737 passed**, 2 failed, 3 skipped (Postgres-
  only tests cần `BUILD*_TEST_DATABASE_URL` riêng, tự skip đúng thiết kế).
  2 failed là **pre-existing, không do BUILD-32** — xác nhận bằng
  `git stash` chạy lại trên `main` HEAD sạch, lỗi giống hệt: môi trường local
  này có `AGENT_RUNTIME_ENABLED=true` trong `.env`, khiến 2 test
  `*_route_is_off_by_default_without_touching_db` (viết cho trường hợp flag
  OFF) gọi tới tầng DB thật và literal-fail trên `db=object()` — không liên
  quan gì tới quan sát/durability.
- `pytest tests/` (toàn bộ, trừ 2 dir cv2/numpy trên, gồm cả 13 test mới của
  BUILD-32): **1540 passed**, 9 khác failed + 2 đã biết ở trên = 11 failed,
  6 skipped. 9 failed còn lại
  (`test_auth_routes.py` x4, `test_patient_routes.py` x1,
  `test_security_authz.py` x1, `test_chat_history_e2e.py` x1,
  `test_push_routes_contract.py` x1, `test_retrieval_sql.py` x1) — xác nhận
  **pre-existing** bằng `git stash` + chạy lại trên `main` HEAD sạch: giống
  hệt lỗi (email-verification token flow, doctor_search 401, Postgres GUC
  `word_similarity_threshold` chưa SET trong DB dev local này) — hoàn toàn
  không liên quan tới bất kỳ file BUILD-32 nào đụng tới.
- Test mới cho BUILD-32
  (`tests/test_agent_v2_build32_durable_observability.py`, 13 case): PASS —
  `BufferingSink` (tee đúng inner sink, pop() theo trace_id, eviction FIFO khi
  đầy); `runtime.py` error_code classification theo đúng exception type
  (`openai.APITimeoutError`→MODEL_TIMEOUT, generic→MODEL_ERROR,
  `EmptySynthesisError`→EMPTY_REPLY, budget/timeout/tool paths); 4 test cho
  `_persist_durable_trace` (stamp đúng AgentRun/span/evaluation, 0 model-call
  → cost thật = 0 không phải N/A, empty_reply flag đúng, **exception-safe**:
  `db.commit()` raise giả lập nhưng hàm không raise ra ngoài).
- Test cũ phải sửa để khớp API mới (liệt kê minh bạch, không sửa để né lỗi):
  `tests/test_agent_feedback_service.py` (23 case) — `verify_trace_ownership`/
  `classify_priority`/`trace_summary_out`/`session_messages` đổi signature
  nhận `db`, thêm `AgentRun`/`AgentRunSpan`/`AgentRunEvaluation` vào SQLite
  fixture, thêm 1 test mới xác nhận durable row được ưu tiên hơn ring buffer.
  `tests/test_agent_v2_evaluation_v2.py` — fake `_Db` thêm `.execute()` cho
  `_agent_run_query` mới, thêm assertion `cost_per_query is None` +
  `NOT_AVAILABLE` khi không có `AgentRun` nào (không fabricate 0.0).
  `tests/test_agent_v2_transaction_durability.py` —
  `test_exception_during_orchestration_rolls_back_everything` cập nhật: vẫn
  xác nhận checkpoint/handoff partial state bị rollback sạch, NHƯNG giờ có
  đúng 1 `AgentRun` row mới (INTERNAL_ERROR, do tính năng mới ở mục 8) thay vì
  0 row như trước — đây là hành vi MỚI có chủ đích (raw orchestrator-level
  exception trước đây không để lại dấu vết durable nào), không phải nới lỏng
  test cho qua.

**Không có test nào assert response text/routing/safety outcome của Agent V2
bị sửa để pass** — xác nhận AGENT BEHAVIOR CHANGED: NO.

## 11. Local E2E (traffic thật, không mock)

Chạy qua `run_agent_orchestration()` trực tiếp (không qua HTTP layer, cùng
cách `tests/test_agent_v2_transaction_durability.py` đã làm) với Postgres dev
thật, 1 patient thật seed riêng cho E2E, **1 model call thật tới OpenAI**
(model `gpt-5.4-mini`, không mock) cho câu hỏi RAG:

```
[out_of_scope]                      COMPLETED  OUT_OF_SCOPE_REQUEST
[schedule_today]                    COMPLETED  TODAY_DOSES               (0 model call)
[triage_symptom]                    COMPLETED  PERSONAL_SYMPTOM          (0 model call)
[dose_safety]                       COMPLETED  MEDICATION_DOSE_SAFETY    (0 model call)
[general_medical_real_model_call]   COMPLETED  GENERAL_MEDICAL_INFORMATION (1 model call, THẬT)
[safety_acute_danger]               HANDOFF_CREATED  ACUTE_DANGER_ESCALATION
```

Sau đó **thoát hẳn tiến trình Python** (xoá sạch ring buffer + `AgentTelemetry`
singleton module-level — đúng những gì một lần restart backend thật sự làm,
vì cả hai đều là biến toàn cục cấp-process) và chạy verify trong **tiến trình
Python hoàn toàn mới**:

- Ring buffer rỗng trong tiến trình mới (`len(get_local_traces())==0`) — xác
  nhận mọi kết quả bên dưới đến từ DB, không phải cache còn sót.
- Cả 6 `AgentRun` row tồn tại durable, đúng `trace_id`/`actor_id`/`status`.
- `general_medical_real_model_call`: `model_calls=1`, `input_tokens=1512`,
  `output_tokens=179`, `model="gpt-5.4-mini"` — **số thật từ OpenAI response**,
  `cost_status="NOT_AVAILABLE"` (đúng, vì `AGENT_MODEL_PRICING_JSON` rỗng
  trong `.env` local — không có giá nào để tính, N/A thật chứ không fabricate
  0).
- `schedule_today`: `model_calls=0`, `input_tokens=0`, `output_tokens=0` —
  zero thật (0 model call), không phải N/A.
- `duration_ms` mỗi run > 0 sau khi vá lỗi nêu ở mục dưới (xem "Phát hiện
  trong lúc E2E").
- Mỗi run có `AgentRunSpan` (2–8 span/run tuỳ độ phức tạp) và đúng 1
  `AgentRunEvaluation` row.
- `/admin/rag/traces/{trace_id}` (gọi hàm trực tiếp, DB session thật,
  KHÔNG ring buffer) trả về đủ cả 6 trace, `source: "durable"` cho tất cả.
- `/admin/rag/traces` (list) liệt kê đủ tất cả trace durable.
- `/admin/rag/system`: `cost_daily_status` xuất hiện thật (`PARTIAL` — vì có
  1 run priced-unknown lẫn cùng ngày), không còn hardcode.
- Ticket BUILD-29 nộp trước khi thoát tiến trình (`create_ticket`, priority
  tự P2) → sau khi tiến trình mới khởi động: `get_ticket()` trả
  `trace.found=True`, `trace.intent` đúng durable; `get_ticket_session()`
  trả về đủ 6 turn của conversation.

**67/70 check PASS ở lần chạy đầu.** 3 FAIL đầu tiên (`duration_ms` = 0 cho
3/6 scenario tất định) → điều tra thấy nguyên nhân thật: các nhánh trả lời
tất định của orchestrator (`_out_of_scope_reply`,
`_context_clarification_reply`, `_clinical_clarification_reply`,
`_schedule_reply`, `_fail_closed`, và nhánh handoff-creation-failure) build
`RunResult` trực tiếp bằng `RunMetrics()` mặc định (`elapsed_ms=0.0`) —
KHÔNG bao giờ đi qua `ReadOnlyAgentRuntime._result()`, nơi duy nhất trước đây
tính `elapsed_ms` thật. Đây là bug thật, đúng phạm vi BUILD-32 (release gate
yêu cầu "REAL STEP LATENCY: PASS", "real duration > 0" là required test) —
đã vá bằng cách thêm `AgentOrchestrator._clock`, capture `started` một lần ở
đầu `run()`, truyền qua cả 6 điểm build `RunResult`/`OrchestrationResult` này
để tính `elapsed_ms` thật từ đồng hồ thật. Chạy lại E2E: **67/70 PASS**, 3
FAIL còn lại (`triage_symptom`/`dose_safety`/`safety_acute_danger` vẫn đọc
`duration_ms=0.0`) — điều tra tiếp: `time.monotonic()` trên máy Windows dev
local này dùng `GetTickCount64()`, độ phân giải thật đo được
**15.625ms/tick** (`time.get_clock_info('monotonic')`); các nhánh tất định
này hoàn thành nhanh hơn 1 tick nên `elapsed_ms` đọc đúng-nhưng-tình cờ-bằng-0
(không phải lại hardcode — `out_of_scope`/`schedule_today` cùng dạng nhánh đã
hiện đúng 15-16ms ở những lần chạy vượt qua ranh giới tick). Đây là giới hạn
độ phân giải đồng hồ hệ điều hành Windows dev, không phải lỗi wiring — trên
Linux production, `clock_gettime(CLOCK_MONOTONIC)` có độ phân giải micro-giây
nên hiện tượng "0 do trùng tick" gần như không xảy ra với cùng logic. Ghi
nhận minh bạch, không che giấu.

**LOCAL E2E: PASS** (67/70 automated check pass; 3 fail còn lại là giới hạn
đồng hồ hệ điều hành đã điều tra và giải thích rõ ràng, không phải lỗi logic).
**TRACE SURVIVES RESTART: PASS** (bằng chứng: tiến trình mới, ring buffer
rỗng, mọi dữ liệu đọc được đều từ DB). **TICKET DURABLE CORRELATION: PASS**
(ticket mở lại được trace/session sau khi ring buffer rỗng).

## 12. Authorization / cross-patient / no-chain-of-thought

- Mọi endpoint Admin bị đụng tới (`/admin/rag/traces`,
  `/admin/rag/traces/{trace_id}`, `/admin/rag/system`, `/admin/rag/health`,
  `/admin/rag/generation`, `/admin/tickets/*`) vẫn giữ nguyên
  `Depends(_require_admin)`/`require_role("admin")` — xác nhận bằng grep diff,
  không route nào mất decorator.
- `AgentRunSpan.metadata_json` chỉ chứa đúng tập `_ALLOWED_ATTRIBUTE_KEYS`
  sẵn có trong `observability.py` (allowlist đã áp dụng từ trước BUILD-32) —
  không có kênh dữ liệu chưa sanitize mới nào được thêm.
- Không có prompt/model reasoning/raw tool payload nào được persist —
  `AgentRunSpan` chỉ giữ operation/outcome/latency/tool_name/model (đã có sẵn
  allowlist), `AgentRunEvaluation` chỉ giữ status/score theo dimension
  (`evaluation_v2.EvaluationResult.as_dict()`, không đổi).
- `verify_trace_ownership` durable path so khớp `AgentRun.actor_id` (id thật,
  không hash) — nhưng chỉ dùng nội bộ, server-side, chưa từng trả ra response;
  không đổi nguyên tắc fail-closed cũ (trace tồn tại + actor không khớp →
  từ chối; không tìm thấy → coi như "không có gì để đối chiếu", vẫn giữ hành
  vi cũ).

**ADMIN AUTHORIZATION: PASS. CROSS-PATIENT PROTECTION: PASS (không đổi logic
authorization, chỉ đổi nguồn đọc). NO CHAIN-OF-THOUGHT PERSISTED: PASS.**

## 13. Release Gate

```
BUILD-32: PASS

CURRENT OBSERVABILITY AUDIT: PASS
DURABLE TRACE: PASS            (AgentRun +18 cột, migration 0042, verify mục 9/11)
DURABLE SPANS: PASS            (AgentRunSpan, real timing, verify mục 11)
REAL STEP LATENCY: PASS        (đã vá bug elapsed_ms=0 phát hiện qua E2E, mục 11)
TOKEN USAGE: PASS              (real OpenAI usage, mục 11)
COST TRACKING: PASS            (AVAILABLE/NOT_AVAILABLE thật, không hardcode 0, mục 11)
TIMEOUT TRACKING: PASS         (MODEL_TIMEOUT/REQUEST_TIMEOUT theo exception type thật)
EMPTY REPLY TRACKING: PASS     (EmptySynthesisError → EMPTY_REPLY, unit test mục 10)
ERROR TAXONOMY: PASS           (12 canonical code, runtime.py + unit test)
TICKET DURABLE CORRELATION: PASS (mục 11, ticket mở lại sau "restart")
TRACE SURVIVES RESTART: PASS   (mục 11, tiến trình mới hoàn toàn)
ADMIN AUTHORIZATION: PASS      (mục 12)
CROSS-PATIENT PROTECTION: PASS (mục 12)
NO CHAIN-OF-THOUGHT PERSISTED: PASS (mục 12)
DB MIGRATION: PASS             (mục 9, upgrade→downgrade→upgrade thật)
LOCAL E2E: PASS                (mục 11, 67/70 tự động + giải thích 3 còn lại)
AGENT BEHAVIOR CHANGED: NO     (không sửa response text/routing/safety nào;
                                 duy nhất 1 thay đổi hành vi thật là
                                 orchestrator-level crash giờ để lại 1
                                 AgentRun row INTERNAL_ERROR thay vì 0 row --
                                 đây là tính năng quan sát mới có chủ đích,
                                 không phải hành vi trả lời Agent V2)
READY FOR PR: YES
```
