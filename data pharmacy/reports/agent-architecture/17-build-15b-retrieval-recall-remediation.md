# BUILD-15B — Retrieval Recall Remediation

Date: 2026-08-18  
Scope: deterministic retrieval recall remediation and, only after its gate passed, one offline GPT-4o Judge round. `AGENT_RUNTIME_ENABLED=false` remains unchanged. No corpus artifact, embedding, vector, RRF configuration, Safety logic, or runtime flag was changed.

## Root-cause analysis

The canonical corpus contains four public chunks for `agiclovir-5-agimexpharm`, including one `tac_dung_phu` chunk. Corpus evidence was therefore present for both failures.

The production lexical threshold remains `0.55`. The original lexical name signal used `similarity(ten_thuoc, complete_query)`, which penalizes a valid product name when a user adds an intent phrase or inserts spaces:

| Golden case | Original relevant lexical score | Why it was rejected |
| --- | ---: | --- |
| `agiclovir-side-effect` | 0.5250 | The complete Vietnamese question is longer than the product name. |
| `difficult-misspelling` | 0.4722 | The spaced `Agi clo vir` form and `phan tram` wording lower whole-string similarity. |

`word_similarity(ten_thuoc, query)` scores the product-name span at 1.0000 and 0.5714 respectively, both above the unchanged production threshold. This is generic pg_trgm matching, not a drug/query-specific exception and not a lowered fuzzy threshold.

## Remediation

- Kept the existing indexed lexical name/content query and its threshold unchanged.
- When that high-threshold branch returns no evidence, added a bounded `word_similarity(product name, query)` fallback using the same `pg_trgm.word_similarity_threshold`.
- The fallback is separately queried because combining it with the indexed predicates in one SQL `OR` caused PostgreSQL to select a sequential scan. It is only reached after the normal branch has no candidates.
- The lexical candidate branch remains a source in the existing production lexical + vector + RRF flow. This evaluation intentionally measures that lexical source only; it does not claim a fresh vector/RRF benchmark or make an embedding request.
- Added PostgreSQL regressions for the two failures and a no-result guard. No golden expected result was changed.

## Deterministic validation

`pytest -q tests/test_retrieval.py tests/test_retrieval_sql.py tests/test_agent_v2_retrieval.py tests/test_agent_v2_rag_evaluation.py`: **26 passed**.

Broader Agent V2 + legacy retrieval regression: **127 passed, 2 skipped**. The two skips remain explicit disposable-PostgreSQL concurrency tests that require `BUILD12_TEST_DATABASE_URL` or `BUILD10_TEST_DATABASE_URL`; they are not suppressed failures.

After one warm-up, three complete `golden-rag-v1` runs returned the expected product at rank 1 for both remediated cases. Every existing relevant case still passed and the unknown-drug case remained empty.

| Metric | BUILD-14/14C | BUILD-15B candidate |
| --- | ---: | ---: |
| Hit@10 | 0.666667 | 1.000000 |
| MRR@10 | 0.666667 | 1.000000 |
| NDCG@10 | 0.666667 | 1.000000 |
| MAP@10 | 0.666667 | 1.000000 |
| Precision@5 | 0.133333 | 0.200000 |
| Exact Match / ROUGE-L / BLEU-4 | 0.714286 / 0.802198 / 0.784132 | 1.000000 / 1.000000 / 1.000000 |
| No-result contract | 0.714286 | 1.000000 |

Candidate P95 latency across the three warmed runs was 5656.419 ms, 5596.759 ms and 5634.739 ms. The additional fallback only runs for an empty lexical candidate set. These measurements are retained as a new retrieval-version baseline input; they were not used to overwrite BUILD-14C's historical baseline or to conceal a quality result.

Corpus identity is unchanged and remains fail-closed: `legacy-drug-chunks-openai-v1`, manifest `E57B24693AE64F7B1514D820911C5804DCD71CB3AAF4CF45B17A2D87603E0C04`, `text-embedding-3-small` at 1536 dimensions, and `pgvector-hnsw-cosine-v1`.

## One-round DeepEval rerun

The deterministic gate passed before this rerun. Exactly one GPT-4o Judge round was started, using public golden queries and public drug-corpus context only. The durable artifact is [golden-rag-v1-deepeval-15b-run.json](../../v2/rag_openai/evaluation/golden-rag-v1-deepeval-15b-run.json).

The runner completed with two explicit `FAILED_OSERROR` metric calls for `difficult-misspelling` (Faithfulness and Answer Relevancy). The failure is preserved; no score was inferred and no retry was made because BUILD-15B allows at most one round.

| Measure | Result |
| --- | ---: |
| Contextual Relevancy | 0.529861 (6 scored cases) |
| Faithfulness | 1.000000 (5 scored cases; 1 failed metric call) |
| Answer Relevancy | 0.400000 (5 scored cases; 1 failed metric call) |
| Judge variance | Not applicable: one permitted round |
| Actual Judge tokens | 25,422 input / 5,715 output |
| Actual Judge cost | US$0.120705 |

The score/cost uses the configured GPT-4o price basis (US$2.50/M input, US$10.00/M output), consistent with the [official OpenAI GPT-4o documentation](https://developers.openai.com/api/docs/models/gpt-4o). Judge output has no runtime or Safety authority.

## Result

BUILD-15B: FAIL

AGICLOVIR RECALL: PASS

MISSPELLING RECALL: PASS

HIT@10: 1.000000

MRR@10: 1.000000

NDCG@10: 1.000000

MAP@10: 1.000000

CORPUS IDENTITY: PASS

DETERMINISTIC GATE: PASS

DEEPEVAL RERUN: FAIL (`FAILED_OSERROR`; no retry under one-round limit)

CONTEXTUAL RELEVANCY: 0.529861 (partial)

FAITHFULNESS: 1.000000 (partial)

ANSWER RELEVANCY: 0.400000 (partial)

NEW JUDGE COST: US$0.120705

BUILD-15 FINAL: FAIL

READY FOR BUILD-16: NO
