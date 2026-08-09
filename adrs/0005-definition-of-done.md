# ADR-0005: Definition of Done (DoD)

**Status:** Accepted
**Ngày:** 2026-08-04
**Người đề xuất:** Nguyễn Hải Yến (PM) · Phạm Thành Đạt (QA)
**Người duyệt:** Trương Quốc Trường (Tech Leader — merger chính) — `[chờ xác nhận đầu Sprint 02]`

## Bối cảnh (Context)

Không có tiêu chuẩn "hoàn thành" rõ ràng dẫn đến tình trạng "code chạy được nhưng thực ra chưa xong" — thiếu test, thiếu docs, chưa review — gây rework và mất niềm tin giữa các thành viên (và giữa team với AI).

## Quyết định (Decision)

Một task chỉ được coi là **Done** khi đáp ứng đầy đủ:

### Checklist chuẩn (áp dụng cho mọi task)

- [ ] Code đã implement, đúng Acceptance Criteria ghi trong `/tasks/TASK-XXX-*.md`
- [ ] Test pass (unit / integration, e2e nếu áp dụng) — `pytest` xanh ở local **và** trên CI
- [ ] `ruff` không còn lỗi lint
- [ ] Docs / Contracts được cập nhật (nếu có thay đổi liên quan) — `/specs`, `/adrs`, `api-contracts.md`
- [ ] PR đã được review bởi **reviewer bắt buộc theo domain** (xem [`../TEAM.md`](../TEAM.md) §2) và có trạng thái approved
- [ ] Không có secret/dữ liệu bệnh nhân/ảnh thật bị commit
- [ ] Task status đã được cập nhật thành `Done` trong `/tasks` **và** trong file sprint tương ứng ở `/planning/sprints/`
- [ ] Đã ghi vào `WORKLOG.md` (ngày làm, output)

### Checklist bổ sung — task đụng tới AI (LLM / Vision / RAG)

- [ ] Đã chạy bộ đánh giá trong `eval/` và **kết quả đạt ngưỡng** trong [ADR-0001](./0001-test-strategy.md) (đặc biệt: recall safety layer ≥ 90–95%)
- [ ] Kết quả đánh giá được commit vào `eval/results/` (có bằng chứng, không chỉ nói miệng)
- [ ] Prompt được đặt trong file prompt riêng, có phiên bản, không viết inline giữa code
- [ ] Hành động của agent có ghi `audit_log` (reasoning, confidence, nguồn RAG)

### Checklist bổ sung — task đụng tới an toàn/dữ liệu bệnh nhân

- [ ] Không vi phạm ràng buộc BR-7.x trong [`../specs/business-rules.md`](../specs/business-rules.md) (agent không kê đơn/đổi liều/chẩn đoán, không khẳng định khi không có nguồn RAG)
- [ ] Phân quyền kiểm tra **cả role lẫn quan hệ liên kết** với bệnh nhân
- [ ] Không log PHI/PII dạng plain

**Không merge khi chưa đạt DoD.** AI không tự merge trong mọi trường hợp — merge do merger chính/backup trong `TEAM.md` quyết định.

## Vì sao thân thiện với AI + Team

- Agent biết chính xác khi nào task được coi là "dùng được", không dừng giữa chừng hoặc báo Done quá sớm.
- Member biết chính xác khi nào một nhánh/PR được phép merge.
- Tránh tình trạng "code xong rồi nhưng thực ra chưa xong thật".

## Hệ quả (Consequences)

**Tích cực:**
- Chất lượng đồng đều giữa các task, ít rework, tiến độ dự đoán được tốt hơn.

**Đánh đổi / rủi ro:**
- Task nhìn "chậm" hơn nếu chỉ đo bằng tốc độ code, nhưng thực chất giảm rework về sau.

## Câu chốt

> Done không phải là code chạy được. Done là đủ chuẩn để merge.
