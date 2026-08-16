# Phase 4 Report --- V1/V2 Compatibility Layer

**Ngày:** 2026-08-16T09:27:22.568979+00:00  
**Scope:** standalone compatibility baseline, no public API/runtime changes.

## 1. Output đã tạo

- `scripts/data_v2/compatibility_layer.py`
- `data pharmacy/v2/compatibility/legacy_resolution_report.json`
- `data pharmacy/v2/compatibility/fresh_reconciliation.jsonl`
- `data pharmacy/v2/compatibility/shadow_comparison.json`
- `data pharmacy/reports/phase4-compatibility-report.md`

## 2. Số liệu chính

| Metric | Value |
|---|---:|
| Legacy IDs total | 3562 |
| Legacy IDs resolved | 3562 |
| Legacy IDs unresolved | 0 |
| Duplicate mappings | 0 |
| Shadow compared IDs | 3562 |
| Shadow identity mismatches | 0 |
| Shadow missing knowledge cases | 0 |
| Shadow name mismatches | 0 |
| V1 p95 latency ms | 0.0023 |
| V2 p95 latency ms | 0.0040 |

## 3. Fresh Product Reconciliation

| Class | Count |
|---|---:|
| EXACT_LEGACY_MATCH | 37 |
| CHANGED_SLUG_MATCH | 0 |
| NEW_PRODUCT | 11 |
| AMBIGUOUS | 0 |

Rows:

| Fresh ID | Class | Candidate legacy IDs |
|---|---|---|
| `ketoconazol-2-medipharco-10g` | EXACT_LEGACY_MATCH | ketoconazol-2-medipharco-10g |
| `promethazin-cream-2-medipharco-10g` | EXACT_LEGACY_MATCH | promethazin-cream-2-medipharco-10g |
| `lifedovate-cream-0-05-hadiphar-10g` | EXACT_LEGACY_MATCH | lifedovate-cream-0-05-hadiphar-10g |
| `pvp-iodine-10-danapha-1-chai-20ml` | EXACT_LEGACY_MATCH | pvp-iodine-10-danapha-1-chai-20ml |
| `biroxime-cream-1-y-med-20g` | EXACT_LEGACY_MATCH | biroxime-cream-1-y-med-20g |
| `leopovidone-10-leopard-15ml` | EXACT_LEGACY_MATCH | leopovidone-10-leopard-15ml |
| `povidon-iodin-10-s-pharm-20ml` | EXACT_LEGACY_MATCH | povidon-iodin-10-s-pharm-20ml |
| `xanh-methylen-1-hoa-duoc-17ml` | EXACT_LEGACY_MATCH | xanh-methylen-1-hoa-duoc-17ml |
| `ho-nuoc-hdpharma-20g` | EXACT_LEGACY_MATCH | ho-nuoc-hdpharma-20g |
| `nady-rosa-nadyphar-80g` | EXACT_LEGACY_MATCH | nady-rosa-nadyphar-80g |
| `betadine-sat-khuan-lon-125ml` | EXACT_LEGACY_MATCH | betadine-sat-khuan-lon-125ml |
| `tyrosur-engelhard-5g` | EXACT_LEGACY_MATCH | tyrosur-engelhard-5g |
| `ceelin-z-united-60ml` | EXACT_LEGACY_MATCH | ceelin-z-united-60ml |
| `pokemine-medisun-20x10ml` | EXACT_LEGACY_MATCH | pokemine-medisun-20x10ml |
| `enervon-c-united-10x10` | EXACT_LEGACY_MATCH | enervon-c-united-10x10 |
| `myhemo-reliv-3x10` | EXACT_LEGACY_MATCH | myhemo-reliv-3x10 |
| `tothema-2x10-ong-10ml` | EXACT_LEGACY_MATCH | tothema-2x10-ong-10ml |
| `cardioton-lipa-6x10` | EXACT_LEGACY_MATCH | cardioton-lipa-6x10 |
| `berocca-bayer-10v` | EXACT_LEGACY_MATCH | berocca-bayer-10v |
| `long-huyet-ph-2x12-tan-bam-tim-giam-phu-ne` | EXACT_LEGACY_MATCH | long-huyet-ph-2x12-tan-bam-tim-giam-phu-ne |
| `upsa-c-10v` | EXACT_LEGACY_MATCH | upsa-c-10v |
| `tardyferon-b9-3x10` | EXACT_LEGACY_MATCH | tardyferon-b9-3x10 |
| `procare-diamond-216mg-catalent-30v` | EXACT_LEGACY_MATCH | procare-diamond-216mg-catalent-30v |
| `magne-b6-corbiere-sanofi-5x10` | EXACT_LEGACY_MATCH | magne-b6-corbiere-sanofi-5x10 |
| `fucagi-500mg-agimexpharm-1v` | NEW_PRODUCT | - |
| `agiclovir-5-agimexpharm` | EXACT_LEGACY_MATCH | agiclovir-5-agimexpharm |
| `fugacar-500mg-lusomedicamenta-1v` | NEW_PRODUCT | - |
| `mebendazole-500mg-mekophar-1v` | NEW_PRODUCT | - |
| `nyst-25000iu-opc-10-goi` | NEW_PRODUCT | - |
| `fugacar-500mg-olic-1v` | NEW_PRODUCT | - |
| `alzental-400mg-shinpoong-1x1-thuoc-tri-giun` | NEW_PRODUCT | - |
| `fubenzon-500mg-dhg-1x1` | NEW_PRODUCT | - |
| `mebendazol-500mg-nam-ha-1v-giun-nui` | NEW_PRODUCT | - |
| `azoltel-400mg-stella-1x1` | NEW_PRODUCT | - |
| `timbov-farmaprim-1x3` | NEW_PRODUCT | - |
| `shampoo-clobetasol-vcp-100ml` | NEW_PRODUCT | - |
| `hoat-huyet-truong-phuc-3x10` | EXACT_LEGACY_MATCH | hoat-huyet-truong-phuc-3x10 |
| `tuan-hoan-nao-thai-duong-2x6` | EXACT_LEGACY_MATCH | tuan-hoan-nao-thai-duong-2x6 |
| `dacolfort-500mg-danapha-3x10` | EXACT_LEGACY_MATCH | dacolfort-500mg-danapha-3x10 |
| `gikanin-500mg-khapharco-10x10` | EXACT_LEGACY_MATCH | gikanin-500mg-khapharco-10x10 |
| `op-zen-160mg-opc-5x10` | EXACT_LEGACY_MATCH | op-zen-160mg-opc-5x10 |
| `cebraton-traphaco-5x10` | EXACT_LEGACY_MATCH | cebraton-traphaco-5x10 |
| `bilomag-6x10v` | EXACT_LEGACY_MATCH | bilomag-6x10v |
| `tebonin-120mg-dr-willmar-2x15` | EXACT_LEGACY_MATCH | tebonin-120mg-dr-willmar-2x15 |
| `tanganil-500mg-pierre-fabre-3x10` | EXACT_LEGACY_MATCH | tanganil-500mg-pierre-fabre-3x10 |
| `tanakan-40mg-ipsen-2x15` | EXACT_LEGACY_MATCH | tanakan-40mg-ipsen-2x15 |
| `rutin-vitamin-c-mekophar-10x10` | EXACT_LEGACY_MATCH | rutin-vitamin-c-mekophar-10x10 |
| `remem-120mg-4x15` | EXACT_LEGACY_MATCH | remem-120mg-4x15 |

## 4. Vấn đề phát hiện

- 11 fresh products are NEW_PRODUCT and must not be auto-merged

## 5. Quyết định còn mở

- Có tự động đưa `NEW_PRODUCT` vào corpus chính ở Phase 5 không, hay phải qua review queue.
- Có chấp nhận `CHANGED_SLUG_MATCH` bằng exact normalized name là đủ để auto-map không.
- Ngưỡng shadow production cuối cùng cho Phase 5/6 vẫn chưa chốt.

## 6. Trạng thái

**PASS WITH ISSUES**

Compatibility layer chứng minh được resolver legacy slug → UUID, V1/V2/SHADOW facade behavior, và baseline shadow comparison mà không đổi response production.

## PHASE 4 RESULT

```text
STATUS:
PASS WITH ISSUES

LEGACY IDS:
Total: 3562
Resolved: 3562
Unresolved: 0

FRESH RECONCILIATION:
Exact: 37
Changed slug: 0
New product: 11
Ambiguous: 0

SHADOW MODE:
PASS

BREAKING API CHANGE:
NO

OPEN ISSUES:
- 11 fresh products are NEW_PRODUCT and must not be auto-merged

READY FOR PHASE 5:
YES
```
