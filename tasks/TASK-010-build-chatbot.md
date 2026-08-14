# TASK-010: Build chatbot/RAG (VMEC-04) — backend + tích hợp frontend

**Domain:** `drug-knowledge` (chính) — cắt ngang `conversation`, `safety`, `escalation` (xem [`FEAT-005`](../specs/features.md#feat-005--hội-thoại-tự-nhiên--phân-loại-4-nhãn) → [`FEAT-008`](../specs/features.md#feat-008--safety-layer-song-song))
**Owner:** Nguyễn Minh Đạt + AI
**Sprint:** sprint-02
**Status:** 🔄 In Progress (backend + frontend wiring + auth thật + vòng 3 + quick_replies/banner escalation/greeting cá nhân hoá đều Done — chỉ còn #14 theo dõi thêm, không chặn)

## Mục tiêu (Goal)

Xây dựng chatbot/RAG cho bệnh nhân hỏi về thuốc, lịch uống, đơn thuốc — có safety layer song song, guardrail chống injection/rò rỉ dữ liệu, và cơ chế escalate khi phát hiện nguy hiểm. Triển khai đúng theo thiết kế đã chốt trong [`chatbot-rag-design.md`](../chat-bot-build/chatbot-rag-design.md), thực hiện theo 3 kickoff prompt (thư mục `chat-bot-build/`, đổi tên từ `specs/` ngày 2026-08-12):

- [`build-kickoff-prompt.md`](../chat-bot-build/build-kickoff-prompt.md) — Phase 0-7 (schema DB, chunking, embedding, hybrid retrieval, LangGraph agent, endpoint `/api/v1/chat`, eval harness)
- [`kickoff-prompt-vong-2.md`](../chat-bot-build/kickoff-prompt-vong-2.md) — Vòng 2 (đóng backlog mục 10: chỗ nối auth thật, overlay redflag, escalation nhắc lại, xác nhận danh tính thuốc trước khi trả lời, AI safety hardening/guardrails)
- [`kickoff-prompt-vong-3.md`](../chat-bot-build/kickoff-prompt-vong-3.md) — Vòng 3 (safety_layer LLM-first, fix bug pending_drug_confirmation treo, format lại lịch uống thuốc, intent chào hỏi, lịch sử chat, persona "Capy") — bắt nguồn từ PM thử tay thật phát hiện lỗ hổng an toàn, không phải red-team

## Acceptance Criteria (AC)

**Backend — đã merge vào `main` qua PR #7 (`51c8b7b`), đối chiếu `chatbot-rag-design.md` mục 10 và 2 kickoff prompt:**

- [x] DB schema + extension `pgvector`/`pg_trgm`/`unaccent`, bảng `drug_chunks` + `audit_log` (Phase 1)
- [x] Script chunking 4 chunk/thuốc theo `field_group`, `thoi_diem_dung` không lọt vào RAG (Phase 2, `scripts/chunk_drugs.py`)
- [x] Embedding `text-embedding-3-small` + cột lexical `_unaccent` (Phase 3, `scripts/embed_and_insert.py`)
- [x] Hybrid retrieval: lọc ngưỡng thô từng nguồn → RRF trên union (Phase 4, `backend/services/retrieval.py`)
- [x] LangGraph agent: `safety_layer` song song + node intent/retrieval/prescription_lookup/answer_generation (Phase 5, `backend/agents/`)
- [x] `POST /api/v1/chat` + `AuditLogDTO` đầy đủ trace (Phase 6, `backend/api/chat_routes.py`)
- [x] Eval harness: ground truth + out-of-domain, chốt `NGUONG_VECTOR=0.60`/`NGUONG_LEXICAL=0.55` bằng số đo thật (Phase 7, `eval/`)
- [x] `get_current_patient_id()` — chỗ nối auth thật, chưa đổi behavior (vòng 2 mục 2, `backend/api/chat_deps.py`)
- [x] 4 overlay redflag message theo công thức `CẢNH BÁO: [LOẠI] NGUY HIỂM` (vòng 2 mục 3, `backend/services/escalation.py`, giữ marker `[CẦN CHỐT]` chờ duyệt y tế)
- [x] Escalation nhắc lại t=15/25/35/45p + trạng thái `resolved` + endpoint `PATCH` xác nhận (vòng 2 mục 4, `backend/services/escalation_reminder.py`, `backend/api/escalation_routes.py`)
- [x] Xác nhận danh tính thuốc trước khi trả lời — đóng #12/#15/#17 (vòng 2 mục 5, `backend/agents/nodes/drug_confirmation_nodes.py`)
- [x] Input/output guardrails (injection, redact secret, chặn rò rỉ chéo bệnh nhân) + rate limiter + egress allowlist + bộ test red-team (vòng 2 mục 9, `backend/services/guardrails.py`, `backend/api/rate_limit.py`, `backend/egress_allowlist.py`, `eval/redteam_prompts.py`)
- [x] Tune RRF (#1/#2) — đo lại 2026-08-09, giữ nguyên ngưỡng hiện tại (vòng 2 mục 6, xem `chatbot-rag-design.md` mục 15)
- [x] Auth thật (JWT) — `TASK-010-auth-api` (Trương Quốc Trường) merge 2026-08-12, thay hẳn `X-Internal-Secret` tạm. `backend/api/security.py` đổi sang đọc JWT thật; proxy `frontend/src/app/api/chat/route.ts` đổi từ tự gắn secret sang forward nguyên header `Authorization: Bearer <token>` từ `useAuth()`
- [x] Nối chat UI của bệnh nhân (frontend) vào `POST /api/v1/chat` thật — `feature/build-chatbot`, verify end-to-end 2026-08-12 (curl thẳng `vmec-04fe-production.up.railway.app/api/chat` trả `200` kèm `reply` thật). Sửa đúng contract thật (`patient_id` bắt buộc, đọc `data.reply` thay vì `.response/.analysis` cũ)

**Vòng 3 — safety_layer LLM-first + UX (`kickoff-prompt-vong-3.md`, merge 2026-08-12, xem chi tiết `chatbot-rag-design.md` mục 10 #24-#31 và `chat-bot-build/vong-3-investigation.md`):**

- [x] **#26 — Việc lớn nhất vòng 3.** Điều tra kiến trúc phát hiện production **trước đó không có lớp LLM nào chạy trong `safety_layer` cả** (`llm_classifier` chưa từng được cắm giá trị thật dù interface injectable đã có sẵn) — đây là lý do gốc câu "muốn uống 10 viên thuốc ngủ" lọt qua, không phải 1 case regex trượt. Đã cắm LLM classifier thật (`temperature=0`, 5 category, trả về mức độ Nhẹ/Trung bình/Nguy hiểm thay vì nhị phân), regex cũ giữ song song làm lớp phụ (lấy mức cao nhất)
- [x] #31 — "Trung bình → escalate không khẩn" cho 2 category `self_harm`/`clinical_symptom`, chỉ báo kênh family (bác sĩ xem qua trace, không chủ động báo), bệnh nhân nhận 1 câu ghi nhận nhẹ
- [x] Fix bug dây chuyền: `pending_drug_confirmation` bị treo khi safety_layer lẽ ra phải cắt ngang (mục 4 kickoff vòng 3)
- [x] #24 — bug timezone thật: seed script dùng `datetime.now(UTC).replace(hour=8)` giữ `tzinfo=UTC` nên lệch 7 tiếng so với giờ VN — đã sửa dùng `VN_TZ`. **Còn nợ:** data cũ đã seed trên Railway trước fix cần seed lại
- [x] #28 — viết lại `build_today_schedule_node`: lọc đúng ngày hôm nay (trước đây trả cả lịch sử), lọc theo buổi, format lại theo mẫu PM, tên thuốc rút gọn, ghép `thời điểm dùng`. Phát hiện + sửa thêm 1 bug thật: `_detect_requested_buoi` bản đầu so khớp trên chuỗi đã bỏ dấu khiến "tôi" và "tối" trùng nhau — gần như mọi câu có chữ "tôi" bị hiểu nhầm hỏi riêng buổi tối
- [x] #25 — intent `greeting`/`out_of_scope` (gộp 1 nhãn) cho "xin chào"/câu ngoài phạm vi thuốc — trước đó rơi nhầm vào `drug_info`; nới lỏng luồng xác nhận thuốc: "không, [tên thuốc khác]" xử lý luôn trong 1 lượt
- [x] #27 — bảng `chat_messages` (migration `0009`) tách 2 cơ chế: lưu đầy đủ để hiển thị lại cho bệnh nhân (soft-delete, không đụng `audit_log`) khác với cửa sổ ngữ cảnh ngắn hạn 15 phút dùng để trả lời (thay hẳn `last_discussed_drug_id`); intent `chat_history_query` cho tra cứu dài hạn theo yêu cầu, không tự động bơm vào mọi câu trả lời
- [x] #29 — persona "Capy" (thân thiện tỉ lệ nghịch mức độ nghiêm trọng), 5 câu giải thích/category (`CATEGORY_EXPLANATIONS`)
- [x] #18/#19/#20/#23 — 4 điểm `[CẦN CHỐT]` gốc của vòng 3 đã chốt đầy đủ 2026-08-12 (PM + Phạm Thành Đạt), gỡ hết marker `# TODO [CẦN CHỐT]` liên quan
- [x] #30 — ghi nhận rủi ro tồn dư hệ thống: `temperature=0` giảm nhưng không triệt tiêu hoàn toàn dao động giữa các lần gọi LLM (đo được ở 2/5 category) — áp dụng cho mọi tác vụ phân loại LLM trong dự án, không riêng safety_layer

**Hoàn tất 2026-08-13 — PM tự quyết định shape (không chờ team app), merge `feature/build-chatbot` vào `main` mới (auth-api thật + prescription-hitl-ui) trước khi làm:**

- [x] Banner đề xuất gọi cấp cứu — `GET /api/v1/escalations/current` (vòng 2 mục 4 ý 4), trả `{status, severity, reminder_count, created_at}` hoặc `null`, dùng lại đúng field có sẵn trên `Escalation`, không thêm cột mới. Test riêng cho case bệnh nhân không đọc được escalation của người khác qua query string
- [x] #22 — `quick_replies: list[str] | None` trong `ConversationChatResponse`. Suy tập trung ở 1 hàm `_infer_quick_replies()` (`drug_confirmation_nodes.py`) dựa theo `stage`, không sửa 24 điểm tạo `_StepResult` rải rác — an toàn hơn, tránh lệch thứ tự tham số. Gắn cho: câu hỏi Có/Không xác nhận thuốc, menu top-3, 3 gợi ý ở greeting
- [x] 2 endpoint `chat/history*` (#27) — giữ nguyên shape đã có từ vòng 3, chỉ sửa lỗ hổng bảo mật phát sinh khi merge (xem "Ghi chú" bên dưới), không đổi contract
- [x] #21 — `Patient.full_name` (có thật từ `TASK-010-auth-api`) giờ dùng cá nhân hoá câu chào, fallback về bản không tên khi patient_id không khớp dòng `Patient` nào (Patient.id chưa có FK bắt buộc, có chủ đích)

**Còn mở — chưa Done hẳn:**

- [ ] #14 (precision@1 field_group thấp ở nhánh ngoài đơn) — để mở, không chặn, theo dõi thêm (xem `chatbot-rag-design.md` mục 15)

**Vòng 4 — cải thiện chất lượng chatbot (`kickoff-prompt-vong-4.md`, bắt đầu 2026-08-13):**

- [x] Điều tra routing câu ngoài phạm vi trong lúc chờ xác nhận thuốc: nguyên nhân là hai state reply-parsing tin mọi văn bản là tên/mô tả thuốc, không phải `intent_classification`; LLM gate nhị phân đã chặn trước search, có unit/E2E/eval thật.
- [x] Fuzzy 2 tầng cho định danh thuốc ngoài đơn: dùng `similarity(ten_thuoc_unaccent)` lấy top-5; chỉ bỏ qua LLM chọn ứng viên khi `top1 >= 0.25` và `top1 - top2 >= 0.05`; mọi nhánh vẫn phải hỏi bệnh nhân xác nhận.
- [x] Bổ sung regression an toàn cho bốn câu hỏi giả định quá liều đã xác minh sau deploy Vòng 3.
- [x] Match triệu chứng với chunk `tac_dung_phu` của thuốc trong đơn vào audit trace; không kết luận nguyên nhân cho bệnh nhân và vẫn ghi entry này khi safety redflag cắt luồng. Cosine `0.20` chỉ lọc candidate, LLM nhị phân `temperature=0` xác minh match; eval live 12/12 đúng, FP=0/FN=0.
- [x] Tóm tắt hội thoại độc lập theo giờ cho bệnh nhân có hoạt động, chỉ dùng khi `chat_history_query` yêu cầu hoặc dashboard tương lai; không đưa vào prompt intent/answer tự động.
- [x] Áp dụng `soul.md` đúng phạm vi patient-facing: restyle Nhóm A, giữ nguyên tuyệt đối escalation Nhóm B; `answer_generation`/summary dùng persona Capy nhưng intent/safety classifier không dùng. Static regression + live check tiếng Anh/c3 đã pass, báo cáo ở `eval/soul_persona_report.json`.

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [ ] [`chatbot-rag-design.md`](../chat-bot-build/chatbot-rag-design.md) (toàn bộ) — nguồn thiết kế chính
- [ ] [`build-kickoff-prompt.md`](../chat-bot-build/build-kickoff-prompt.md) + [`kickoff-prompt-vong-2.md`](../chat-bot-build/kickoff-prompt-vong-2.md) + [`kickoff-prompt-vong-3.md`](../chat-bot-build/kickoff-prompt-vong-3.md)
- [ ] [`chat-bot-build/vong-3-investigation.md`](../chat-bot-build/vong-3-investigation.md) — kết quả điều tra kiến trúc `safety_layer` thật trước khi vòng 3 code (mục 2 kickoff vòng 3 bắt buộc)
- [ ] [`business-rules.md`](../specs/business-rules.md) §3, §6, §7
- [ ] [`adrs/0006-tech-stack.md`](../adrs/0006-tech-stack.md), [`0008-vector-store-pgvector.md`](../adrs/0008-vector-store-pgvector.md), [`0009-safety-layer-dual-classifier.md`](../adrs/0009-safety-layer-dual-classifier.md)
- [ ] [`api-contracts.md`](../specs/api-contracts.md) §2 (`PrescriptionDTO`), §4 (chat), §6 (`escalation-api`), §8 (`DrugInfoDTO`)
- [ ] `AGENTS.md`

## Gợi ý chia subtask (AI tự cập nhật khi bắt đầu)

Phần build chính (Phase 0-7, vòng 2, vòng 3, auth thật, frontend wiring) đã Done — subtask còn lại chỉ xoay quanh mục "Còn mở":

- [ ] Trao đổi với team app chốt shape `quick_replies` (#22) + 2 endpoint `chat/history*` (#27) + endpoint trạng thái escalation cho banner (vòng 2 mục 4 ý 4) — gộp thành 1 buổi trao đổi thay vì 3 lần riêng lẻ, vì cùng loại quyết định "shape API chờ FE xác nhận"
- [ ] Có nguồn dữ liệu tên bệnh nhân thật → gỡ chốt tạm #21, thêm cá nhân hoá câu chào
- [ ] Theo dõi thêm #14 (precision@1), không cần hành động ngay

## Definition of Done

Áp dụng checklist chuẩn ở [`ADR-0005`](../adrs/0005-definition-of-done.md). Tiêu chí riêng của task này:

- [ ] Phần "Còn mở" ở AC phải Done hoặc được chuyển thành task con riêng có AC/DoD rõ ràng trước khi đóng task này
- [ ] Không merge auth tạm (`X-Internal-Secret`) ra ngoài phạm vi thử nghiệm nội bộ

## Ghi chú / trao đổi thêm

- Phần lớn backend (Phase 0-7 + toàn bộ vòng 2 trừ vài mục CẦN CHỐT) đã merge vào `main` qua PR #7 (`51c8b7b feat: add FastAPI + LangGraph medication reminder backend (Phase 1-7 + round 2 AI safety hardening)`) **trước khi** file task này được tạo — file này được viết hồi cứu để `/tasks/` phản ánh đúng luật spec-driven ở `AGENTS.md` §2, không phải để mở lại việc đã Done.
- 2026-08-10: branch `feature/TASK-010-build-chat-bot` gốc (4 commit đầu tiên nối UI) bị xoá theo quyết định của owner, không merge — phần nối UI đã **làm lại từ đầu** trên branch `feature/build-chatbot` (khác branch, cùng tên mục đích), xong và verify end-to-end 2026-08-12.
- **`🔴 CHẶN PRODUCTION` đã đóng 2026-08-12:** `patient_id` từng đọc thẳng từ request body qua `X-Internal-Secret` tạm — `TASK-010-auth-api` (Trương Quốc Trường) đã xây xong JWT thật, thay hẳn cơ chế tạm này. Không còn là rủi ro mở.
- 2026-08-12: 3 file kickoff (`build-kickoff-prompt.md`, `chatbot-rag-design.md`, `kickoff-prompt-vong-2.md`) chuyển từ `specs/` sang thư mục riêng `chat-bot-build/` (cùng lúc thêm `kickoff-prompt-vong-3.md`) — mọi link trong file task này đã cập nhật theo đường dẫn mới.
- Vòng 3 bắt nguồn từ **PM tự thử tay chatbot thật** (không phải quy trình test/red-team), phát hiện 1 lỗ hổng an toàn thật (safety_layer thực chất chưa từng có lớp LLM nào chạy — #26) và nhiều vấn đề UX (`today_schedule`, greeting) — bài học: thử tay định kỳ vẫn cần thiết dù đã có eval/test suite tự động.
- **2026-08-13, merge `feature/build-chatbot` (vòng 3) vào `main` mới:** branch vòng 3 tách ra từ trước khi `TASK-010-auth-api`/`prescription-hitl-ui` merge, nên phải hợp nhất lại. Dùng **merge**, không phải rebase — rebase thử trước tiên bị conflict ở tận các commit rất cũ (crawler dữ liệu thuốc, không liên quan chatbot) vì replay lại từng bước lịch sử gốc trong khi `main` đã squash — abort, đổi sang merge (chỉ giải quyết khác biệt ở trạng thái cuối). 3 conflict thật: `backend/api/security.py` (hợp nhất `_HasPatientId` Protocol của vòng 3 với `CurrentUser`/JWT của auth-api), `backend/db/models.py` (2 class độc lập `ChatMessage` vs `PhotoVerification`+`Account`, giữ cả 2), và trùng số migration `0009` (đổi `chat_messages` thành `0014`, giữ chuỗi tuyến tính).
- **Lỗ hổng bảo mật phát hiện lúc merge (đã sửa cùng lúc):** merge tự động giữ nguyên `Depends(require_internal_secret)` ở 2 endpoint `chat/history*` (thêm ở vòng 3, trước khi có JWT) — hàm này không còn được import trong `chat_routes.py` (auth-api đã đổi sang JWT cho endpoint `/chat` chính), lẽ ra sẽ `NameError` khi load module. Về bản chất còn tệ hơn crash: nếu lỡ chạy được, **bất kỳ ai biết `X-Internal-Secret` (không cần biết danh tính) đọc được lịch sử chat của bất kỳ `patient_id` nào tự gõ vào body** — đã sửa cả 2 sang `Depends(get_current_user)` + JWT thật, khớp đúng nguyên tắc "1 CHỖ NỐI DUY NHẤT" của `get_current_patient_id()`.
