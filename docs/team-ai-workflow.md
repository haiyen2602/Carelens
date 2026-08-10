# Team + AI làm việc hiệu quả — Big Picture & Nguyên tắc

> File này giải thích **tư duy nền** đằng sau cấu trúc repo và `AGENTS.md`. Thành viên mới nên đọc file này để hiểu "vì sao" trước khi đọc "luật" trong `AGENTS.md`.

## 1. Big Picture Workflow

Một team + AI vận hành dự án theo vòng lặp 7 bước, từ ý tưởng đến sản phẩm, lặp lại theo Sprint:

1. **Brainstorm** — Ý tưởng, nhu cầu, brainstorm với AI, xác định mục tiêu.
2. **Specs (Spec-driven)** — Domains, Features, User roles, API Contracts, Business rules → viết vào `/specs`.
3. **Architecture (ADR)** — ADRs, tech stack, kiến trúc, rules & conventions, folder structure → viết vào `/adrs`.
4. **Planning (Sprint/Tasks)** — Backlog, Sprint, User stories, Task (lớn), ước lượng & ưu tiên → viết vào `/planning`, `/tasks`.
5. **Parallel Execution (Team + AI)** — Mỗi thành viên + AI chọn task trong Sprint, làm song song, commit thường xuyên.
6. **Review & Merge** — PR/Review (người hoặc AI), verify, resolve conflict, merge vào `main`.
7. **Next Sprint (lặp lại)** — Retro, cải tiến, Sprint tiếp theo.

Nền tảng chung xuyên suốt cả 7 bước:
- **Workspace**: Git Repository dùng chung cho tất cả (một nguồn sự thật).
- **Roles & Responsibilities**: rõ ràng, linh hoạt (Human + AI).
- **Tools**: Git, CI/CD, Test, Docs, AI Agents, MCP (Jira, Linear...).
- **Rules & Standards**: coding convention, Definition of Done, review rules.

## 2. Sáu nguyên tắc để Team + AI làm việc hiệu quả

```
Context đúng → AI hiểu đúng → Code đúng → Sản phẩm đúng
```

Mỗi nguyên tắc dưới đây được thể chế hoá thành luật cụ thể trong `AGENTS.md` hoặc một ADR — xem rationale đầy đủ ("Vì sao") ở file tương ứng, không lặp lại ở đây.

1. **Spec-driven (không code trước)** → *Spec tốt = ít đổi hướng = ít tốn chi phí.* (`AGENTS.md` §1, §6)
2. **ADR là nền (không mạnh ai nấy làm)** → *ADR giúp team thống nhất và dễ dàng scale.* (`AGENTS.md` §9, [`/adrs`](../adrs))
3. **Task đủ lớn (để AI tự chia nhỏ)** → *Đừng chia quá nhỏ, hãy để AI phát huy.* ([ADR-0001](../adrs/0001-test-strategy.md))
4. **Làm việc qua contract (không phụ thuộc ngầm)** → *Contract rõ ràng = tách rời tốt = làm song song hiệu quả.* ([ADR-0003](../adrs/0003-api-contract-first.md))
5. **AI luôn đọc context trước khi code** → *Context càng rõ ràng, AI càng làm đúng hướng.* (`AGENTS.md` §2)
6. **Git workflow là kỷ luật** → *Kỷ luật Git = an toàn = dễ cộng tác.* (`AGENTS.md` §5)

## 3. Context base phải luôn được duy trì

Bảng chi tiết thành phần nào cập nhật khi nào: xem `AGENTS.md` §10.

**Kết quả khi làm đúng:**
- Team cùng hiểu, cùng một hướng.
- AI làm việc như một thành viên thực thụ.
- Code chất lượng, ít lỗi, ít rework.
- Tiến độ ổn định và dự đoán được.
- Dễ dàng on-boarding thành viên mới.

> **Tip:** Nếu team cảm thấy "AI làm ra kết quả không đúng mong muốn" → rất có thể là do context chưa đủ tốt hoặc chưa được cập nhật, chứ không phải AI "kém".

> **Ghi nhớ:** AI không thay thế team. AI khuếch đại cách team làm việc!

## 4. Vòng lặp thực thi mỗi ngày

Xem chi tiết từng bước (Pick Task → AI+Dev code → Local test → Commit & Push → PR & Review → Merge) trong [`AGENTS.md`](../AGENTS.md), mục 4.

## 5. Năm ADR nền tảng khuyến nghị

Xem chi tiết trong thư mục [`/adrs`](../adrs):

1. **Test-Driven / Test Strategy** — Test là hợp đồng hành vi của hệ thống.
2. **Domain Split (Microservice/Hybrid)** — Chia domain tốt = chia context tốt.
3. **API Contract First** — Team scale bằng contract, không scale bằng hiểu ngầm.
4. **Project Structure & Coding Convention** — Không có convention, AI sẽ tạo ra kết quả hỗn loạn rất nhanh.
5. **Definition of Done (DoD)** — Done không phải là code chạy được. Done là đủ chuẩn để merge.

Tư duy tổng kết: **Chia rõ (Boundary rõ) → Contract rõ (Giao tiếp rõ) → Test rõ (Đích đến rõ) → Team + AI chạy song song hiệu quả.**
