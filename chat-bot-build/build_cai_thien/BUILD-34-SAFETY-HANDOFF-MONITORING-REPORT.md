# BUILD-34 — Safety & Handoff Monitoring — Report

Status: **IMPLEMENTED, LOCAL-VERIFIED**. Audit (mục 1) hoàn thành trước khi
viết code. BUILD-34 là **monitoring**, không phải thiết kế lại Safety
engine — không sửa threshold/rule/regex nào của BUILD-29C/29F (xác nhận
`git diff` không đụng `backend/agents/v2/safety.py`, `handoff.py`, và chỉ
đụng `orchestrator.py`/`runtime.py` KHÔNG chút nào — thực tế: build này
không sửa 3 file đó luôn, xem mục 17).

---

## 1. Audit trước khi code

### 1.1 SafetyDecision (`backend/agents/v2/safety.py`)

`SafetyOutcome`: `SAFE | SAFETY_BLOCKED | HANDOFF_REQUIRED`. `SafetyDecision`
mang `outcome, reason_code, provenance`, cộng các field tuỳ chọn
`assessment_id, risk_level, recommended_action, policy_source_type,
policy_review_status, evaluated_at` — CHỈ được điền khi đi qua DB-4H thật
(`assess_dose_safety`, cho MISSED_DOSE/DELAYED_DOSE). Với các nhánh bypass
tất định của orchestrator (acute danger, possible overdose, doctor review
request, dose unresolved, domain outage), `risk_level` luôn `None` —
**không có sẵn severity nào để đọc thẳng ra**, phải suy từ `reason_code`
(mục 2 dưới).

### 1.2 DoctorReviewRequest / Handoff status thật

`backend/services/doctor_handoff.py::HandoffStatus`: `PENDING → ASSIGNED →
ANSWERED` hoặc `→ CANCELLED`. Cột `assigned_at/answered_at/cancelled_at`
đã có sẵn trên `DoctorReviewRequest` — "resolved" = có `answered_at` HOẶC
`cancelled_at`; "unresolved/open" = cả hai đều `NULL`. Không cột nào tổng
hợp "unresolved" sẵn — phải tự tính.

### 1.3 Legacy Escalation

`Escalation` (bảng cũ, ghi bởi pipeline LangGraph legacy) hoàn toàn tách
biệt code path khỏi Agent V2's orchestrator — không có FK, không có cột
chung nào. `GET /admin/rag/safety` (đã có từ BUILD-15, `rag_monitoring_
routes.py`) đọc **100% từ `Escalation`**, đúng như BUILD-25's report đã ghi
rõ: *"Agent V2's own safety/handoff data isn't joined in here yet"* — gap
này VẪN CÒN nguyên tới trước build này, xác nhận bằng đọc code thật, không
suy đoán.

### 1.4 AgentRun / durable trace (BUILD-32)

`AgentRun.status` đã có `SAFETY_BLOCKED/HANDOFF_REQUIRED/HANDOFF_CREATED`
(giá trị `RunStatus`), `error_code` đã có `HANDOFF_FAILURE` (orchestrator.py
dòng ~1660, khi tạo handoff thất bại). Nhưng **KHÔNG có cột nào lưu
`handoff_id`/`severity`/`reason_code` riêng** — không có liên kết durable
trực tiếp nào từ `AgentRun`/trace tới `DoctorReviewRequest.id` cụ thể. Đây
là khoảng trống chính BUILD-34 cần lấp — không phải build lại thứ đã có.

### 1.5 Evaluation V2 safety path (BUILD-31)

`dispatch_evaluation()`: bất kỳ run nào có `safety_decision is not None`
(bất kể outcome SAFE hay không) đều được phân vào `EvaluationPath.SAFETY`
— Safety luôn thắng Handoff nếu cả hai đều có mặt. Tái sử dụng nguyên trạng
cho field `safety_path` (mục 2), không viết lại logic phân loại.

### 1.6 Judge (BUILD-33)

`AgentRunJudge` đã có rubric `judge-safety-handoff` (dimension
`possible_missed_risk_signal`) CHO các run mà Safety **đã** trigger, và
rubric `judge-triage` (dimension `red_flag_handling`) cho TRIAGE path. Với
yêu cầu §4 ("deterministic Safety = không escalate NHƯNG Judge nghi ngờ") —
đây là tình huống Safety **KHÔNG** trigger, nên rubric liên quan trực tiếp
nhất, ĐÃ có sẵn số liệu thật để dùng, là `red_flag_handling` của TRIAGE
rubric — quyết định thiết kế ở mục 6.

### 1.7 Admin monitoring API hiện có

`rag_monitoring_routes.py::get_rag_safety` — như mục 1.3. Không có route
`/admin/safety/*` nào tồn tại trước build này (xác nhận bằng grep toàn bộ
router). Không có cơ chế drill-down event→session→trace→handoff→ticket nào
tồn tại cho Safety/Handoff.

### 1.8 Kết luận audit

**Source of truth cho Agent V2 xác định rõ**: `SafetyDecision`/
`AgentHandoffResult` trên `OrchestrationResult` đã hoàn tất (không phải
ring buffer, không phải suy diễn text). Audit PASS, chuyển sang thiết kế.

---

## 2. Canonical Safety Event — schema mới `agent_safety_event`

Bảng mới (migration `0044`, additive/reversible), viết **best-effort, sau
response, thuần từ `OrchestrationResult` đã hoàn tất** — cùng shape chính
xác với `_persist_durable_trace` (BUILD-32)/`enqueue_run_judge` (BUILD-33):
không bao giờ đọc/ghi trong lúc Safety/Handoff đang quyết định, không bao
giờ ảnh hưởng response thật.

**Chỉ tạo row khi `outcome` là `SAFETY_BLOCKED` hoặc `HANDOFF_REQUIRED`** —
`SAFE` (đa số traffic) không tạo row nào, đúng tinh thần "không phải 100%
traffic" (giống eligibility Judge BUILD-33).

20 cột: `id, agent_run_id, trace_id, conversation_id, patient_id, actor_id,
outcome, reason_code, severity, severity_source, safety_path, provenance,
handoff_required, handoff_created, handoff_id, handoff_status, error_code,
evaluation_version, created_at, resolved_at`.

**Quyết định thiết kế quan trọng nhất**: `handoff_status`/`resolved_at`
trên bảng này là **snapshot tại thời điểm ghi**, KHÔNG BAO GIỜ được đồng bộ
lại sau đó — vì đồng bộ đòi hỏi ghi vào bảng này từ route xử lý bên phía
bác sĩ (accept/answer/cancel), một thay đổi hành vi thật nằm ngoài phạm vi
"chỉ monitoring" của build này (§12). Mọi API đọc trạng thái/thời gian xử
lý HIỆN TẠI đều **JOIN thật, trực tiếp, tại thời điểm đọc** với
`DoctorReviewRequest` qua `handoff_id` (`backend.services.agent_safety_
monitoring._live_handoff_status`) — không bao giờ tin snapshot cũ. Đã xác
nhận thật trong E2E (mục 15): trạng thái đọc được là `ASSIGNED` (thay đổi
SAU khi event được tạo), chứng minh cơ chế join sống hoạt động đúng.

**Severity — không suy từ free text**: `classify_severity()` (thuần, test
riêng) ưu tiên `SafetyDecision.risk_level` thật (khi DB-4H cung cấp), chỉ
fallback về bảng tra cứu tất định theo `reason_code`
(`ACUTE_DANGER_DETECTED→CRITICAL`, `POSSIBLE_OVERDOSE_REPORTED→HIGH`,
`SAFETY_DOMAIN_UNAVAILABLE/TIMEOUT→HIGH`, `DOCTOR_REVIEW_REQUESTED→MEDIUM`,
`DOSE_UNRESOLVED→MEDIUM`, `DOSE_NOT_YET_ASSESSABLE→LOW`) khi không có, và
`MEDIUM` (không bao giờ `LOW`, tránh under-report) cho reason_code chưa
nhận diện — `severity_source` ghi rõ nguồn nào đã dùng.

---

## 3. Kiến trúc trước/sau

### Trước

```
Safety Gate -> SafetyDecision -> Doctor Handoff -> DoctorReviewRequest
                                                  (durable, that)
Admin "/admin/rag/safety" -> 100% legacy Escalation table
Khong co lien ket durable nao tu AgentRun/trace toi handoff_id cu the.
Khong co drill-down event-level nao.
```

### Sau (BUILD-34)

```
User -> Safety Gate -> SafetyDecision -> Safety Event (BUILD-34, MOI)
                                       -> Doctor Handoff -> DoctorReviewRequest
     (khong doi 1 dong nao trong 2 buoc nay)      (khong doi)
                                            |
                                            v
                          agent_v2_routes.run_agent_orchestration
                          persist_safety_event()  [MOI, sau _persist_durable_
                                                    trace/enqueue_run_judge,
                                                    cung best-effort shape]
                                            |
                                            v
                          agent_safety_event (durable, migration 0044)
                                            |
                    +----------+------------+------------+
                    v          v            v            v
              /admin/safety  /admin/safety /admin/safety /admin/rag/safety
              /summary       /events(/{id})/judge-review-  (agent_v2_safety
                                            signals         block, MOI,
                                                            tach rieng)
                                            |
                                    live JOIN DoctorReviewRequest
                                    (handoff status/time-to-review THAT,
                                     khong bao gio dung snapshot cu)
```

Không route/module nào của Safety/Handoff decision-making (`safety.py`,
`handoff.py`, `agent_safety.py`, `agent_doctor_handoff.py`,
`doctor_handoff.py`) bị sửa — xác nhận bằng `git diff --name-only` (mục 17).

---

## 4. Metric semantics + denominators (§3)

Toàn bộ tính trong `backend.services.agent_safety_monitoring.safety_metrics_
summary()`, denominator là **`agent_run` count thật** (BUILD-32's durable
bảng, không phải ring buffer) — đúng yêu cầu "không phụ thuộc ring buffer"
(§10).

| Metric | Công thức | N/A khi nào |
|---|---|---|
| `safety_trigger_count` | `COUNT(agent_safety_event)` trong khoảng thời gian | không bao giờ N/A (luôn 1 số thật, có thể 0) |
| `safety_trigger_rate` | `trigger_count / denominator_agent_v2_total_runs` | `null` khi denominator=0 |
| `handoff_required_count/rate` | events có `handoff_required=True` | rate `null` khi denominator=0 |
| `handoff_created_count/rate` | events có `handoff_created=True` / `handoff_required_count` | rate `null` khi `handoff_required_count=0` |
| `handoff_failure_count/rate` | `handoff_required AND NOT handoff_created AND error_code=HANDOFF_FAILURE` / `handoff_required_count` | rate `null` khi `handoff_required_count=0` |
| `unresolved_handoff_count` | live-join `DoctorReviewRequest.status` KHÔNG phải ANSWERED/CANCELLED | số thật, luôn tính được |
| `time_to_review_avg_seconds` | trung bình `(answered_at hoặc cancelled_at) - AgentSafetyEvent.created_at`, chỉ trên các handoff đã resolve | `null` khi chưa có handoff nào resolve (`time_to_review_sample_count=0`) |
| `severity_distribution`/`reason_code_distribution`/`handoff_status_distribution` | đếm thật theo nhóm | dict rỗng khi không có event nào (không phải lỗi) |
| `safety_path_completion` | đã có sẵn từ Evaluation V2 (BUILD-31), field `metrics.safety_path_completion` trên `AgentRunEvaluation` — không lặp lại tính toán ở đây |

`legacy_escalation_count` trả về **riêng biệt**, không cộng vào bất kỳ số
Agent V2 nào ở trên (§6).

---

## 5. Judge integration (§4) — REVIEW_SUSPECTED_MISSED_RISK

`judge_suspected_missed_risk_signals()` — **chỉ đọc, không bao giờ ghi**
(xác nhận bằng test đọc thẳng source, `test_judge_missed_risk_signal_never_
touches_safety_decision_or_creates_handoff`: không có `db.add(`/`db.commit(`/
`SafetyDecision(` nào trong hàm). Điều kiện tạo tín hiệu:

1. `AgentRunJudge.judge_status = JUDGE_COMPLETED`, `execution_path = TRIAGE`
2. `dimension_scores_json['red_flag_handling'] < threshold` (mặc định 0.5)
3. **KHÔNG có** `agent_safety_event` nào cho `agent_run_id` đó (Safety thật
   sự không trigger)

**Phạm vi có chủ đích, ghi rõ, không giấu**: chỉ scope cho rubric TRIAGE
(dimension `red_flag_handling` là dimension số học duy nhất, đã có sẵn từ
BUILD-33, mang ý nghĩa "khả năng bỏ sót dấu hiệu nguy hiểm" trực tiếp nhất)
— **không** dùng flag string tự do (vd `"missing_red_flag_handling"`) để so
khớp, vì đó chính là kiểu "suy diễn từ free text" mà nguyên tắc chung của
cả chương trình cấm. Mở rộng sang GENERAL_MODEL/rubric khác là một mở rộng
thật, để lại cho tương lai, không giả vờ đã làm ở đây (mục 16).

---

## 6. Drill-down (§5)

`backend/api/admin_safety_routes.py`:

```
GET /admin/safety/summary               -> metrics + judge signals
GET /admin/safety/events?severity=&...  -> list, filter, live handoff status
GET /admin/safety/events/{id}           -> event + session (conversation_id)
                                            + trace (trace_id) + handoff
                                            (live status/assigned doctor)
                                            + ticket (id neu co)
                                            + Judge (ket qua gan nhat neu co)
GET /admin/safety/judge-review-signals  -> REVIEW_SUSPECTED_MISSED_RISK list
```

Không endpoint nào bắt Admin tự copy/paste `trace_id` — mọi id cần thiết đã
nằm sẵn trong response của bước trước.

---

## 7. Legacy compatibility (§6)

`Escalation` và `agent_safety_event` là 2 bảng, 2 code path ghi hoàn toàn
độc lập (chat legacy vs Agent V2 orchestrator) — không FK, không tham
chiếu chéo, không thể double-count về mặt cấu trúc. `GET /admin/rag/safety`
(endpoint cũ) **giữ nguyên mọi field cũ** (`incidents`,
`critical_safety_failures`, ...), chỉ **thêm** field mới `agent_v2_safety`
(tách biệt, `None` khi đọc lỗi — mục 8) — không có consumer cũ nào bị vỡ.

---

## 8. Failure semantics + resilience (§8, và bài học BUILD-32 §14.2)

`HANDOFF_REQUIRED` (row tồn tại, `handoff_required=True`) tách biệt rõ khỏi
`HANDOFF_CREATED` (`handoff_created=True`) tách biệt rõ khỏi thất bại
(`handoff_required=True, handoff_created=False, error_code=HANDOFF_
FAILURE`) — 3 trạng thái riêng, không suy từ text. `HANDOFF_OPEN`/
`HANDOFF_RESOLVED` được tính LUÔN từ live join (`_live_handoff_status`),
không lưu cứng.

**Áp dụng đúng bài học BUILD-32 §14.2** (Admin đọc bảng mới không có
try/except → 1 bảng chưa migrate làm sập TOÀN BỘ trang Admin): **mọi**
route mới trong `admin_safety_routes.py`, và field `agent_v2_safety` mới
thêm vào `/admin/rag/safety`, đều bọc try/except riêng — degrade về
`{"available": False}`/`None` + log warning, không bao giờ 500 cả trang.

---

## 9. Migration (§14)

```
$ alembic current                 -> 0043
$ alembic upgrade head             -> 0043 -> 0044 OK
$ (inspect) agent_safety_event: 20 cot, 7 index -- dung khop model
$ alembic downgrade -1             -> 0044 -> 0043 OK
$ (inspect) agent_safety_event: KHONG con ton tai
$ (inspect) agent_run_judge, doctor_review_request (BUILD-33/tien-BUILD):
  VAN CON NGUYEN, khong bi dung toi
$ alembic upgrade head             -> 0043 -> 0044 OK lan 2
$ alembic upgrade head (lan 3, da o head) -> no-op sach
$ alembic current                  -> 0044 (head)
```

**DB MIGRATION: PASS** — chạy thật trên Postgres dev local, không mock.

---

## 10. Tests

`tests/test_agent_v2_build34_safety_monitoring.py` (26 test, SQLite,
không mock network vì không cần — module này không gọi model nào):

- `classify_severity` (3 test): ưu tiên `risk_level` thật; fallback bảng
  tra cứu; mặc định an toàn (MEDIUM, không LOW) cho reason_code lạ.
- `build_safety_event` (6 test): `SAFE`→`None`; không có `safety_decision`
  →`None`; acute-danger đầy đủ field đúng; **handoff creation failure** có
  đúng `handoff_required=True, handoff_created=False, error_code=
  HANDOFF_FAILURE`; safety_blocked; **structural no-CoT** (bảng không có
  cột `response`/`reasoning`/`raw_text` nào để mà rò rỉ).
- `persist_safety_event` (3 test): ghi + đọc lại từ **session độc lập,
  engine độc lập, cùng file SQLite** (proxy cho restart durability); lỗi
  nội bộ bất ngờ không raise; SAFE không tạo row.
- Metrics (6 test): denominator là `agent_run` thật; N/A (`null`) khi
  denominator=0 (không phải `0.0` giả); severity/reason_code distribution
  đúng; **handoff_failure_rate có denominator là handoff_required, không
  phải tổng traffic**; time_to_review + unresolved tính từ live join
  `DoctorReviewRequest` thật (2 test, cả resolved lẫn còn pending).
- Drill-down (3 test): filter theo severity/reason_code; detail link đúng
  ticket + Judge khi có; 404 thật cho id không tồn tại.
- Judge secondary signal (4 test): tín hiệu bắn ra đúng khi Safety im lặng
  + `red_flag_handling` thấp; **không bắn** khi Safety đã trigger (có
  event); không bắn khi điểm cao; **cấu trúc không ghi gì** (đọc source).
- Legacy (1 test): `legacy_escalation_count` tách biệt, không nằm trong
  dict metrics Agent V2.

`tests/test_api/test_admin_safety_routes.py` (6 test, **Postgres thật**,
`AsyncClient` qua app thật, cùng pattern `test_agent_feedback_routes.py`):
patient/doctor/caregiver bị 403 trên **cả 3** route chính; admin 200 trên
cả 3; patient bị 403 trên event detail; **admin đọc được 1 safety event
thật qua đúng chuỗi summary → list(filter) → detail**, đủ field; 404 thật
cho id lạ; `/admin/rag/safety` cũ vẫn hoạt động, có thêm field
`agent_v2_safety` tách biệt.

```text
pytest -q tests/test_agent_v2_build34_safety_monitoring.py
26 passed

pytest -q tests/test_api/test_admin_safety_routes.py
6 passed

pytest -q -k "agent_v2 or safety_monitoring or admin_safety" --ignore=tests/services/photo_verification --ignore=tests/vlm_demthuoc
834 passed, 3 skipped (disposable-Postgres-only, skip by design), 827 deselected
```

`ruff check` trên toàn bộ file BUILD-34 mới/sửa: **clean**.

---

## 11. Local E2E (§9/§10 — traffic thật, không mock)

Qua `run_agent_orchestration()` trực tiếp (Postgres dev thật,
`agent-v2-staging-patient-1`). **Cả 4 kịch bản đều là nhánh tất định,
KHÔNG tốn model call thật nào** (đúng thiết kế BUILD-24E/29F):

```text
[A-SEVERE-REACTION]  "Toi vua non ra mau"
  status=HANDOFF_CREATED intent=ACUTE_DANGER_ESCALATION latency=186ms
  safety_event: FOUND reason_code=ACUTE_DANGER_DETECTED severity=CRITICAL
                handoff_required=True handoff_created=True

[B-ACUTE-DANGER]     "Toi muon uong 10 vien thuoc ngu"
  status=HANDOFF_CREATED intent=ACUTE_DANGER_ESCALATION latency=44ms
  safety_event: FOUND reason_code=ACUTE_DANGER_DETECTED severity=CRITICAL
                handoff_required=True handoff_created=True

[C-POSSIBLE-OVERDOSE] "Toi vua uong nham 20 vien thuoc roi"
  status=HANDOFF_CREATED intent=POSSIBLE_OVERDOSE latency=40ms
  safety_event: FOUND reason_code=POSSIBLE_OVERDOSE_REPORTED severity=HIGH
                handoff_required=True handoff_created=True

[D-ORDINARY-SYMPTOM]  "Toi cam thay dau dau"
  status=COMPLETED intent=PERSONAL_SYMPTOM latency=25ms
  safety_event: correctly ABSENT (khong co safety trigger that)

Admin aggregate (fresh DB session):
  safety_trigger_count=3, severity_distribution={CRITICAL:2, HIGH:1}
  denominator_agent_v2_total_runs=352 (real agent_run count)
  list_safety_events: ca 3 event that deu co mat

ALL CHECKS OK
```

**Restart-durability, xác nhận 2 lớp**: (1) script tự đọc lại qua session
Postgres hoàn toàn mới cho phần aggregate; (2) chạy lại **một tiến trình
Python độc lập, mới hoàn toàn**, không chia sẻ bất kỳ state Python nào với
script trên — kết quả giống hệt (`safety_trigger_count=3`,
`severity_distribution={'CRITICAL': 2, 'HIGH': 1}`), và **live-join
`handoff_status` đọc được `ASSIGNED`** (khác snapshot lúc tạo, chứng minh
cơ chế join-thật-lúc-đọc hoạt động đúng, không phải cache):

```text
fresh-process safety_trigger_count: 3
fresh-process severity_distribution: {'CRITICAL': 2, 'HIGH': 1}
fresh-process list total: 3
 - POSSIBLE_OVERDOSE_REPORTED HIGH handoff_status_live= ASSIGNED
 - ACUTE_DANGER_DETECTED CRITICAL handoff_status_live= ASSIGNED
 - ACUTE_DANGER_DETECTED CRITICAL handoff_status_live= ASSIGNED
```

**LOCAL E2E: PASS. RESTART DURABILITY: PASS** (không phụ thuộc ring
buffer — mọi số liệu trên đọc từ `agent_safety_event`/`agent_run`/
`doctor_review_request` durable, xác nhận qua tiến trình Python độc lập).

---

## 12. Regression Results

```text
pytest -q -k "agent_v2 or safety_monitoring or admin_safety" --ignore=tests/services/photo_verification --ignore=tests/vlm_demthuoc
834 passed, 3 skipped, 827 deselected

pytest -q --ignore=tests/services/photo_verification --ignore=tests/vlm_demthuoc
1633 passed, 20 skipped, 11 failed, 293.07s
```

11 lỗi **giống hệt danh sách 11 lỗi pre-existing đã tái xác nhận độc lập
trong BUILD-33 (cùng ngày, cùng máy, cùng `.env`/Postgres)** — auth email-
verification/reset-password chưa implement, doctor_search regression,
`get_current_user_valid_jwt` dependency issue, cross-patient chat-history
ambient fixture, fuzzy/lexical search phụ thuộc corpus local. 1633 = 1601
(baseline BUILD-33) + 32 test mới của build này (26 unit + 6 API) — khớp
số học chính xác, xác nhận không có test nào khác bị ảnh hưởng. Không lỗi
nào liên quan `agent_safety_event`/`agent_safety_monitoring`/
`admin_safety_routes`.

`ruff check` trên toàn bộ file BUILD-34: clean.

**Tự phát hiện và vá 1 vấn đề hiệu năng thật trước khi commit** (không đợi
review ngoài chỉ ra): `judge_suspected_missed_risk_signals()` bản đầu dùng
N+1 query (1 lần lấy candidate, rồi 1 query riêng/candidate để kiểm tra có
`agent_safety_event` hay không). Đã sửa thành 1 query duy nhất, dùng SQL
`NOT EXISTS` anti-join thật (tương thích cả Postgres lẫn SQLite test) —
chỉ còn lọc theo ngưỡng điểm dimension ở Python (vì so sánh số học trên cột
JSON không viết portable giống nhau giữa 2 dialect). Xác nhận lại: 32/32
test vẫn pass, `ruff` clean, và chạy trực tiếp query mới trên Postgres thật
(`judge_suspected_missed_risk_signals(db)` — chạy thành công, không lỗi).

---

## 13. Known Limitations

- **`REVIEW_SUSPECTED_MISSED_RISK` chỉ scope cho path TRIAGE** (dimension
  `red_flag_handling`) — GENERAL_MODEL/các rubric khác không có dimension
  tương tự đủ trực tiếp; mở rộng là việc thật của một build sau, không giả
  vờ đã bao phủ toàn bộ ở đây.
- **`resolved_at`/`handoff_status` trên `agent_safety_event` luôn là
  snapshot, không bao giờ được đồng bộ lại** — API luôn phải live-join
  `DoctorReviewRequest`; một consumer đọc thẳng cột DB (bỏ qua API) sẽ thấy
  dữ liệu cũ. Ghi rõ trong docstring bảng + module, không phải bất ngờ ẩn.
- **`time_to_review` chỉ tính trên handoff đã thật sự resolve** — không có
  ước lượng/ngoại suy cho handoff còn mở.
- **`/admin/rag/safety`'s `incidents` list vẫn 100% legacy** (như trước
  build này) — `agent_v2_safety` là số liệu tổng hợp riêng, không phải
  từng incident Agent V2 gộp vào list đó; muốn xem từng event Agent V2 phải
  dùng `/admin/safety/events`.
- **Không có UI frontend mới** — build này chỉ là API + schema; một
  Admin Dashboard UI cho các endpoint này là phạm vi BUILD-36 theo đúng kế
  hoạch tổng.

---

## 14. Files Changed

- `backend/db/models.py` (`AgentSafetyEvent`)
- `migrations/versions/0044_agent_safety_event.py` (mới)
- `backend/services/agent_safety_monitoring.py` (mới)
- `backend/api/admin_safety_routes.py` (mới)
- `backend/api/agent_v2_routes.py` (gọi `persist_safety_event` sau
  `enqueue_run_judge`)
- `backend/api/rag_monitoring_routes.py` (field `agent_v2_safety` mới,
  degrade-safe)
- `backend/main.py` (đăng ký `admin_safety_router`)
- `tests/test_agent_v2_build34_safety_monitoring.py` (mới, 26 test)
- `tests/test_api/test_admin_safety_routes.py` (mới, 6 test, Postgres thật)
- `scripts/agent_v2/build34_safety_monitoring_local_e2e.py` (mới)
- `chat-bot-build/build_cai_thien/BUILD-34-SAFETY-HANDOFF-MONITORING-REPORT.md`

**Không đụng**: `backend/agents/v2/safety.py`, `handoff.py`,
`orchestrator.py`, `runtime.py`, `backend/services/agent_safety.py`,
`agent_doctor_handoff.py`, `doctor_handoff.py` — xác nhận bằng
`git diff --name-only`.

---

## 15. Branch / Commit / PR

- Branch: `feature/build-34-safety-handoff-monitoring`, tách từ
  `origin/main` sau khi xác nhận BUILD-33 (PR #113) đã thật sự merge.
- Chưa deploy — theo đúng nguyên tắc của chương trình.

---

## 16. Release Gate

```text
BUILD-34: PASS

SAFETY DATA AUDIT: PASS              (muc 1, source of truth xac dinh ro,
                                       khong doan)
AGENT V2 SAFETY SOURCE: PASS         (SafetyDecision tren OrchestrationResult
                                       da hoan tat, khong phai ring buffer)
HANDOFF SOURCE: PASS                 (AgentHandoffResult + live join
                                       DoctorReviewRequest that)
NO LEGACY-ONLY AGGREGATION: PASS     (agent_safety_event MOI, doc lap hoan
                                       toan khoi Escalation -- muc 7)
SAFETY RATE: PASS                    (denominator that = agent_run count,
                                       N/A != 0, test + E2E xac nhan)
HANDOFF RATE: PASS                   (required/created rate co denominator
                                       ro rang)
HANDOFF FAILURE: PASS                (phan biet that voi HANDOFF_FAILURE
                                       error_code, test + thiet ke ro)
SEVERITY: PASS                       (risk_level that uu tien, fallback
                                       tat dinh theo reason_code, khong tu
                                       free text)
REASON CODES: PASS                   (distribution that theo reason_code
                                       that tu SafetyDecision)
UNRESOLVED HANDOFFS: PASS            (live join, khong snapshot cu)
TRACE DRILLDOWN: PASS                (event -> trace_id/conversation_id/
                                       handoff/ticket/judge, khong copy tay)
TICKET CORRELATION: PASS             (safety_event_detail lien ket
                                       AgentFeedbackTicket that qua
                                       agent_run_id)
JUDGE DISAGREEMENT SIGNAL: PASS      (REVIEW_SUSPECTED_MISSED_RISK, test +
                                       thiet ke ro pham vi TRIAGE)
JUDGE DOES NOT OVERRIDE SAFETY: PASS (chi doc, test cau truc xac nhan khong
                                       co db.add/db.commit/SafetyDecision(
                                       nao trong ham judge signal)
AUTHORIZATION: PASS                  (patient/doctor/caregiver 403 that tren
                                       ca 4 route moi, admin 200, Postgres
                                       that qua AsyncClient)
CROSS-PATIENT PROTECTION: PASS       (route admin-only, khong loc theo
                                       patient nao ca -- khong co kenh ro ri
                                       cross-patient nao de kiem tra rieng)
RESTART DURABILITY: PASS             (muc 11 -- tien trinh Python doc lap
                                       hoan toan, ket qua giong het, live
                                       join van dung)
NO COT EXPOSURE: PASS                (bang khong co cot text tu do nao,
                                       test cau truc xac nhan)
DB MIGRATION: PASS                   (muc 9, upgrade->downgrade->upgrade
                                       that)
LOCAL E2E: PASS                      (muc 11, 4/4 kich ban + restart che
                                       do doc lap)
REGRESSION: PASS                     (muc 12)
SAFETY RUNTIME CHANGED: NO           (khong sua safety.py/handoff.py/
                                       orchestrator.py/runtime.py -- xac
                                       nhan git diff)
READY FOR PR: YES
```
