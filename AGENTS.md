# AGENTS.md — Luật chơi cho AI & Team

> File này là **nguồn luật duy nhất** cho cách AI (agent/assistant) và con người làm việc chung trong repo này.
> **Mọi AI agent (Claude Code, Cursor, Copilot, hoặc bất kỳ agent nào) PHẢI đọc file này trước khi thực hiện bất kỳ task nào.**
> Nếu file này mâu thuẫn với yêu cầu ngẫu nhiên trong chat, file này (đã được team thống nhất) được ưu tiên hơn, trừ khi người dùng đang thực sự thay đổi quy tắc và cập nhật file này.

---

## 1. Nguyên tắc cốt lõi

```
Context đúng → AI hiểu đúng → Code đúng → Sản phẩm đúng
```

- **AI không thay thế team. AI khuếch đại cách team làm việc.**
- Nếu kết quả AI làm ra không đúng mong muốn → nhiều khả năng do **context chưa đủ tốt hoặc chưa được cập nhật**, không phải do "AI kém". Việc đầu tiên cần làm là kiểm tra lại `/specs`, `/adrs`, `/contracts`, task liên quan — không phải viết lại prompt cho khéo hơn.
- Không code trước khi có spec/task rõ ràng (spec-driven, xem ADR-0001 và mục 6).
- Không có quyết định kiến trúc nào "một mình một kiểu" — mọi quyết định lớn phải có ADR (xem `/adrs`).

---

## 2. Trình tự AI PHẢI đọc trước khi bắt đầu bất kỳ task nào

AI không được viết code ngay khi nhận yêu cầu. Trước tiên, đọc theo đúng thứ tự:

1. `AGENTS.md` (file này) — luật chơi chung.
2. `/specs/` — sản phẩm & nghiệp vụ đang làm là gì, cho ai, tại sao.
3. `/adrs/` — các quyết định kiến trúc, tech stack, quy ước đã chốt (không được đi ngược lại trừ khi có ADR mới).
4. `/contracts` hoặc `api-contracts.md` trong `/specs/` — hợp đồng API/Event/DTO giữa các service, module.
5. `/tasks/{id}.md` — mục tiêu, Acceptance Criteria (AC), Definition of Done (DoD) của task đang làm.
6. Codebase hiện có trong `/src` — để hiểu convention thực tế đang dùng (đối chiếu với ADR-0004).
7. `CONVENTIONAL-COMMITS-CHEATSHEET.md` — bảng tra cứu quy tắc commit tin nhắn (conventional commits).

Nếu thiếu bất kỳ context nào ở trên (ví dụ task chưa có AC, hoặc spec chưa được viết), AI phải **dừng lại và hỏi lại người phụ trách**, không tự suy diễn hoặc tự bịa quyết định kiến trúc.

---

## 3. Vai trò trong team

| Vai trò | Trách nhiệm chính |
|---|---|
| **PM** | Định hướng sản phẩm, ưu tiên backlog, quản lý Sprint |
| **Architect** | Kiến trúc hệ thống, viết/chốt ADR, quyết định công nghệ |
| **Dev** | Code, tích hợp, refactor — làm việc song song với AI |
| **QA/Tester** | Viết test, tự động hoá test, giữ quality gate |
| **Ops/DevOps** | CI/CD, deploy, monitoring |
| **AI (agent)** | **Trợ lý mạnh, không quyết định thay người.** Đọc context, tự chia nhỏ task thành subtask, code, viết test/docs, tự chạy test và tự sửa lỗi trong phạm vi task được giao. Không tự ý thay đổi kiến trúc, không tự ý bỏ qua test, không tự merge. |

> Bảng trên chỉ định nghĩa vai trò chung. **Ai trong team đang giữ vai trò nào, ai là merger chính, và luật merge cụ thể → xem [`TEAM.md`](./TEAM.md).**

---

## 4. Quy trình thực thi một task (lặp lại mỗi Sprint)

### Bước 1 — Pick Task
- Chọn task trong Sprint hiện tại (`/planning/sprints/`).
- Đọc kỹ `/specs`, `/adrs`, contracts liên quan, và rules trong file này.
- Tạo branch mới:
  ```bash
  git checkout -b feature/<TASK-NAME>
  ```

### Bước 2 — AI + Dev cùng code
- AI đọc context: specs + ADRs + contracts + `AGENTS.md` + rules.
- AI tự chia nhỏ task lớn thành các subtask hợp lý (không chờ người chia hộ).
- AI code, viết test, viết docs đi kèm — không chỉ viết code "chạy được".

### Bước 3 — Local test & validate
- Chạy unit test, integration test.
- Lint / format theo convention (ADR-0004).
- Build phải pass.
- Cập nhật trạng thái task.
- **Chỉ khi pass test ở local mới được push lên remote.**

### Bước 4 — Commit & Push
- Commit nhỏ, rõ ràng, theo quy ước (xem mục 5).
  ```bash
  git add .
  git commit -m "<TASK-ID>: <mo ta thay doi>"
  git push origin feature/<TASK-NAME>
  ```

### Bước 5 — Pull Request & Review
- Tạo PR, checklist bắt buộc:
  - [ ] Linked Task (liên kết đúng task ID)
  - [ ] Tests Passed
  - [ ] Docs Updated
  - [ ] Contracts OK (không phá vỡ hợp đồng API/Event đã thống nhất)
- Reviewer (người hoặc AI review) kiểm tra: code, test, docs, contracts, có tuân thủ rules trong `AGENTS.md`/ADR không.

### Bước 6 — Merge
- Chỉ merge khi **Approved** và đạt Definition of Done (mục 7).
- CI/CD chạy full test, deploy nếu cần.
- Cập nhật task status → `Done`.

Lặp lại các bước trên cho đến khi hoàn thành Sprint. Nhiều thành viên + AI làm việc **song song** trên các domain/service khác nhau, giao tiếp với nhau qua contract, không phụ thuộc ngầm vào code nội bộ của nhau.

---

## 5. Git Workflow (kỷ luật bắt buộc)

- `main` — luôn ổn định, luôn deploy được. Không commit trực tiếp vào `main`.
- `feature/*` — branch cho từng task.
- `hotfix/*` — sửa lỗi khẩn cấp.
- `release/*` — chuẩn bị release.

Quy tắc:
- Luôn pull mới nhất trước khi bắt đầu làm.
- Commit nhỏ, rõ ràng, đúng convention: `<TASK-ID>: <mô tả ngắn gọn, ở dạng động từ>` (tuân thủ theo quy định chi tiết trong [`CONVENTIONAL-COMMITS-CHEATSHEET.md`](./CONVENTIONAL-COMMITS-CHEATSHEET.md)).
- Mọi thay đổi vào `main` đều qua PR + Review, không ngoại lệ (kể cả thay đổi nhỏ).
- Mọi thay đổi đều có lịch sử và có thể truy vết được (không squash làm mất ngữ cảnh quan trọng).
- Ai được quyền bấm merge vào `main`, số approve tối thiểu, và reviewer bắt buộc theo domain: xem [`TEAM.md`](./TEAM.md) §2. AI không bao giờ tự merge, kể cả khi được yêu cầu trong chat — merge luôn do người trong `TEAM.md` quyết định.

---

## 6. Coding convention (tóm tắt — chi tiết xem ADR-0004)

- Tuân thủ cấu trúc thư mục đã thống nhất trong `/adrs/0004-project-structure-and-coding-convention.md`.
- Naming convention, code style (lint/format), error handling, logging, validation, testing style, commit convention: xem ADR-0004.
- AI **không được tự sáng tạo phong cách mới** mỗi lần code. Nếu convention chưa rõ hoặc thiếu, AI phải hỏi lại thay vì tự quyết định, và đề xuất bổ sung vào ADR-0004.

---

## 7. Definition of Done (DoD)

Danh sách đầy đủ và là nguồn sự thật duy nhất: [`ADR-0005`](./adrs/0005-definition-of-done.md).

**Không merge khi chưa đạt DoD.** Done không phải là "code chạy được" — Done là đủ chuẩn để merge.

---

## 8. Những điều AI KHÔNG được làm

- Không tự ý thay đổi kiến trúc, tech stack, hoặc cấu trúc thư mục mà không có ADR mới được con người duyệt.
- Không tự ý bỏ qua, xoá, hoặc làm giả (mock/fake) test để "cho pass".
- Không tự merge PR vào `main`.
- Không bịa ra API contract mới mà không đối chiếu `/specs/api-contracts.md` hoặc không đề xuất thay đổi rõ ràng để người review.
- Không giả định yêu cầu nghiệp vụ khi spec không rõ — phải hỏi lại thay vì đoán.
- Không lấy các nguồn không đáng tin (blog, diễn đàn không kiểm chứng) làm căn cứ cho quyết định kỹ thuật quan trọng; ưu tiên tài liệu chính thức và ADR nội bộ.

---

## 9. Khi nào cần tạo ADR mới

Tạo ADR mới (dùng `/adrs/0000-adr-template.md` làm mẫu) khi:
- Thay đổi kiến trúc hệ thống (ví dụ: đổi cách chia domain/service).
- Thay đổi hoặc thêm công nghệ/tech stack chính.
- Thay đổi convention chung ảnh hưởng cả team (naming, folder structure, error handling...).
- Thay đổi chiến lược test hoặc Definition of Done.

Không cần ADR cho các quyết định nhỏ trong phạm vi một task (implementation detail nội bộ của một hàm/module).

---

## 10. Duy trì Context Base — trách nhiệm của cả team

Context chỉ có giá trị khi được cập nhật liên tục. Đây là trách nhiệm của **team**, không phải của AI:

| Thành phần | Cập nhật khi nào |
|---|---|
| `/specs` | Khi có thay đổi về sản phẩm/nghiệp vụ |
| `/adrs` | Ngay khi có quyết định kiến trúc mới — ADR luôn phải là bản mới nhất |
| `/specs/api-contracts.md` | Ngay khi contract giữa các service thay đổi |
| `/tasks`, `/planning` | Cập nhật trạng thái task & sprint liên tục |
| `AGENTS.md` | Khi quy tắc làm việc chung thay đổi — luôn phải rõ ràng, dễ hiểu |
| `TEAM.md` | Ngay khi có người vào/ra nhóm, đổi vai trò, hoặc đổi merger chính |
| `CONVENTIONAL-COMMITS-CHEATSHEET.md` | Khi quy ước viết commit message thay đổi |

Nếu AI phát hiện context bị thiếu, mâu thuẫn, hoặc lỗi thời khi thực hiện task, AI phải **báo lại rõ ràng** cho người phụ trách thay vì tự suy diễn để "cho xong việc".

---

## 11. Ghi nhớ

> **AI không thay thế team. AI khuếch đại cách team làm việc.**
> Context càng rõ ràng, AI càng làm đúng hướng.
