# Report: Crawl thuốc trên Long Châu

**Scripts:** `crawl_longchau.py` (1 trang sản phẩm), `crawl_category.py` (cả 1 danh mục)
**Trang test:** https://nhathuoclongchau.com.vn/thuoc/agiclovir-5-agimexpharm-30338.html
**Output mẫu:** `output.json`

## 1. Cách crawl được sử dụng

**Không dùng Playwright — dùng `requests + BeautifulSoup`.** Lý do:

Trang sản phẩm và trang danh mục của nhathuoclongchau.com.vn đều là **Next.js SSR**
(server-side rendering). Khi kiểm tra HTML trả về từ 1 request `GET` thuần (không chạy JS),
toàn bộ dữ liệu cần thiết đã có sẵn dưới dạng JSON trong thẻ:

```html
<script id="__NEXT_DATA__" type="application/json">{...}</script>
```

Đây chính là `props.pageProps` mà Next.js dùng để hydrate trang ở client. Với trang sản phẩm,
bên trong có `product` (tên, hoạt chất, dạng bào chế, quy cách, danh mục...) và `content`
(các đoạn mô tả dạng HTML: chỉ định, cách dùng/liều dùng, tác dụng phụ, bảo quản, lưu ý...).
Vì dữ liệu đã đầy đủ ngay trong response đầu tiên, chạy trình duyệt thật (Playwright) để
render JS là không cần thiết — chỉ tốn thêm thời gian khởi động browser mà không thu được
thêm dữ liệu nào.

Quy trình cho 1 trang (`crawl_longchau.py`):
1. `requests.get(url)` — 1 request duy nhất, có set `User-Agent` giống trình duyệt thật.
2. `BeautifulSoup` tìm thẻ `<script id="__NEXT_DATA__">`, lấy nội dung, `json.loads()`.
3. Với các field trả về dạng chuỗi HTML lồng bên trong JSON (`dosage`, `usage`, `careful`...),
   dùng `html_fragment_to_sections()` (BeautifulSoup) để tách theo từng thẻ `<h2/h3/h4>` thành
   dict `{tiêu đề: nội dung text}`, rồi `find_section()` tìm value có tiêu đề khớp từ khoá
   (vd tiêu đề chứa "cách dùng" → field `huong_dan_su_dung`, chứa "liều dùng" → `lieu_dung`,
   chứa "chỉ định" → `tac_dung`).

## 2. Nút "Xem thêm"

Trang sản phẩm **có** nút "Xem thêm", nhưng chỉ ở phần **ảnh sản phẩm** và **bình luận** —
không che phần nội dung thuốc. Vì script lấy dữ liệu thẳng từ `__NEXT_DATA__` (nguồn dữ liệu
gốc dùng để render trang) thay vì đọc DOM đã hiển thị, nó **không bị ảnh hưởng bởi bất kỳ
truncate hiển thị (CSS/JS) nào** — dữ liệu lấy được luôn là bản đầy đủ, không cần thao tác
click nào.

## 3. Có dùng API nội bộ không?

**Có, gián tiếp, ở cả 2 script.** `__NEXT_DATA__` chính là kết quả mà `getServerSideProps`
của Next.js đã gọi API nội bộ của Long Châu ở phía server rồi nhúng sẵn vào HTML trả về — đọc
thẻ này tương đương dùng lại chính API đó, nhưng không cần dò ngược endpoint/headers/token
riêng, và không tốn thêm request nào ngoài request tải trang.

Riêng `crawl_category.py` có 1 giới hạn thật sự của API nội bộ (xem mục 6): trang danh mục
SSR chỉ nhúng sẵn tối đa ~12 sản phẩm/lần gọi, phần còn lại chỉ tải được qua API phân trang khi
người dùng cuộn trang thật trên trình duyệt. Script **không** gọi trực tiếp API phân trang đó
(chưa xác định được endpoint/tham số ổn định), mà dùng cách khác — xem mục 6.

## 4. Field lấy được / không lấy được (crawl 1 trang sản phẩm)

| Field | Lấy được? | Nguồn / cách suy ra |
|---|---|---|
| `ten_thuoc` | ✅ | `product.name` (tên ngắn, vd "ACICLOVIR 800MG MEYER..."), chuẩn hoá lại cách viết hoa bằng `normalize_product_name()` — không dùng `webName` vì đó là câu SEO dài kèm công dụng, không phải tên thương mại gọn |
| `ham_luong` | ✅ | `product.ingredient[]`, lọc bỏ tá dược/excipient, ghép `tên hoạt chất + hàm lượng` |
| `dang_thuoc` | ✅ | `product.dosageForm` |
| `tong_so_luong` | ✅ | `product.specification` |
| `tac_dung` | ✅ | tách từ `content.usage`, lấy riêng đoạn "Chỉ định" (bỏ Dược lực học/Dược động học vì đó là kiến thức chuyên sâu, không phải công dụng cho bệnh nhân đọc); fallback lấy nguyên đoạn nếu trang không tách section bằng heading |
| `tac_dung_phu` | ✅ | `content.adverseEffect`, lấy nguyên văn đã làm sạch HTML (field này trên site không tách theo `<h3>` như các field khác) |
| `huong_dan_su_dung` | ✅ | `content.dosage`, đoạn dưới tiêu đề "Cách dùng" |
| `lieu_dung` | ✅ | `content.dosage`, đoạn dưới tiêu đề "Liều dùng" |
| `duong_dung` | ✅ (suy luận có kiểm soát) | **không** lấy trực tiếp từ site (không có field riêng) — suy ra từ `dang_thuoc` qua bảng từ khoá cố định `ROUTE_KEYWORDS` (vd "mỡ/kem/gel/bôi" → "Bôi ngoài da", "tiêm" → "Tiêm"...), mặc định "Uống" nếu không khớp từ khoá nào. Đây là ánh xạ dựa trên 1 field có cấu trúc sẵn (`dang_thuoc`), không phải đoán từ văn bản mô tả tự do |
| `thoi_diem_dung` | ❌ để `""` | Long Châu không có field/section riêng cho thời điểm dùng (trước/sau ăn...). Đây là dữ liệu thuộc về đơn thuốc bác sĩ kê cho từng bệnh nhân cụ thể — khác nguồn hoàn toàn với các field còn lại (dữ liệu tham chiếu chung của thuốc), nên **luôn** để trống dù trang có hay không có thông tin này |
| `huong_dan_bao_quan` | ✅ | `content.preservation` |
| `luu_y_dac_biet` | ✅ | tách `content.careful` theo từng `<h3>` (Chống chỉ định, Thận trọng khi sử dụng, Khả năng lái xe..., Thời kỳ mang thai, Thời kỳ cho con bú, Tương tác thuốc...) + `product.warning[]` |
| `id` | ✅ (tự sinh) | Slug hoá từ `product.name` (tên ngắn, không dấu, nối bằng `-`) |
| `danh_muc` | ✅ | `product.categories[-1].name` (danh mục cụ thể nhất), fallback `breadcrumbs` nếu thiếu |

**Lưu ý về validate:** `schema.json` liệt kê `thoi_diem_dung` là field **bắt buộc**, nhưng
crawler luôn để trống field này (lý do ở trên) — nghĩa là mọi bản ghi do crawler tạo ra sẽ
luôn bị `validate_record()` báo "thiếu trường bắt buộc: thoi_diem_dung". Đây là cảnh báo
**biết trước, không phải lỗi** — chỉ để nhắc rằng field này cần được bổ sung thủ công sau, từ
đơn thuốc thật, không phải từ dữ liệu crawl.

## 5. Đánh giá khả năng mở rộng — crawl 1 trang

- Toàn bộ trang `/thuoc/*.html` dùng chung 1 template Next.js, nên cấu trúc
  `__NEXT_DATA__.props.pageProps.product` / `.content` gần như chắc chắn giữ nguyên schema cho
  mọi sản phẩm thuộc danh mục "Thuốc" — chỉ cần đổi URL đầu vào là chạy được ngay.
- Việc tách section theo tiêu đề (`html_fragment_to_sections`) là generic, không hardcode tiêu
  đề của riêng sản phẩm mẫu, nên vẫn hoạt động khi sản phẩm khác có bộ tiêu đề khác (thêm/bớt
  vài mục).
- **Rủi ro:** các danh mục ngoài "Thuốc" (thực phẩm chức năng, dụng cụ y tế, mỹ phẩm...) có thể
  dùng field set khác trong `product` (vd thiếu `dosageForm`/`ingredient`) — code đã có
  `.get(..., "")` fallback nhưng chưa test thực tế trên các danh mục này. Nếu Long Châu đổi tên
  field trong `__NEXT_DATA__`, script sẽ trả rỗng hàng loạt mà không tự báo lỗi rõ ràng — nên
  dựa vào cảnh báo "thiếu trường bắt buộc" của `validate_record()` để phát hiện sớm.

## 6. Crawl cả 1 danh mục (`crawl_category.py`)

**Vấn đề:** trang danh mục cũng là Next.js SSR, nhưng `__NEXT_DATA__` chỉ nhúng sẵn **tối đa
~12 sản phẩm đầu tiên** (`initTotalProducts` có thể lên đến 80-90). Phần còn lại chỉ tải được
qua 1 API nội bộ khi người dùng cuộn trang thật trên trình duyệt — không gọi thẳng bằng
`requests` được (chưa xác định được endpoint/tham số ổn định của API phân trang này).

**Cách giải quyết — không dùng API phân trang, không giả lập browser:** trang danh mục có sẵn
các bộ lọc hiển thị bên trái (thương hiệu, đối tượng sử dụng, nước sản xuất, chỉ định, thành
phần...). Mỗi bộ lọc áp dụng **server-side** và làm `initTotalProducts` giảm xuống đúng số sản
phẩm khớp lọc đó. Nếu 1 giá trị lọc cho ra ≤ 12 sản phẩm, SSR trả về **đầy đủ** nhóm đó. Vì 1
danh mục thường có vài chục giá trị lọc trải đều trên số sản phẩm, hợp toàn bộ các nhóm nhỏ lại
gần như luôn phủ được toàn bộ danh mục mà không cần gọi API riêng nào.

Tham số query cho từng loại filter được xác định bằng thử nghiệm thực tế (không suy ra được từ
tên field trả về), map cố định trong `FILTER_QUERY_KEYS`:

| code (từ `filterAttributes`) | tham số query |
|---|---|
| `prescription` | `thuoc-ke-don` |
| `objectUse` | `doi-tuong-su-dung` |
| `manufactor` | `nuoc-san-xuat` |
| `indications` | `chi-dinh` |
| `brand` | `thuong-hieu` |
| `brandOrigin` | `xuat-xu-thuong-hieu` |
| `ingredient` | `thanh-phan` |

`priceSystem` chưa xác định được đúng format tham số nên không nằm trong danh sách — nếu 1 số
sản phẩm chỉ lọc được qua `priceSystem` (không trùng giá trị lọc nào khác), chúng sẽ bị thiếu.

Quy trình:
1. `discover_products()` — gọi trang gốc + lần lượt từng giá trị của từng filter đã biết tham
   số, gộp kết quả theo `sku` (loại trùng tự nhiên vì dùng dict). In cảnh báo nếu 1 giá trị lọc
   vẫn > 12 sản phẩm (khả năng còn sót) hoặc tổng số gom được < `initTotalProducts` ban đầu.
2. `crawl_details()` — với từng sản phẩm tìm được, gọi lại đúng `extract_fields()` dùng chung
   với `crawl_longchau.py` (import trực tiếp, không lặp code) để lấy đầy đủ field.
3. Có delay ngẫu nhiên 1.2-2.2s giữa các request (`polite_sleep`) và retry tối đa 3 lần với
   backoff khi lỗi mạng/parse, để giảm rủi ro bị chặn khi crawl số lượng lớn trang.
4. Tự sinh `id`, chống trùng slug trong cùng 1 lần crawl (thêm hậu tố `-2`, `-3`...), gán
   `danh_muc` theo tham số `--danh-muc` truyền vào (không dùng lại `danh_muc` mà
   `extract_fields()` tự suy ra từ từng trang, để đảm bảo mọi thuốc trong file cùng 1 tên danh
   mục thống nhất theo tên thư mục output).
5. Ghi toàn bộ ra 1 file `thuoc.json` (JSON array) trong đúng thư mục nhóm của `data pharmacy/`.

## 7. Đánh giá khả năng mở rộng — crawl cả danh mục

- **Không đảm bảo phủ 100%** sản phẩm trong danh mục — chỉ là "gần như luôn đủ" nhờ hợp nhiều
  bộ lọc nhỏ. Script tự log cảnh báo khi tổng số gom được < `initTotalProducts`, nên biết được
  ngay có thiếu hay không sau mỗi lần chạy, nhưng không tự động vá phần thiếu.
- Nếu Long Châu thêm loại filter mới (code mới trong `filterAttributes`) mà chưa có trong
  `FILTER_QUERY_KEYS`, filter đó bị bỏ qua hoàn toàn (không lỗi, chỉ không dùng để gom sản
  phẩm) — cần bổ sung tham số query bằng tay (thử nghiệm thực tế) khi mở rộng sang danh mục có
  filter mới, ví dụ `priceSystem` hiện chưa map được.
- Áp dụng được cho mọi danh mục con của `/thuoc/...` mà không cần sửa code, chỉ cần đổi
  `category_url` và `--danh-muc`; danh mục có nhiều filter đa dạng (nhiều thương hiệu/nước SX)
  sẽ có tỉ lệ phủ tốt hơn danh mục ít filter.
- Vì `crawl_details()` gọi lại `extract_fields()` giống hệt crawl 1 trang, mọi ưu điểm/hạn chế
  ở mục 4-5 (field `thoi_diem_dung` luôn trống, rủi ro đổi schema `__NEXT_DATA__`...) áp dụng
  y hệt cho từng sản phẩm trong danh mục.
- Thời gian crawl tỉ lệ với (số giá trị filter + số sản phẩm) × ~1.5s delay — với danh mục vài
  chục sản phẩm và vài chục giá trị lọc, tổng thời gian có thể lên tới vài phút; nên cân nhắc
  chạy nền (background) khi crawl danh mục lớn.
