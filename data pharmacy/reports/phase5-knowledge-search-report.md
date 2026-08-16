# Phase 5 Report --- Knowledge/Search V2

**Ngày:** 2026-08-16T09:33:42.708245+00:00  
**Scope:** standalone Knowledge/Search V2 over Canonical V2 JSONL. No API/RAG/Agent changes.

## 1. Output đã tạo

- `scripts/data_v2/knowledge_search_v2.py`
- `data pharmacy/v2/knowledge_search/eval_results.json`
- `data pharmacy/v2/knowledge_search/new_product_review_queue.jsonl`
- `data pharmacy/reports/phase5-knowledge-search-report.md`

## 2. Drug Resolution

- Exact legacy/public ID: supported.
- Exact normalized name: supported.
- Conservative alias: supported only when unique.
- Fuzzy typo: supported only when one candidate is clearly best.
- Ambiguous/nonexistent: fail closed, no knowledge returned.

## 3. Structured Lookup

- `get_knowledge(drug_product_id, knowledge_type)` implemented for all Phase 5 knowledge types.
- Known drug + known topic uses structured path, no vector/semantic search.
- Structured lookup coverage on eval: 66.67%

## 4. Semantic Search

- Implemented as local lexical semantic fallback over `drug_knowledge.content_raw`.
- Used only when topic is not confidently detected or structured path has no rows.
- Semantic fallback rate on eval: 8.33%

## 5. Eval

| Metric | Value |
|---|---:|
| Eval cases | 12 |
| Drug resolution accuracy | 100.00% |
| Knowledge-type accuracy | 100.00% |
| Structured lookup coverage | 66.67% |
| Semantic fallback rate | 8.33% |
| Wrong-drug rate | 0.00% |
| No-result rate | 25.00% |
| Latency p50 ms | 0.2519 |
| Latency p95 ms | 45.7040 |

Rows:

| Case | Path | Resolution | Drug | Type | Results |
|---|---|---|---|---|---:|
| known_topic_contraindication | structured | RESOLVED | agiclovir-5-agimexpharm | CONTRAINDICATION | 1 |
| known_topic_side_effect | structured | RESOLVED | ketoconazol-2-medipharco-10g | ADVERSE_EFFECT | 1 |
| diacriticless_topic | structured | RESOLVED | berocca-bayer-10v | INDICATION | 1 |
| typo_name | structured | RESOLVED | magne-b6-corbiere-sanofi-5x10 | GENERAL_DOSAGE | 1 |
| similar_name_exact | structured | RESOLVED | cefixim-200mg-cuu-long-2x10 | GENERAL_DOSAGE | 1 |
| ambiguous_alias | fail_closed | AMBIGUOUS | - | GENERAL_DOSAGE | 0 |
| nonexistent_drug | fail_closed | NOT_FOUND | - | ADVERSE_EFFECT | 0 |
| multiple_drugs | fail_closed | AMBIGUOUS | - | INDICATION | 0 |
| semantic_open_ended | semantic_fallback | RESOLVED | ketoconazol-2-medipharco-10g | - | 5 |
| storage_structured | structured | RESOLVED | tothema-2x10-ong-10ml | STORAGE | 1 |
| pregnancy_structured | structured | RESOLVED | tardyferon-b9-3x10 | PREGNANCY_LACTATION | 2 |
| interaction_structured | structured | RESOLVED | procare-diamond-216mg-catalent-30v | INTERACTION | 1 |

## 6. NEW_PRODUCT Review Queue

- `fucagi-500mg-agimexpharm-1v` — Fucagi 500mg Agimexpharm 1v
- `fugacar-500mg-lusomedicamenta-1v` — Fugacar 500mg Lusomedicamenta 1v
- `mebendazole-500mg-mekophar-1v` — Mebendazole 500mg Mekophar 1v
- `nyst-25000iu-opc-10-goi` — NYST 25000iu OPC 10 GÓI
- `fugacar-500mg-olic-1v` — Fugacar 500mg OLIC 1v
- `alzental-400mg-shinpoong-1x1-thuoc-tri-giun` — Alzental 400mg Shinpoong 1x1 - Thuốc TRỊ GIUN
- `fubenzon-500mg-dhg-1x1` — Fubenzon 500mg DHG 1x1
- `mebendazol-500mg-nam-ha-1v-giun-nui` — Mebendazol 500mg NAM Hà 1v - GIUN NÚI
- `azoltel-400mg-stella-1x1` — Azoltel 400mg Stella 1x1
- `timbov-farmaprim-1x3` — Timbov Farmaprim 1x3
- `shampoo-clobetasol-vcp-100ml` — Shampoo Clobetasol VCP 100ml

## 7. Wrong Drug Cases

-

## 8. Vấn đề phát hiện / Open Issues

- 11 NEW_PRODUCT rows remain in review queue; not auto-added to production corpus

## 9. Trạng thái

**PASS WITH ISSUES**

Structured path works independently from V1 RAG/Agent. Semantic search remains a fallback baseline and is not production embedding migration.

## PHASE 5 RESULT

```text
STATUS:
PASS WITH ISSUES

DRUG RESOLUTION:
Accuracy: 100.00%
Ambiguous/nonexistent: fail closed

STRUCTURED LOOKUP:
Coverage: 66.67%
Known drug + known topic avoids semantic/vector path

SEMANTIC SEARCH:
Fallback rate: 8.33%
Production embeddings not regenerated

EVAL:
Cases: 12
Knowledge-type accuracy: 100.00%
No-result rate: 25.00%
Latency p95 ms: 45.7040

WRONG DRUG CASES:
-

OPEN ISSUES:
- 11 NEW_PRODUCT rows remain in review queue; not auto-added to production corpus

READY FOR PHASE 6:
YES
```
