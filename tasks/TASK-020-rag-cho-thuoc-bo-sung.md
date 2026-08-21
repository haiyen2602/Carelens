# TASK-020: RAG cho thuốc bổ sung qua `drug_request`

**Domain:** `drug-knowledge` (RAG / pgvector)
**Owner:** Nguyễn Minh Đạt
**Người bàn giao:** Nguyễn Hải Yến
**Sprint:** Chưa phân Sprint
**Status:** Not started
**Ưu tiên:** P2 — **không chặn luồng kê đơn**, xem mục "Vì sao không gấp"

## Bối cảnh

Từ 2026-08-20, danh mục thuốc là allowlist đóng (ADR-0013, FB-14): bác sĩ không kê được thuốc không có trong danh mục. Đường thoát là bảng `drug_request` — bác sĩ xin bổ sung, admin duyệt, duyệt xong mới kê được.

Thuốc duyệt qua đường này **đã dùng được cho việc kê đơn**: nó xuất hiện ở ô gợi ý, trang tra cứu của bác sĩ, và màn hình dữ liệu thuốc của admin (gắn nhãn `source = DRUG_REQUEST`).

**Nhưng chatbot không trả lời được gì về nó** — bảng `drug_chunks` không có dòng nào cho thuốc đó, nên `hybrid_search` không tìm ra. Bệnh nhân hỏi "thuốc X có tác dụng phụ gì" thì bot không có dữ liệu.

## Mục tiêu (Goal)

Sinh chunk + embedding cho các thuốc đã duyệt trong `drug_request`, ghi vào `drug_chunks`, để chatbot trả lời được về chúng như với thuốc trong danh mục gốc.

## Đường ranh giới — ai làm gì

**Phía đã bàn giao (đã xong, không cần đụng):**

Bảng `drug_request` với các dòng `status = 'APPROVED'`, mỗi dòng có:

| Cột | Ý nghĩa |
|---|---|
| `approved_drug_id` | Dạng `req-<slug>-<hash6>`. **Chính là `drug_id`** dùng ở mọi nơi khác trong hệ thống |
| `ten_thuoc` | Tên bác sĩ khai |
| `dang_thuoc` | Dạng bào chế (NOT NULL) |
| `duong_dung` | Đường dùng (NOT NULL) |
| `ham_luong` | Có thể NULL |
| `requested_by_doctor_id`, `reviewed_by_account_id` | Truy vết ai xin, ai duyệt |

Lấy danh sách bằng `backend.services.drug_requests.liet_ke_thuoc_da_duyet(db)` — đừng viết SQL thẳng vào bảng (ADR-0002).

**Phía cần làm (task này):**

Đọc các dòng đó → sinh nội dung 4 nhóm trường → embed → `INSERT INTO drug_chunks` với `drug_id = approved_drug_id`.

## Acceptance Criteria (AC)

- [ ] Có cách sinh `drug_chunks` cho một thuốc trong `drug_request` đã duyệt, đúng 4 `field_group` mà `scripts/chunk_drugs.py` đang dùng: `cong_dung`, `tac_dung_phu`, `cach_dung`, `bao_quan`.
- [ ] `ten_thuoc_unaccent` sinh bằng hàm `unaccent()` **ngay trong SQL lúc insert** — cùng quy ước với `drug_chunks` hiện có (xem `backend/db/models.py::Drug`, migration 0001).
- [ ] Embedding cùng model và cùng số chiều với các chunk hiện có, để index HNSW dùng chung được.
- [ ] Hỏi chatbot về một thuốc vừa duyệt thì trả lời được, **có trích nguồn**.
- [ ] Khi thiếu dữ liệu cho một `field_group`, **không sinh chunk rỗng** — bỏ qua nhóm đó, đúng quy ước đã ghi trong `scripts/chunk_drugs.py`.
- [ ] Bot **không bịa** khi không có dữ liệu: nói rõ là chưa có thông tin thay vì suy diễn.
- [ ] Không đụng vào luồng kê đơn, `_chuan_hoa_item`, hay ma trận quyền của `drug_request`.

## Nút thắt thật — không phải phần code

Phần khó nhất **không phải** sinh embedding, mà là **lấy đâu ra nội dung y khoa** cho 4 nhóm trường đó. Bác sĩ khi gửi yêu cầu chỉ khai tên thuốc, dạng bào chế và đường dùng — không khai công dụng, tác dụng phụ, cách dùng, bảo quản.

Ba hướng, cần chốt trước khi code:

| | Hướng | Đánh giá |
|---|---|---|
| 1 | Bổ sung ô nhập nội dung vào form yêu cầu, bác sĩ tự khai | Có dữ liệu ngay, nhưng **không có nguồn** — xem mục dưới |
| 2 | Crawl theo tên thuốc như pipeline V2 đang làm | Có provenance thật, nhưng tên bác sĩ khai có thể không khớp nguồn nào |
| 3 | Admin nhập nội dung lúc duyệt, kèm bắt buộc khai nguồn | Chậm nhất, chất lượng cao nhất |

## Mâu thuẫn với ADR-0012 cần giải quyết

ADR-0012 đặt nguyên tắc dữ liệu thuốc phải có provenance. `product-vision.md` §6 ghi **rủi ro an toàn số 1** là agent "bịa" thông tin thuốc.

Nội dung do bác sĩ tự gõ thì **không có nguồn**. Nếu đưa thẳng vào `drug_chunks`, chatbot sẽ trả lời bằng dữ liệu không thẩm định mà người dùng không phân biệt được với dữ liệu có nguồn — đúng thứ FB-13 và FB-24 đã chất vấn.

Cần chốt một trong hai:

- **Bắt buộc khai nguồn** khi gửi yêu cầu (URL, tờ hướng dẫn sử dụng), và lưu vào chunk.
- **Đánh dấu chunk là "chưa thẩm định"** và cho bot nói rõ điều đó khi trả lời từ nguồn này.

Đây là quyết định sản phẩm/an toàn, không phải quyết định kỹ thuật — nên chốt với PM trước khi code.

## Vì sao không gấp

Luồng kê đơn **đã chạy đủ** mà không cần task này. Thuốc duyệt qua `drug_request` là nhánh hiếm (danh mục gốc có 3.556 thuốc), và với MVP thì **để chatbot im lặng về thuốc chưa thẩm định an toàn hơn** để nó trả lời bằng nội dung không nguồn.

Vì vậy task này là P2. Nếu trước Demo Day không kịp, cách xử lý đúng là **nói rõ giới hạn** trong phần demo, không phải vội nhét dữ liệu chưa thẩm định vào RAG.

## Tham chiếu

- ADR-0013 — danh mục thuốc là allowlist đóng
- ADR-0012 — provenance dữ liệu thuốc
- `specs/api-contracts.md` §1e — `drug-request-api`
- `backend/db/models.py::DrugRequest` — ghi chú kiến trúc đầy đủ
- `scripts/chunk_drugs.py` — quy ước 4 `field_group`
- `backend/services/retrieval.py::hybrid_search` — đường chatbot đọc `drug_chunks`
