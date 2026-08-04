# Sprint 02 — Dữ liệu thuốc, Vision & Nền móng kỹ thuật

**Thời gian:** 2026-08-02 → 2026-08-08 `[PM xác nhận lại mốc]`
**Sprint Goal:** Giải quyết **rủi ro số 1 của dự án** — có dữ liệu thuốc thật, có nguồn, nằm trong repo — đồng thời có số đo thật cho bài toán vision và dựng xong nền móng kỹ thuật để Sprint 03 code feature được ngay.
**Trạng thái:** 🔄 In progress

> Nguồn công việc: mục "Kế hoạch tuần sau" trong [`../../JOURNAL.md`](../../JOURNAL.md) Week 1.

## Task trong Sprint

| Task ID | Tên task | Domain | Owner (người + AI) | Ưu tiên | Status | Link |
|---|---|---|---|---|---|---|
| `TASK-001` | Thu thập & chuẩn hoá dữ liệu thuốc cho RAG | `drug-knowledge` | Nguyễn Minh Đạt + AI | **P0** | 🔄 In Progress | [`TASK-001`](../../tasks/TASK-001-thu-thap-du-lieu-thuoc.md) |
| `TASK-002` | Spike: metric & model đếm viên thuốc từ ảnh | `photo-verification` | Nguyễn Minh Đạt + AI | **P0** | To Do | [`TASK-002`](../../tasks/TASK-002-spike-vision-dem-vien-thuoc.md) |
| `TASK-003` | Skeleton FastAPI + docker-compose (Postgres + pgvector) + CI xanh | `infra` | Trương Quốc Trường + AI | **P0** | To Do | [`TASK-003`](../../tasks/TASK-003-skeleton-fastapi-docker-ci.md) |
| `TASK-004` | Form bác sĩ nhập đơn thuốc mô phỏng | `prescription` | Nguyễn Hải Yến + AI | P1 | To Do | [`TASK-004`](../../tasks/TASK-004-form-bac-si-nhap-don-thuoc.md) |
| `TASK-005` | Form khảo sát sức khoẻ bệnh nhân hằng ngày | `conversation` | Nguyễn Hải Yến + AI | P1 | To Do | [`TASK-005`](../../tasks/TASK-005-form-khao-sat-suc-khoe.md) |
| `TASK-006` | Làm rõ & chốt workflow hệ thống xuyên suốt | `docs` | Cả team | P1 | To Do | [`TASK-006`](../../tasks/TASK-006-chot-workflow-he-thong.md) |
| `TASK-007` | Wireframe / UI flow trên Figma (3 vai trò) | `frontend` | Nguyễn Hải Yến | P1 | 🔄 Carry over từ Sprint 01 | [`TASK-007`](../../tasks/TASK-007-wireframe-ui-flow.md) |
| `TASK-008` | Bộ test set safety layer + danh sách redflag tiếng Việt | `safety` | Phạm Thành Đạt + AI | **P0** | To Do | [`TASK-008`](../../tasks/TASK-008-test-set-safety-layer.md) |
| `TASK-009` | Hoàn thiện context base (`/specs`, `/adrs`, `/tasks`, `/planning`) | `docs` | Cả team + AI | P1 | 🔄 In Progress | [`TASK-009`](../../tasks/TASK-009-hoan-thien-context-base.md) |

## Việc quản trị team (không phải task code)

- [ ] **Chốt số approve tối thiểu** trước khi merge — `TEAM.md` §2 đang để trống, cần quyết ngay đầu sprint (carry over từ retro Sprint 01). — *Owner: Trương Quốc Trường*
- [ ] Chốt các luật còn để trống trong `TEAM.md` §3 (xử lý khi 2 người cùng đụng một domain, khi merger chính + backup đều vắng). — *Owner: Nguyễn Hải Yến (PM)*
- [ ] Điền Slack/email liên hệ của 4 thành viên vào `TEAM.md` §1.
- [ ] Chốt **model LLM cụ thể** + provider (ảnh hưởng chi phí và accuracy) — `[đang để CẦN CHỐT trong ADR-0006]`. — *Owner: Nguyễn Minh Đạt*
- [ ] Duyệt chính thức ADR-0001 → ADR-0011 (hiện đang ghi `[chờ xác nhận đầu Sprint 02]`).

## Điều kiện hoàn thành Sprint (Gate 02)

- [ ] Dữ liệu thuốc **đã nằm trong repo**, đúng `data pharmacy/schema.json`, có nguồn cho từng bản ghi
- [ ] Có con số thật cho bài toán đếm viên thuốc (metric đã chốt + kết quả spike), ghi trong `eval/`
- [ ] `docker compose up` chạy được, `/health` trả 200, CI xanh trên `main`
- [ ] Workflow hệ thống được cả team thống nhất, không còn hiểu khác nhau giữa các thành viên
- [ ] Bộ test set safety layer đầu tiên đã có, dùng để đo được ở Sprint 04
- [ ] Context base đầy đủ, mọi `[CẦN CHỐT]` quan trọng của Sprint 03 đã được trả lời

## Trạng thái task

- `To Do` — chưa bắt đầu
- `In Progress` — đang làm
- `In Review` — đang chờ PR review
- `Done` — đã merge, đạt Definition of Done ([ADR-0005](../../adrs/0005-definition-of-done.md))
- `Blocked` — đang bị chặn, ghi rõ chặn bởi ai/cái gì

## Rủi ro của Sprint này

| Rủi ro | Dấu hiệu nhận biết | Xử lý |
|---|---|---|
| TASK-001 không tìm được nguồn dữ liệu đủ tốt | Hết ngày 3 của sprint vẫn chưa chốt được nguồn | Thu hẹp: 20–30 thuốc phổ biến bệnh mãn tính, làm sâu thay vì rộng |
| TASK-002 spike kéo dài không có kết luận | Quá 2 ngày công vẫn chưa có số | Dừng spike, chốt metric tạm và ghi rõ giới hạn — fallback caregiver đã có sẵn (ADR-0011) |
| Vẫn không có code nào được commit (lặp lại vấn đề Sprint 01) | Hết ngày 4 mà `src/` vẫn rỗng | Ưu tiên TASK-003 lên trước, đẩy task tài liệu xuống |

## Retro cuối Sprint (điền sau khi kết thúc)

**Làm tốt:**
- [ ]

**Cần cải thiện:**
- [ ]

**Hành động cho Sprint tiếp theo:**
- [ ]

---
**Điều hướng:** [Roadmap 5 tuần](../roadmap.md) · [Sprint 01](./sprint-01.md) · [Backlog](../backlog.md) · [Tasks](../../tasks/)
