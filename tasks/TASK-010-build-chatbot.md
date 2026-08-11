# TASK-010: Build chatbot/RAG (VMEC-04) — backend + tích hợp frontend

**Domain:** `drug-knowledge` (chính) — cắt ngang `conversation`, `safety`, `escalation` (xem [`FEAT-005`](../specs/features.md#feat-005--hội-thoại-tự-nhiên--phân-loại-4-nhãn) → [`FEAT-008`](../specs/features.md#feat-008--safety-layer-song-song))
**Owner:** Nguyễn Minh Đạt + AI
**Sprint:** sprint-02
**Status:** 🔄 In Progress (backend Done, frontend + vài mục CẦN CHỐT còn mở)

## Mục tiêu (Goal)

Xây dựng chatbot/RAG cho bệnh nhân hỏi về thuốc, lịch uống, đơn thuốc — có safety layer song song, guardrail chống injection/rò rỉ dữ liệu, và cơ chế escalate khi phát hiện nguy hiểm. Triển khai đúng theo thiết kế đã chốt trong [`chatbot-rag-design.md`](../specs/chatbot-rag-design.md), thực hiện theo 2 kickoff prompt:

- [`build-kickoff-prompt.md`](../specs/build-kickoff-prompt.md) — Phase 0-7 (schema DB, chunking, embedding, hybrid retrieval, LangGraph agent, endpoint `/api/v1/chat`, eval harness)
- [`kickoff-prompt-vong-2.md`](../specs/kickoff-prompt-vong-2.md) — Vòng 2 (đóng backlog mục 10: chỗ nối auth thật, overlay redflag, escalation nhắc lại, xác nhận danh tính thuốc trước khi trả lời, AI safety hardening/guardrails)

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

**Còn mở — chưa Done:**

- [ ] Nối chat UI của bệnh nhân (frontend) vào `POST /api/v1/chat` thật. *(Đã từng làm trên branch `feature/TASK-010-build-chat-bot`, nhưng branch đó đã bị xoá theo quyết định của owner ngày 2026-08-10 — cần làm lại từ đầu, đối chiếu `api-contracts.md` §4 cho đúng shape `ChatResponse`.)*
- [ ] Trạng thái đề xuất gọi cấp cứu lộ ra tầng response/endpoint riêng để FE hiển thị banner liên tục từ t=15p tới khi `resolved` — `[CẦN CHỐT — cần thống nhất shape với team app trước]` (vòng 2 mục 4 ý 4)
- [ ] Auth thật (JWT đăng nhập bác sĩ/bệnh nhân, domain `auth` — Trương Quốc Trường) thay `X-Internal-Secret` tạm — chờ domain `auth` xây xong, chỉ cần đổi bên trong `get_current_patient_id()`, không sửa nơi gọi
- [ ] #14 (precision@1 field_group thấp ở nhánh ngoài đơn) — để mở, không chặn, theo dõi thêm (xem `chatbot-rag-design.md` mục 15)

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [ ] [`chatbot-rag-design.md`](../specs/chatbot-rag-design.md) (toàn bộ) — nguồn thiết kế chính
- [ ] [`build-kickoff-prompt.md`](../specs/build-kickoff-prompt.md) + [`kickoff-prompt-vong-2.md`](../specs/kickoff-prompt-vong-2.md)
- [ ] [`business-rules.md`](../specs/business-rules.md) §3, §6, §7
- [ ] [`adrs/0006-tech-stack.md`](../adrs/0006-tech-stack.md), [`0008-vector-store-pgvector.md`](../adrs/0008-vector-store-pgvector.md), [`0009-safety-layer-dual-classifier.md`](../adrs/0009-safety-layer-dual-classifier.md)
- [ ] [`api-contracts.md`](../specs/api-contracts.md) §2 (`PrescriptionDTO`), §4 (chat), §6 (`escalation-api`), §8 (`DrugInfoDTO`)
- [ ] `AGENTS.md`

## Gợi ý chia subtask (AI tự cập nhật khi bắt đầu)

- [ ] Tạo branch `feature/build-chatbot` từ `main`, phạm vi = phần "Còn mở" ở AC (chủ yếu frontend wiring)
- [ ] Nối UI chat bệnh nhân → `POST /api/v1/chat`, xử lý đủ các nhánh response (`reply`, `severity`, `safety_flag`, `needs_clarification`, `sources`)
- [ ] Dùng `scripts/seed_demo_patient.py` / `scripts/seed_random_patient.py` (đã có ở backend) để tạo bệnh nhân test cho FE — kiểm tra có cần seed script riêng phía FE không
- [ ] Trao đổi với team app (domain `auth`) chốt shape endpoint/field lộ trạng thái escalation cho banner
- [ ] Viết test tích hợp FE ↔ `/api/v1/chat` (không mock backend)

## Definition of Done

Áp dụng checklist chuẩn ở [`ADR-0005`](../adrs/0005-definition-of-done.md). Tiêu chí riêng của task này:

- [ ] Phần "Còn mở" ở AC phải Done hoặc được chuyển thành task con riêng có AC/DoD rõ ràng trước khi đóng task này
- [ ] Không merge auth tạm (`X-Internal-Secret`) ra ngoài phạm vi thử nghiệm nội bộ

## Ghi chú / trao đổi thêm

- Phần lớn backend (Phase 0-7 + toàn bộ vòng 2 trừ vài mục CẦN CHỐT) đã merge vào `main` qua PR #7 (`51c8b7b feat: add FastAPI + LangGraph medication reminder backend (Phase 1-7 + round 2 AI safety hardening)`) **trước khi** file task này được tạo — file này được viết hồi cứu để `/tasks/` phản ánh đúng luật spec-driven ở `AGENTS.md` §2, không phải để mở lại việc đã Done.
- 2026-08-10: branch `feature/TASK-010-build-chat-bot` (4 commit: wire chat UI vào backend thật, seed script test, doc TASK-010 bản đầu, rule đặt tên branch tiếng Anh) đã bị **xoá theo quyết định của owner**, không merge. Phần nối UI cần làm lại từ đầu — xem AC "Còn mở".
- `🔴 CHẶN PRODUCTION` (ghi trong `build-kickoff-prompt.md` Phase 6): `patient_id` hiện đọc thẳng từ request body, đã có mitigation tạm `X-Internal-Secret` (fail-closed) nhưng **chưa phải auth thật** — không cho ai ngoài thử nghiệm nội bộ chạm vào `/api/v1/chat` cho tới khi domain `auth` xong.
