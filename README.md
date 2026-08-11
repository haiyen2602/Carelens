# VMEC-04: AI Agent Nhắc Thuốc & Theo Dõi Tuân Thủ Điều Trị

> Bệnh nhân điều trị dài ngày quên/uống sai thuốc, bác sĩ không có dữ liệu tuân thủ thật giữa hai lần tái khám → AI Agent nhắc thuốc, xác nhận bằng ảnh + hội thoại tự nhiên, tạo bằng chứng khách quan về tuân thủ điều trị cho bệnh nhân mãn tính.

## Vấn đề (Problem)

- **Bệnh nhân** (đặc biệt người cao tuổi nhiều bệnh nền: tim mạch, huyết áp, thận, gan) dùng nhiều loại thuốc ở nhiều khung giờ mỗi ngày, dễ quên liều, uống trễ giờ, uống sai loại, hoặc tự ý ngưng thuốc khi thấy đỡ. Với bệnh nhân sau đột quỵ, thiếu 1–2 liều đã có thể gây khó thở, ho, và căng thẳng cho cả gia đình.
- **Bác sĩ** không có dữ liệu nào về việc bệnh nhân có thực sự uống thuốc hay không giữa hai lần khám, phải dựa hoàn toàn vào lời kể của bệnh nhân — dẫn tới rủi ro ra quyết định lâm sàng sai (tăng liều/đổi thuốc vì tưởng phác đồ không hiệu quả, trong khi bệnh nhân chưa dùng đủ liều).
- Các giải pháp hiện có (app nhắc lịch, hộp chia thuốc thủ công, gọi điện nhắc) đều dừng ở mức thông báo, không tạo được **bằng chứng khách quan** rằng liều thuốc đã được uống.

## Giải pháp (Solution)

- **Feature 1 — Xác nhận bằng ảnh:** Bệnh nhân chụp ảnh thuốc đã bày trước khi uống; AI vision đếm số viên và đối chiếu với phác đồ bác sĩ đã duyệt (tối đa 2 lần chụp lại nếu không khớp trước khi chuyển sang xác minh bởi người thân).
- **Feature 2 — Hội thoại tự nhiên:** Bệnh nhân trả lời tự do ("tôi uống rồi", "hôm nay bận nên chưa uống"...); agent phân loại 4 nhãn Taken/Missed/Delayed/SideEffect và phát hiện tín hiệu tác dụng phụ ẩn trong câu nói.
- **Feature 3 — Đánh giá mức nghiêm trọng theo ngữ cảnh thuốc (RAG):** Không dùng rule cứng — bỏ 1 liều thuốc tim mạch nghiêm trọng hơn bỏ 3 liều vitamin. Agent kết hợp thông tin thuốc có nguồn để quyết định khi nào escalate, với một lớp an toàn song song (từ khoá redflag + LLM) chạy độc lập để không bỏ sót triệu chứng nghiêm trọng.
- **Human-in-the-loop:** Agent chỉ hoạt động trên đơn đã bác sĩ duyệt; mọi đề xuất thay đổi lịch nhắc phải qua bác sĩ phê duyệt trước khi áp dụng.

## Target User

- **Primary — Bệnh nhân:** người cao tuổi nhiều bệnh nền dùng thuốc dài ngày, và người trẻ trong liệu trình ngắn hạn (VD: kháng sinh) dễ bỏ ngang.
- **Primary — Bác sĩ:** bác sĩ nội khoa/chuyên khoa quản lý nhiều bệnh nhân mãn tính, cần dữ liệu tuân thủ thật thay vì lời khai.
- **Secondary — Người thân (Caregiver):** con cái/người chăm sóc, cần biết sớm khi có bất thường mà không phải gọi giục liên tục.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI Agent | LangGraph + LLM (phân loại hội thoại 4 nhãn, đánh giá mức nghiêm trọng, RAG) |
| Backend | FastAPI + Python 3.11+ |
| Scheduler | Cron job (1 phút/lần) quét bảng `dose_event` — thay vì per-dose Celery task, có biến time-offset để tăng tốc escalation khi demo |
| Frontend — Bác sĩ | Web desktop (React/Next.js), tạo & duyệt phác đồ, dashboard tuân thủ |
| Frontend — Bệnh nhân | Mobile PWA, xác nhận thuốc + chat AI |
| Frontend — Người thân | Mobile, duyệt ảnh + xử lý cảnh báo |
| Database | PostgreSQL (bảng `dose_event`, phác đồ, audit log) |
| Vector Store / RAG | pgvector (extension trong PostgreSQL, không dùng vector DB riêng) |
| Safety Layer | Dual-layer classifier: keyword rules + LLM, kết hợp bằng OR logic để tối đa recall triệu chứng nghiêm trọng |
| DevOps | Docker + GitHub Actions (CI: ruff lint + pytest trên mọi push/PR vào main) |

## Quick Start

```bash
# 1. Clone repo
git clone https://github.com/a20-ai-thuc-chien/A20-App-VMEC04.git   # cập nhật lại URL repo thật của team P-067
cd A20-App-VMEC04

# 2. Setup environment
cp .env.example .env
# Điền API keys (LLM provider, ...) vào .env

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run development server
uvicorn src.main:app --reload
```

## Project Structure

```
├── backend/             # Backend FastAPI (doi ten tu src/ 2026-08-11 de tach
│   │                    # ro voi frontend/)
│   ├── agents/          # LangGraph agent definitions
│   │   ├── graph.py     # Main graph (nodes + edges)
│   │   ├── state.py     # State schema
│   │   ├── nodes/       # parse_phac_do, sinh_lich_nhac, phan_loai_hoi_thoai,
│   │   │                # doi_chieu_anh, danh_gia_muc_nghiem_trong, escalate
│   │   └── tools/       # RAG (pgvector), vision (đếm viên thuốc), safety-layer
│   ├── api/             # FastAPI routes (doctor/patient/caregiver)
│   ├── models/          # Pydantic schemas
│   ├── services/        # Business logic, cron scheduler dose_event
│   ├── config.py        # Settings
│   └── main.py          # App entry point
├── frontend/            # Next.js app (service Railway rieng)
├── tests/               # Test suite
├── docs/                # BRIEF, PRD, workflow, functional decomposition, system flow
├── eval/                # Evaluation results (accuracy phân loại, recall triệu chứng...)
├── presentation/        # Demo materials
├── Dockerfile           # Multi-stage build
├── docker-compose.yml   # Full stack
└── .github/workflows/   # CI/CD pipelines (ruff + pytest)
```

## API Endpoints

| Method | Path | Description |
|--------|------|--------------|
| GET | /health | Health check |
| POST | /api/v1/prescriptions | Bác sĩ tạo phác đồ |
| POST | /api/v1/prescriptions/{id}/approve | Bác sĩ duyệt phác đồ (HITL) |
| POST | /api/v1/chat | Hội thoại xác nhận với agent |
| POST | /api/v1/doses/{id}/photo | Bệnh nhân gửi ảnh xác nhận thuốc |
| GET | /api/v1/dashboard | Dashboard tuân thủ cho bác sĩ |

## Deliverables Checklist

- [ ] Source Code (GitHub) — chưa bắt đầu code, đang ở giai đoạn thiết kế/tài liệu
- [x] README.md — draft Week 1
- [x] Architecture Diagram (`docs/architecture_diagram.md`) — draft sơ bộ
- [ ] AI Logs (auto-collected)
- [ ] Live URL / Deploy
- [ ] Video Demo
- [ ] Pitch Deck (`presentation/`)
- [x] Weekly Journal (`JOURNAL.md`) — Week 1 đã ghi
- [x] Worklog (`WORKLOG.md`) — Week 1 đã ghi
- [ ] Evaluation Evidence (`eval/results/`)

## Team — P-067 (G14 - T067)

| Member | Role | Student ID |
|--------|------|-----------|
| Nguyễn Minh Đạt | Team Leader / Data Engineer / AI Engineer | 2A202601142 |
| Nguyễn Hải Yến | Project Manager / UI-UX Designer / Frontend Developer | 2A202601604 |
| Phạm Thành Đạt | AI Engineer / Fullstack Developer / Tester | 2A202601672 |
| Trương Quốc Trường | Fullstack Developer / Tech Leader (merge chính vào main) | 2A202601195 |

## License

MIT
