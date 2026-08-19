# APP-1 — Runtime Audit

**Ngày audit:** 2026-08-17
**Phạm vi:** đọc mã nguồn local tại `feature/database-architecture-v2`, `application_integration_v2_plan.md`, và DB closeout. Không có runtime/code, migration, cấu hình, artifact hoặc dữ liệu nào bị sửa.

## Kết quả điều hành

Audit tĩnh hoàn tất. Runtime hiện tại vẫn lấy các bảng/DTO legacy làm contract đọc và phần lớn write-path. Riêng Doctor Prescription Flow đã có **V2 sidecar write**: sau khi tạo/sửa `Prescription` legacy, service đồng bộ deterministic sang V2; khi duyệt, chỉ plan/rule V2 đầy đủ mới được `ACTIVE`. API và frontend chưa đọc V2 schedule/occurrence/state/safety.

Hai P0 ngăn xác minh runtime end-to-end trên máy này:

1. Import `backend.main` thất bại do route xóa caregiver trả HTTP 204 nhưng FastAPI đánh giá endpoint có response body (`backend/api/caregiver_routes.py:220`). `pytest --collect-only -q` dừng ở assertion này; backend hiện không thể khởi động/được test qua TestClient.
2. Docker Desktop daemon không hoạt động (`docker ps` không kết nối được named pipe), vì vậy không thể xác nhận revision/schema của PostgreSQL local hay chạy flow thật. Codebase công bố Alembic head `0027`, nhưng không được suy diễn rằng local DB đang ở revision đó.

Theo fail-closed của Application Integration V2, đây là **PASS WITH P0 BLOCKERS** cho audit (phát hiện đã được ghi nhận), nhưng chưa đủ điều kiện bắt đầu integration design có thể thực thi/kiểm chứng.

## APP-1.1 — Local Runtime Unblock (2026-08-17)

Hai P0 của APP-1 đã được xử lý và xác minh trên môi trường local disposable:

- `DELETE /api/v1/caregiver-links/{link_id}` giữ nguyên authorization và xóa record, nhưng khai báo rõ `response_model=None` và `response_class=Response` cho HTTP `204 No Content`. Điều này loại bỏ response body theo đúng semantics 204. Regression test xác nhận `204` có body rỗng.
- Thiếu `python-multipart` là environment drift: dependency đã có trong `requirements.txt` nhưng chưa được cài trong Python local. Đã cài đúng dependency khai báo, không đổi dependency manifest.
- Backend import PASS (`48` routes). Lifespan startup PASS với `GET /health` = `200`; V2 catalog warmup hoàn tất và legacy escalation scheduler khởi động/rút lui bình thường trong TestClient lifecycle.
- PostgreSQL dùng container tạm `p067-app11-db` ở `localhost:5433`, volume mới `p067-app11_pgdata`; không dùng container/volume legacy tại `localhost:5432`.
- Sau validation, container và volume tạm này đã được xóa. Không còn test state để lần chạy sau vô tình tái sử dụng.
- `alembic upgrade head` từ database trống đạt revision `0027`.
- Identity import lượt một tạo `3,556` products, `3,556` maps, `1,406` ingredients, `5,287` valid product-ingredient links. Lượt hai tạo `0` row. Source hashes trước/sau trùng nhau. Safety seed tạo `49` policies rồi lượt hai tạo `0` (existing `49`).
- PostgreSQL validation: `3,556` active maps, duplicate active `legacy_drug_id` = `0`, orphan product-ingredient = `0`.
- API test collection (`tests/test_api` + caregiver routes) PASS. Basic API smoke PASS `3`; focused Database Architecture V2 regression PASS `73`.

Toàn bộ root pytest collection hiện còn 4 errors thuộc VLM test subtree do local Python thiếu optional `numpy`/`cv2`; hai package này không nằm trong `requirements.txt`. Đây không còn là P0 cho FastAPI/API runtime hoặc APP-1.1 scope; không cài/đổi dependency VLM ngoài phạm vi task. Một API/auth legacy subset cũng có expectation cũ (401 vs 403, email verification/reset routes) và không liên quan đến fix 204; không dùng subset này làm bằng chứng smoke.

## Evidence và giới hạn

- `alembic heads` từ repo trả `0027 (head)`; closeout DB ghi V2 additive hoàn tất qua `0023`–`0027` và clean-DB gate đã PASS trong phase Database Architecture.
- `backend/config.py` đặt `DRUG_KNOWLEDGE_BACKEND` mặc định là `v2`, có rollback `v1` và chế độ `shadow` trả V1 đồng thời log so sánh V2.
- Lần audit này không truy cập dữ liệu bệnh nhân, không dùng Docker volume cũ và không gửi request lên Railway.
- Các nhận định về local PostgreSQL là static/source audit cho đến khi Docker hoạt động và một database clean được dựng từ repo.

## CURRENT RUNTIME MAP

| Flow | Frontend → API | Service/runtime hiện tại | Table / logic legacy | V2 tương ứng | Trạng thái integration và rollback risk |
| --- | --- | --- | --- | --- | --- |
| Drug search/select | `MedicineCombobox` → Next `/api/drugs` → `GET /api/v1/drugs` | `drug_knowledge.tim_thuoc` / `lay_thuoc` | V1 truy vấn legacy chỉ khi backend=`v1` hoặc so sánh `shadow`; UI truyền `drug_id`, tên, dạng, hàm lượng | File-backed Canonical V2 `v2_agent` resolves legacy slug sang `drug_product_id`; operational `drug_id_map` dùng khi write prescription | **V2_PRIMARY cho catalog search** theo config mặc định, nhưng public DTO vẫn legacy. `shadow` và `v1` là rollback. UI cho free-text nên product identity vẫn có thể unresolved. |
| Doctor create/approve prescription | `doctor/prescribe` → `lib/prescriptions` → Next proxy `/api/prescriptions` → `POST /api/v1/prescriptions`, sau đó `/approve` | `tao_phac_do`, `duyet_phac_do` | `Prescription.items` JSON, `Prescription.status`; approve sinh grouped legacy `DoseEvent` | `sync_prescription_schedule`, `activate_prescription_schedule` → `prescription_item`, `medication_plan`, `schedule_rule`, `schedule_rule_time`, optional `schedule_rule_cycle` | **Legacy read + V2 sidecar write hiện hữu**. Một transaction sở hữu cả legacy/V2 rows; V2 chỉ ACTIVE nếu identity, dates, times, doses/day, meal và timezone hợp lệ, còn lại `REVIEW_REQUIRED`. Frontend đọc legacy nên rollback V2 không đổi UI, nhưng DB thiếu migration `0027` sẽ làm create/sửa rollback. |
| Doctor edit/stop prescription | `doctor/patients` → `PUT /api/prescriptions/{id}`; stop endpoint chỉ backend hiện có | `sua_phac_do`, `dung_phac_do` | Overwrite `Prescription.items`; regenerate/cancel future `DoseEvent` legacy | `sync_prescription_schedule`/activate chỉ có ở create/edit; V2 occurrence không được create ở đây | Edit có V2 sidecar sync. Stop chỉ cancel legacy `DoseEvent`; chưa có đồng bộ cancel V2 occurrence, nên **không được chuyển read-path sang V2** trước khi có thiết kế reconciliation. |
| Patient/family dose list và update | `patient`, family pages, `proto-store` → `/api/doses` / `PATCH /api/doses/{id}` | `dose_routes.update_dose_status` ghi status và commit trực tiếp | `DoseEvent` grouped nhiều thuốc trong `expected_items[]`; `PhotoVerification` thay đổi `DoseEvent` | `generate_dose_occurrences`; `transition_dose_occurrence`, `advance_dose_occurrences`; `dose_event_log`, `notification_job` | **LEGACY only runtime.** Direct PATCH bỏ qua V2 transition validation, row lock, immutable log, outbox và safety. Không có V2 API/read adapter, do đó chưa có SHADOW an toàn cho patient UI. |
| Dose schedule/generation | Không có frontend/API V2 caller | Legacy `sinh_dose_event` được gọi khi approve/edit | `DoseEvent` theo giờ, nhưng group items cùng thời điểm | `generate_dose_occurrences(window_start, window_end)` tạo một product/một thời điểm, UTC + local fields + deterministic key | V2 generator có explicit finite window và không tự commit, nhưng không được scheduler/API gọi. Scheduler hiện khởi động chỉ cho legacy escalation reminder; không được dùng lại làm V2 scheduler mà chưa qua design. |
| Reminder/dose state | UI gọi legacy PATCH hoặc photo flow | `dose_state.transition_dose_occurrence` và `advance_dose_occurrences` có sẵn nhưng không expose | Legacy statuses `PENDING/TAKEN/DELAYED/MISSED/CANCELLED/AWAITING_CAREGIVER` | V2 `DoseOccurrence`, immutable `DoseEventLog`, idempotent `NotificationJob` | **V2 domain only, no runtime integration.** UI còn map nhóm status legacy, không có `SCHEDULED/DUE/SKIPPED` contract. |
| Safety/escalation | Doctor/patient/family alerts → `/api/escalations`; chat/photo có legacy escalation callback | `trigger_emergency_escalation`, APScheduler reminder; reporting và agent query legacy | `Escalation`, `DoseEvent`, chat/photo-specific logic | `assess_dose_safety`, `process_safety_escalation` → `missed_dose_assessment`, `safety_event`, V2 `notification_job` | **LEGACY only runtime.** V2 policy/escalation is fail-closed/idempotent but has no route, recipient resolution, provider delivery, or Agent integration. Legacy category-unreviewed rules must never become strong automatic advice/escalation. |

## Backend/API và direct DB writes

Các router HTTP đã đọc/ghi ORM trực tiếp thay vì qua V2 domain service gồm:

- `backend/api/dose_routes.py`: `GET /doses` truy vấn `DoseEvent`; `PATCH /doses/{id}` ghi raw `status` rồi `commit`. Đây là điểm ưu tiên phải thay bằng adapter/domain trong APP-4, không phải đổi payload ngay.
- `backend/api/photo_routes.py` và `services/photo_verification/verifier.py`: thao tác `PhotoVerification` và `DoseEvent` legacy; mismatch gọi legacy escalation.
- `backend/api/escalation_routes.py`, `reporting_routes.py`, `caregiver_routes.py`, chat/agent tools: đọc/ghi `Escalation`, `DoseEvent`, `CaregiverLink`, `DoctorWatch` legacy trực tiếp hoặc qua legacy service.
- `backend/services/prescription/service.py`: vẫn là owner của `Prescription` legacy và legacy occurrence generation, nhưng gọi V2 write-path trong cùng transaction. Đây là seam đã có cho APP-3, không phải một cutover hoàn chỉnh.

V2 domain services không có router hiện hữu: `scheduling/write_path.py`, `occurrence_generator.py`, `dose_state.py`, `safety_policy_domain/service.py` và `safety_policy_domain/escalation.py`. Chúng phải chỉ được gọi qua application service/adapter mới, không expose ORM tables trực tiếp cho frontend.

## LEGACY DEPENDENCIES

- `Prescription.items` JSON là public source của frontend response và traceability legacy; frontend flatten một prescription thành từng dòng thuốc.
- `DoseEvent` là grouped-dose contract cho patient/family, photo verification, adherence reporting, chat tools và legacy escalation scheduler.
- `Escalation` là nguồn dashboard/API/chat hiện tại; V2 `safety_event` chưa thay nó.
- Next server proxies dùng `X-Internal-Secret` cho nhiều read/write routes; dose status và escalation read dùng JWT theo đường khác. Authorization model V2 cần giữ boundary này cho tới khi có decision được duyệt.
- Frontend dùng `DEMO_DOCTOR_ID` cho create/approve và fallback update. Backend nhận `doctor_id` trong body. Đây là debt authorization không được che giấu bởi V2 integration.
- Doctor có thể nhập thuốc tự do. Không được tự map; V2 sidecar phải tiếp tục để item/plan/rule `REVIEW_REQUIRED` khi `drug_id_map` không active/không xác định.
- App lifespan đang khởi động APScheduler cho reminder/summarization của **legacy escalation**, không phải V2 occurrence/reminder delivery.

## V2 INTEGRATION POINTS

| Mode | Điểm dùng được | Quy tắc an toàn |
| --- | --- | --- |
| `LEGACY` | Dose list/status, photo, chat, reporting, escalation dashboard hiện tại | Giữ contract và hành vi hiện hữu; không ghi song song tự phát. |
| `SHADOW` | Drug catalog đã có `shadow`; Doctor Prescription có V2 sidecar deterministic để reconcile đối chiếu legacy item với V2 item/plan/rule | Không đổi API response/read source. Ghi V2 chỉ qua transaction hiện có; log/count reconciliation không chứa PII. |
| `V2_PRIMARY` khả thi sau thiết kế | Doctor prescription write adapter là điểm đầu tiên: cùng request contract legacy, V2 validation trước activation, compatibility response vẫn từ legacy adapter trong giai đoạn đầu | Chỉ sau DB clean `0027`, identity import, transaction/reconciliation tests và quyết định explicit về stop/edit semantics. Không dual-write độc lập. |
| Chưa khả thi | Dose/state, reminder/notification, safety/escalation | Cần V2 API/read models, identity/recipient authorization, finite generator worker và rollback adapter trước khi primary. |

## API COMPATIBILITY RISKS

1. Prescription request/response dùng naming legacy (`drug_id`, `ten_thuoc`, `lieu_dung`, `gio_nhac`, `duration_days`). Không có `drug_product_id`, V2 plan/rule status, normalized time rows hoặc occurrence trong public DTO. APP-3 phải duy trì DTO này và thêm field chỉ sau contract approval.
2. Frontend create ngay sau đó approve cùng thao tác. Any V2 validation failure phải giữ legacy-visible decision semantics rõ ràng; không âm thầm activate V2 schedule `REVIEW_REQUIRED`.
3. `doses_per_day`, cycle fields đã xuất hiện trong frontend input nhưng contract ghi nhận chúng mới Proposed; meal/start/end/cycle không được round-trip đầy đủ từ legacy response. Đặc biệt frontend tính `endDate` từ `startDate + durationDays`, trong khi V2 quy ước end-date inclusive. APP-2 phải chốt adapter semantics trước khi đổi UI/read-path.
4. `DoseEvent` một time có nhiều thuốc, còn V2 `DoseOccurrence` là một thuốc/một thời điểm. Không được thay ID, grouping hoặc status vocabulary của `/doses` trong một release.
5. Contract `specs/api-contracts.md` vẫn Draft cho API flows và mô tả dose update khác runtime thực tế. Cần review/approve contract trước bất kỳ endpoint V2 public nào.
6. V2 drug catalog runtime đọc Canonical JSONL; operational V2 identity tables là Postgres importer khác. Không được coi hai nguồn là interchangeable hoặc fall back sang manual mapping.

## TEST TOOLING

| Layer | Hiện có | Kết quả audit |
| --- | --- | --- |
| Backend unit/service | `tests/` có suite legacy và suite V2 scheduling, occurrence, dose-state, safety policy/escalation; DB closeout ghi focused V2 PostgreSQL suite PASS | Có nền tảng domain test tốt. Tuy nhiên `pytest --collect-only -q` hiện **FAIL** khi import FastAPI app tại caregiver DELETE 204, nên API/integration suite root chưa runnable. |
| Backend integration PostgreSQL | Alembic, importer/seed và concurrency tests opt-in đã có từ DB phase | Docker daemon off nên APP-1 không thể chạy fresh DB integration hoặc xác nhận revision local. |
| Frontend unit/component | `frontend/package.json` chỉ có `dev/build/start/lint/format`; không có test script hoặc declared Vitest/Jest/Testing Library | Không có frontend automated-test tooling được cấu hình. |
| Browser E2E | Không có Playwright/Cypress config, test directory hay dependency declared trong manifest. Một optional Playwright entry trong lockfile không phải test setup. | Không available. |

### Browser E2E đề xuất cho APP-7 (chưa implement)

1. Doctor chọn thuốc canonical đã resolve, tạo rồi duyệt prescription; kiểm tra legacy UI/DTO giữ nguyên và V2 sidecar reconciliation được xác minh bằng test-only DB fixture.
2. Doctor nhập/free-text hoặc drug ID unmapped, giờ thiếu/invalid, meal/cycle/date invalid; legacy request không bị tự suy đoán, V2 row là `REVIEW_REQUIRED`, không có V2 occurrence.
3. Edit rồi stop prescription: kiểm tra legacy future grouped events theo contract và assertion reconciliation cho V2 stop/cancel semantics sau khi APP-2 chốt design.
4. Khi APP-4 đã expose V2 adapter: một prescription nhiều thuốc cùng giờ phải render group UI hợp lệ nhưng tạo/rà soát occurrence riêng; kiểm tra timezone/DST/boundary qua backend fixture.
5. Khi APP-5 đã expose V2 safety adapter: transition/rerun/race không duplicate event/job; legacy-unreviewed policy không tạo clinical advice hay escalation mạnh.

## Thứ tự integration an toàn

1. **Gỡ P0 local-runtime gates** (FastAPI 204 route và Docker clean DB); xác nhận `alembic upgrade head` = `0027`, identity import/seed theo closeout. Đây là precondition, không nằm trong thay đổi APP-1.
2. **APP-2 design:** chốt legacy DTO adapters, ownership/rollback cho create-edit-stop, end-date inclusive, authorization và reconciliation keys. Không đổi API/runtime.
3. **APP-3 Doctor Prescription Flow:** dùng seam V2 sidecar hiện có; bắt đầu `LEGACY` → reconciliation/shadow → V2-primary write boundary khi approved. Giữ legacy read response và legacy grouped dose generation cho đến khi gate pass.
4. **APP-4 Dose/Schedule:** thêm V2 generator worker boundary và read/write adapter, nhưng chỉ sau finite-window, status/grouping/rollback design được duyệt.
5. **APP-5 Safety:** connect V2 state to reviewed safety/escalation policy; no recipient/provider/Agent integration.
6. **APP-6 shadow reconciliation**, rồi **APP-7 local E2E**; chỉ sau đó closeout/cutover decision riêng.

## P0/P1

### P0

- `backend/main` không import được: `@caregiver_router.delete(..., status_code=204)` tại `backend/api/caregiver_routes.py:220` gây `AssertionError: Status code 204 must not have a response body`. Không thể chạy local API hoặc root API/integration suite.
- Docker Desktop/daemon không chạy, nên PostgreSQL local revision/schema, clean migration, identity import và transactional runtime flows chưa xác minh được. Không reuse hay tin vào volume/state cũ.

### P1

- Dose PATCH legacy ghi trạng thái trực tiếp, bỏ qua V2 state machine/event log/outbox/safety; photo/chat/reporting/escalation cũng còn phụ thuộc `DoseEvent`/`Escalation`.
- Stop prescription chưa có V2 occurrence cancellation/reconciliation path; V2 read-path sẽ có risk inconsistent state nếu bật sớm.
- DTO/contract Draft thiếu V2 identity/schedule/state semantics; inclusive end-date và optional cycle chưa round-trip đầy đủ.
- Mixed internal-secret/JWT auth và `DEMO_DOCTOR_ID` là compatibility/security debt phải được xử lý bằng approved design, không qua silent API change.
- DB closeout còn P1 identity provenance/operational validation: 491 unresolved ingredient links + 1 duplicate source link, deferred strict constraints, và legacy real-data backfill chỉ NO-OP. Không ngăn sidecar import đã validated, nhưng không được diễn giải như clinical completeness.

---

# APP-1 RUNTIME AUDIT

**STATUS:** PASS — APP-1.1 đã clear hai P0 runtime ban đầu trên PostgreSQL disposable sạch.

**CURRENT RUNTIME MAP:** Legacy public API/read flows; V2 catalog default for drug search and V2 sidecar write for Doctor Prescription. Dose, reminder/state, safety and escalation remain legacy runtime.

**LEGACY DEPENDENCIES:** `Prescription.items`, `DoseEvent`, `Escalation`, `PhotoVerification`, legacy scheduler/chat/reporting, internal-secret/JWT split, and legacy DTOs.

**V2 INTEGRATION POINTS:** Drug catalog `v1`/`shadow`/`v2`; deterministic prescription sidecar sync/activation; unexposed V2 occurrence, state, notification, safety and escalation domain services.

**API COMPATIBILITY RISKS:** Legacy DTO/status/grouping and authorization must remain stable; no automatic identity mapping; end-date/cycle and stop semantics require approved adapters.

**TEST TOOLING:** Backend API collection, basic smoke và focused V2 regression hiện chạy được; root VLM-only collection vẫn cần optional `numpy`/`cv2`. Frontend có lint/format nhưng không có browser E2E.

**BROWSER E2E AVAILABLE: NO**

**P0/P1:** P0 initial đã clear: FastAPI 204 semantics, dependency drift và clean Docker/PostgreSQL đã xác minh. P1 = legacy direct writes/dependencies, no V2 API adapters, incomplete DTO semantics, inherited identity validation debt, cùng VLM test extras không nằm trong requirements.

**READY FOR INTEGRATION DESIGN: YES** — sau validation clean PostgreSQL `0027`. No cutover, Railway action or Agent integration was performed.

---

# APP-1 P0 REMAINING: NONE

**BACKEND START: PASS** — import `backend.main` (48 routes) và TestClient lifespan + `GET /health` = 200.

**CLEAN POSTGRES: PASS** — PostgreSQL pgvector container/volume disposable riêng, không reuse state cũ.

**ALEMBIC HEAD: 0027**

**V2 IMPORT/SEED: PASS** — manifest/hash integrity PASS; import lượt hai 0 row; safety seed lượt hai 0 policy; active-map duplicates/orphans = 0.

**TESTS:** API collection PASS; basic API smoke `3 passed`; focused V2 regression `73 passed`. Full root collection còn 4 VLM-only missing optional dependencies (`numpy`/`cv2`), ngoài APP-1.1 scope.

**READY FOR APP-2: YES**
