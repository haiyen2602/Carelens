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
| `admin-rag-monitoring-api` | REST | `observability` | FE admin RAG | Draft | §1f |
| `drug-request-api` | REST | `drug-requests` | FE bác sĩ, FE admin | Draft | §1e |
| `prescription-api` | REST | `prescription` | FE bác sĩ, `scheduling` | Draft | §2 |
| `dose-api` | REST | `scheduling` | FE bệnh nhân, FE bác sĩ | Draft | §3 |
| `drug-image-delivery-api` | REST | `drug-image` | FE bệnh nhân | Draft | §3a |
| `chat-api` | REST | `conversation` | FE bệnh nhân | Draft | §4 |
| `doctor-takeover-api` | REST | `conversation` | FE bệnh nhân, FE bác sĩ | Draft | §4a |
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
    {
      "drug_id": "panadol-extra",
      "drug_product_id": "drug-product-panadol-extra",
      "ten_thuoc": "Panadol Extra",
      "so_vien": 1,
      "image": {
        "status": "AVAILABLE",
        "url": "/api/v1/drug-images/img_01",
        "alt": "Hình ảnh bao bì Panadol Extra",
        "view_type": "front"
      }
    }
  ],
  "evidence": { "type": null, "verified": false }
}
```

`status` ∈ `PENDING` | `TAKEN` | `MISSED` | `DELAYED` | `SIDE_EFFECT` | `AWAITING_CAREGIVER`
`evidence.type` ∈ `null` | `photo` | `self_report` | `caregiver_approved`

`drug_product_id` và `image` là trường bổ sung trong từng `expected_items[]`.
Client cũ có thể bỏ qua chúng. `image.status` ∈ `AVAILABLE` | `NO_IMAGE`;
`NO_IMAGE` luôn có `url: null` và không được thay bằng ảnh của sản phẩm khác.
Mọi định danh ảnh bắt nguồn từ `drug_product_id`, hoặc từ `drug_id` legacy qua
`drug_id_map` có trạng thái `ACTIVE`; không có mapping theo tên/slug/OCR.

### 3a. `drug-image-delivery-api`

| Method | Path | Role | Mô tả |
|---|---|---|---|
| GET | `/api/v1/drug-images/{drug_image_id}` | authenticated | Trả bytes của ảnh catalog `VALIDATED` + `is_primary`, chỉ khi caller có liên kết với bệnh nhân đang được kê đúng canonical product |

`drug_image_id` là định danh opaque do dose response cung cấp. Route không nhận
`storage_key`, đường dẫn file, source URL, hay `patient_id`; backend tự xác thực
JWT và quan hệ patient/caregiver/doctor. Response dùng MIME đã lưu trong catalog,
`Cache-Control: private, max-age=86400`, và không phải delivery route cho ảnh
xác nhận liều của bệnh nhân.

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

### Agent V2 dynamic suggested actions (BUILD-29D.2)

`POST /api/v1/agent/v2/orchestrate` accepts the existing `conversation_id`
and an optional `selected_action`. The client may only echo an action that
was returned in the latest `suggested_actions` for the same authenticated
actor, patient, and conversation. `entity_id` and `topic` are never trusted
as authorization or lookup inputs by themselves.

```json
{
  "patient_id": "patient_01",
  "conversation_id": "conversation_01",
  "message": "Cong dung",
  "selected_action": {
    "action_id": "b18cb31f-3a97-4c62-b57e-9bec9c8475f8",
    "type": "drug_followup",
    "value": "drug_uses",
    "entity_id": "long-huyet"
  }
}
```

```json
{
  "reply": "...",
  "suggested_actions": [
    {
      "action_id": "d940d92d-a016-4236-9b39-b333983f5331",
      "type": "topic_followup",
      "label": "Nguyên nhân gây gan nhiễm mỡ",
      "value": "causes",
      "topic": "gan nhiễm mỡ"
    }
  ]
}
```

The server issues 0–4 actions only after the real answer has been produced.
It appends the same user-facing labels to the reply, so the action array and
answer offer the same follow-up directions. The server allowlists
`topic_followup` values (`definition`, `causes`, `symptoms`, `treatment`,
`prevention`, `danger`, `urgent_signs`, `diagnosis`, `monitoring`),
`drug_followup` values (`drug_uses`, `dosage`, `administration`,
`side_effects`, `contraindications`, `warnings`, `interactions`), and
`schedule_followup` values (`today_schedule`, `next_dose`,
`upcoming_schedule`, `adherence_history`). Unknown values are never stored
or applied. Invalid or stale actions are treated as ordinary user text.
Safety and deterministic medication-time routing inspect the raw message
first; client `entity_id` and `topic` never authorize lookup or access.

### 4a. `doctor-takeover-api`

**Bổ sung 2026-08-30, TASK-021.** Một handoff `ACTIVE` là thread chung có
thời hạn giữa đúng một bệnh nhân và bác sĩ đã nhận ca. Backend là nguồn sự
thật của thread; hai frontend polling cùng dữ liệu này, không đồng bộ qua
`localStorage`.

| Method | Path | Role | Mô tả |
|---|---|---|---|
| GET | `/api/v1/agent/v2/handoff/status?patient_id=` | `patient` | Trả handoff `ACTIVE` hiện tại và toàn bộ thread `PATIENT`/`DOCTOR`/`SYSTEM` của chính bệnh nhân. |
| GET | `/api/v1/agent/v2/handoffs/{handoff_id}` | `patient` | Trả thread của handoff đã biết, kể cả vừa kết thúc, để bệnh nhân nhận được thông báo dừng. |
| POST | `/api/v1/agent/v2/handoffs/{handoff_id}/stop` | `patient` | Bệnh nhân chủ động dừng một handoff `ACTIVE` của chính mình. Idempotent sau khi đã dừng. |
| GET | `/api/v1/doctor/reviews/{handoff_id}` | `doctor` | Chi tiết handoff, thread chung và `chat_history` (các tin nhắn bệnh nhân ↔ chatbot hiển thị được) của bệnh nhân trong ca. |

`handoff_id` không cấp quyền. Mọi route trên xác thực JWT và kiểm tra quan hệ
với `patient_id`; caller không có quyền nhận `403` hoặc `404` theo quy ước §10.

```json
{
  "handoff_id": "handoff_01",
  "status": "ACTIVE",
  "messages": [
    {"id": "msg_01", "sender_role": "PATIENT", "content": "Bác sĩ ơi", "created_at": "2026-08-30T13:41:00Z"},
    {"id": "msg_02", "sender_role": "DOCTOR", "content": "Tôi đang theo dõi.", "created_at": "2026-08-30T13:41:28Z"}
  ]
}
```

Khi bác sĩ, bệnh nhân hoặc timeout kết thúc một handoff `ACTIVE`, backend phải
chuyển nó thành `RESOLVED` và ghi đúng một message `SYSTEM` có nội dung:
`"Bác sĩ xin dừng cuộc trò chuyện tại đây"`. Scheduler dùng chung quét mỗi
phút; handoff tự kết thúc khi đã **10 phút** kể từ tin nhắn `PATIENT` gần nhất
(hoặc từ lúc `activated_at` nếu bệnh nhân chưa gửi tin nào). Retry/tick lặp lại
không được tạo message SYSTEM thứ hai.

`chat_history` chỉ gồm các tin nhắn patient/assistant không bị ẩn của bệnh nhân
và chỉ được trả cho bác sĩ xem đúng handoff đó. Agent V2 phải ghi bản hiển thị
của mỗi lượt patient/assistant vào lịch sử này sau khi đã có response terminal;
không lưu prompt, chain-of-thought, secret hay output tool thô.

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

API quản trị dữ liệu thuốc và cơ sở tri thức RAG cho Admin. Hỗ trợ đầy đủ CRUD và tự động ghi log kiểm toán (`SystemAuditLog`).

**Cập nhật 2026-08-21 (FB-14):** danh sách còn nối thêm các thuốc đã duyệt qua
`drug_request` (xem §1e) — nếu không, admin duyệt xong rồi mở màn hình này lại
không thấy dấu vết gì. Mỗi dòng vì thế mang thêm trường `source`:

| `source` | Nghĩa |
|---|---|
| `CANONICAL` | Đến từ artifact Canonical V2, có provenance (ADR-0012). **Mặc định** — client cũ chưa đọc trường này không đổi hành vi |
| `DRUG_REQUEST` | Thuốc bác sĩ xin bổ sung, admin đã duyệt. Chưa có trong artifact V2, chưa có chunk RAG, `ingredients` luôn rỗng |

Dòng `DRUG_REQUEST` mang `mapping_status = UNMAPPED` (chúng chưa hề có bản ghi
trong `drug_id_map`) và **chỉ xuất hiện** khi không lọc trạng thái ánh xạ hoặc khi
lọc đúng `UNMAPPED`. Chúng luôn được xếp ở cuối toàn bộ danh sách, không phải cuối
mỗi trang, để phân trang không lặp dòng.

Thứ tự tra cứu ở `GET /api/v1/admin/drugs/{id}`: canonical trước, không thấy mới
tra `drug_request` — đường ngoại lệ không bao giờ ghi đè lên dữ liệu có nguồn.

| Method | Path | Role | Mô tả |
|---|---|---|---|
| GET | `/api/v1/admin/drugs/filters` | `admin` | Lấy danh sách các dạng bào chế và đường dùng có trong DB |
| GET | `/api/v1/admin/drugs` | `admin` | Danh sách thuốc, hỗ trợ tìm kiếm theo từ khóa, lọc theo dạng bào chế, đường dùng, trạng thái ánh xạ và phân trang |
| POST | `/api/v1/admin/drugs` | `admin` | Thêm thuốc mới vào cơ sở tri thức RAG (ghi audit log) |
| GET | `/api/v1/admin/drugs/{drug_product_id}` | `admin` | Chi tiết thuốc, hoạt chất, toàn bộ mapping và các đoạn văn bản tri thức RAG |
| PATCH | `/api/v1/admin/drugs/{drug_product_id}` | `admin` | Cập nhật thông tin thuốc và các đoạn tri thức RAG (ghi audit log) |
| DELETE | `/api/v1/admin/drugs/{drug_product_id}` | `admin` | Xóa thuốc và các chunk tri thức liên quan khỏi hệ thống (ghi audit log) |

`GET /api/v1/admin/drugs` nhận các query parameter tùy chọn:

| Parameter | Kiểu | Mặc định | Ràng buộc |
|---|---|---:|---|
| `q` | string | `null` | Tìm theo `display_name` hoặc `legacy_drug_id` |
| `dosage_form` | string | `null` | Lọc theo dạng bào chế |
| `route` | string | `null` | Lọc theo đường dùng |
| `mapping_status` | enum | `null` | `ACTIVE` \| `AMBIGUOUS` \| `RETIRED` \| `UNMAPPED` |
| `page` | integer | `1` | >= 1, đánh số từ 1 |
| `page_size` | integer | `20` | 1..100 |

Response list 200 chứa `items`, `page`, `page_size`, `total`, `total_pages`.

## 1f. `admin-rag-monitoring-api` (proposed by BUILD-31; review required)

`GET /api/v1/admin/rag/retrieval` remains admin-only. Its `metrics` object
uses `number | null`: `null` means unavailable, never a zero score. The
companion `metric_provenance[metric]` declares `status` (`AVAILABLE`,
`NOT_AVAILABLE`, or `NOT_APPLICABLE`), `source` (`golden`, `heuristic`, or
`operational`), and a machine-readable `reason` when no score can be
calculated. `evaluated_sample_count` is the number of retrieval-backed traces
considered, not all chat traffic.

Live traffic currently has no authoritative relevance IDs. Therefore
`hit_rate_10`, `mrr_10`, and `ndcg_10` are `null` with
`reason: "no_relevance_ground_truth"`. Independent numeric IR metrics are
only returned by a future/versioned golden-evaluation result that supplies
retrieved IDs and relevant IDs. This is a non-breaking response extension and
semantic correction, but requires Architect/Frontend review before release.

## 1e. `drug-request-api`

Đường thoát cho FB-14. Từ 2026-08-20 danh mục thuốc là **allowlist đóng** — bác sĩ
không kê được thuốc không có `drug_id` (xem §2). Không có đường thoát thì gặp thuốc
ngoài danh mục là bác sĩ kẹt hẳn. Đây là đường đó: bác sĩ gửi yêu cầu, admin duyệt,
duyệt xong mới kê được.

| Method | Path | Role | Mô tả |
|---|---|---|---|
| POST | `/api/v1/drug-requests` | `doctor` | Gửi yêu cầu bổ sung, luôn tạo ở `PENDING` |
| GET | `/api/v1/drug-requests` | `doctor` | Yêu cầu **của chính mình** (lọc theo JWT, không nhận `doctor_id` từ query) |
| GET | `/api/v1/admin/drug-requests` | `admin` | Toàn bộ hàng đợi, lọc theo `status` |
| POST | `/api/v1/admin/drug-requests/{id}/approve` | `admin` | Sinh `approved_drug_id`, chuyển `APPROVED` |
| POST | `/api/v1/admin/drug-requests/{id}/reject` | `admin` | `note` **bắt buộc** |

**Chỉ `admin` được duyệt** — khớp ma trận quyền trong `user-roles.md`. Cho bác sĩ tự
duyệt yêu cầu của chính mình thì lỗ hổng FB-14 quay lại nguyên vẹn.

Trạng thái: `PENDING` → `APPROVED` | `REJECTED`. Xử lý lại một yêu cầu đã xong trả 409.

`approved_drug_id` dạng `req-<slug>-<hash6>` — chính là giá trị FE gửi lên trong
`PrescriptionItemIn.drug_id` khi kê đơn. Tiền tố `req-` để nhìn id là biết thuốc đến
từ đường ngoại lệ.

Mã lỗi riêng của contract này (ngoài §10):

| `code` | HTTP | Khi nào |
|---|---:|---|
| `CONTROLLED_SUBSTANCE_BLOCKED` | 422 | Tên thuốc chứa hoạt chất bị kiểm soát — chặn ngay lúc **tạo**, không đợi tới bước duyệt |
| `DRUG_ALREADY_IN_CATALOG` | 409 | Đã có thuốc mang mã đó trong danh mục gốc |
| `INVALID_DRUG_REQUEST_STATE` | 409 | Duyệt/từ chối một yêu cầu đã xử lý, hoặc từ chối mà không ghi lý do |
| `DRUG_REQUEST_NOT_FOUND` | 404 | |

**Hai giới hạn phải biết:**

1. Đây là **cổng người, không phải allowlist**. Danh sách chất bị kiểm soát thu hẹp
   bề mặt chứ không đóng lại được — admin bấm duyệt qua loa là mở lại FB-14.
2. Thuốc duyệt qua đường này **chatbot không trả lời được** (chưa có dữ liệu trong
   `drug_chunks`). Việc sinh chunk + embedding thuộc mảng RAG, tách task riêng.
Mỗi item có `id`, `legacy_drug_id`, `display_name`, `dosage_form`, `route`,
`strength_text`, `packaging`, `category_id`, `category_name`, `severity`, `ingredients`, `mapping_status` và `mappings`.
Detail trả thêm các trường văn bản RAG: `cong_dung`, `cach_dung`, `tac_dung_phu`, `bao_quan`.
Caller không có role `admin` nhận response phân quyền chuẩn (403/401).

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
| 2026-08-23 | `admin-rag-monitoring-api` (§1f, proposed) | BUILD-31 quy định provenance, trạng thái N/A và denominator cho metric Evaluation V2; live IR metric không có ground truth trả `null`, không alias hay dùng `0`. | `[chờ Architect/Frontend review]` |
| 2026-08-26 | `dose-api` (§3), `drug-image-delivery-api` (mới, §3a) | B-06 thêm metadata ảnh catalog an toàn vào `expected_items[]` và route bytes xác thực. Không breaking: field là additive; ảnh thiếu trả `NO_IMAGE`/`url: null`; không lộ storage/provenance. | `[chờ Architect/Frontend review]` |
| 2026-08-30 | `doctor-takeover-api` (mới, §4a) | TASK-021 thêm thread chung bệnh nhân/bác sĩ, bệnh nhân dừng, timeout 10 phút và lịch sử chatbot an toàn cho bác sĩ trong handoff. Additive; cần Architect + Frontend review. | `[chờ Architect/Frontend review]` |

---
**Lưu ý cho AI:** Không tự ý tạo field/endpoint/event mới nằm ngoài file này. Nếu task yêu cầu thay đổi contract, hãy **đề xuất thay đổi rõ ràng ở đây trước** (kèm dòng mới trong bảng "Lịch sử thay đổi") để người phụ trách review, thay vì âm thầm thay đổi trong code.
