# Kickoff Prompt — Vòng 3: safety_layer LLM-first + hiển thị lịch uống thuốc

> Dán cho agent coding, cùng quy ước như 2 file trước. Vòng này bắt nguồn từ buổi thử tay thật của PM
> (Nguyễn Minh Đạt) sau khi vòng 2 đóng — phát hiện 1 lỗ hổng an toàn thật (không phải red-team, là hành vi
> thật khi dùng bình thường) và 1 vấn đề UX ảnh hưởng domain `today_schedule`.

---

## 0. Cập nhật `chatbot-rag-design.md` trước khi code

Ghi các quyết định dưới đây vào mục 10 (tiếp số từ #17: #18, #19, #20...), giữ nguyên style đã dùng — không
đánh số lại các mục cũ.

---

## 1. Bối cảnh — vì sao vòng này tồn tại

Thử tay thật phát hiện: câu **"Tôi muốn uống 10 viên thuốc ngủ"** không kích hoạt `safety_layer` (khác câu
tương đương "tôi có 10 viên thuốc ngủ, uống hết có sao không" — câu này trigger đúng). Nguyên nhân: bug
overdose gốc ở Phase 5b được sửa bằng 2 điều kiện regex độc lập (số lượng+đơn vị **VÀ** cụm từ rủi ro) — câu
mới thiếu cụm từ rủi ro nên trượt qua. PM xác nhận: đây không phải 1 lỗ cần vá thêm, mà là dấu hiệu cả cách
tiếp cận (pattern-matching cho việc đánh giá "nguy hiểm hay không") đã tới giới hạn — quyết định chuyển hướng
kiến trúc: **LLM-first**, regex lùi thành lớp phòng vệ phụ, không phải cơ chế chính.

---

## 2. Điều tra kiến trúc hiện tại — làm TRƯỚC khi sửa bất kỳ dòng nào

**Không giả định.** Đọc lại code `safety_layer` thật, trả lời rõ trước khi thiết kế lại:

- Case `matched_group=None` (đã gặp ở vòng 2, mục 3) cho thấy có vẻ đã tồn tại 1 đường LLM chạy song song
  với regex. Đường đó là gì — 1 LLM call độc lập đánh giá "có nguy hiểm không", hay chỉ là 1 nhánh fallback
  hẹp trong 1 số điều kiện nhất định?
- Vì sao case "muốn uống 10 viên thuốc ngủ" lọt qua cả đường đó (nếu nó thực sự tồn tại và luôn chạy)? Nếu
  đường LLM đó có chạy nhưng vẫn không bắt được, đây là vấn đề prompt/instruction của chính nó, không phải
  thiếu 1 đường LLM mới — cần biết trước khi quyết có viết lại từ đầu hay chỉnh sửa cái đã có.
- `safety_layer` hiện chạy đồng bộ hay bất đồng bộ với luồng chính (mục 8 thiết kế nói "song song, độc lập")
  — xác nhận lại cơ chế race hiện tại trước khi làm mục 4 dưới đây.

**Definition of done:** 1 đoạn mô tả ngắn (không phải code) xác nhận kiến trúc thật, gửi lại trước khi bắt
đầu mục 3.

---

## 3. Safety_layer LLM-first

### 3.1. Khung tiêu chí ("taxonomy") — nội dung system prompt

Đây là câu trả lời cho câu hỏi "dấu hiệu nào là nghiêm trọng" — mô tả bằng ngôn ngữ tự nhiên để LLM tự suy
luận theo ngữ cảnh, không phải danh sách từ khoá cứng:

1. **Ý định/hành vi liên quan tới liều lượng bất thường** — không cần khớp đúng cụm "quá liều": bất kỳ phát
   biểu nào về việc uống 1 lượng thuốc rõ ràng vượt mức bình thường, dù diễn đạt như ý định, câu hỏi, hay đã
   xảy ra rồi.
2. **Triệu chứng cấp tính** — khó thở, đau ngực, mất ý thức/lơ mơ, co giật, nôn ra máu, sưng phù bất thường
   (mặt/họng).
3. **Ý định tự hại** — kể cả nói gián tiếp, không cần từ khoá "tự tử"/"tự hại" xuất hiện nguyên văn.
4. **Nhầm lẫn thuốc nghiêm trọng** — uống nhầm thuốc người khác, uống nhầm liều gấp nhiều lần liều kê.
5. **Phản ứng sau uống thuốc mà bệnh nhân tự mô tả là nặng** — đánh giá dựa mức độ nghiêm trọng toát ra từ
   câu, không dựa từ khoá cố định (vd "chóng mặt quá" và "hơi chóng mặt" khác mức độ, LLM cần phân biệt được).

### 3.2. Kiến trúc

- **LLM classifier làm chính** — 1 lần gọi, `temperature=0` (bắt buộc, không phải tuỳ chọn — lý do: #13b đã
  chứng minh temperature ảnh hưởng trực tiếp tới độ ổn định cho tác vụ cần phán quyết nhất quán, không lặp
  lại bài học đó lần 2). Input: tin nhắn bệnh nhân + 5 tiêu chí ở 3.1.
- **Output KHÔNG phải nhị phân** (không chỉ `is_redflag: bool`) — trả về **mức độ**, dùng lại đúng từ vựng đã
  có trong hệ thống (`"Nhẹ" | "Trung bình" | "Nguy hiểm" | "Không đáng ngại"`), cộng `category` (1 trong 5
  nhóm ở 3.1, hoặc `none`), `reasoning` (ngắn, để ghi vào trace). Lý do: nếu mở rộng nhận diện ra nhiều loại
  triệu chứng hơn (đúng mục tiêu ở đây) mà vẫn giữ nhị phân, rủi ro là quá nhạy — mọi triệu chứng hơi đáng
  chú ý đều bị đẩy thẳng thành cảnh báo khẩn cấp, gây báo động giả liên tục cho gia đình/bác sĩ.
- **Tái dùng `build_level_action_node` đã có (vòng 2, mục 5b)** để xử lý theo mức độ trả về — Nhẹ → chỉ log,
  Trung bình → escalate không khẩn, Nguy hiểm → escalate khẩn + overlay. Không xây 1 đường xử lý HIGH-only
  riêng cho `safety_layer` tách biệt khỏi node đã có — tránh 2 hệ thống độc lập cùng tính "mức độ nghiêm
  trọng" theo 2 cách khác nhau, dễ trôi lệch nhau theo thời gian (đúng bài học từ việc hợp nhất `_apply_
  redflag` và `LEVEL` node vào chung 1 `trigger_emergency_escalation()` ở vòng 2). Lưu ý: khác `combine_
  severity()` (cần `drug_id`/RAG context cho 1 `dose_event` cụ thể), `safety_layer` có thể trigger từ bất kỳ
  tin nhắn nào không gắn với 1 thuốc/liều cụ thể — chỉ tái dùng tầng **xử lý theo mức độ** (`build_level_
  action_node`), không ép `safety_layer` phải chạy qua `combine_severity()`'s RAG+fallback riêng của nó.
- **Regex hiện có KHÔNG bị xoá** — giữ làm lớp phòng vệ phụ, chạy song song, kết quả cuối = mức cao nhất
  giữa LLM và regex (nếu regex trigger, tối thiểu coi là Nguy hiểm) — đúng nguyên tắc defense-in-depth đã
  dùng nhất quán (ngưỡng vector/lexical trước RRF, patch cross-drug filter giữ song song với giải pháp gốc
  ở #17).
- **Chi phí thật:** xác nhận với PM đây có phải +1 lần gọi LLM/lượt hay không (tuỳ kết quả điều tra mục 2) —
  nếu có, ghi rõ vào doc như 1 thay đổi cost đã được duyệt, không âm thầm.

### 3.3. Category mới chưa có overlay message tương ứng — CẦN CHỐT

5 hằng số overlay hiện có (`OVERDOSE`, `MISSED_DOSE`, `SYMPTOM`, `SIDE_EFFECT`, `GENERIC`) không phủ hết 5
category ở 3.1:

- **"Ý định tự hại"** — không nên dùng chung overlay với các category khác. Đề xuất: category này cần phản
  hồi **khác hẳn** về bản chất, không chỉ khác câu chữ — ngoài việc escalate cho gia đình/bác sĩ như các
  category khác, phản hồi trực tiếp cho bệnh nhân nên **kèm thông tin đường dây hỗ trợ khủng hoảng** ngay
  lập tức, không chỉ 1 overlay cảnh báo đơn thuần. Đây là khuyến nghị hành vi, không phải quyết định nội
  dung — câu chữ cụ thể vẫn `[CẦN CHỐT — PM + Phạm Thành Đạt]`, nhưng **hành vi** "phải có thông tin hỗ trợ
  trực tiếp cho bệnh nhân, không chỉ escalate" nên giữ nguyên dù wording cuối cùng là gì.
- **"Nhầm lẫn thuốc nghiêm trọng"** — chưa rõ nên map vào `GENERIC` hay cần overlay riêng. `[CẦN CHỐT — PM]`.

### 3.4. Test bắt buộc

- Re-run đúng 2 case đã biết: "muốn uống 10 viên thuốc ngủ" (phải trigger) và câu hỏi y tế hợp lệ đã có sẵn
  trong test suite (không được trigger — không regression).
- **Không tin 1 lần chạy** — đúng kỷ luật đã dùng ở case C (mục 9.3, vòng 2): chạy lại tối thiểu 20 lần cho
  case biên (câu ở ranh giới rõ/không rõ nguy hiểm), đo tỷ lệ ổn định trước khi tin.
- Test riêng cho 5 category ở 3.1, mỗi category tối thiểu 2 case (1 rõ ràng, 1 biên).
- Test OR-logic: 1 case LLM bắt được nhưng regex không bắt (ngược lại case ban đầu) và 1 case ngược lại —
  xác nhận cả 2 đường cùng góp phần, không đường nào bị tắt khi có đường kia.

---

## 4. Bug: `pending_drug_confirmation` bị treo khi safety_layer lẽ ra phải cắt ngang

**Đây là hậu quả dây chuyền từ bug ở mục 1, không phải bug độc lập** — nhưng cần fix riêng vì bản chất khác:
đây là vấn đề **thứ tự ưu tiên giữa 2 lớp**, không phải nội dung phát hiện của từng lớp.

Khi câu nguy hiểm bị hiểu nhầm thành câu hỏi thường (như đã xảy ra), hệ thống tạo `pending_drug_confirmation`
chờ xác nhận — nếu bệnh nhân không trả lời đúng khuôn có/không, mọi câu tiếp theo (kể cả câu hoàn toàn không
liên quan) bị ép qua bộ phân tích có/không cho tới khi hết TTL (30 phút). Sau khi mục 3 xong, đây vẫn là 1
rủi ro kiến trúc cần khoá lại độc lập: **nếu safety_layer trigger redflag ở BẤT KỲ thời điểm nào, phải xoá
ngay `pending_drug_confirmation` đang treo (nếu có) trước khi xử lý redflag** — không để 2 trạng thái (đang
chờ xác nhận thuốc + đang có redflag) tồn tại cùng lúc.

**Test bắt buộc — race thật, không mock timing** (đúng pattern đã dùng ở Phase 5 cho test async interruption):
giả lập 1 pending_drug_confirmation đang active, gửi tin nhắn tiếp theo là redflag rõ ràng → xác nhận (a)
redflag được xử lý đúng, (b) `pending_drug_confirmation` bị xoá, (c) tin nhắn kế tiếp sau đó được hiểu là câu
hỏi mới, không bị ép qua bộ phân tích có/không cũ.

---

## 5. Hiển thị lịch uống thuốc (`today_schedule`) — format lại, thêm dữ liệu

### 5.1. Vấn đề hiện tại

- Timestamp thô (`2026-08-09T08:00:00+00:00`) — khó đọc, và **nghi ngờ offset sai** (nếu 8:00 là giờ VN thật
  thì offset đúng phải là `+07:00`, không phải `+00:00`). **Kiểm tra ngay, ưu tiên cao nhất trong mục này:**
  `dose_event.scheduled_at` lưu là giờ VN naive hay UTC thật? Nếu có lệch timezone, **cascade nhắc lại của
  mục 4 vòng 2** (APScheduler, mốc 15→+10→+10→+10 phút) đang dùng chung datetime này — lệch timezone ở đây
  có thể khiến giờ nhắc lại sai lệch nhiều tiếng so với ý định. Xác nhận và sửa tận gốc lưu trữ nếu sai, không
  chỉ sửa ở tầng hiển thị.
- Hỏi "buổi sáng" nhưng nhận về lịch cả ngày — node `today_schedule` không có bước lọc theo buổi.
- Tên thuốc hiển thị nguyên dạng SKU (`"Solufemo 100mg Hataphar 20 ỐNG"`) thay vì tên ngắn gọn bệnh nhân quen
  dùng.
- Không có thông tin **thời điểm dùng** (trước/sau ăn...) trong lịch — hiện chỉ join tới `dose_event`, chưa
  join tới `PrescriptionDTO.items[].thoi_diem_dung`.

### 5.2. Khung giờ buổi — đã chốt

```
Sáng:  5h  – 11h
Trưa:  11h – 13h
Chiều: 13h – 18h
Tối:   18h – 24h (0h)
```

Dùng chung 1 bảng khung giờ này cho cả việc lọc câu hỏi lẫn hiển thị — không xây 2 lần.

### 5.3. Lọc theo buổi — thêm bước so khớp từ khoá thuần, KHÔNG cần LLM

Bắt các từ "sáng"/"trưa"/"chiều"/"tối" trong câu hỏi bằng so khớp chuỗi đơn giản, map sang khung giờ ở 5.2,
filter `dose_event` theo đúng khung giờ đó. Không khớp từ khoá nào → giữ hành vi cũ (trả cả ngày). Giữ đúng
quyết định gốc "domain này không cần LLM" (mục 6, thiết kế gốc) — đây là bước filter cứng, không phải suy
luận ngôn ngữ.

### 5.4. Format hiển thị — theo đúng ví dụ PM đưa

**Khi hỏi cả ngày ("hôm nay uống thuốc gì"):**

```
Hôm nay, ngày 9 tháng 8 năm 2026

Buổi sáng, 8 giờ bạn cần uống:
- Solufemo 100mg, Silygamma 150mg, Cavinton Forte (đã uống)

Buổi trưa, 12 giờ bạn cần uống:
- Ulcersep 262.5mg (chưa uống)

Buổi chiều, 14 giờ bạn cần uống:
- Cavinton Forte (chưa uống)

Buổi tối, 20 giờ bạn cần uống:
- Silygamma 150mg, Cavinton Forte, Tearbalance (chưa uống)
```

- Ngày tháng: `"Hôm nay, ngày {D} tháng {M} năm {YYYY}"` — hàm format thuần, không LLM.
- Nếu 1 buổi có nhiều mốc giờ khác nhau (vd sáng có cả 6h và 9h) → mỗi mốc giờ 1 dòng riêng trong cùng buổi,
  sắp tăng dần.
- Tên thuốc rút gọn (bỏ hãng sản xuất + quy cách đóng gói, giữ hàm lượng nếu có) — chỉ ở tầng hiển thị, không
  đổi gì ở tầng match/lưu trữ (`drug_id` vẫn dùng tên gốc, tránh lặp lại rủi ro core-name đã gặp ở mục 5 vòng
  2 — đây thuần là format, không phải logic so khớp).

**Khi hỏi theo buổi ("buổi sáng tôi cần uống thuốc gì"):**

```
Buổi sáng bạn cần uống Solufemo 100mg, Silygamma 150mg, Cavinton Forte vào lúc 8 giờ, trước bữa ăn sáng.
```

- Thêm `thời điểm dùng` (`thoi_diem_dung` từ đơn thuốc active, join theo `drug_id`) vào cuối câu.
- Nếu các thuốc trong cùng mốc giờ có **cùng** `thoi_diem_dung` → gộp 1 câu như trên.
- Nếu **khác nhau** → liệt từng thuốc kèm thời điểm riêng, mỗi dòng 1 thuốc.
- Nếu 1 thuốc **không có** `thoi_diem_dung` trong đơn (null/rỗng) → bỏ hẳn phần đó cho thuốc đó, không hiển
  thị chỗ trống hay câu cụt nghĩa.

### 5.5. Test bắt buộc

- Case nhiều thuốc cùng giờ, cùng thời điểm dùng → gộp đúng 1 câu.
- Case nhiều thuốc cùng giờ, khác thời điểm dùng → liệt riêng từng dòng.
- Case thiếu `thoi_diem_dung` → không hiển thị cụt nghĩa.
- Case hỏi "buổi sáng" → chỉ trả buổi sáng, không lẫn buổi khác.
- Case timezone: xác nhận `scheduled_at` hiển thị đúng giờ VN thật (không lệch 7 tiếng).

---

## 6. Mở rộng intent — chào hỏi/ngoài phạm vi

Phát hiện thêm khi PM thử tay: "xin chào"/"hello" rơi vào mặc định `drug_info`, ra `"không tìm thấy thuốc
của bạn"` — sai hoàn toàn ý định người dùng.

- Thêm giá trị mới vào enum `intent` (`ConversationState`, mục 9 thiết kế gốc): `greeting` (hoặc
  `out_of_scope`, đặt tên cho rõ cả 2 trường hợp: chào hỏi thuần và câu hoàn toàn ngoài phạm vi thuốc).
- Đưa vào **cùng lần gọi `intent_classification` đã có sẵn** — không thêm LLM call mới, chỉ mở rộng tập nhãn
  classifier được phép trả về.
- Response cho `greeting`: câu chào tự nhiên + gợi ý ngắn gọn 3 việc chatbot làm được (hỏi thuốc, xem lịch
  hôm nay, báo đã/chưa uống) — cố định, không cần LLM sinh (tiết kiệm, và tránh rủi ro tự suy diễn không cần
  thiết cho 1 câu chào đơn giản).

**Test bắt buộc:** "xin chào", "hello", "chào bạn", và tối thiểu 1 câu hoàn toàn ngoài phạm vi (vd hỏi thời
tiết) — không rơi vào luồng tra thuốc.

### 6.1. Quick-reply buttons — mở rộng ra ngoài phạm vi chào hỏi

Không chỉ cho greeting — cùng cơ chế nên tái dùng cho: xác nhận thuốc (mục 5 vòng 2 — nút "Có"/"Không", hoặc
chọn 1 trong top-3 + "Không tìm thấy"), lọc buổi (mục 5 vòng 3 — nút "Sáng"/"Trưa"/"Chiều"/"Tối"). Khi bệnh
nhân bấm, gửi lên đúng 1 chuỗi cố định — giảm phụ thuộc vào độ chính xác của việc phân tích câu gõ tự do
(mục 8), dù vẫn cần giữ nguyên hỗ trợ gõ tay cho bệnh nhân không bấm nút.

**Cần thêm field mới trong response API** (`quick_replies: list[str]`) — đây là thay đổi **API contract**,
ảnh hưởng team app đang xây giao diện. `[CẦN CHỐT — thống nhất shape với team app]`, cùng loại quyết định
như endpoint escalation-status ở mục 4 vòng 2, không tự chốt 1 mình phía backend.

---

## 7. Lịch sử chat — tách "hiển thị" khỏi "ngữ cảnh dùng để trả lời"

Phát hiện: hỏi tác dụng phụ thuốc A, rồi hỏi thuốc B, rồi hỏi "tác dụng phụ của thuốc đấy" (ý định quay lại
thuốc trước) — hệ thống không có gì để hiểu "thuốc đấy" là thuốc nào, vì mỗi lượt xử lý độc lập hoàn toàn.

PM đề xuất ban đầu: lịch sử chat kiểu Claude (nhớ tới khi user xoá). **Đã điều chỉnh lại** — mô hình "nhớ vô
thời hạn tới khi xoá" phù hợp với Claude vì người dùng tự nhiên tạo đoạn chat mới liên tục (có điểm reset rõ
ràng theo nhiệm vụ). VMEC-04 khác: 1 bệnh nhân trò chuyện liên tục hàng tháng/năm, không có điểm reset tự
nhiên ngoài việc user tự xoá (hiếm khi xảy ra) — nếu đưa toàn bộ lịch sử vào mỗi lần gọi LLM, chi phí tăng vô
hạn theo thời gian, và ngữ cảnh y tế cũ (thuốc tuần trước) có thể trộn nhầm vào câu trả lời hiện tại.

**Thiết kế: tách 2 việc khác nhau, dùng 2 cơ chế khác nhau.**

### 7.1. Lịch sử hiển thị cho bệnh nhân — đầy đủ, giữ tới khi xoá

- Bảng mới `chat_messages` (`patient_id`, `role`, `content`, `created_at`) — lưu đầy đủ mọi tin nhắn, không
  giới hạn thời gian.
- Chỉ dùng để **hiển thị lại** cho bệnh nhân xem (giống lịch sử chat Claude) — **không** đưa vào LLM. Rẻ, vì
  chỉ là đọc dữ liệu đã lưu.
- "Xoá đoạn chat" = **ẩn khỏi màn hình bệnh nhân** (soft-delete), **không xoá `audit_log`** — 2 kho dữ liệu
  khác mục đích (đúng nguyên tắc đã áp dụng ở log từ chối thuốc §5.4 vòng 2: audit cần giữ nguyên cho bác
  sĩ/đội kỹ thuật xem theo #7, không phụ thuộc việc bệnh nhân có xoá màn hình chat của họ hay không).
  `[CẦN CHỐT — PM/mentor]`: chính sách có cho phép xoá vĩnh viễn dữ liệu y tế hay chỉ ẩn — đây là câu hỏi
  chính sách, không phải kỹ thuật thuần.

### 7.2. Ngữ cảnh dùng để trả lời — cửa sổ trượt có giới hạn, thay thế `last_discussed_drug_id`

- Khi gọi `intent_classification`/`answer_generation`, đưa vào **toàn bộ tin nhắn trong 15 phút gần nhất**
  (tính từ tin nhắn hiện tại lùi lại), lấy từ `chat_messages` (7.1). **Đã chốt: 15 phút**, dùng tiêu chí thời gian
  thuần, không giới hạn thêm theo số lượng tin nhắn — phù hợp hơn cửa sổ đếm số tin nhắn vì bám sát đúng lý
  do đưa ra ở trên (ngữ cảnh y tế cũ dễ gây nhầm lẫn, nên giới hạn theo "gần đây" tự nhiên hơn là "N tin gần
  nhất", vốn có thể trải dài nhiều giờ nếu bệnh nhân nhắn thưa).
- Cơ chế này **thay thế hoàn toàn** thiết kế `last_discussed_drug_id` (1 giá trị đơn) — cửa sổ trượt giải
  quyết được nhiều kiểu tham chiếu hơn (không chỉ "thuốc đang nói"), không cần duy trì 2 cơ chế ngữ cảnh song
  song. Không cần thêm cột `last_discussed_drug_id` vào bảng `pending_drug_confirmation` như thiết kế cũ.
- **Chi phí thật, cần biết trước khi build:** mỗi lần gọi LLM giờ tốn nhiều token đầu vào hơn hiện tại (nhiều
  tin nhắn thay vì 1) — tăng có kiểm soát (bị chặn bởi N/K), không phải tăng vô hạn như đưa toàn bộ lịch sử,
  nhưng vẫn là thay đổi cost thật, ghi rõ vào doc như đã làm với các quyết định cost khác trong dự án.

**Test bắt buộc:** chuỗi 3 lượt thật (hỏi thuốc A → hỏi thuốc B → "tác dụng phụ của thuốc đấy") → xác nhận
trả lời đúng thuốc B. Case ngoài 15 phút → không dùng ngữ cảnh cũ, xử lý như câu hỏi mới. Case "xoá đoạn
chat" → `chat_messages` bị ẩn khỏi hiển thị, nhưng `audit_log` cho đúng khoảng thời gian đó vẫn tra cứu được
đầy đủ qua tầng dành cho bác sĩ/đội kỹ thuật.

### 7.3. Dài hạn — truy xuất theo yêu cầu, KHÔNG tự động bơm vào mọi câu trả lời

**Nguyên tắc:** khác hẳn 7.2 — dài hạn không bao giờ tự động chạy trong mọi lượt, chỉ kích hoạt khi bệnh nhân
chủ động cần tới, để không tái phạm đúng rủi ro đã né ở 7.2 (chi phí không kiểm soát, ngữ cảnh cũ trộn nhầm
vào câu hỏi hiện tại) — chỉ là ở quy mô tháng/năm thay vì 15 phút, hậu quả nếu sai còn lớn hơn.

**(a) Tra cứu lịch sử theo yêu cầu — giống RAG, không phải "luôn nhớ"**
- Thêm 1 giá trị intent mới (`chat_history_query`, cùng cách mở rộng enum như mục 6's `greeting`) — khi bệnh
  nhân hỏi trực tiếp về lịch sử trò chuyện của chính họ (vd "trước đây tôi từng hỏi về thuốc gì", "tuần
  trước tôi hỏi tác dụng phụ gì nhỉ").
- Tìm trong `chat_messages` (7.1) bằng lexical/khoảng thời gian đơn giản — không cần vector search phức tạp
  như RAG thuốc (đây chỉ tìm lại tin nhắn cũ của chính 1 bệnh nhân, phạm vi nhỏ, không cần độ phức tạp đó).
- Không chạy nếu intent không phải `chat_history_query` — không có đường ngầm nào khác đưa dữ liệu dài hạn
  vào câu trả lời.

**(b) Dữ liệu dài hạn có cấu trúc, phục vụ lâm sàng — để dành vòng sau, chỉ ghi nhận hướng**
- Vd: tần suất bệnh nhân hỏi lặp lại 1 chủ đề trong nhiều tháng có thể là tín hiệu lâm sàng đáng chú ý, nên
  tổng hợp hiển thị cho bác sĩ (không phải để chatbot tự dùng trả lời bệnh nhân). Đây là tính năng cho bác
  sĩ, khác phạm vi chatbot bệnh nhân đang làm — không build trong vòng 3, chỉ ghi vào mục 10 làm hướng tương
  lai.

**Nguyên tắc an toàn bắt buộc, áp dụng cho cả (a) và (b):** không tự động biến 1 câu nói của bệnh nhân trong
chat (vd "tôi bị dị ứng penicillin") thành 1 "fact" được ghi nhớ và tự động áp dụng vào câu trả lời tương lai
mà không qua xác thực của bác sĩ — cùng nguyên tắc với #13a (không tự suy diễn). 1 câu nói ngoài luồng trong
chat không có sức nặng như dữ liệu y tế đã xác thực trong `PrescriptionDTO`. Nếu phát hiện bệnh nhân đề cập
thông tin có vẻ quan trọng về y tế (dị ứng, tiền sử bệnh...) trong chat, hướng xử lý đúng là **gợi ý bệnh
nhân xác nhận với bác sĩ**, không phải tự lưu lại và tự động dùng sau này.

**Test bắt buộc:** hỏi lịch sử ("trước đây tôi hỏi gì") → tìm đúng trong `chat_messages`, không lẫn dữ liệu
bệnh nhân khác (đúng nguyên tắc isolation đã áp dụng cho mọi tool cá nhân hoá từ Phase 5b). Câu hỏi thường
(không phải `chat_history_query`) → xác nhận dữ liệu dài hạn KHÔNG bị đưa vào ngữ cảnh, chỉ có 15 phút ngắn
hạn như 7.2.

---

## 8. Nới lỏng phân tích có/không trong luồng xác nhận thuốc (mục 5 vòng 2)

Phát hiện: bot hỏi "phải thuốc X không?", bệnh nhân trả lời "không, [tên thuốc khác]" trong cùng 1 câu — hệ
thống chỉ nhận ra "không", không xử lý luôn tên thuốc mới đi kèm, phải hỏi lại thêm 1 lượt thừa.

- Khi phát hiện "không" (decline), **chạy luôn phần còn lại của câu qua đúng fuzzy-match đã có ở §5.1/§5.2**
  để thử tìm ứng viên mới ngay trong cùng lượt — tái dùng logic đã xây, không viết matcher mới, không thêm
  LLM call.
- Nếu fuzzy-match tìm được ứng viên rõ ràng từ phần còn lại → hỏi xác nhận ứng viên mới ngay (tiết kiệm 1
  lượt so với hành vi cũ: từ chối → hỏi lại tên → xác nhận).
- Nếu không tìm được gì từ phần còn lại → giữ hành vi cũ (hỏi lại tên khác theo §5.1, hoặc hiện top-3 theo
  §5.2).

**Test bắt buộc:** case "không, [tên thuốc khác]" trong 1 câu → xác nhận đúng thuốc mới, không cần thêm lượt
hỏi lại tên. Regression: case "không" đơn thuần (không kèm tên) → vẫn giữ hành vi cũ nguyên vẹn.

---

## 9. Persona "Capy" — giọng văn thân thiện, mức độ giảm dần theo độ nghiêm trọng

PM muốn chatbot có tên riêng ("Capy"/"Capy Medi", khớp thương hiệu capybara đã có của app), giọng văn thân
thiện hơn, bớt cứng nhắc — nhưng **không áp dụng đều cho mọi loại phản hồi**. Ví dụ PM đưa ra tự thể hiện
đúng nguyên tắc cần giữ: câu chào có "<3", câu cảnh báo nguy hiểm thì nghiêm túc, không có yếu tố dễ thương.

### 9.1. Nguyên tắc: thân thiện tỉ lệ nghịch với mức độ nghiêm trọng

- **Chào hỏi, câu hỏi thông tin thuốc thông thường, lịch uống thuốc** — thân thiện, có thể dùng tên riêng
  "Capy"/"Capy Medi", biểu tượng nhẹ nhàng (vd "<3"), gọi tên bệnh nhân khi tự nhiên.
- **CLASSIFY=Taken/xác nhận thường** — thân thiện vừa phải, không cần trang trọng nhưng cũng không cần biểu
  tượng.
- **SEVERITY=Trung bình trở lên, mọi cảnh báo redflag (mục 3)** — nghiêm túc, rõ ràng, **không dùng biểu
  tượng dễ thương, không đùa cợt** — vẫn có thể giữ tên "Capy Medi" trong câu dẫn (không mất bản sắc), nhưng
  nội dung chính phải nghiêm túc, đi thẳng vào vấn đề.

### 9.2. Cá nhân hoá câu chào — cần xác nhận nguồn dữ liệu tên bệnh nhân

Ví dụ PM: `"Chào {tên_bệnh_nhân}, Capy Medi sẵn sàng chăm sóc bạn <3"` — cần tên hiển thị của bệnh nhân.
`[CẦN THÔNG TIN]`: tên bệnh nhân lấy từ đâu — có sẵn trong DB chatbot hiện tại (bảng nào?), hay cần gọi sang
hệ thống chính của app (liên quan `auth-api`, #10, cùng nguồn dữ liệu người dùng)? Nếu chưa có sẵn, giữ tạm
bản chào không có tên (`"Chào bạn, Capy Medi..."`) cho tới khi nguồn dữ liệu này rõ ràng — không tự bịa/giả
định lấy tên từ đâu.

Vẫn là template cố định (không cần LLM sinh câu chào) — chỉ thêm bước interpolate tên vào chỗ trống, đúng
tinh thần "rẻ, không thêm LLM call" đã giữ xuyên suốt mục 6.

### 9.3. Mở rộng mục 3.3 — thêm câu giải thích ngắn cho mỗi category, KHÔNG để LLM tự soạn lúc nguy hiểm

PM muốn câu cảnh báo có kèm "giải thích lý do ngắn gọn" (vd *"Capy Medi cảnh báo bạn đây là hành động nguy
hiểm. [giải thích ngắn]"*). **Không để LLM tự sinh giải thích tại thời điểm phát hiện nguy hiểm** — đúng lý
do #13a được lập ra (không tự suy diễn), áp dụng nghiêm ngặt nhất đúng lúc nhạy cảm nhất.

Thay vào đó: viết sẵn **1 câu giải thích cố định cho mỗi trong 5 category** (taxonomy mục 3.1), qua cùng quy
trình duyệt như 5 overlay message đã có (PM + Phạm Thành Đạt) — mở rộng phạm vi mục 3.3 từ "5 tiêu đề cảnh
báo" thành "5 tiêu đề + 5 câu giải thích ngắn đi kèm", vẫn giữ `# TODO [CẦN CHỐT]` cho toàn bộ, không tự viết
nội dung y khoa.

**Test bắt buộc:** với mỗi category, response cuối = đúng ghép `"Capy Medi cảnh báo bạn đây là hành động
nguy hiểm. {câu giải thích cố định của category đó}"` — không có phần nào trong câu do LLM sinh tự do tại
runtime.

### 9.4. Áp dụng persona vào phần LLM-generated (answer_generation)

- Thêm 1 đoạn ngắn vào `_ANSWER_PROMPT` mô tả giọng văn Capy (thân thiện, gần gũi, xưng "Capy"/"mình" khi
  phù hợp) — áp dụng cho câu trả lời RAG (`drug_info`), **không đổi gì về kỷ luật grounding đã có** (#13a,
  #13b vẫn nguyên vẹn — đổi giọng văn, không đổi nguồn thông tin được phép dùng).
- Các hằng số có sẵn (`TAKEN_RESPONSE`, `LOW_ACTION_RESPONSE`, `MEDIUM_ACTION_RESPONSE`...) — cập nhật câu
  chữ cho hợp giọng Capy theo đúng mức độ ở 9.1, nhưng đây vẫn là nội dung patient-facing đã/đang chờ duyệt
  — sửa câu chữ không có nghĩa là bỏ qua bước duyệt nếu nội dung đó thuộc phạm vi CẦN CHỐT đã có.

---

## 10. Thứ tự

1. Mục 2 (điều tra kiến trúc `safety_layer` — bắt buộc trước, không code gì trước khi có kết luận)
2. Mục 5.1 phần timezone (kiểm tra/sửa gốc lưu trữ) — tách riêng làm sớm vì có thể ảnh hưởng mục 4 vòng 2 đã
   đóng, cần biết sớm nếu phải mở lại phần đó
3. Mục 6 (intent chào hỏi) + mục 8 (nới lỏng có/không) — rẻ, tái dùng hạ tầng có sẵn, làm sớm cùng lúc
4. Mục 3 (safety_layer LLM-first) — ưu tiên cao nhất trong các việc "mới" liên quan an toàn
5. Mục 4 (fix pending_drug_confirmation bị treo khi có redflag)
6. Mục 7 (lịch sử chat — bảng `chat_messages`, cửa sổ ngắn hạn 15 phút, tra cứu dài hạn theo yêu cầu) — làm
   sau mục 3/4 vì cùng đụng tới `intent_classification`, gộp thay đổi vào cùng 1 lần sửa thay vì rải rác
7. Mục 5 còn lại (format hiển thị lịch, lọc buổi, thời điểm dùng)
8. Mục 9 (persona Capy) — làm SAU CÙNG, sau khi toàn bộ nội dung patient-facing khác (overlay, response
   constants) đã ổn định — đổi giọng văn 1 lần cho tất cả, tránh phải sửa đi sửa lại theo từng mục xong trước

---

**Khi nào dừng lại hỏi:** kết quả điều tra mục 2 nếu cho thấy kiến trúc khác hẳn giả định (vd không có đường
LLM nào tồn tại từ trước) — xác nhận lại phạm vi mục 3 trước khi code. Tổng cộng 6 điểm cần dừng lại (4 CẦN
CHỐT + 1 CẦN THÔNG TIN + phạm vi mở rộng), rải rác trong file, không tự chọn phương án cho bất kỳ điểm nào:

1. Mục 3.3 — nội dung overlay cho category "tự hại" — PM + Phạm Thành Đạt (**hành vi** "kèm thông tin hỗ trợ
   trực tiếp" có thể implement trước, chỉ chờ đúng câu chữ).
2. Mục 3.3 — nội dung/cách xử lý category "nhầm lẫn thuốc nghiêm trọng" — PM.
3. Mục 6.1 — shape field `quick_replies` trong response API — thống nhất với team app trước khi code phần
   trả về, không tự quyết định cấu trúc field một mình phía backend.
4. Mục 7.1 — chính sách "xoá đoạn chat" có xoá vĩnh viễn hay chỉ ẩn khỏi hiển thị — PM/mentor.
5. Mục 9.2 — `[CẦN THÔNG TIN]` nguồn dữ liệu tên hiển thị bệnh nhân — chưa có thì giữ bản chào không tên,
   không tự bịa nguồn.
6. Mục 9.3 — phạm vi mục 3.3 đã mở rộng thêm 5 câu giải thích ngắn (1/category) — cùng quy trình duyệt PM +
   Phạm Thành Đạt như 5 tiêu đề overlay, không phải nội dung mới cần quy trình riêng.
