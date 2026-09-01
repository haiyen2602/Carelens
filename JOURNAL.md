# Weekly Journal — Team P-067 (VMEC-04 / CapyMedi)

> **Nhật ký Phát triển Sản phẩm:** Ghi lại quá trình 5 tuần xây dựng AI Agent Nhắc thuốc & Theo dõi Tuân thủ điều trị. Tổng hợp mục tiêu, tiến độ (Done/Doing), khó khăn & giải pháp (Blocked), bài học kỹ thuật và báo cáo nộp Mentor Duty qua từng chặng.

---

## 📅 Tuần 1: Khởi động, Khảo sát thị trường & Định hình sản phẩm (25/07 – 31/07/2026)

### 🎯 Mục tiêu tuần

- [X] Lựa chọn đề tài, xác định vấn đề lâm sàng và đối tượng người dùng trọng tâm (VMEC-04).
- [X] Phân chia vai trò cụ thể trong team và thiết lập quy chuẩn Git Workflow / CI.
- [X] Thống nhất tên thương hiệu sản phẩm: **"CapyMedi"**.
- [X] Nghiên cứu thị trường (App Vinmec, Apple Health, MediSafe, Max) và khảo sát thực tế.
- [X] Hoàn thành tài liệu Đặc tả sản phẩm (BRIEF & PRD) và khởi tạo bảng khảo sát người dùng.

### ✅ Đã hoàn thành (Done)

- Tìm hiểu và định nghĩa các metrics đánh giá cho bài toán OCR / Computer Vision nhận diện và đếm số lượng viên thuốc.
- Tạo biểu mẫu khảo sát thực tế và xây dựng bộ câu hỏi phỏng vấn chuyên sâu cho bác sĩ và bệnh nhân mãn tính.
- Làm rõ toàn bộ luồng nghiệp vụ (Workflow): *Bác sĩ kê đơn ➔ Lên lịch nhắc ➔ Chụp ảnh xác nhận ➔ Nhận diện bỏ liều/tác dụng phụ ➔ Escalate cho người thân/bác sĩ*.
- Phân chia vai trò chính xác: **M.Đạt** (Team Lead / Data / AI), **Hải Yến** (PM / UI-UX / Frontend), **Thành Đạt** (AI Engineer / Fullstack / QA), **Quốc Trường** (Tech Lead / Fullstack).
- Chốt tên thương hiệu: **"Capy medi"** (AI Agent y tế thân thiện, kiên nhẫn và đáng tin cậy).

### 🔄 Đang thực hiện (Doing)

- Triển khai khảo sát và phỏng vấn thực tế bác sĩ nội khoa và bệnh nhân cao tuổi.
- Thu thập và chuẩn hóa bộ dữ liệu thông tin thuốc (tên hoạt chất, biệt dược, hướng dẫn sử dụng, tương tác, cảnh báo tác dụng phụ).
- Khảo sát các tiện ích và kỳ vọng của người dùng đối với một ứng dụng hỗ trợ y tế thông minh.

### 🚧 Khó khăn & Giải pháp (Blocked & Solutions)

| Khó khăn gặp phải                                                                                                                        | Giải pháp xử lý                                                                                                                                                                                                          | Kết quả đạt được                                                                                                                 |
| :------------------------------------------------------------------------------------------------------------------------------------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :-------------------------------------------------------------------------------------------------------------------------------------- |
| Chưa tìm thấy điểm đột phá để tạo khoảng cách khác biệt vượt trội so với các app nhắc việc/sức khỏe thông thường. | Tập trung vào bài toán cốt lõi: Không chỉ "nhắc lịch" mà tạo**bằng chứng khách quan về tuân thủ điều trị** cho bác sĩ thông qua Vision đếm thuốc + Hội thoại tự nhiên + RAG có nguồn. | BRIEF và PRD thể hiện rõ định vị sản phẩm: Khép kín vòng lặp chăm sóc giữa Bác sĩ – Bệnh nhân – Người thân.    |
| Chưa rõ thực tế tại bệnh viện/ngành dược đã ứng dụng OCR ở những khâu nào.                                                 | Đặt câu hỏi cho Mentor/Coach và tìm kiếm tài liệu về số hóa đơn thuốc, kiểm đếm tồn kho dược bệnh viện.                                                                                               | Xác định phạm vi MVP tập trung vào kiểm đếm viên thuốc trước khi uống, không ôm đồm OCR hồ sơ bệnh án phức tạp. |

### 💡 Bài học & Quyết định kỹ thuật

- Điểm mấu chốt của dự án không dừng lại ở việc "bệnh nhân quên thuốc", mà là **ngăn ngừa bác sĩ ra quyết định lâm sàng sai lầm** do thiếu dữ liệu tuân thủ thực tế.
- Ràng buộc an toàn *Human-in-the-loop (HITL)* là điều kiện tiên quyết: Bác sĩ là người duy nhất duyệt đơn, AI không được tự ý đổi liều hay kê đơn thuốc.

### 🔗 Dữ liệu nộp bài (Mentor Duty Log)

- **Thời gian nộp:** 31/07/2026, 22:21
- **Link khảo sát & Dữ liệu:** [Bảng Khảo sát Người dùng &amp; Y tế (Google Sheets)](https://docs.google.com/spreadsheets/d/1Ywu4qKBupXsPEJrjuQYd16jsMzZUrL23gn_8E6eYlnk/edit?usp=sharing)
- **Kế hoạch tuần tiếp theo:** Thu thập thêm dữ liệu thuốc, xây dựng bản Prototype UI đầu tiên và tích hợp mô hình thị giác máy tính.

---

## 📅 Tuần 2: Xây dựng Prototype, Tích hợp VLM & Chatbot RAG (01/08 – 07/08/2026)

### 🎯 Mục tiêu tuần

- [X] Hoàn thiện bản Prototype giao diện người dùng cho cả 2 vai trò: Bác sĩ và Bệnh nhân.
- [X] Nghiên cứu và thử nghiệm công nghệ thị giác máy tính để nhận diện và đếm số lượng viên thuốc.
- [X] Xây dựng Chatbot trả lời thông tin thuốc và đơn thuốc dựa trên RAG.
- [X] Mở rộng cơ sở dữ liệu thuốc chuẩn hóa và tiếp nhận phản hồi từ bác sĩ chuyên khoa.

### ✅ Đã hoàn thành (Done)

- Hoàn thiện tương đối bản Prototype giúp trực quan hóa giao diện sử dụng dành cho Bác sĩ (quản lý đơn thuốc, lịch nhắc) và Bệnh nhân (lịch uống trong ngày, chat tư vấn).
- **Chuyển đổi kỹ thuật quan trọng:** Chuyển từ giải pháp OCR truyền thống sang **VLM (Vision-Language Model)** — mô hình cho kết quả vượt trội, phân biệt được nhiều loại nhãn, nhận diện bao bì và đếm số lượng viên thuốc chính xác hơn.
- Xây dựng Chatbot phiên bản 1 có khả năng tra cứu thông tin thuốc từ cơ sở dữ liệu chuẩn hóa và giải đáp đơn thuốc của bệnh nhân.

### 🔄 Đang thực hiện (Doing)

- Tiếp tục hoàn thiện sản phẩm MVP, kết nối các thành phần Backend và Frontend.
- Tiếp nhận ý kiến đóng góp từ các bác sĩ thực tế dựa trên bản demo ý tưởng để liên tục cải tiến nghiệp vụ.

### 🚧 Khó khăn & Giải pháp (Blocked & Solutions)

| Khó khăn gặp phải                                                                                                                                      | Giải pháp xử lý                                                                                                                                                                                                  | Kết quả đạt được                                                                                                       |
| :--------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------- |
| Chưa chắc chắn về việc AI nhận diện triệu chứng bệnh nhân là do tác dụng phụ của thuốc hay do tương tác chéo giữa các loại thuốc. | Thiết kế cấu trúc RAG chuyên biệt phân tách rõ 2 tầng: Tầng 1 tra cứu tác dụng phụ đơn thuốc; Tầng 2 đối chiếu ma trận tương tác thuốc (Drug-Drug Interaction) từ dữ liệu Dược thư. | Giảm thiểu nguy cơ AI suy đoán sai, luôn kèm khuyến cáo tham vấn bác sĩ khi phát hiện dấu hiệu bất thường. |

### 💡 Bài học & Quyết định kỹ thuật

- VLM xử lý ảnh chụp thuốc gia đình tốt hơn nhiều so với mô hình Object Detection thuần túy nhờ khả năng hiểu ngữ cảnh (màu sắc, hình dạng, vỉ thuốc kết hợp với thông tin trong đơn thuốc).

### 🔗 Dữ liệu nộp bài (Mentor Duty Log)

- **Thời gian nộp:** 07/08/2026, 21:22
- **Link Prototype & Tài liệu:** [Tài liệu Prototype &amp; Đặc tả Luồng VLM (Google Docs)](https://docs.google.com/document/d/15L63kT943Gs91QpA6RT30iPfp5iDSgb4RQ2QmU93JRY/edit?usp=sharing)
- **Kế hoạch tuần tiếp theo:** Tối ưu hóa Chatbot, kết nối trọn vẹn với Frontend và chuẩn bị nộp bài Gate 2 / Build Showcase.

---

## 📅 Tuần 3: Build Showcase, Hoàn thiện Kiến trúc & Bộ Đánh giá (08/08 – 15/08/2026)

### 🎯 Mục tiêu tuần

- [X] Đăng sản phẩm lên **Build Showcase** để nhận phản hồi từ cộng đồng và Mentor.
- [X] Hoàn thiện Sơ đồ Kiến trúc Hệ thống (Architecture Diagram) và Sơ đồ Luồng Dữ liệu (Data Flow).
- [X] Xây dựng bộ công cụ đánh giá tự động (Evaluation Framework) cho RAG và phân loại an toàn.
- [X] Cải thiện sản phẩm theo phản hồi của Gate 2.

### ✅ Đã hoàn thành (Done)

- Đăng tải sản phẩm lên Build Showcase thành công, thu thập nhiều góp ý giá trị về UI/UX và an toàn y tế.
- Xây dựng tài liệu kiến trúc chi tiết (`ARCHITECTURE.md`) với sơ đồ phân tầng rõ ràng giữa Frontend, Backend, Fail-safe Safety Gateway và Vector Store.
- Thiết lập bộ dữ liệu kiểm thử vàng (Deterministic Golden Set) và kịch bản Red-teaming để kiểm tra tính an toàn của Agent.

### 🔄 Đang thực hiện (Doing)

- Tinh chỉnh sản phẩm theo các góp ý từ Build Showcase để chuẩn bị quay video demo.
- Bổ sung và chuẩn hóa các yêu cầu của Gate 2 sau buổi trao đổi cùng Mentor.

### 🚧 Khó khăn & Giải pháp (Blocked & Solutions)

- *Tình trạng:* Tiến độ diễn ra thuận lợi, hệ thống hoạt động ổn định và vượt qua các mốc kiểm thử chính của Gate 2.

### 💡 Bài học & Quyết định kỹ thuật

- Cần xây dựng bộ test tự động độc lập với LLM (Deterministic checks) để đảm bảo các quy tắc an toàn y tế luôn được kiểm soát 100% trên CI mà không phụ thuộc vào độ biến thiên ngẫu nhiên của mô hình.

### 🔗 Dữ liệu nộp bài (Mentor Duty Log)

- **Thời gian nộp:** 15/08/2026, 08:45
- **Link Showcase & Video:** [Thư mục Build Showcase &amp; Demo Materials (Google Drive)](https://drive.google.com/drive/folders/160dUiGzmv_iIfkAyEXbVFz5e6P_UXX4d?usp=sharing)
- **Kế hoạch tuần tiếp theo:** Chuyển đổi Chatbot sang kiến trúc Agent V2 (LangGraph), phát triển giao diện Mobile PWA và tích hợp công cụ giám sát.

---

## 📅 Tuần 4: Chuyển đổi Agent V2, Đa kênh Thông báo & Dashboard Admin (16/08 – 22/08/2026)

### 🎯 Mục tiêu tuần

- [X] Nâng cấp Chatbot lên **Agent V2 (LangGraph)** với khả năng xử lý trạng thái và ghi nhận ngữ cảnh đa lượt.
- [X] Xây dựng Dashboard kiểm tra chỉ số hoạt động và theo dõi an toàn của Chatbot trên trang Admin.
- [X] Phát triển tính năng thông báo nhắc thuốc đa kênh (Push notification, cuộc gọi nhắc, Today Schedule).
- [X] Sửa lỗi và hoàn thiện tính năng đăng nhập bảo mật bằng Google OAuth.

### ✅ Đã hoàn thành (Done)

- Deploy thành công Chatbot Version 2 lên hệ thống ứng dụng thực tế.
- Bổ sung trang **Admin Monitoring Dashboard** cho phép kiểm tra chi tiết các chỉ số: tỷ lệ an toàn, độ trễ, số lượt kích hoạt Handoff và danh sách Audit Trail.
- Giao diện người dùng được cập nhật tab *Lịch uống hôm nay (Today Schedule)* cùng hệ thống thông báo đẩy trực tiếp khi đến giờ uống thuốc.
- Hoàn thiện tính năng xác thực tài khoản Google OAuth và phân quyền RBAC.

### 🔄 Đang thực hiện (Doing)

- Tích hợp công nghệ chuyển đổi giọng nói thành văn bản (Speech-to-Text) và văn bản thành giọng nói (Text-to-Speech) hỗ trợ người cao tuổi.
- Xây dựng hệ thống Semantic Caching / Truy xuất câu hỏi phổ biến để tối ưu hóa thời gian phản hồi của chatbot.

### 🚧 Khó khăn & Giải pháp (Blocked & Solutions)

- *Tình trạng:* Các tính năng mới tích hợp mượt mà, CI/CD tự động kiểm tra mã nguồn trên từng Pull Request.

### 💡 Bài học & Quyết định kỹ thuật

- Tách riêng biệt lớp xử lý an toàn (Fail-closed Safety Layer) khỏi luồng trả lời chính của Agent giúp loại bỏ hoàn toàn nguy cơ AI tự ý kê đơn hoặc đưa ra lời khuyên y tế sai lệch khi gặp lỗi.

### 🔗 Dữ liệu nộp bài (Mentor Duty Log)

- **Thời gian nộp:** 22/08/2026, 09:20
- **Link Codebase:** [GitHub Repository P-067 (VMEC-04)](https://github.com/AI20K-Build-Phase-Cohort-3/P-067)
- **Kế hoạch tuần tiếp theo:** Phát triển tra cứu thuốc bằng hình ảnh nâng cao, hoàn thiện voice chat hai chiều và tối ưu hóa toàn diện trước Demo Day.

---

## 📅 Tuần 5: Hoàn thiện Đa phương thức, Kiểm thử Toàn diện & Sẵn sàng Demo Day (23/08 – 01/09/2026)

### 🎯 Mục tiêu tuần

- [X] Hoàn thiện tính năng tra cứu thông tin thuốc bằng hình ảnh (Drug Image Retrieval & Verification).
- [X] Tích hợp Voice Chat hai chiều (người dùng nói ➔ AI hiểu ➔ AI phản hồi bằng giọng đọc tự nhiên).
- [X] Hoàn thiện hệ thống cảnh báo qua Telegram Bot và Web Push Notification.
- [X] Chạy kiểm thử toàn diện (Full Test Suite), đo lường độ bao phủ mã nguồn (Coverage) và độ trễ SLO.
- [X] Thiết kế Pitch Deck trình bày Demo Day và chuẩn bị kịch bản thuyết trình.

### ✅ Đã hoàn thành (Done)

- **Đa phương thức (Multimodal):** Hoàn thiện trọn vẹn cả 3 hình thức tương tác: Văn bản (Text), Giọng nói (Voice STT/TTS), và Hình ảnh thuốc (Image Vision).
- **Thông báo đa kênh:** Kết nối thành công bot Telegram gửi thông báo tự động tới người thân khi bệnh nhân có dấu hiệu bỏ liều hoặc gặp tác dụng phụ.
- **Trang Quản trị & Giám sát:** Hoàn thiện giao diện Admin giám sát RAG Health, phản hồi người dùng (Feedback Tickets) và can thiệp y khoa (Doctor Handoff).
- **Kiểm thử thực nghiệm xuất sắc:** Chạy toàn bộ **1.918 tests passed**, đạt **99% Line Coverage** cho lõi an toàn `safety.py`, độ trễ trung vị P50 chỉ **3,38 giây**.
- **Slide thuyết trình:** Hoàn thiện bộ slide Pitch Deck 10 trang chuẩn hóa theo Chapter 09 trên Canva và kịch bản chi tiết 45 giây cho Slide 7 Technical Highlights.

### 🔄 Đang thực hiện (Doing)

- Tổng duyệt toàn bộ 10 Deliverables nộp Ban Tổ Chức AI20K.
- Luyện tập thuyết trình và demo kịch bản trực tiếp trên môi trường Production Railway ([https://c3-app-067.up.railway.app](https://c3-app-067.up.railway.app)).

### 🚧 Khó khăn & Giải pháp (Blocked & Solutions)

- *Tình trạng:* Hệ thống đã deploy ổn định trên Railway Production, đạt 200 OK trên các Health Check endpoints, sẵn sàng 100% cho ngày hội Demo Day.

### 💡 Bài học & Quyết định kỹ thuật

- Việc giữ kỷ luật kiểm thử liên tục (Continuous Testing với hơn 2.400 test cases) và duy trì nhật ký phát triển đều đặn giúp team tự tin phản biện mọi câu hỏi kỹ thuật từ Ban Giám Khảo.

### 🔗 Dữ liệu nộp bài (Mentor Duty Log)

- **Thời gian hoàn thiện:** 01/09/2026
- **Link Slide Pitch Deck:** [Slide Pitch Deck Demo Day (Canva)](https://canva.link/ilknefaktrieh91)
- **Live Production App:** [https://c3-app-067.up.railway.app](https://c3-app-067.up.railway.app)
