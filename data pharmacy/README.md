# data pharmacy

Kho dữ liệu thuốc tự tổng hợp (không crawl), tổ chức theo nhóm thuốc, dùng để RAG truy xuất và hiển thị thông tin thuốc cho người dùng.

## Cấu trúc

```
data pharmacy/
  schema.json              <- định nghĩa các trường + mô tả (JSON Schema, dùng chung cho mọi nhóm)
  _template.json           <- bản mẫu trống cho 1 thuốc, copy ra để điền tay nếu muốn
  <Tên nhóm thuốc>/
    raw.md (hoặc raw.txt)  <- nội dung thô, chưa xử lý, có thể chứa nhiều thuốc
    thuoc.json             <- mảng các thuốc trong nhóm, đã map đúng field (dữ liệu dùng cho RAG)
```

Mỗi thư mục con của `data pharmacy/` là 1 nhóm thuốc (vd: `Thuốc cảm lạnh, ho`,
`Thuốc thần kinh`, `Thuốc kháng viêm`, `Thuốc kháng dị ứng`, `Thuốc kháng sinh`...).
Script tự quét mọi thư mục con có chứa `raw.md`/`raw.txt` — không cần khai báo
danh sách nhóm ở đâu cả, cứ tạo thư mục mới là dùng được.

## Cách dùng

1. Trong thư mục nhóm thuốc, tạo/sửa `raw.md`. Mỗi thuốc là 1 khối, gõ theo tiêu đề
   tiếng Việt; giữa 2 thuốc chèn 1 dòng riêng gồm 3 dấu `-` trở lên (`---`):

   ```
   Tên thuốc: ...
   Hàm lượng: ...
   Dạng thuốc: ...
   Tổng số lượng: ...
   Hướng dẫn sử dụng: ...
   Liều dùng: ...
   Đường dùng: ...
   Thời điểm dùng: ...
   Lưu ý đặc biệt:
   - ...
   - ...

   ---

   Tên thuốc: (thuốc thứ 2 trong cùng nhóm)
   ...
   ```

   Tiêu đề không phân biệt hoa/thường hay có dấu/không dấu. Danh sách các tiêu đề
   được nhận diện nằm trong `HEADER_SYNONYMS` ở `scripts/map_drug_data.py`.

2. Chạy:

   ```
   python scripts/map_drug_data.py                          # map tất cả các nhóm
   python scripts/map_drug_data.py --category "Thuốc kháng sinh"   # chỉ map 1 nhóm
   ```

   Script tách `raw.md` thành từng khối theo `---`, map mỗi khối vào đúng field
   theo `schema.json`, tự thêm `id` (slug từ tên thuốc) và `danh_muc` (tên thư
   mục), rồi ghi cả nhóm ra `thuoc.json` (1 JSON array). Nếu thiếu trường bắt
   buộc hoặc gặp tiêu đề không nhận diện được, script in cảnh báo kèm tên thuốc
   để dễ sửa.

3. Nếu không muốn gõ raw text, có thể copy nhiều bản `_template.json`, gộp
   thành 1 array rồi lưu thẳng vào `<nhóm>/thuoc.json`, sau đó chạy
   `python scripts/map_drug_data.py --validate-only` để kiểm tra thiếu trường
   bắt buộc ở tất cả các nhóm.

Không cần API key, không tốn phí — toàn bộ dùng thư viện chuẩn của Python.
