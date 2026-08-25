# BUILD-37 — Production Release & Validation

**Ngày**: 2026-08-25
**Phạm vi**: Release + verify BUILD-32→36 lên production một cách có kiểm soát. Không thêm feature mới, không sửa runtime/router/safety để "làm đẹp" dashboard.

---

## 1. Pre-release audit

- **PR #116 (BUILD-36) đã merge**: `mergedAt: 2026-08-25T13:03:59Z`, merge commit `7e64491`, xác nhận qua `gh pr view 116 --json state,mergedAt,mergeCommit` → `state: MERGED`.
- **Checkout/pull latest origin/main**: `git fetch origin --prune` → `git checkout main && git pull --ff-only` → fast-forward `3aeb873 → 7e64491`, `git status --short` sạch (chỉ còn 3 file loose không liên quan, có từ trước session này: `ba_audit.txt`, `schema_snapshot_post_stamp.txt`, `schema_snapshot_pre_24r.txt` — không đụng tới).
- **Commit release**: `7e6449176fb83a809258eda51e14fd5a7e239634` (merge PR #116).
- **Migration chain tới head**: `alembic heads` → 1 head duy nhất `0045`. Thứ tự xác nhận: `0041→0042 (BUILD-32) →0043 (BUILD-33) →0044 (BUILD-34) →0045 (BUILD-36)`.
- **Railway target**: project `VMEC-04` (`14b221cb-1a7b-4b20-b5d1-331268729371`), environment `production`, services `VMEC-04/BE` + `VMEC-04/FE` + `Postgres`.
- **Không deploy từ feature branch/worktree cũ**: deploy thực hiện từ 1 `git worktree` **mới, sạch**, checkout đúng `7e64491` (`git worktree add /tmp/build37-release-worktree 7e64491 --detach`) — tránh rủi ro 3 file loose ở trên lọt vào image qua `COPY . .` của Dockerfile.
- **Không có agent/session khác đang deploy cùng lúc**: `railway deployment list --service VMEC-04/BE --json` xác nhận deployment đang live (`b71cef2f`, trước khi tôi deploy) ở trạng thái `SUCCESS` ổn định, không có deployment nào `BUILDING/DEPLOYING` đồng thời; deployment ID thay đổi đúng 1 lần theo hành động của tôi (`baf0d53f` do set biến môi trường → `44be6145` do `railway up` thật).
- **Deployment commit/hash trước và sau**:
  - **BE trước**: deployment `b71cef2f-2133-4659-ac7f-f24958732851`, `cliMessage: "BUILD-32 exact main HEAD 9ba8882"` — xác nhận `9ba8882` là ancestor thật của `main` hiện tại (`git merge-base --is-ancestor 9ba8882 HEAD` → true), `main` đi trước 15 commit.
  - **BE sau**: deployment `44be6145-0a42-4633-b8a4-dfab518d3249`, build từ worktree tại `7e64491`.
  - **FE trước**: deployment `d3486072-337e-4a3b-9d66-77288aa9f8bc` (2026-08-24T15:33:36Z) — build cũ, KHÔNG có route `/admin/monitoring` (xác nhận 404 trước khi deploy FE — xem §3).
  - **FE sau**: deployment `41155de8-d539-4e19-a5d0-aa78c9aaa518` — build log liệt kê rõ `/admin/monitoring`, `/admin/monitoring/traces`, `/admin/monitoring/traces/[traceId]`, `/admin/monitoring/sessions/[conversationId]`.

**Phát hiện quan trọng, xử lý minh bạch (không tự quyết)**:
1. `AGENT_JUDGE_ENABLED` chưa từng được set trên production (`config.py` default `False`) dù đã có đủ credentials Judge thật — nghĩa là scheduler `_run_judge_worker` (dù luôn được add vào job store) chạy no-op vì `agent_judge_enabled` gate ở `escalation_scheduler.py:100`. **Đã hỏi người dùng, được xác nhận bật `AGENT_JUDGE_ENABLED=true`** như một phần của release này (thay đổi hành vi/chi phí thật, không tự quyết).
2. `agent_safety_event` là bảng MỚI (migration 0044 vừa chạy) nên không có existing event nào để verify §7. **Đã hỏi người dùng, được xác nhận gửi 1 câu acute-danger thật lên tài khoản canary** (không phải bệnh nhân thật, cùng cơ chế đã dùng ở BUILD-24O/34) để tạo 1 safety event thật, verify toàn bộ pipeline end-to-end.

---

## 2. Migration verification

**Trước deploy** (đọc trực tiếp qua `DATABASE_PUBLIC_URL`, read-only, không tự stamp/repair):

```text
alembic_version (BEFORE): 0042
tables present: agent_feedback_ticket, agent_run, agent_run_evaluation, agent_run_span
tables MISSING: agent_run_judge, agent_safety_event, agent_golden_run, agent_golden_run_case
agent_run columns: (không có prompt_version/retrieval_version)
agent_run row count: 591
```

**Deploy log thật** (`railway logs --deployment 44be6145...`, `preDeployCommand: python scripts/safe_migrate.py`):

```text
[PRE-DEPLOY] Current DB revision '0042' is valid.
[PRE-DEPLOY] Running alembic upgrade head...
INFO  [alembic.runtime.migration] Running upgrade 0042 -> 0043, BUILD-33: durable production LLM Judge V2 results.
INFO  [alembic.runtime.migration] Running upgrade 0043 -> 0044, BUILD-34: canonical durable Safety/Handoff monitoring event.
INFO  [alembic.runtime.migration] Running upgrade 0044 -> 0045, BUILD-36: durable persistence for golden-evaluation runs + 2 ticket indexes.
[PRE-DEPLOY] Migrations complete successfully.
```

**Sau deploy** (đọc trực tiếp lại, độc lập với log trên):

```text
alembic_version (AFTER): 0045
tables present: agent_feedback_ticket, agent_golden_run, agent_golden_run_case, agent_run,
                agent_run_evaluation, agent_run_judge, agent_run_span, agent_safety_event
agent_run new columns: prompt_version, retrieval_version  (cả 2 đều có)
agent_feedback_ticket indexes: ix_agent_feedback_ticket_trace_id, ix_agent_feedback_ticket_agent_run_id (cả 2 đều có)
agent_run row count: 591  (không đổi -- migration additive-only, không mất dữ liệu)
```

Không có migration drift. Không cần repair/stamp thủ công.

---

## 3. Deploy

- `VMEC-04/BE`: `railway up --service VMEC-04/BE --environment production -c` từ worktree sạch tại `7e64491` → `Deploy complete`, deployment `44be6145`.
- `VMEC-04/FE`: **phát hiện thật trong lúc verify** — sau khi BE deploy xong, `GET https://c3-app-067.up.railway.app/admin/monitoring` trả về **404** vì FE service chưa được redeploy (deployment cũ `d3486072`, trước BUILD-36 merge). Đã deploy `frontend/` riêng (`railway up --service VMEC-04/FE ...`), build log liệt kê rõ các route mới, sau đó `/admin/monitoring` → 200.
- **Backend health**: `GET /health` → `200 {"status":"ok","env":"production"}`. Log khởi động sạch: `Drug Knowledge V2 warmup complete: products=3556 chunks=42588`, `Scheduler started` với đủ 5 job (`_run_reminder_check`, `_run_hourly_summary`, `_run_dose_push_reminder`, `_run_photo_cleanup`, `_run_judge_worker`), `Application startup complete`, không exception/traceback nào trong toàn bộ log khởi động.
- **Frontend health/load**: `GET /` → 200, `GET /admin/monitoring` → 200, `GET /admin/monitoring/traces` → 200, `GET /admin/tickets` → 200. Log khởi động: `Next.js 16.3.0 ... Ready in 0ms`, sạch.
- **Postgres reachable**: xác nhận trực tiếp qua kết nối read-only thật (không qua trung gian) trong toàn bộ §2 và các phần sau.
- **Scheduler/worker startup**: xác nhận qua log — `_run_judge_worker` chạy tick 30s thật, `Job "_run_judge_worker (...) executed successfully"`.
- **Không có crash loop**: 1 chu kỳ khởi động sạch duy nhất mỗi service (BE có 1 lần "Stopping Container"/"Starting Container" — đây là lifecycle bình thường của Railway giữa bước pre-deploy-command và app container, không phải crash).

---

## 4. Agent V2 production smoke (A–D)

**Sự cố methodology tự phát hiện, KHÔNG phải bug production** (ghi nhận trung thực): batch smoke test đầu tiên (A/B/D) dùng `curl -d "<văn bản có dấu>"` inline qua Windows Git Bash — text tiếng Việt có dấu bị hỏng byte trước khi rời máy, khiến `classify_intent()` nhận được text đã hỏng và fallback sai intent (D trả lời generic thay vì triage). Test C (Paracetamol) không bị lộ vì entity chính là ASCII. Xác minh gốc rễ bằng 3 bước: (1) gọi thẳng backend không qua proxy với cùng câu B, dùng `--data-binary @file` (tránh encode qua shell argument) → intent đúng `TODAY_DOSES`; (2) gửi lại đúng câu B có dấu qua PROXY nhưng vẫn `-d` inline → vẫn sai (loại trừ giả thuyết "cold start tự sửa"); (3) gửi lại đúng câu B có dấu qua PROXY với `--data-binary @file` → đúng ngay. **Kết luận: lỗi encode ở tooling test của tôi (Windows Git Bash shell-argument), không phải lỗi hệ thống thật.** Từ đây về sau mọi request có dấu đều dùng file UTF-8 thật.

**Kết quả A–D thật, sạch, qua `/api/chat` (frontend proxy), tài khoản canary `agent-v2-canary-patient1-account`**:

| # | Query | intent (durable) | execution_path | status | model_calls | tokens | cost |
|---|---|---|---|---|---|---|---|
| A | "Bệnh tiểu đường là gì?" | `GENERAL_MEDICAL_INFORMATION` | `GENERAL_MODEL` | COMPLETED (honest decline, `error_code=GROUNDING_FAILURE` — đúng, không fabricate kiến thức không có bằng chứng) | 1 | 863 | $0.0017 |
| B | "Hôm nay tôi uống thuốc gì?" | `TODAY_DOSES` | `DETERMINISTIC_SCHEDULE` | COMPLETED, reply có ngày thật "25/08/2026" | 0 | **0** | **$0.0** |
| C | "Công dụng của thuốc Paracetamol là gì?" | `DRUG_INFORMATION` | `DRUG_LOOKUP` | COMPLETED, trả lời đúng nội dung thuốc thật | 1 | 1695 | $0.0019 |
| D | "Tôi cảm thấy hơi đau đầu..." | `PERSONAL_SYMPTOM` | `TRIAGE` | COMPLETED, clinical clarification + hướng dẫn 115 nếu nặng lên | 0 | **0** | **$0.0** |

- **`/api/chat` thực sự đi Agent V2**: response có `chatbot_version:"agent-v2"`, `trace_id`, `agent_run_id` thật ở mọi request.
- **Không Legacy fallback âm thầm**: `CHAT_RUNTIME` production vẫn `v2` (không đổi), mọi response đều có field Agent V2 (`safety_disposition`, `handoff_id`, `citations`) — legacy response shape không có các field này.
- **trace_id/agent_run_id được tạo**: có ở cả 4/4.
- **Durable AgentRun persisted**: xác nhận trực tiếp bằng query cho cả 4 `agent_run_id` — khớp 100% với response.
- **execution_path đúng**: khớp đúng semantics từng loại (schedule → DETERMINISTIC_SCHEDULE 0 token, symptom → TRIAGE 0 token, drug → DRUG_LOOKUP có token, general → GENERAL_MODEL có token).
- **Không có unexpected error**: `error_code` chỉ xuất hiện ở A (`GROUNDING_FAILURE`, đúng — honest decline theo thiết kế BUILD-24F, không phải lỗi).

---

## 5. Durable Observability verification

Xác nhận trực tiếp qua DB + qua `GET /traces/{trace_id}` thật (dùng trace an toàn của scenario Safety, §7):

- **AgentRun/AgentRunSpan/AgentRunEvaluation persisted**: có đủ, `trace_detail()` trả về 5 span thật (`ROUTER`, `RUNTIME`×2, `GROUNDING`, `EVALUATION`) với duration thật (không phải giả lập).
- **duration thật**: `duration_ms` thật khác nhau theo từng loại request (schedule ~7ms deterministic, model-call ~2.2-3.5s thật).
- **token usage thật khi có model call**: A=863, C=1695 (khác nhau, thật theo độ dài câu trả lời thật).
- **schedule/no-model path có token=0**: B và D xác nhận `total_tokens=0`, KHÔNG phải N/A — một số 0 thật (đúng đắn theo `_persist_durable_trace`'s `metrics.model_calls <= 0` branch).
- **cost semantics đúng**: B/D `cost_status=AVAILABLE, total=0.0` (0 thật vì 0 model call); A/C `cost_status=AVAILABLE` với giá trị thật > 0.
- **unknown pricing = NOT_AVAILABLE, không phải 0**: Judge dùng model `anxs/gemini-3.7-flash-high` (không có trong `AGENT_MODEL_PRICING_JSON`) → `agent_run_judge.cost_status=NOT_AVAILABLE`, `cost_usd=NULL` — xác nhận trực tiếp, không phải giả định.
- **timeout/error/empty_reply không hardcode**: tất cả 4 smoke query đều `timeout=false`, `empty_reply=false` (thật, vì đều có reply thật); `error_code` chỉ có ở A, đúng thực tế.
- **Trace vẫn xem được sau restart/redeploy**: BE đã restart 2 lần trong buổi (đợt set biến môi trường, đợt `railway up` thật) — dữ liệu `agent_run` với 591 row từ trước migration này vẫn nguyên vẹn sau cả 2 lần restart (row count không đổi qua migration).

**Bug thật tìm thấy VÀ SỬA trong lúc verify §5/§12** (không có trong code trước khi bắt đầu BUILD-37, do chính BUILD-36 viết): `trace_detail()` so khớp ring buffer bằng `t.id == run.id` (agent_run_id) thay vì `t.id == run.trace_id` — `TraceRecord.id` thực chất được stamp từ `trace_id` (xem `TelemetryService.create_trace`/`_record_agent_v2_telemetry`), nên so sánh này KHÔNG BAO GIỜ khớp — `content_available` luôn `False` dù trace vừa mới tạo vài giây trước và vẫn còn thật trong buffer. Phát hiện bằng cách đối chiếu 2 endpoint cho CÙNG 1 trace: `/sessions/{id}` (đúng, key theo trace_id) trả về nội dung thật, `/traces/{id}` (sai) báo "content unavailable" cho cùng trace đó. **Đã sửa** (`run.trace_id` thay vì `run.id`), thêm 2 test hồi quy (1 xác nhận `False` trung thực khi không có gì trong buffer, 1 seed `TraceRecord` thật qua `TelemetryService` thật và xác nhận nội dung thật hiện ra đúng) — 46/46 pass, ruff clean. Đây là fix riêng, **PR #118, CHƯA merge/deploy** — production hiện tại (ngay sau BUILD-37) vẫn còn bug này (`content_available` sai `False`) cho tới khi PR #118 được review/merge/deploy riêng.

Raw query/reply text phụ thuộc ring buffer theo thiết kế — **không tính là failure của BUILD-37** (giới hạn kiến trúc có chủ đích, đã ghi trong `ARCHITECTURE.md` §"Agent V2 Observability Pipeline" mới). UI degrade honest khi mất nội dung: đã xác nhận qua code (`content_available: buffered is not None`, không tái tạo/giả lập) — sau khi fix PR #118, hành vi sẽ đúng thật cho cả 2 trường hợp (còn buffer / đã mất buffer).

---

## 6. Judge production verification

- **Scheduler job active**: `_run_judge_worker` có trong job store, tick 30s, log xác nhận `executed successfully` nhiều lần.
- **judge_enabled/config đúng chính sách production**: `AGENT_JUDGE_ENABLED=true` (mới bật, theo xác nhận người dùng §1), `AGENT_JUDGE_SAMPLING_RATE` không set → default `0.05` (5%).
- **Sampling rate đúng — ordinary traffic không bị judge 100%**: xác nhận qua dữ liệu thật — 606 `agent_run` nhưng chỉ 5 `agent_run_judge` (~0.8%), toàn bộ 5 đều `eligibility_reason` ưu tiên (`ERROR_OR_FALLBACK`×4, `SAFETY_ANOMALY`×1) — KHÔNG có row nào tới từ random-sample roll trúng (đúng thống kê với mẫu nhỏ và 5% rate), nhưng cơ chế ưu tiên hoạt động thật.
- **Ticket/safety/anomaly priority đúng**: 4 run có `error_code=GROUNDING_FAILURE` (honest-decline, coi là fallback/anomaly) → tự động enqueue dù không trúng roll ngẫu nhiên; 1 run safety-escalation → enqueue với `eligibility_reason=SAFETY_ANOMALY`, khớp đúng scenario §7.
- **AgentRunJudge chuyển JUDGE_PENDING → JUDGE_COMPLETED**: xác nhận — cả 5/5 row hiện tại đều `JUDGE_COMPLETED` (0 pending, 0 failed tại thời điểm kiểm tra) — scheduler tick 30s đã xử lý xong trước khi tôi kiểm tra.
- **Judge failure không ảnh hưởng chat response**: đảm bảo bằng kiến trúc (Judge chạy ở tiến trình/tick riêng, sau khi response đã trả về patient từ lâu — xem sơ đồ `ARCHITECTURE.md` mới) — không phải try/except phòng thủ tại request time.
- **Judge token/cost tách khỏi Agent cost**: `agent_run_judge` có cột `input_tokens`/`output_tokens`/`cost_usd`/`cost_status` RIÊNG, độc lập hoàn toàn với `agent_run`'s cost fields — xác nhận qua schema + dữ liệu thật (Judge cost `NOT_AVAILABLE`, Agent cost vẫn `AVAILABLE` bình thường).
- **provider/model/rubric/version persisted**: `judge_provider='google'`, `judge_model='anxs/gemini-3.7-flash-high'`, `rubric_name='judge-general-medical'`, `rubric_version='rubric-v1'` — tất cả real, đọc trực tiếp từ row thật, không suy diễn.

**Xác nhận rõ provider/model THẬT của production** (yêu cầu §6 quan trọng nhất, không giả định = local Vilao config): production dùng `google` / `anxs/gemini-3.7-flash-high` qua `AGENT_JUDGE_BASE_URL=https://api.vilao.ai/v1` — đọc trực tiếp `railway variables` + xác nhận khớp với giá trị thật trên các row `agent_run_judge` đã chấm điểm thật (điểm thật khác nhau: 0.3/0.35/0.55/0.65/1.0 — không phải giá trị cố định/giả).

---

## 7. Safety & Handoff monitoring

**1 safety event thật được tạo có kiểm soát** (đã xin xác nhận người dùng §1, tài khoản canary, câu "Tôi vừa nôn ra máu" — 0 model call, deterministic path):

- Response: `status=HANDOFF_CREATED`, `safety_disposition=HANDOFF_REQUIRED`, `handoff_id` thật, reply đúng theo `runtime.py`'s fixed reason-code message (có "115", không có liều lượng cụ thể).
- `agent_safety_event`: `outcome=HANDOFF_REQUIRED`, `reason_code=ACUTE_DANGER_DETECTED`, `severity=CRITICAL`, `severity_source=reason_code_mapped`, `handoff_required=true`, `handoff_created=true`, `handoff_id` khớp.
- **Live `DoctorReviewRequest` join**: `doctor_review_request.status='ASSIGNED'` khớp với `agent_safety_event.handoff_status` snapshot ('ASSIGNED') — cả 2 đọc ra cùng trạng thái tại cùng thời điểm (không lệch, dù snapshot column theo thiết kế KHÔNG được sync lại sau này — đây là behavior đúng theo BUILD-34, không phải trùng hợp).
- `overview_metrics`: `safety_trigger_rate.numerator=1`, `handoff_rate.numerator=1` — khớp chính xác 1/1 với DB.
- **`REVIEW_SUSPECTED_MISSED_RISK` chỉ là review signal**: xác nhận bằng thiết kế/structural test đã có từ BUILD-34 (0 `db.add`/`SafetyDecision(` trong hàm sinh signal này) — không đổi trong BUILD-37.
- **Judge không override SafetyDecision**: trace của chính event này CÓ được Judge chấm (`eligibility_reason=SAFETY_ANOMALY`, `overall_score=1.0`, dimension scores `response_appropriateness/escalation_communication/possible_missed_risk_signal` đều 1.0) nhưng **safety_disposition/handoff_id/agent_safety_event không hề thay đổi bởi Judge** — Judge chạy SAU, ghi vào bảng riêng (`agent_run_judge`), không viết lại `agent_safety_event`/`doctor_review_request`.

---

## 8. Golden Evaluation production/dashboard integration

- **Schema tồn tại**: `agent_golden_run`/`agent_golden_run_case` có mặt sau migration 0045 (xác nhận §2).
- **Chưa có persisted run nào trên production** (đúng thực tế — chưa ai chạy `run_golden_evaluation.py --persist` nhắm production kể từ khi bảng này tồn tại).
- **Dashboard hiển thị đúng, không fabricate**: `GET /golden` → `{"available":true,"has_run":false}` — trung thực, không trả về số liệu giả.
- **Không chạy golden evaluation trả phí/full trên production trong build này** — theo đúng chỉ dẫn (chỉ optional "nếu phù hợp policy", không được người dùng yêu cầu rõ ràng như mục Judge/Safety), để tránh tốn thêm token/cost ngoài dự kiến của việc release.

---

## 9. Admin Dashboard V2 — verify thật, đối chiếu DB/API

Không chỉ verify page load — đối chiếu số liệu trực tiếp:

**`/overview`** (JSON thật) đối chiếu với DB (đọc độc lập, không qua endpoint):

| Metric | Dashboard | DB trực tiếp | Khớp |
|---|---|---|---|
| `total_requests` | 606 | `SELECT count(*) FROM agent_run` = 606 | ✓ |
| `success_rate.numerator` | 526 | `WHERE status='COMPLETED'` = 526 | ✓ |
| `error_rate.numerator` | 9 | `WHERE error_code IS NOT NULL` = 9 | ✓ |
| `safety_trigger_rate.numerator` | 1 | `SELECT count(*) FROM agent_safety_event` = 1 | ✓ |
| `judged_rate.numerator` | 5 | `SELECT count(*) FROM agent_run_judge` = 5 | ✓ |
| `ticket_rate.numerator` | 3 | distinct `agent_run_id` trong `agent_feedback_ticket` = 3 | ✓ |

**Mọi endpoint khác đã gọi thật và kiểm tra nội dung** (không chỉ HTTP 200):
- `quality`: `golden_hit_rate_at_10`/`mrr`/`ndcg` đúng `NOT_APPLICABLE` với `reason: no_stable_retrieval_id_contract_see_build_31_and_build_35`; `judge_overall_score=0.57` thật (trung bình 5 row thật); `metric_type` đúng `HEURISTIC`/`GOLDEN`/`LLM_JUDGE` phân biệt rõ.
- `retrieval`: `rag_query_volume=5`, `grounding_failure_rate` đúng 9/606, `empty_retrieval_rate` đúng `NOT_APPLICABLE` với lý do fix từ BUILD-36 (`grounding_failure_spans_multiple_intents...`).
- `performance`: percentile thật theo từng span type, `SAFETY`/`HANDOFF`/`CHECKPOINT` đúng `NOT_APPLICABLE` (chưa có span type đó trong mẫu thật).
- `cost`: `agent_cost_usd=0.0497` thật, `judge_cost_usd` đúng `NOT_AVAILABLE`, `by_model_usd` thật.
- `errors`: `TOOL_TIMEOUT`/`RETRIEVAL_TIMEOUT` đúng luôn-0 kèm `note` giải thích rõ never-emitted — không giả vờ là đã đo được.
- `judge`: `total_judged=5`, phân phối điểm thật, `judge_cost_usd` đúng `NOT_AVAILABLE`.
- `golden`: `has_run=false` trung thực.
- `versions/filters`: giá trị distinct THẬT từ DB (`model=["gpt-5.4-mini"]`, `error_code=["GROUNDING_FAILURE"]`, `golden_set_version=[]` rỗng đúng).
- `traces`/`traces/{id}`/`sessions/{id}`: xem §12.

---

## 10. Metric semantics — verify thật trên production

- **N/A ≠ 0, NOT_AVAILABLE ≠ 0**: xác nhận nhiều lần thật — `judge_cost_usd` `NOT_AVAILABLE` (không phải `$0`), `golden_*` `NOT_APPLICABLE` (không phải `0.0`), `empty_retrieval_rate` `NOT_APPLICABLE`.
- **denominator/sample_count đúng**: mọi rate field đều có `numerator`/`denominator`/`sample_count` khớp giá trị thật đã đối chiếu ở §9.
- **live vs golden vs heuristic vs LLM_JUDGE labels đúng**: `quality` endpoint có `metric_type` phân biệt rõ 3 nhóm, không trộn lẫn.
- **live HitRate/MRR/NDCG vẫn N/A**: xác nhận đúng, chưa có stable retrieval ID contract (BUILD-31/35 chưa giải quyết, BUILD-37 không mở rộng scope để tự sửa).
- **TOOL_TIMEOUT/RETRIEVAL_TIMEOUT không giả như event thật**: xác nhận — luôn 0 kèm `note` never-emitted rõ ràng trong chính response, không phải chỉ ở tooltip UI.
- **Safety metric scope_note hiện đúng khi filter không áp đầy đủ**: đã verify qua BUILD-36's test suite (2 test mới trong code review response) — không re-test lại bằng filter thật trên production riêng cho mục này vì logic hoàn toàn giống, đã cross-check `error_code=GROUNDING_FAILURE` filter thật ở §11 cho phần filter chung.

---

## 11. Filters — verify backend thực sự đổi kết quả (không chỉ dropdown UI)

| Filter | Không filter | Có filter | Khớp kỳ vọng |
|---|---|---|---|
| `date_from=2026-08-25T14:00:00Z` | `total_requests=606` | `total_requests=1` | ✓ thu hẹp thật |
| `error_code=GROUNDING_FAILURE` | `total_requests=606` | `total_requests=9` | ✓ khớp chính xác với DB (§9) |

`versions/filters` trả về đúng giá trị distinct thật (không phải danh sách tĩnh) — model/prompt_version/retrieval_version/execution_path/status/error_code/judge_model/rubric_version/safety_severity đều lấy từ `SELECT DISTINCT` thật trên DB hiện tại (production hiện chỉ có 1 giá trị mỗi loại vì mới release, nhưng cơ chế là real query, không phải hard-code — đã unit-test kỹ ở BUILD-36 với nhiều giá trị khác nhau). `model`/`prompt_version`/`retrieval_version`/`execution_path`/`status`/`judge_score_min/max` dùng chung 1 hàm `_apply_agent_run_filters` với `date_from`/`error_code` đã test thật ở trên — cùng code path, không phải logic riêng biệt có rủi ro khác.

---

## 12. Trace / Session / Ticket drill-down

Verify end-to-end thật, không copy/paste ID thủ công (dùng đúng `trace_id`/`handoff_id` trả về từ chính response gốc):

- **trace list → trace detail**: `GET /traces/{trace_id}` (dùng trace safety-test) trả về đầy đủ: 5 span thật, tokens/cost thật (0/0.0), evaluation thật (`execution_path=SAFETY`), **Judge thật** (`judge_status=JUDGE_COMPLETED`, score + dimension scores + `eligibility_reason=SAFETY_ANOMALY`), **Safety thật** (outcome/reason_code/severity/handoff), `ticket: null` (đúng — chưa có ticket cho run này).
- **session**: `GET /sessions/{conversation_id}` trả về đúng 1 turn với `query_preview`/`final_answer_preview` là nội dung thật (khác với `/traces/{id}` cùng lúc báo `content_available:false` — chính là bug đã tìm và sửa ở §5, PR #118).
- **Evaluation V2 / Judge / Safety đều correlate đúng** trong CÙNG 1 response `trace_detail` — không cần gọi nhiều endpoint riêng để ráp lại thủ công.
- **Ticket correlation**: không test round-trip mới (không tạo ticket mới ngoài kế hoạch), nhưng `ticket_rate.numerator=3` (§9) xác nhận cơ chế correlation hoạt động với dữ liệu ticket có sẵn từ trước.
- **Old durable trace vẫn có metadata sau deploy**: 591 `agent_run` row từ trước migration/deploy này vẫn nguyên vẹn (row count không đổi qua 2 lần restart, xem §2/§5) — dashboard đọc được cả dữ liệu cũ lẫn mới cùng lúc (VD: `total_requests=606` bao gồm cả 591 cũ).
- **Raw query/reply unavailable → render honest**: xác nhận qua code (`content_available: buffered is not None` — chưa fix xong sẽ luôn `False`, ĐANG chờ PR #118; sau khi merge sẽ đúng cho cả 2 trường hợp).

---

## 13. Authorization — verify thật qua HTTP, không chỉ code

| Route | Admin token | Patient token | Không token |
|---|---|---|---|
| `/overview`, `/quality`, `/retrieval`, `/performance`, `/cost`, `/errors`, `/judge`, `/golden`, `/versions/filters` | 200 (9/9) | 403 (9/9) | 401 |
| `/traces?limit=5` | 200 | — | — |

Doctor/caregiver không có token thật trên production để test trực tiếp trong build này — nhưng `require_role("admin")` là dependency DUY NHẤT áp cho mọi route (không có logic riêng theo role không-phải-admin), và cả 3 role non-admin (patient/doctor/caregiver) đã được test thật qua `account_client` fixture + Postgres thật trong BUILD-36's own test suite (`test_patient_doctor_caregiver_denied_every_monitoring_route`, real Postgres). Kết hợp bằng chứng production-live (patient → 403 thật) + bằng chứng test-suite (đủ 3 role) là đủ, không cần mint thêm token doctor/caregiver riêng chỉ để lặp lại đúng 1 cơ chế uniform.

**Không leak cross-patient data**: routes này không nhận `patient_id` filter theo caller — chỉ admin mới gọi được, và mọi dữ liệu trả về là aggregate/theo `agent_run_id`/`trace_id` cụ thể (không phải theo `patient_id` của người gọi) — không có surface cho cross-patient leak kiểu BUILD-29's `verify_trace_ownership` (route đó dành cho patient tự xem trace của mình, khác route admin này).

---

## 14. Frontend verification

- **Admin navigation có Monitoring**: `frontend/src/app/admin/layout.tsx` có entry "Admin Monitoring V2" (từ BUILD-36, không đổi ở BUILD-37).
- **Tab load đúng**: `GET /admin/monitoring`, `/admin/monitoring/traces` → 200 (server-rendered, route thật tồn tại trong build production, xác nhận qua build log liệt kê route + qua HTTP status thật).
- **Loading/empty/error/N/A states**: đã code-review + unit-test kỹ ở BUILD-36 (`NAValue` render literal "N/A"); BUILD-37 không sửa code frontend nên không re-verify lại từ đầu, chỉ xác nhận build/deploy thành công và route load được.
- **Trace/session/ticket links**: cấu trúc route `/admin/monitoring/traces/[traceId]`, `/admin/monitoring/sessions/[conversationId]`, `/admin/tickets/[id]` đều có trong build output.
- **Giới hạn thật của lần verify này**: không có browser automation (Playwright/Puppeteer) trong repo (đã xác nhận từ BUILD-36) — không kiểm tra được console/runtime error qua browser thật. Verify dừng ở: build production thành công (không lỗi TypeScript/build), route trả 200, API layer trả dữ liệu đúng cấu trúc frontend mong đợi (đã match type trong `admin-monitoring.ts` từ BUILD-36). Đây là giới hạn phương pháp, không phải bằng chứng có lỗi.

---

## 15. Rollback readiness

- **Previous stable deployment BE**: `b71cef2f-2133-4659-ac7f-f24958732851` (commit `9ba8882`, "BUILD-32 exact main HEAD"), trạng thái `SUCCESS`, healthy trước khi tôi deploy.
- **Previous stable deployment FE**: `d3486072-337e-4a3b-9d66-77288aa9f8bc` (2026-08-24T15:33:36Z), trạng thái `SUCCESS`.
- **Rollback method** (2 đường, đã xác nhận khả dụng):
  1. **Railway dashboard**: mở deployment card cũ (`b71cef2f`/`d3486072`) → nút "Redeploy" — dùng lại đúng image đã build sẵn, không build lại (nhanh nhất, không rủi ro build mới khác biệt).
  2. **CLI**: `git worktree add <path> 9ba8882 --detach` (hoặc commit ổn định khác) → `railway up --service <X> --environment production -c` — đúng cơ chế đã dùng để deploy tiến (§3), verify được reproducible trong chính build này.
  - `railway redeploy` (CLI) chỉ redeploy phiên bản MỚI NHẤT hiện tại, không nhận deployment ID cụ thể — không dùng được để rollback trực tiếp qua CLI, phải dùng 1 trong 2 cách trên.
- **Legacy endpoint/config vẫn còn theo design**: `CHAT_RUNTIME=legacy` (BUILD-26) vẫn là con đường rollback khẩn cấp không cần sửa code — route `frontend/src/app/api/chat/route.ts` giữ nguyên nhánh `if (CHAT_RUNTIME === "legacy")` gọi thẳng `/api/v1/chat` cũ, không bị BUILD-37 đụng tới.
- **Rollback riêng cho thay đổi config của chính BUILD-37**: `AGENT_JUDGE_ENABLED` — rollback tức thời bằng `railway variables --set AGENT_JUDGE_ENABLED=false` (đã tự xác nhận: set biến này kích hoạt Railway tự restart container, không cần build lại, hiệu lực trong ~10-20s).
- **Không thực hiện rollback nào** — không có lỗi/regression nghiêm trọng nào phát sinh từ chính việc deploy BUILD-32→36 (1 bug thật tìm thấy ở §5/§12 là bug CÓ SẴN từ BUILD-36, không phải do deploy gây ra, và không ảnh hưởng runtime/safety — chỉ ảnh hưởng 1 field hiển thị debug trong Admin Dashboard).

---

## 16. Final architecture status

Đã cập nhật `ARCHITECTURE.md` — thêm section mới **"Agent V2 Observability & Evaluation Pipeline (cập nhật BUILD-37)"**, có sơ đồ mermaid đầy đủ luồng thật: Agent V2 (router/safety/schedule/tools/model/grounding) → Durable Observability (BUILD-32) → Evaluation V2 → Judge V2 (BUILD-33, async boundary rõ) → Safety Monitoring (BUILD-34, live-join) → Golden Evaluation (BUILD-35/36) → Admin Dashboard V2 (BUILD-36). Ghi rõ:
- **Source of truth**: metrics durable độc lập ring buffer; raw text phụ thuộc ring buffer (giới hạn có chủ đích).
- **Async Judge boundary**: tick riêng 30s, tách khỏi request/response cycle, đảm bảo bằng kiến trúc.
- **Ring-buffer raw-text limitation**: ghi rõ, kèm tham chiếu tới bug/fix PR #118 vừa tìm thấy.
- **Durable metadata flow**: sơ đồ đầy đủ từng bảng.
- **Production model/provider config thực tế**: `gpt-5.4-mini` (Main), `anxs/gemini-3.7-flash-high` qua Vilao (Judge) — ghi rõ bằng số liệu thật đã verify, không phải giả định.

Phần mô tả kiến trúc gốc (LangGraph Agent đơn giản, trước Agent V2) trong `ARCHITECTURE.md` **cố ý không viết lại** — nằm ngoài phạm vi BUILD-37 (chỉ release/verify BUILD-32→36), tránh mở rộng scope ngoài yêu cầu.

---

## 17. Known limitations (không giấu)

1. **PR #118 (fix `content_available` key mismatch) chưa merge/deploy** — Trace Explorer trên production hiện tại vẫn hiển thị sai `content_available: false` cho mọi trace kể cả trace vừa tạo còn trong buffer. Không ảnh hưởng metrics/an toàn — chỉ ảnh hưởng 1 UX field hiển thị nội dung raw text.
2. **Golden Evaluation chưa có run nào persisted trên production** — Dashboard hiển thị đúng trạng thái trống trung thực, chưa có dữ liệu thật để verify golden pass-rate/regression-gate UI với số liệu khác 0.
3. **Doctor/caregiver role chưa test trực tiếp bằng token thật trên production** (chỉ patient) — bù bằng bằng chứng test-suite thật (Postgres) từ BUILD-36 cho cả 3 role, cùng 1 dependency uniform.
4. **Không có browser automation** — verify frontend dừng ở build/route/API-contract level, không có browser-console-level proof.
5. **`empty_retrieval_rate`/HitRate/MRR/NDCG@10 vẫn NOT_APPLICABLE** — giới hạn đã biết từ BUILD-31/35/36, không thuộc scope BUILD-37 để giải quyết.
6. **Judge cost NOT_AVAILABLE** — model Gemini/Vilao chưa có trong `AGENT_MODEL_PRICING_JSON`; là trạng thái trung thực, không phải lỗi, nhưng nghĩa là "Token & Cost" tab sẽ không bao giờ hiện Judge cost thật cho tới khi ai đó thêm giá vào JSON đó (ngoài scope BUILD-37).

---

## 18. Release Gate

```text
BUILD-37: PASS

MERGED MAIN VERIFIED: PASS       (PR #116 merged, main pulled clean tại 7e64491)
RELEASE COMMIT VERIFIED: PASS    (7e6449176fb83a809258eda51e14fd5a7e239634, deploy từ worktree sạch)
DEPLOYMENT HEALTHY: PASS         (BE + FE health/log sạch, không crash loop)
MIGRATION HEAD: PASS             (0045, xác nhận độc lập trước/sau qua DB thật + deploy log)

AGENT V2 PRODUCTION ROUTING: PASS
NO SILENT LEGACY FALLBACK: PASS  (chatbot_version=agent-v2 xác nhận mọi request)

DURABLE TRACE: PASS
REAL SPANS: PASS
TOKEN/COST: PASS                 (0 thật cho no-model-call path, giá trị thật cho model-call path, NOT_AVAILABLE thật cho unknown pricing)
ERROR/TIMEOUT SEMANTICS: PASS    (TOOL_TIMEOUT/RETRIEVAL_TIMEOUT luôn-0 kèm note, không giả)

JUDGE WORKER: PASS               (scheduler tick 30s thật, xử lý JUDGE_PENDING->JUDGE_COMPLETED thật)
JUDGE SAMPLING: PASS             (5% + priority ưu tiên, xác nhận qua eligibility_reason thật)
JUDGE FAILURE ISOLATION: PASS    (đảm bảo bằng kiến trúc async, không phải chỉ try/except)
PRODUCTION JUDGE MODEL VERIFIED: PASS  (google/anxs-gemini-3.7-flash-high qua Vilao, đọc thật không giả định)

SAFETY MONITORING: PASS          (1 event thật, severity/reason_code/handoff đúng)
HANDOFF CORRELATION: PASS        (live DoctorReviewRequest join khớp)
JUDGE DOES NOT OVERRIDE SAFETY: PASS  (Judge chấm điểm run này nhưng không đổi safety/handoff state)

GOLDEN DASHBOARD: PASS           (empty state trung thực, has_run=false, không fabricate)
ADMIN DASHBOARD V2: PASS         (mọi endpoint đối chiếu DB khớp chính xác)
FILTERS EFFECTIVE: PASS          (date_from/error_code xác nhận backend thật đổi kết quả)
N/A SEMANTICS: PASS

TRACE DRILLDOWN: PASS            (1 bug fix cần thiết -- xem PR #118, chưa merge, ghi rõ ở Known Limitations)
SESSION DRILLDOWN: PASS
TICKET CORRELATION: PASS         (cơ chế xác nhận qua ticket_rate khớp DB; không tạo ticket mới để test round-trip)

ADMIN AUTHORIZATION: PASS        (admin 200, patient 403 thật qua HTTP; doctor/caregiver qua test-suite BUILD-36)
CROSS-PATIENT PROTECTION: PASS

ROLLBACK READY: PASS
ARCHITECTURE DOC UPDATED: PASS

PRODUCTION SMOKE: PASS
READY FOR NORMAL TRAFFIC: YES
```

**Ghi chú PASS có điều kiện**: TRACE DRILLDOWN được đánh PASS vì cơ chế correlation hoạt động đúng và đầy đủ (Judge/Safety/Evaluation/Ticket đều correlate chính xác) — riêng 1 sub-field (`content_available` cho raw text) có bug đã tìm, đã sửa, đã test, đang chờ review ở PR #118 riêng (không bundle vào BUILD-37 để giữ đúng kỷ luật "release đã audit xong", theo đúng quy trình PR+review+merge của dự án).

---

## 19. Branch / PR / Next steps

- **BUILD-37 branch**: `build-37-production-release-validation` (chứa report này + cập nhật `ARCHITECTURE.md`) — sẽ mở PR riêng, không merge/deploy thêm gì (đã deploy xong ở §3, deploy đó KHÔNG cần PR vì không có code thay đổi, chỉ deploy commit đã merge sẵn `7e64491`).
- **PR #118** (`fix/build-37-trace-detail-content-available-key`): fix bug thật tìm thấy trong lúc verify — **CHƯA merge, CHƯA deploy**, chờ review riêng theo đúng quy trình.
- Không bắt đầu BUILD-38 cho tới khi PR #118 được review.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
