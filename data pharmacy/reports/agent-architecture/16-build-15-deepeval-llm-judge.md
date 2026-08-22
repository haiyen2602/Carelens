# BUILD-15 — DeepEval + LLM-as-a-Judge

Date: 2026-08-18  
Scope: offline/pre-release RAG evaluation only. `AGENT_RUNTIME_ENABLED=false` remains unchanged. No Agent runtime, Safety decision, corpus, retrieval setting, or public API was modified.

## Implementation

- Added `deepeval>=2,<3` and an offline-only `TrackingGPT4oJudge` adapter. It uses the backend Judge credential (`OPENAI_JUDGE_API_KEY`, with the existing backend-only fallback), `RAG_JUDGE_MODEL=gpt-4o`, temperature `0`, timeout and SDK retries disabled.
- The adapter is a native DeepEval `GPTModel` subclass, so DeepEval receives structured outputs and its cost contract correctly. It records aggregate input/output tokens and estimated cost, but never persists API keys, Judge prompts, Judge reason text, or hidden reasoning.
- `scripts/agent_v2/run_deepeval_rag_judge.py` uses the versioned `golden-rag-v1` dataset and live public `drug_chunks` retrieval. It persists only public query, answer, context provenance references (`chunk_id`, `drug_id`, `field_group`), canonical metric score/status, model/evaluation version and usage/cost in `golden-rag-v1-deepeval-run.json`.
- The PII/PHI guard rejects email, telephone-like values and operational/patient identifier markers before any Judge call. The runner's scope is versioned public drug corpus text only; no patient, conversation, actor or operational context is passed to GPT-4o.
- DeepEval is confined to this offline script. It cannot influence runtime answer composition, Tool Gateway, Safety Domain, or release a Safety decision.

## Evaluation configuration and reproducibility

| Item | Value |
| --- | --- |
| Dataset | `golden-rag-v1` |
| Corpus / manifest | `legacy-drug-chunks-openai-v1` / `E57B…0C04` |
| Retrieval | unchanged `lexical-pg-trgm-v1` |
| Judge | `gpt-4o`, temperature 0 |
| DeepEval | 2.9.7 |
| Evaluation version | `deepeval-rag-judge-v1` |
| Rounds | 2 independent rounds |
| Context sent to Judge | top 2 public chunks, max 1,500 characters/chunk |
| GPT-4o price basis | US$2.50/M input, US$10.00/M output, as documented for GPT-4o by [OpenAI](https://developers.openai.com/api/docs/models/gpt-4o) |

The deterministic BUILD-14 result is embedded with the Judge artifact for comparison: Hit@10/MRR@10/NDCG@10/MAP@10 = 0.666667; Exact Match = 0.714286; ROUGE-L F1 = 0.802198; BLEU-4 = 0.784132. These metrics measure a different property and are not replaced by Judge scores.

## Measured Judge scores

Only cases with retrieved public context are included in the score average. The known no-evidence case is explicitly `NOT_APPLICABLE_NO_EVIDENCE`; it is not silently converted to a scored PASS.

| Metric | Baseline (round 1) | Mean (2 rounds) | Variance |
| --- | ---: | ---: | ---: |
| Contextual Relevancy | 0.456845 | 0.456845 | 0.000000 |
| Faithfulness | 1.000000 | 1.000000 | 0.000000 |
| Answer Relevancy | 0.500000 | 0.500000 | 0.000000 |

Judge variance is zero across the two measured rounds under the same model/version, prompt templates and temperature. This is an observation, not a general guarantee that GPT-4o will be deterministic across all future runs.

## Fail-closed result and cost reconciliation

The two retained P1 retrieval misses—`agiclovir-side-effect` and `difficult-misspelling`—have no context although their golden cases expect evidence. Across two rounds this creates 12 `FAILED_MISSING_CONTEXT` metric records (2 cases × 3 metrics × 2 rounds). Per the BUILD-15 rule, missing score is not PASS; the Judge release gate therefore fails.

| Judge execution | Input tokens | Output tokens | Cost |
| --- | ---: | ---: | ---: |
| Initial adapter attempt — failed after provider response (`AttributeError`), retained honestly | 26,961 | 11,200 | US$0.1794025 |
| Corrected two-round DeepEval evaluation | 33,493 | 8,532 | US$0.1690525 |
| Total BUILD-15 Judge cost | 60,454 | 19,732 | **US$0.3484550** |

The first spend is retained rather than hidden. The adapter bug was fixed locally before the second run: it now subclasses DeepEval's native GPT model so structured `(result, cost)` output is consumed correctly.

## Validation

- `pytest -q tests/test_agent_v2_deepeval_judge.py tests/test_agent_v2_rag_evaluation.py tests/test_agent_v2_model_gateway.py`: **9 passed**.
- Broader Agent V2 regression: **112 passed, 2 skipped**. The skips are explicitly environment-gated PostgreSQL integration tests (`BUILD12_TEST_DATABASE_URL` and `BUILD10_TEST_DATABASE_URL` were not configured), not suppressed failures.
- Tests cover public-input rejection, all required metrics, missing-context failure, metric/provider failure handling, native DeepEval adapter recognition, deterministic evaluation hooks and Judge workload configuration.
- The live artifact records successful GPT-4o Judge scores and explicit missing-context failures. No missing score, API error or failed metric is considered a pass.

## Result

BUILD-15: FAIL

DEEPEVAL: PASS

CONTEXTUAL RELEVANCY: 0.456845

FAITHFULNESS: 1.000000

ANSWER RELEVANCY: 0.500000

JUDGE VARIANCE: 0.000000 across 2 rounds

JUDGE COST: US$0.3484550 total (60,454 input / 19,732 output tokens)

PII/PHI SAFETY: PASS

DETERMINISTIC COMPARISON: PASS

REGRESSION: PASS

READY FOR BUILD-16: NO

## BUILD-15B update — retrieval recall remediation

BUILD-15B corrected the two original retrieval recall failures without changing the golden dataset, corpus, embedding or RRF configuration. The lexical candidate source now uses a same-threshold, bounded `word_similarity(product name, query)` fallback only when the existing lexical branch returned no evidence. Both `agiclovir-side-effect` and `difficult-misspelling` retrieve the expected product at rank 1; all deterministic quality metrics are 1.000000 and corpus identity remains exact.

Only after that deterministic gate passed, exactly one additional GPT-4o Judge round was attempted. Its public-only artifact is [golden-rag-v1-deepeval-15b-run.json](../../v2/rag_openai/evaluation/golden-rag-v1-deepeval-15b-run.json). It retained US$0.120705 of actual usage (25,422 input / 5,715 output tokens), bringing total recorded BUILD-15/15B Judge cost to US$0.469160. Two metric calls ended as `FAILED_OSERROR`. No score was invented and no retry was made under the requested one-round limit.

Therefore BUILD-15 remains **FAIL** and not ready for BUILD-16. The complete remediation record is [BUILD-15B](17-build-15b-retrieval-recall-remediation.md).

## BUILD-15C final reliability closeout

BUILD-15C retained the versioned golden data, BUILD-15B retrieval, canonical corpus identity, GPT-4o, temperature `0`, and all three metric definitions. It corrected the adapter's per-metric client lifecycle, preserved SDK retries at `0` so failures remain explicit, and added sanitized transport error classes plus failure-path tests. The BUILD-15B `FAILED_OSERROR` is attributed to the local 120-second execution supervisor and per-call client lifecycle, not to a confirmed OpenAI API/model failure.

The deterministic gate reran at Hit@10/MRR@10/NDCG@10/MAP@10 = **1.000000** with corpus identity PASS. One, and only one, complete GPT-4o Judge round then completed with every applicable metric scored and the no-evidence case explicitly not applicable. It used 25,420 input and 5,768 output tokens at US$0.121230. This brings the retained BUILD-15/15B/15C Judge accounting to 111,296 input tokens, 31,215 output tokens, and US$0.590390.

The final closeout is [BUILD-15C](18-build-15c-deepeval-judge-reliability-closeout.md).

BUILD-15: PASS

DEEPEVAL: PASS

CONTEXTUAL RELEVANCY: 0.529861

FAITHFULNESS: 1.000000

ANSWER RELEVANCY: 0.500000

JUDGE VARIANCE: NOT APPLICABLE (one permitted reliability round)

JUDGE COST: US$0.590390 total retained BUILD-15/15B/15C accounting

PII/PHI SAFETY: PASS

DETERMINISTIC COMPARISON: PASS

REGRESSION: PASS

READY FOR BUILD-16: YES
