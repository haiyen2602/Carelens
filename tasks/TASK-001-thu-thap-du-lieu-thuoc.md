# TASK-001: Thu thập & chuẩn hoá dữ liệu thuốc cho RAG

**Domain:** `drug-knowledge`
**Owner:** Nguyễn Minh Đạt + AI
**Sprint:** sprint-02
**Status:** In Progress
**Ưu tiên:** P0 · **Feature:** [`FEAT-006`](../specs/features.md#feat-006--rag-thông-tin-thuốc-có-nguồn)

## Mục tiêu (Goal)

Đưa được một bộ dữ liệu thuốc **thật, có nguồn trích dẫn, đúng schema** vào repo để làm nền cho RAG. Đây là rủi ro số 1 của dự án: không có dữ liệu đủ tốt thì agent sẽ bịa thông tin y tế (xem [`docs/journal.md`](../docs/journal.md) Week 1).

## Acceptance Criteria (AC)

- [ ] Có tối thiểu **50 bản ghi thuốc** trong `data pharmacy/`, ưu tiên thuốc phổ biến cho **bệnh mãn tính** (tim mạch, huyết áp, tiểu đường) + nhóm cảm/ho đã có sẵn.
- [ ] Mỗi bản ghi **validate pass** theo [`data pharmacy/schema.json`](../data%20pharmacy/schema.json) — đủ 8 trường bắt buộc: `ten_thuoc`, `ham_luong`, `dang_thuoc`, `tong_so_luong`, `huong_dan_su_dung`, `lieu_dung`, `duong_dung`, `thoi_diem_dung`.
- [ ] Mỗi bản ghi có `id` (tự sinh từ tên thuốc) và `danh_muc` (tự lấy theo tên thư mục) — do **script điền**, không gõ tay.
- [ ] Mỗi bản ghi có **nguồn trích dẫn** (URL + ngày truy cập) truy vết được về tờ hướng dẫn sử dụng / Dược thư / trang chính thức. Bản ghi không có nguồn → **không được commit**.
- [ ] Có script validate chạy được bằng một lệnh (`make validate-data` hoặc tương đương) và **được nối vào CI** — CI đỏ nếu có file sai schema hoặc thiếu nguồn.
- [ ] Có `data pharmacy/README.md` cập nhật: nguồn đã dùng, quy trình thêm thuốc mới, giới hạn đã biết của bộ dữ liệu.
- [ ] Ghi rõ **những gì bộ dữ liệu này KHÔNG có** (VD: chưa có bảng tương tác thuốc–thuốc) để FEAT-007 không giả định nhầm.

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [ ] [`/specs/features.md`](../specs/features.md) — FEAT-006
- [ ] [`/specs/domains.md`](../specs/domains.md) — ranh giới `drug-knowledge`, ràng buộc "không bao giờ trả thông tin không có `source`"
- [ ] [`/specs/business-rules.md`](../specs/business-rules.md) — BR-7.x (agent không chẩn đoán/kê đơn)
- [ ] [`/adrs/0008-vector-store-pgvector.md`](../adrs/0008-vector-store-pgvector.md)
- [ ] [`data pharmacy/schema.json`](../data%20pharmacy/schema.json) + [`data pharmacy/_template.json`](../data%20pharmacy/_template.json)
- [ ] [`AGENTS.md`](../AGENTS.md)

## Gợi ý chia subtask (AI tự cập nhật khi bắt đầu)

- [ ] Chốt **danh sách nguồn hợp lệ** và ghi vào `data pharmacy/README.md` (nguồn nào được dùng, nguồn nào bị loại và vì sao)
- [ ] Chốt danh sách 50+ thuốc mục tiêu theo nhóm bệnh mãn tính — PM/Team Lead duyệt trước khi thu thập
- [ ] Viết script thu thập/chuẩn hoá → `raw.md` → `thuoc.json` theo đúng cấu trúc thư mục hiện có
- [ ] Viết script tự sinh `id` + `danh_muc`
- [ ] Viết script validate schema + kiểm tra trường nguồn; nối vào `Makefile` và `.github/workflows/ci.yml`
- [ ] Rà tay ngẫu nhiên **10 bản ghi** đối chiếu nguồn gốc (chống lỗi im lặng của script/LLM), ghi kết quả rà vào README
- [ ] Cập nhật `data pharmacy/README.md` + đánh dấu FEAT-006 trong backlog

## Definition of Done

Áp dụng checklist chuẩn ở [`ADR-0005`](../adrs/0005-definition-of-done.md), **kèm checklist bổ sung cho task đụng an toàn/dữ liệu bệnh nhân**. Tiêu chí riêng của task này:

- [ ] Script validate chạy xanh trên toàn bộ `data pharmacy/`
- [ ] Không commit dữ liệu bệnh nhân thật, không commit nội dung có bản quyền dạng copy nguyên khối
- [ ] Kết quả rà tay 10 bản ghi được ghi lại (có bằng chứng, không nói miệng)

## Ghi chú / trao đổi thêm

- **Rủi ro đã ghi trong sprint:** nếu hết ngày 3 của sprint vẫn chưa chốt được nguồn → thu hẹp còn 20–30 thuốc phổ biến, **làm sâu thay vì rộng**. Quyết định thu hẹp phải ghi lại ở đây.
- Embedding và nạp lên pgvector **không** thuộc task này — đó là việc của Sprint 03 (FEAT-006 phần RAG). Task này chỉ lo dữ liệu sạch + có nguồn trong repo.
- `[CẦN CHỐT]` Có crawl tự động hay nhập tay bán thủ công? Ảnh hưởng tới thời gian và rủi ro sai dữ liệu — Team Lead quyết trước khi bắt đầu.

---
**Điều hướng:** [Sprint 02](../planning/sprints/sprint-02.md) · [Backlog](../planning/backlog.md) · [Tasks](./)
