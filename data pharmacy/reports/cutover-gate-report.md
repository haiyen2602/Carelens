# Cutover Gate Report --- V2 Staging & Shadow Validation

**Ngày:** 2026-08-16T10:05:18.345871+00:00  
**Scope:** FastAPI HTTP route validation for `DRUG_KNOWLEDGE_BACKEND=shadow|v2|v1`. No V1 deprecation/cutover.

## HTTP Results

| Mode | Case | HTTP | Sources | Backend Trace | Route | Wrong Drug | Wrong Type | Latency ms |
|---|---|---:|---:|---|---|---:|---:|---:|
| shadow | known_indication | 200 | 4 | shadow | structured_lookup | False | False | 8010.05 |
| shadow | typo_no_diacritic | 200 | 4 | shadow | structured_lookup | False | False | 21.36 |
| shadow | semantic_open | 200 | 4 | shadow | rag_v2 | False | False | 18.89 |
| shadow | pregnancy_safety | 200 | 4 | shadow | structured_lookup | False | False | 17.87 |
| shadow | contraindication_safety | 200 | 4 | shadow | structured_lookup | False | False | 17.70 |
| shadow | interaction_safety | 200 | 4 | shadow | structured_lookup | False | False | 18.06 |
| shadow | ambiguous_drug | 200 | 0 | - | - | False | False | 124.18 |
| shadow | nonexistent_drug | 200 | 0 | - | - | False | False | 132.64 |
| shadow | multiple_drugs | 200 | 0 | - | - | False | False | 134.39 |
| v2 | known_indication | 200 | 1 | v2 | structured_lookup | False | False | 20.61 |
| v2 | typo_no_diacritic | 200 | 1 | v2 | structured_lookup | False | False | 17.96 |
| v2 | semantic_open | 200 | 5 | v2 | rag_v2 | False | False | 17.69 |
| v2 | pregnancy_safety | 200 | 2 | v2 | structured_lookup | False | False | 17.56 |
| v2 | contraindication_safety | 200 | 1 | v2 | structured_lookup | False | False | 17.87 |
| v2 | interaction_safety | 200 | 1 | v2 | structured_lookup | False | False | 17.37 |
| v2 | ambiguous_drug | 200 | 0 | - | - | False | False | 117.88 |
| v2 | nonexistent_drug | 200 | 0 | - | - | False | False | 126.69 |
| v2 | multiple_drugs | 200 | 0 | - | - | False | False | 133.26 |
| v1 | known_indication | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 20.65 |
| v1 | typo_no_diacritic | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 16.92 |
| v1 | semantic_open | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 17.24 |
| v1 | pregnancy_safety | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 17.31 |
| v1 | contraindication_safety | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 17.36 |
| v1 | interaction_safety | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 17.53 |
| v1 | ambiguous_drug | 200 | 0 | - | - | False | False | 117.13 |
| v1 | nonexistent_drug | 200 | 0 | - | - | False | False | 127.71 |
| v1 | multiple_drugs | 200 | 0 | - | - | False | False | 132.28 |

## CUTOVER GATE RESULT

```text
STATUS:
PASS WITH ISSUES

HTTP/SHADOW:
Shadow cases: 9
HTTP route exercised: YES

V1 VS V2:
V1 cases: 9
V2 cases: 9
Structured extra RAG: 0
Errors: 0

WRONG DRUG:
0

WRONG TYPE:
0

LATENCY:
p50=18.89ms, p95=134.39ms, max=8010.05ms

V1 ROLLBACK:
PASS

BREAKING CHANGE:
NO

READY FOR V2 DEFAULT:
YES

OPEN ISSUES:
- First V2/SHADOW request has cold-start index load latency; warm cache before cutover
```
