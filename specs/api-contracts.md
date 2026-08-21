# API Contracts — VMEC-04

> **Owner:** Architect (Nguyễn Minh Đạt) + Dev phụ trách từng domain · **Cập nhật khi:** contract giữa các service/module thay đổi
> Đây là nguồn sự thật về cách các domain/frontend **giao tiếp với nhau**. Xem [ADR-0003](../adrs/0003-api-contract-first.md) (API Contract First). Mọi thay đổi ở đây bắt buộc phải qua review — vì ảnh hưởng đến tất cả bên tiêu thụ (consumer).
> **Trạng thái tổng thể: `Draft` (Sprint 02)** — chưa có implementation, contract được chốt trước khi code.

## Nguyên tắc

- Contract được định nghĩa **trước khi code**.
- Domain A không cần đọc sâu code của domain B — chỉ cần đọc contract.
- Khi contract đổi → phải review rõ ràng, thông báo cho mọi consumer bị ảnh hưởng, ghi vào mục "Lịch sử thay đổi" cuối file.
- Prefix mọi REST endpoint: `/api/v1`. Auth: `Authorization: Bearer <JWT>`, payload JWT chứa `sub` (user id) + `role`.
- Mọi endpoint đều kiểm tra **role + quan hệ liên kết** với bệnh nhân (xem [`user-roles.md`](./user-roles.md)).

## Danh sách contract

| Contract | Loại | Domain cung cấp | Domain tiêu thụ | Trạng thái | Định nghĩa |
|---|---|---|---|---|---|
| `auth-api` | REST | `auth` | Tất cả frontend | Draft | §1 |
| `account-api` | REST | `auth` | FE admin | Draft | §1b |
| `admin-drug-api` | REST | `drug-knowledge` | FE admin RAG | Draft | §1d |
| `prescription-api` | REST | `prescription` | FE bác sĩ, `scheduling` | Draft | §2 |
| `dose-api` | REST | `scheduling` | FE bệnh nhân, FE bác sĩ | Draft | §3 |
| `chat-api` | REST | `conversation` | FE bệnh nhân | Draft | §4 |
| `photo-api` | REST | `photo-verification` | FE bệnh nhân, FE người thân | Draft | §5 |
| `escalation-api` | REST | `escalation` | FE người thân, FE bác sĩ | Draft | §6 |
| `dashboard-api` | REST | `reporting` | FE bác sĩ | Draft | §7 |
| `PrescriptionDTO`, `DoseEventDTO`, `DrugInfoDTO`, `EscalationDTO` | DTO Schema | tương ứng | nội bộ | Draft | §8 |
| `scheduling.dose_due`, `conversation.classified`, `photo.verified`, `safety.redflag` | Event Schema (nội bộ, in-process) | tương ứng | `escalation`, `audit`, `reporting` | Draft | §9 |
| `Thuoc` (dữ liệu thuốc cho RAG) | JSON Schema | `drug-knowledge` | `conversation`, `escalation` | **Stable** | [`../data pharmacy/schema.json`](../data%20pharmacy/schema.json) |

**Nguồn sự thật cho OpenAPI:** khi backend đã chạy, FastAPI tự sinh `/docs` + `/openapi.json`. File này vẫn là nơi **chốt contract trước khi code**; nếu hai bên lệch nhau → sửa cho khớp và ghi vào lịch sử thay đổi.

---

## 1. `auth-api`

| Method | Path | Role | Mô tả |
|---|---|---|---|
| POST | `/api/v1/auth/login` | public | Đăng nhập, trả JWT |
| POST | `/api/v1/auth/register` | public | Đăng ký tài khoản mới, trả JWT |
| POST | `/api/v1/auth/forgot-password` | public | Yêu cầu email đặt lại mật khẩu |
| POST | `/api/v1/auth/reset-password` | public | Đặt lại mật khẩu mới qua token |
| POST | `/api/v1/auth/change-password` | any | Đổi mật khẩu cho người dùng hiện tại (Bearer) |
| POST | `/api/v1/auth/set-password` | any | Đặt mật khẩu **lần đầu** cho tài khoản tạo qua Google (Bearer, không hỏi mật khẩu cũ) |
| POST | `/api/v1/auth/refresh` | any | Làm mới token |
| GET | `/api/v1/auth/me` | any | Thông tin user hiện tại + role + danh sách liên kết |
| POST | `/api/v1/auth/oauth/google` | internal | "Login with Google" — đổi danh tính Google đã xác thực thành JWT của hệ thống |

```json
// POST /api/v1/auth/register — request
{
  "full_name": "Nguyễn Văn A",
  "email": "patient@example.com",
  "password": "mat-khau-toi-thieu-8-ky-tu",
  "role": "patient"
}
```

`role` khi tự đăng ký chỉ nhận `patient` (mặc định `patient`); giá trị khác — kể cả `doctor` — trả `422`. Bệnh nhân và người thân dùng chung role `patient` trên form đăng ký; `doctor`/`caregiver`/`admin` chỉ được tạo bởi `admin` qua `account-api` §1b (sửa 2026-08-17 theo yêu cầu PM: trước đây `doctor` mở cho tự đăng ký).

**Ràng buộc contract — `email` là danh tính, không phân biệt chữ hoa/thường (sửa 2026-08-17, migration 0026):** mọi endpoint nhận `email` (`/auth/register`, `/auth/login`, `/auth/oauth/google`, `POST /accounts`) chuẩn hoá về `trim` + `lower` **trước** khi tra cứu hoặc lưu, và bảng `account` có unique index trên biểu thức `lower(btrim(email))`. Vì vậy `MCK@gmail.com` và `mck@gmail.com` là **một** tài khoản: đăng ký lại bằng biến thể chữ hoa trả `409`, đăng nhập bằng biến thể nào cũng vào đúng tài khoản đó, và "Login with Google" vào tài khoản đã đăng ký thủ công thay vì tạo tài khoản thứ hai. Chuẩn hoá **chỉ** gồm `trim` + `lower` — **không** bỏ dấu `.` và **không** cắt `+tag` (quy ước riêng của Gmail; áp dụng chung sẽ gộp sai hai email khác nhau ở nhà cung cấp khác, mà gộp sai tài khoản là lỗi không sửa ngược được).

```json
// POST /api/v1/auth/login, POST /api/v1/auth/register — response 200/201
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": { "id": "usr_01", "full_name": "Nguyễn Văn A", "role": "patient" }
}
```

## 1b. `account-api`

**Thêm sau `auth-api` §1 (2026-08-13)** — chưa có trong bản Draft gốc, phát sinh khi wire login thật cho `doctor`/`patient`: không có luồng tự đăng ký (đúng chủ đích, `user-roles.md`: chỉ `admin` được quản lý tài khoản), nên cần 1 API để admin tạo tài khoản cho các role khác. Đề xuất bởi AI, cần Architect/PM review.

| Method | Path | Role | Mô tả |
|---|---|---|---|
| POST | `/api/v1/accounts` | `admin` | Tạo tài khoản (bất kỳ role nào) |
| GET | `/api/v1/accounts` | `admin` | Danh sách toàn bộ tài khoản |
| PATCH | `/api/v1/accounts/{id}/status` | `admin` | Khoá/mở khoá tài khoản (`active`\|`locked`) |

```json
// POST /api/v1/accounts — request
{
  "email": "bs.huy@capymedi.dev",
  "password": "mat-khau-toi-thieu-8-ky-tu",
  "full_name": "BS. Phạm Quốc Huy",
  "role": "doctor",
  "patient_id": null,
  "doctor_id": null
}
```

```json
// POST /api/v1/accounts — response 201 (khớp GET/PATCH cũng trả dạng này)
{
  "id": "usr_01",
  "full_name": "BS. Phạm Quốc Huy",
  "email": "bs.huy@capymedi.dev",
  "role": "doctor",
  "status": "active",
  "patient_id": null,
  "doctor_id": null,
  "created_at": "2026-08-13T10:00:00+07:00"
}
```

**Ràng buộc contract:** `POST /auth/login` (§1) **bắt buộc** kiểm tra `status == "active"` — tài khoản `locked` không được cấp JWT (403), không chỉ chặn ở UI. Không có trạng thái `pending` — mọi tài khoản do admin tạo qua endpoint này là `active` ngay, không có bước kích hoạt riêng. `patient_id`/`doctor_id` là liên kết tối thiểu (text tự do) — **chưa phải** mô hình liên kết bác sĩ↔bệnh nhân↔người thân đầy đủ (đó là việc khác, ngoài phạm vi).

## 1c. "Login with Google" — `POST /api/v1/auth/oauth/google`

**Cập nhật theo ADR-0013 (2026-08-21)** — Supabase Auth (chạy trong Next.js qua `@supabase/ssr` / `@supabase/supabase-js`) làm môi giới OAuth; nguồn sự thật về danh tính vẫn là bảng `account` + JWT của backend, nhờ vậy ~40 route còn lại không phải đổi gì.

```json
// POST /api/v1/auth/oauth/google — request (server-to-server)
{
  "email": "patient@gmail.com",
  "full_name": "Nguyễn Văn A",
  "provider_account_id": "supabase-user-uuid-or-google-sub",
  "email_verified": true
}
```

Response: **giống hệt** `POST /auth/login` (§1, `LoginResponse`) — không có định dạng phiên riêng nào cho Google.

**Ràng buộc contract:**
- `role` **không** nằm trong request. Tài khoản tạo qua đường này luôn là `patient`; tài khoản đã tồn tại giữ nguyên `role` sẵn có (không leo thang quyền qua body).
- Endpoint **internal**, chặn bằng `X-Internal-Secret` (`require_internal_secret`) và **không được mở public**: nó không có mật khẩu nào để kiểm tra, toàn bộ niềm tin nằm ở chỗ người gọi đã xác thực Google giúp rồi. Public hoá = ai cũng nhận được JWT của email bất kỳ.
- `email_verified: false` → `400` (fail-closed). Nếu chấp nhận, một địa chỉ Google chưa xác thực trùng email tài khoản mật khẩu sẽ thành đường chiếm tài khoản.
- Tra cứu tài khoản theo email **không phân biệt chữ hoa/thường** (§1, migration 0026). Đây là điểm quan trọng nhất của bản sửa 2026-08-17: trước đó tài khoản đăng ký thủ công bằng `MCK@gmail.com` không được tìm thấy khi Google trả về `mck@gmail.com`, nên endpoint tạo **tài khoản thứ hai** với `patient_id` mới và hồ sơ trống, trong khi đơn thuốc/lịch uống thuốc/cảnh báo vẫn nằm ở tài khoản đầu.
- Vẫn kiểm tra `status == "active"` → `locked` trả `403`, giống §1 (nút khoá tài khoản của admin không lách được qua OAuth).
- Cột mới `account.auth_provider` (`password`\|`google`, migration 0025): tài khoản Google không có mật khẩu người dùng nên `POST /auth/change-password` trả `400` thay vì "mật khẩu hiện tại không chính xác". `GET /auth/me` trả thêm trường `auth_provider` để frontend biết **trước khi mở dialog** là phải hiện "Đặt mật khẩu" hay "Đổi mật khẩu" — nếu chỉ biết sau khi gọi API thì người dùng đã điền xong 3 ô mật khẩu rồi mới nhận lỗi.

### 1c-2. `POST /api/v1/auth/set-password` (quyết định PM 2026-08-17)

Cho tài khoản Google đặt mật khẩu lần đầu để **đăng nhập được cả hai đường** (email+mật khẩu và Google). Lý do phải có: backend hiện **chưa** cài `/auth/forgot-password` (§1 có ghi nhưng chưa implement), nên tài khoản chỉ có Google mà chủ sở hữu mất quyền truy cập Gmail sẽ không còn đường vào nào.

```json
// POST /api/v1/auth/set-password — request (Bearer)
{ "new_password": "mat-khau-toi-thieu-8-ky-tu" }
```

Response: **giống hệt** `POST /auth/change-password` (`ChangePasswordResponse` = `LoginResponse` + `detail`), vì ghi mật khẩu làm `password_changed_at` thay đổi và thu hồi mọi token cũ — phải trả token mới nếu không người vừa đặt mật khẩu bị đăng xuất khỏi chính thiết bị của họ.

**Ràng buộc contract:**
- **Không** có `current_password` — đó là điểm khác duy nhất so với `/auth/change-password`, và là lý do endpoint này phải tồn tại riêng: tài khoản Google chưa hề có mật khẩu nào để nhập.
- Chỉ nhận tài khoản `auth_provider == "google"`; tài khoản đã có mật khẩu → `400` và **không** ghi gì. Không có ràng buộc này thì một `access_token` bị lộ đổi được mật khẩu mà không cần biết mật khẩu cũ.
- Điều kiện trên là **cổng chỉ mở được một lần**: thành công sẽ đổi `auth_provider` thành `"password"`, nên lần gọi thứ hai trả `400`, mọi lần đổi sau bắt buộc qua `/auth/change-password`.
- Google vẫn đăng nhập được sau đó — `/auth/oauth/google` giữ nguyên `auth_provider` của tài khoản đã tồn tại.

### 1c-3. `POST /api/v1/auth/reset-password-sync` (ADR-0013 Supabase Reset Password)

Đồng bộ mật khẩu mới từ Supabase Auth Reset Password flow sang database của hệ thống:

```json
// POST /api/v1/auth/reset-password-sync — request (server-to-server)
{
  "email": "patient@gmail.com",
  "new_password": "mat-khau-moi-toi-thieu-8-ky-tu",
  "provider_account_id": "supabase-user-uuid"
}
```

Response: **giống hệt** `LoginResponse` (§1).
- Chặn bằng `X-Internal-Secret`.
- Cập nhật `password_hash`, `password_changed_at` (thu hồi token cũ) và chuyển `auth_provider` thành `"password"`.

### 1c-4. `POST /api/v1/auth/verify-email-sync` (ADR-0013 Supabase Email Verification)

Xác minh email thành công từ Supabase Auth và kích hoạt tài khoản `is_email_verified = true`:

```json
// POST /api/v1/auth/verify-email-sync — request (server-to-server)
{
  "email": "patient@gmail.com",
  "provider_account_id": "supabase-user-uuid"
}
```

Response: **giống hệt** `LoginResponse` (§1).
- Chặn bằng `X-Internal-Secret`.
- Cập nhật `is_email_verified = true` và `supabase_uid`.

## 2. `prescription-api`

| Method | Path | Role | Mô tả |
|---|---|---|---|
| POST | `/api/v1/prescriptions` | `doctor` | Tạo phác đồ (trạng thái `draft`) |
| GET | `/api/v1/prescriptions?patient_id=` | `doctor`, `patient`, `caregiver` | Danh sách phác đồ (lọc theo liên kết) |
| GET | `/api/v1/prescriptions/{id}` | `doctor`, `patient`, `caregiver` | Chi tiết phác đồ |
| PATCH | `/api/v1/prescriptions/{id}` | `doctor` | Sửa phác đồ (chỉ khi `draft`, hoặc sửa phác đồ đang chạy → sinh lại dose_event chưa tới hạn) |
| GET | `/api/v1/prescriptions/{id}/preview-schedule` | `doctor` | **Preview timeline** lịch nhắc trước khi duyệt (không ghi DB) |
| POST | `/api/v1/prescriptions/{id}/approve` | `doctor` | **Duyệt (HITL)** → `approved` → kích hoạt sinh `dose_event` |
| POST | `/api/v1/prescriptions/{id}/stop` | `doctor` | Dừng phác đồ đang chạy |

```json
// POST /api/v1/prescriptions — request
{
  "patient_id": "usr_02",
  "start_date": "2026-08-10",
  "duration_days": 14,
  "note": "Sau đột quỵ, theo dõi huyết áp",
  "items": [
    {
      "ten_thuoc": "Panadol Extra",
      "ham_luong": "500mg",
      "dang_thuoc": "viên nén",
      "lieu_dung": "1 viên/lần, ngày 2 lần",
      "duong_dung": "uống",
      "thoi_diem_dung": "sau ăn sáng và sau ăn tối",
      "so_vien_moi_lan": 1,
      "gio_nhac": ["08:00", "20:00"],
      "doses_per_day": 2,
      "has_cycle": true,
      "cycle_on_days": 5,
      "cycle_off_days": 2,
      "drug_id": "panadol-extra"
    }
  ]
}
```

`doses_per_day`, `has_cycle`, `cycle_on_days`, and `cycle_off_days` are
optional additive fields for DB-4E. Clients that do not send them remain
compatible: the backend derives doses/day from `gio_nhac` and writes no cycle.
When `has_cycle=true`, `cycle_on_days > 0` and `cycle_off_days >= 0` are
required. A doctor-selected `gio_nhac` count must equal `doses_per_day` before
the V2 plan/rule can become active; unresolved drug identity or any uncertain
schedule remains `REVIEW_REQUIRED` in V2. This does not change legacy
prescription or `dose_event` responses.

```json
// POST /api/v1/prescriptions/{id}/approve — response 200
{
  "id": "presc_01",
  "status": "approved",
  "approved_by": "usr_01",
  "approved_at": "2026-08-09T10:00:00+07:00",
  "dose_events_created": 28
}
```

**Ràng buộc contract:** endpoint `approve` là **cửa duy nhất** để chuyển phác đồ sang `approved`. Không domain nào được set `status = approved` bằng đường khác (ADR-0010).

## 3. `dose-api`

| Method | Path | Role | Mô tả |
|---|---|---|---|
| GET | `/api/v1/doses?patient_id=&date=` | `patient`, `doctor`, `caregiver` | Lịch liều theo ngày |
| GET | `/api/v1/doses/{id}` | `patient`, `doctor`, `caregiver` | Chi tiết một liều + trạng thái + bằng chứng |
| POST | `/api/v1/doses/{id}/confirm` | `patient` | Xác nhận bằng **nút bấm** (fallback) → `TAKEN (tự khai)` |
| POST | `/api/v1/doses/{id}/photo` | `patient` | Gửi ảnh xác nhận (multipart) — xem §5 |

```json
// GET /api/v1/doses/{id} — response 200 (DoseEventDTO)
{
  "id": "dose_1001",
  "prescription_id": "presc_01",
  "patient_id": "usr_02",
  "scheduled_at": "2026-08-10T08:00:00+07:00",
  "window_start": "2026-08-10T07:30:00+07:00",
  "window_end": "2026-08-10T08:30:00+07:00",
  "status": "PENDING",
  "reminder_level": 0,
  "expected_items": [
    { "drug_id": "panadol-extra", "ten_thuoc": "Panadol Extra", "so_vien": 1 }
  ],
  "evidence": { "type": null, "verified": false }
}
```

`status` ∈ `PENDING` | `TAKEN` | `MISSED` | `DELAYED` | `SIDE_EFFECT` | `AWAITING_CAREGIVER`
`evidence.type` ∈ `null` | `photo` | `self_report` | `caregiver_approved`

## 4. `chat-api`

| Method | Path | Role | Mô tả |
|---|---|---|---|
| POST | `/api/v1/chat` | `patient` | Gửi tin nhắn tự nhiên cho agent |
| GET | `/api/v1/chat/history?dose_id=` | `patient`, `doctor` | Lịch sử hội thoại |

```json
// POST /api/v1/chat — request
{ "dose_id": "dose_1001", "message": "hôm nay tôi bận nên chưa uống, mà thấy hơi chóng mặt" }
```

```json
// POST /api/v1/chat — response 200
{
  "reply": "Dạ, cháu đã ghi nhận là bác chưa uống liều 8h. Bác cho cháu biết chóng mặt bắt đầu từ khi nào ạ?",
  "classification": { "label": "MISSED", "secondary_labels": ["SIDE_EFFECT"], "confidence": 0.82 },
  "severity": "MEDIUM",
  "safety_flag": false,
  "needs_clarification": false,
  "sources": [ { "drug_id": "panadol-extra", "field": "tac_dung_phu" } ]
}
```

**Ràng buộc contract:**
- `classification.label` ∈ `TAKEN` | `MISSED` | `DELAYED` | `SIDE_EFFECT`.
- `severity` ∈ `LOW` | `MEDIUM` | `HIGH`.
- `safety_flag = true` → FE **bắt buộc** hiện overlay cấp cứu, bỏ qua hội thoại thường.
- `sources` rỗng → agent **không** được khẳng định thông tin thuốc trong `reply` (FEAT-006).

## 5. `photo-api`

| Method | Path | Role | Mô tả |
|---|---|---|---|
| POST | `/api/v1/doses/{id}/photo` | `patient` | Upload ảnh (multipart/form-data, field `file`) |
| GET | `/api/v1/photo-verifications/pending` | `caregiver` | Hàng đợi ảnh cần người thân duyệt (SLA 1 giờ) |
| POST | `/api/v1/photo-verifications/{id}/review` | `caregiver` | Người thân duyệt/từ chối |

```json
// POST /api/v1/doses/{id}/photo — response 200
{
  "verification_id": "pv_01",
  "matched": false,
  "detected_count": 2,
  "expected_count": 1,
  "confidence": 0.91,
  "attempt": 1,
  "max_attempts": 2,
  "next_action": "RETAKE",
  "message": "Cháu đếm được 2 viên nhưng đơn thuốc là 1 viên. Bác chụp lại giúp cháu nhé."
}
```

`next_action` ∈ `NONE` (đã khớp, `TAKEN`) | `RETAKE` | `CAREGIVER_REVIEW` (hết 2 lần)

## 6. `escalation-api`

| Method | Path | Role | Mô tả |
|---|---|---|---|
| GET | `/api/v1/escalations?status=` | `caregiver`, `doctor` | Hàng đợi cảnh báo (kèm ngữ cảnh) |
| POST | `/api/v1/escalations/{id}/ack` | `caregiver`, `doctor` | Đánh dấu đã xem/đã xử lý |

```json
// GET /api/v1/escalations — item (EscalationDTO)
{
  "id": "esc_01",
  "patient_id": "usr_02",
  "dose_id": "dose_1001",
  "severity": "HIGH",
  "trigger": "safety_redflag",
  "raw_utterance": "tôi thấy khó thở quá",
  "reason": "Phát hiện từ khoá redflag 'khó thở' + LLM xác nhận triệu chứng hô hấp nghiêm trọng",
  "created_at": "2026-08-10T08:12:00+07:00",
  "status": "OPEN",
  "notified": ["caregiver", "doctor"]
}
```

`trigger` ∈ `missed_dose` | `side_effect` | `safety_redflag` | `photo_mismatch`
`status` ∈ `OPEN` | `ACKED` | `RESOLVED`

## 7. `dashboard-api`

| Method | Path | Role | Mô tả |
|---|---|---|---|
| GET | `/api/v1/dashboard` | `doctor` | Tổng quan tất cả bệnh nhân của bác sĩ |
| GET | `/api/v1/dashboard/patients/{id}` | `doctor` | Chi tiết tuân thủ 1 bệnh nhân (heatmap, danh sách liều) |
| GET | `/api/v1/audit-log?patient_id=` | `doctor`, `admin` | Audit log hành động agent |
| GET | `/health` | public | Health check |

```json
// GET /api/v1/dashboard/patients/{id} — response 200 (rút gọn)
{
  "patient_id": "usr_02",
  "period": { "from": "2026-08-01", "to": "2026-08-10" },
  "adherence": {
    "total_doses": 20,
    "taken_verified": 12,
    "taken_self_reported": 5,
    "missed": 2,
    "delayed": 1,
    "rate_verified": 0.6,
    "rate_self_reported": 0.85
  },
  "open_escalations": 1
}
```

**Ràng buộc contract:** `rate_verified` và `rate_self_reported` **luôn trả riêng biệt** — FE không được gộp thành một con số duy nhất (FEAT-010).

## 8. DTO Schema (dùng nội bộ giữa các domain)

| DTO | Domain sở hữu | Field bắt buộc |
|---|---|---|
| `PrescriptionDTO` | `prescription` | `id`, `patient_id`, `doctor_id`, `status`, `items[]`, `start_date`, `duration_days` |
| `DoseEventDTO` | `scheduling` | `id`, `prescription_id`, `patient_id`, `scheduled_at`, `window_start`, `window_end`, `status`, `expected_items[]` |
| `DrugInfoDTO` | `drug-knowledge` | `drug_id`, `ten_thuoc`, `noi_dung`, **`source`** (bắt buộc, không được rỗng), `score` |
| `EscalationDTO` | `escalation` | `id`, `patient_id`, `severity`, `trigger`, `reason`, `created_at`, `status` |

## 9. Event Schema (nội bộ, in-process)

Ở MVP đây là **event nội bộ trong một process FastAPI** (không dùng message broker) — nhưng vẫn định nghĩa như contract để sau này tách service không phải viết lại.

```json
{ "event": "scheduling.dose_due", "version": "1.0",
  "payload": { "dose_id": "string", "patient_id": "string", "reminder_level": "number" } }
```

```json
{ "event": "conversation.classified", "version": "1.0",
  "payload": { "dose_id": "string", "label": "TAKEN|MISSED|DELAYED|SIDE_EFFECT",
               "confidence": "number", "raw_utterance": "string" } }
```

```json
{ "event": "photo.verified", "version": "1.0",
  "payload": { "dose_id": "string", "matched": "boolean", "detected_count": "number",
               "expected_count": "number", "attempt": "number" } }
```

```json
{ "event": "safety.redflag", "version": "1.0",
  "payload": { "patient_id": "string", "dose_id": "string|null", "raw_utterance": "string",
               "matched_keywords": ["string"], "llm_flagged": "boolean" } }
```

**Ràng buộc contract:** `safety.redflag` có **ưu tiên cao nhất** — consumer phải xử lý nó trước mọi event khác của cùng bệnh nhân (ADR-0009).

## 10. Quy ước lỗi (Error contract)

Mọi lỗi trả về cùng một hình dạng:

```json
{ "error": { "code": "PRESCRIPTION_NOT_APPROVED",
             "message": "Phác đồ chưa được bác sĩ duyệt.",
             "details": { "prescription_id": "presc_01" } } }
```

| HTTP | Khi nào |
|---|---|
| 400 | Payload sai định dạng (Pydantic validation) |
| 401 | Thiếu/hết hạn JWT |
| 403 | Role đúng nhưng **không có liên kết** với bệnh nhân đó |
| 404 | Không tồn tại (hoặc không được phép biết là tồn tại) |
| 409 | Xung đột trạng thái (VD: duyệt phác đồ đã duyệt, xác nhận liều đã đóng window) |
| 422 | Vi phạm ràng buộc nghiệp vụ (VD: sinh lịch từ phác đồ chưa duyệt) |
| 500 | Lỗi hệ thống — **không bao giờ lộ chi tiết nội bộ cho FE** |

## 1d. `admin-drug-api`

API chỉ đọc cho màn hình Admin RAG. Dữ liệu được tổng hợp từ các bảng canonical
`drug_product`, `drug_product_ingredient`, `ingredient` và `drug_id_map`; không có
endpoint tạo/sửa/xóa hoặc reindex.

| Method | Path | Role | Mô tả |
|---|---|---|---|
| GET | `/api/v1/admin/drugs` | `admin` | Danh sách thuốc canonical, tìm kiếm/lọc/phân trang |
| GET | `/api/v1/admin/drugs/{drug_product_id}` | `admin` | Chi tiết thuốc, hoạt chất và toàn bộ mapping |

`GET /api/v1/admin/drugs` nhận các query parameter tùy chọn:

| Parameter | Kiểu | Mặc định | Ràng buộc |
|---|---|---:|---|
| `q` | string | `null` | Tìm theo `display_name` hoặc `legacy_drug_id` |
| `mapping_status` | enum | `null` | `ACTIVE` \| `AMBIGUOUS` \| `RETIRED` \| `UNMAPPED` |
| `page` | integer | `1` | >= 1, đánh số từ 1 |
| `page_size` | integer | `20` | 1..100 |

Response list 200 chứa `items`, `page`, `page_size`, `total`, `total_pages`.
Mỗi item có `id`, `legacy_drug_id`, `display_name`, `dosage_form`, `route`,
`strength_text`, `category_id`, `ingredients`, `mapping_status` và `mappings`.
`mapping_status` là trạng thái tóm tắt, có thể `null` khi sản phẩm chưa có
mapping; `mappings` luôn là mảng đầy đủ các bản ghi mapping của sản phẩm.
Các trường canonical chưa có dữ liệu trả `null`, không suy đoán hoặc thay bằng
chuỗi rỗng. Detail trả cùng shape của một item với toàn bộ collections.
Sản phẩm không tồn tại trả `404`; caller không có role `admin` nhận response
phân quyền chuẩn của repository.

## Lịch sử thay đổi quan trọng (breaking changes)

| Ngày | Contract | Thay đổi | Người duyệt |
|---|---|---|---|
| 2026-08-04 | tất cả | Bản draft đầu tiên, dựng từ `README.md` + `ARCHITECTURE.md` + PRD Gate 01 | `[chờ Architect + Tech Lead review]` |
| 2026-08-13 | `account-api` (mới, §1b) | Thêm contract mới — cần khi wire login thật cho doctor/patient (không có luồng tự đăng ký, cần admin tạo tài khoản qua API thay vì chỉ CLI `scripts/create_admin.py`). Xem `tasks/TASK-010-auth-api.md`. | `[chờ Architect/PM review]` |
| 2026-08-17 | `prescription-api` (§2) | DB-4E đề xuất bổ sung optional `doses_per_day` và cycle (`has_cycle`, `cycle_on_days`, `cycle_off_days`) vào item. Không breaking: payload/response cũ giữ nguyên; backend fallback theo `gio_nhac`. | `[chờ Architect/PM review]` |
| 2026-08-17 | `auth-api` (§1, §1c mới) | Thêm `POST /auth/oauth/google` (internal, `X-Internal-Secret`) cho nút "Đăng nhập bằng Google" — Better Auth chỉ làm môi giới OAuth, JWT vẫn do backend phát. Kèm cột mới `account.auth_provider` (migration 0025). Không breaking: mọi endpoint cũ giữ nguyên request/response. | `[chờ Architect/PM review]` |
| 2026-08-17 | `auth-api` (§1, §1c-2 mới) | Thêm `POST /auth/set-password` (Bearer, chỉ tài khoản `auth_provider="google"`, không hỏi mật khẩu cũ) cho phép tài khoản Google đặt mật khẩu lần đầu và đăng nhập được cả hai đường; `GET /auth/me` trả thêm `auth_provider`. Không breaking: thêm endpoint + thêm field response. | `[chờ Architect/PM review]` |
| 2026-08-17 | `auth-api` (§1, §1c), `account-api` (§1b) | `email` là danh tính **không phân biệt chữ hoa/thường**: mọi endpoint nhận email chuẩn hoá `trim`+`lower` trước khi tra cứu/lưu, kèm unique index `ux_account_email_normalized` trên `lower(btrim(email))` (migration 0026, đã chuẩn hoá 3 dòng cũ trên production). Sửa bug thật: cùng một người thành 2 tài khoản khi đăng ký thủ công bằng chữ hoa rồi đăng nhập bằng Google. **Có thể breaking với client cũ** ở một chỗ: `/auth/register` và `POST /accounts` giờ trả `409` cho email chỉ khác nhau về chữ hoa/thường, và `GET /auth/me` trả email ở dạng chữ thường. | `[chờ Architect/PM review]` |
| 2026-08-19 | `admin-drug-api` (§1d, mới) | Thêm contract read-only cho Admin RAG: list/detail thuốc canonical V2, tìm kiếm/lọc trạng thái mapping, phân trang; không thêm reindex hay mutation endpoint. | `[chờ Architect/PM review]` |

---
**Lưu ý cho AI:** Không tự ý tạo field/endpoint/event mới nằm ngoài file này. Nếu task yêu cầu thay đổi contract, hãy **đề xuất thay đổi rõ ràng ở đây trước** (kèm dòng mới trong bảng "Lịch sử thay đổi") để người phụ trách review, thay vì âm thầm thay đổi trong code.
