# TASK-004: Form bác sĩ nhập đơn thuốc mô phỏng

**Domain:** `prescription`
**Owner:** Nguyễn Hải Yến + AI
**Sprint:** sprint-02
**Status:** To Do
**Ưu tiên:** P1 · **Feature:** [`FEAT-001`](../specs/features.md#feat-001--tạo--duyệt-phác-đồ-human-in-the-loop)

## Mục tiêu (Goal)

Có một form để bác sĩ nhập đơn thuốc mô phỏng, làm **input thật cho agent sinh lịch nhắc** ở Sprint 03. Không có đơn thuốc thì không có `dose_event`, không có gì để nhắc — đây là đầu vào của gần như toàn bộ luồng còn lại.

## Acceptance Criteria (AC)

- [ ] Form nhập được đủ các trường khớp [`data pharmacy/schema.json`](../data%20pharmacy/schema.json): `ten_thuoc`, `ham_luong`, `dang_thuoc`, `lieu_dung`, `duong_dung`, `thoi_diem_dung`, số ngày điều trị.
- [ ] **Một đơn thuốc chứa được nhiều thuốc** (thêm/xoá dòng thuốc), không phải một form một thuốc.
- [ ] Có validate phía client: trường bắt buộc không để trống, số ngày điều trị > 0, thông báo lỗi bằng **tiếng Việt** rõ ràng.
- [ ] Phác đồ tạo mới ở trạng thái `draft` — **không** sinh lịch nhắc (BR-1.1 trong [`business-rules.md`](../specs/business-rules.md)).
- [ ] Có nút **Duyệt** tách biệt hẳn khỏi nút Lưu — thể hiện đúng ranh giới HITL: chỉ Duyệt mới kích hoạt agent.
- [ ] Dữ liệu form khớp `PrescriptionDTO` trong [`/specs/api-contracts.md`](../specs/api-contracts.md); nếu chưa có/chưa khớp thì **cập nhật contract trước**, không tự đặt field mới.
- [ ] Accessibility: mọi input có `<label>` gắn đúng, form đi được bằng bàn phím, lỗi được đọc bởi screen reader (`aria-describedby` / `aria-invalid`).
- [ ] Chạy được để demo và chụp ảnh vào tài liệu sprint.

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [ ] [`/specs/features.md`](../specs/features.md) — FEAT-001
- [ ] [`/specs/business-rules.md`](../specs/business-rules.md) — §1 vòng đời phác đồ (BR-1.1 → BR-1.5)
- [ ] [`/specs/api-contracts.md`](../specs/api-contracts.md) — `PrescriptionDTO`
- [ ] [`/specs/user-roles.md`](../specs/user-roles.md) — quyền của role `doctor`
- [ ] [`/adrs/0010-human-in-the-loop.md`](../adrs/0010-human-in-the-loop.md)
- [ ] [`/adrs/0003-api-contract-first.md`](../adrs/0003-api-contract-first.md)
- [ ] [`AGENTS.md`](../AGENTS.md)

## Gợi ý chia subtask (AI tự cập nhật khi bắt đầu)

- [ ] Đối chiếu contract `PrescriptionDTO` với schema thuốc, chốt danh sách field cuối cùng
- [ ] Dựng form nhiều dòng thuốc (thêm/xoá dòng)
- [ ] Validate client + thông báo lỗi tiếng Việt
- [ ] Phân biệt rõ Lưu (`draft`) vs Duyệt (`approved`) trên UI
- [ ] Rà accessibility (label, keyboard, aria)
- [ ] Ghi lại phần chưa nối backend (nếu TASK-003 chưa xong) và cách nối sau

## Definition of Done

Áp dụng checklist chuẩn ở [`ADR-0005`](../adrs/0005-definition-of-done.md). Tiêu chí riêng của task này:

- [ ] Không dùng dữ liệu bệnh nhân thật — chỉ dữ liệu mô phỏng
- [ ] Form không cho phép bất kỳ đường nào tạo phác đồ ở trạng thái `approved` mà không qua hành động Duyệt tường minh

## Ghi chú / trao đổi thêm

- **Phụ thuộc:** nếu [`TASK-003`](./TASK-003-skeleton-fastapi-docker-ci.md) chưa xong, làm form trước với mock data rồi nối API sau — **không chờ** backend, nhưng phải ghi rõ phần còn thiếu.
- Sinh `dose_event` từ phác đồ đã duyệt **không** thuộc task này (FEAT-002, Sprint 03). Task này dừng ở việc có đơn thuốc đúng cấu trúc và đúng trạng thái.
- `[CẦN CHỐT]` Form này là trang web riêng hay nằm trong app FE chính? Ảnh hưởng tới việc có phải dựng scaffold frontend luôn trong sprint này — PM quyết cùng [`TASK-007`](./TASK-007-wireframe-ui-flow.md).

---
**Điều hướng:** [Sprint 02](../planning/sprints/sprint-02.md) · [Backlog](../planning/backlog.md) · [Tasks](./)
