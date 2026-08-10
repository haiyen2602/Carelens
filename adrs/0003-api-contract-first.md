# ADR-0003: API Contract First

**Status:** Accepted
**Ngày:** 2026-08-04
**Người đề xuất:** Nguyễn Minh Đạt (Architect)
**Người duyệt:** Trương Quốc Trường (Tech Leader) — `[chờ xác nhận đầu Sprint 02]`

## Bối cảnh (Context)

Sau khi chia domain (ADR-0002), các domain/service cần giao tiếp với nhau. Nếu không có hợp đồng (contract) rõ ràng, các bên sẽ phụ thuộc ngầm vào implementation nội bộ của nhau — dễ vỡ khi một bên thay đổi code mà bên kia không biết.

## Quyết định (Decision)

Các service giao tiếp với nhau qua **contract rõ ràng, định nghĩa trước khi code**, dùng một trong các hình thức:

- OpenAPI (REST)
- gRPC Proto
- Event Schema
- DTO Schema

Contract được lưu trong `/specs/api-contracts.md` (hoặc thư mục `/contracts` riêng nếu dự án lớn), là nguồn sự thật cho mọi bên tiêu thụ (consumer).

### Áp dụng cho VMEC-04

VMEC-04 có **3 frontend (bác sĩ / bệnh nhân / người thân)** do một người làm, trong khi backend + agent do ba người khác làm — nếu không chốt contract trước, FE sẽ phải chờ BE xong mới bắt đầu, không đủ 5 tuần.

| Loại contract | Dùng ở đâu trong VMEC-04 |
|---|---|
| **REST (OpenAPI)** | Toàn bộ giao tiếp FE ↔ BE. FastAPI tự sinh `/openapi.json` — nhưng bản chốt trước khi code nằm ở [`../specs/api-contracts.md`](../specs/api-contracts.md) §1–7. |
| **DTO Schema** (Pydantic) | Giao tiếp giữa các domain trong monolith: `PrescriptionDTO`, `DoseEventDTO`, `DrugInfoDTO`, `EscalationDTO` — §8. |
| **Event Schema** | Event nội bộ in-process: `scheduling.dose_due`, `conversation.classified`, `photo.verified`, `safety.redflag` — §9. Định nghĩa như contract thật ngay từ đầu để sau này tách service không phải viết lại. |
| **JSON Schema** | Dữ liệu thuốc cho RAG: [`../data pharmacy/schema.json`](../data%20pharmacy/schema.json) — **đã Stable**, mọi script crawl/chuẩn hoá phải xuất đúng schema này. |

**Ràng buộc bổ sung (đặc thù dự án y tế):**

- `DrugInfoDTO` **bắt buộc** có field `source` không rỗng. Contract này chính là cơ chế kỹ thuật chống việc agent bịa thông tin thuốc — rủi ro an toàn cao nhất của dự án.
- Response của `/api/v1/chat` bắt buộc trả `safety_flag`; FE **phải** hiện overlay cấp cứu khi `safety_flag = true`. Đây là phần contract không được bỏ qua vì lý do UI.
- Mọi lỗi theo đúng một hình dạng duy nhất (`api-contracts.md` §10) để FE xử lý thống nhất.
- Đổi contract → thêm dòng vào bảng "Lịch sử thay đổi" cuối `api-contracts.md` + thông báo consumer bị ảnh hưởng.

## Vì sao thân thiện với AI + Team

- Service A không cần đọc sâu code của Service B, chỉ cần đọc contract.
- Frontend, Backend, và AI agent có thể làm việc song song ngay khi contract đã chốt, không cần chờ implementation xong.
- Khi contract đổi → bắt buộc phải review rõ ràng, không thể "âm thầm" đổi.

## Hệ quả (Consequences)

**Tích cực:**
- Tách rời (decoupling) tốt giữa các domain, làm song song hiệu quả hơn.
- Giảm rủi ro breaking change không được phát hiện sớm.

**Đánh đổi / rủi ro:**
- Cần overhead ban đầu để thiết kế contract trước khi code.
- Nếu contract thiết kế tệ, phải sửa sẽ tốn kém vì nhiều bên đã phụ thuộc vào nó.

## Câu chốt

> Team scale bằng contract, không scale bằng hiểu ngầm.
