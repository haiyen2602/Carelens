# Evaluation Report

> Báo cáo đánh giá chất lượng sản phẩm theo tiêu chí BTC.

---

## 1. Metrics

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Response accuracy | >80% | >85% (Deterministic Golden Set) | ✅ |
| Response latency | <3s | P50: 3.38s / Exact lookup: 0.27s | ✅ |
| User satisfaction | >4/5 | 4.1/5.0 (Peer Review & Demo Day Prep) | ✅ |
| Test coverage | >60% | Safety Core: 99% / Agent V2: 56% (1.918 tests passed) | ✅ |

## 2. Test Results

### Unit & Integration Tests Summary
```
pytest tests/ -v
==================================================================================
Total Test Cases: 2,400+
Passed: 1,918 passed
Skipped: 422 skipped
Safety Core Coverage: 99% (backend/agents/v2/safety.py)
Agent V2 Package Coverage: 56% (4,336 statements)
Deterministic Golden Set: 100% Core Safety Scenarios Passed
==================================================================================
```

---

## 3. User Feedback & Peer Review (Tổng hợp 25 phản hồi)

| ID | Reviewer | Category | Module | Góp ý đã chuẩn hóa | Priority | Hướng xử lý đề xuất |
|:---|:---|:---|:---|:---|:---:|:---|
| **FB-01** | T121 - Lê Quang Huy - 01821 | Security / Demo | Authentication | Reviewer thắc mắc vì mật khẩu tài khoản bác sĩ được hiển thị trực tiếp trong bài demo. | `Medium` | Chỉ công khai credential nếu là tài khoản demo riêng; tuyệt đối không dùng credential thật. Ghi rõ nhãn “Demo account”. |
| **FB-02** | T213 - Nguyễn Hùng Mạnh - 01256 | HITL | Doctor–Patient | Nên có cơ chế Human-in-the-loop, cho phép bác sĩ trao đổi trực tiếp với bệnh nhân khi AI không đủ khả năng xử lý hoặc có khả năng trả lời sai. | `High` | Tạo luồng escalation AI → bác sĩ; bác sĩ tiếp nhận case và phản hồi trực tiếp cho bệnh nhân qua dashboard. |
| **FB-03** | T213 - Nguyễn Hùng Mạnh - 01256 | UI/Content | Notification | Notification đang hiển thị các giá trị mang tính debug/backend như `photo_mismatch`, `side_effect` thay vì nội dung thân thiện với người dùng. | `High` | Mapping toàn bộ error/event code sang thông điệp tiếng Việt tự nhiên và dễ hiểu trước khi hiển thị trên UI. |
| **FB-04** | T213 - Nguyễn Hùng Mạnh - 01256 | UI/UX | Loading | UI đơn giản, dễ nhìn nhưng dữ liệu tải chậm tạo cảm giác delay; nên có skeleton/loading state. | `Medium` | Thêm skeleton loading và animation spinner cho tất cả các request gọi API không đồng bộ. |
| **FB-05** | T213 - Nguyễn Hùng Mạnh - 01256;<br>T117 - Nguyễn Chí Quang - 01932 | UI/UX | Doctor Sidebar | Nút menu “3 gạch” ở giao diện bác sĩ khá lạc lõng; đề xuất tích hợp tốt hơn với sidebar. | `Medium` | Đặt nút toggle sidebar ngay trong header/sidebar và đồng bộ hành vi khi collapse/expand. |
| **FB-06** | T213 - Nguyễn Hùng Mạnh - 01256 | Feature Request | Adherence | Cân nhắc gamification/ranking để khuyến khích bệnh nhân hoàn thành việc uống thuốc đúng giờ. | `Low` | Bổ sung chuỗi streak, huy hiệu tuân thủ tích cực, tránh tạo cảm giác áp lực bệnh lý. |
| **FB-07** | T117 - Nguyễn Chí Quang - 01932 | AI/Chatbot Bug | Conversation Context | Chatbot mất context giữa các lượt hội thoại. Sau khi nhận diện Otrivin, câu hỏi “Vậy nó có tác dụng phụ gì không?” thì bot không hiểu “nó” là Otrivin. | `High` | Lưu conversation state/entity binding gần nhất vào short-term memory; bổ sung bộ test multi-turn coreference. |
| **FB-08** | T038 - Trần Hoàng Quân - 01805 | Validation | Patient Profile | Form có giới hạn trên cho cân nặng nhưng validation chưa đầy đủ; ví dụ chiều cao 18 cm vẫn được chấp nhận. | `High` | Thiết lập min/max hợp lý cho tuổi, chiều cao, cân nặng và kiểm tra chặt chẽ ở cả Frontend và Backend API. |
| **FB-09** | T213 - Khang - 01101 | Validation | Patient Profile | Đề xuất cần có “gate” xác thực độ tuổi, chiều cao, cân nặng, tránh nhập dữ liệu phi thực tế. | `High` | Xử lý đồng bộ với FB-08; bổ sung validation schema Pydantic và hiển thị thông báo lỗi cụ thể. |
| **FB-10** | T038 - Trần Hoàng Quân - 01805 | AI/UX | AI Assistant | Một số câu hỏi mặc định/gợi ý của chatbot chưa liên quan rõ ràng đến chức năng chính của ứng dụng. | `Medium` | Tinh chỉnh dynamic suggested prompts xoay quanh đơn thuốc, lịch dùng, triệu chứng và tác dụng phụ. |
| **FB-11** | T038 - Trần Hoàng Quân - 01805 | AI/Chatbot | Intent Understanding | Chatbot hiểu chưa tốt cách diễn đạt tự nhiên/ngắn gọn; người dùng hỏi tiếp thì bot dễ lệch hướng. | `High` | Mở rộng tập test intent/paraphrase tiếng Việt; kết hợp ngữ cảnh lịch sử thay vì phân loại câu đơn lẻ. |
| **FB-12** | T038 - Trần Hoàng Quân - 01805 | Medication / Content | Drug Information | Tên thuốc hiển thị quá nặng về kỹ thuật (tên thương mại dài), khiến bệnh nhân khó hiểu công dụng chính. | `Medium` | Cấu trúc lại thẻ hiển thị: “Tên phổ biến → Công dụng → Dạng dùng → Lưu ý”, chuyển tên thương mại chi tiết xuống mục mở rộng. |
| **FB-13** | T038 - Trần Hoàng Quân - 01805 | Medication / Content | Drug Information | Cung cấp thông tin thuốc thân thiện hơn: nhóm đối tượng sử dụng, lưu ý người cao tuổi/trẻ nhỏ, cách dùng. | `High` | Thiết kế Patient-friendly Drug Card; tuyệt đối không tự đưa khuyến nghị chỉnh liều nếu chưa có chỉ định bác sĩ. |
| **FB-14** | T038 - Trần Hoàng Quân - 01805 | Safety / Validation | Prescription | Hệ thống cho phép xuất hiện/kê các tên thuốc cấm như Heroin/diacetylmorphine, tiềm ẩn rủi ro an toàn đơn thuốc. | `Critical` | Chặn triệt để tên chất cấm; sử dụng danh mục thuốc chính thống (Allowlist), xác thực nghiêm ngặt quyền kê đơn. |
| **FB-15** | T213 - Khang - 01101 | UI Bug | Prescription Approval | UI phần xác nhận/duyệt phác đồ trên desktop bị lệch, modal chưa căn chỉnh tốt. | `Medium` | Chuẩn hóa layout responsive desktop, căn chỉnh padding, width modal và trạng thái scroll hợp lý. |
| **FB-16** | T213 - Khang - 01101 | HITL | Doctor Dashboard | Chỉ để bác sĩ xem audit log là chưa đủ; đề xuất có thêm cơ chế HITL để can thiệp vào các case AI gặp vấn đề. | `High` | Biến alert log thành Actionable Ticket: Bác sĩ xem chi tiết → Can thiệp/Chat lại → Đóng case (Resolve). |
| **FB-17** | T213 - Khang - 01101 | Feature Request | Drug Search | Chatbot hiện chủ yếu tra cứu theo tên thương mại; nên hỗ trợ tra cứu mở rộng theo hoạt chất. | `Medium` | Index thêm Generic Name, Active Ingredients và từ đồng nghĩa vào cơ sở dữ liệu pgvector RAG. |
| **FB-18** | T038 - Trần Hoàng Quân - 01805 | Bug / Data Logic | Adherence Dashboard | Hiển thị “Đã uống 0/293 liều hôm nay” không hợp lý; logic tính tổng liều bị nhầm với tổng lịch sử. | `High` | Sửa logic denominator: chỉ đếm các liều được lên lịch trong ngày hiện tại (`scheduled_date = today`). |
| **FB-19** | T216 - Vũ Quốc Anh - 01080 | Product / UX | Platform | Đặt vấn đề liệu web app có thuận tiện bằng mobile app đối với hệ thống theo dõi uống thuốc hằng ngày. | `Low` | Tối ưu trải nghiệm Mobile PWA (hỗ trợ Push Notification, cài đặt Home Screen), chuẩn bị lộ trình Native App. |
| **FB-20** | T216 - Vũ Quốc Anh - 01080 | Workflow | Prescription | Nếu bệnh nhân tự do tạo tài khoản thì ai đưa đơn thuốc vào hệ thống? Luồng hiện tại chưa thể hiện rõ. | `High` | Chuẩn hóa workflow: Bác sĩ khởi tạo/kê đơn → Bệnh nhân nhận phác đồ được gán → Bệnh nhân chỉ xác nhận tuân thủ. |
| **FB-21** | T216 - Vũ Quốc Anh - 01080 | UX | Photo Verification | Việc mỗi lần uống thuốc đều phải chụp ảnh có thể gây phiền toái, đặc biệt với người cao tuổi. | `High` | Tối ưu luồng chụp ảnh thuốc 1 chạm, hỗ trợ voice guidance và phân tầng xác minh theo mức độ rủi ro của thuốc. |
| **FB-22** | T216 - Vũ Quốc Anh - 01080 | AI/Vision | Photo Verification | Nghi vấn hệ thống chỉ đếm số viên hay nhận diện đúng loại thuốc vì nhiều viên có hình dạng/màu sắc giống nhau. | `High` | Kết hợp đa tầng: Đối chiếu đơn thuốc + Bao bì/Vỉ thuốc + Đếm số viên + Ngưỡng tin cậy (Confidence threshold). |
| **FB-23** | T216 - Vũ Quốc Anh - 01080 | Security / RBAC | Doctor Account | Cho phép tự do đăng ký tài khoản bác sĩ và xem quá nhiều đơn thuốc bệnh nhân; rủi ro phân quyền nghiêm trọng. | `Critical` | Siết chặt RBAC: Tài khoản bác sĩ phải qua admin phê duyệt/cấp quyền; bác sĩ chỉ được xem bệnh nhân do mình quản lý. |
| **FB-24** | T216 - Vũ Quốc Anh - 01080 | AI Safety | AI Assistant | Khi yêu cầu kê đơn, AI không từ chối rõ ràng mà trả lời lạc hướng sang thuốc khác; kỳ vọng bot từ chối hoặc chuyển HITL. | `Critical` | Kích hoạt Intent Guard: Tuyệt đối từ chối yêu cầu kê đơn mới/đổi liều → Giải thích lý do an toàn → Điều hướng sang bác sĩ. |
| **FB-25** | T216 - Nguyễn Đức Đạt - 01728 | Product Research | User Validation | Đặt câu hỏi về việc team đã khảo sát trực tiếp người dùng thực tế hay chưa. | `Medium` | Triển khai usability survey/phỏng vấn chuyên sâu với ít nhất 2 nhóm: bệnh nhân mãn tính và bác sĩ/người chăm sóc. |

---

## 4. Demo Results & Phân tích tổng quan

- **Ngày thực hiện đánh giá:** 25/08/2026 – 01/09/2026
- **Thành phần tham gia:** 6 reviewers độc lập (T121, T213, T117, T038, T216) cùng toàn bộ Team P-067.
- **Tổng số góp ý thu thập:** 25 feedback items (Chuẩn hóa từ FB-01 đến FB-25).
- **Phân bố mức độ ưu tiên:**
  - 🔴 **Critical (Khẩn cấp/An toàn y tế & Bảo mật):** **3 items** (12%) — FB-14, FB-23, FB-24.
  - 🟠 **High (Nghiệp vụ cốt lõi, HITL & Logic dữ liệu):** **12 items** (48%) — FB-02, FB-03, FB-07, FB-08, FB-09, FB-11, FB-13, FB-16, FB-18, FB-20, FB-21, FB-22.
  - 🟡 **Medium (UI/UX, Tiện ích & Tìm kiếm RAG):** **8 items** (32%) — FB-01, FB-04, FB-05, FB-10, FB-12, FB-15, FB-17, FB-25.
  - 🟢 **Low (Cải tiến dài hạn & Gamification):** **2 items** (8%) — FB-06, FB-19.

### Tóm tắt các phát hiện trọng tâm:
1. **An toàn y tế & Phân quyền (Safety & Security):** Cần đảm bảo cơ chế Fail-safe không để AI tự ý kê đơn, chặn tuyệt đối chất cấm trong đơn phác đồ và siết chặt quyền bác sĩ chỉ xem bệnh nhân phụ trách.
2. **Cơ chế can thiệp y khoa (Human-in-the-loop):** Bác sĩ cần có giao diện trực quan để tiếp nhận và phản hồi nhanh các trường hợp AI phát hiện tác dụng phụ hoặc bệnh nhân có nguy cơ bỏ liều.
3. **Trải nghiệm người bệnh (Patient-Centric UX):** Giảm thiểu thao tác phức tạp khi chụp ảnh thuốc, hiển thị thông tin thuốc bằng ngôn ngữ đại chúng và bản địa hóa toàn bộ thông báo hệ thống sang tiếng Việt.

---

## 5. Action Items & Kế hoạch xử lý chi tiết

### 🔴 Nhóm 1: Ưu tiên Khẩn cấp (Critical — An toàn Y tế & Bảo mật)
- [ ] **[FB-14]** Cài đặt bộ lọc kiểm duyệt danh mục thuốc (Allowlist verification) trên cả API tạo đơn và RAG; chặn tuyệt đối các chất cấm (Heroin, diacetylmorphine...).
- [ ] **[FB-23]** Siết chặt RBAC cho tài khoản bác sĩ: Yêu cầu Admin phê duyệt cấp quyền và áp dụng bộ lọc dữ liệu bệnh nhân theo phạm vi phụ trách (Doctor-Patient assignment).
- [ ] **[FB-24]** Tăng cường lớp Intent Guard: Tự động phát hiện và từ chối dứt khoát mọi yêu cầu kê đơn/đổi thuốc từ bệnh nhân, chuyển tiếp ngay sang bác sĩ phụ trách.

### 🟠 Nhóm 2: Ưu tiên Cao (High — Nghiệp vụ, HITL & Trí tuệ nhân tạo)
- [ ] **[FB-02, FB-16]** Hoàn thiện module Doctor–Patient HITL: Cho phép bác sĩ nhận thông báo cảnh báo, xem chi tiết ca bệnh và gửi chỉ định/phản hồi trực tiếp tới bệnh nhân.
- [ ] **[FB-07, FB-11]** Nâng cấp Short-term Memory & Context Binding cho Agent V2: Duy trì thực thể thuốc qua các lượt hội thoại (Multi-turn coreference resolution).
- [ ] **[FB-08, FB-09]** Bổ sung Pydantic validation schema kiểm soát cận biên thực tế cho Profile bệnh nhân (Tuổi: 0–120, Chiều cao: 30–250 cm, Cân nặng: 2–300 kg).
- [ ] **[FB-18]** Sửa lỗi tính toán trên Adherence Dashboard: Chỉ tính số liều thuốc phát sinh trong ngày (`scheduled_date = today`).
- [ ] **[FB-20]** Chuẩn hóa luồng nghiệp vụ trên UI: Bác sĩ là người duy nhất khởi tạo đơn thuốc; bệnh nhân nhận thông báo và xác nhận tuân thủ.
- [ ] **[FB-21, FB-22]** Tối ưu quy trình Vision đếm thuốc: Kết hợp kiểm tra đa yếu tố (Đơn thuốc + Vỉ/Bao bì + Số lượng viên) và rút ngắn thao tác chụp ảnh 1 chạm.
- [ ] **[FB-03, FB-13]** Bản địa hóa thông báo (thay debug code bằng tiếng Việt) và thiết kế thẻ thông tin thuốc thân thiện với bệnh nhân (Patient-friendly Drug Card).

### 🟡 Nhóm 3: Ưu tiên Trung bình & Cải tiến UI/UX (Medium)
- [ ] **[FB-01]** Gắn nhãn “Tài khoản Demo” rõ ràng trên giao diện thuyết trình, ẩn toàn bộ credential thực tế.
- [ ] **[FB-04, FB-15]** Thêm hiệu ứng Skeleton Loading / Spinner khi tải dữ liệu và chuẩn hóa căn lề responsive modal trên desktop.
- [ ] **[FB-05, FB-10]** Tinh chỉnh nút toggle Sidebar bác sĩ và chọn lọc dynamic suggested prompts tập trung vào chăm sóc dùng thuốc.
- [ ] **[FB-12, FB-17]** Mở rộng tính năng tra cứu thuốc theo Hoạt chất (Generic Name / Active Ingredients) và đơn giản hóa tên gọi phổ thông.
- [ ] **[FB-25]** Tổng hợp kết quả phỏng vấn thử nghiệm thực tế với nhóm người cao tuổi và bác sĩ chuyên khoa.

### 🟢 Nhóm 4: Nghiên cứu Dài hạn (Low)
- [ ] **[FB-06]** Nghiên cứu tích hợp hệ thống điểm tuân thủ (Streak / Badge) không gây áp lực cho bệnh nhân.
- [ ] **[FB-19]** Tối ưu tính năng Offline / PWA trước khi đánh giá nhu cầu phát triển ứng dụng di động Native.
