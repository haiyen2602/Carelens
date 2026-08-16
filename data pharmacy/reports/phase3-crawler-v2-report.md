# Phase 3 Report --- Crawler V2 Raw Snapshot Pilot

**Ngày:** 2026-08-16T09:22:00.274279+00:00  
**Scope:** Crawler V2 pilot only, no full-corpus crawl.  
**Legacy/runtime:** not modified.

## 1. Output đã tạo

- `scripts/data_v2/crawler_v2.py`
- `data pharmacy/v2/raw_snapshots/longchau/*.json`
- `data pharmacy/v2/source_snapshot.jsonl`
- `data pharmacy/v2/fresh_crawl_pilot/drug_product.jsonl`
- `data pharmacy/v2/fresh_crawl_pilot/drug_knowledge.jsonl`
- `data pharmacy/v2/fresh_crawl_pilot/drug_product_ingredient.jsonl`
- `data pharmacy/v2/fresh_crawl_pilot/validation.jsonl`
- `data pharmacy/reports/phase3-crawler-v2-report.md`

## 2. Số liệu chính

| Metric | Value |
|---|---:|
| Category URLs used | 4 |
| Product URLs discovered | 48 |
| Product URLs fetched | 48 |
| Raw snapshots written | 48 |
| Source metadata rows | 48 |
| Fresh V2 drug products | 48 |
| Fresh V2 knowledge items | 576 |
| Validation PASS | 43 |
| Validation WARNING | 5 |
| Validation FAIL | 0 |
| Matched Legacy V1 by `drug_id` | 37 |
| Matched Migrated V2 by `drug_id` | 37 |
| Knowledge lost from parsed fields | 0 |

Category sample:

| Category URL | Detail URLs |
|---|---:|
| `https://nhathuoclongchau.com.vn/thuoc/thuoc-da-lieu` | 12 |
| `https://nhathuoclongchau.com.vn/thuoc/thuoc-bo-and-vitamin` | 12 |
| `https://nhathuoclongchau.com.vn/thuoc/thuoc-khang-sinh-khang-nam` | 12 |
| `https://nhathuoclongchau.com.vn/thuoc/thuoc-tim-mach-and-mau` | 12 |

Legacy V1 vs Fresh Crawled V2 field comparison:

| Field | Exact | Different | Missing one side |
|---|---:|---:|---:|
| `ten_thuoc` | 37 | 0 | 0 |
| `ham_luong` | 37 | 0 | 0 |
| `dang_thuoc` | 37 | 0 | 0 |
| `tong_so_luong` | 37 | 0 | 0 |
| `tac_dung` | 37 | 0 | 0 |
| `tac_dung_phu` | 37 | 0 | 0 |
| `huong_dan_su_dung` | 37 | 0 | 0 |
| `lieu_dung` | 37 | 0 | 0 |
| `duong_dung` | 35 | 0 | 2 |
| `huong_dan_bao_quan` | 37 | 0 | 0 |
| `luu_y_dac_biet` | 37 | 0 | 0 |

## 3. Vấn đề phát hiện

- Fresh drug_id `alzental-400mg-shinpoong-1x1-thuoc-tri-giun` not found in Legacy V1
- Fresh drug_id `alzental-400mg-shinpoong-1x1-thuoc-tri-giun` not found in migrated V2
- Fresh drug_id `azoltel-400mg-stella-1x1` not found in Legacy V1
- Fresh drug_id `azoltel-400mg-stella-1x1` not found in migrated V2
- Fresh drug_id `fubenzon-500mg-dhg-1x1` not found in Legacy V1
- Fresh drug_id `fubenzon-500mg-dhg-1x1` not found in migrated V2
- Fresh drug_id `fucagi-500mg-agimexpharm-1v` not found in Legacy V1
- Fresh drug_id `fucagi-500mg-agimexpharm-1v` not found in migrated V2
- Fresh drug_id `fugacar-500mg-lusomedicamenta-1v` not found in Legacy V1
- Fresh drug_id `fugacar-500mg-lusomedicamenta-1v` not found in migrated V2
- Fresh drug_id `fugacar-500mg-olic-1v` not found in Legacy V1
- Fresh drug_id `fugacar-500mg-olic-1v` not found in migrated V2
- Fresh drug_id `mebendazol-500mg-nam-ha-1v-giun-nui` not found in Legacy V1
- Fresh drug_id `mebendazol-500mg-nam-ha-1v-giun-nui` not found in migrated V2
- Fresh drug_id `mebendazole-500mg-mekophar-1v` not found in Legacy V1
- Fresh drug_id `mebendazole-500mg-mekophar-1v` not found in migrated V2
- Fresh drug_id `nyst-25000iu-opc-10-goi` not found in Legacy V1
- Fresh drug_id `nyst-25000iu-opc-10-goi` not found in migrated V2
- Fresh drug_id `shampoo-clobetasol-vcp-100ml` not found in Legacy V1
- Fresh drug_id `shampoo-clobetasol-vcp-100ml` not found in migrated V2
- Fresh drug_id `timbov-farmaprim-1x3` not found in Legacy V1
- Fresh drug_id `timbov-farmaprim-1x3` not found in migrated V2

## 4. Quyết định còn mở

- Chốt raw snapshot retention convention: giữ trong repo demo hay chuyển sang ignored artifact khi raw tăng lớn.
- Chốt target Phase 4 shadow comparison: field exact match có cần đạt ngưỡng nào hay chỉ dùng để phát hiện drift.
- Chốt có cho phép Crawler V2 dùng category SSR để discover pilot URL hay Phase 3 production chỉ nhận explicit product URL.

## 5. Trạng thái

**PASS WITH ISSUES**

Phase 3 chứng minh được pipeline mới: fetch URL → ghi raw snapshot có timestamp/hash/parser version → parse → sinh Canonical V2 → validation → so sánh với V1/V2 migrated, không crawl toàn bộ corpus.
