# Phase 6 Report --- RAG V2 Migration & Evaluation

**Ngày:** 2026-08-16T09:50:52.874330+00:00  
**Scope:** standalone offline RAG V2 over `drug_knowledge`; no Agent/API/prescription changes.

## 1. Output đã tạo

- `scripts/data_v2/rag_v2_evaluation.py`
- `data pharmacy/v2/rag_eval/v2_chunks.jsonl`
- `data pharmacy/v2/rag_eval/v2_embedding_index.jsonl`
- `data pharmacy/v2/rag_eval/eval_results.json`
- `data pharmacy/reports/phase6-rag-evaluation-report.md`

## 2. Chunk/Index V2

- V2 chunks: 42654
- V1 chunks compared: 14200
- Rule: one `drug_knowledge` row = one chunk; no cross-knowledge-type merge.
- Each V2 chunk keeps `drug_product_id`, `legacy_drug_id`, `knowledge_type`, and provenance metadata.
- Embedding/index mode: local reproducible TF-IDF hash vectors (`local-tfidf-hash-v1`) stored outside production.

## 3. Metrics

| Metric | V1 | V2 |
|---|---:|---:|
| Eval cases | 18 | 18 |
| Hit@5 | 100.00% | 100.00% |
| Recall@5 | 100.00% | 100.00% |
| Wrong-drug rate | 22.22% | 0.00% |
| Safety wrong-drug rate | 100.00% | 0.00% |
| Wrong-knowledge-type rate | 41.67% | 0.00% |
| Type Hit@5 | 58.33% | 100.00% |
| No-result rate | 0.00% | 22.22% |
| Latency p50 ms | 23.4127 | 1.7332 |
| Latency p95 ms | 42.5557 | 260.5097 |

## 4. V2 Eval Rows

| Case | Resolution | Hit@5 | Type Hit@5 | Wrong Drug | No Result |
|---|---|---:|---:|---:|---:|
| indication_known | RESOLVED | True | True | False | False |
| adr_known | RESOLVED | True | True | False | False |
| contraindication_known | RESOLVED | True | True | False | False |
| interaction_known | RESOLVED | True | True | False | False |
| dosage_typo | RESOLVED | True | True | False | False |
| storage_known | RESOLVED | True | True | False | False |
| pregnancy_known | RESOLVED | True | True | False | False |
| administration_known | RESOLVED | True | True | False | False |
| driving_warning | RESOLVED | True | True | False | False |
| precaution | RESOLVED | True | True | False | False |
| similar_name_exact | RESOLVED | True | True | False | False |
| diacriticless | RESOLVED | True | True | False | False |
| semantic_open | RESOLVED | True | True | False | False |
| semantic_open_2 | RESOLVED | True | True | False | False |
| ambiguous_alias | AMBIGUOUS | False | True | False | True |
| multiple_drugs | AMBIGUOUS | False | True | False | True |
| nonexistent | NOT_FOUND | False | True | False | True |
| near_name_fail_closed | NOT_FOUND | False | True | False | True |

## 5. Regression

-

## 6. Open Issues

- V2 no-result rate is materially higher than V1 because ambiguous/nonexistent cases fail closed
- V2 p95 latency is higher in offline eval due resolver scan; index resolver before runtime use

## 7. Trạng thái

**PASS WITH ISSUES**

V2 demonstrates the intended safety shape: resolve drug first, filter by `drug_product_id`, filter by `knowledge_type` when detected, then vector search. V1 remains untouched for rollback.

## PHASE 6 RESULT

```text
STATUS:
PASS WITH ISSUES

EVAL CASES:
18

V1:
Hit@K: 100.00%
Wrong drug: 22.22%
Wrong type: 41.67%
Latency: p50=23.4127ms, p95=42.5557ms

V2:
Hit@K: 100.00%
Wrong drug: 0.00%
Wrong type: 0.00%
Latency: p50=1.7332ms, p95=260.5097ms

REGRESSION:
-

OPEN ISSUES:
- V2 no-result rate is materially higher than V1 because ambiguous/nonexistent cases fail closed
- V2 p95 latency is higher in offline eval due resolver scan; index resolver before runtime use

READY FOR PHASE 7:
YES
```
