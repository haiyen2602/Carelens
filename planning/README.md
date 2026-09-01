# /planning — Backlog, Roadmap & Sprint

> Trả lời câu hỏi **"làm gì trước, làm gì sau, tuần này ai làm gì"**. Đây là bước 4 trong vòng lặp 7 bước (xem [`../docs/team-ai-workflow.md`](../docs/team-ai-workflow.md)).

## Cấu trúc

| File | Nội dung | Owner |
|---|---|---|
| [`roadmap.md`](./roadmap.md) | Bức tranh 5 tuần: sprint nào làm gì, gate nào, **đường găng**, rủi ro | PM |
| [`backlog.md`](./backlog.md) | Feature FEAT-001…012 + quy tắc ưu tiên + việc đã cắt khỏi v1 | PM |
| [`sprints/sprint-01.md`](./sprints/sprint-01.md) | Tuần 1 — ✅ Done (Gate 01) | PM |
| [`sprints/sprint-02.md`](./sprints/sprint-02.md) | Tuần 2 — 🔄 **Đang chạy** | PM |
| [`sprints/sprint-template.md`](./sprints/sprint-template.md) | Mẫu để copy cho sprint 03, 04, 05 | — |

## Ba mức chi tiết — đừng lẫn lộn

```
backlog.md   →  FEAT-XXX   mức feature ("đủ lớn", có AC ở mức feature trong /specs/features.md)
sprints/*.md →  TASK-XXX   việc của một sprint, có owner, có status
/tasks/*.md  →  subtask    AI + Dev tự chia khi bắt đầu task
```

Nguyên tắc (xem [ADR-0001](../adrs/0001-test-strategy.md)): backlog và sprint **chỉ chứa việc đủ lớn**. Việc chia nhỏ thành subtask là do AI + Dev tự làm khi bắt đầu, ghi lại trong file task — không chờ người chia sẵn từng bước.

## Sprint hiện tại

**Sprint 02** (02/8 – 08/8): dữ liệu thuốc cho RAG, spike vision, skeleton FastAPI + CI, context base.
→ Xem [`sprints/sprint-02.md`](./sprints/sprint-02.md)

## Cập nhật khi nào

| Việc | Cập nhật ở đâu |
|---|---|
| Bắt đầu / xong một task | Status trong `sprints/sprint-0X.md` **và** trong file `/tasks/TASK-XXX-*.md` |
| Thêm/bỏ/đổi ưu tiên feature | `backlog.md` |
| Đổi mốc thời gian, đổi phạm vi tuần | `roadmap.md` |
| Kết thúc sprint | Retro trong `sprints/sprint-0X.md` + tạo file sprint mới từ template |
| Việc đã làm trong ngày | [`../docs/worklog.md`](../docs/worklog.md) |
| Bài học / khó khăn của tuần | [`../docs/journal.md`](../docs/journal.md) |

---
**Lưu ý cho AI:** Khi hoàn thành một task, phải cập nhật status ở **cả hai chỗ** — file task trong `/tasks` và bảng trong file sprint tương ứng. Đây là một dòng trong Definition of Done ([ADR-0005](../adrs/0005-definition-of-done.md)).
