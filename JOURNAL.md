# Weekly Journal — Team P-067 (VMEC-04)

> Ghi lại mỗi tuần: học được gì, khó khăn gì, quyết định gì, kế hoạch tiếp.

---

## Week 1: 25/7 - 1/8

### Mục tiêu tuần này
- [x] Chọn đề tài, xác định vấn đề và người dùng chính (VMEC-04 — AI Agent nhắc thuốc & theo dõi tuân thủ điều trị)
- [x] Research thị trường: app tương tự, app Vinmec, chia sẻ trải nghiệm thực tế chăm sóc người thân dùng thuốc
- [x] Viết BRIEF và PRD hoàn chỉnh
- [x] Chốt phân chia vai trò trong team và thiết lập Git workflow

### Đã hoàn thành
- Research các app nhắc thuốc/chăm sóc sức khoẻ đã deploy trên thị trường (Calendar thủ công, app Max, Health app của Apple, MediSafe)
- Tìm hiểu app Vinmec để xem tính năng chatbot và các điểm liên quan tới đề tài
- Chia sẻ câu chuyện thực tế trong gia đình về việc chăm sóc người thân lớn tuổi dùng thuốc — làm cơ sở xác định pain point
- Hoàn thành BRIEF: vấn đề, người dùng chính, cách người dùng đang xoay xở, điểm khác biệt (AI xác nhận bằng ảnh, hội thoại tự nhiên, đánh giá mức nghiêm trọng theo ngữ cảnh thuốc), phạm vi MVP, chỉ số thành công, giả định rủi ro
- Hoàn thành PRD: danh sách tính năng theo vai trò (bác sĩ/bệnh nhân/người thân/agent), chi tiết 10 tính năng với input/output và tiêu chí nghiệm thu, yêu cầu phi chức năng, ràng buộc an toàn, cắt phạm vi v1
- Chốt phân chia vai trò: M.Đạt (Team Lead/Data/AI), Yến (PM/UI-UX/Frontend), T.Đạt (AI Engineer/Fullstack/Tester), Trường (Fullstack/Tech Lead)
- Thiết lập quy tắc Git workflow team P-067: nhánh feature/fix/chore, PR bắt buộc review qua Trường trước khi merge vào main, CI (ruff + pytest) chạy trên mọi push/PR

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| Chưa có bộ dữ liệu thông tin thuốc thực tế để làm RAG cho chatbot | Bắt đầu tìm nguồn có sẵn, nếu không đủ sẽ crawl thêm | Đang trong tiến độ (In progress), chưa commit repo |
| Rủi ro cao nhất: nếu dữ liệu thuốc không đủ, agent có thể "bịa" thông tin (thành phần, tương tác, hướng dẫn dùng) | Xác định RAG trên dữ liệu có nguồn là ưu tiên kỹ thuật hàng đầu, ghi rõ thành giả định rủi ro trong BRIEF | Đã ghi nhận là rủi ro an toàn cao nhất của đề tài, cần giải quyết sớm ở Tuần 2 |
| Cần thống nhất phạm vi 5 tuần để không lan man tính năng | Xác định rõ scope MVP vs sprint sau vs không làm trong PRD (VD: không tích hợp EMR/HIS thật, không cho agent kê đơn/đổi thuốc) | PRD có bảng cắt phạm vi rõ ràng, dùng làm kim chỉ nam cho các tuần tiếp theo |

### Bài học
- Điểm mấu chốt của đề tài không phải "bệnh nhân quên thuốc" mà là "bác sĩ ra quyết định lâm sàng trên dữ liệu sai" — cần giữ thông điệp này xuyên suốt khi trình bày sản phẩm
- Ràng buộc Human-in-the-loop (bác sĩ duyệt mọi thay đổi) là điều kiện tiên quyết để bác sĩ tin dùng sản phẩm, không phải tính năng phụ
- Nên chấp nhận đánh đổi "báo thừa còn hơn bỏ sót" cho recall triệu chứng nghiêm trọng — đây là chỉ số quan trọng nhất của cả hệ thống

### Kế hoạch tuần sau
- [ ] Tìm dữ liệu thuốc cho chatbot (crawl nếu không có sẵn) và commit lên repo
- [ ] Research ứng dụng OCR trong bệnh viện/dược phẩm, có ví dụ thực tế cụ thể
- [ ] Define metric cho bài toán nhận diện số lượng thuốc (bounding box vs segmentation)
- [ ] Mở rộng và làm rõ thêm file workflow để cả team chốt được luồng hoạt động xuyên suốt dự án
- [ ] Tạo form để bác sĩ điền đơn thuốc mô phỏng (làm input cho agent sinh lịch nhắc)
- [ ] Tạo form khảo sát sức khỏe người bệnh hằng ngày
- [ ] Code Object Detection thuốc + README giải thích bài toán, giá trị đánh giá
- [ ] Viết README.md project và kiểm tra, merge vào main

---

## Week 2: [Ngày bắt đầu] - [Ngày kết thúc]

### Mục tiêu tuần này
- [ ] [Mục tiêu 1]

### Đã hoàn thành
-

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| | | |

### Bài học
-

### Kế hoạch tuần sau
-

---

<!-- Tiếp tục copy block trên cho Week 3, 4, 5, 6 -->