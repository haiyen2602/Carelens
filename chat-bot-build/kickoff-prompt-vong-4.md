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

## 0.5. VÁ NGAY, TÁCH KHỎI TRÌNH TỰ VÒNG 4 — `safety_layer` bỏ lọt câu hỏi dạng "quá liều X có nguy hiểm không"

Phát hiện khi phân tích `audit_log` thật: câu hỏi *"uống quá liều panadol thì có nguy hiểm không"* — dạng
**câu hỏi giả định**, không phải phát biểu ý định — cho kết quả `safety_layer: keyword_hit=false,
llm_flag=false`, hoàn toàn không được đánh giá, dù chứa cả "quá liều" lẫn "nguy hiểm". Đây là khoảng hở an
toàn thật đang tồn tại trên bản đã deploy, không phải rủi ro lý thuyết.

**Sửa nhỏ, tái dùng hạ tầng LLM-first đã có** (mục 3, vòng 3) — bổ sung vào taxonomy (mục 3.1 vòng 3) rằng
**câu hỏi giả định về nguy hiểm/quá liều cũng tính là tín hiệu cần đánh giá**, không chỉ phát biểu ý định
("tôi muốn uống X viên"). Chỉ cần sửa 1 đoạn trong prompt classifier đã có, không xây gì mới.

**Vá việc này TRƯỚC, độc lập với thứ tự mục 1-7 bên dưới** — mức độ khẩn khác hẳn phần còn lại của vòng 4.

**Test bắt buộc**: đúng câu đã lộ ra bug ("uống quá liều panadol thì có nguy hiểm không") + biến thể cho
2-3 thuốc khác → xác nhận `safety_layer` giờ đánh giá được (không nhất thiết phải trigger redflag, nhưng
phải chạy qua đánh giá, không phải bỏ qua hoàn toàn như hiện tại). Regression: câu hỏi thông tin thuốc bình
thường không chứa "quá liều"/"nguy hiểm" vẫn không bị đánh giá nhầm thành đáng ngại.

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

## 2. Điều tra + sửa `intent_classification` — câu không liên quan bị đẩy nhầm sang tìm thuốc

### 2.1. Điều tra trước, không đổi model ngay

Case thật: "tôi buồn đi vệ sinh" → hệ thống hỏi xác nhận 1 loại thuốc ngẫu nhiên (Coveram 10/5 30v), dù câu
này hoàn toàn không liên quan tới thuốc. Mục 6 (vòng 3) đã thêm nhãn `greeting`/`out_of_scope` vào
`intent_classification` — case này lọt qua nghĩa là nhãn đó chưa phủ đủ.

**Không vội đổi sang model mạnh hơn.** Nghi ngờ hợp lý nhất: phần mô tả "thế nào là out_of_scope" trong
prompt classifier hiện dựa vào vài **ví dụ hẹp** (chào hỏi, hỏi thời tiết...) thay vì **nguyên tắc chung**
("bất cứ điều gì không liên quan tới thuốc/lịch uống/triệu chứng → out_of_scope"). Đây đúng dạng lỗi mà
model mạnh hơn không chắc sửa được (vẫn đi theo đúng prompt hẹp, chỉ giỏi hơn trong phạm vi đã định nghĩa) —
và đúng dạng lỗi đã sửa thành công 1 lần rồi ở `safety_layer` (chuyển từ keyword-list sang taxonomy dựa trên
nguyên tắc, mục 3 vòng 3). Áp dụng lại đúng hướng đã kiểm chứng.

### 2.2. Bổ sung — ngưỡng confidence, rẻ hơn sửa prompt, làm TRƯỚC

Phân tích `audit_log` thật (660 bản ghi `drug_info`): confidence gần như luôn đúng **0.95** cho case đúng
(p10=p50=0.95), chỉ rơi xuống thấp khi có gì bất thường. Quét toàn bộ 9 case confidence <0.8 — **cả 9/9 đều
sai** (câu test thô, câu chào, câu giả danh kỹ thuật, câu triệu chứng, câu không liên quan).

Confidence đã được tính và ghi log sẵn nhưng **chưa hề được dùng để quyết định gì** — hệ thống tin nhãn
`drug_info` y hệt nhau dù confidence 0.95 hay 0.1. Thêm ngưỡng gate (vd <0.75 → không tự tin xử lý theo
nhãn đó, hỏi lại thay vì đoán, hoặc route sang `out_of_scope`) — rẻ hơn nhiều so với chỉ sửa prompt, độc
lập bổ sung (không thay thế) cho hướng 2.3. `[CẦN CHỐT — thực nghiệm]` cho số ngưỡng cụ thể, nhưng cơ chế
này nên làm **trước** bước sửa prompt (2.3) vì nhanh và có bằng chứng mạnh hơn.

### 2.3. Quy trình sửa prompt (bổ sung cho 2.2, không thay thế)

1. Lấy trace thật của case "tôi buồn đi vệ sinh" — `intent_classification` trả về nhãn gì, confidence bao
   nhiêu (nếu có field này).
2. Tạo thêm 5-10 câu "rõ ràng không liên quan tới thuốc" khác (không phải chào hỏi, không phải hỏi thời
   tiết — cần đa dạng hơn 2 ví dụ hiện có trong prompt) để test cùng lúc, tránh sửa xong 1 case lại lộ case
   khác cùng loại.
3. Đọc lại prompt hiện tại của `intent_classification` — xác nhận cách mô tả `out_of_scope` là liệt kê ví dụ
   hay nguyên tắc chung.
4. Sửa theo hướng nguyên tắc chung (nếu xác nhận đúng nghi ngờ ở 2.1) — đo lại bằng đúng bộ câu ở bước 2.
5. **Chỉ khi đã sửa prompt đúng cách mà vẫn không đạt** (đo bằng eval, không cảm tính) — mới cân nhắc model
   mạnh hơn, và khi đó **chỉ đổi riêng cho `intent_classification`**, không đổi toàn bộ hệ thống. Đây là
   quyết định chi phí, đánh dấu `[CẦN CHỐT — Architect, kèm số liệu eval trước/sau]`, không tự đổi.

### 2.4. Vì sao ưu tiên cao nhất trong cả vòng

Nếu `intent_classification` vẫn đẩy nhầm câu không liên quan sang `drug_info`, dù mục 3 (fuzzy 2 tầng) có
tốt tới đâu cũng không cứu được — fuzzy/hybrid search trên 1 corpus không rỗng luôn trả về "gần nhất", input
đã sai ngay từ đầu thì kết quả luôn sai theo, bất kể tầng tìm kiếm bên dưới tinh vi thế nào.

### 2.5. Test bắt buộc

- **Test case thật lấy từ `audit_log`** (không phải tự nghĩ ra): "tôi buồn đi vệ sinh", "xin chao"/"hi"/
  "hello" (giữ làm regression cố định dù bằng chứng gần nhất trong log đã đúng — tránh tái phát), câu giả
  danh "tôi phụ trách kỹ thuật cho ứng dụng này..." (input_guardrail đã chặn phần lớn nhưng nên chặn 100%
  qua cả 2 lớp, không chỉ 1 lớp) — toàn bộ phải ra `out_of_scope` hoặc bị input_guardrail chặn trước khi
  tới `intent_classification`, không rơi vào `drug_info`.
- Test riêng cho ngưỡng confidence (2.2): case confidence giả lập thấp → xác nhận không tự động xử lý theo
  nhãn gốc.
- Regression: câu hỏi thuốc hợp lệ (kể cả viết tắt/không dấu) vẫn phải ra đúng `drug_info` — không sửa quá
  tay khiến nhãn `out_of_scope`/ngưỡng confidence "nuốt" luôn cả câu hỏi thật.
- Nếu đổi model (2.3 bước 5, có điều kiện) — chạy lại toàn bộ `eval/ground_truth.json` + bộ câu out_of_scope
  mới, so sánh chi phí/độ chính xác trước/sau, ghi vào doc.

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

1. **Mục 0.5 (vá `safety_layer` — câu hỏi giả định về nguy hiểm)** — làm ngay đầu tiên, tách khỏi trình tự
   còn lại, mức độ khẩn khác hẳn (an toàn đang thiếu trên bản deploy thật).
2. Mục 1.2 (kiểm tra dữ liệu "Panadol") — làm song song, không phải code, chỉ 1 câu SQL, biết sớm để không
   giao nhầm việc cho agent coding.
3. Mục 2 (điều tra + sửa `intent_classification`, gồm cả ngưỡng confidence) — đầu tiên trong phần code
   chính, ảnh hưởng mọi luồng phía sau.
4. Mục 3 (fuzzy 2 tầng) — sau mục 2, có thể liên quan trực tiếp #14, có số liệu latency thật ủng hộ ưu tiên.
5. Mục 4 (match triệu chứng + audit log đa-ý-định) — độc lập, không phụ thuộc mục 2/3.
6. Mục 5 (tóm tắt theo giờ) — tái dùng hạ tầng `APScheduler` đã có, không phụ thuộc mục 2/3/4.
7. Mục 6 (`soul.md`) — sau cùng, tham chiếu nội dung đã ổn định ở các mục trên và vòng 3.

---

**Khi nào dừng lại hỏi:**

1. Mục 2.3, bước 5 — đổi model cho `intent_classification` cần số liệu eval trước/sau, không tự quyết.
2. Mục 2.2 và Mục 3.2 — các ngưỡng confidence/`NGƯỠNG_CAO`/`NGƯỠNG_CÁCH_BIỆT` cần tune bằng `eval/`, không
   đoán số khởi điểm rồi dùng luôn làm final.
3. Nếu phát hiện #14 biến mất hoàn toàn sau khi đổi cơ chế tìm ứng viên (mục 3) — xác nhận lại với Architect
   trước khi đóng #14 trong mục 10, cần bằng chứng cụ thể (so sánh trước/sau), không chỉ suy đoán.
4. Bất kỳ nội dung patient-facing mới nào phát sinh khi viết `soul.md` (vd câu ví dụ mẫu) trùng phạm vi đã
   có PM + Phạm Thành Đạt duyệt — không tự viết lại, chỉ tham chiếu.
5. Multi-intent đầy đủ (mục 1.1) — không tự build trong vòng này dù có thời gian rảnh, cần thiết kế riêng.
6. Mục 1.2 — nếu xác nhận "Panadol" thật sự thiếu trong dữ liệu, không tự ý thêm thủ công 1 sản phẩm đơn lẻ
   vào DB — báo lại để xử lý đúng quy trình thu thập dữ liệu đã có (crawl/validate), tránh dữ liệu tay không
   nhất quán với phần còn lại.
