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

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI Agent | LangGraph agent với scheduler & vòng lặp theo dõi tuân thủ |
| RAG | Vector DB trên cơ sở dữ liệu thuốc mô phỏng (chỉ định, tác dụng phụ) |
| Tools | Reminder/notification (email/web push), adherence tracker, escalation |
| Guardrails | Chặn agent tự kê đơn/tự đổi liều |
| Backend | FastAPI + Python 3.11+ + cron/Celery |
| Frontend | React/Next.js — đăng nhập bệnh nhân, người thân, bác sĩ |
| Database | PostgreSQL |
| DevOps | Docker + GitHub Actions, deploy cloud |

## Quick Start

```bash
# 1. Clone repo
git clone https://github.com/a20-ai-thuc-chien/VMEC-04-medication-adherence.git
cd VMEC-04-medication-adherence

# 2. Setup environment
cp .env.example .env
# Điền API keys (LLM, DB, notification service) vào .env

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Run development server
uvicorn src.main:app --reload --port 8000
```

## Project Structure

```
├── src/
│   ├── agents/          # LangGraph agent definitions
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
```

## API Endpoints

| Method | Path | Description |
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
