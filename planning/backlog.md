# Backlog — VMEC-04

> **Owner:** PM (Nguyễn Hải Yến) · **Cập nhật khi:** thêm/sửa/ưu tiên lại hạng mục công việc
> Danh sách các feature ở mức lớn (feature level), chưa hoặc đang được đưa vào Sprint. Khi một hạng mục được chọn cho Sprint, tạo task chi tiết trong [`/tasks`](../tasks/) theo mẫu `TASK-000-template.md`.
> Định nghĩa chi tiết từng feature (mục tiêu người dùng + AC): [`../specs/features.md`](../specs/features.md).

## Backlog

| ID | Tên | Domain | Ưu tiên | Ước lượng | Sprint dự kiến | Trạng thái |
|---|---|---|---|---|---|---|
| `FEAT-006` | RAG thông tin thuốc có nguồn | `drug-knowledge` | **P0** | L | Sprint 02–03 | 🔄 In progress |
| `FEAT-004` | Xác nhận liều bằng ảnh (vision đếm viên) | `photo-verification` | **P0** | L | Sprint 02–04 | 🔄 In progress (spike) |
| `FEAT-001` | Tạo & duyệt phác đồ (HITL) | `prescription`, `auth` | **P0** | M | Sprint 02–03 | Backlog |
| `FEAT-002` | Sinh lịch nhắc & dose window | `scheduling` | **P0** | M | Sprint 03 | Backlog |
| `FEAT-003` | Nhắc thuốc 3 cấp độ (cron 1 phút) | `scheduling`, `notification` | **P0** | M | Sprint 03 | Backlog |
| `FEAT-008` | Safety layer song song | `safety` | **P0** | M | Sprint 02–04 | 🔄 In progress (test set) |
| `FEAT-005` | Hội thoại tự nhiên & phân loại 4 nhãn | `conversation` | **P0** | L | Sprint 03–04 | Backlog |
| `FEAT-007` | Đánh giá mức nghiêm trọng theo ngữ cảnh thuốc | `escalation`, `drug-knowledge` | **P1** | M | Sprint 04 | Backlog |
| `FEAT-009` | Escalation & hàng đợi cảnh báo người thân | `escalation`, `notification` | **P1** | M | Sprint 04 | Backlog |
| `FEAT-010` | Dashboard tuân thủ cho bác sĩ | `reporting` | **P1** | M | Sprint 04 | Backlog |
| `FEAT-011` | Audit log hành động của AI | `audit` | **P1** | S | Sprint 03 | Backlog |
| `FEAT-012` | Đề xuất đổi lịch nhắc chờ bác sĩ duyệt | `scheduling`, `prescription` | **P2** | M | Sprint 05 (nếu kịp) | Backlog |

**Ước lượng:** S = ≤ 1 ngày công · M = 2–3 ngày công · L = 4+ ngày công (của 1 người + AI)

## Quy tắc ưu tiên

Xếp theo thứ tự, tiêu chí trên thắng tiêu chí dưới:

1. **Rủi ro an toàn / rủi ro làm sụp đề tài trước.** Cụ thể: chất lượng dữ liệu thuốc cho RAG (nếu thiếu → agent bịa thông tin y tế) và safety layer. Đây là lý do `FEAT-006` và `FEAT-008` được ưu tiên sớm dù chưa "nhìn thấy được" trên UI.
2. **Điều kiện tiên quyết của thứ khác.** `FEAT-001` (duyệt phác đồ) chặn `FEAT-002` → `FEAT-003` → gần như toàn bộ phần còn lại. Làm trước để mở khoá luồng song song.
3. **Giá trị cốt lõi phân biệt sản phẩm.** Bằng chứng khách quan (`FEAT-004`) và dữ liệu tuân thủ thật cho bác sĩ (`FEAT-010`) — bỏ hai cái này thì sản phẩm trở thành app nhắc lịch thường.
4. **Cần cho demo cuối kỳ.** Thứ nào lên được video demo và pitch deck thì ưu tiên hơn thứ chỉ tốt về mặt kỹ thuật.
5. **Chi phí thấp, làm được song song.** Khi các tiêu chí trên ngang nhau, chọn việc không chặn người khác.

**Mức ưu tiên:** `P0` = không có thì không demo được · `P1` = cần cho một demo thuyết phục · `P2` = có thì tốt

## Việc kỹ thuật nền (không phải feature, nhưng chặn feature)

| ID | Tên | Owner | Sprint | Trạng thái |
|---|---|---|---|---|
| `INFRA-01` | Skeleton FastAPI + Docker compose (Postgres + pgvector) + CI xanh | Trương Quốc Trường | Sprint 02 | Backlog |
| `INFRA-02` | Schema DB + Alembic migration đầu tiên | Trương Quốc Trường | Sprint 03 | Backlog |
| `INFRA-03` | Khung `eval/` + bộ test set đầu tiên (safety, phân loại) | Phạm Thành Đạt | Sprint 02–03 | Backlog |
| `INFRA-04` | Deploy môi trường demo (live URL) | Trương Quốc Trường | Sprint 05 | Backlog |

## Đã cắt khỏi phạm vi v1

Ghi lại để không ai đề xuất lại giữa chừng (nguồn: PRD Gate 01, [`../specs/product-vision.md`](../specs/product-vision.md) §4):

- Tích hợp EMR/HIS thật của bệnh viện
- Agent kê đơn / đổi thuốc / đổi liều / chẩn đoán — **cấm vĩnh viễn**, không phải hoãn
- Đồng bộ thiết bị đo (huyết áp, đường huyết)
- Tích hợp nhà thuốc / đặt thuốc / thanh toán
- Tele-consult video
- Đa ngôn ngữ ngoài tiếng Việt

---
**Lưu ý:** Chỉ đưa các hạng mục **đủ lớn** (feature level) vào đây. Việc chia nhỏ thành task/subtask cụ thể được AI + Dev tự thực hiện khi bắt đầu Sprint (xem [ADR-0001](../adrs/0001-test-strategy.md), mục "Task đủ lớn").
