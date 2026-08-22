# /adrs — Architecture Decision Records

> Nơi ghi lại **mọi quyết định kiến trúc** của VMEC-04: quyết định gì, vì sao, đánh đổi gì. Đây là bước 3 trong vòng lặp 7 bước (xem [`../docs/team-ai-workflow.md`](../docs/team-ai-workflow.md)).
> **ADR không được đi ngược lại trừ khi có ADR mới thay thế.** Khi nào cần tạo ADR mới: xem `AGENTS.md` §9.

## Danh sách ADR

| ADR | Tên | Status | Câu chốt |
|---|---|---|---|
| [0000](./0000-adr-template.md) | Template | — | Copy file này khi viết ADR mới |
| [0001](./0001-test-strategy.md) | Test-Driven / Test Strategy | Accepted | Test là hợp đồng hành vi. Với AI không tất định, **ngưỡng chỉ số trên test set** là hợp đồng đó. |
| [0002](./0002-domain-split.md) | Domain Split (Modular Monolith) | Accepted | Chia domain tốt = chia context tốt. |
| [0003](./0003-api-contract-first.md) | API Contract First | Accepted | Team scale bằng contract, không scale bằng hiểu ngầm. |
| [0004](./0004-project-structure-and-coding-convention.md) | Project Structure & Coding Convention | Accepted | Không có convention, AI sẽ tạo ra code hỗn loạn rất nhanh. |
| [0005](./0005-definition-of-done.md) | Definition of Done | Accepted | Done không phải là code chạy được. Done là đủ chuẩn để merge. |
| [0006](./0006-tech-stack.md) | Tech Stack | Accepted | Stack đủ quen để 4 người chạy trong 5 tuần, đủ tường minh để truy vết mọi hành động AI. |
| [0007](./0007-scheduler-cron-dose-event.md) | Scheduler — cron 1 phút quét `dose_event` | Accepted | Trạng thái để trong DB, cron job đơn giản đọc — tự phục hồi sau restart. |
| [0008](./0008-vector-store-pgvector.md) | Vector Store — pgvector | Accepted | Rủi ro là agent bịa thông tin thuốc, không phải tốc độ vector search. |
| [0009](./0009-safety-layer-dual-classifier.md) | Safety Layer — dual classifier (OR) | Accepted | Báo thừa còn hơn bỏ sót. Lớp an toàn phải sống cả khi mọi thứ khác đã chết. |
| [0010](./0010-human-in-the-loop.md) | Human-in-the-loop — bác sĩ duyệt | Accepted | AI nhắc và thu bằng chứng. Bác sĩ vẫn quyết định điều trị. |
| [0011](./0011-photo-verification-fallback.md) | Xác nhận ảnh — 2 lần rồi fallback người thân | Accepted | Bằng chứng phân tầng theo độ tin cậy, bác sĩ luôn biết đang xem tầng nào. |
| [0012](./0012-drug-data-v2-compatibility-and-provenance.md) | Drug Data V2 Compatibility And Provenance | Proposed | Xây V2 bên cạnh V1: slug vẫn là hợp đồng ngoài, UUID là lõi nội bộ, provenance tăng dần và không đoán dữ liệu y tế. |
| [0013](./0013-danh-muc-thuoc-la-allowlist-dong.md) | Danh mục thuốc là allowlist đóng | Accepted | Bác sĩ chọn thuốc từ danh mục, không gõ thuốc vào danh mục — siết FB-14, kèm đường thoát qua admin duyệt. |

## Nhóm theo chủ đề

- **Cách team làm việc:** 0001 (test), 0004 (convention), 0005 (DoD)
- **Cấu trúc hệ thống:** 0002 (domain split), 0003 (contract), 0006 (tech stack)
- **Quyết định đặc thù VMEC-04:** 0007 (scheduler), 0008 (pgvector/RAG), 0009 (safety), 0010 (HITL), 0011 (xác nhận ảnh), 0013 (allowlist thuốc)

## An toàn — đọc trước khi làm bất kỳ task nào đụng tới agent

Ba ADR dưới đây là **ràng buộc an toàn của sản phẩm y tế**, không phải sở thích kỹ thuật. Vi phạm chúng là lỗi nghiêm trọng, không phải "khác phong cách":

- **[0009](./0009-safety-layer-dual-classifier.md)** — safety layer chạy song song, OR logic, LLM chết thì keyword vẫn chạy.
- **[0010](./0010-human-in-the-loop.md)** — agent chỉ chạy trên phác đồ `approved`; không kê đơn/đổi liều/chẩn đoán.
- **[0008](./0008-vector-store-pgvector.md)** — không có nguồn RAG thì không khẳng định thông tin thuốc.

Các ràng buộc này được cụ thể hoá thành quy tắc `BR-x.x` trong [`../specs/business-rules.md`](../specs/business-rules.md).

## Quy trình tạo ADR mới

1. Copy [`0000-adr-template.md`](./0000-adr-template.md) → `00XX-<ten-quyet-dinh>.md` (số tăng dần).
2. Điền đủ: Bối cảnh → Quyết định → Vì sao (kèm **phương án đã cân nhắc và loại bỏ**) → Hệ quả (kèm **đánh đổi**).
3. Status ban đầu là `Proposed`; chuyển `Accepted` sau khi có người duyệt.
4. Thêm dòng vào bảng ở file này.
5. Nếu ADR mới thay thế ADR cũ → đổi ADR cũ thành `Superseded by ADR-00XX`, **không xoá** (giữ lịch sử quyết định).

**Không cần ADR** cho quyết định nhỏ trong phạm vi một task (chi tiết implementation nội bộ của một hàm/module).

---
**Lưu ý cho AI:** Không tự ý thay đổi kiến trúc, tech stack, hoặc convention mà không có ADR mới được con người duyệt (`AGENTS.md` §8). Nếu thấy một ADR đã lỗi thời hoặc mâu thuẫn với thực tế code, **báo lại cho người phụ trách** và đề xuất ADR mới — không âm thầm code theo cách khác.
