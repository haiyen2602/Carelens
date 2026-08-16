# V2 Default Rollout Report

**Ngày:** 2026-08-16T10:08:30.268725+00:00  
**Scope:** Controlled V2 default with V1/SHADOW rollback retained. No V1 deprecation.

## HTTP Results

| Label | Case | HTTP | Sources | Backend | Route | Wrong Drug | Wrong Type | Latency ms |
|---|---|---:|---:|---|---|---:|---:|---:|
| default | known_indication | 200 | 1 | v2 | structured_lookup | False | False | 37.85 |
| default | typo_no_diacritic | 200 | 1 | v2 | structured_lookup | False | False | 17.19 |
| default | semantic_open | 200 | 5 | v2 | rag_v2 | False | False | 18.01 |
| default | contraindication | 200 | 1 | v2 | structured_lookup | False | False | 17.58 |
| default | interaction | 200 | 1 | v2 | structured_lookup | False | False | 17.16 |
| default | pregnancy | 200 | 2 | v2 | structured_lookup | False | False | 16.27 |
| default | ambiguous | 200 | 0 | - | - | False | False | 136.23 |
| default | nonexistent | 200 | 0 | - | - | False | False | 133.57 |
| default | multiple_drugs | 200 | 0 | - | - | False | False | 128.36 |
| v1_rollback | known_indication | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 21.22 |
| v1_rollback | typo_no_diacritic | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 16.98 |
| v1_rollback | semantic_open | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 16.74 |
| v1_rollback | contraindication | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 19.43 |
| v1_rollback | interaction | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 17.25 |
| v1_rollback | pregnancy | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 16.79 |
| v1_rollback | ambiguous | 200 | 0 | - | - | False | False | 123.86 |
| v1_rollback | nonexistent | 200 | 0 | - | - | False | False | 131.22 |
| v1_rollback | multiple_drugs | 200 | 0 | - | - | False | False | 131.17 |
| shadow_smoke | known_indication | 200 | 4 | shadow | structured_lookup | False | False | 22.22 |
| shadow_smoke | typo_no_diacritic | 200 | 4 | shadow | structured_lookup | False | False | 18.99 |

## V2 DEFAULT RESULT

```text
STATUS:
PASS

V2 DEFAULT:
YES

STARTUP WARMUP:
PASS (3562 products, 42654 chunks, 7859.00ms)

HTTP REGRESSION:
PASS

WRONG DRUG:
-

WRONG TYPE:
-

LATENCY:
p50=19.43ms, p95=133.57ms, max=136.23ms, default_max=136.23ms

V1 ROLLBACK:
PASS

BREAKING CHANGE:
NO

READY TO ENTER STABILIZATION:
YES

OPEN ISSUES:
-
```
