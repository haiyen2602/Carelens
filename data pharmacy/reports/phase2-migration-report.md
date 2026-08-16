# Phase 2 Report --- Canonical V2 + Legacy Importer

**Ngày:** 2026-08-16T09:04:43.854514+00:00  
**Runtime production:** không thay đổi.  
**Crawler/RAG/Agent:** không chạy, không sửa.

## 1. Output đã tạo

- `scripts/data_v2/legacy_importer.py`
- `data pharmacy/v2/drug_product.jsonl`
- `data pharmacy/v2/drug_id_map.jsonl`
- `data pharmacy/v2/ingredient.jsonl`
- `data pharmacy/v2/drug_product_ingredient.jsonl`
- `data pharmacy/v2/drug_knowledge.jsonl`
- `data pharmacy/v2/import_summary.json`
- `reports/data-v2/phase2-migration-report.md`
- `docs/data/adr-data-v2-identity-compatibility.md`

## 2. Số liệu chính

| Metric | Value |
|---|---:|
| Legacy drugs | 3562 |
| V2 drug products | 3562 |
| ID mappings | 3562 |
| Unmapped legacy drug_id | 0 |
| Duplicate mapping | 0 |
| Knowledge items | 42654 |
| Ingredient relationship rows | 5793 |
| Structured ingredients | 1408 |
| Ingredient parse successes | 5299 |
| Ingredient warnings | 494 |
| Unmapped/unknown headings | 21 |
| Source fields with unintended loss | 0 |

Knowledge by type:

| Type | Count |
|---|---:|
| `ADMINISTRATION` | 3562 |
| `ADVERSE_EFFECT` | 3562 |
| `CONTRAINDICATION` | 3550 |
| `DRIVING_WARNING` | 3410 |
| `GENERAL_DOSAGE` | 3562 |
| `INDICATION` | 3562 |
| `INTERACTION` | 3555 |
| `PRECAUTION` | 8860 |
| `PREGNANCY_LACTATION` | 5496 |
| `REVIEW_REQUIRED` | 21 |
| `STORAGE` | 3514 |

Unmapped headings:

| Heading | Count |
|---|---:|
| `các đối tượng đặc biệt khác` | 14 |
| `các đối tượng đặc biệt` | 4 |
| `các nhóm bệnh nhân đặc biệt` | 1 |
| `trẻ sơ sinh và trẻ nhỏ` | 1 |
| `chỉ định` | 1 |

## 3. Vấn đề phát hiện

- Ingredient parser conservative nên structured coverage chưa đầy đủ; mọi case không chắc được giữ raw + warning.
- Legacy records không có raw provenance, nên toàn bộ migrated knowledge mang `LEGACY_NO_RAW_SOURCE`.
- 48 legacy records không có `huong_dan_bao_quan`, nên không sinh `STORAGE` cho các thuốc đó.
- Một số `luu_y_dac_biet` không match taxonomy an toàn, được giữ với `knowledge_type = REVIEW_REQUIRED`.
- `muc_nghiem_trong` chỉ được giữ trong `legacy_metadata`, không đưa vào `drug_knowledge`.

## 4. Quyết định còn mở

- Target định lượng cho Phase 4-6: drug resolution match, knowledge coverage, cross-drug regression, latency.
- Schema chi tiết cho `source_snapshot` và validation result khi sang Phase 3.
- Có chấp nhận `REVIEW_REQUIRED` như một `knowledge_type` tạm trong V2 JSONL hay muốn tách thành review queue riêng ở Phase 5.

## 5. Random review sample

Deterministic sample 30 thuốc, seed `67`:

- `trixlazi-davi-3x10` — Trixlazi DAVI 3x10 (Thuốc bổ và vitamin, Uống)
- `mekoderm-neomycin-mekophar-10g` — Mekoderm-neomycin Mekophar 10g (Thuốc da liễu, Bôi ngoài da)
- `savi-pantoprazole-40mg-2x10` — SAVI Pantoprazole 40mg 2x10 (Thuốc tiêu hoá và gan mật, Uống)
- `actelsar-40mg-actavis-2x14` — Actelsar 40mg Actavis 2x14 (Thuốc tim mạch và máu, Uống)
- `dorotril-h-domesco-2x14` — Dorotril-h Domesco 2x14 (Thuốc tim mạch và máu, Uống)
- `amlor-5mg-viatris-3x10-tablets` — Amlor 5mg Viatris 3x10 Tablets (Thuốc tim mạch và máu, Uống)
- `medskin-clovir-800mg-dhg-3x10` — Medskin Clovir 800mg DHG 3x10 (Thuốc kháng virus, Uống)
- `vasulax-10mg-micro-3x10` — Vasulax 10mg Micro 3x10 (Thuốc tim mạch và máu, Uống)
- `bihasal-2-5mg-hasan-5x10` — Bihasal 2.5mg Hasan 5x10 (Thuốc tim mạch và máu, Uống)
- `hasitec-10mg-hasan-3x10` — Hasitec 10mg Hasan 3x10 (Thuốc tim mạch và máu, Uống)
- `lovenox-4000-sanofi-2-ong` — Lovenox 4000 Sanofi 2 ỐNG (Thuốc tiêm chích và dịch truyền, Tiêm)
- `biracin-e-bidiphar-5ml` — Biracin-e Bidiphar 5ml (Thuốc mắt, tai, mũi, họng, Nhỏ mắt)
- `franmoxy-500mg-eloge-10x10` — Franmoxy 500mg Eloge 10x10 (Thuốc kháng sinh, Uống)
- `nephrosteril-250ml` — Nephrosteril 250ml (Thuốc tiêm chích và dịch truyền, Tiêm truyền)
- `regatonic-phil-6x10` — Regatonic PHIL 6x10 (Thuốc bổ và vitamin, Uống)
- `bioflora-250mg-biocodex-2x5` — Bioflora 250mg Biocodex 2x5 (Thuốc tiêu hoá và gan mật, Uống)
- `cefixim-50mg-vidipha-10-goi` — Cefixim 50mg Vidipha 10 GÓI (Thuốc kháng sinh, Uống)
- `halixol-30mg-egis-2x10` — Halixol 30mg EGIS 2x10 (Thuốc mắt, tai, mũi, họng, Uống)
- `novobion-cpc1-2x15` — Novobion cpc1 2x15 (Thuốc bổ và vitamin, Uống)
- `auclanityl-250-31-25mg-tipharco-12-goi` — Auclanityl 250/31.25mg Tipharco 12 GÓI (Thuốc kháng sinh, Uống)
- `captopril-25mg-stella-10x10` — Captopril 25mg Stella 10x10 (Thuốc tim mạch và máu, Uống)
- `cefurobiotic-500mg-tenamyd-5x10` — Cefurobiotic 500mg Tenamyd 5x10 (Thuốc kháng sinh, Uống)
- `patylcrem-hasan-10g` — Patylcrem Hasan 10g (Thuốc da liễu, Bôi ngoài da)
- `dromasm-fort-80mg-hataphar-10x10` — Dromasm FORT 80mg Hataphar 10x10 (Thuốc tiêu hoá và gan mật, Uống)
- `dibetalic-traphaco-15g` — Dibetalic Traphaco 15g (Thuốc da liễu, Bôi ngoài da)
- `histudon-200mg-1ml-ha-tay-60ml` — Histudon 200mg/1ml HÀ TÂY 60ml (Thuốc tim mạch và máu, Uống)
- `sanlein-mini-0-1-santen-30-ong-x-0-4ml` — Sanlein MINI 0.1% Santen 30 ỐNG X 0.4ml (Thuốc mắt, tai, mũi, họng, Nhỏ mắt)
- `cefixim-200mg-cuu-long-2x10` — Cefixim 200mg CỬU LONG 2x10 (Thuốc kháng sinh, Uống)
- `eslo-10-hetero-3x10` — ESLO 10 Hetero 3x10 (Thuốc thần kinh, Uống)
- `pantoloc-20-takeda-1x14` — Pantoloc 20 Takeda 1x14 (Thuốc tiêu hoá và gan mật, Uống)

## 6. Trạng thái

**PASS WITH ISSUES**

Phase 2 migration reproducible và không đụng legacy/runtime. Kết quả đủ điều kiện đi tiếp nếu reviewer chấp nhận các parsing warning được báo cáo thay vì tự đoán.

## PHASE 2 RESULT

```text
STATUS:
PASS WITH ISSUES

MIGRATION:
Legacy drugs: 3562
V2 drugs: 3562
ID mappings: 3562
Unmapped: 0
Knowledge items: 42654
Ingredients parsed: 5299
Ingredient warnings: 494

DATA LOSS:
-

LEGACY MODIFIED:
NO

PRODUCTION MODIFIED:
NO

OPEN ISSUES:
- 494 ingredient segments preserved raw with warning
- 21 luu_y_dac_biet headings require review

READY FOR PHASE 3:
YES
```
