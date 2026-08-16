# Kế hoạch Data Rebuild V2 cho Agent nhắc lịch uống thuốc

> **Rà lại 2026-08-16** (đối chiếu với code/git thật — xem
> [`docs/drug-data-overview.md`](../docs/drug-data-overview.md)) + **2 quyết định mới đã chốt với
> Owner (Nguyễn Minh Đạt)** để loại bỏ 2 điểm mâu thuẫn/rủi ro lớn của bản plan gốc:
>
> 1. **Re-crawl scope (mục 2.1, 14, DoD mục 21):** **không crawl lại toàn bộ 3562 sản phẩm ngay**.
>    Dataset hiện tại được đóng băng là `legacy-v1`. Crawler V2 chỉ bắt buộc đảm bảo mọi dữ liệu
>    mới hoặc dữ liệu được recrawl từ thời điểm V2 trở đi có raw snapshot + provenance. Re-crawl
>    legacy làm theo batch ưu tiên, ví dụ `50 → 200 → toàn bộ nếu thật sự cần`, để tránh vừa làm
>    tăng rủi ro rate-limit/chặn IP vừa chặn tiến độ những phần không cần raw ngay.
> 2. **Drug identity (mục 5):** **giữ backward compatibility**. V2 có thể có internal ID mới
>    (`drug_product.id = UUID`), nhưng API/public contract trong giai đoạn migration vẫn dùng
>    `drug_id = legacy slug` như hiện tại (`panadol-extra`, ...). Thêm mapping `drug_id_map`
>    (`legacy_drug_id`, `drug_product_id`). Chỉ đổi public contract sang UUID nếu có ADR riêng và
>    migration plan đầy đủ cho prescription, fixtures, API, frontend, eval.
>
> Quyết định đi kèm: **Data V2 phải được xây song song với V1**. Không đập nền nhà trong lúc app
> đang đứng trên đó: V1 `drug`/`drug_chunks` vẫn chạy production/demo, V2 được đưa vào theo từng
> phase nhỏ, có compatibility layer và shadow comparison trước khi cutover từng capability.

## 1. Mục tiêu

Xây lại nền dữ liệu thuốc trước khi sửa Agent/RAG.

Sau phase này, hệ thống cần đạt được:

-   Dữ liệu thuốc có cấu trúc rõ ràng, không trộn nhiều loại thông tin
    vào một field.
-   Mỗi thông tin y khoa biết nó đến từ nguồn nào.
-   Phân biệt dữ liệu gốc từ website với dữ liệu do hệ thống suy
    ra/chuẩn hóa.
-   Agent có thể tìm đúng `drug_id` trước, sau đó lấy đúng loại kiến
    thức cần trả lời.
-   Vector search/embedding chỉ là lớp tìm kiếm bổ sung, không phải nơi
    lưu "sự thật".
-   Dữ liệu cũ vẫn được giữ để đối chiếu và migration, không sửa/xóa
    trực tiếp.

------------------------------------------------------------------------

## 2. Vấn đề của dữ liệu hiện tại

Pipeline hiện tại về cơ bản là:

``` text
Long Châu
→ crawl
→ thuoc.json
→ gộp thành 4 field_group
→ chunk
→ embedding
→ pgvector
```

Một số vấn đề chính:

### 2.1 Không giữ raw source đầy đủ

Crawler đọc `__NEXT_DATA__` của Long Châu rồi chuyển ngay sang schema
của app.

Điều này khiến về sau khó trả lời:

-   Record này crawl từ URL nào?
-   Crawl lúc nào?
-   Nội dung nguồn lúc đó là gì?
-   Parser version nào đã tạo record?
-   Nếu parser sai thì có thể parse lại từ dữ liệu gốc không?

### 2.2 Một field chứa quá nhiều loại kiến thức

Ví dụ `luu_y_dac_biet` có thể chứa:

-   chống chỉ định;
-   thận trọng;
-   tương tác thuốc;
-   thai kỳ/cho con bú;
-   ảnh hưởng lái xe;
-   đối tượng cần thận trọng.

Nhưng chunker hiện tại lại gộp toàn bộ phần này với `tac_dung_phu`.

Kết quả là một chunk "tác dụng phụ" thực tế có thể chứa cả chống chỉ
định và tương tác thuốc.

### 2.3 `cach_dung` cũng đang bị gộp

Hiện tại:

``` text
cach_dung =
huong_dan_su_dung
+ lieu_dung
+ duong_dung
```

Trong V2, ba loại dữ liệu này cần được phân biệt.

### 2.4 Thành phần thuốc đang bị flatten thành text

Ví dụ:

``` text
Vitamin B1 ... 125mg;
Pyridoxin ... 125mg;
Cyanocobalamin 125mcg
```

Trong khi nguồn đã có danh sách ingredient có cấu trúc.

### 2.5 Một số field là dữ liệu hệ thống suy ra

Ví dụ `duong_dung` có thể được suy ra từ `dang_thuoc`.

Điều này không sai, nhưng cần ghi rõ:

``` text
giá trị từ nguồn
```

khác với:

``` text
giá trị do rule của hệ thống suy ra
```

### 2.6 `muc_nghiem_trong` không phải thuộc tính y khoa chuẩn của thuốc

Field này hiện là rule nội bộ phục vụ logic missed-dose.

Không nên coi:

``` text
drug.muc_nghiem_trong = "Nhẹ"
```

là một fact y khoa của thuốc.

------------------------------------------------------------------------

# 3. Kiến trúc dữ liệu V2

Pipeline mới:

``` text
SOURCE
   ↓
RAW SNAPSHOT
   ↓
SOURCE PARSER
   ↓
CANONICAL DATA
   ↓
VALIDATION
   ↓
KNOWLEDGE DATA
   ↓
SEARCH / EMBEDDING
   ↓
AGENT
```

Ý nghĩa rất đơn giản:

> Giữ nguyên dữ liệu nguồn trước, chuẩn hóa sau, tìm kiếm sau cùng.

------------------------------------------------------------------------

# 4. Các bước triển khai

## Bước 1 --- Đóng băng dataset hiện tại

### Làm gì?

Giữ nguyên toàn bộ:

-   `thuoc.json`;
-   `_chunks.jsonl`;
-   database hiện tại;
-   crawler;
-   chunker;
-   embedding scripts.

Đặt thành một version, ví dụ:

``` text
legacy-v1
```

### Mục tiêu

Có bản backup/reference cố định để:

-   so sánh V1 với V2;
-   rollback;
-   kiểm tra migration;
-   không vô tình làm mất dữ liệu cũ.

Không sửa trực tiếp dataset legacy.

------------------------------------------------------------------------

## Bước 2 --- Lưu raw source khi crawl

### Làm gì?

Crawler mới phải lưu dữ liệu nguồn trước khi parse.

Ví dụ:

``` json
{
  "source": "nhathuoclongchau",
  "source_url": "...",
  "retrieved_at": "...",
  "content_hash": "...",
  "raw_next_data": {}
}
```

### Mục tiêu

Nếu parser có bug, chúng ta có thể parse lại mà không cần crawl lại
website.

Đồng thời mỗi record có provenance rõ ràng:

``` text
Thông tin này đến từ đâu?
→ URL nào?
→ crawl lúc nào?
→ raw content nào?
```

------------------------------------------------------------------------

## Bước 3 --- Tạo Canonical Drug Schema V2

### Làm gì?

Không dùng `thuoc.json` hiện tại làm schema cuối.

Tách dữ liệu thành các entity rõ ràng.

Core:

``` text
data_source
source_snapshot

drug_product
drug_alias

ingredient
drug_product_ingredient

drug_knowledge
```

### Mục tiêu

Phân biệt:

``` text
Thuốc là gì?
```

với:

``` text
Chúng ta biết gì về thuốc đó?
```

------------------------------------------------------------------------

# 5. Drug Product

Ví dụ:

``` text
drug_product

id
legacy_drug_id

brand_name
display_name

dosage_form
route

package_text
category

source_snapshot_id
```

Primary key nên là UUID.

UUID là internal identity của canonical V2, không phải public contract ngay lập tức.

`legacy_drug_id` vẫn được giữ để migration dữ liệu cũ và để API/public contract tiếp tục dùng
`drug_id` dạng slug trong giai đoạn chạy song song.

Mapping bắt buộc:

``` text
drug_id_map

legacy_drug_id
drug_product_id
```

Nguyên tắc migration:

-   `drug_product.id` là UUID nội bộ của V2.
-   `legacy_drug_id` là slug hiện tại trong `thuoc.json`, `drug.id`,
    `drug_chunks.drug_id`, `PrescriptionDTO.items[].drug_id`.
-   `DrugInfoDTO.drug_id`, `PrescriptionDTO.items[].drug_id` và frontend vẫn dùng
    legacy slug cho đến khi có ADR đổi public contract.
-   Không đổi public `drug_id` sang UUID trong Data Rebuild phase này.

------------------------------------------------------------------------

# 6. Ingredient

Không giữ thành phần thuốc chỉ dưới dạng một string.

Thiết kế:

``` text
ingredient

id
canonical_name
```

và:

``` text
drug_product_ingredient

drug_product_id
ingredient_id

strength_value
strength_unit
raw_strength
```

Ví dụ:

``` text
3B Agi-Neurin
   │
   ├── Thiamin mononitrate | 125 | mg
   ├── Pyridoxine hydrochloride | 125 | mg
   └── Cyanocobalamin | 125 | mcg
```

### Mục tiêu

Sau này có thể tìm kiếm:

-   thuốc chứa hoạt chất X;
-   thuốc có nhiều hoạt chất;
-   thuốc cùng hoạt chất nhưng khác brand;
-   strength chính xác.

------------------------------------------------------------------------

# 7. Drug Knowledge

Đây là thay đổi quan trọng nhất.

Thay vì 4 nhóm:

``` text
cong_dung
tac_dung_phu
cach_dung
bao_quan
```

chuyển thành knowledge type rõ ràng:

``` text
INDICATION
ADVERSE_EFFECT
CONTRAINDICATION
PRECAUTION
INTERACTION
PREGNANCY_LACTATION
DRIVING_WARNING

ADMINISTRATION
GENERAL_DOSAGE

STORAGE
```

Schema ví dụ:

``` text
drug_knowledge

id
drug_product_id

knowledge_type

content_raw
content_normalized

source_snapshot_id
source_section

review_status
created_at
```

### Mục tiêu

Agent hỏi:

> Thuốc này có chống chỉ định gì?

thì backend lấy:

``` text
drug_id
+
knowledge_type = CONTRAINDICATION
```

Không cần tìm trong một chunk lớn chứa đủ loại thông tin.

------------------------------------------------------------------------

# 8. Không đưa `thoi_diem_dung` vào Drug Knowledge

`thoi_diem_dung` không phải kiến thức chung của thuốc.

Ví dụ:

``` text
Panadol uống lúc 8h
```

là lịch của một bệnh nhân cụ thể.

Nó phải nằm ở domain:

``` text
Prescription
MedicationPlan
ScheduleRule
```

Không nằm trong drug dataset.

------------------------------------------------------------------------

# 9. Xử lý `muc_nghiem_trong`

Không đưa field này vào canonical `drug_product`.

Trong migration có thể giữ dưới tên:

``` text
legacy_missed_dose_risk
```

và đánh dấu:

``` text
NOT_CLINICALLY_REVIEWED
```

### Mục tiêu

Không để hệ thống hiểu nhầm một heuristic nội bộ thành thuộc tính y khoa
chính thức của thuốc.

------------------------------------------------------------------------

# 10. Phân biệt source data và inferred data

Ví dụ route có thể được nguồn cung cấp hoặc hệ thống suy ra.

Lưu thêm metadata:

``` text
route = ORAL
route_source = SOURCE_EXPLICIT
```

hoặc:

``` text
route = ORAL
route_source = INFERRED_FROM_DOSAGE_FORM
route_rule_version = route-v2
```

### Mục tiêu

Biết chính xác:

> Website nói điều này

hay:

> Code của chúng ta suy ra điều này.

------------------------------------------------------------------------

# 11. Validation

Sau khi parse, mỗi record phải chạy validation.

Ví dụ:

``` text
drug name missing?
ingredient malformed?
strength malformed?
unknown unit?
route conflict?
knowledge không có source?
duplicate drug?
empty knowledge?
```

Kết quả:

``` text
PASS
WARNING
FAIL
```

`FAIL` không được tự động đưa vào production knowledge base.

### Mục tiêu

Không để crawler chạy thành công đồng nghĩa với dữ liệu đúng.

------------------------------------------------------------------------

# 12. Review status

Mỗi knowledge item nên có trạng thái:

``` text
UNREVIEWED
AUTO_VALIDATED
HUMAN_REVIEWED
REJECTED
```

### Mục tiêu

Phân biệt:

``` text
schema đúng
```

với:

``` text
nội dung y khoa đã được kiểm chứng.
```

Hai khái niệm này khác nhau.

------------------------------------------------------------------------

# 13. Migration dataset cũ

Không cần bỏ 3.562 thuốc hiện tại.

Viết:

``` text
legacy_importer
```

để chuyển:

``` text
thuoc.json V1
        ↓
Canonical V2
```

Mapping cơ bản:

``` text
ten_thuoc
→ drug_product

ham_luong
→ ingredient parser

tac_dung
→ INDICATION

tac_dung_phu
→ ADVERSE_EFFECT

huong_dan_su_dung
→ ADMINISTRATION

lieu_dung
→ GENERAL_DOSAGE

huong_dan_bao_quan
→ STORAGE

luu_y_dac_biet
→ phân loại theo heading
   → CONTRAINDICATION
   → PRECAUTION
   → INTERACTION
   → PREGNANCY_LACTATION
   → DRIVING_WARNING
```

Dữ liệu legacy chưa có raw provenance phải được đánh dấu rõ.

### Mục tiêu

Tận dụng dataset hiện tại để bootstrap V2 thay vì làm lại mọi thứ ngay
lập tức.

------------------------------------------------------------------------

# 14. Re-crawl theo batch ưu tiên

Sau khi crawler V2 hoạt động:

``` text
legacy record
     ↓
re-crawl
     ↓
raw snapshot
     ↓
canonical parser
     ↓
compare legacy vs new
     ↓
accept / review
```

Không bắt buộc crawl lại toàn bộ dataset trước khi tiếp tục phát triển.

Quyết định hiện tại:

-   Dataset 3.562 thuốc hiện tại được giữ làm `legacy-v1`.
-   Legacy importer có thể chuyển toàn bộ legacy sang canonical V2 nhưng phải đánh dấu
    provenance là `LEGACY_NO_RAW_SOURCE`.
-   Crawler V2 dùng cho dữ liệu mới/recrawl từ thời điểm đó trở đi, và mọi output của nó phải có
    `source_url`, `retrieved_at`, `content_hash`, raw snapshot.
-   Re-crawl legacy chạy theo batch ưu tiên, ví dụ `50 → 200 → toàn bộ nếu thật sự cần`.
-   Không đặt full re-crawl toàn corpus làm blocker cho Phase 1-4.

### Mục tiêu

Nâng dần dataset từ:

``` text
LEGACY_NO_RAW_SOURCE
```

sang:

``` text
SOURCE_CAPTURED
```

------------------------------------------------------------------------

# 15. Chunking V2

Chỉ làm chunking **sau khi canonical data ổn định**.

Không còn:

``` text
Tác dụng phụ
+
Chống chỉ định
+
Tương tác
+
Thai kỳ
→ một chunk
```

Thay vào đó:

``` text
drug_knowledge
      ↓
knowledge type
      ↓
nếu content dài
      ↓
split thành nhiều chunk cùng knowledge type
```

Ví dụ:

``` text
INTERACTION
   ├── chunk 1
   └── chunk 2
```

### Mục tiêu

Không làm mất semantic structure chỉ để phục vụ embedding.

------------------------------------------------------------------------

# 16. Embedding

Embedding là bước cuối, không phải canonical data.

Thiết kế riêng:

``` text
knowledge_embedding

knowledge_id
embedding_model
embedding_version
content_hash
embedding
created_at
```

### Mục tiêu

Có thể thay model embedding mà không phải thay dữ liệu thuốc.

Nếu content không đổi thì không cần embed lại.

------------------------------------------------------------------------

# 17. Agent sẽ sử dụng dữ liệu như thế nào?

Sau Data V2, luồng mong muốn:

``` text
User:
"3B Agi-Neurin có chống chỉ định gì?"

        ↓

Agent hiểu:
drug = "3B Agi-Neurin"
topic = CONTRAINDICATION

        ↓

Drug Resolver

        ↓

drug_id

        ↓

Knowledge Service

        ↓

WHERE drug_id = ?
AND knowledge_type = CONTRAINDICATION

        ↓

Answer
```

Vector search không cần tham gia vào trường hợp này.

### Mục tiêu

Nguyên tắc:

> Resolve thuốc trước → lấy structured truth → semantic search khi thật
> sự cần → LLM diễn đạt cuối cùng.

------------------------------------------------------------------------

# 18. Chạy song song V1/V2 và feature flag

Trong migration, không thay V1 trực tiếp bằng V2. Tạo facade để routing theo backend được chọn:

``` text
                 ┌→ V1 drug / drug_chunks
request → facade ┤
                 └→ V2 drug_product / drug_knowledge
```

Feature flag:

``` text
DRUG_KNOWLEDGE_BACKEND=v1|v2|shadow
```

Ý nghĩa:

-   `v1`: response lấy từ V1 như hiện tại.
-   `v2`: response lấy từ V2.
-   `shadow`: response vẫn lấy từ V1, nhưng V2 chạy song song để log/so sánh chất lượng.

Chỉ switch capability sang V2 khi đạt acceptance criteria đã đo:

-   drug resolution match đạt target;
-   knowledge coverage đạt target;
-   không missing prescription joins;
-   không có cross-drug regression;
-   eval suite pass;
-   latency chấp nhận được.

------------------------------------------------------------------------

# 19. Thứ tự Agent nên thực hiện công việc

Không để một agent task làm tất cả. Data Rebuild được chia thành các phase nhỏ:

## Phase 1 --- Audit + schema design

Phase này **không đụng runtime production**.

Output:

``` text
legacy manifest
dataset statistics
backup/reference version
canonical schema draft
knowledge taxonomy
V1 → V2 mapping
```

------------------------------------------------------------------------

## Phase 2 --- Canonical V2 tables + legacy importer

Output:

``` text
drug_product
drug_id_map
ingredient
drug_product_ingredient
drug_knowledge
legacy importer
quality report
```

Chưa sửa RAG.

------------------------------------------------------------------------

## Phase 3 --- Crawler V2 + provenance

Output:

``` text
raw snapshot
source metadata
parser
canonical record
```

------------------------------------------------------------------------

## Phase 4 --- V1/V2 compatibility layer

Output:

``` text
facade
DRUG_KNOWLEDGE_BACKEND=v1|v2|shadow
shadow comparison logs
no production behavior change in shadow mode
```

------------------------------------------------------------------------

## Phase 5 --- Knowledge/Search V2

Output:

``` text
PASS
WARNING
FAIL

duplicate report
missing-data report
provenance report
knowledge-type report
Drug Resolver
Drug Alias
SQL indexes
Knowledge Service
```

Review thủ công một sample đại diện trước khi tiếp tục.

------------------------------------------------------------------------

## Phase 6 --- RAG migration

Sau khi canonical dataset và Knowledge Service được chấp nhận mới xây:

``` text
knowledge chunking
embedding
pgvector
semantic search
evaluation
```

------------------------------------------------------------------------

## Phase 7 --- Agent integration

Cuối cùng mới tích hợp Agent dùng V2 theo từng capability:

``` text
drug identity resolution
knowledge lookup by type
answer generation
audit_log
controlled cutover
```

------------------------------------------------------------------------

# 20. Demo-quality và Production-quality scope

Không trộn scope demo/đồ án với scope production thật.

## Demo-quality V2

Phạm vi hợp lý cho đồ án/demo:

-   audit 3.562 records;
-   thiết kế canonical schema;
-   migrate legacy data sang V2;
-   crawler V2 lưu provenance cho dữ liệu mới/recrawl;
-   giữ slug `drug_id`;
-   chưa bắt buộc re-crawl toàn bộ;
-   chưa bỏ `drug_chunks` V1.

## Production-quality V2

Chỉ nâng lên mức này khi mục tiêu là sản phẩm thật:

-   re-crawl toàn corpus;
-   provenance per-record đầy đủ;
-   review y khoa;
-   versioning;
-   source reconciliation;
-   controlled cutover V1 → V2.

Roadmap mục tiêu:

``` text
LEGACY V1
   │
   ├── giữ nguyên để app tiếp tục chạy
   │
   ▼
Audit + Canonical Design
   │
   ▼
V2 Database + Legacy Import
   │
   ▼
Compatibility Mapping
legacy_drug_id ↔ UUID
   │
   ▼
Crawler V2 + Provenance
   │
   ▼
V1/V2 Shadow Comparison
   │
   ▼
Knowledge/Search V2
   │
   ▼
Agent sử dụng V2
   │
   ▼
sau cùng mới deprecate V1
```

------------------------------------------------------------------------

# 21. Definition of Done cho Data Phase

Không chuyển sang rebuild Agent/RAG cho đến khi tối thiểu đạt:

-   Mỗi drug có canonical ID.
-   Ingredient được lưu có cấu trúc khi nguồn cho phép.
-   Knowledge được tách theo semantic type.
-   Knowledge liên kết được với drug.
-   Dữ liệu mới/recrawl bằng crawler V2 có source URL / snapshot / retrieval time.
-   Dữ liệu inferred được phân biệt với source data.
-   Legacy provenance unknown được đánh dấu rõ.
-   Có `drug_id_map` giữa legacy slug và UUID nội bộ.
-   Public contract vẫn dùng legacy slug cho đến khi có ADR đổi contract.
-   Có compatibility/shadow strategy trước khi switch capability sang V2.
-   `thoi_diem_dung` không còn trong canonical drug data.
-   `muc_nghiem_trong` không còn được coi là thuộc tính y khoa
    canonical.
-   Validation report chạy được.
-   Dataset có version.
-   Có thể rebuild canonical dataset từ raw snapshot đối với dữ liệu đã `SOURCE_CAPTURED`.
-   Có sample được review trước khi production migration.

------------------------------------------------------------------------

# 22. Nguyên tắc quan trọng cho Agent

Agent thực hiện migration phải tuân thủ:

1.  **Không xóa dữ liệu legacy.**
2.  **Không tự sửa nội dung y khoa để "cho đúng hơn".**
3.  **Không tự suy diễn dữ liệu thiếu nếu không có rule rõ ràng.**
4.  **Giữ raw source bất biến.**
5.  **Mọi transformation phải reproducible.**
6.  **Source fact và inferred fact phải phân biệt được.**
7.  **Không làm embedding trước khi canonical schema ổn định.**
8.  **Không dùng LLM extraction nếu deterministic parser có thể làm
    được.**
9.  **Case không chắc chắn phải đưa vào review queue thay vì đoán.**
10. **Mỗi phase phải có quality report trước khi chuyển phase tiếp
    theo.**

------------------------------------------------------------------------

# 23. To-do triển khai

Checklist này dùng để tách task nhỏ theo phase. Mỗi item nên có output kiểm chứng được, không chỉ
“đã code xong”.

## Phase 1 --- Audit + schema design

- [ ] Đóng băng dataset hiện tại thành `legacy-v1`.
- [ ] Tạo legacy manifest: danh sách file, số record từng danh mục, hash/checksum, thời điểm freeze.
- [ ] Ghi rõ `data pharmacy/*/thuoc.json`, `_chunks.jsonl`, crawler hiện tại, chunker hiện tại và DB hiện tại là V1 reference.
- [ ] Rà lại thống kê 3.562 records: missing field, duplicate `id`, duplicate `ten_thuoc`, phân bố `danh_muc`, `duong_dung`, `muc_nghiem_trong`.
- [ ] Chốt canonical schema draft cho `drug_product`, `drug_id_map`, `ingredient`, `drug_product_ingredient`, `drug_knowledge`.
- [ ] Chốt knowledge taxonomy V2: `INDICATION`, `ADVERSE_EFFECT`, `CONTRAINDICATION`, `PRECAUTION`, `INTERACTION`, `PREGNANCY_LACTATION`, `DRIVING_WARNING`, `ADMINISTRATION`, `GENERAL_DOSAGE`, `STORAGE`.
- [ ] Chốt source/inferred metadata: `SOURCE_EXPLICIT`, `INFERRED_FROM_DOSAGE_FORM`, `LEGACY_NO_RAW_SOURCE`, `SOURCE_CAPTURED`.
- [ ] Chốt V1 → V2 mapping cho từng field trong `schema.json`.
- [ ] Ghi rõ rule: public `drug_id` vẫn là legacy slug trong giai đoạn migration.
- [ ] Ghi rõ Phase 1 không đụng runtime production.

Output bắt buộc:

``` text
legacy manifest
dataset audit report
canonical schema draft
knowledge taxonomy
V1 → V2 mapping
```

## Phase 2 --- Canonical V2 tables + legacy importer

- [ ] Tạo migration/schema cho các bảng V2 ở trạng thái song song với V1, không xoá/sửa bảng V1.
- [ ] Tạo `drug_product` với `id = UUID` và `legacy_drug_id`.
- [ ] Tạo `drug_id_map(legacy_drug_id, drug_product_id)`.
- [ ] Tạo `ingredient` và `drug_product_ingredient`.
- [ ] Tạo `drug_knowledge`.
- [ ] Thêm cột/field metadata cho provenance và inferred/source distinction.
- [ ] Viết `legacy_importer` đọc `data pharmacy/*/thuoc.json` và nạp sang V2.
- [ ] Import `legacy_drug_id` từ `thuoc.id` hiện tại, không tự tạo public ID mới.
- [ ] Parse ingredient từ `ham_luong` ở mức best-effort; phần không chắc chắn giữ `raw_strength` và đánh warning.
- [ ] Map `tac_dung` → `INDICATION`.
- [ ] Map `tac_dung_phu` → `ADVERSE_EFFECT`.
- [ ] Map `huong_dan_su_dung` → `ADMINISTRATION`.
- [ ] Map `lieu_dung` → `GENERAL_DOSAGE`.
- [ ] Map `huong_dan_bao_quan` → `STORAGE`.
- [ ] Tách `luu_y_dac_biet` theo heading sang các knowledge type phù hợp.
- [ ] Đánh dấu toàn bộ legacy knowledge là `LEGACY_NO_RAW_SOURCE`.
- [ ] Đưa case không phân loại chắc chắn vào report/review queue, không đoán.
- [ ] Sinh quality report sau import.

Output bắt buộc:

``` text
V2 tables
legacy importer
drug_id_map coverage report
ingredient parse report
knowledge-type coverage report
legacy provenance report
```

## Phase 3 --- Crawler V2 + provenance

- [ ] Thiết kế raw snapshot format cho Long Châu.
- [ ] Lưu `source`, `source_url`, `retrieved_at`, `content_hash`, parser version và `raw_next_data`.
- [ ] Đảm bảo raw snapshot immutable sau khi ghi.
- [ ] Viết parser V2 từ raw snapshot sang canonical record.
- [ ] Không parse trực tiếp vào schema cuối nếu chưa lưu raw.
- [ ] Thêm validation cho snapshot thiếu URL/thời điểm/hash.
- [ ] Tạo batch recrawl runner, mặc định batch nhỏ.
- [ ] Chạy pilot batch 50 record ưu tiên.
- [ ] Sinh report so sánh legacy vs recrawl.
- [ ] Chỉ tăng batch lên 200/toàn bộ khi có quyết định riêng.

Output bắt buộc:

``` text
raw snapshot files/table
parser V2
pilot recrawl report
legacy-vs-source comparison report
```

## Phase 4 --- V1/V2 compatibility layer

- [ ] Thiết kế facade cho drug knowledge lookup.
- [ ] Thêm feature flag `DRUG_KNOWLEDGE_BACKEND=v1|v2|shadow`.
- [ ] `v1`: giữ hành vi hiện tại.
- [ ] `v2`: đọc từ V2 knowledge service.
- [ ] `shadow`: trả response từ V1 nhưng chạy V2 song song để log kết quả.
- [ ] Log so sánh V1/V2: resolved drug, knowledge type, coverage, missing data, latency.
- [ ] Đảm bảo `PrescriptionDTO.items[].drug_id` legacy slug vẫn join được qua `drug_id_map`.
- [ ] Viết test không có missing prescription joins với dữ liệu legacy.
- [ ] Không bật `v2` mặc định trước khi Phase 5-6 đạt AC.

Output bắt buộc:

``` text
facade
feature flag
shadow comparison log
prescription join compatibility tests
```

## Phase 5 --- Knowledge/Search V2

- [ ] Xây Drug Resolver dùng `drug_product`, `drug_alias`, `drug_id_map`.
- [ ] Xây Knowledge Service lookup theo `legacy_drug_id` hoặc `drug_product_id`.
- [ ] Hỗ trợ query theo `knowledge_type`.
- [ ] Thêm index cho `legacy_drug_id`, `drug_product_id`, `knowledge_type`, tên thuốc đã chuẩn hóa.
- [ ] Viết validation report: duplicate, missing data, empty knowledge, unknown unit, route conflict.
- [ ] Đo drug resolution match so với V1/eval set.
- [ ] Đo knowledge coverage theo từng knowledge type.
- [ ] Đo cross-drug regression.
- [ ] Review thủ công sample đại diện.

Output bắt buộc:

``` text
Drug Resolver V2
Knowledge Service V2
validation report
coverage report
manual review sample
```

## Phase 6 --- RAG migration

- [ ] Chỉ chunk từ `drug_knowledge`, không chunk trực tiếp từ `thuoc.json`.
- [ ] Chunk giữ nguyên `knowledge_type`.
- [ ] Tạo `knowledge_embedding`.
- [ ] Lưu `embedding_model`, `embedding_version`, `content_hash`.
- [ ] Không embed lại nếu `content_hash` không đổi.
- [ ] Xây semantic search V2 trên knowledge chunks.
- [ ] Chạy eval suite hiện tại trên V1 và V2.
- [ ] So sánh latency V1/V2.
- [ ] So sánh recall/precision và cross-drug misattribution.
- [ ] Chỉ cho phép `DRUG_KNOWLEDGE_BACKEND=v2` khi eval đạt target.

Output bắt buộc:

``` text
knowledge chunker
knowledge embeddings
semantic search V2
V1/V2 eval comparison
latency report
```

## Phase 7 --- Agent integration

- [ ] Tích hợp Agent dùng facade thay vì gọi trực tiếp V1 retrieval.
- [ ] Resolve thuốc trước, lookup knowledge theo type sau.
- [ ] Với câu hỏi structured như chống chỉ định/tương tác/liều dùng/bảo quản, ưu tiên Knowledge Service.
- [ ] Chỉ dùng semantic search khi lookup structured không đủ.
- [ ] Ghi audit log backend đang dùng: `v1`, `v2`, hoặc `shadow`.
- [ ] Ghi audit log `legacy_drug_id`, `drug_product_id`, `knowledge_type`, source/provenance status.
- [ ] Chạy shadow trong demo trước khi bật V2 thật.
- [ ] Có rollback đơn giản về `DRUG_KNOWLEDGE_BACKEND=v1`.

Output bắt buộc:

``` text
agent integration through facade
audit log update
shadow run report
rollback path
```

## Cutover/deprecate V1

Chỉ làm sau Phase 7, không nằm trong demo-quality scope mặc định.

- [ ] Có ADR riêng cho public contract nếu muốn đổi `drug_id` từ legacy slug sang UUID.
- [ ] Có migration plan cho prescription, fixtures, frontend, API và eval.
- [ ] Có full corpus recrawl nếu chuyển sang production-quality scope.
- [ ] Có provenance per-record đầy đủ hoặc lý do ngoại lệ rõ ràng.
- [ ] Có review y khoa/source reconciliation nếu định dùng như sản phẩm thật.
- [ ] Chạy V2 production một thời gian đủ dài trước khi deprecate V1.
- [ ] Chỉ xoá hoặc archive V1 khi có rollback alternative đã được review.

------------------------------------------------------------------------

## Tóm tắt

Toàn bộ kế hoạch có thể nhớ bằng một dòng:

``` text
Giữ nguồn
→ Chuẩn hóa
→ Tách kiến thức
→ Validate
→ Migrate
→ Search
→ Embed
→ Agent
```

Mục tiêu không phải tạo ra nhiều chunk tốt hơn.

Mục tiêu là tạo ra **một Drug Knowledge Base đáng tin cậy**, để chatbot
chỉ cần lấy đúng dữ liệu thay vì phải dùng RAG/LLM để đoán dữ liệu nào
là đúng.
