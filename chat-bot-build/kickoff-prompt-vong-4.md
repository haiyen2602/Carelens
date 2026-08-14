# Kickoff Prompt — Vòng 4: Intent routing, Fuzzy search 2 tầng, match triệu chứng, tóm tắt hội thoại, soul.md

> Dán cho agent coding, cùng quy ước như 3 file trước. Vòng này bắt nguồn từ 3 nguồn: (a) 4 đề xuất cải thiện
> PM đưa ra sau khi vòng 3 hoàn tất và deploy (không phải bug, là nâng cấp chất lượng có chủ đích), (b) 2
> phát hiện thật từ live-testing (tin nhắn nhiều ý định bị bỏ sót phần lớn, câu không liên quan bị đẩy nhầm
> sang tìm thuốc), và (c) phân tích trực tiếp `audit_log` thật (2008 bản ghi) — xác nhận bằng số liệu thay vì
> suy đoán.

---

## 0. Cập nhật `chatbot-rag-design.md` trước khi code

Ghi các quyết định dưới đây vào mục 10 (tiếp số từ số hiện có trong bảng — xác nhận số chính xác lúc đọc
doc, không đoán), giữ nguyên style đã dùng — không đánh số lại các mục cũ.

---

## 0.5. ĐÃ ĐIỀU TRA, ĐÓNG — KHÔNG CẦN SỬA `safety_layer`

Nghi ngờ ban đầu (từ phân tích `audit_log` — 64 bản ghi khớp câu "uống quá liều panadol thì có nguy hiểm
không") **không phải khoảng hở an toàn thật**. Nguyên nhân: dữ liệu phân tích trải qua mốc deploy fix vòng 3
mục 3 (2026-08-12) mà không lọc theo thời gian trước khi kết luận.

**Bằng chứng đóng (ghi vào `chatbot-rag-design.md` mục 10, không xoá dấu vết):**
- 64 bản ghi TRƯỚC 12/08 → `keyword_hit=false, llm_flag=false` — đúng bug gốc vòng 3 (lúc đó
  `check_safety()` gọi không kèm `llm_classifier`), **đã sửa từ trước, không phải phát hiện mới**.
- 12 bản ghi SAU 12/08, cùng câu hỏi y hệt → `llm_flag=true, level='Nguy hiểm', category='dosage_risk'`,
  đầy đủ escalate. 0/12 lọt.
- Quét rộng mọi bản ghi sau 12/08 chứa "nguy hiểm"/"quá liều"/"an toàn"/"có sao không" → 0 case lọt.
- Gọi trực tiếp `classify_safety_llm()` (live, OpenAI thật) với 4 biến thể câu hỏi giả định → cả 4 đúng
  `Nguy hiểm`/`dosage_risk` với prompt hiện tại trong repo.

**Việc cần làm — không phải sửa code, mà khoá lại bằng regression test:**
Thêm 4 câu đã verify (panadol, paracetamol, aspirin, câu chung chung "nếu tôi lỡ uống quá liều thuốc thì
sao") vào `eval/safety_llm_check.py` làm case cố định — không phải vì đang lỗi, mà để tránh tái phát khi
mục 2 (sửa `intent_classification`) hoặc bất kỳ thay đổi model/prompt nào sau này vô tình làm hỏng lại đúng
pattern câu hỏi giả định này.

---

## 1. Bối cảnh

6 việc, ưu tiên theo mức độ nền tảng — việc ảnh hưởng tới tầng định tuyến gốc (mục 2) làm trước, vì nó ảnh
hưởng tới mọi luồng phía sau:

1. Điều tra + sửa `intent_classification` — câu hoàn toàn không liên quan tới thuốc bị lọt vào luồng tìm
   thuốc (phát hiện thật khi thử tay: "tôi buồn đi vệ sinh" → bot hỏi xác nhận 1 loại thuốc ngẫu nhiên).
2. Thay cơ chế tìm ứng viên thuốc ở §5.2 (vòng 2) từ hybrid search (vector+lexical+RRF) sang fuzzy 2 tầng —
   đúng bản chất hơn cho việc định danh tên riêng, và có thể liên quan trực tiếp tới #14 (còn treo từ vòng
   2 — chưa rõ vì sao `tac_dung_phu` xếp hạng thấp hơn field_group khác cùng thuốc).
3. Match triệu chứng bệnh nhân báo cáo với `tac_dung_phu` của thuốc trong đơn — hỗ trợ bác sĩ suy đoán
   nguyên nhân, không phải kết luận tự động cho bệnh nhân. Bao gồm cả việc đảm bảo audit log ghi đủ ngữ cảnh
   khi 1 tin nhắn chứa nhiều ý định (xem mục 3.4 — đánh số theo mục con của mục 4, xem chi tiết bên dưới).
4. Tóm tắt hội thoại theo giờ — tầng giữa giữa ngữ cảnh ngắn hạn 15 phút (§7.2 vòng 3) và tra cứu dài hạn
   theo yêu cầu (§7.3 vòng 3), không tự động bơm vào câu trả lời.
5. `soul.md` — hình thức hoá persona Capy (mục 9 vòng 3) thành 1 file riêng, dễ bảo trì.
6. (Ghi nhận, không build trong vòng này) Multi-intent xử lý đầy đủ — xem mục 1.1.

### 1.1. Vấn đề đã biết nhưng CHƯA build trong vòng này: tin nhắn nhiều ý định trong 1 lượt

Phát hiện thật: 1 tin nhắn chứa nhiều yêu cầu khác nhau (vd hỏi lịch hôm nay + hỏi lịch buổi tối + báo
triệu chứng + hỏi 1 câu redflag) — hệ thống hiện chỉ xử lý được 1 ý định/lượt (`intent_classification` trả
về đúng 1 nhãn), nên chỉ phần nghiêm trọng nhất (redflag) được xử lý, các phần còn lại biến mất hoàn toàn
khỏi cả response lẫn trace.

**Điều không đổi**: redflag vẫn phải chiếm ưu tiên tuyệt đối, cắt ngang bất kỳ lúc nào (đúng thiết kế mục 8,
vòng 2/3) — không làm yếu phần này để cố trả lời hết mọi thứ trong 1 lượt.

**Điều cần sửa ngay trong vòng này (rẻ)**: audit log phải ghi đủ ngữ cảnh dù response chỉ nói 1 phần — xem
mục 4.4.

**Điều để dành vòng sau (việc lớn, không build ở đây)**: multi-intent đầy đủ — trích xuất nhiều ý định từ 1
tin nhắn, xử lý theo thứ tự ưu tiên (an toàn trước), ghép hoặc tuần tự trả lời từng phần. Đây là thay đổi
kiến trúc lớn (đổi `intent_classification` từ đơn nhãn sang đa nhãn, đổi cách điều phối downstream node),
cần thiết kế riêng, không bolt-on vào vòng này.

### 1.2. Không phải code — kiểm tra dữ liệu trước

Phát hiện khi phân tích `audit_log`: câu hỏi *"uống quá liều panadol thì có nguy hiểm không"* (chạy lặp lại
~47 lần, dạng test "legit medical question") — **100% ra `no_candidates_at_all`**, kể cả qua `hybrid_search`
cũ (có embedding, không chỉ fuzzy). "Panadol" là 1 brand paracetamol rất phổ biến ở Việt Nam — 0% tìm được
ở mọi thuật toán gợi ý đây nhiều khả năng là **thiếu dữ liệu gốc** (không có trong 3562 thuốc crawl từ Long
Châu), không phải lỗi thuật toán search.

**Việc cần làm trước khi đổ lỗi cho thuật toán**: `SELECT * FROM drug_chunks WHERE ten_thuoc_unaccent ILIKE
'%panadol%'` để xác nhận. Nếu xác nhận thiếu — đây là việc của nhóm thu thập dữ liệu (bổ sung brand phổ
biến còn thiếu), **không phải việc sửa code trong vòng 4**, không giao cho agent coding "sửa" nhầm.

---

## 2. Sàn độ tin cậy cho `_search_distinct_drug_candidates()` — sửa đúng chỗ 2 nhánh reply-parsing tin mù kết quả search

**ĐÃ ĐIỀU TRA, ĐỔI HƯỚNG HOÀN TOÀN** — root cause KHÔNG nằm ở `intent_classification` như bản kickoff gốc
nghi ngờ. Bằng chứng: gọi trực tiếp `classify_intent()` (prompt hiện tại) với đúng câu bug + 4 câu
out-of-scope khác → 5/5 đúng `greeting`, confidence 0.9-0.95. `intent_classification` đã được sửa đúng
nguyên tắc chung từ vòng 3 (#25 trong design doc) — không cần sửa lại, xoá bỏ toàn bộ kế hoạch sửa prompt
đã ghi trong bản kickoff trước.

### 2.0. Trước khi giữ lại bất kỳ phần nào của kế hoạch cũ — re-verify bằng chứng, không tin dữ liệu cũ

Bài học từ mục 0.5 (đóng vì dữ liệu `audit_log` phân tích trải qua mốc fix mà không lọc theo thời gian) áp
dụng lại y hệt ở đây: phát hiện "`intent_classification` đã sửa từ #25" đặt dấu hỏi cho chính bằng chứng
"9/9 case confidence <0.8 đều sai" đã dùng để đề xuất ngưỡng confidence trước đó.

**Việc cần làm trước**: lọc lại đúng 9 case đó theo thời gian, đối chiếu với mốc deploy #25. Nếu toàn bộ 9
case đều xảy ra **trước** #25 — bỏ hẳn ý tưởng ngưỡng confidence cho `intent_classification` (không phải sai
nguyên tắc, chỉ là không còn bằng chứng thật ủng hộ trên code hiện tại). Nếu có case **sau** #25 vẫn confidence
thấp và sai — giữ lại ý tưởng này như 1 lớp phòng vệ phụ, ưu tiên thấp hơn mục 2.1 bên dưới.

### 2.1. Root cause thật — tái hiện được, có bằng chứng cụ thể

Cơ chế: khi bệnh nhân có `pending_drug_confirmation` treo (đang giữa luồng xác nhận thuốc từ lượt trước) —
`chat_routes.py` bỏ qua `intent_classification` hoàn toàn theo đúng thiết kế đã có (mục 11, vòng 2), ép cứng
`intent="drug_info"`. Đây không phải bug, là thiết kế cố ý.

Bug thật nằm ở 2 nhánh xử lý reply trong luồng đó — `STAGE_IN_RX_AWAITING_NEW_NAME`/
`STAGE_OUT_RX_AWAITING_REDESCRIBE` (khi bot đã hỏi "cho tôi tên thuốc khác"/"mô tả lại giúp mình") — coi
**bất kỳ văn bản nào** người dùng gõ tiếp theo là tên/mô tả thuốc mới, không kiểm tra gì trước khi đưa vào
`_search_distinct_drug_candidates()`. Hàm này (embedding-based, cùng hàm sẽ làm fallback reflexion vòng 2 ở
mục 3.3 bên dưới) trên 1 corpus không rỗng **luôn trả về "gần nhất"**, bất kể có liên quan hay không (đúng
#15) — 2 nhánh trên tin tưởng mù quáng kết quả đó, không có bước lọc nào.

Tái hiện trực tiếp:
```
'tôi buồn đi vệ sinh'  -> [{'drug_id': 'coveram-10-5-30v', ...}]    ← khớp đúng bug đã báo cáo
'tôi thích ăn phở'     -> [{'drug_id': 'bisoloc-5mg-united-3x10', ...}]  ← cũng sai
'hôm nay trời đẹp quá' -> []                                        ← case này đúng, không match
```

### 2.2. ĐÃ ĐIỀU TRA — không phải bài toán chỉnh ngưỡng, đổi hướng sang LLM gate hẹp

Test thật trên cả 3 kênh (lexical `word_similarity` trên `noi_dung`, vector `NGUONG_VECTOR`, name-similarity
trên `ten_thuoc`) — **không kênh nào, ở bất kỳ ngưỡng nào, tách sạch được** câu hợp lệ (tên/mô tả thuốc)
khỏi câu vô nghĩa. Bằng chứng: lexical bị nhiễu bởi prefix lặp lại ("Thuốc: ... — danh_mục") khiến câu vô
nghĩa khớp giả tạo cao hơn cả câu hợp lệ; vector đúng với câu vô nghĩa (0 match) nhưng cũng từ chối luôn câu
hợp lệ dạng chỉ có tên ngắn (ngưỡng 0.60 tune cho câu hỏi đầy đủ, không hợp bối cảnh reply ngắn).

**Nguyên nhân gốc**: cơ chế **OR** giữa 2 kênh (đúng cho RAG retrieval — ưu tiên không bỏ sót, đã chốt từ
vòng 1) ở ngữ cảnh này cộng dồn nhược điểm cả 2 chiều — lexical sai theo hướng thừa (nhận nhầm) vẫn lọt qua
vì OR chỉ cần 1 kênh đồng ý, vector đúng theo hướng từ chối nonsense không cứu được gì vì logic OR không
quan tâm kênh kia nói không. Đây là 2 bài toán khác bản chất: RAG retrieval cần recall (đừng bỏ sót), cổng
lọc reply ở đây cần precision (đừng nhận nhầm) — cùng 1 cơ chế đúng chỗ này lại sai chỗ khác.

**Hướng sửa mới, thay hoàn toàn cho việc "siết ngưỡng"**: thêm 1 lớp LLM gate hẹp phạm vi, chạy **trước khi
search**, chỉ trả lời nhị phân "văn bản này có vẻ là tên/mô tả thuốc không?" — đúng nguyên tắc đã dùng thành
công cho `safety_layer` (chuyển từ similarity/keyword sang LLM khi tín hiệu thô không tách được, mục 3 vòng
3). Input ngắn, output có/không, `temperature=0` — chi phí thấp hơn nhiều so với 1 lần gọi LLM thông thường,
nhưng vẫn là **+1 lời gọi LLM mới** trong 2 nhánh reply-parsing này, cần đánh dấu cost như mọi quyết định
tương tự trong dự án.

Việc phụ, làm nếu tiện (không phải fix chính): sửa lexical search bỏ qua dòng prefix "Thuốc: ... —
danh_mục" trước khi tính `word_similarity` — giảm nhiễu ở kênh này, nhưng không đủ để giải quyết toàn bộ vấn
đề 1 mình (recall vector vẫn kém với câu ngắn), không thay thế được LLM gate.

### 2.3. Sửa 2 nhánh reply-parsing — thêm LLM gate trước search, không phải chỉnh sàn

Khi LLM gate trả lời "không" (không phải tên/mô tả thuốc) — xử lý y hệt trường hợp "không tìm thấy gì" đã
có sẵn ở §5.2 (vòng 2): tiếp tục đúng cơ chế trần 2 vòng + câu xin lỗi cố định, không xây luồng mới. Khi gate
trả lời "có" — mới chạy `_search_distinct_drug_candidates()` như hiện tại (ngưỡng `NGUONG_VECTOR`/
`NGUONG_LEXICAL` giữ nguyên, không đổi — không phải nguồn gốc vấn đề như đã xác nhận).

### 2.4. Liên hệ mục 3 — LLM gate là lớp riêng, KHÔNG cần sửa `_search_distinct_drug_candidates()`

Khác dự tính ban đầu (đặt ngưỡng bên trong hàm) — vì LLM gate chạy **trước khi gọi hàm search**, hàm
`_search_distinct_drug_candidates()` giữ nguyên hoàn toàn (ngưỡng `NGUONG_VECTOR`/`NGUONG_LEXICAL` không
đổi). Mục 3.3 (fuzzy 2 tầng, bên dưới) dùng lại đúng hàm này cho reflexion vòng 2 — **không bị ảnh hưởng
bởi thay đổi ở mục 2**, không cần đồng bộ gì thêm giữa 2 mục. Vẫn nên làm mục 2 trước mục 3 vì mục 2 chặn
đúng nguồn gây bug đã xác nhận, nhưng không còn phụ thuộc kỹ thuật bắt buộc giữa 2 mục như bản trước.

### 2.5. Vì sao vẫn ưu tiên cao nhất trong cả vòng

Root cause đổi nhưng kết luận ưu tiên không đổi: nếu 2 nhánh reply-parsing vẫn tin mù kết quả search chưa
lọc, dù mục 3 (fuzzy 2 tầng cho đường chính) có tốt tới đâu cũng không cứu được — bug xảy ra ở 1 nhánh khác,
song song, không đi qua đường chính đó.

### 2.6. Test bắt buộc

- **Test case thật đã tái hiện**: "tôi buồn đi vệ sinh", "tôi thích ăn phở" trong đúng ngữ cảnh
  `STAGE_IN_RX_AWAITING_NEW_NAME`/`STAGE_OUT_RX_AWAITING_REDESCRIBE` (giả lập đang có pending confirmation
  treo) → xác nhận LLM gate trả lời "không", KHÔNG chạy search, KHÔNG tạo pending confirmation mới với
  candidate sai — xử lý như "chưa tìm thấy".
- **Test riêng cho LLM gate**: bộ câu hợp lệ ngắn (chỉ tên thuốc, kể cả viết tắt/không dấu — "paracetamol",
  "vitamin C", "panadol extra") → gate phải trả lời "có", không chặn nhầm reply hợp lệ. Đây là test quan
  trọng nhất — nếu gate quá nghiêm, tái tạo đúng vấn đề "recall kém" đã thấy ở kênh vector.
- Regression: reply hợp lệ trong đúng 2 nhánh này (bệnh nhân mô tả lại đúng, tên thuốc viết tắt/không dấu)
  vẫn phải tìm được candidate đúng sau khi qua gate — không siết gate quá tay khiến reflexion hợp lệ bị chặn.
- Nếu mục 2.0 xác nhận có case `intent_classification` sai sau #25 — thêm bộ test riêng theo đúng hướng cũ
  (ngưỡng confidence cho `intent_classification`), độc lập với LLM gate ở mục này.

---

## 3. Fuzzy search 2 tầng — thay cơ chế tìm ứng viên ở §5.2 (ngoài đơn thuốc)

**Không ảnh hưởng §5.1** (fuzzy match trong đơn thuốc — tập nhỏ, đã đúng, giữ nguyên). Đây chỉ thay cách
tìm ứng viên khi thuốc **không có trong đơn** (tìm trên cả 3562 thuốc).

**Bằng chứng bổ sung từ `audit_log` thật, củng cố ưu tiên mục này**: `drug_identity_resolution` hiện có
p50=12ms nhưng **p90=5.3 giây, p99=8.9 giây, max=10.2 giây** — cứ 10 lượt tra thuốc có 1 lượt chờ hơn 5
giây. Đổi sang fuzzy tầng 1 (không cần embedding) trực tiếp giải quyết phần lớn đuôi trễ này.

### 3.1. Tầng 1 — fuzzy match thuần, không dùng vector

- Dùng `similarity()` trên `ten_thuoc_unaccent` (đã có cột + GIN trigram index từ Phase 1/3) — lấy top-5.
- **Không gọi OpenAI embedding cho bước này** — khác hẳn `_search_distinct_drug_candidates()` cũ (hybrid,
  cần embed câu hỏi). Đây là cải thiện chi phí thật, không chỉ chất lượng.

### 3.2. Tầng 2 — quyết định có cần LLM cân nhắc hay không

```
top-5 (điểm số fuzzy) →
  NẾU top-1 ≥ NGƯỠNG_CAO (vd 0.90) VÀ (top-1 - top-2) ≥ NGƯỠNG_CÁCH_BIỆT (vd 0.15)
    → bỏ qua LLM, dùng thẳng top-1 làm ứng viên
  NGƯỢC LẠI (điểm thấp, HOẶC top-1/top-2 quá sát nhau)
    → LLM cân nhắc trong 5 ứng viên, chọn 1 (có thể dùng thêm ngữ cảnh câu hỏi gốc, không chỉ điểm số)
```

`NGƯỠNG_CAO`/`NGƯỠNG_CÁCH_BIỆT` — `[CẦN CHỐT — thực nghiệm]`, đặt config có TODO, tune bằng `eval/` giống
cách đã làm với `NGUONG_VECTOR`/`NGUONG_LEXICAL` (sweep trên `eval/ground_truth.json`, đo tỷ lệ chọn đúng
theo từng mức ngưỡng trước khi chốt số).

**Nguyên tắc an toàn bắt buộc, không đổi bất kể nhánh nào ở trên chạy:** dù bỏ qua LLM hay không, **luôn
luôn hỏi xác nhận bệnh nhân** trước khi trả lời — cái được lược bớt ở nhánh tin cậy cao chỉ là chi phí tính
toán (không gọi LLM), không bao giờ là bước xác nhận an toàn. Đây là điểm không thương lượng, lý do: #12/
#15/#17 (18.8% nhầm thuốc đo được thật ở vòng 2) là hậu quả trực tiếp của việc bỏ qua bước xác nhận khi độ
tin cậy "trông có vẻ" đủ cao — không lặp lại.

### 3.3. Reflexion — tái dùng §5.2 đã có, không xây cơ chế mới

Luồng "từ chối → top-3 khác → vẫn không đúng → mô tả lại → tìm lần 2 → vẫn không có → câu xin lỗi cố định"
đã có sẵn ở §5.2 (vòng 2), tối đa 2 vòng. Chỉ thay đổi 1 điểm: **vòng 2 (sau khi bệnh nhân mô tả lại) dùng
hybrid search cũ (`_search_distinct_drug_candidates()`, semantic) làm phương án dự phòng**, không lặp lại
fuzzy tầng 1 — vì tới bước này, bệnh nhân đã mô tả nhiều hơn tên (có thể theo công dụng), phù hợp semantic
hơn fuzzy tên riêng. Giữ nguyên trần 2 vòng, không mở rộng thêm.

`_search_distinct_drug_candidates()` **không bị xoá** — đổi vai trò từ "đường chính duy nhất" thành "phương
án dự phòng cho vòng 2 của reflexion".

### 3.4. Test bắt buộc

- Case top-1 rõ ràng vượt trội (≥ ngưỡng cao, cách biệt rõ) → xác nhận bỏ qua LLM, nhưng **vẫn** có bước hỏi
  xác nhận bệnh nhân (test cụ thể: `pending_drug_confirmation` vẫn được tạo, không trả lời thẳng).
- Case 2 candidate top-1/top-2 sát điểm nhau (dù cả 2 đều cao) → xác nhận đi qua nhánh LLM, không bỏ qua.
- Case điểm thấp → LLM cân nhắc.
- Case reflexion vòng 2 → xác nhận dùng đúng `_search_distinct_drug_candidates()`, không lặp lại fuzzy tầng 1.
- **Test case thật lấy từ `audit_log`**: "Paracetamol " (có khoảng trắng cuối) từng khớp nhầm thành
  `micardis-40mg-boehringer-3x10` (thuốc huyết áp, hoàn toàn không liên quan) — thêm làm regression case cố
  định, xác nhận cơ chế mới không lặp lại kiểu match sai này.
- Regression: chạy lại `eval/ground_truth.json` (32 câu) + `eval/out_of_domain.json` (15 câu) trên cơ chế
  mới, so sánh với số liệu cũ (mục 15, `chatbot-rag-design.md`) — đặc biệt xem #14 có còn tái hiện không khi
  không còn đi qua RRF cho việc định danh thuốc.
- Đo lại p50/p90/p99 latency của `drug_identity_resolution` sau khi đổi, so với số liệu cũ (p90=5.3s,
  p99=8.9s ở trên) — xác nhận cải thiện thật bằng số, không chỉ tin "chắc sẽ nhanh hơn".

**Kết quả thực hiện 2026-08-13:** `fuzzy_name_search()` mới (`backend/services/retrieval.py`) dùng
`similarity(ten_thuoc_unaccent)`, không embedding, latency thật ~50-130ms/câu (so với đuôi cũ p90=5.2s,
p99=7.9s — cải thiện thật, đo trong `eval/tune_fuzzy_tier1.py`). Sweep 4 tập dữ liệu (`ground_truth.json` 32
câu đầy đủ, `short_name_ground_truth.json` 10 câu ngắn/viết tắt đã xác minh unique, `out_of_domain.json` 15
câu, `short_name_ambiguous.json` 10 câu tên thật nhưng nhiều SKU) chốt tạm `NGUONG_CAO=0.25`/
`NGUONG_CACH_BIET=0.05` — phát hiện quan trọng: **gap mới là tuyến phòng thủ chính**, không phải điểm tuyệt
đối (tập ambiguous có điểm cao tới 0.586 nhưng gap luôn ≤0.048, dưới ngưỡng 0.05 nên không bao giờ lọt
fast-path). Tầng 2 dùng `select_fuzzy_drug_candidate()` (`classification.py`) — LLM chọn 1 trong top-5 hoặc
trả `null` nếu không an toàn; mặc định fail-closed (`None`) khi chưa wire LLM. Case "Paracetamol " (khoảng
trắng cuối) nay xếp đúng Paracetamol lên đầu, không còn khớp nhầm Micardis.

**Tinh chỉnh 2026-08-14 (phản hồi review, điều kiện cuối trước khi đóng mục 3):** (1) 15 câu
`out_of_domain.json` đều là câu hỏi đầy đủ, không đại diện use-case ngắn thật — thêm
`eval/short_ood_nonexistent.json` (10 brand ngắn giả định, đã xác minh 0 match ILIKE), phát hiện `feverex`
(score=0.208, gap=0.093) lẽ ra lọt fast-path sai ở ngưỡng cũ 0.15/0.20. Trần OOD gộp vẫn `0.238`. (2) Sweep
mịn bước 0.01 trong 0.25-0.30 (biệt cố định 0.05): GT-short giữ 100% tới `0.28`, tụt xuống 90% (case
"fluopas") từ `0.29` — **chốt `NGUONG_CAO=0.28`** (`backend/config.py::fuzzy_name_high_threshold`, điểm cuối
trước khi tụt), margin trên trần OOD tăng từ +0.012 lên +0.042, không đánh đổi gì so với 0.25 (GT-full/
GT-short/OOD/ambiguous giữ nguyên). `NGUONG_CACH_BIET=0.05` không đổi (`fuzzy_name_gap_threshold`).

Test: `tests/test_fuzzy_drug_identity_resolution.py` (3 test khoá invariant fast-path/LLM-review/fail-closed,
không cần Postgres/LLM) + `tests/test_drug_confirmation_dispatch.py::test_fuzzy_name_search_paracetamol_does_not_match_micardis`
(DB thật, khoá đúng regression case đã lộ bug gốc). Xem `chatbot-rag-design.md` mục 10 #34 cho số liệu sweep đầy đủ.

---

## 4. Match triệu chứng ↔ `tac_dung_phu` — hỗ trợ bác sĩ, không kết luận cho bệnh nhân

### 4.1. Cơ chế

- Khi bệnh nhân báo cáo triệu chứng (qua `CLASSIFY=SideEffect`, hoặc redflag triệu chứng ở `safety_layer`
  mục 3 vòng 3), chạy retrieval **giới hạn trong các `drug_id` thuộc đơn thuốc active của bệnh nhân đó**
  (không tìm trên cả 3562 thuốc) — rẻ, tái dùng đúng kiểu filter đã có ở §5.1.
- So khớp triệu chứng bệnh nhân mô tả với nội dung `tac_dung_phu` của từng thuốc trong đơn.

### 4.2. Ranh giới bắt buộc — đây là gợi ý, không phải kết luận

- Kết quả match **chỉ đưa vào trace/audit_log** (bác sĩ xem, theo #7), **không nói thẳng cho bệnh nhân**
  kiểu "thuốc X gây ra triệu chứng này". Nhiều tác dụng phụ (chóng mặt, buồn nôn...) trùng lặp giữa rất
  nhiều thuốc khác nhau — match được không đồng nghĩa đúng nguyên nhân.
- Format ghi log: `"Có thể liên quan tới tác dụng phụ của {ten_thuoc} (độ khớp {X}%)"` — giữ tính chưa chắc
  chắn tường minh, cùng kỷ luật với #13a (không tự suy diễn thành kết luận chắc chắn).
- Nếu nhiều thuốc trong đơn cùng match — liệt hết theo thứ tự độ khớp, không tự chọn 1 thuốc "đúng nhất" để
  báo cáo — quyết định cuối thuộc về bác sĩ đọc log, không phải hệ thống.

**Bằng chứng từ `audit_log` cho thấy đây là việc cần thật**: các case triệu chứng hiện có (vd "Tôi cảm thấy
buồn nôn") đang chạy `severity_assessment` với `drug_id: null` — nghĩa là hiện tại đánh giá mức độ nghiêm
trọng cho triệu chứng **không hề dựa vào thuốc cụ thể nào trong đơn**, chỉ dùng mức sàn mặc định
(`fallback_severity: "Trung bình"`). Mục này khắc phục đúng khoảng trống đó.

**Quyết định đã chốt (Vòng 4)**: trước khi chốt ngưỡng cho match này, tạo một bộ `eval/` có nhãn thủ công
gồm: triệu chứng khớp rõ với 1 thuốc, không có liên hệ rõ ràng, nhiều thuốc cùng khớp, và triệu chứng đi kèm
redflag. Sweep các ngưỡng trên chính bộ này, đo false positive/false negative trước khi đưa số cuối vào config.
Không được lấy kết quả gần nhất rồi ghi log như một match; chỉ các thuốc vượt ngưỡng đã được thực nghiệm mới
được ghi, vẫn liệt kê đầy đủ nếu có nhiều thuốc vượt ngưỡng. Số ngưỡng cụ thể là kết quả của eval, không đoán
trước.

**Quyết định bổ sung sau sweep**: cosine trên chunk dài không tách sạch được match đúng khỏi không liên quan
(vd triệu chứng đúng có thể thấp hơn một kết quả sai). Vì vậy dùng **2 tầng**: (1) cosine chỉ lọc một tập ứng
viên rộng trong thuốc active, không tự kết luận match; (2) LLM nhị phân, `temperature=0`, đọc triệu chứng gốc
và đúng chunk `tac_dung_phu` của từng ứng viên để trả lời `match`/`không match`. Chỉ `match` từ tầng 2 mới
được ghi audit. Đây là lời gọi LLM nội bộ có chi phí đã được phê duyệt, không tạo nội dung mới cho bệnh nhân;
với redflag vẫn chạy audit này nhưng response chỉ thuộc safety layer.

**Kết quả thực hiện**: dùng cosine `>=0.20` để lọc ứng viên (giữ 12/12 liên hệ đúng ở tầng 1), sau đó chạy
LLM nhị phân trên ứng viên còn lại. `eval/tune_side_effect_match.py --validate-llm --candidate-threshold 0.20`
đạt precision 100%, recall 100%, `FP=0`, `FN=0` trên bộ 11 case đã gán nhãn; chỉ các match LLM xác nhận được
ghi trace.

### 4.3. Test bắt buộc

- Case 1 thuốc trong đơn có `tac_dung_phu` khớp rõ triệu chứng → xác nhận log đúng format, đúng field
  `source_field_groups` kiểu đã dùng ở SEVERITY (mục "SEVERITY nguồn RAG", vòng 2).
- Case nhiều thuốc cùng match → liệt đủ, không chỉ 1.
- Case không thuốc nào match → log rõ "không tìm thấy liên hệ rõ ràng", không im lặng.
- **Test bắt buộc riêng**: response gửi cho **bệnh nhân** (khác trace) không chứa bất kỳ kết luận nhân quả
  nào kiểu "do thuốc X gây ra" — chỉ audit log mới có.

### 4.4. Audit log phải ghi đủ ngữ cảnh khi 1 tin nhắn chứa nhiều ý định (liên quan mục 1.1)

Phát hiện thật: tin nhắn dài chứa cả câu hỏi lịch + báo triệu chứng + 1 câu redflag — response chỉ xử lý
redflag, nhưng **audit log/trace phải ghi nhận toàn bộ tín hiệu phát hiện được trong tin nhắn**, không chỉ
phần được trả lời. Cụ thể: nếu tin nhắn chứa cả nội dung khớp mô tả triệu chứng VÀ trigger redflag, vẫn chạy
match triệu chứng ↔ `tac_dung_phu` (mục 4.1) để ghi vào trace, dù response cuối cùng chỉ hiển thị nội dung
cảnh báo redflag cho bệnh nhân. Mục đích: bác sĩ đọc lại log sau này thấy đủ bối cảnh (redflag + triệu chứng
đi kèm + có hỏi gì khác), không chỉ "phát hiện redflag" trơ trọi.

**Test bắt buộc riêng**: tin nhắn giả lập chứa cả nội dung triệu chứng lẫn trigger redflag → xác nhận trace
có cả 2 entry (match triệu chứng + redflag), response cho bệnh nhân chỉ hiển thị nội dung redflag.

---

## 5. Tóm tắt hội thoại theo giờ — tầng giữa, không tự động bơm vào context

### 5.1. Vai trò — khác gì với §7.2/§7.3 (vòng 3)

- §7.2 (15 phút, tự động, mọi lượt) — giữ mạch hội thoại tức thời. Không đổi.
- §7.3 (tra cứu dài hạn theo yêu cầu, đọc `chat_messages` thô) — vẫn giữ, nhưng giờ có thêm nguồn tóm tắt
  để đọc nhanh hơn thay vì đọc lại toàn bộ tin nhắn thô của nhiều giờ/ngày.
- **Tóm tắt theo giờ = tầng dữ liệu mới ở giữa**, phục vụ đúng 2 mục đích: (a) làm nguồn nhanh hơn cho
  `chat_history_query` (§7.3(a)), (b) dữ liệu cho dashboard bác sĩ sau này (§7.3(b), vẫn để ngỏ, không build
  dashboard trong vòng này).

### 5.2. Cơ chế — tái dùng `APScheduler` + `SQLAlchemyJobStore` đã có (mục 4 vòng 2)

- Thêm 1 job mới chạy mỗi giờ — chỉ tóm tắt cho **bệnh nhân có tin nhắn mới trong giờ đó** (không chạy vô
  điều kiện cho mọi bệnh nhân, kiểm soát chi phí).
- Mỗi giờ ra **1 bản tóm tắt độc lập** (không gộp dồn với giờ trước) — tránh token tăng dần theo thời gian
  nếu phải đọc lại bản tóm tắt cũ mỗi lần tóm tắt tiếp.
- Bảng mới (hoặc mở rộng `chat_messages`) lưu: `patient_id`, `hour_bucket` (mốc giờ), `summary_text`,
  `message_count`, `created_at`.

### 5.3. Ranh giới bắt buộc — nguyên tắc quan trọng nhất của mục này

**Không bao giờ tự động đưa vào `intent_classification`/`answer_generation`** — chỉ đọc khi có yêu cầu tra
cứu (§7.3(a)) hoặc hiển thị dashboard. Nếu vi phạm nguyên tắc này (tự động bơm tóm tắt cũ vào mọi câu trả
lời), tái phạm đúng rủi ro đã bác bỏ khi từ chối mô hình "nhớ vô hạn giống Claude" ở vòng 3 — ngữ cảnh y tế
cũ/đã nén lại có thể trộn nhầm vào câu hỏi hiện tại không liên quan.

### 5.4. Chi phí

1 lần gọi LLM/bệnh nhân có hoạt động/giờ — dự đoán được theo số bệnh nhân đang hoạt động (khác cơ chế 15
phút, vốn tính theo mỗi lượt chat). Ghi vào doc như mọi quyết định cost khác trong dự án.

### 5.5. Test bắt buộc

- Case bệnh nhân có tin nhắn trong giờ → có bản tóm tắt mới, đúng nội dung giờ đó (không lẫn giờ khác).
- Case bệnh nhân không hoạt động trong giờ → không tạo bản tóm tắt rỗng, không tốn lệnh gọi LLM.
- **Test bắt buộc riêng, đúng dạng đã dùng ở §9.4 vòng 3**: gọi `intent_classification`/`answer_generation`
  thật, xác nhận bản tóm tắt theo giờ KHÔNG xuất hiện trong prompt gửi đi, kể cả khi bệnh nhân có tóm tắt cũ
  tồn tại — chỉ 15 phút gần nhất (§7.2) được đưa vào.
- Test `chat_history_query` (§7.3(a)) đọc đúng bản tóm tắt khi bệnh nhân hỏi lại lịch sử — không đọc lại
  toàn bộ `chat_messages` thô nếu đã có tóm tắt giờ đó.

**Kết quả thực hiện 2026-08-13/14:** bảng `hourly_conversation_summaries` (migration `0015`) — 1 summary độc
lập/`(patient_id, hour_bucket)`, unique constraint làm job idempotent. Job mới `_run_hourly_summary` dùng
chung `AsyncIOScheduler`, chạy phút 0 mỗi giờ (`max_instances=1`, tránh chồng lượt), chỉ gọi LLM cho bệnh
nhân có `chat_messages` chưa ẩn trong giờ vừa kết thúc — `create_completed_hour_summaries()`
(`backend/services/hourly_conversation_summary.py`). `get_hourly_summaries_for_history()` (đọc, dùng trong
`chat_history_query`) tách biệt hoàn toàn `get_recent_context()` (đọc, dùng trong intent/answer) — 2 hàm
độc lập, không hàm nào gọi hàm kia. Test: 4 test đơn vị/tích hợp (`tests/test_hourly_conversation_summary.py`
— bucket, tạo/không tạo summary, `chat_history_query` ưu tiên đọc summary) + mới thêm 2026-08-14
`tests/test_chat_history_e2e.py::test_hourly_summary_never_appears_in_intent_classification_prompt` (e2e
qua `/api/v1/chat` thật, đúng dạng test đã dùng ở §9.4 vòng 3 — seed 1 summary với nội dung riêng biệt, xác
nhận `classify_intent()` không nhận được nội dung đó). **Cần chạy migration `0015` ở môi trường deploy.**

---

## 6. `soul.md` — persona Capy, viết SAU CÙNG

### 6.1. Phạm vi — chỉ giọng văn, không lẫn nội dung an toàn

- Chỉ mô tả: tên "Capy"/"Capy Medi", tông giọng thân thiện, cách xưng hô, ví dụ câu chào/phản hồi thường —
  đúng nội dung đã có ở mục 9 vòng 3 (thân thiện tỉ lệ nghịch mức nghiêm trọng).
- **Không viết lại** nội dung đã thuộc phạm vi khác — 5 câu giải thích cảnh báo, taxonomy phân loại mức độ
  (mục 3.1 vòng 3), kỷ luật grounding (#13a/#13b). File này **tham chiếu tới** các phần đó (nêu tên
  file/hàm chứa nội dung gốc), không copy nội dung sang — 2 nguồn cùng mô tả 1 thứ dễ trôi lệch nhau theo
  thời gian (bài học đã gặp ở 2 đường escalate từng lệch nhau trước khi hợp nhất, vòng 2).

### 6.1.1. Danh sách cụ thể — restyle được (nhóm A) vs KHÔNG được đụng (nhóm B)

Rà lại toàn bộ response constant hiện có trong repo, phân 2 nhóm rõ ràng, agent bám đúng danh sách này khi
restyle, không tự suy đoán phạm vi:

**Nhóm A — restyle theo `soul.md` mục 1-9, tự do đổi câu chữ:**
- `conversation_nodes.py`: `GREETING_RESPONSE`, `GREETING_QUICK_REPLIES`, `NO_SOURCE_MESSAGE`,
  `NO_SCHEDULE_TODAY_MESSAGE`, chat_history fallback. Riêng `CAVEAT_LIEU_DUNG`/`CAVEAT_THOI_DIEM_MISSING`:
  đổi được câu chữ, **phải giữ nguyên ý nghĩa** (liều chung không cá nhân hoá; thời điểm dùng cần hỏi bác
  sĩ) — không phải nội dung cấm, chỉ đổi giọng không đổi ý. Format lịch uống hôm nay
  (`_format_full_day_answer`/`_format_buoi_answer`): đổi được từ ngữ/kết nối câu, **giữ nguyên cấu trúc**
  (tiêu đề ngày, nhóm theo buổi, kèm thời điểm dùng) đã chốt ở mục 5.4 vòng 3.
- `dose_confirmation_nodes.py`: `ASK_AGAIN_MESSAGE`, và **3 câu đang treo TODO** — `TAKEN_RESPONSE`,
  `LOW_ACTION_RESPONSE`, `MEDIUM_ACTION_RESPONSE`. PM tự quyết trực tiếp (không cần Phạm Thành Đạt, khác
  overlay khẩn cấp) — sau khi restyle, **gỡ TODO marker**, coi như đã chốt.
- `drug_confirmation_nodes.py`: toàn bộ — `NOT_FOUND_FINAL_MESSAGE`, `ASK_DIFFERENT_NAME_MESSAGE`,
  `ASK_DESCRIBE_AGAIN_MESSAGE`, `UNPARSEABLE_YES_NO_MESSAGE`, `UNPARSEABLE_CHOICE_MESSAGE_TEMPLATE`,
  `TOO_MANY_UNPARSEABLE_REPLIES_MESSAGE`, `_confirm_question()`, `_top3_menu()`.

**Nhóm B — KHÔNG đụng, cần vòng duyệt PM + Phạm Thành Đạt mới nếu muốn đổi:**
- `escalation.py`: `OVERDOSE_OVERLAY_MESSAGE`, `MISSED_DOSE_OVERLAY_MESSAGE`, `SYMPTOM_OVERLAY_MESSAGE`,
  `SIDE_EFFECT_OVERLAY_MESSAGE`, `GENERIC_OVERLAY_MESSAGE`, `SELF_HARM_OVERLAY_MESSAGE`,
  `CATEGORY_EXPLANATIONS` (cả 5 dòng). Đây đúng nội dung mục 8 (`soul.md`) đã loại trừ — giữ nguyên tuyệt
  đối, không "làm mềm giọng" dù chỉ đổi 1 chữ, kể cả khi agent nghĩ câu đó nghe "quá cứng" so với phần còn
  lại — cứng có chủ đích, không phải thiếu sót cần restyle.

**Ví dụ mẫu (nhóm A) để agent bám tông, không cần viết hết từng câu còn lại theo kiểu này — áp cùng tinh
thần cho các câu còn lại trong nhóm A:**

| Trước | Sau |
|---|---|
| "Capy đã ghi nhận thông tin của bạn. Đây là mức độ nhẹ, hệ thống sẽ tiếp tục theo dõi trong 48 giờ tới." | "Capy đã ghi nhận rồi nhé! Mức độ này nhẹ thôi, Capy sẽ để ý theo dõi thêm cho bạn trong 48 giờ tới ạ." |
| "Capy Medi đã ghi nhận thông tin của bạn. Người thân và bác sĩ đã được thông báo để theo dõi thêm." | "Capy đã ghi nhận rồi nhé. Để an toàn hơn, Capy đã báo cho người thân và bác sĩ của bạn cùng theo dõi giúp bạn." |
| "Xin lỗi, thuốc bạn tìm kiếm hiện giờ không có thông tin." | "Dạ, Capy chưa tìm được thông tin về thuốc này ạ. Bạn hỏi thêm bác sĩ hoặc dược sĩ để chắc chắn hơn nhé." |

### 6.2. Không load vào mọi prompt — chỉ phần sinh nội dung cho bệnh nhân

- **Load vào**: `answer_generation`, greeting, các response constants sinh cho bệnh nhân.
- **KHÔNG load vào**: prompt của safety classifier (mục 3.2 vòng 3), `intent_classification` (mục 2, vòng
  này) — cả 2 cần tập trung tuyệt đối vào phân loại chính xác, không nhiễu bởi hướng dẫn giọng văn, đặc biệt
  khi đã biết GPT-4o-mini không tất định tuyệt đối kể cả `temperature=0` (#30, ghi nhận ở vòng 3).

### 6.3. Test bắt buộc

- Xác nhận `safety_layer`'s classifier prompt VÀ `intent_classification`'s prompt không chứa nội dung từ
  `soul.md` (kiểm tra tĩnh, đọc code).
- Chạy lại `eval/redteam_prompts.py` case c3 (đúng case đã dùng để verify #13a sau khi đổi giọng văn ở vòng
  3) — xác nhận persona mới (nếu có thay đổi thêm ở vòng này) không phá kỷ luật grounding.
- **Test mục 9 (luôn trả lời tiếng Việt)**: gửi câu hỏi bằng tiếng Anh (vd "What are the side effects of
  {tên thuốc}?") qua `answer_generation` thật → xác nhận response trả về bằng tiếng Việt, tên thuốc/đơn vị
  đo giữ nguyên gốc. Đồng thời xác nhận `intent_classification`/safety classifier vẫn hiểu đúng câu tiếng
  Anh này (không cần trả lời tiếng Việt, nhưng vẫn phải phân loại đúng) — 2 test riêng, không gộp chung.

**Kết quả thực hiện 2026-08-14:** `tests/test_soul_persona.py` xác nhận tĩnh persona chỉ nằm ở phần sinh nội
dung patient-facing, không nằm trong prompt `intent_classification`/safety; các response Nhóm B trong
`escalation.py` không đổi. `eval/soul_persona_check.py` chạy 9 lời gọi live: case c3 lặp 6/6 không tự dựng
liều tối đa, câu hỏi tiếng Anh được trả lời bằng tiếng Việt và giữ nguyên `Vitamin C 500mg`, intent trả
`drug_info`, safety trả `Nguy hiểm`/`clinical_symptom`. Báo cáo lưu tại `eval/soul_persona_report.json`.

### 6.4. Điểm nối mới — kết quả xác thực ảnh uống thuốc (từ hệ CV của Phạm Thành Đạt)

Phát hiện khi viết `soul.md`: app có tính năng chụp ảnh xác nhận uống thuốc, xử lý bằng CV (YOLOv8, Phạm
Thành Đạt phụ trách) — chatbot **không xử lý ảnh**, chỉ nhận lại kết quả (chấp nhận/từ chối) và diễn đạt cho
bệnh nhân bằng giọng Capy (mục 6, `soul.md`).

`[CẦN THÔNG TIN — hỏi Phạm Thành Đạt, KHÔNG GẤP]`: format kết quả gửi sang chatbot (endpoint mới? bảng
chung?), danh sách lý do từ chối cụ thể (không chỉ "mờ"), và quan hệ với `CLASSIFY=Taken` đã có (ảnh chấp
nhận có tự động đánh dấu `dose_event` đã uống không, hay là tín hiệu độc lập). `soul.md` đã viết sẵn khung
giọng văn cho case "mờ" làm mẫu — cần bổ sung câu cho từng lý do cụ thể khi có câu trả lời, không phải viết
lại từ đầu.

**Không code phần wiring kỹ thuật này trong vòng 4** — chỉ chuẩn bị sẵn giọng văn ở `soul.md`, chờ xác nhận
API contract trước khi xây endpoint/logic nhận kết quả CV.

---

## 7. Thứ tự

1. **Mục 0.5** — đã đóng, không cần làm gì (xem ghi chú trong mục đó) — chỉ cần thêm 4 câu vào regression
   test khi tiện, không phải việc ưu tiên.
2. Mục 1.2 (kiểm tra dữ liệu "Panadol") — làm song song/đầu tiên trong các việc thật, không phải code, chỉ
   1 câu SQL, biết sớm để không giao nhầm việc cho agent coding.
3. Mục 2 (điều tra + sửa `intent_classification`, gồm cả ngưỡng confidence) — đầu tiên trong phần code
   chính, ảnh hưởng mọi luồng phía sau.
4. Mục 3 (fuzzy 2 tầng) — sau mục 2, có thể liên quan trực tiếp #14, có số liệu latency thật ủng hộ ưu tiên.
5. Mục 4 (match triệu chứng + audit log đa-ý-định) — độc lập, không phụ thuộc mục 2/3.
6. Mục 5 (tóm tắt theo giờ) — tái dùng hạ tầng `APScheduler` đã có, không phụ thuộc mục 2/3/4.
7. Mục 6 (`soul.md`) — sau cùng, tham chiếu nội dung đã ổn định ở các mục trên và vòng 3.

---

**Khi nào dừng lại hỏi:**

1. Mục 2.0 — chỉ giữ lại ngưỡng confidence cho `intent_classification` nếu có bằng chứng sau mốc #25, không
   mặc định làm theo kế hoạch cũ.
2. Mục 2.2 — thêm LLM gate là **+1 lời gọi LLM mới**, cần xác nhận cost trước khi build, không âm thầm
   thêm. Mục 3.2 — `NGƯỠNG_CAO`/`NGƯỠNG_CÁCH_BIỆT` cần tune bằng `eval/`, độc lập với mục 2.2 (không còn phụ
   thuộc nhau như bản kế hoạch trước — xem mục 2.4), không đoán số khởi điểm rồi dùng luôn làm final.
3. Nếu phát hiện #14 biến mất hoàn toàn sau khi đổi cơ chế tìm ứng viên (mục 3) — xác nhận lại với Architect
   trước khi đóng #14 trong mục 10, cần bằng chứng cụ thể (so sánh trước/sau), không chỉ suy đoán.
4. Bất kỳ nội dung patient-facing mới nào phát sinh khi viết `soul.md` (vd câu ví dụ mẫu) trùng phạm vi đã
   có PM + Phạm Thành Đạt duyệt — không tự viết lại, chỉ tham chiếu.
5. Multi-intent đầy đủ (mục 1.1) — không tự build trong vòng này dù có thời gian rảnh, cần thiết kế riêng.
6. Mục 1.2 — nếu xác nhận "Panadol" thật sự thiếu trong dữ liệu, không tự ý thêm thủ công 1 sản phẩm đơn lẻ
   vào DB — báo lại để xử lý đúng quy trình thu thập dữ liệu đã có (crawl/validate), tránh dữ liệu tay không
   nhất quán với phần còn lại.
