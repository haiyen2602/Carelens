# Features — VMEC-04

> **Owner:** PM (Nguyễn Hải Yến) · **Cập nhật khi:** thêm/sửa/loại bỏ tính năng
> Danh sách tính năng ở mức tổng quan (feature level — đủ lớn, xem [ADR-0001](../adrs/0001-test-strategy.md) mục "Task đủ lớn"). Task chi tiết được triển khai trong [`/tasks`](../tasks/); thứ tự ưu tiên & sprint xem [`/planning/backlog.md`](../planning/backlog.md).
> Nguồn: PRD chốt tại Gate 01 (2026-08-01) — 10 tính năng theo vai trò.

## Danh sách tính năng

| ID | Tên tính năng | Domain liên quan | Mô tả ngắn | Ưu tiên | Trạng thái |
|---|---|---|---|---|---|
| `FEAT-001` | Tạo & duyệt phác đồ (HITL) | `prescription`, `auth` | Bác sĩ nhập đơn thuốc qua form, duyệt để kích hoạt agent | **High** | Planned |
| `FEAT-002` | Sinh lịch nhắc & dose window | `scheduling` | Agent parse phác đồ đã duyệt → sinh `dose_event`, dose window ±30', preview timeline cho bác sĩ | **High** | Planned |
| `FEAT-003` | Nhắc thuốc 3 cấp độ | `scheduling`, `notification` | Cron 1 phút quét liều đến hạn, nhắc tăng dần, đóng dose window khi hết hạn | **High** | Planned |
| `FEAT-004` | Xác nhận liều bằng ảnh | `photo-verification` | Vision đếm viên thuốc, đối chiếu phác đồ, tối đa 2 lần chụp lại → người thân duyệt | **High** | Planned |
| `FEAT-005` | Hội thoại tự nhiên & phân loại 4 nhãn | `conversation` | Bệnh nhân trả lời tự do → Taken/Missed/Delayed/SideEffect, hỏi lại khi confidence thấp | **High** | Planned |
| `FEAT-006` | RAG thông tin thuốc có nguồn | `drug-knowledge` | Truy xuất chỉ định/tác dụng phụ/tương tác từ pgvector, luôn kèm nguồn, không bịa | **High** | In progress |
| `FEAT-007` | Đánh giá mức nghiêm trọng theo ngữ cảnh thuốc | `escalation`, `drug-knowledge` | Kết hợp loại thuốc + RAG → Nhẹ / Trung bình / Nghiêm trọng (không rule cứng) | **High** | Planned |
| `FEAT-008` | Safety layer song song | `safety` | Keyword rules OR LLM phát hiện triệu chứng nguy hiểm, cắt luồng + escalate khẩn < 2' | **High** | Planned |
| `FEAT-009` | Escalation & hàng đợi cảnh báo người thân | `escalation`, `notification` | Gửi cảnh báo theo mức rủi ro, người thân xử lý hàng đợi có ngữ cảnh | Med | Planned |
| `FEAT-010` | Dashboard tuân thủ cho bác sĩ | `reporting` | Tuân thủ **tự khai** vs **có xác minh**, heatmap lịch sử, cảnh báo | Med | Planned |
| `FEAT-011` | Audit log hành động của AI | `audit` | Ghi reasoning, confidence, nguồn RAG cho mọi hành động agent; bác sĩ xem được | Med | Planned |
| `FEAT-012` | Đề xuất đổi lịch nhắc chờ bác sĩ duyệt | `scheduling`, `prescription` | Agent đề xuất, **không tự áp dụng** — bác sĩ duyệt mới có hiệu lực | Low (sprint sau) | Planned |

## Chi tiết từng feature

### FEAT-001 — Tạo & duyệt phác đồ (Human-in-the-loop)

**Mục tiêu người dùng:** Là bác sĩ, tôi muốn nhập đơn thuốc của bệnh nhân và tự tay duyệt trước khi hệ thống bắt đầu nhắc, để tôi kiểm soát được những gì AI làm với bệnh nhân của mình.

**Acceptance Criteria (AC) ở mức feature:**
- [ ] Bác sĩ nhập được: tên thuốc, hàm lượng, dạng thuốc, liều dùng, đường dùng, thời điểm dùng, số ngày điều trị (khớp `data pharmacy/schema.json`).
- [ ] Phác đồ mới ở trạng thái `draft`/`pending`, **không** sinh lịch nhắc.
- [ ] Chỉ khi bác sĩ bấm **Duyệt** → trạng thái `approved` → agent mới kích hoạt (FEAT-002).
- [ ] Bác sĩ dừng/sửa được phác đồ đang chạy; các `dose_event` chưa tới hạn được cập nhật theo.
- [ ] Mọi hành động duyệt/sửa/dừng đều ghi audit log kèm người thực hiện + thời điểm.

**Ghi chú kỹ thuật:** Là điều kiện tiên quyết của FEAT-002 → FEAT-010. Xem [ADR-0010](../adrs/0010-human-in-the-loop.md).

---

### FEAT-002 — Sinh lịch nhắc & dose window

**Mục tiêu người dùng:** Là bệnh nhân, tôi muốn nhận nhắc đúng giờ theo đúng đơn bác sĩ đã duyệt, không phải tự tính toán "uống lúc mấy giờ".

**AC:**
- [ ] Từ phác đồ `approved`, hệ thống sinh đầy đủ `dose_event` cho toàn bộ đợt điều trị.
- [ ] Mỗi `dose_event` có: thời điểm nhắc, **dose window ±30 phút**, danh sách thuốc + số viên mong đợi, trạng thái ban đầu `pending`.
- [ ] Bác sĩ xem được **preview timeline** trước khi duyệt.
- [ ] Sinh lịch là **idempotent**: duyệt lại/sửa phác đồ không tạo `dose_event` trùng lặp.

**Ghi chú kỹ thuật:** Node `parse_phac_do` + `sinh_lich_nhac`. Không sinh lịch cho phác đồ chưa duyệt.

---

### FEAT-003 — Nhắc thuốc 3 cấp độ

**Mục tiêu người dùng:** Là bệnh nhân hay quên, tôi muốn được nhắc nhiều lần với mức độ tăng dần, để không bỏ sót liều nhưng cũng không bị làm phiền quá mức.

**AC:**
- [ ] Cron job chạy **mỗi 1 phút**, quét `dose_event` đến hạn — độ trễ nhắc < 1 phút.
- [ ] Nhắc theo 3 cấp độ tăng dần trong dose window `[CẦN CHỐT: mốc thời gian chính xác của cấp 2, cấp 3 — đề xuất T+0, T+15', T+30']`.
- [ ] Hết dose window mà không có phản hồi → `dose_event` chuyển `MISSED` và đi vào FEAT-007.
- [ ] Có biến **time-offset** để tăng tốc mô phỏng khi demo.
- [ ] Bệnh nhân đã xác nhận → dừng ngay các cấp nhắc còn lại.

**Ghi chú kỹ thuật:** Xem [ADR-0007](../adrs/0007-scheduler-cron-dose-event.md).

---

### FEAT-004 — Xác nhận liều bằng ảnh

**Mục tiêu người dùng:** Là bác sĩ, tôi muốn có bằng chứng khách quan rằng thuốc đã thực sự được uống, không chỉ là bệnh nhân bấm "đã uống".

**AC:**
- [ ] Bệnh nhân chụp ảnh thuốc đã bày ra trước khi uống, gửi qua PWA.
- [ ] Vision tool đếm số viên và đối chiếu với số viên mong đợi của `dose_event`.
- [ ] Khớp → `TAKEN` (có xác minh). Không khớp → yêu cầu chụp lại, **tối đa 2 lần**.
- [ ] Sau 2 lần vẫn không khớp → chuyển sang **người thân duyệt** trong 1 giờ.
- [ ] Có fallback **nút bấm** khi bệnh nhân không chụp được ảnh → đánh dấu `TAKEN (tự khai)`, phân biệt rõ với `TAKEN (có xác minh)` trên dashboard.
- [ ] Ảnh được lưu kèm kết quả đối chiếu và confidence vào audit log.

**Ghi chú kỹ thuật:** Metric mô hình đếm viên (bounding box vs segmentation) chốt ở TASK-002. Xem [ADR-0011](../adrs/0011-photo-verification-fallback.md).

---

### FEAT-005 — Hội thoại tự nhiên & phân loại 4 nhãn

**Mục tiêu người dùng:** Là bệnh nhân cao tuổi, tôi muốn trả lời bằng lời nói tự nhiên ("hôm nay bận nên chưa uống") thay vì phải học cách dùng app.

**AC:**
- [ ] Agent phân loại câu trả lời tự do thành đúng 1 trong 4 nhãn: `TAKEN` / `MISSED` / `DELAYED` / `SIDE_EFFECT`.
- [ ] Confidence thấp hơn ngưỡng `[CẦN CHỐT: đề xuất 0.7]` → agent **hỏi lại** thay vì đoán.
- [ ] Phát hiện tín hiệu tác dụng phụ **ẩn** trong câu nói (VD: "uống xong thấy chóng mặt" → `TAKEN` + `SIDE_EFFECT`).
- [ ] Mọi phát ngôn của bệnh nhân đồng thời đi qua safety layer (FEAT-008), độc lập với luồng này.
- [ ] Nhãn + confidence + reasoning ghi vào audit log.

**Ghi chú kỹ thuật:** Bộ test hội thoại tiếng Việt lưu ở `eval/`; accuracy mục tiêu ≥ 85%.

---

### FEAT-006 — RAG thông tin thuốc có nguồn

**Mục tiêu người dùng:** Là bệnh nhân, tôi muốn hỏi "thuốc này uống trước hay sau ăn?" và nhận câu trả lời đúng, có nguồn — không phải thông tin AI tự bịa.

**AC:**
- [ ] Dữ liệu thuốc chuẩn hoá theo `data pharmacy/schema.json`, mỗi bản ghi có `id` + `danh_muc` + nguồn.
- [ ] Embedding & lưu trên **pgvector**; truy vấn trả về top-k kèm **nguồn trích dẫn bắt buộc**.
- [ ] **Không tìm được nguồn → agent trả lời "không có thông tin, vui lòng hỏi bác sĩ"**, tuyệt đối không suy đoán.
- [ ] Agent không trả lời câu hỏi mang tính chẩn đoán/kê đơn (chuyển hướng sang bác sĩ).

**Ghi chú kỹ thuật:** Đây là **rủi ro an toàn cao nhất của dự án** (xem `JOURNAL.md` Week 1). Xem [ADR-0008](../adrs/0008-vector-store-pgvector.md), TASK-001.

---

### FEAT-007 — Đánh giá mức nghiêm trọng theo ngữ cảnh thuốc

**Mục tiêu người dùng:** Là người thân, tôi không muốn bị báo động mỗi lần bố mẹ quên 1 viên vitamin, nhưng phải biết ngay khi họ bỏ liều thuốc tim mạch.

**AC:**
- [ ] Mức nghiêm trọng được tính từ **loại thuốc + ngữ cảnh RAG**, không phải rule cứng theo số liều bỏ lỡ.
- [ ] Phân loại 3 mức: **Nhẹ** (ghi log, theo dõi 48h) / **Trung bình** (escalate người thân + bác sĩ) / **Nghiêm trọng** (overlay cấp cứu + escalate khẩn < 2 phút).
- [ ] Ví dụ nghiệm thu: bỏ 1 liều thuốc tim mạch > bỏ 3 liều vitamin.
- [ ] Reasoning + nguồn RAG dùng để quyết định được ghi audit log.

**Ghi chú kỹ thuật:** Phụ thuộc FEAT-006. Xem [`business-rules.md`](./business-rules.md) §3.

---

### FEAT-008 — Safety layer song song

**Mục tiêu người dùng:** Là bệnh nhân/người thân, tôi cần hệ thống không bao giờ bỏ sót dấu hiệu nguy hiểm, kể cả khi tôi nói nó một cách bình thản giữa câu chuyện khác.

**AC:**
- [ ] Hai lớp chạy độc lập: **keyword rules** + **LLM classifier**, kết hợp bằng **OR** (một lớp cờ đỏ là đủ).
- [ ] Chạy trên **mọi** phát ngôn của bệnh nhân, không phụ thuộc luồng `phan_loai_hoi_thoai`; lỗi/độ trễ luồng chính không được chặn safety.
- [ ] Cờ đỏ → cắt ngang luồng hiện tại, hiện **overlay cấp cứu**, push khẩn người thân + bác sĩ trong < 2 phút.
- [ ] **Recall ≥ 90–95%** trên bộ test triệu chứng nghiêm trọng; chấp nhận false positive.
- [ ] Danh sách keyword redflag versioned trong repo, có thể mở rộng không cần đổi code.

**Ghi chú kỹ thuật:** Xem [ADR-0009](../adrs/0009-safety-layer-dual-classifier.md). Đây là chỉ số quan trọng nhất của cả hệ thống.

---

### FEAT-009 — Escalation & hàng đợi cảnh báo người thân

**Mục tiêu người dùng:** Là người thân, tôi muốn thấy cảnh báo **kèm ngữ cảnh** (bệnh nhân đã nói gì, bỏ liều thuốc nào) để biết phải làm gì, thay vì một thông báo trống rỗng.

**AC:**
- [ ] Cảnh báo hiển thị: bệnh nhân, liều/thuốc liên quan, phát ngôn gốc, mức nghiêm trọng, thời điểm.
- [ ] Người thân xử lý được cảnh báo (đã xem / đã liên hệ / cần bác sĩ) — trạng thái phản ánh về dashboard bác sĩ.
- [ ] Mức Nghiêm trọng gửi song song cả người thân và bác sĩ, không xếp hàng chờ.
- [ ] Có chống spam: gộp cảnh báo trùng trong cùng dose window.

---

### FEAT-010 — Dashboard tuân thủ cho bác sĩ

**Mục tiêu người dùng:** Là bác sĩ, tôi muốn nhìn một màn hình là biết bệnh nhân này có thực sự uống thuốc hay không, trước khi quyết định tăng liều/đổi thuốc.

**AC:**
- [ ] Phân biệt rõ **tuân thủ tự khai** vs **tuân thủ có xác minh (ảnh)** — không gộp thành một con số.
- [ ] Xem theo bệnh nhân: tỷ lệ tuân thủ, heatmap theo ngày/khung giờ, danh sách liều `MISSED`/`DELAYED`.
- [ ] Danh sách cảnh báo đã escalate và trạng thái xử lý.
- [ ] Cập nhật gần real-time sau mỗi `dose_event` đóng.
- [ ] Chỉ hiển thị bệnh nhân do chính bác sĩ đó phụ trách.

---

### FEAT-011 — Audit log hành động của AI

**Mục tiêu người dùng:** Là bác sĩ, tôi chỉ tin dùng AI khi truy vết được vì sao nó ra quyết định đó.

**AC:**
- [ ] Mỗi hành động agent ghi: node/bước, input rút gọn, output, confidence, nguồn RAG, phiên bản prompt/model, timestamp.
- [ ] Bản ghi audit **append-only** — không sửa, không xoá.
- [ ] Bác sĩ xem được audit log của bệnh nhân mình phụ trách.
- [ ] Không log dữ liệu nhạy cảm thừa (tuân thủ PHI/PII).

---

### FEAT-012 — Đề xuất đổi lịch nhắc chờ bác sĩ duyệt *(sprint sau)*

**Mục tiêu người dùng:** Là bác sĩ, tôi muốn AI gợi ý điều chỉnh giờ nhắc cho phù hợp thói quen bệnh nhân, nhưng quyền quyết định vẫn thuộc về tôi.

**AC:**
- [ ] Agent phát hiện mẫu (VD: luôn uống trễ 1 tiếng khung sáng) → tạo **đề xuất**, không tự áp dụng.
- [ ] Đề xuất vào hàng đợi duyệt của bác sĩ, kèm lý do + dữ liệu chứng minh.
- [ ] Bác sĩ duyệt → lịch nhắc cập nhật; từ chối → giữ nguyên, ghi log.

---
**Lưu ý cho AI:** Feature ở đây là "đủ lớn" — không phải task chi tiết. Khi bắt đầu triển khai, AI được quyền tự chia feature thành các subtask hợp lý (ghi lại trong [`/tasks`](../tasks/)), thay vì chờ người chia sẵn từng bước nhỏ. Các ô `[CẦN CHỐT]` **phải hỏi PM trước khi code**, không tự quyết.
