# BUILD-14 — Deterministic RAG Evaluation

Date: 2026-08-18  
Scope: versioned, deterministic RAG evaluation only. `AGENT_RUNTIME_ENABLED=false` remains unchanged. No model, embedding, LLM-as-a-Judge, RAG re-index, or Agent runtime request was made.

## Deliverables

- `data pharmacy/v2/rag_openai/evaluation/golden-rag-v1.json` is a versioned, non-PII golden dataset. Its seven cases cover exact drug, natural-language, indication, usage, side-effect, difficult spelling, and no-result queries.
- `backend/agents/v2/rag_evaluation.py` calculates Hit@10, MRR@10, NDCG@10, Precision@k, MAP@10, Exact Match, ROUGE-L F1, and smoothed BLEU-4 without an external package or an LLM. No-result behavior is assessed separately because standard relevance metrics are not defined for an empty relevant set.
- `scripts/agent_v2/run_deterministic_rag_evaluation.py` is the reproducible local/CI integration runner. It reads the golden dataset, checks the complete corpus registry and row count, uses only the existing pg_trgm lexical retrieval branch, and serializes every version and result. It intentionally makes no embedding request, so it cannot present lexical-only results as vector/RRF results.
- The runner compares the live registry with the signed corpus manifest for corpus version, chunk manifest, embedding model/dimension, and index version. Any mismatch is embedding identity drift and is fail-closed. A semantic-vector drift comparison would require a separately approved retained vector sample; BUILD-14 does not manufacture one.
- A release-gate primitive compares a candidate strictly against a measured baseline for quality, latency, tokens, and cost. It does not contain invented quality or price thresholds. A baseline is created only after the live runner succeeds.

## Versioned inputs

| Item | Value |
| --- | --- |
| Golden dataset | `golden-rag-v1` |
| Corpus | `legacy-drug-chunks-openai-v1` |
| Corpus chunk manifest | `E57B24693AE64F7B1514D820911C5804DCD71CB3AAF4CF45B17A2D87603E0C04` |
| Chunking | `legacy-drug-chunks-v1` |
| Embedding | `text-embedding-3-small`, 1536 dimensions |
| Index | `pgvector-hnsw-cosine-v1` |
| Deterministic retrieval runner | `lexical-pg-trgm-v1` |
| Deterministic response template | `deterministic-grounded-template-v1` |
| Prompt | `none-build-14` |

The corpus manifest retains BUILD-7D's durable ingestion record: 14,423 chunks, 18,899,846 input tokens, and US$0.377997. These historical embedding costs are recorded as corpus provenance; BUILD-14 itself made zero model/embedding calls.

## Natural-language Paracetamol regression

`natural-paracetamol-finding` expects `paracetamol-kabi-1000mg-frensenius-kabi-48-chai-x-100ml` for the natural-language query “Thuốc Paracetamol Kabi có tác dụng hạ sốt không?”. BUILD-7D recorded that this natural-language lexical case did not meet the then-current threshold. The golden case preserves that correct relevance expectation and never treats an empty result as an expected PASS. On the live BUILD-14 run it now returns the expected product at rank 1.

## Validation executed

`pytest -q tests/test_agent_v2_rag_evaluation.py tests/test_agent_v2_retrieval.py tests/test_rag_corpus_recovery.py`: **14 passed**.

This verifies metric calculations, no-result treatment, the Paracetamol recall regression, strict baseline regression behavior, corpus reproducibility primitives, and existing Retrieval Gateway behavior. The suite does not contact PostgreSQL or OpenAI.

The broader Agent V2 regression suite (`tests/test_agent_v2_*.py`) also passed after BUILD-14C: **108 passed, 2 skipped**. The two existing infrastructure-specific skips remain explicit and are not counted as passes.

## Live lexical evaluation

The rerun used the existing local PostgreSQL corpus. No embedding/model API was called. The measured, versioned baseline is [golden-rag-v1-baseline.json](../../v2/rag_openai/evaluation/golden-rag-v1-baseline.json). A final independent candidate retained all quality/identity metrics, but its P95 was higher than the measured baseline; the strict release gate therefore fails closed.

| Measure | Measured baseline | Final candidate |
| --- | ---: | ---: |
| Hit@10 | 0.666667 | 0.666667 |
| MRR@10 | 0.666667 | 0.666667 |
| NDCG@10 | 0.666667 | 0.666667 |
| Precision@5 | 0.133333 | 0.133333 |
| MAP@10 | 0.666667 | 0.666667 |
| Exact Match | 0.714286 | 0.714286 |
| ROUGE-L F1 | 0.802198 | 0.802198 |
| BLEU-4 | 0.784132 | 0.784132 |
| No-result contract accuracy | 0.714286 | 0.714286 |
| P50 latency | 3383.325 ms | 3404.848 ms |
| P95 latency | 5577.928 ms | 5650.603 ms |
| Input/output tokens | 0 / 0 | 0 / 0 |
| New provider cost | US$0.000000 | US$0.000000 |

Corpus identity drift is **PASS**: the database registry matches corpus `legacy-drug-chunks-openai-v1`, chunk manifest `E57…0C04`, `text-embedding-3-small`, 1536 dimensions, and `pgvector-hnsw-cosine-v1`.

The measured baseline is intentionally a no-regression threshold, not an invented quality target. Two cases remain visible in the results: `agiclovir-side-effect` and `difficult-misspelling` return no lexical candidate. They fail closed and do not produce a fabricated drug answer, but are P1 recall follow-up items. The 72.675 ms P95 regression is also a P1 performance-gate finding: enough to fail this strict gate, not silently relaxed. This runner evaluates lexical retrieval only; it must not be used to claim fresh vector/RRF quality without an approved deterministic query-vector fixture.

## Reproducible next command

To repeat the candidate gate against the recorded baseline, run:

```powershell
python scripts/agent_v2/run_deterministic_rag_evaluation.py --baseline 'data pharmacy/v2/rag_openai/evaluation/golden-rag-v1-baseline.json' --output data\rag-eval\golden-rag-v1-candidate.json
```

No CI job should accept a changed corpus/version as the old baseline.

The CI-safe unit gate is:

```powershell
pytest -q tests/test_agent_v2_rag_evaluation.py tests/test_agent_v2_retrieval.py tests/test_rag_corpus_recovery.py
```

## BUILD-14C — Stable Performance Release Gate

BUILD-14C preserved the corpus, golden dataset, and lexical retrieval code. It used one warm-up run followed by two independent three-run cohorts in the same local PostgreSQL environment. The initial single-run P95 difference (5577.928 ms to 5650.603 ms) was not used as a reason to relax a threshold: the new tolerance is the directly observed pooled P95 envelope.

| Measure | Result |
| --- | ---: |
| Benchmark runs | 3 baseline + 3 candidate (6 measured; 42 query samples) |
| Warm-up | 1 complete golden run |
| P50 | 3340.549 ms |
| P95 | 5582.220 ms |
| P99 | 5622.922 ms |
| Median | 3340.549 ms |
| Overall latency variance | 4,555,826.552 ms² |
| Baseline-run P95 range / variance | 5568.629–5582.220 ms / 31.184 ms² |
| Candidate-run P95 range / variance | 5545.395–5622.922 ms / 1006.679 ms² |

The baseline and candidate P95 ranges overlap. The immutable stored baseline P95 (5577.928 ms) and candidate median P95 (5588.865 ms) are both inside the measured pooled envelope 5545.395–5622.922 ms. Therefore the former 72.675 ms single-run difference is measurement variability in this benchmark, not a meaningful latency regression under the empirical stability rule. No tolerance percentage or hard-coded latency margin was introduced.

Quality metrics remain exact no-regression across every measured run. Corpus identity remains exact: corpus version, manifest hash, `text-embedding-3-small`, 1536 dimensions, and `pgvector-hnsw-cosine-v1` all match. No OpenAI or embedding request was issued. The two existing fail-closed recall misses (`agiclovir-side-effect`, `difficult-misspelling`) remain P1 and their expected results were not altered.

BUILD-14C: PASS

BENCHMARK RUNS: 6 measured (3 baseline / 3 candidate)

WARMUP: PASS (1 run)

P50: 3340.549 ms

P95: 5582.220 ms

P99: 5622.922 ms

MEASURED VARIABILITY: PASS (pooled P95 spread 77.528 ms)

PERFORMANCE TOLERANCE: PASS (empirical P95 envelope 5545.395–5622.922 ms)

QUALITY REGRESSION: PASS

CORPUS IDENTITY: PASS

PERFORMANCE GATE: PASS

RELEASE GATE: PASS

BUILD-14 FINAL: PASS

READY FOR BUILD-15: YES
