# Report: Crawl trang thuốc Long Châu

**Trang crawl:** https://nhathuoclongchau.com.vn/thuoc/agiclovir-5-agimexpharm-30338.html
**Script:** `crawl_longchau.py`
**Output:** `output.json`

## 1. Cách crawl được sử dụng

**Không dùng Playwright — dùng `requests + BeautifulSoup`.** Lý do:

Trang chi tiết sản phẩm của nhathuoclongchau.com.vn là **Next.js SSR** (server-side rendering).
Khi kiểm tra HTML trả về từ 1 request `GET` thuần (không chạy JS), toàn bộ dữ liệu sản
phẩm đã có sẵn dưới dạng JSON trong thẻ:

```html
<script id="__NEXT_DATA__" type="application/json">{...}</script>
```

Đây chính là `props.pageProps` mà Next.js dùng để hydrate trang ở client — bên trong có
`product` (thông tin sản phẩm: tên, hoạt chất, dạng bào chế, quy cách, danh mục...) và
`content` (các đoạn mô tả dạng HTML: cách dùng/liều dùng, tác dụng phụ, bảo quản, lưu ý...).
Vì dữ liệu đã đầy đủ ngay trong response đầu tiên (verify bằng cách so khớp: tên sản phẩm,
đoạn "Cách dùng"... xuất hiện y hệt trong cả `__NEXT_DATA__` lẫn phần HTML hiển thị), việc
chạy trình duyệt thật (Playwright) để render JS là không cần thiết — chỉ tốn thêm thời gian
khởi động browser mà không thu được thêm dữ liệu nào.

Quy trình:
1. `requests.get(url)` — 1 request duy nhất, có set `User-Agent` giống trình duyệt thật.
2. `BeautifulSoup` tìm thẻ `<script id="__NEXT_DATA__">`, lấy nội dung, `json.loads()`.
3. Với các field trả về dạng chuỗi HTML lồng bên trong JSON (`dosage`, `careful`,
   `preservation`...), tiếp tục dùng `BeautifulSoup` để tách theo từng thẻ `<h3>` thành
   dict `{tiêu đề: nội dung text}`, rồi map vào đúng field theo tên tiêu đề (vd tiêu đề
   chứa "cách dùng" → field `huong_dan_su_dung`, chứa "liều dùng" → field `lieu_dung`).

## 2. Nút "Xem thêm"

Trang này **có** nút "Xem thêm", nhưng chỉ xuất hiện ở phần **ảnh sản phẩm** ("Xem thêm 5 ảnh")
và **bình luận** ("Xem thêm 5 bình luận") — không che phần nội dung thuốc (mô tả, cách dùng,
lưu ý...). Quan trọng hơn: vì script lấy dữ liệu thẳng từ `__NEXT_DATA__` (nguồn dữ liệu gốc
dùng để render trang) thay vì đọc DOM đã hiển thị, nó **không bị ảnh hưởng bởi bất kỳ truncate
hiển thị (CSS/JS) nào** — dù trang có ẩn bớt nội dung bằng nút "Xem thêm" ở phần mô tả hay
không, dữ liệu lấy được luôn là bản đầy đủ. Do đó script không cần thao tác click nào.

## 3. Có dùng API nội bộ không?

**Có, gián tiếp.** `__NEXT_DATA__` chính là kết quả mà `getServerSideProps` của Next.js đã gọi
API nội bộ của Long Châu ở phía server rồi nhúng sẵn vào HTML trả về — nên đọc thẻ này tương
đương với việc dùng lại chính API đó, nhưng có 2 lợi thế:
- Không cần dò ngược endpoint/headers/token xác thực riêng (API nội bộ thường có thể bị đổi,
  chặn theo origin, hoặc yêu cầu header đặc biệt).
- Không tốn thêm request nào — dữ liệu đã có sẵn trong lần tải trang đầu tiên.

Script không tự gọi lại 1 endpoint API riêng biệt nào của Long Châu.

## 4. Field lấy được / không lấy được

| Field output.json | Lấy được? | Nguồn trong `__NEXT_DATA__` |
|---|---|---|
| `ten_thuoc` | ✅ | `product.webName` |
| `ham_luong` | ✅ | `product.ingredient[]` (lọc bỏ tá dược/excipient, ghép `tên hoạt chất + hàm lượng`) |
| `dang_thuoc` | ✅ | `product.dosageForm` |
| `tong_so_luong` | ✅ | `product.specification` |
| `huong_dan_su_dung` | ✅ | `content.dosage`, đoạn dưới tiêu đề "Cách dùng" |
| `lieu_dung` | ✅ | `content.dosage`, đoạn dưới tiêu đề "Liều dùng" |
| `duong_dung` | ❌ để `""` | Không có field riêng cho "đường dùng" trên trang; thông tin này chỉ nằm lẫn trong câu văn tự do ở "Cách dùng" ("Thuốc mỡ dùng bôi ngoài") — không tách ra vì đề bài yêu cầu không tự suy diễn từ văn bản tự do |
| `thoi_diem_dung` | ❌ để `""` | Không có field/section nào cho "thời điểm dùng" (trước/sau ăn...) — sản phẩm này là thuốc bôi ngoài da nên khái niệm này không áp dụng |
| `huong_dan_bao_quan` | ✅ | `content.preservation` |
| `luu_y_dac_biet` | ✅ | `content.careful` (tách theo từng `<h3>`: Chống chỉ định, Thận trọng khi sử dụng, Khả năng lái xe..., Thời kỳ mang thai, Thời kỳ cho con bú, Tương tác thuốc) + `product.warning[]` |
| `id` | ✅ (tự sinh) | Slug hoá từ `product.name` (tên ngắn, không dấu, nối bằng `-`) |
| `danh_muc` | ✅ | `product.categories[-1].name` (danh mục cụ thể nhất, fallback `breadcrumbs` nếu thiếu) |

Không có field nào bị bỏ trống do lỗi crawl — 2 field để `""` là do **trang nguồn thực sự
không có dữ liệu tách biệt cho field đó**, đúng theo quy tắc "không tự suy diễn" của đề bài.

## 5. Đánh giá khả năng mở rộng sang các trang thuốc khác

**Khả năng mở rộng tốt, với một vài lưu ý:**

- Toàn bộ site nhathuoclongchau.com.vn dùng chung 1 template Next.js cho trang `/thuoc/*.html`,
  nên cấu trúc `__NEXT_DATA__.props.pageProps.product` / `.content` gần như chắc chắn giữ
  nguyên schema cho mọi sản phẩm thuộc danh mục "Thuốc" — script hiện tại chỉ cần đổi URL đầu
  vào (`python crawl_longchau.py <url-khac>`) là chạy được ngay, không cần sửa code.
- Việc tách section theo tiêu đề `<h3>` (`html_fragment_to_sections`) là generic — không
  hardcode tiêu đề cụ thể của sản phẩm này, nên vẫn hoạt động với sản phẩm có bộ tiêu đề khác
  (vd thêm "Cho con bú", "Tương tác thuốc" hoặc thiếu bớt 1 vài mục).
- **Rủi ro cần lưu ý khi mở rộng:**
  - Các danh mục khác ngoài "Thuốc" (thực phẩm chức năng, dụng cụ y tế, mỹ phẩm...) có thể
    dùng field set khác trong `product` (vd không có `dosageForm`/`ingredient`) — cần fallback
    `.get(..., "")` như đã làm, nhưng nên test thêm trên vài trang mẫu trước khi chạy hàng loạt.
  - Nếu Long Châu đổi tên field trong `__NEXT_DATA__` (đổi phiên bản frontend) thì script sẽ
    trả về rỗng hàng loạt — nên có bước validate/log cảnh báo khi field bắt buộc trống, tương
    tự cách `data pharmacy/scripts/map_drug_data.py` đang làm với `schema.json`.
  - Cần thêm rate-limit/delay giữa các request nếu crawl số lượng lớn trang, để tránh bị chặn
    IP — script hiện tại (crawl 1 trang) chưa cần việc này.
- Để crawl hàng loạt, chỉ cần bọc `fetch_next_data` + `extract_fields` trong vòng lặp qua danh
  sách URL (vd lấy từ trang danh mục `/thuoc/...`), không cần thay đổi kiến trúc.
