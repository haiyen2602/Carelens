# Chuẩn bị Vòng 3 — điều tra kiến trúc thật + readiness từng mục

> Viết trước khi code, đúng quy ước dự án (kickoff-prompt-vong-3.md mục 0: "không code trước, viết tài
> liệu sau"). Toàn bộ phát hiện dưới đây xác nhận qua đọc code `backend/` thật + `git log`/`git status`,
> không suy đoán từ mô tả trong kickoff prompt. Trạng thái deploy: đã xác nhận qua phiên làm việc trước —
> Railway (project `VMEC-04`), 3 service `BE`/`FE`/`DB`, `src/` đã đổi tên hẳn thành `backend/`, migration
> tới `0008`, `git status backend/` sạch (không có gì dở dang chưa commit).

---

## Mục 2 — Điều tra kiến trúc `safety_layer` thật (BẮT BUỘC trước mục 3, đã xong)

### Câu hỏi 1: "Đường LLM chạy song song với regex là gì — LLM call độc lập hay fallback hẹp?"

**Trả lời, xác nhận bằng code, không suy đoán:**

- `backend/services/safety.py::check_safety(utterance, llm_classifier=None)` — keyword layer LUÔN chạy
  trước; chỉ gọi `llm_classifier` nếu **keyword layer sạch VÀ có truyền `llm_classifier`**.
- `backend/agents/orchestrator.py::default_safety_check()` gọi `check_safety(utterance)` — **KHÔNG
  truyền `llm_classifier`**.
- `backend/api/chat_deps.py::get_chat_services()` — implementation THẬT dùng cho production — wire
  `safety_check=default_safety_check`.

**Kết luận, quan trọng nhất của cả cuộc điều tra: hiện tại production KHÔNG CÓ đường LLM nào chạy trong
`safety_layer` cả.** `LLMSafetyClassifier` (Protocol) tồn tại như 1 chỗ nối injectable, nhưng chưa từng
được cắm giá trị thật ở đường sống. Mọi nhắc tới `matched_group=None` (case LLM flag nhưng không khớp
keyword group) trong `chatbot-rag-design.md` mục 7.1/10 mô tả 1 khả năng kiến trúc đã CHUẨN BỊ SẴN chỗ
nối, không phải hành vi đang chạy thật — cần sửa lại cách hiểu này trước khi báo cáo lại design doc.

### Câu hỏi 2: "Vì sao 'muốn uống 10 viên thuốc ngủ' lọt qua?"

Đúng như nghi ngờ trong kickoff — **không phải lỗi 1 đường LLM có sẵn nhưng bắt trượt, mà vì hoàn toàn
không có đường nào khác ngoài keyword regex để bắt.** `_QUANTITY_RE` (số lượng + đơn vị) bắt đúng "10
viên", nhưng `_OVERDOSE_RISK_PHRASES` yêu cầu 1 cụm từ rủi ro tường minh ("uống hết"/"uống gấp đôi"/"có
sao không"...) — câu "muốn uống 10 viên thuốc ngủ" không chứa cụm nào trong danh sách, AND-logic giữa 2
điều kiện độc lập không thoả, keyword layer trả `is_redflag=False`, và vì không có LLM nào chạy tiếp, câu
này lọt thẳng qua `safety_layer` không bị chặn.

### Câu hỏi 3: "`safety_layer` chạy đồng bộ hay bất đồng bộ, cơ chế race hiện tại?"

Xác nhận đúng như thiết kế mục 8 gốc: `asyncio.create_task(safety_check(...))` chạy song song thật,
kiểm tra `safety_task.done()` ở ranh giới giữa MỖI cặp node liên tiếp trong `run_conversation()`
(`backend/agents/orchestrator.py`), cộng 1 lần kiểm tra cuối sau node cuối cùng. Không phải bug, không
cần sửa phần này.

### Hệ quả cho mục 3 (safety_layer LLM-first) — không đổi phạm vi, chỉ đổi độ khẩn

Vì hiện tại production hoàn toàn không có lớp LLM nào (0%, không phải "1 lớp có nhưng yếu"), việc ở mục 3
không phải "nâng cấp" mà là **xây mới hoàn toàn 1 lần gọi LLM classifier**, cắm vào đúng chỗ nối
`llm_classifier` đã có sẵn interface (`LLMSafetyClassifier` Protocol) — kiến trúc injection đã đúng chỗ,
chỉ thiếu implementation thật + wiring vào `get_chat_services()`. Không cần đổi `orchestrator.py`/
`check_safety()`, chỉ cần: (a) viết hàm LLM classifier thật theo taxonomy mục 3.1, (b) đổi
`default_safety_check` (hoặc thêm 1 phiên bản mới) để truyền `llm_classifier` đó, (c) wire vào
`chat_deps.py`.

---

## Bug xác nhận riêng — mục 4 (`pending_drug_confirmation` treo khi có redflag)

Đọc `backend/api/chat_routes.py` xác nhận: khi có `pending_drug_confirmation` đang chờ, request VẪN chạy
qua `run_conversation()` với `safety_check` đầy đủ (dòng 137-142) — safety_layer **có** chạy song song
đúng như comment ghi. Nhưng khi redflag trigger giữa lúc này, `_apply_redflag()`
(`backend/agents/orchestrator.py`) chỉ set `response`/`severity`/`trace`, **không có bất kỳ lệnh nào xoá
dòng `pending_drug_confirmation` khỏi DB.** Xác nhận bằng cách đọc toàn bộ `chat_routes.py` — không có
lệnh xoá pending ở nhánh redflag tại bất kỳ đâu. Đúng như vòng 3 mô tả: bug thật, nằm ở **thiếu 1 side
effect** (dọn dẹp state chéo), không phải sai logic phát hiện redflag.

---

## Readiness từng mục — trạng thái CHƯA làm, xác nhận bằng code (không phải suy đoán từ mô tả)

| Mục | Nội dung | Trạng thái xác nhận |
|---|---|---|
| 3 | Safety_layer LLM-first | **0% — chưa có gì**, xem điều tra trên |
| 4 | Fix treo `pending_drug_confirmation` khi redflag | **Chưa sửa** — bug xác nhận còn nguyên |
| 5.1 | Timezone `scheduled_at` | Cột đã đúng kiểu `DateTime(timezone=True)` (Postgres `TIMESTAMPTZ`) — **schema không sai**, nhưng CHƯA xác nhận giá trị ghi vào lúc tạo `dose_event` (`scripts/seed_demo_patient.py` hoặc nơi tạo record) có đúng offset VN thật hay không — cần query DB thật, chưa làm trong lần chuẩn bị này |
| 5.3 | Lọc theo buổi | **Chưa có** — `build_today_schedule_node` không có bước lọc nào theo "sáng/trưa/chiều/tối" |
| 5.4 | Format hiển thị + thời điểm dùng | **Chưa có** — hiện trả nguyên `scheduled_at.isoformat()` thô + `ten_thuoc` nguyên dạng, không gộp theo buổi, không join `thoi_diem_dung` |
| 6 | Intent `greeting`/`out_of_scope` | **Chưa có** — `_INTENT_PROMPT` (`backend/services/classification.py`) chỉ có đúng 3 nhãn gốc (`drug_info`/`today_schedule`/`dose_confirmation`), khớp `Literal` trong `state.py` |
| 6.1 | `quick_replies` field | **Chưa có** trong `ConversationChatResponse` (`backend/models/schemas.py`, chưa kiểm tra kỹ nhưng không thấy nhắc trong `chat_routes.py::_to_response`) |
| 7 | Bảng `chat_messages` + cửa sổ 15 phút | **Chưa có gì** — không có model, không có migration (dừng ở `0008`), không grep thấy `chat_messages`/`ChatMessage` ở đâu trong `backend/` |
| 8 | Nới lỏng "không, [tên khác]" | **Chưa có** — `drug_confirmation_nodes.py` chỉ có `UNPARSEABLE_YES_NO_MESSAGE`, không có logic chạy tiếp fuzzy-match phần còn lại của câu |
| 9 | Persona "Capy" | **Chưa có** — chưa kiểm tra sâu response constants, nhưng theo đúng thứ tự mục 10 (làm sau cùng), hợp lý là chưa động tới |

**Kết luận chung: toàn bộ vòng 3 chưa bắt đầu code — đúng như `reonboarding-prompt.md` đã cảnh báo trước
đó ("việc đang chờ làm, chưa bắt đầu").** Không có phát hiện nào cho thấy 1 phần đã làm dở/làm nhầm.

---

## 6 điểm PHẢI dừng lại hỏi trước khi code — nhắc lại đầy đủ từ kickoff, chưa có câu trả lời nào

1. **Nội dung overlay category "ý định tự hại"** (mục 3.3) — PM + Phạm Thành Đạt. Hành vi "kèm thông tin
   hỗ trợ khủng hoảng trực tiếp cho bệnh nhân" có thể code trước, chỉ câu chữ cụ thể còn chờ.
2. **Category "nhầm lẫn thuốc nghiêm trọng"** — map vào GENERIC hay overlay riêng — PM.
3. **Shape field `quick_replies`** (mục 6.1) — thống nhất với team app trước khi code phần trả response,
   không tự quyết 1 mình phía backend.
4. **Chính sách "xoá đoạn chat"** (mục 7.1) — xoá vĩnh viễn hay chỉ ẩn khỏi hiển thị — PM/mentor.
5. **Nguồn dữ liệu tên hiển thị bệnh nhân** (mục 9.2) — chưa biết bảng nào/API nào có tên bệnh nhân, giữ
   bản chào không tên nếu chưa rõ, không tự bịa nguồn.
6. **Phạm vi mục 3.3 mở rộng thêm 5 câu giải thích ngắn/category** (mục 9.3) — cùng quy trình duyệt PM +
   Phạm Thành Đạt, không phải nội dung mới cần quy trình khác.

---

## Thứ tự làm — giữ nguyên đúng như kickoff đã chốt, không tự đổi

1. Mục 2 (điều tra — **đã xong**, xem trên)
2. Mục 5.1 timezone — kiểm tra giá trị thật trong DB trước (query trực tiếp `dose_event.scheduled_at`
   của 1 vài record, so với giờ thật đã biết) — làm sớm vì có thể ảnh hưởng cascade nhắc lại escalation
   đã đóng ở vòng 2
3. Mục 6 (intent chào hỏi) + mục 8 (nới lỏng có/không) — rẻ, tái dùng hạ tầng có sẵn
4. Mục 3 (safety_layer LLM-first) — ưu tiên an toàn cao nhất
5. Mục 4 (fix treo pending khi redflag)
6. Mục 7 (chat history)
7. Mục 5 còn lại (format hiển thị, lọc buổi, thời điểm dùng)
8. Mục 9 (persona Capy) — sau cùng

---

## Việc cần làm NGAY, trước khi giao cho agent code thật

- ~~Chốt/xin trả lời 6 điểm dừng lại ở trên~~ — **ĐÃ CHỐT 2026-08-12** (PM, trong phiên làm việc này),
  ghi vào `chatbot-rag-design.md` mục 10 #18–#23. Tóm tắt:
  - #18: overlay "tự hại" = cảnh báo nguy hiểm + khuyên gặp bác sĩ, KHÔNG hotline — giữ TODO chờ Phạm
    Thành Đạt duyệt thêm
  - #19: category "nhầm lẫn thuốc" → dùng chung GENERIC_OVERLAY_MESSAGE
  - #20: xoá đoạn chat = chỉ ẩn (soft-delete), audit_log không đổi
  - #21: tên bệnh nhân chưa có nguồn → giữ bản chào không tên
  - #22: `quick_replies: list[str]` — backend đề xuất trước, PM mang qua team app xác nhận sau
  - #23: phạm vi mở rộng 3.3 (5 câu giải thích/category) — PM duyệt scope, nội dung chờ Phạm Thành Đạt
- Query DB thật (đã trỏ Railway) xác nhận `dose_event.scheduled_at` có đúng giờ VN hay lệch — 5 phút,
  chặn trước mục 5.1 thật sự bắt đầu. **Còn treo, chưa làm.**
