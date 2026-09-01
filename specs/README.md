# /specs — Context nghiệp vụ của VMEC-04

> Trả lời câu hỏi **"chúng ta đang xây cái gì, cho ai, theo luật nào"**. Đây là bước 2 trong vòng lặp 7 bước (xem [`../docs/team-ai-workflow.md`](../docs/team-ai-workflow.md)).
> Quyết định **kỹ thuật/kiến trúc** không nằm ở đây — nằm ở [`/adrs`](../adrs/).

## Thứ tự đọc

| # | File | Trả lời câu hỏi | Owner |
|---|---|---|---|
| 1 | [`product-vision.md`](./product-vision.md) | Vấn đề gì, cho ai, phạm vi tới đâu, đo thành công bằng gì | PM |
| 2 | [`user-roles.md`](./user-roles.md) | Ai được làm gì trong hệ thống (ma trận quyền) | PM |
| 3 | [`domains.md`](./domains.md) | Hệ thống chia thành những domain nào, ai sở hữu dữ liệu nào | Architect + PM |
| 4 | [`features.md`](./features.md) | Danh sách tính năng FEAT-001…012 + Acceptance Criteria mức feature | PM |
| 5 | [`business-rules.md`](./business-rules.md) | **Các con số và quy tắc cứng** code phải tuân theo (dose window, ngưỡng, SLA) | PM + Architect |
| 6 | [`api-contracts.md`](./api-contracts.md) | Các domain/frontend giao tiếp với nhau qua hợp đồng nào | Architect + Dev domain |
| 7 | [`glossary.md`](./glossary.md) | Một khái niệm = một cái tên, dùng thống nhất ở DB/API/code/docs | Architect |

## Quy ước dùng chung

- Chỗ nào ghi **`[CẦN CHỐT: ...]`** nghĩa là team **chưa quyết** → AI và Dev **phải hỏi** người phụ trách trước khi code, không tự chọn giá trị.
- Chỗ nào ghi **`[ĐỀ XUẤT — CẦN CHỐT]`** là con số gợi ý đã có lý do, nhưng vẫn cần PM/Architect xác nhận.
- Mọi thay đổi trong `/specs` phải đi kèm cập nhật task/PR tương ứng (xem `AGENTS.md` §10).

## Truy vết ngược lên tài liệu gốc

| Tài liệu | Vai trò |
|---|---|
| [`../README.md`](../README.md) | Tóm tắt sản phẩm + tech stack + deliverables |
| [`../docs/architecture.md`](../docs/architecture.md) | Kiến trúc hệ thống chi tiết (component, data flow, security) |
| [`../docs/journal.md`](../docs/journal.md) · [`../docs/worklog.md`](../docs/worklog.md) | Lịch sử quyết định theo tuần/ngày — nguồn gốc của phần lớn nội dung trong `/specs` |
| [`../TEAM.md`](../TEAM.md) | Ai giữ vai trò gì, ai review domain nào, ai merge |
