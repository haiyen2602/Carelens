# TASK-009: Hoàn thiện context base (`/specs`, `/adrs`, `/tasks`, `/planning`)

**Domain:** `docs`
**Owner:** Cả team + AI (chủ trì: Nguyễn Hải Yến — PM)
**Sprint:** sprint-02
**Status:** In Progress
**Ưu tiên:** P1

## Mục tiêu (Goal)

Hoàn thiện bộ context base để **AI và người mới có đủ ngữ cảnh làm việc mà không phải hỏi lại từ đầu** — đúng hành động đã ghi trong retro Sprint 01. Phần lớn file đã có; task này lấp các chỗ còn trống, sửa các chỗ mâu thuẫn, và đảm bảo mọi liên kết trong repo trỏ tới file thật tồn tại.

## Acceptance Criteria (AC)

- [ ] **Mọi link nội bộ trong repo trỏ tới file tồn tại** — hiện đang có link chết, tối thiểu:
  - [ ] `WORKLOG.md` được nhiều file trỏ tới ([`specs/README.md`](../specs/README.md), [`planning/README.md`](../planning/README.md), [ADR-0005](../adrs/0005-definition-of-done.md) — mục DoD yêu cầu "đã ghi vào `WORKLOG.md`") nhưng **file này chưa tồn tại** → tạo hoặc bỏ tham chiếu, không để nửa vời.
  - [ ] `TEAM.md` §2 ghi *"`/specs/domains.md` — file này chưa tồn tại"* nhưng file **đã có** → cập nhật lại bảng reviewer theo `domains.md` thật.
- [ ] `/tasks` có đủ **file task cho mọi TASK-XXX được liệt kê trong [`sprint-02.md`](../planning/sprints/sprint-02.md)** (TASK-001 → TASK-009), mỗi file có AC kiểm chứng được — yêu cầu bắt buộc của [ADR-0001](../adrs/0001-test-strategy.md) ("mọi task phải có AC trước khi code").
- [ ] `/tasks/README.md` giải thích: quy ước đặt tên file, vòng đời status, cập nhật status ở đâu.
- [ ] **`TEAM.md` không còn ô để trống** — số approve tối thiểu, luật khi 2 người cùng đụng một domain, luật khi merger chính + backup đều vắng, liên hệ Slack/email của 4 thành viên.
- [ ] **ADR-0001 → ADR-0011 được duyệt chính thức** — hiện tất cả đang ghi `[chờ xác nhận đầu Sprint 02]`; sau khi duyệt phải ghi tên người duyệt + ngày thật.
- [ ] ADR-0006 có **model LLM + provider cụ thể** (đang để `[CẦN CHỐT]`, ảnh hưởng chi phí và accuracy).
- [ ] Rà **mâu thuẫn giữa các file** và sửa về một nguồn sự thật duy nhất — đặc biệt giữa `ARCHITECTURE.md`, `docs/architecture_diagram.md` và `/specs/domains.md`.
- [ ] Dọn các **README trùng lặp ở gốc repo** (`README.md`, `README_20K.md`, `README_boilerplate.md`, `README_dat.md`) — chốt một file chính, phần còn lại gộp hoặc xoá; người mới clone repo không được phải đoán đọc file nào.
- [ ] `JOURNAL.md` Week 2 được điền (hiện còn placeholder).
- [ ] Mọi `[CẦN CHỐT]` còn lại được **liệt kê thành một danh sách tập trung** kèm người chịu trách nhiệm — để không ô nào bị quên (phần chốt nội dung workflow thuộc [`TASK-006`](./TASK-006-chot-workflow-he-thong.md)).

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [ ] [`AGENTS.md`](../AGENTS.md) — §2 (task phải có AC), §10 (đổi specs thì cập nhật task/PR)
- [ ] [`docs/team-ai-workflow.md`](../docs/team-ai-workflow.md) — vòng lặp 7 bước, vai trò từng thư mục
- [ ] [`specs/README.md`](../specs/README.md) · [`planning/README.md`](../planning/README.md) · [`adrs/README.md`](../adrs/README.md)
- [ ] [`TEAM.md`](../TEAM.md) · [`planning/sprints/sprint-01.md`](../planning/sprints/sprint-01.md) (retro — nguồn gốc của task này)
- [ ] [`adrs/0005-definition-of-done.md`](../adrs/0005-definition-of-done.md)

## Gợi ý chia subtask (AI tự cập nhật khi bắt đầu)

- [ ] Quét toàn repo tìm **link chết** và ô `[CẦN CHỐT]` / `[điền ...]` còn trống → lập danh sách
- [ ] Tạo file task còn thiếu trong `/tasks` (TASK-001 → TASK-009) + `/tasks/README.md`
- [ ] Quyết về `WORKLOG.md`: tạo file thật hay bỏ khỏi DoD — nếu tạo, backfill các ngày đã làm việc
- [ ] Sửa `TEAM.md`: bảng reviewer theo `domains.md`, điền các ô trống (cần PM + Tech Leader quyết)
- [ ] Họp duyệt ADR-0001 → ADR-0011, cập nhật người duyệt + ngày
- [ ] Chốt model LLM + provider vào ADR-0006
- [ ] Rà mâu thuẫn `ARCHITECTURE.md` ↔ `docs/architecture_diagram.md` ↔ `specs/domains.md`
- [ ] Dọn README trùng ở gốc repo
- [ ] Điền `JOURNAL.md` Week 2

## Definition of Done

Áp dụng checklist chuẩn ở [`ADR-0005`](../adrs/0005-definition-of-done.md). Tiêu chí riêng của task này:

- [ ] Không còn link nội bộ chết trong repo (kiểm bằng script/rà tay, ghi lại cách kiểm)
- [ ] Không còn ô `[điền ...]` / `[X ngày]` / `[kênh liên lạc]` trong `TEAM.md`
- [ ] Một thành viên **khác người viết** đọc lại và xác nhận đủ ngữ cảnh để bắt đầu một task Sprint 03 mà không cần hỏi thêm

## Ghi chú / trao đổi thêm

- Task này là **điều kiện của Gate 02**: *"Context base đầy đủ, mọi `[CẦN CHỐT]` quan trọng của Sprint 03 đã được trả lời"*.
- Phân vai rõ để không trùng với [`TASK-006`](./TASK-006-chot-workflow-he-thong.md): TASK-006 chốt **nội dung nghiệp vụ** của workflow; TASK-009 lo **tính đầy đủ và nhất quán của bộ tài liệu** (link, ô trống, trùng lặp, trạng thái ADR).
- Nếu sprint quá tải, ưu tiên theo thứ tự: (1) file task + AC trong `/tasks`, (2) duyệt ADR + chốt model LLM, (3) `TEAM.md`, (4) dọn README. Ba việc đầu chặn Sprint 03; việc dọn README chỉ gây khó chịu chứ không chặn.
- Nhắc lại rủi ro của sprint: nếu hết ngày 4 mà `src/` vẫn rỗng thì **task tài liệu bị đẩy xuống sau** [`TASK-003`](./TASK-003-skeleton-fastapi-docker-ci.md).

---
**Điều hướng:** [Sprint 02](../planning/sprints/sprint-02.md) · [Sprint 01 retro](../planning/sprints/sprint-01.md) · [Tasks](./)
