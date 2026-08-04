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
| POST | `/api/v1/auth/refresh` | any | Làm mới token |
| GET | `/api/v1/auth/me` | any | Thông tin user hiện tại + role + danh sách liên kết |

```json
// POST /api/v1/auth/login — response 200
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": { "id": "usr_01", "full_name": "Nguyễn Văn A", "role": "patient" }
}
```

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
      "drug_id": "panadol-extra"
    }
  ]
}
```

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

## Lịch sử thay đổi quan trọng (breaking changes)

| Ngày | Contract | Thay đổi | Người duyệt |
|---|---|---|---|
| 2026-08-04 | tất cả | Bản draft đầu tiên, dựng từ `README.md` + `ARCHITECTURE.md` + PRD Gate 01 | `[chờ Architect + Tech Lead review]` |

---
**Lưu ý cho AI:** Không tự ý tạo field/endpoint/event mới nằm ngoài file này. Nếu task yêu cầu thay đổi contract, hãy **đề xuất thay đổi rõ ràng ở đây trước** (kèm dòng mới trong bảng "Lịch sử thay đổi") để người phụ trách review, thay vì âm thầm thay đổi trong code.
