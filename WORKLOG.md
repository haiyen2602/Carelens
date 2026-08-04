# Worklog — Team P-067 (VMEC-04)

> Ghi lại tất cả công việc đã làm theo ngày. Ai làm gì, kết quả gì.

---

## 2026-07-25 (T7)

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Cả team | Kickoff dự án VMEC-04, thảo luận đề tài và pain point ban đầu | ✅ Done | Thống nhất hướng đề tài: AI nhắc thuốc & theo dõi tuân thủ điều trị | 2h |
| M.Đạt, Yến, T.Đạt, Trường | Chốt phân chia vai trò trong team | ✅ Done | M.Đạt: Team Lead/Data/AI · Yến: PM/UI-UX/FE · T.Đạt: AI/Fullstack/Tester · Trường: Fullstack/Tech Lead | 1h |

**Tổng kết ngày:** Chốt được đề tài và vai trò từng thành viên, tạo tiền đề để research song song từ ngày mai.

---

## 2026-07-26 (CN)

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Trường | Thiết lập Git workflow team P-067 (quy tắc branch, PR, CI) | ✅ Done | Tài liệu Git workflow: feature/fix/chore, PR review qua Trường, CI ruff + pytest | 1.5h |
| Yến | Bắt đầu tìm hiểu các app nhắc thuốc/chăm sóc sức khỏe đã có trên thị trường | 🔄 WIP | Danh sách sơ bộ: Calendar thủ công, app Max, Apple Health, MediSafe | 1.5h |

**Tổng kết ngày:** Có bộ quy tắc làm việc chung trên repo; bắt đầu khảo sát cạnh tranh.

---

## 2026-07-27 (T2)

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Yến | Tiếp tục research app tương tự, so sánh tính năng | 🔄 WIP | Bảng so sánh điểm mạnh/yếu các app hiện có | 2h |
| Trường | Tải và trải nghiệm app Vinmec | 🔄 WIP | Ghi nhận app chưa có chatbot, chưa gắn với đề tài nhóm đang làm | 1.5h |
| T.Đạt, M.Đạt | Chuẩn bị chia sẻ câu chuyện thực tế chăm sóc người thân dùng thuốc | 🔄 WIP | Outline câu chuyện dùng làm case study cho BRIEF | 1h |

**Tổng kết ngày:** Tiến độ research đúng kế hoạch, chuẩn bị dữ liệu đầu vào cho BRIEF.

---

## 2026-07-28 (T3)

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Yến | Tìm hiểu: research các app khác xem có ai làm/deploy sản phẩm tương tự chưa | ✅ Done | Kết luận: chưa có sản phẩm nào ghép trọn vòng khép kín đơn duyệt → nhắc → xác nhận có bằng chứng → escalate → bác sĩ duyệt lại | 2h |
| Trường | Tìm hiểu: tải app Vinmec, xem đã có chatbot/tính năng gắn với đề tài chưa | ✅ Done | App Vinmec chưa có chatbot tương tự, ghi nhận làm input cho phần "điểm khác biệt" trong BRIEF | 1.5h |
| T.Đạt | Chia sẻ câu chuyện gia đình chăm sóc người thân lớn tuổi dùng thuốc | ✅ Done | Case study minh hoạ pain point bệnh nhân cao tuổi nhiều bệnh nền | 1h |
| M.Đạt | Chia sẻ câu chuyện gia đình chăm sóc người thân lớn tuổi dùng thuốc | ✅ Done | Case study minh hoạ pain point, dùng chung với phần trên | 1h |

**Tổng kết ngày:** Hoàn thành toàn bộ task nghiên cứu thị trường/case study theo đúng deadline 28/7, đủ dữ liệu để viết BRIEF.

---

## 2026-07-29 (T4)

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Yến | Viết tài liệu BRIEF: vấn đề, người dùng chính, cách xoay xở hiện tại | 🔄 WIP | Draft BRIEF phần 1-3 | 2.5h |
| M.Đạt | Đóng góp phần điểm khác biệt AI (xác nhận ảnh, hội thoại tự nhiên, đánh giá mức nghiêm trọng theo RAG) | 🔄 WIP | Draft BRIEF phần 4 | 2h |
| T.Đạt, Trường | Rà soát phạm vi MVP / sprint sau / không làm | 🔄 WIP | Draft BRIEF phần 5 (phạm vi) | 1.5h |

**Tổng kết ngày:** BRIEF thành hình đầy đủ các phần chính, cần hoàn thiện chỉ số thành công và giả định rủi ro.

---

## 2026-07-30 (T5)

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Yến | Hoàn thiện BRIEF: chỉ số thành công, giả định có thể làm sụp ý tưởng | ✅ Done | BRIEF VMEC-04 hoàn chỉnh | 2h |
| M.Đạt, T.Đạt | Bắt đầu viết PRD: danh sách tính năng theo vai trò | 🔄 WIP | Draft bảng tính năng bác sĩ/bệnh nhân/người thân/agent | 2.5h |
| Trường | Rà soát yêu cầu phi chức năng (hiệu năng, bảo mật, độ tin cậy) | 🔄 WIP | Draft phần 3 PRD | 1.5h |

**Tổng kết ngày:** Chốt xong BRIEF; PRD bắt đầu có cấu trúc rõ ràng theo từng vai trò.

---

## 2026-07-31 (T6)

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| M.Đạt, T.Đạt | Viết chi tiết từng tính năng PRD (input/output, tiêu chí nghiệm thu) — phần phác đồ, lịch nhắc, luồng phản hồi | 🔄 WIP | PRD mục 2.1-2.5 | 3h |
| Yến | Viết chi tiết PRD phần phát hiện bỏ liều, safety layer, dashboard, luồng người thân | 🔄 WIP | PRD mục 2.6-2.10 | 2.5h |
| Trường | Viết ràng buộc an toàn (agent KHÔNG được làm gì) và cắt phạm vi v1 | 🔄 WIP | PRD mục 4-5 | 1.5h |

**Tổng kết ngày:** PRD gần hoàn chỉnh, còn thiếu review chéo trước khi chốt cuối tuần.

---

## 2026-08-01 (T7)

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Cả team | Review chéo BRIEF + PRD, thống nhất bản cuối | ✅ Done | BRIEF & PRD VMEC-04 hoàn chỉnh (Gate 01) | 2h |
| Yến | Bắt đầu dựng Wireframe/UI flow trên Figma | 🔄 WIP | Board Figma khởi tạo, chưa có màn hình chi tiết | 2h |
| Trường | Chuẩn bị checklist công việc Tuần 2 (data thuốc, OCR, form bác sĩ) | ✅ Done | Roadmap Tuần 2 cập nhật trên file Timeline | 1h |

**Tổng kết ngày:** Chốt xong Gate 01 (đề tài + BRIEF + PRD), sẵn sàng bước sang Tuần 2 với trọng tâm dữ liệu thuốc, OCR và workflow chi tiết.

---

## [YYYY-MM-DD]

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| | | | | |

**Tổng kết ngày:**

---

<!-- Format: copy block trên cho mỗi ngày làm việc -->