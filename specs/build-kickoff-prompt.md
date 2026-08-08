# Kickoff Prompt — Build VMEC-04 Chatbot/RAG (FEAT-005–008)

> Dán prompt này cho agent coding (Claude Code hoặc tương đương có quyền đọc/ghi file + chạy bash trong repo).
> Agent cần có quyền truy cập toàn bộ repo, không chỉ 1 file.

---

## 0. Vai trò và tài liệu nguồn — ĐỌC TRƯỚC KHI CODE

Bạn là engineer triển khai phần chatbot/RAG cho VMEC-04 (Capy Daily), dựa **đúng theo** thiết kế đã chốt
trong các file sau. Đây không phải bài tự thiết kế lại — mọi quyết định kiến trúc quan trọng đã có,
việc của bạn là hiện thực hoá chính xác, không tự ý đổi.

Đọc theo thứ tự trước khi viết bất kỳ dòng code nào:

1. `chatbot-rag-design.md` (toàn bộ) — tài liệu thiết kế chính, nguồn sự thật cho mọi quyết định RAG/chatbot
2. `business-rules.md` §3, §6, §7 — ngưỡng severity, redflag, audit
3. `adrs/0006-tech-stack.md`, `0008-vector-store-pgvector.md`, `0009-safety-layer-dual-classifier.md`
4. `api-contracts.md` §2 (`PrescriptionDTO`), §8 (`DrugInfoDTO`)
5. `data pharmacy/schema.json` + xem qua 2-3 file `thuoc.json` mẫu thật để hiểu field thực tế
6. `scripts/classify_severity.py` — đã chạy xong, không cần sửa trừ khi phát hiện bug

Điều chỉnh đường dẫn trên cho khớp cấu trúc thật của repo nếu khác.

**Sau khi đọc xong, việc đầu tiên: tóm tắt lại ngắn gọn 5 điểm sau để tự xác nhận hiểu đúng, trước khi code:**
- Chunking strategy: 4 chunk/thuốc theo field_group nào, vì sao `thoi_diem_dung` không vào RAG
- Retrieval: thứ tự lọc ngưỡng thô → RRF (không phải RRF trước rồi mới lọc)
- 3 tool riêng biệt trong LangGraph và lý do tách (rủi ro lộ dữ liệu bệnh nhân khác)
- Ràng buộc chi phí: 3-4 lần gọi LLM/utterance, model nào cho mọi tác vụ
- Caveat bắt buộc khi trả lời `lieu_dung`, và audit field xác nhận caveat đã chèn

Nếu tóm tắt của bạn mâu thuẫn với chính tài liệu, hoặc giữa các tài liệu mâu thuẫn nhau — **dừng lại và hỏi**,
không tự chọn phương án rồi code tiếp.

---

## 1. Nguyên tắc bắt buộc — KHÔNG được tự ý đổi

- Model LLM cho mọi tác vụ: `gpt-4o-mini` + Structured Outputs. Không đổi sang model khác trừ khi có kết quả
  `eval/` cho thấy accuracy < 85% (mục 2 design doc).
- Embedding: `text-embedding-3-small`. Vector store: `pgvector`.
- Hợp nhất retrieval: **RRF**, không phải alpha-weighting (alpha chỉ là phương án dự phòng đã ghi rõ).
- Thứ tự bắt buộc: **lọc ngưỡng thô ở từng nguồn (vector, lexical) → rồi mới RRF trên tập đã lọc**. Không
  chạy RRF trước rồi lọc sau — đây là quyết định kiến trúc đã chốt, không phải chi tiết tối ưu.
- Lexical search: `pg_trgm` trên cột đã `unaccent`, dùng `similarity()` cho `ten_thuoc` (ngắn-ngắn) và
  `word_similarity()`/`<%>` cho `noi_dung` (ngắn-dài) — không dùng lẫn 2 hàm này cho nhau.
- 3 tool LangGraph tách riêng (`tra_cuu_thuoc_chung`, `tra_cuu_lich_uong_ca_nhan`, `tra_cuu_don_thuoc_ca_nhan`)
  — không gộp logic dù có vẻ tiết kiệm code, vì rủi ro lộ dữ liệu bệnh nhân khác qua nhầm ngữ cảnh.
- Safety layer chạy **song song, độc lập**, không phải 1 node tuần tự trong graph chính.
- Mọi nhánh kết thúc đều ghi `AuditLogDTO` đầy đủ `trace`, kể cả nhánh không dùng LLM (query DB thẳng).
- `thoi_diem_dung` không bao giờ vào RAG — viết test/assertion đảm bảo field này không lọt vào chunk nào.

---

## 2. Các giá trị CHƯA CHỐT — không được tự đoán số, phải để config + hỏi lại

Đây là danh sách từ mục 10 tài liệu thiết kế. Khi code chạm tới các mục này, đặt thành **config có giá trị
đề xuất rõ ràng đánh dấu TODO**, không hardcode rải rác trong logic, và báo lại cho Architect trước khi coi
là final:

| Giá trị | Đề xuất tạm (chưa chốt) |
|---|---|
| `NGUONG_VECTOR`, `NGUONG_LEXICAL` | Cần đo phân phối thật trên tập câu hỏi out-of-domain trước khi chọn số — xem lưu ý mục 4 bên dưới, không đoán theo cảm tính |
| `k` (hằng số RRF) | 60 |
| `top_k` sau hợp nhất | 5 |
| SLA escalate mức Trung bình | ≤15 phút (đang chờ PM xác nhận ở `business-rules.md`) |
| Gộp `INTENT` + `CLASSIFY` thành 1 lần gọi LLM hay tách riêng | Tách riêng cho bản đầu, tối ưu sau nếu cần |
| Trace log hiển thị cho ai | Chỉ bác sĩ (chưa chốt chính thức) |

**Rủi ro pháp lý dữ liệu (mục 10 #9, chưa xử lý):** `data pharmacy/` crawl từ nhathuoclongchau.com.vn, chưa
có đánh giá quyền sử dụng lại nội dung ngoài phạm vi demo/nộp bài. Không tự ý mở rộng cách dùng dữ liệu này
(vd đóng gói phân phối lại, dùng cho bản public ngoài hackathon) mà không hỏi trước.

---

## 3. Thứ tự build theo phase

Mỗi phase: làm xong → chạy test → báo cáo ngắn (đã làm gì, test nào pass, có giá trị CẦN CHỐT nào bị đụng
tới không) → mới sang phase tiếp theo. Không gộp nhiều phase làm một lần commit lớn.

### Phase 0 — Xác nhận hiểu đúng thiết kế
Output: bản tóm tắt 5 điểm ở mục 0 phía trên. Không viết code ở phase này.

### Phase 1 — DB schema & extensions
- Bật extension: `pgvector`, `pg_trgm`, `unaccent`
- Bảng `drug_chunks`: `id, drug_id, danh_muc, muc_nghiem_trong, field_group, noi_dung, noi_dung_unaccent,
  ten_thuoc_unaccent, embedding vector(1536), created_at`
- Index: HNSW trên `embedding`; GIN trigram trên `noi_dung_unaccent` và `ten_thuoc_unaccent`
- Bảng `audit_log` đúng schema `AuditLogDTO` (mục 5.2) — append-only, ghi rõ trong migration/comment là
  không được UPDATE/DELETE ở tầng ứng dụng (BR-7.5)

**Definition of done:** migration chạy được, có test insert 1 chunk mẫu + 1 audit log mẫu, đọc lại đúng dữ liệu.

### Phase 2 — Chunking script (mục 3.1)
- Input: `data pharmacy/*/thuoc.json` → output: 4 chunk/thuốc theo đúng bảng field_group
- Prefix cố định mỗi chunk theo đúng format đã định
- Test bắt buộc: với 1 thuốc mẫu thật, ra đúng 4 record, đúng nội dung gộp, và **assertion `thoi_diem_dung`
  không xuất hiện trong bất kỳ chunk nào**

### Phase 3 — Embedding + cột lexical
- Batch embed toàn bộ chunk bằng `text-embedding-3-small`
- Build cột `_unaccent` bằng hàm `unaccent()` ngay trong SQL lúc insert, không build ở application layer —
  để đảm bảo cột index và cách xử lý câu hỏi lúc query dùng chung 1 logic
- Log số lượng đã embed, ước tính chi phí

### Phase 4 — Hybrid retrieval function (mục 4)
Thứ tự bắt buộc, implement đúng như đã note ở mục 1:
1. Vector search → lọc `cosine_similarity >= NGUONG_VECTOR`
2. Lexical search → lọc theo `similarity()`/`word_similarity()` tuỳ cột `>= NGUONG_LEXICAL`
3. Hợp nhất bằng RRF **chỉ trên union của (1) và (2)** — chunk qua ít nhất 1 trong 2 vẫn được tính
4. Nếu union ở bước 3 rỗng → trả "không có nguồn" ngay, không chạy RRF

**Test bắt buộc (đây là điểm dễ code sai nhất):** viết case chunk chỉ pass ngưỡng vector, KHÔNG pass ngưỡng
lexical — chunk đó phải vẫn xuất hiện trong kết quả cuối cùng, không bị loại vì thiếu điểm lexical. Nếu test
này fail, khả năng cao logic đang là AND thay vì OR ở bước 3/4.

Trả về đủ `DrugInfoDTO` với `vector_score`, `lexical_score`, `rrf_score`, `rank` (mục 5.1) — không rút gọn
còn 1 điểm tổng hợp.

### Phase 5 — LangGraph agent (mục 8-9)
- `ConversationState` đúng schema mục 9
- Node `safety_layer`: chạy async song song, không block; ghi trace dù không có redflag
- Node `intent_classification`, `retrieval` (gọi Phase 4), `prescription_lookup` (merge `thoi_diem_dung`
  từ `PrescriptionDTO.items[]` theo `drug_id`), `answer_generation`
- `answer_generation`: bắt buộc chèn caveat khi `field_group=cach_dung` có `lieu_dung`; nếu thiết kế đã bổ
  sung caveat riêng cho trường hợp không có đơn active chứa thuốc (mục 3.1), audit cả 2 caveat riêng biệt
  trong trace, không gộp thành 1 field chung
- Mỗi node ghi đúng 1 entry vào `trace` theo format mục 5.2 (step, model nếu có, input rút gọn, kết quả,
  confidence nếu có, `duration_ms`)

**Test bắt buộc:** với redflag xuất hiện giữa chừng, trace phải cho thấy đúng bước nào bị cắt ngang, không
phải trace rỗng hoặc trace giả như luồng chạy hết bình thường.

### Phase 6 — FastAPI endpoint + persist audit log ✅ (2026-08-08)
- `POST /api/v1/chat` (đổi từ `/api/v1/conversation` ghi ở đây ban đầu — khớp `api-contracts.md` §4, nguồn
  contract thật; xem lịch sử review) — chạy LangGraph 2 giai đoạn (`intent_classification` → toàn bộ node
  còn lại của cả 3 nhánh, mỗi node tự bảo vệ theo `state["intent"]`), ghi `AuditLogDTO` vào `audit_log`,
  trả response đúng shape `ChatResponse` (`reply`, `classification`, `severity` LOW/MEDIUM/HIGH,
  `safety_flag`, `needs_clarification`, `sources`)
- Test: mọi nhánh kết thúc (drug_info, today_schedule, dose_confirmation, `REFUSE`, redflag `HIGH`) đều ghi
  đủ trace + audit log — `tests/test_chat_routes.py`
- **Đã giải quyết (không còn treo):**
  - `escalate_fn` không còn là tham số optional có thể quên truyền — route handler luôn tự dựng
    `build_db_escalate_fn(db)` (ghi thật vào bảng `escalation`, không stub) ngay trong `chat()`, không có
    đường nào gọi `run_conversation()` mà thiếu nó nữa. Startup-check riêng không còn cần thiết.
  - `safety_flag` trả cho FE giờ hợp nhất **cả 2 nguồn HIGH** (`severity_en == "HIGH"`), không chỉ nguồn
    safety_layer redflag — sửa đúng theo BR-3.5 (trước đó nếu chỉ map thẳng `state["safety_flag"]`, ca HIGH
    từ SEVERITY→LEVEL sẽ không bật overlay cấp cứu cho FE). Tên field response `safety_flag` PHẢI giữ
    nguyên (api-contracts.md §4 quy định) dù ý nghĩa khác `ConversationState["safety_flag"]` nội bộ — mapping
    tường minh qua `_should_show_emergency_overlay()` (src/api/chat_routes.py), không đọc thẳng.

- **🔴 CHẶN PRODUCTION (không phải "việc để mở" thường — xem `chatbot-rag-design.md` mục 10 #10):**
  `patient_id` hiện nhận thẳng trong request body (`ConversationChatRequest`), không xác thực qua JWT —
  `auth-api` (`api-contracts.md` §1) chưa được xây, hoàn toàn chưa có timeline trong bất kỳ tài liệu nào.
  Hệ quả: bất kỳ ai gọi endpoint đều đọc/ghi được dữ liệu của `patient_id` bất kỳ họ tự gõ vào — vô hiệu hoá
  toàn bộ test cách ly 2 bệnh nhân đã làm kỹ ở Phase 5b (test đó chỉ đúng ở tầng tool, không có gì chặn ở
  tầng endpoint). **Không cho ai ngoài phạm vi thử nghiệm nội bộ chạm vào `/api/v1/chat` (kể cả demo) cho
  tới khi có tối thiểu 1 cơ chế xác thực chặn giữa request và `patient_id` được tin dùng.**

- **Vẫn còn treo, chưa tự quyết (mức thường, không chặn thử nghiệm nội bộ):**
  - `src/services/escalation.py`: `HIGH_OVERLAY_MESSAGE` vẫn là **placeholder** (xem TODO trong file) — PHẢI
    dừng lại xin PM + mentor duyệt nội dung thật (mục 10 #5 `chatbot-rag-design.md`) trước khi cho endpoint
    này nhận traffic thật với bệnh nhân.
  - Prompt LLM thật (`src/services/classification.py`: classify_intent/classify_dose/classify_severity/
    generate_answer) là **bản nháp đầu tiên**, chưa qua eval (Phase 7) — không coi là đã tối ưu.

### Phase 7 — Eval harness (`eval/`)
- Tập câu hỏi có ground truth (đúng thuốc, đúng `field_group` kỳ vọng)
- **Bắt buộc có tập câu hỏi out-of-domain cố ý** (thuốc không tồn tại trong 3688 bản ghi, gõ sai nghiêm
  trọng) — dùng tập này để đo phân phối `cosine_similarity`/`trigram_similarity` thật, từ đó chọn
  `NGUONG_VECTOR`/`NGUONG_LEXICAL` bằng số liệu, không đoán
- Đo riêng: retrieval precision/recall, tỷ lệ hallucination (câu trả lời không grounded vào chunk nào),
  tỷ lệ caveat bị thiếu khi đáng lẽ phải có

---

## 4. Lưu ý kỹ thuật khi tinh chỉnh `NGUONG_VECTOR`

`text-embedding-3-small` (và embedding OpenAI nói chung) có xu hướng anisotropy — cosine similarity giữa
2 câu **hoàn toàn không liên quan** vẫn có thể ở mức khá cao (không gần 0 như trực giác). Không chọn ngưỡng
kiểu "nghe hợp lý" (vd 0.5) mà không đo — hãy chạy embedding trên tập out-of-domain ở Phase 7 trước, xem
phân phối thật, rồi mới chốt số.

---

## 5. Khi nào phải dừng lại hỏi thay vì tự quyết

- Bất kỳ giá trị nào ở bảng mục 2 (CẦN CHỐT)
- Phát hiện mâu thuẫn giữa `chatbot-rag-design.md` và `business-rules.md`/ADR
- Cần mở rộng cách dùng `data pharmacy/` ra ngoài phạm vi demo/nộp bài (rủi ro pháp lý chưa xử lý)
- Bất kỳ thay đổi nào với kiến trúc "lọc ngưỡng thô trước RRF" — đây không phải chi tiết implementation,
  đổi nó thay đổi hành vi an toàn của cả hệ thống

---

**Bắt đầu từ Phase 0.**
