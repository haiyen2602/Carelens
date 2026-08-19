# Phase 7 Report --- Agent Integration V2

**Ngày:** 2026-08-16T09:57:34.264604+00:00  
**Scope:** Agent-facing Data/Search/RAG V2 integration behind `DRUG_KNOWLEDGE_BACKEND=v1|v2|shadow`. No V1 deprecation/cutover.

## 1. Output đã tạo

- `backend/services/drug_knowledge/v2_agent.py`
- `backend/config.py` (`drug_knowledge_backend`)
- `backend/agents/nodes/drug_confirmation_nodes.py` integration after confirmed drug identity
- `scripts/data_v2/agent_v2_evaluation.py`
- `data pharmacy/v2/agent_eval/eval_results.json`
- `data pharmacy/reports/phase7-agent-integration-report.md`

## 2. E2E Eval

| Metric | Value |
|---|---:|
| Cases | 13 |
| Resolved drug cases | 10 |
| Ambiguous/nonexistent/multi-drug fail-closed cases | 3 |
| Wrong-drug rate | 0.00% |
| Wrong-type rate | 0.00% |
| Structured without RAG rate | 100.00% |
| Open-query RAG V2 rate | 100.00% |
| Fail-closed safety rate | 100.00% |
| Latency p50 ms | 0.0194 |
| Latency p95 ms | 0.0841 |

| Case | Route | Results | Wrong Drug | Wrong Type |
|---|---|---:|---:|---:|
| known_indication | structured_lookup | 1 | False | False |
| known_adr | structured_lookup | 1 | False | False |
| known_contraindication | structured_lookup | 1 | False | False |
| known_interaction | structured_lookup | 1 | False | False |
| known_dosage_typo_no_diacritic | structured_lookup | 1 | False | False |
| known_storage | structured_lookup | 1 | False | False |
| safety_pregnancy | structured_lookup | 2 | False | False |
| safety_driving | structured_lookup | 1 | False | False |
| semantic_open | rag_v2 | 5 | False | False |
| semantic_open_no_diacritic | rag_v2 | 5 | False | False |
| ambiguous_alias | fail_closed_before_knowledge | 0 | False | False |
| multiple_drugs | fail_closed_before_knowledge | 0 | False | False |
| nonexistent | fail_closed_before_knowledge | 0 | False | False |

## 3. Routing

- Known drug + known topic: `structured_lookup`.
- Semantic/open query: `rag_v2` after confirmed `legacy_drug_id -> drug_product_id`.
- Ambiguous/nonexistent/multiple-drug: fail closed before knowledge lookup in this eval.
- `SHADOW`: returns V1 results while logging V2 count/path/type comparison.

## 4. Wrong Drug

-

## 5. Open Issues

- Run SHADOW/live HTTP route in staging before cutover; Phase 7 keeps V1 as default rollback path

## PHASE 7 RESULT

```text
STATUS:
PASS WITH ISSUES

E2E EVAL:
Cases: 13
Resolved: 10
Fail-closed safety: 100.00%

WRONG DRUG:
0.00%

STRUCTURED VS RAG ROUTING:
Structured without RAG: 100.00%
Open-query RAG V2: 100.00%

LATENCY:
p50=0.0194ms, p95=0.0841ms

V1 ROLLBACK:
PASS

BREAKING CHANGE:
NO

OPEN ISSUES:
- Run SHADOW/live HTTP route in staging before cutover; Phase 7 keeps V1 as default rollback path

READY FOR CUTOVER:
NO
```
