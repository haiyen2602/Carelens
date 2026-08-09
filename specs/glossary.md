# Glossary — VMEC-04

> **Owner:** Architect · **Cập nhật khi:** xuất hiện thuật ngữ mới trong specs/code
> Mục đích: cả team và AI dùng **cùng một từ cho cùng một khái niệm**. Tên trong cột "Tên trong code" là tên bắt buộc dùng khi đặt tên bảng/biến/hàm — không tự dịch lại hay đặt tên khác.

## Thuật ngữ nghiệp vụ

| Thuật ngữ | Tên trong code | Nghĩa |
|---|---|---|
| Phác đồ (điều trị) | `prescription` | Đơn thuốc bác sĩ tạo cho một bệnh nhân trong một đợt điều trị: danh sách thuốc, liều, giờ uống, số ngày. |
| Liều / lần uống thuốc | `dose_event` | Một lần uống thuốc cụ thể tại một thời điểm cụ thể. Đơn vị nhỏ nhất mà hệ thống theo dõi. |
| Dose window | `window_start` / `window_end` | Khoảng thời gian ±30 phút quanh giờ đã lên lịch, trong đó xác nhận vẫn được tính là `TAKEN`. |
| Nhắc 3 cấp độ | `reminder_level` (0→3) | Chuỗi nhắc tăng dần mức khẩn trong dose window. |
| Xác nhận có xác minh | `evidence.type = "photo"` | Liều được xác nhận bằng ảnh đã đối chiếu số viên — **bằng chứng khách quan**. |
| Xác nhận tự khai | `evidence.type = "self_report"` | Liều được xác nhận bằng nút bấm, không có ảnh. Giá trị chứng cứ thấp hơn. |
| Bốn nhãn hội thoại | `TAKEN`, `MISSED`, `DELAYED`, `SIDE_EFFECT` | Kết quả phân loại câu trả lời tự do của bệnh nhân. |
| Mức nghiêm trọng | `severity`: `LOW`/`MEDIUM`/`HIGH` | Nhẹ / Trung bình / Nghiêm trọng — quyết định escalate tới ai, nhanh thế nào. |
| Escalation | `escalation` | Hành động báo lên người thân và/hoặc bác sĩ khi có bất thường. |
| Cờ đỏ / redflag | `safety_flag`, `matched_keywords` | Dấu hiệu triệu chứng nguy hiểm phát hiện bởi safety layer → luôn `HIGH`. |
| Safety layer | `safety` | Lớp an toàn chạy **song song, độc lập** với luồng hội thoại chính (keyword OR LLM). |
| Người thân / người chăm sóc | `caregiver` | Vai trò duyệt ảnh và xử lý cảnh báo, không được kê/sửa phác đồ. |
| Tuân thủ điều trị | `adherence` | Mức độ bệnh nhân uống thuốc đúng đơn. Luôn báo cáo tách **`rate_verified`** vs **`rate_self_reported`**. |
| Audit log | `audit_log` | Bản ghi append-only mọi hành động của agent: reasoning, confidence, nguồn RAG. |

## Thuật ngữ kỹ thuật

| Thuật ngữ | Nghĩa trong dự án này |
|---|---|
| **HITL** (Human-in-the-loop) | Bác sĩ phải duyệt phác đồ và mọi đề xuất đổi lịch trước khi có hiệu lực. Xem [ADR-0010](../adrs/0010-human-in-the-loop.md). |
| **RAG** | Truy xuất thông tin thuốc **có nguồn** từ pgvector rồi mới sinh câu trả lời. Không có nguồn → không khẳng định. |
| **pgvector** | Extension vector search trong PostgreSQL — dùng thay vector DB riêng. Xem [ADR-0008](../adrs/0008-vector-store-pgvector.md). |
| **LangGraph node** | Một bước trong graph agent (`parse_phac_do`, `sinh_lich_nhac`, `phan_loai_hoi_thoai`, `doi_chieu_anh`, `danh_gia_muc_nghiem_trong`, `escalate`, `hitl_duyet_lich`). |
| **Vision tool** | Công cụ đếm số viên thuốc từ ảnh và đối chiếu với `expected_items`. |
| **Time-offset** | Biến env rút ngắn mọi mốc thời gian để demo escalation nhanh, không phải cơ chế nghiệp vụ. |
| **Recall (safety)** | Tỷ lệ ca có triệu chứng nghiêm trọng được phát hiện. **Chỉ số quan trọng nhất của hệ thống** (≥ 90–95%). |
| **Dry-run / preview timeline** | Xem trước lịch nhắc sinh ra từ phác đồ mà **không** ghi DB, để bác sĩ kiểm tra trước khi duyệt. |

## Quy ước đặt tên tiếng Việt trong code

Dự án dùng **tên tiếng Việt không dấu** cho các khái niệm nghiệp vụ đặc thù đã xuất hiện trong `ARCHITECTURE.md` (VD: node `parse_phac_do`, `sinh_lich_nhac`, `phan_loai_hoi_thoai`, `doi_chieu_anh`, `danh_gia_muc_nghiem_trong`), và **tiếng Anh** cho khái niệm kỹ thuật phổ thông (`dose_event`, `prescription`, `severity`, `escalation`).

**Nguyên tắc:** đã đặt tên nào thì giữ nguyên tên đó ở mọi nơi (DB, API, code, docs). Không tồn tại song song `phac_do` và `prescription` cho cùng một thứ — xem cột "Tên trong code" ở trên là chuẩn. Chi tiết naming convention: [ADR-0004](../adrs/0004-project-structure-and-coding-convention.md).

---
**Lưu ý cho AI:** Nếu gặp một khái niệm nghiệp vụ chưa có trong file này, **thêm vào đây** trong cùng PR thay vì tự đặt tên mới rồi để người sau đoán.
