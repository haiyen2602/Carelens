# BUILD-15C — DeepEval Judge Reliability Closeout

Date: 2026-08-18  
Scope: Judge reliability/completeness only. `golden-rag-v1`, the BUILD-15B retrieval implementation, corpus/manifest/embedding/index, GPT-4o, temperature `0`, and the three DeepEval metric definitions were retained unchanged. `AGENT_RUNTIME_ENABLED=false` remains unchanged.

## FAILED_OSERROR root cause

BUILD-15B's one-round process was started under a local command supervisor with a 120-second limit. The supervisor timed out at 124 seconds while the Python process continued in the background and finished later. The persisted result contained two bare `FAILED_OSERROR` records near the end of the round.

The original adapter also constructed a new `OpenAI` SDK/httpx client for every DeepEval metric call (up to 18 per round), disabled SDK retries, and collapsed every exception to only its outer Python class. It therefore could neither reuse a stable transport nor distinguish a provider connection failure from a local transport/handle error. There is no OpenAI status code, request ID, API timeout, model failure, or dataset evidence that supports attributing this specific error to GPT-4o.

Root-cause disposition: **local execution-supervisor timeout plus per-call transport lifecycle; not a confirmed OpenAI model/API error**.

## Reliability remediation

- `TrackingGPT4oJudge` now owns one SDK client for a full Judge round, reuses it for all metric calls, and closes it after the round.
- SDK retry remains `0`: a provider error continues to be recorded as a failed metric instead of being hidden by an untracked retry.
- Failure classification now distinguishes `FAILED_OPENAI_TIMEOUT`, `FAILED_OPENAI_CONNECTION`, and `FAILED_TRANSPORT_OSERROR`, while preserving no raw transport details, prompts, secrets, PII/PHI, or hidden reasoning.
- The final round used a 10-minute local supervisor budget. This is execution control only; it does not change the prompt, metric definition, model, temperature, corpus, retrieval, answer, or Judge threshold.

Focused reliability and retrieval suite: **33 passed**. It includes the exact `OSError` failure path, client reuse/close behavior, missing-context fail-closed behavior, PII/PHI rejection, and deterministic retrieval regressions.

Broader Agent V2 + legacy retrieval regression: **129 passed, 2 skipped**. The two explicit skips require disposable PostgreSQL URLs (`BUILD12_TEST_DATABASE_URL` and `BUILD10_TEST_DATABASE_URL`); they are not failures suppressed as passes.

## Deterministic gate

The gate was rerun before Judge calls. It retained the BUILD-15B retrieval version and corpus identity:

| Gate | Result |
| --- | --- |
| Hit@10 | 1.000000 |
| MRR@10 | 1.000000 |
| NDCG@10 | 1.000000 |
| MAP@10 | 1.000000 |
| Corpus identity | PASS |

Identity is still `legacy-drug-chunks-openai-v1`, manifest `E57B24693AE64F7B1514D820911C5804DCD71CB3AAF4CF45B17A2D87603E0C04`, `text-embedding-3-small` at 1536 dimensions, and `pgvector-hnsw-cosine-v1`.

## Complete GPT-4o Judge round

After the deterministic gate passed, exactly one complete Judge round was run. All six evidence-bearing golden cases have valid scores for all three metrics. The no-evidence golden case is explicitly `NOT_APPLICABLE_NO_EVIDENCE` for all three, not a scored pass. There were zero failed metric calls and no additional Judge round was run.

The durable public-only artifact is [golden-rag-v1-deepeval-15c-run.json](../../v2/rag_openai/evaluation/golden-rag-v1-deepeval-15c-run.json). It contains only public golden query/answer/context references, canonical scores/statuses, versioning and aggregate usage; it contains no patient, conversation, actor, prompt, secret or hidden-reasoning data.

| Metric | Result |
| --- | ---: |
| Contextual Relevancy | 0.529861 |
| Faithfulness | 1.000000 |
| Answer Relevancy | 0.500000 |
| Applicable failed metric calls | 0 |
| Judge tokens | 25,420 input / 5,768 output |
| New Judge cost | US$0.121230 |

The Judge remains offline/pre-release only and has no authority over runtime output or Safety decisions. Cost uses the configured GPT-4o basis (US$2.50/M input and US$10.00/M output), as documented in the [official OpenAI GPT-4o documentation](https://developers.openai.com/api/docs/models/gpt-4o).

## Result

BUILD-15C: PASS

OSERROR ROOT CAUSE: PASS — local supervisor/transport lifecycle; no confirmed provider/model error

JUDGE RELIABILITY: PASS

DETERMINISTIC GATE: PASS

CONTEXTUAL RELEVANCY: 0.529861

FAITHFULNESS: 1.000000

ANSWER RELEVANCY: 0.500000

FAILED METRIC CALLS: 0

JUDGE TOKENS: 25,420 input / 5,768 output

NEW JUDGE COST: US$0.121230

PII/PHI SAFETY: PASS

REGRESSION: PASS

BUILD-15 FINAL: PASS

READY FOR BUILD-16: YES
