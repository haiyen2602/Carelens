# Prompt định hướng lại — phiên Claude Code mới, không còn lịch sử cũ

> Dán prompt này đầu tiên cho phiên Claude Code mới, trước khi giao bất kỳ việc gì khác (kể cả file kickoff
> vòng 3 đã chuẩn bị sẵn). Mục đích: dựng lại đúng hiểu biết về trạng thái dự án từ chính repo, không dựa vào
> trí nhớ hội thoại cũ (đã mất).

---

## 0. Nguyên tắc bắt buộc cho phiên này

Bạn là 1 phiên Claude Code hoàn toàn mới, **không có bất kỳ ký ức nào** về những gì đã build trong dự án
này — kể cả khi có 1 đoạn tóm tắt/summary nào đó còn sót lại trong context, **không tin nó**. Lý do: chính
dự án này đã từng gặp đúng lỗi đó 1 lần (1 phần việc — cơ chế escalation nhắc lại — suýt bị coi là "chưa
làm" chỉ vì nó nằm trong 1 đoạn summary bị nén, không hiển thị trong lịch sử — chỉ phát hiện được khi verify
lại từ code thật). Áp dụng đúng bài học đó ngay từ đầu phiên này: **mọi kết luận về "đã làm gì, chưa làm gì"
phải dựa trên việc đọc code/test/git thật, không dựa trên bất kỳ mô tả bằng lời nào**, kể cả mô tả trong
chính prompt này.

---

## 1. Bối cảnh ngắn gọn (để định hướng, không phải để tin theo)

Đây là phần chatbot RAG trong VMEC-04 (Capy Daily) — app quản lý thuốc, xác nhận uống thuốc. Chatbot trả lời
câu hỏi về thuốc, xem lịch uống thuốc trong ngày, và xử lý báo cáo đã/chưa uống thuốc kèm đánh giá mức độ
nghiêm trọng + escalate gia đình/bác sĩ khi cần. Dự án đã qua nhiều vòng build (không nhớ rõ số vòng chính
xác — xác nhận lại ở bước 2).

---

## 2. Việc đầu tiên — đọc nguồn sự thật, không phải code trước

Theo đúng thứ tự:

1. **Đọc toàn bộ `chat-bot-build/chatbot-rag-design.md`** (điều chỉnh đường dẫn nếu khác) — đây là tài liệu thiết kế
   chính, đặc biệt **mục 10** — bảng trạng thái các quyết định/vấn đề đánh số (#1, #2, #5... có thể lên tới
   #20+) — đây là nguồn duy nhất đáng tin về việc gì đã chốt, đã đóng, còn mở, và ai quyết (PM/Architect/
   Phạm Thành Đạt/mentor).
2. **Đọc `business-rules.md`, `api-contracts.md`, `features.md`** nếu tồn tại (cùng thư mục `specs/`).
3. **Tìm mọi file có tên dạng "kickoff"/"build-kickoff"/"vong-2"/"vong-3"** trong `specs/` hoặc thư mục gốc
   repo — đây là các bản kế hoạch build theo từng vòng, có thể còn phần đã lên kế hoạch nhưng **chưa build**
   (đặc biệt tìm 1 file nội dung xoay quanh `safety_layer` LLM-first, hiển thị lịch uống thuốc, lịch sử
   chat — nếu tồn tại, đây là việc đang chờ làm, chưa bắt đầu).
4. **Chạy `git log --oneline --all`** — đối chiếu số lượng/nội dung commit với những gì mục 10 nói đã đóng.
   Không suy đoán từ tên commit — mở diff nếu cần để xác nhận nội dung thật.

---

## 3. Xác nhận trạng thái thật, không tin số cũ

- Chạy toàn bộ test suite thật (`pytest tests/ -v` hoặc lệnh tương đương ghi trong README/CI config) — ghi
  nhận số pass/fail **thật của lần chạy này**, không dùng con số nào từng được nhắc tới ở bất kỳ đâu khác.
- Nếu có sai lệch giữa (a) số lượng test/commit thật và (b) trạng thái mô tả trong mục 10 của design doc —
  đây là dấu hiệu có phần việc bị thất lạc thông tin (giống sự cố escalation reminder đã từng xảy ra). Nêu
  rõ sai lệch đó ra, không tự ý giả định bên nào đúng.
- Kiểm tra `.env`/`config.py` xem các giá trị đã "chốt" theo mục 10 (vd `NGUONG_VECTOR`, `hnsw_ef_search`,
  `INTERNAL_AUTH_SECRET`...) có thực sự khớp với giá trị ghi trong doc không.

---

## 4. Báo cáo lại trước khi làm bất kỳ việc gì tiếp theo

Không code gì ở bước này. Viết lại ngắn gọn:

- Bảng mục 10 hiện có bao nhiêu mục, mục nào đã đóng/còn mở, dựa trên bằng chứng gì (số test, tên commit cụ
  thể) — không phải chỉ chép lại nguyên văn trạng thái ghi trong doc.
- File kế hoạch nào (nếu có) đang ở trạng thái "đã viết nhưng chưa build" — liệt cụ thể.
- Bất kỳ sai lệch nào phát hiện được ở bước 3.

Sau khi có báo cáo này, PM sẽ xác nhận lại rồi mới giao việc tiếp theo (có thể là file kickoff vòng mới, dán
riêng sau prompt này).
