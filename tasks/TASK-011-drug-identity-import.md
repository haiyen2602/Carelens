# TASK-011: DB-4B — Drug Identity Import

**Domain:** `drug-knowledge`
**Owner:** Nguyễn Minh Đạt + AI
**Sprint:** Chưa phân Sprint
**Status:** In Progress
**Ưu tiên:** P0

## Mục tiêu (Goal)

Import lớp định danh thuốc của Final Canonical Drug Data V2 vào local PostgreSQL để operational database có canonical `drug_product_id`. Việc import chỉ tạo lớp identity/reference phục vụ các bước migration tiếp theo; không thay đổi runtime Drug Knowledge, Search hoặc RAG.

## Phạm vi

Importer phải xử lý bốn artifact và bảng tương ứng:

- `drug_product.jsonl` → `drug_product`
- `drug_id_map.jsonl` → `drug_id_map`
- `ingredient.jsonl` → `ingredient`
- `drug_product_ingredient.jsonl` → `drug_product_ingredient`

Môi trường đích là local Docker/PostgreSQL trên migration head có additive schema Database Architecture V2 (revision hiện hành sau DB-4A; report DB-4A ghi nhận revision gốc `0023`, sau xử lý conflict được renumber thành `0025`).

## Acceptance Criteria (AC)

- [x] Đã đọc và xác minh `manifest.json` cùng schema/field thực tế của cả bốn Final Canonical V2 JSONL artifact trước khi viết mapping import.
- [x] Có importer cho `drug_product`, `drug_id_map`, `ingredient`, và `drug_product_ingredient`.
- [x] Importer dùng upsert/deterministic key và có thể chạy lại an toàn.
- [ ] Lần chạy lại trên cùng source và database tạo **0 bản ghi trùng lặp** và không làm sai lệch dữ liệu đã import.
- [ ] Import thành công vào một local Docker/PostgreSQL validation database đã upgrade qua additive schema DB-4A.
- [ ] Tổng số bản ghi hợp lệ trong database được đối soát với từng source artifact; mọi chênh lệch đều có giải thích và danh sách record cụ thể.
- [ ] Với `mapping_status=ACTIVE`, mỗi `legacy_drug_id` chỉ có tối đa một canonical `drug_product_id`.
- [ ] Không tự động sử dụng record `AMBIGUOUS` hoặc `RETIRED` làm active mapping/backfill mapping.
- [ ] Không có `drug_id_map.drug_product_id` hoặc `drug_product_ingredient.drug_product_id` trỏ tới product không tồn tại.
- [ ] Không có `drug_product_ingredient.ingredient_id` trỏ tới ingredient không tồn tại.
- [ ] Có report riêng cho mapping ambiguous, retired, unmapped hoặc record không thể import; nếu không có, report phải ghi rõ count bằng 0.
- [ ] SHA-256 hoặc cơ chế tương đương xác nhận các source artifact và manifest không bị importer sửa đổi.
- [ ] Không thay đổi `DRUG_KNOWLEDGE_BACKEND` và không chuyển runtime Drug Knowledge/Search/RAG sang database.
- [ ] Không backfill `prescription`, `prescription_item`, `medication_plan`, `schedule_rule`, legacy `dose_event` hoặc `dose_occurrence`.
- [ ] Không thêm/enforce FK hoặc `NOT NULL` đang được DB-4A/DB-3 để lại cho các validation gate sau.
- [ ] Không deploy Railway và không thay đổi shared/production database.
- [ ] Tạo report `data pharmacy/reports/database-architecture/09-drug-identity-import.md` với bằng chứng lệnh chạy, kết quả validation và kết luận readiness.

## Format kết luận bắt buộc trong report

```text
DB-4B DRUG IDENTITY IMPORT

IMPORT:
IDEMPOTENCY:
COUNT RECONCILIATION:
ACTIVE MAPPING:
ORPHANS:
AMBIGUOUS/UNMAPPED:
P0/P1:

READY FOR PRESCRIPTION BACKFILL:
YES / NO
```

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [ ] [`AGENTS.md`](../AGENTS.md)
- [ ] [`specs/domains.md`](../specs/domains.md) — ranh giới `drug-knowledge`
- [ ] [`specs/business-rules.md`](../specs/business-rules.md) — ràng buộc an toàn dữ liệu thuốc
- [ ] [`specs/api-contracts.md`](../specs/api-contracts.md) — xác nhận DB-4B không thay đổi public contract
- [ ] [`adrs/0004-project-structure-and-coding-convention.md`](../adrs/0004-project-structure-and-coding-convention.md)
- [ ] [`adrs/0005-definition-of-done.md`](../adrs/0005-definition-of-done.md)
- [ ] [`adrs/0012-drug-data-v2-compatibility-and-provenance.md`](../adrs/0012-drug-data-v2-compatibility-and-provenance.md)
- [ ] [`data pharmacy/reports/database-architecture/database_architecture_v2_plan.md`](../data%20pharmacy/reports/database-architecture/database_architecture_v2_plan.md) — baseline; ADR và report DB-1 → DB-4A mới hơn được ưu tiên nếu có khác biệt
- [ ] Toàn bộ report DB-1 → DB-4A trong [`data pharmacy/reports/database-architecture/`](../data%20pharmacy/reports/database-architecture/), đặc biệt `08-additive-schema-implementation.md`
- [ ] [`data pharmacy/v2/final_canonical/manifest.json`](../data%20pharmacy/v2/final_canonical/manifest.json) và bốn identity/reference JSONL artifact
- [ ] `backend/db/models.py`
- [ ] Migration additive schema DB-4A hiện hành trong `migrations/versions/`
- [ ] [`CONVENTIONAL-COMMITS-CHEATSHEET.md`](../CONVENTIONAL-COMMITS-CHEATSHEET.md)

## Gợi ý chia subtask (AI tự cập nhật khi bắt đầu)

- [ ] Ghi hash, kích thước, số dòng và schema thực tế của manifest/artifacts trước import.
- [ ] Đối chiếu schema artifact với ORM model và DDL DB-4A; báo blocker nếu không thể ánh xạ mà không tự bịa dữ liệu.
- [ ] Thiết kế thứ tự import bảo toàn quan hệ: product/ingredient trước, junction/mapping sau.
- [ ] Implement importer có dry-run/validation hợp lý và transaction boundary rõ ràng.
- [ ] Viết unit test cho parsing, mapping status, duplicate input và idempotent upsert.
- [ ] Upgrade/tạo local validation database và chạy import lần một.
- [ ] Chạy importer lần hai, so sánh counts và kiểm tra duplicate.
- [ ] Chạy validation về active mapping uniqueness, orphan và ambiguous/unmapped.
- [ ] So sánh hash source trước/sau.
- [ ] Viết `09-drug-identity-import.md` và dừng; không thực hiện prescription/dose backfill.

## Definition of Done

Áp dụng checklist chuẩn tại [`ADR-0005`](../adrs/0005-definition-of-done.md). Tiêu chí riêng của task:

- [ ] Importer và test tuân thủ convention trong ADR-0004.
- [ ] Unit/integration test liên quan pass; lint và compile/build liên quan pass.
- [ ] Local import, re-import và toàn bộ validation trong AC có bằng chứng tái lập được.
- [ ] Database dùng để validation được ghi rõ và không ghi đè/xóa local development database mặc định.
- [ ] Source artifacts giữ nguyên hash trước và sau import.
- [ ] Report `09-drug-identity-import.md` có đầy đủ format kết luận bắt buộc.
- [ ] P0/P1 được liệt kê rõ; `READY FOR PRESCRIPTION BACKFILL` chỉ là `YES` khi không còn blocker ảnh hưởng identity mapping/backfill.
- [ ] Không có thay đổi ngoài phạm vi DB-4B.

## Ngoài phạm vi / Không được làm

- Backfill prescription hoặc dose.
- Dual-write, shadow read, read-primary hoặc cutover runtime.
- Thay đổi Drug Knowledge facade, Search, RAG hay `DRUG_KNOWLEDGE_BACKEND`.
- Enforce FK/`NOT NULL` cho các trường đang chờ backfill/validation.
- Sửa nội dung Final Canonical V2 artifacts.
- Deploy Railway hoặc thao tác shared/production database.

## Ghi chú / trao đổi thêm

- Public `drug_id` tiếp tục là legacy slug; canonical UUID/string `drug_product_id` chỉ dùng nội bộ theo ADR-0012.
- Ambiguous/retired mapping có thể được lưu để audit nếu schema/source quy định, nhưng không được tự động coi là active mapping.
- Nếu revision local thực tế đã được renumber sau merge conflict, dùng migration head hiện hành và ghi rõ revision trong report thay vì ép database quay về revision số cũ.
- Reviewer bắt buộc: Nguyễn Minh Đạt (`drug-knowledge`) và Trương Quốc Trường cho phần database/backend theo `TEAM.md`.
