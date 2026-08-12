# Prototype: Chatbot tra cứu thông tin thuốc trong đơn

Bản **thử nghiệm** để xem hành vi thật của thiết kế đã thảo luận, trước khi build
vào `src/` chính thức theo `ARCHITECTURE.md`. Chạy thật bằng `OPENAI_API_KEY`
trong `.env` ở gốc repo — không dùng DB/auth, chỉ đọc thẳng `data pharmacy/`.

## Cách chạy

```bash
pip install openai python-dotenv
python prototypes/drug_chatbot/demo.py
```

Cần có `OPENAI_API_KEY` trong `.env` ở gốc repo (đã có sẵn theo bạn xác nhận).

Đổi model qua biến môi trường (mặc định `gpt-5-nano`):
```bash
CHATBOT_MODEL=gpt-4o-mini python prototypes/drug_chatbot/demo.py
```

## Thiết kế đã áp dụng (theo đúng những gì đã chốt trong hội thoại)

1. **Thẻ cô đọng (lớp 2)** — `ham_luong`/`lieu_dung`/`thoi_diem_dung` lấy từ
   `MOCK_PRESCRIPTION` trong `demo.py` (mô phỏng đơn bác sĩ đã duyệt,
   `PrescriptionDTO.items[]`), **không** lấy từ `data pharmacy/`. Vì bác sĩ
   nhập qua form (ngắn gọn), field này thực tế sẽ không bao giờ dài — nên
   *không* cần bước rút gọn LLM ở đây.
2. **Khớp tên thuốc theo từ khoá**, không cần gõ đủ cụm — khớp cả theo
   `ten_thuoc` (tên biệt dược) lẫn từng hoạt chất tách từ `ham_luong` (tên
   hoạt chất, vd hỏi "Metformin" vẫn khớp đúng "Galvus Met").
3. **2 loại "không tìm thấy" khác nhau:**
   - Hỏi thuốc **ngoài đơn hiện tại** → từ chối, hướng về bác sĩ, **không** log.
   - Thuốc **có trong đơn** nhưng **không có** trong `data pharmacy/` → câu trả
     lời cố định + ghi vào `missing_drugs_log.jsonl` (hàng đợi bổ sung dữ liệu
     sau bằng `scripts/map_drug_data.py` / `crawler/`).
4. **Rút gọn văn bản dài từ kho tham chiếu** (khi chatbot cần trích 1 field dài,
   ví dụ `lieu_dung`/`tac_dung_phu` của `data pharmacy/` có thể rất dài) —
   LLM rút gọn rồi **validate bằng code**: trích mọi số+đơn vị (mg/ml/viên/
   lần...) trong bản gốc và bản rút gọn, nếu bản rút gọn có số **không có**
   trong bản gốc → huỷ, dùng lại bản gốc. Test thật với `lieu_dung` dài
   11.573 ký tự của Galvus Met → rút còn 851 ký tự, validate pass.
5. Câu trả lời luôn kèm `sources: [{drug_id, field}]` — khớp `chat-api` đã
   chốt trong `specs/api-contracts.md` §4.

## Bệnh án giả định (`CASE_PROFILES`)

Ngoài đơn mẫu cố định (`0`), có 3 "bệnh án" tự build từ dữ liệu **thật** trong
`data pharmacy/` (không hardcode thuốc) — chọn 1 thuốc đại diện mỗi `danh_muc`
phù hợp tình huống, tự sinh `lieu_dung` ngắn gọn kiểu bác sĩ (qua LLM + validate
chống bịa số) từ đoạn `lieu_dung` tham chiếu (có thể rất dài — đã test thật với
Galvus Met 11.573 ký tự), gán `thoi_diem_dung` theo quy ước `danh_muc`
(`THOI_DIEM_BY_DANH_MUC` — chỉ là quy ước hợp lý cho demo, **không phải tư vấn
y khoa**, bản thật phải lấy từ bác sĩ):

1. Cụ bà 68 tuổi — tăng huyết áp, đái tháo đường type 2, thiếu vitamin B
2. Nam 35 tuổi — viêm họng cấp do nhiễm khuẩn, cần tăng đề kháng
3. Nữ 50 tuổi — viêm da dị ứng, mất ngủ do căng thẳng, rối loạn tiêu hoá nhẹ

## Bug đã phát hiện & sửa khi chạy thật (đáng lưu ý khi build lại vào `src/`)

**Vòng 1:**
- `gpt-5-nano` (reasoning-tier) **không nhận tham số `temperature` tuỳ chỉnh**
  — chỉ dùng mặc định. Gọi API với `temperature=0.x` sẽ lỗi 400.
- So khớp tên thuốc theo **nguyên cụm** thất bại khi người dùng chỉ gõ 1 từ
  (vd "Cordamil" thay vì "Cordamil 40mg Helcor") — phải so theo **token**,
  bỏ token là số/đơn vị.
- Phân loại field theo từ khoá bị lỗi **thứ tự dict**: `"tac dung"` là
  substring của `"tac dung phu"` nên "tác dụng phụ" bị nhận nhầm thành field
  `tac_dung`. Sửa bằng cách chọn keyword khớp **dài nhất** thay vì khớp đầu
  tiên theo thứ tự khai báo.

**Vòng 2 (phát hiện khi test thêm câu hỏi tự nhiên hơn):**
- Câu hỏi **tổng quát về lịch uống thuốc** (vd "sáng nay tôi uống thuốc gì")
  không nhắc tên thuốc nào → luôn rơi vào nhánh "không thấy thuốc trong đơn".
  Phải tách riêng 1 nhánh nhận diện ý định "hỏi lịch" (`is_schedule_query`),
  xử lý **trước** bước tìm tên thuốc, và trả lời thẳng từ đơn (không cần LLM).
- Token hoá bị dính dấu câu: `"Cordamil:40"` bị coi là 1 token liền
  (`"cordamil:40"`), không khớp được với token `"cordamil"` — phải strip dấu
  câu trước khi tách từ (`_tokenize()`), áp dụng cho **cả câu hỏi lẫn tên
  thuốc trong đơn** (so khớp set cần cả 2 bên cùng chuẩn hoá).
- Khi câu hỏi không nêu đủ tên thuốc (vd chỉ "Cordamil"), context gửi cho LLM
  không nhắc rõ đang nói về đúng thuốc nào → model tự mâu thuẫn ("không có
  thông tin cụ thể" rồi liệt kê chi tiết ngay sau). Sửa bằng cách luôn prefix
  context với `"Thông tin thuốc: {ten_thuoc} ({ham_luong})"`.
- So khớp buổi trong ngày ("sáng"/"tối"...) bị lệch dấu: so chuỗi **có dấu**
  (label hiển thị) với chuỗi **đã bị `normalize()` bỏ dấu** → không bao giờ
  khớp. Sửa bằng cách so theo key không dấu, chỉ dùng label có dấu để hiển thị.
- Thuật toán chọn thuốc đại diện cho bệnh án ban đầu chọn `lieu_dung` **ngắn
  nhất** — vô tình ưu tiên chuỗi **rỗng** (0 ký tự, luôn ngắn nhất) và câu
  **chung chung vô nghĩa** ("Tham khảo tờ hướng dẫn sử dụng..."). Sửa bằng
  cách loại các trường hợp đó trước, rồi chọn theo độ dài **gần 120 ký tự**
  thay vì ngắn nhất tuyệt đối.

## Giới hạn đã biết (chưa xử lý trong bản thử nghiệm này)

- `classify_field()`/`is_schedule_query()` chỉ so khớp từ khoá đơn giản,
  không phải NLU thật — câu hỏi diễn đạt khác đi có thể rơi vào nhánh tổng
  quát thay vì đúng field, dù câu trả lời vẫn thường đúng nhờ fallback tổng
  hợp. Bản build thật nên cân nhắc dùng LLM để phân loại intent/field thay vì
  keyword cứng.
- `THOI_DIEM_BY_DANH_MUC` là quy ước tự đặt cho demo, không phải dữ liệu y
  khoa — bản thật bắt buộc lấy `thoi_diem_dung` từ bác sĩ nhập, không được
  suy ra theo `danh_muc`.
- Chưa nối với `prescription-api` thật (đơn/bệnh án vẫn sinh ra trong tiến
  trình chạy, không lưu DB).
- Chưa có audit log (`FEAT-011`) — mọi câu trả lời nên được ghi log đầy đủ khi
  build vào `src/`.
