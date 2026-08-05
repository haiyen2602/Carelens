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
| `huong_dan_su_dung` | ✅ | `content.dosage`, đoạn dưới tiêu đề "Cách dùng"; fallback lấy nguyên đoạn nếu trang không tách section bằng heading (xem mục 8.1) |
| `lieu_dung` | ✅ | `content.dosage`, đoạn dưới tiêu đề "Liều dùng" |
| `duong_dung` | ✅ (suy luận có kiểm soát) | **không** lấy trực tiếp từ site (không có field riêng) — suy ra từ `dang_thuoc` qua bảng từ khoá cố định `ROUTE_KEYWORDS` (vd "mỡ/kem/gel/bôi" → "Bôi ngoài da", "tiêm" → "Tiêm"...). **Không còn mặc định "Uống"** khi không khớp từ khoá nào (xem mục 8.3) — chỉ trả "Uống" khi khớp 1 trong các từ khoá xác nhận dương tính (`ORAL_KEYWORDS`: viên/uống/siro/cốm/hoàn), còn lại để trống để `validate_record()` bắt lỗi thay vì khẳng định sai |
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
4. Tự sinh `id`, chống trùng id trong cùng 1 lần crawl (thêm hậu tố `-2`, `-3`...). Mặc định
   **giữ nguyên** `danh_muc` mà `extract_fields()` tự suy ra riêng cho từng sản phẩm
   (`product.categories[-1].name` — danh mục con cụ thể nhất của chính trang đó), để 1 thư mục
   output có thể gộp nhiều danh mục con nhỏ của site (vd thư mục `Thuốc tim mạch và máu/` chứa
   cả `Thuốc chống đông máu`, `Thuốc trị mỡ máu`, `Thuốc tăng cường tuần hoàn não`...) mà mỗi
   thuốc vẫn giữ đúng phân loại riêng của nó. Chỉ khi truyền cờ `--danh-muc-co-dinh` thì mới ép
   `danh_muc` của **mọi** thuốc về đúng 1 giá trị `--danh-muc` (dùng khi thư mục output tương
   ứng 1-1 với 1 danh mục duy nhất của site, không cần tách nhỏ thêm).
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
- Thời gian crawl tỉ lệ với (số giá trị filter + số sản phẩm) × ~1.5-3s delay — với danh mục vài
  trăm sản phẩm (vd "Thuốc tim mạch và máu" ~1000 SP), tổng thời gian có thể lên tới 15-20 phút;
  nên cân nhắc chạy nền (background) khi crawl danh mục lớn.

## 8. Các lỗi đã phát hiện và sửa (qua PR review, 2026-08-04)

Sau khi crawl thật 4 danh mục (kháng virus, kháng sinh, kháng nấm→điều trị ung thư, tim mạch và
máu — tổng ~1470 sản phẩm) và đưa lên PR review, phát hiện 3 lỗi thực tế trong code (không phải
lỗi giả định) — dưới đây là mô tả và cách sửa, để biết code hiện tại **đã đáng tin hơn** ở
những điểm nào so với bản đầu.

### 8.1. Mất dữ liệu âm thầm khi trang không dùng heading `<h2/h3/h4>`

`html_fragment_to_sections()` chỉ tách được section khi HTML có thẻ heading. Một số trang sản
phẩm viết `dosage`/`usage` thành 1 đoạn văn liền, không có heading — trước khi sửa, các field
này bị bỏ trống hoàn toàn dù nội dung vẫn có trong HTML. Xác nhận bằng số liệu thật: 28 sản phẩm
(rải rác ở 3 danh mục lớn) bị thiếu `huong_dan_su_dung`/`lieu_dung`/`tac_dung` theo kiểu này.

**Sửa:** nếu không tách được section nào, lấy nguyên đoạn text đã làm sạch HTML thay vì bỏ trống
— áp dụng cho cả `tac_dung` (dồn vào 1 field) và `huong_dan_su_dung` (không tách được "cách
dùng" khỏi "liều dùng" từ 1 đoạn không heading nên chỉ dồn vào `huong_dan_su_dung`, để
`lieu_dung` trống thay vì trùng lặp nội dung ở cả 2 field).

Ngoài ra còn 1 biến thể của lỗi này: 1 số heading chứa `\xa0` (non-breaking space) giữa các từ
(vd `"Chỉ\xa0định"`), khiến so khớp từ khoá theo khoảng trắng thường thất bại. Sửa bằng cách gom
mọi loại whitespace (kể cả `\xa0`) về 1 khoảng trắng chuẩn trong `strip_diacritics()`.

### 8.2. `tra mắt` bị phân loại nhầm thành "Bôi ngoài da"

`classify_duong_dung()` chỉ có từ khoá `"mo"` (mỡ) map sang "Bôi ngoài da", nên dạng bào chế
`"Thuốc mỡ tra mắt"` (thuốc tra mắt, không phải bôi da) bị gán sai route. Sửa bằng cách thêm từ
khoá `"tra mat"` → `"Nhỏ mắt"`, kiểm tra **trước** từ khoá `"mo"` chung chung.

### 8.3. Mặc định "Uống" cho mọi dạng bào chế không nhận diện được — rủi ro dữ liệu y tế sai

Đây là lỗi nghiêm trọng nhất trong 3 lỗi: bản gốc `classify_duong_dung()` trả về `"Uống"` cho
**bất kỳ** `dang_thuoc` nào không khớp từ khoá đặc thù nào (tiêm/đặt/bôi/nhỏ...) — tức là khẳng
định 1 đường dùng cụ thể dựa trên "loại trừ", không phải bằng chứng thật. Nguy hiểm hơn thiếu dữ
liệu, vì thiếu thì còn biết mà kiểm tra, còn sai mà không ai để ý thì có thể gây nhầm lẫn thật
(vd tưởng thuốc uống được trong khi thực chất là dạng khác).

**Sửa:** đảo logic — chỉ trả `"Uống"` khi khớp 1 từ khoá xác nhận dương tính (`ORAL_KEYWORDS`:
`vien`, `uong`, `siro`, `com`, `hoan`). Nếu không khớp bất kỳ từ khoá nào (route đặc thù lẫn
oral), trả về `""` — để `validate_record()` tự báo thiếu trường bắt buộc, buộc review thủ công
thay vì âm thầm sai. Đã verify với toàn bộ ~90 giá trị `dang_thuoc` thực tế xuất hiện trong 4
danh mục đã crawl; chỉ còn 9 sản phẩm (dạng `"Dạng bột"`, `"Hỗn dịch"` không kèm từ "uống"/"tiêm"
— thật sự mơ hồ ngay cả với người đọc) bị để trống thay vì đoán.

### 8.4. Chống chặn khi crawl danh mục lớn

`crawl_category.py` bổ sung `CHECKPOINT_PAUSE` — sau mỗi `CHECKPOINT_EVERY = 20` request, nghỉ
thêm 8-15s (ngoài delay ngẫu nhiên 1.5-3s mỗi request) — tránh gửi request đều đặn hàng trăm lần
liên tục, 1 pattern dễ bị WAF/rate-limit phát hiện khi crawl danh mục vài trăm-nghìn sản phẩm.

### 8.5. Kết quả sau khi sửa + dọn dữ liệu

Chạy lại phát hiện + crawl có mục tiêu (không crawl lại toàn bộ) để backfill 20/28 sản phẩm ở
mục 8.1 bằng dữ liệu đúng; 8 sản phẩm còn thiếu 1 trong 2 field `huong_dan_su_dung`/`lieu_dung`
sau backfill là do **trang nguồn thật sự chỉ có 1 trong 2 mục con đó** (không phải bug nữa). Sau
đó loại bỏ toàn bộ sản phẩm còn thiếu bất kỳ field bắt buộc nào (trừ `thoi_diem_dung`, luôn để
trống theo thiết kế — xem mục 4) khỏi dữ liệu đã ship, để đảm bảo mọi bản ghi trong
`data pharmacy/*/thuoc.json` đều đầy đủ field. Kết quả: 1469 → 1418 sản phẩm hoàn chỉnh trên 4
danh mục.
