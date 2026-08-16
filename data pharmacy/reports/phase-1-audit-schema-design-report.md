# Phase 1 Report --- Audit + Schema Design

**Ngày:** 2026-08-16  
**Phạm vi:** `data pharmacy/` legacy dataset, schema hiện tại, chunk staging hiện tại, plan Data V2.  
**Runtime production:** không thay đổi.

## 1. Output đã tạo

- Legacy audit report này cho Phase 1.
- Legacy manifest ở mức file/count/hash cho 11 file `thuoc.json`, `schema.json`, `_chunks.jsonl`.
- Dataset statistics cho `legacy-v1`.
- Canonical schema draft đã chốt ở mức entity: `drug_product`, `drug_id_map`, `ingredient`, `drug_product_ingredient`, `drug_knowledge`.
- Knowledge taxonomy V2 đã chốt ở mức draft: `INDICATION`, `ADVERSE_EFFECT`, `CONTRAINDICATION`, `PRECAUTION`, `INTERACTION`, `PREGNANCY_LACTATION`, `DRIVING_WARNING`, `ADMINISTRATION`, `GENERAL_DOSAGE`, `STORAGE`.
- Mapping principle đã chốt: public `drug_id` vẫn là legacy slug; UUID chỉ là internal `drug_product.id` trong giai đoạn migration.
- ADR-0012 draft đã tạo để chốt các quyết định kiến trúc trước Phase 2: legacy freeze, public/internal identity, V1/V2 song song, raw snapshot storage, ingredient parser conservative.

## 2. Số liệu chính

| Hạng mục | Số liệu |
|---|---:|
| Tổng số thuốc legacy | 3.562 |
| Số file `thuoc.json` | 11 |
| Số `danh_muc` chi tiết | 49 |
| Required field missing | 0 |
| Duplicate `id` | 0 |
| Duplicate `ten_thuoc` chính xác | 1 cặp |
| `thoi_diem_dung` không rỗng | 0 |
| `huong_dan_bao_quan` rỗng | 48 |
| `luu_y_dac_biet` rỗng | 7 |
| `_chunks.jsonl` lines | 14.200 |
| Distinct `drug_id` trong chunks | 3.562 |

Per folder:

| Folder | Records |
|---|---:|
| Thuốc bổ và vitamin | 316 |
| Thuốc da liễu | 307 |
| Thuốc kháng sinh | 425 |
| Thuốc kháng virus | 79 |
| Thuốc mắt, tai, mũi, họng | 188 |
| Thuốc thần kinh | 348 |
| Thuốc tim mạch và máu | 832 |
| Thuốc tiêm chích và dịch truyền | 159 |
| Thuốc tiêu hoá và gan mật | 625 |
| Thuốc trị tiểu đường | 201 |
| Thuốc điều trị ung thư | 82 |

Phân bố `duong_dung`: Uống 2.808, Bôi ngoài da 319, Tiêm 202, Nhỏ mắt 109, Tiêm truyền 69, Xịt 32, Nhỏ tai 11, Nhỏ mũi 10, Ngậm 2.

Phân bố `muc_nghiem_trong`: Nguy hiểm 1.388, Trung bình 1.352, Nhẹ 822.

Chunk field groups: `cong_dung` 3.562, `tac_dung_phu` 3.562, `cach_dung` 3.562, `bao_quan` 3.514.

Manifest hashes:

| File | SHA256 |
|---|---|
| `schema.json` | `F5456F0747D8AAE67D2E604BC39CD017FC36E10A0A3C52117DE8F803C8CE1E8C` |
| `_chunks.jsonl` | `5A6491BE6D0C8C258B1B3E0EDFC6DED0C9870E106798FF35755952CD486F507F` |
| `Thuốc bổ và vitamin/thuoc.json` | `5418C1004A7951BF5958FBF37A6B5A1653834A1EB242ECE04BC0DA7FDFF0E3D4` |
| `Thuốc da liễu/thuoc.json` | `12D2E6BA311ADA00B6C1A101BB00A1D938A517D0AA0441186B9ED62F9272EC58` |
| `Thuốc kháng sinh/thuoc.json` | `E61A767BD187EFE256F199217AB69B9E44242541DD42FF63DC2A67A11DBBD7F8` |
| `Thuốc kháng virus/thuoc.json` | `618806C0E980697071AB1A8C78A9E34C0BA892060BFBBBA299ACB7DB6D7ABB3B` |
| `Thuốc mắt, tai, mũi, họng/thuoc.json` | `4094628AA03751CCD8026F8A089E4795EA63EA64848B861F07591AB0F1B7E471` |
| `Thuốc thần kinh/thuoc.json` | `D1D10D270A694B3A0C8AA32CF40BD8570BF23FC02016A2645F26B75CDA670606` |
| `Thuốc tim mạch và máu/thuoc.json` | `4BCD71255CCFFE594FDC38FAEEF95CBDC036D9199306A27AD3849EE30A0751C5` |
| `Thuốc tiêm chích và dịch truyền/thuoc.json` | `EFC7212058DEE842C78BC299A1760455E0A1AA8899296121369E6C5ED7F1A50C` |
| `Thuốc tiêu hoá và gan mật/thuoc.json` | `76000CFCB23B678D21CAFAF188104485808D288747994058921F66C31B84FEC8` |
| `Thuốc trị tiểu đường/thuoc.json` | `51BE8D80946179682F56E243761E59724F5F32BFED68ECBF3B9C5508FF340BA4` |
| `Thuốc điều trị ung thư/thuoc.json` | `A786DC6BA1BAF6B33543B83820BFFADD654FF151029AA493C2BF9955A6A28FE8` |

## 3. Vấn đề phát hiện

- Legacy dataset không có raw snapshot, source URL, retrieved time per record.
- `source` hiện tại trong runtime chỉ là nhãn nội bộ theo field/chunk, không phải provenance truy ngược ra URL gốc.
- Có 1 cặp duplicate `ten_thuoc` chính xác: `Nifedipin t20 Retard Stella 10x10`; `id` không trùng nên chưa phải lỗi khóa.
- Có 48 thuốc thiếu `huong_dan_bao_quan`, kéo theo `bao_quan` chỉ có 3.514 chunks thay vì 3.562.
- Có 7 thuốc không có `luu_y_dac_biet`.
- `muc_nghiem_trong` là heuristic rule-based theo `danh_muc`, không phải fact y khoa per-drug.
- `duong_dung` là inferred data từ `dang_thuoc`, cần lưu provenance/inference metadata trong V2.

## 4. Quyết định còn mở

- Chốt target định lượng cho Phase 4-6: drug resolution match, knowledge coverage, cross-drug regression, latency.
- Chốt mức schema chi tiết cho `source_snapshot` và validation result.

## 4b. Quyết định đã chốt sau report

- **Legacy freeze:** giữ dataset hiện tại read-only + manifest SHA256 hiện có là đủ cho đồ án. Chưa cần archive/storage phức tạp.
- **Raw snapshot storage:** dùng filesystem raw JSON + metadata trong DB cho demo/3.562 thuốc. Chưa cần object storage.
- **Ingredient parser:** parse conservatively. Parse được chắc chắn thì structured; không chắc thì giữ `raw_ingredient`/`raw_strength` + warning, không đoán.
- **ADR:** tạo ADR ngắn trước Phase 2 vì public `drug_id = legacy slug`, internal `id = UUID`, và V1/V2 song song là quyết định kiến trúc ảnh hưởng các phase sau. Xem [ADR-0012](../../adrs/0012-drug-data-v2-compatibility-and-provenance.md).

## 5. Trạng thái

**PASS WITH ISSUES**

Phase 1 đủ điều kiện để đi tiếp sang Phase 2 ở mức demo-quality: đã có audit, số liệu, schema/taxonomy draft và nguyên tắc backward compatibility. Các issue chủ yếu là giới hạn cố hữu của legacy data, không blocker cho legacy importer, nhưng phải được giữ rõ trong report và không được hiểu nhầm là dữ liệu đã có provenance đầy đủ.
