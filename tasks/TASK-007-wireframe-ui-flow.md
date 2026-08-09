# TASK-007: Wireframe / UI flow trên Figma (3 vai trò)

**Domain:** `frontend`
**Owner:** Nguyễn Hải Yến
**Sprint:** sprint-02 (🔄 **carry over từ Sprint 01**, việc #10)
**Status:** To Do
**Ưu tiên:** P1

## Mục tiêu (Goal)

Có wireframe đủ chi tiết cho 3 vai trò người dùng (`doctor`, `patient`, `caregiver`) để Sprint 03–04 code UI không phải vừa code vừa thiết kế. Board Figma đã tạo ở Sprint 01 nhưng **chưa có màn hình chi tiết** — task này hoàn thành phần còn lại.

## Acceptance Criteria (AC)

- [ ] **Doctor (web desktop):** danh sách bệnh nhân · form nhập/sửa phác đồ · màn hình **Duyệt** (kèm preview timeline lịch nhắc) · dashboard tuân thủ · xem audit log.
- [ ] **Patient (mobile PWA):** màn hình nhắc thuốc 3 cấp độ · chụp ảnh xác nhận + luồng chụp lại (tối đa 2 lần) · nút xác nhận tự khai · chat với agent · **overlay cấp cứu** mức Nghiêm trọng.
- [ ] **Caregiver (mobile):** hàng đợi cảnh báo **có ngữ cảnh** (bệnh nhân, thuốc, phát ngôn gốc, mức độ) · màn hình duyệt ảnh xác nhận · heatmap lịch sử tuân thủ.
- [ ] Có **user flow nối các màn hình**, không chỉ màn hình rời — đi được từ nhắc thuốc → chụp ảnh → không khớp → caregiver duyệt.
- [ ] Dashboard bác sĩ **phân biệt trực quan** `TAKEN (có xác minh)` vs `TAKEN (tự khai)` (BR-4.1) — hai màu/nhãn khác nhau, không gộp một con số.
- [ ] Màn hình `patient` đáp ứng yêu cầu người cao tuổi: chữ ≥ 16px (ưu tiên 18px), tương phản WCAG AA, vùng bấm ≥ 44×44px.
- [ ] Mỗi màn hình khớp đúng **ma trận quyền** trong [`/specs/user-roles.md`](../specs/user-roles.md) — không vẽ chức năng mà role đó không được phép (VD: không có nút duyệt phác đồ trên UI bệnh nhân).
- [ ] Link Figma (quyền xem cho cả team) được ghi vào repo — trong `README.md` hoặc `docs/`, để người sau tìm được.

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [ ] [`/specs/user-roles.md`](../specs/user-roles.md) — ma trận quyền theo role
- [ ] [`/specs/features.md`](../specs/features.md) — FEAT-001 → FEAT-011
- [ ] [`/specs/business-rules.md`](../specs/business-rules.md) — §2 nhắc 3 cấp, §3 mức nghiêm trọng, §4 xác nhận ảnh
- [ ] [`/specs/product-vision.md`](../specs/product-vision.md)
- [ ] [`/adrs/0011-photo-verification-fallback.md`](../adrs/0011-photo-verification-fallback.md)

## Gợi ý chia subtask (AI tự cập nhật khi bắt đầu)

- [ ] Liệt kê **danh sách màn hình** cần vẽ theo từng role, đối chiếu ma trận quyền trước khi vẽ
- [ ] Vẽ luồng patient trước (đường đi hay dùng nhất và khó nhất về accessibility)
- [ ] Vẽ luồng doctor (form + duyệt + dashboard)
- [ ] Vẽ luồng caregiver (hàng đợi cảnh báo + duyệt ảnh)
- [ ] Nối user flow xuyên 3 role
- [ ] Rà lại tương phản/kích thước chữ & vùng bấm
- [ ] Review với team, ghi link Figma vào repo

## Definition of Done

Áp dụng checklist chuẩn ở [`ADR-0005`](../adrs/0005-definition-of-done.md) (phần liên quan tới tài liệu/PR). Tiêu chí riêng của task này:

- [ ] Link Figma mở được bởi **cả 3 thành viên còn lại**, không phải chỉ máy người thiết kế
- [ ] Wireframe không chứa dữ liệu bệnh nhân thật — dùng tên/dữ liệu mô phỏng
- [ ] Không có màn hình nào cho phép agent kê đơn/đổi liều/chẩn đoán, kể cả ở dạng nháp (BR-7.1)

## Ghi chú / trao đổi thêm

- **Đã trượt một sprint** — nếu tuần này lại quá tải, ưu tiên vẽ xong **luồng patient** (nhắc → chụp ảnh → xác nhận) vì đó là phần Sprint 03 cần trước, rồi mới tới doctor và caregiver.
- Không cần high-fidelity design system đầy đủ; wireframe đủ rõ để code là được. Đừng đánh đổi thời gian sprint cho phần thẩm mỹ.
- Liên quan trực tiếp tới [`TASK-004`](./TASK-004-form-bac-si-nhap-don-thuoc.md) và [`TASK-005`](./TASK-005-form-khao-sat-suc-khoe.md) — hai form đó nên khớp wireframe, tránh làm hai kiểu rồi phải sửa lại.
- `[CẦN CHỐT]` Caregiver có được chat thay bệnh nhân không? ([`user-roles.md`](../specs/user-roles.md) đang để trống) — ảnh hưởng tới việc có vẽ màn hình chat cho caregiver hay không.

---
**Điều hướng:** [Sprint 02](../planning/sprints/sprint-02.md) · [Sprint 01](../planning/sprints/sprint-01.md) · [Tasks](./)
