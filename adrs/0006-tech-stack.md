# ADR-0006: Tech Stack

**Status:** Accepted
**Ngày:** 2026-08-04 (ghi lại quyết định đã hình thành trong Tuần 1, xem `README.md` §Tech Stack)
**Người đề xuất:** Nguyễn Minh Đạt (Architect) · Trương Quốc Trường (Tech Leader)
**Người duyệt:** Cả team (chốt tại Gate 01, 2026-08-01)

## Bối cảnh (Context)

VMEC-04 phải hoàn thành MVP trong **5 tuần** với **4 người kiêm nhiệm nhiều vai trò**, ngân sách hạ tầng/LLM ở mức tài khoản miễn phí hoặc nhỏ. Cần chốt tech stack sớm để 4 người làm song song trên 3 frontend + backend + agent mà không phải tranh luận lại mỗi task.

Ràng buộc đặc thù:
- Agent cần **state phức tạp** (dose window, trạng thái xác nhận, lịch sử hội thoại) và **nhánh HITL bắt buộc** — không phải luồng ReAct đơn giản.
- Cần **vector search** cho RAG thông tin thuốc.
- Cần **job định kỳ** quét liều đến hạn với độ trễ < 1 phút.
- 3 loại UI cho 3 vai trò trên 3 loại thiết bị khác nhau.

## Quyết định (Decision)

| Layer | Công nghệ | Ghi chú |
|---|---|---|
| Ngôn ngữ backend | **Python 3.11+** | Cả team quen; hệ sinh thái AI tốt nhất |
| Web framework | **FastAPI** | Async, auto-docs OpenAPI, type-safe với Pydantic |
| Agent framework | **LangGraph** | State machine tường minh + nhánh HITL — xem ADR bên dưới |
| LLM | Provider cấu hình qua `.env` `[CẦN CHỐT model cụ thể — Sprint 02]` | Phải đổi được provider không sửa code |
| Database | **PostgreSQL** | Quan hệ phác đồ ↔ dose_event ↔ audit log; hỗ trợ pgvector native |
| Vector store | **pgvector** (extension trong PostgreSQL) | Xem [ADR-0008](./0008-vector-store-pgvector.md) |
| ORM / Migration | SQLAlchemy + **Alembic** | |
| Scheduler | **Cron job 1 phút** quét `dose_event` | Xem [ADR-0007](./0007-scheduler-cron-dose-event.md) |
| FE bác sĩ | **Next.js / React** (web desktop) | Màn hình nhiều dữ liệu, dùng trên máy tính |
| FE bệnh nhân | **Mobile PWA** | Cài nhanh, không qua app store, đủ cho chụp ảnh + chat |
| FE người thân | **Mobile** | Duyệt ảnh + xử lý cảnh báo |
| Lint / Test | **ruff** + **pytest** | Đã chạy trong CI từ 2026-07-26 |
| Đóng gói / CI-CD | **Docker** + **GitHub Actions** | CI chạy ruff + pytest mọi push/PR vào `main` |

## Vì sao (Rationale)

- **FastAPI thay vì Django/Flask:** cần async cho gọi LLM/Vision đồng thời, và auto-sinh OpenAPI để FE làm song song theo contract (ADR-0003). Django quá nặng cho một API service; Flask thiếu validation/type-safety sẵn có.
- **LangGraph thay vì LangChain agent thuần / tự viết:** luồng nghiệp vụ có nhánh rẽ bắt buộc dừng chờ người (HITL) và state nhiều trường — LangGraph mô hình hoá được tường minh, dễ ghi audit từng node. Agent ReAct tự do không phù hợp vì ta **không** muốn agent tự quyết linh hoạt trong ngữ cảnh y tế.
- **PostgreSQL + pgvector thay vì Postgres + vector DB riêng:** giảm một service phải vận hành, xem ADR-0008.
- **PWA cho bệnh nhân thay vì native app:** không đủ 5 tuần để build + phát hành native; PWA vẫn truy cập được camera để chụp ảnh thuốc.
- **Docker + GitHub Actions:** miễn phí ở mức dự án học tập, cả team đã quen.

## Vì sao thân thiện với AI + Team

- Stack phổ biến → AI sinh code chuẩn xác hơn, ít bịa API không tồn tại.
- Pydantic + type hint cho AI "đích đến" rõ ràng khi sinh code, và lint bắt lỗi sớm.
- Một ngôn ngữ (Python) cho cả backend lẫn agent → giảm chi phí chuyển ngữ cảnh giữa các task.

## Hệ quả (Consequences)

**Tích cực:**
- Một service, một ngôn ngữ, một DB → vận hành đơn giản, phù hợp 5 tuần.
- Contract tự sinh từ FastAPI giúp FE và BE không lệch nhau.

**Đánh đổi / rủi ro:**
- Python không mạnh về xử lý ảnh nặng — nếu vision đếm viên thuốc chậm, phải chấp nhận xử lý bất đồng bộ thay vì trả kết quả tức thì.
- Phụ thuộc provider LLM bên ngoài: rate limit / downtime ảnh hưởng trực tiếp tới luồng chính → phải có fallback (đặc biệt cho safety layer, xem ADR-0009).
- **Chưa chốt model LLM cụ thể** — cần quyết trong Sprint 02, vì ảnh hưởng tới chi phí và accuracy phân loại.

## Câu chốt

> Chọn stack đủ quen để 4 người chạy được trong 5 tuần, và đủ tường minh để mọi hành động của AI đều truy vết được.
