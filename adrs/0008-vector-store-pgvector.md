# ADR-0008: Vector Store — pgvector thay vì vector DB riêng

**Status:** Accepted
**Ngày:** 2026-08-04
**Người đề xuất:** Nguyễn Minh Đạt (Architect — phụ trách data thuốc & RAG)
**Người duyệt:** Trương Quốc Trường (Tech Leader) — `[chờ xác nhận đầu Sprint 02]`

## Bối cảnh (Context)

FEAT-006 và FEAT-007 cần truy xuất thông tin thuốc **có nguồn** (chỉ định, tác dụng phụ, tương tác, mức nguy hiểm khi bỏ liều) để:

1. trả lời câu hỏi của bệnh nhân mà **không bịa**, và
2. đánh giá mức nghiêm trọng theo ngữ cảnh thuốc (bỏ 1 liều thuốc tim mạch ≠ bỏ 3 liều vitamin).

Đây là **rủi ro an toàn cao nhất của dự án** (`JOURNAL.md` Week 1): nếu dữ liệu thuốc không đủ hoặc không có nguồn, agent có thể bịa thông tin y tế.

Quy mô dữ liệu dự kiến: **hàng trăm đến vài nghìn bản ghi thuốc** (theo [`../data pharmacy/schema.json`](../data%20pharmacy/schema.json)) — không phải hàng triệu document.

## Quyết định (Decision)

Dùng **pgvector** — extension vector search **trong chính PostgreSQL** đang dùng cho dữ liệu nghiệp vụ. **Không** triển khai vector DB riêng (ChromaDB / Qdrant / Pinecone / Weaviate).

Ràng buộc kèm theo:

- Mỗi chunk embedding **bắt buộc** lưu kèm khoá tham chiếu về bản ghi thuốc gốc (`drug_id`, `danh_muc`, field nguồn) — để mọi câu trả lời đều trích dẫn được nguồn.
- `DrugInfoDTO` trả về **bắt buộc** có field `source` không rỗng (xem [`../specs/api-contracts.md`](../specs/api-contracts.md) §8).
- Truy vấn không tìm được nguồn phù hợp → **trả rỗng**, để agent nói "không có thông tin, vui lòng hỏi bác sĩ" (BR-7.3). Tuyệt đối không để agent tự lấp khoảng trống.
- Model embedding: `[CẦN CHỐT — Sprint 02, cùng lúc chốt nguồn dữ liệu thuốc trong TASK-001]`.

## Vì sao (Rationale)

- **Quy mô dữ liệu nhỏ:** vài nghìn bản ghi hoàn toàn nằm trong khả năng của pgvector; lợi thế hiệu năng của vector DB chuyên dụng chỉ thể hiện ở quy mô lớn hơn nhiều.
- **Một DB thay vì hai:** trong 5 tuần, thêm một service là thêm một thứ phải cài, backup, monitor, và có thể sập lúc demo.
- **Join được với dữ liệu nghiệp vụ:** thông tin thuốc nằm cùng DB với `prescription` và `dose_event` → truy vấn kiểu "thuốc trong liều này thuộc nhóm nguy hiểm nào" làm được bằng một câu SQL, không phải gọi chéo hai hệ thống rồi ghép trong code.
- **Tính nhất quán transaction:** cập nhật dữ liệu thuốc và embedding trong cùng một transaction — không bị lệch giữa hai kho.
- **Đã có PostgreSQL sẵn** trong stack (ADR-0006), nên chi phí thêm gần như bằng 0.

**Phương án bị loại:**
- *ChromaDB:* nhẹ, dễ bắt đầu, nhưng thành kho dữ liệu thứ hai phải đồng bộ và backup riêng; mất khả năng join với dữ liệu nghiệp vụ.
- *Pinecone/Qdrant cloud:* thêm phụ thuộc mạng + chi phí, và đưa dữ liệu ra ngoài — không cần thiết ở quy mô này.

## Vì sao thân thiện với AI + Team

- Một nơi lưu trữ duy nhất → AI không phải suy luận "dữ liệu này nằm ở DB nào".
- Truy vấn RAG viết bằng SQL quen thuộc, dễ review hơn API riêng của một vector DB.
- Ràng buộc `source` bắt buộc trong DTO biến "không được bịa" từ một lời nhắc trong prompt thành **một ràng buộc kỹ thuật** — AI không thể lách qua.

## Hệ quả (Consequences)

**Tích cực:**
- Ít service, ít thứ để sập; backup một lần là xong cả dữ liệu nghiệp vụ và embedding.
- Trích dẫn nguồn trở thành mặc định, không phải tính năng thêm sau.

**Đánh đổi / rủi ro:**
- **Không scale bằng vector DB chuyên dụng** nếu sau này dữ liệu thuốc tăng lên hàng trăm nghìn bản ghi → khi đó cần đánh giá lại (sẽ là một ADR mới thay thế ADR này).
- Cần cài extension `vector` trong image PostgreSQL (dùng image có sẵn pgvector trong `docker-compose.yml`) — thêm một bước setup dễ quên khi onboard.
- Phải tự lo phần chunking, index (HNSW/IVFFlat) và tuning `top-k` — vector DB chuyên dụng làm sẵn nhiều hơn.
- **Rủi ro thật sự không nằm ở lựa chọn kho vector mà nằm ở chất lượng dữ liệu thuốc.** ADR này không giải quyết được việc dữ liệu thiếu — đó là việc của TASK-001.

## Câu chốt

> Rủi ro của dự án là agent bịa thông tin thuốc, không phải tốc độ vector search. Đặt embedding cạnh dữ liệu nghiệp vụ để mọi câu trả lời đều buộc phải có nguồn.
