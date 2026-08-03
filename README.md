<<<<<<< Updated upstream
# AI Agent Nhắc Thuốc & Theo Dõi Tuân Thủ Điều Trị

> Mã đề: **VMEC-04** · Khối: Hệ thống y tế X – App Ứng dụng y tế X (AI y tế)

> Tóm tắt 1 câu: Bệnh nhân quên/uống sai thuốc → AI Agent nhắc lịch thông minh, xác nhận qua hội thoại, phát hiện bỏ liều & tác dụng phụ, escalate cho bác sĩ/người thân khi tuân thủ kém.

## Vấn đề (Problem)

- **Ai gặp vấn đề?** Bệnh nhân, đặc biệt người cao tuổi và người mắc bệnh mãn tính, đang điều trị theo đơn thuốc dài hạn.
- **Biểu hiện:** Quên uống thuốc, uống sai liều/sai giờ, tự ý ngưng thuốc giữa chừng.
- **Hậu quả:** Giảm hiệu quả điều trị, tăng nguy cơ tái nhập viện, khó theo dõi tuân thủ cho bác sĩ/điều dưỡng.
- **Vì sao giải pháp hiện tại chưa đủ?** Nhắc lịch thủ công (báo thức, giấy) không thích ứng với thói quen bệnh nhân, không phát hiện được bỏ liều theo chuỗi, và không có cơ chế cảnh báo chủ động tới người thân/bác sĩ.

## Giải pháp (Solution)

AI Agent quản lý phác đồ dùng thuốc (từ đơn đã được bác sĩ nhập & duyệt), vận hành theo vòng lặp **thu thập → phân tích → giáo dục → escalate**:

- **Lập lịch nhắc thông minh:** Tự sinh lịch nhắc theo phác đồ đã duyệt, tối ưu giờ nhắc theo thói quen bệnh nhân (memory).
- **Hội thoại xác nhận uống thuốc:** Agent hỏi & ghi nhận trạng thái uống thuốc qua hội thoại tự nhiên.
- **Phát hiện bỏ liều & tác dụng phụ:** Theo dõi chuỗi bỏ liều, nhận diện phản hồi bất thường từ bệnh nhân.
- **Escalate chủ động:** Cảnh báo người thân/điều dưỡng khi tuân thủ kém; cảnh báo an toàn và chuyển bác sĩ/cấp cứu khi phát hiện tác dụng phụ nghiêm trọng.
- **Grounded & an toàn:** Trả lời dựa trên đơn thuốc đã duyệt và thông tin thuốc có nguồn (RAG), chống bịa liều/tương tác thuốc.

### Ràng buộc & An toàn (bắt buộc)

- **HITL bắt buộc:** Đơn thuốc/liều **chỉ** do bác sĩ tạo và duyệt. AI **không** tự kê đơn, tự đổi liều, hay khuyên ngưng thuốc.
- Mọi thay đổi phác đồ phải được bác sĩ phê duyệt trước khi áp dụng.
- Grounded trên đơn đã duyệt & dữ liệu thuốc có nguồn gốc rõ ràng — không bịa liều/tương tác.
- Tác dụng phụ nghiêm trọng → cảnh báo an toàn ngay và chuyển bác sĩ/cấp cứu.
- Bảo mật dữ liệu cá nhân/y tế (PII/PHI).
- Luôn khuyến cáo bệnh nhân hỏi bác sĩ/dược sĩ khi có nghi ngờ; guardrails chặn agent kê đơn/đổi liều.

## Target User

- **Primary:** Bệnh nhân (đặc biệt người cao tuổi, bệnh mãn tính) đang điều trị theo đơn thuốc dài hạn.
- **Secondary:** Bác sĩ (nhập & duyệt phác đồ, theo dõi dashboard tuân thủ), người thân/điều dưỡng (nhận cảnh báo khi tuân thủ kém hoặc tác dụng phụ nghiêm trọng).
=======
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
>>>>>>> Stashed changes

## Tech Stack

| Layer | Technology |
|-------|-----------|
<<<<<<< Updated upstream
| AI Agent | LangGraph agent với scheduler & vòng lặp theo dõi tuân thủ |
| RAG | Vector DB trên cơ sở dữ liệu thuốc mô phỏng (chỉ định, tác dụng phụ) |
| Tools | Reminder/notification (email/web push), adherence tracker, escalation |
| Guardrails | Chặn agent tự kê đơn/tự đổi liều |
| Backend | FastAPI + Python 3.11+ + cron/Celery |
| Frontend | React/Next.js — đăng nhập bệnh nhân, người thân, bác sĩ |
| Database | PostgreSQL |
| DevOps | Docker + GitHub Actions, deploy cloud |
=======
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
>>>>>>> Stashed changes

## Quick Start

```bash
# 1. Clone repo
<<<<<<< Updated upstream
git clone https://github.com/a20-ai-thuc-chien/VMEC-04-medication-adherence.git
cd VMEC-04-medication-adherence

# 2. Setup environment
cp .env.example .env
# Điền API keys (LLM, DB, notification service) vào .env

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Run development server
uvicorn src.main:app --reload --port 8000
=======
git clone https://github.com/a20-ai-thuc-chien/A20-App-VMEC04.git   # cập nhật lại URL repo thật của team P-067
cd A20-App-VMEC04

# 2. Setup environment
cp .env.example .env
# Điền API keys (LLM provider, ...) vào .env

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run development server
uvicorn src.main:app --reload
>>>>>>> Stashed changes
```

## Project Structure

```
├── src/
│   ├── agents/          # LangGraph agent definitions
<<<<<<< Updated upstream
│   │   ├── graph.py     # Main graph (thu thập → phân tích → giáo dục → escalate)
│   │   ├── state.py     # State schema (phác đồ, lịch nhắc, tuân thủ)
│   │   ├── nodes/       # Nodes: scheduler, adherence check, escalation...
│   │   └── tools/       # reminder/notification, adherence tracker, RAG lookup
│   ├── api/             # FastAPI routes (bệnh nhân, bác sĩ, người thân)
│   ├── models/          # Pydantic schemas (đơn thuốc, lịch nhắc, log tuân thủ)
│   ├── services/        # Business logic (LLM, scheduling, guardrails)
│   ├── config.py        # Settings
│   └── main.py          # App entry point
├── tests/               # Test suite
├── docs/                # Documentation & architecture diagram
├── eval/                # Evaluation results
├── presentation/        # Demo materials
├── Dockerfile           # Multi-stage build
├── docker-compose.yml   # Full stack (API + DB + scheduler)
└── .github/workflows/   # CI/CD pipelines
=======
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
├── tests/               # Test suite
├── docs/                # BRIEF, PRD, workflow, functional decomposition, system flow
├── eval/                # Evaluation results (accuracy phân loại, recall triệu chứng...)
├── presentation/        # Demo materials
├── Dockerfile           # Multi-stage build
├── docker-compose.yml   # Full stack
└── .github/workflows/   # CI/CD pipelines (ruff + pytest)
>>>>>>> Stashed changes
```

## API Endpoints

| Method | Path | Description |
<<<<<<< Updated upstream
|--------|------|-------------|
| GET | /health | Health check |
| POST | /api/v1/prescriptions | Bác sĩ tạo/duyệt phác đồ dùng thuốc |
| GET | /api/v1/patients/{id}/schedule | Xem lịch nhắc thuốc của bệnh nhân |
| POST | /api/v1/adherence/confirm | Bệnh nhân xác nhận đã uống thuốc |
| POST | /api/v1/adherence/side-effect | Ghi nhận tác dụng phụ, kích hoạt escalate nếu nghiêm trọng |
| GET | /api/v1/doctors/{id}/dashboard | Dashboard tuân thủ (tỉ lệ, chuỗi bỏ liều) cho bác sĩ |
| POST | /api/v1/chat | Hội thoại xác nhận/uống thuốc với agent |

## Yêu cầu cơ bản

- [ ] App deploy, ≥2 vai trò (bệnh nhân/bác sĩ, tùy chọn người thân)
- [ ] Bác sĩ nhập & duyệt phác đồ, agent tạo lịch nhắc
- [ ] Hội thoại xác nhận uống thuốc và ghi nhận
- [ ] Hiển thị khuyến cáo & không tự đổi liều

## Yêu cầu nâng cao

- [ ] Dashboard tuân thủ (tỉ lệ, chuỗi bỏ liều) cho bác sĩ
- [ ] Cảnh báo tác dụng phụ nghiêm trọng → escalate
- [ ] HITL để bác sĩ duyệt điều chỉnh lịch
- [ ] Memory thói quen bệnh nhân tối ưu giờ nhắc
- [ ] Báo cáo định kỳ
- [ ] Xử lý lỗi khi bệnh nhân không phản hồi (nhắc lại/báo người thân)

## Deliverables Checklist

- [x] Source Code (GitHub)
- [x] README.md
- [ ] Architecture Diagram (`docs/architecture_diagram.md`)
- [ ] AI Logs (auto-collected)
- [ ] Live URL / Deploy
- [ ] Video Demo
- [ ] Pitch Deck (`presentation/`)
- [ ] Weekly Journal (`JOURNAL.md`)
- [ ] Worklog (`WORKLOG.md`)
- [ ] Evaluation Evidence (`eval/results/`)

## Team

| Member | Role | Student ID |
|--------|------|-----------|
| [Tên] | [Vai trò] | [MSSV] |
| [Tên] | [Vai trò] | [MSSV] |
| [Tên] | [Vai trò] | [MSSV] |

## License

MIT
=======
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
>>>>>>> Stashed changes
