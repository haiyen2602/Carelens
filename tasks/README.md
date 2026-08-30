# /tasks — Task chi tiết theo sprint

> Trả lời câu hỏi **"việc này cụ thể phải làm gì, xong là thế nào"**. Đây là bước 5 trong vòng lặp 7 bước (xem [`../docs/team-ai-workflow.md`](../docs/team-ai-workflow.md)).
> Danh sách task của một sprint nằm ở [`/planning/sprints/`](../planning/sprints/); file ở đây là **nội dung chi tiết** của từng task.

## Task đang mở — Sprint 02

| Task | Tên | Domain | Owner | Ưu tiên | Status |
|---|---|---|---|---|---|
| [`TASK-001`](./TASK-001-thu-thap-du-lieu-thuoc.md) | Thu thập & chuẩn hoá dữ liệu thuốc cho RAG | `drug-knowledge` | Nguyễn Minh Đạt | **P0** | 🔄 In Progress |
| [`TASK-002`](./TASK-002-spike-vision-dem-vien-thuoc.md) | Spike: metric & model đếm viên thuốc từ ảnh | `photo-verification` | Nguyễn Minh Đạt | **P0** | To Do |
| [`TASK-003`](./TASK-003-skeleton-fastapi-docker-ci.md) | Skeleton FastAPI + docker-compose + CI xanh | `infra` | Trương Quốc Trường | **P0** | To Do |
| [`TASK-004`](./TASK-004-form-bac-si-nhap-don-thuoc.md) | Form bác sĩ nhập đơn thuốc mô phỏng | `prescription` | Nguyễn Hải Yến | P1 | To Do |
| [`TASK-005`](./TASK-005-form-khao-sat-suc-khoe.md) | Form khảo sát sức khoẻ bệnh nhân hằng ngày | `conversation` | Nguyễn Hải Yến | P1 | To Do |
| [`TASK-006`](./TASK-006-chot-workflow-he-thong.md) | Làm rõ & chốt workflow hệ thống xuyên suốt | `docs` | Cả team | P1 | To Do |
| [`TASK-007`](./TASK-007-wireframe-ui-flow.md) | Wireframe / UI flow trên Figma (3 vai trò) | `frontend` | Nguyễn Hải Yến | P1 | To Do (carry over) |
| [`TASK-008`](./TASK-008-test-set-safety-layer.md) | Bộ test set safety layer + redflag tiếng Việt | `safety` | Phạm Thành Đạt | **P0** | To Do |
| [`TASK-009`](./TASK-009-hoan-thien-context-base.md) | Hoàn thiện context base | `docs` | Cả team | P1 | 🔄 In Progress |
| [`TASK-010`](./TASK-010-build-chatbot.md) | Build chatbot/RAG (VMEC-04) — backend + tích hợp frontend | `drug-knowledge` | Nguyễn Minh Đạt | **P0** | 🔄 In Progress (backend Done) |

## Task bảo trì ngoài sprint

| Task | Tên | Domain | Owner | Ưu tiên | Status |
|---|---|---|---|---|---|
| [`TASK-AI-LOG-CODEX`](./TASK-AI-LOG-CODEX.md) | Ghi nhận và gửi AI log của Codex | `infra` | Nguyễn Hải Yến + AI | P1 | 🔄 In Progress |

## Hotfix được phê duyệt ngoài sprint

| Task | Tên | Domain | Owner | Ưu tiên | Status |
|---|---|---|---|---|---|
| [`TASK-021`](./TASK-021-doctor-patient-chat-sync.md) | Đồng bộ hội thoại bác sĩ - bệnh nhân | `conversation`, `notification` | Unassigned + AI | **P0** | 🔎 In Review |

> Sprint 01 diễn ra **trước khi** repo có `/tasks` nên không có file task — xem [`sprint-01.md`](../planning/sprints/sprint-01.md).

## Quy ước

**Đặt tên file:** `TASK-XXX-mo-ta-ngan-khong-dau.md` — số tăng dần **liên tục qua các sprint**, không reset về 001 ở sprint mới.

**Tạo task mới:** copy [`TASK-000-template.md`](./TASK-000-template.md), điền đủ mọi mục. Task **không có Acceptance Criteria cụ thể, kiểm chứng được thì không được bắt đầu code** ([ADR-0001](../adrs/0001-test-strategy.md), [`AGENTS.md`](../AGENTS.md) §2).

**Vòng đời status:**

```
To Do  →  In Progress  →  In Review  →  Done
                ↓
             Blocked  (ghi rõ chặn bởi ai/cái gì)
```

| Status | Nghĩa |
|---|---|
| `To Do` | Chưa bắt đầu |
| `In Progress` | Đang làm |
| `In Review` | Đã mở PR, đang chờ review |
| `Done` | Đã merge, đạt Definition of Done ([ADR-0005](../adrs/0005-definition-of-done.md)) |
| `Blocked` | Đang bị chặn — ghi rõ nguyên nhân ngay trong file task |

**Cập nhật status ở 3 chỗ** (một dòng trong DoD):

1. Header của file task này
2. Bảng ở đầu file `README.md` này
3. Bảng task trong [`/planning/sprints/sprint-0X.md`](../planning/sprints/)

## Ba mức chi tiết — đừng lẫn lộn

```
/planning/backlog.md      →  FEAT-XXX   feature "đủ lớn", AC ở mức feature (/specs/features.md)
/planning/sprints/*.md    →  TASK-XXX   việc của một sprint: owner, ưu tiên, status
/tasks/TASK-XXX-*.md      →  subtask    AI + Dev tự chia khi bắt đầu làm
```

Việc chia nhỏ thành subtask **do AI + Dev tự làm khi bắt đầu task**, ghi lại trong mục "Gợi ý chia subtask" của file task — không chờ người chia sẵn từng bước.

## Lưu ý cho AI

- Đọc **đủ và chỉ đủ** context liệt kê trong mục "Context bắt buộc phải đọc" của task — không đọc sâu code của domain khác (tránh over-context, xem [`/specs/domains.md`](../specs/domains.md)).
- Gặp ô `[CẦN CHỐT]` trong specs/ADR liên quan tới task đang làm → **hỏi người phụ trách**, không tự chọn giá trị.
- Mọi con số nghiệp vụ lấy từ [`/specs/business-rules.md`](../specs/business-rules.md), khai báo thành hằng số có tên, không rải magic number.
- AI **không tự merge PR** trong bất kỳ trường hợp nào ([`AGENTS.md`](../AGENTS.md) §8, [`TEAM.md`](../TEAM.md) §2).

---
**Điều hướng:** [Sprint 02](../planning/sprints/sprint-02.md) · [Backlog](../planning/backlog.md) · [Specs](../specs/) · [ADRs](../adrs/)
