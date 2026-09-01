# TASK-023: Chuẩn hoá phản hồi chatbot cho bệnh nhân

**Domain:** `conversation`, `backend`, `frontend`
**Owner:** Unassigned + AI
**Sprint:** Ngoài sprint (yêu cầu 2026-09-01)
**Status:** In Progress (chờ review)

## Mục tiêu (Goal)

Chuẩn hoá trải nghiệm câu trả lời của Capy cho bệnh nhân theo `soul_v3.md`: thân thiện, linh hoạt và chỉ dùng thông tin đã được hệ thống xác minh. Khi phản hồi dùng nguồn Vinmec, bệnh nhân phải nhận được liên kết nguồn; khi phản hồi về thuốc, phải có lưu ý đây chỉ là thông tin tham khảo.

## Acceptance Criteria (AC)

- [x] Câu trả lời bệnh nhân thuộc luồng thông thường dùng cách xưng hô và giọng điệu đã chốt trong `chat-bot-build/chat-bot-v3/docs/soul_v3.md`; không áp dụng tone này để thay đổi thông điệp emergency, safety hoặc trạng thái handoff cố định.
- [x] Thông tin thuốc, lịch dùng thuốc, trạng thái liều và trạng thái handoff vẫn được render nguyên văn từ dữ liệu đã xác minh; lớp hiển thị không được tự suy diễn, đổi liều, thêm chẩn đoán hoặc sửa nguồn.
- [x] Mọi câu trả lời có Vinmec Web evidence hiển thị ít nhất một liên kết Vinmec đã được truy xuất; không có evidence thì không được tạo hoặc gán link Vinmec.
- [x] Mọi câu trả lời có nội dung thông tin thuốc hiển thị câu lưu ý: `Thông tin này chỉ mang tính tham khảo, không thay thế tư vấn của bác sĩ hoặc dược sĩ.`
- [x] Không thay đổi safety policy, emergency policy hoặc cơ chế doctor handoff trong task này (ràng buộc "không sửa backend" nói chung đã được owner nới — xem Ghi chú bên dưới).

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [x] `specs/product-vision.md`
- [x] `specs/features.md` (FEAT-005, FEAT-006, FEAT-008)
- [x] `specs/business-rules.md`
- [x] `specs/api-contracts.md`
- [x] `adrs/0004-project-structure-and-coding-convention.md`
- [x] `adrs/0005-definition-of-done.md`
- [x] `adrs/0009-safety-layer-dual-classifier.md`
- [x] `adrs/0010-human-in-the-loop.md`
- [x] `chat-bot-build/chat-bot-v3/docs/soul_v3.md`
- [x] `chat-bot-build/chatbot-v2_5/V2.5-DESIGN.md`
- [x] `AGENTS.md`

## Việc đã làm

- [x] `chat-bot-build/soul.md` viết lại theo `soul_v3.md` (tự nhiên hơn, không ép template câu mẫu, giữ nguyên ranh giới "Soul không kiểm soát factual/safety/emergency/handoff").
- [x] `backend/agents/v2/model_gateway.py`: thêm hằng số `_PATIENT_PERSONA_INSTRUCTION` (rút từ `soul_v3.md` mục 1-5), chèn **thêm vào** (không xoá rule chống bịa/provenance nào có sẵn) cuối cả 2 prompt sống — `synthesize_read_only` nhánh `ModelRole.MAIN` (prompt thật đang chạy production) và `_synthesize_free_prose` nhánh `ModelRole.RENDERER` (TASK-V2.5-004 CP2, đang tắt theo `AGENT_V2_5_RENDERER_ENABLED=False` mặc định, cập nhật sẵn để nhất quán khi bật).
- [x] `backend/agents/v2/orchestrator.py`: thêm backstop xác định `_append_drug_info_disclaimer` (cùng pattern `_enforce_vinmec_provenance`/`_enforce_medical_grounding`) — nối câu lưu ý cố định vào cuối reply cho `DRUG_INFORMATION`/`PRESCRIPTION_INFORMATION`/`MEDICATION_DOSE_SAFETY` khi `status == COMPLETED`. Đặt **trước** các backstop có thể thay toàn bộ reply (vendor-leak, Vinmec correction, grounding-decline) để disclaimer chỉ bám vào text thật của model, không bao giờ dính vào câu hệ thống cố định (identity/decline/handoff).
- [x] Frontend: `citations` (đã có sẵn, backend-deterministic, chưa từng hiển thị) nay được thread qua `StoredChatMessage` (`lib/chat-history.ts`) → `appendMessage` (`app/patient/assistant/page.tsx`) → hiển thị link "Nguồn: Vinmec — {title}" trong `components/chat-message.tsx`, chỉ khi `source === "vinmec-web"` và có `url` thật — không đoán/tạo link.
- [x] Test mới: `tests/test_agent_v2_drug_info_disclaimer.py` (11 case). Cập nhật assertion ở `test_agent_v2_orchestrator.py`, `test_agent_v2_medical_grounding.py`, `test_agent_v2_vinmec_provenance.py`, `test_agent_v2_synthesis.py` cho đúng behavior mới (reply giờ có thêm disclaimer).

## Definition of Done

Áp dụng checklist chuẩn ở [`ADR-0005`](../adrs/0005-definition-of-done.md). Tiêu chí riêng:

- [x] Có bằng chứng test rằng UI không thêm/sửa claim y khoa hay URL nguồn (citation render nguyên văn từ backend, không suy diễn).
- [x] Câu trả lời về thuốc có lưu ý đúng nguyên văn (`_DRUG_INFO_DISCLAIMER`, test `test_agent_v2_drug_info_disclaimer.py`).
- [x] Link Vinmec chỉ xuất hiện khi response có Vinmec provenance hợp lệ (`source === "vinmec-web"` + `url` thật).
- [x] Các flow safety, emergency và doctor handoff không đổi (toàn bộ test suite an toàn/handoff hiện có chạy pass, không sửa).

## Ghi chú / trao đổi thêm

### Owner đã nới ràng buộc "không sửa backend" (2026-09-01)

Blocker ban đầu: production không nạp `soul.md`/`soul_v3.md` vào runtime, và với ràng buộc không sửa backend thì không thể làm model đổi giọng văn một cách đáng tin cậy (xem lịch sử Git của file này để xem bản blocker gốc).

Owner đã trực tiếp yêu cầu qua chat: cập nhật `soul.md` theo `soul_v3.md` **và ứng dụng cho chatbot trả lời thật** — tức xác nhận nới ràng buộc đó. Việc còn lại (mục "Việc đã làm" ở trên) đã sửa backend: prompt sống (`model_gateway.py`) và 1 backstop mới trong `orchestrator.py`. Safety/Emergency/Doctor Handoff không bị đụng tới (verify bằng toàn bộ test suite liên quan chạy pass không đổi kết quả).
