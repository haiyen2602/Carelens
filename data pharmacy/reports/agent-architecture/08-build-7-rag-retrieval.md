# BUILD-7 — RAG / Retrieval Architecture

Date: 2026-08-18  
Scope: an Agent V2 Retrieval Gateway behind the existing disabled Agent path. `AGENT_RUNTIME_ENABLED=false` remains unchanged. No Vinmec web search, Doctor Handoff, long-term memory, write tool, migration, or runtime cutover was made.

## Audit and reuse decision

The repository has two distinct retrieval implementations:

- The legacy PostgreSQL path is `backend/services/retrieval.py`: OpenAI query embedding, pgvector/HNSW vector search, pg_trgm lexical search, and RRF fusion over `drug_chunks`.
- The promoted Canonical Drug Knowledge V2 artifact is file-backed. Its verified manifest records 42,588 RAG chunks and the `local-tfidf-hash-v1` index. This is used by the existing Drug Knowledge V2 facade and is not an OpenAI-vector index.

BUILD-7 reuses the former, approved pgvector + RRF pipeline rather than introducing a new vector store or changing legacy chat. `hybrid_search` now accepts an optional, backward-compatible per-call `top_k`; legacy callers retain the configured default.

At the initial audit, clean PostgreSQL revision `0029` contained **0** `drug_chunks` and the old seed script read an obsolete path. BUILD-7C/7D replaced that gap with a separately versioned, active-only OpenAI corpus. The Canonical V2 files remain a 512-dimensional local TF-IDF index and are not queried with `text-embedding-3-small` vectors (1,536 dimensions); no Canonical V2 TF-IDF artifact was edited.

This is a reproducibility/data-pipeline defect, not a reason to bypass the regression tests or to substitute an incompatible index.

## Retrieval Gateway

`backend/agents/v2/retrieval.py` provides a typed, read-only boundary:

```text
validated query
  → Model Gateway EMBEDDING (`text-embedding-3-small`)
  → server-side AgentRetrievalDomainService
  → legacy pgvector + lexical + RRF ranking
  → bounded Retrieval Context
```

The Agent package does not import ORM/SQL. `backend/services/agent_retrieval.py` owns the adapter to the existing retrieval service. The gateway validates input with `extra="forbid"`, caps `top_k` and context token budget from configuration, keeps complete chunks rather than silently truncating evidence, and converts invalid input, embedding/model mismatch, provider errors, retrieval failures, and empty evidence into typed safe results. No model receives raw database errors.

`AGENT_RETRIEVAL_TOP_K=5` and `AGENT_RETRIEVAL_TOKEN_BUDGET=700` are configurable, bounded settings. The configured embedding workload is `text-embedding-3-small`.

## Context, provenance, and isolation

Each returned document carries source/chunk ID, legacy drug ID, field group, source label, vector and lexical scores where available, RRF relevance, rank, and retrieval timestamp. It becomes a `RETRIEVAL` Context item with `RETRIEVAL` authority and lower priority than protected Operational DB, Safety, Doctor, System, and Policy context. Thus retrieved text cannot override a patient dose, safety decision, prescription, or doctor fact.

There is no patient parameter in the retrieval request or domain call. The strict request schema rejects injected fields such as `patient_id`; this generic drug-knowledge path therefore cannot use caller-supplied patient scope to retrieve another patient's data.

## Evaluation hooks

`backend/agents/v2/retrieval_eval.py` adds deterministic, side-effect-free hooks for Hit@10, MRR@10, NDCG@10, Precision@k, and MAP@10. These accept version-controlled evaluation cases and make no model or database call. A golden dataset, threshold, and release gate remain BUILD-14 work; they were not invented during BUILD-7.

## Validation

```text
AGENT_RUNTIME_ENABLED=False
AGENT_EMBEDDING_MODEL=text-embedding-3-small
AGENT_RETRIEVAL_TOP_K=5
AGENT_RETRIEVAL_TOKEN_BUDGET=700

pytest (Agent Retrieval, Model Gateway, legacy retrieval, tools, context,
runtime/routes, chat regressions, and Drug Knowledge V2 catalog):
77 passed, 2 failed

Failing legacy SQL retrieval regressions:
- test_word_similarity_threshold_guc_is_set_not_just_similarity_threshold
- test_lexical_search_finds_exact_drug_name_match

Both failures result from the empty local `drug_chunks` table, not a changed
threshold or ranking algorithm.

Retrieval Gateway/unit tests, context authority/budget tests, embedding-gateway
test, V2 catalog regression, lint, compilation, and `git diff --check`: PASS
```

Tests cover embedding-to-domain handoff, top-k/token budget selection, no-result and unavailable fail-safe behavior, rejected patient-field injection, embedding model pinning, context non-override behavior, legacy-domain source mapping, and deterministic metrics.

## P0/P1

- **P0: none.** BUILD-7D adds a durable pre-request reservation, response staging, cost guard over committed plus outstanding usage, and fail-closed unresolved state. Historical US$0.377997 use remains explicitly reconciled rather than rewritten to the earlier estimate.
- **P1 — retrieval evaluation release gate.** BUILD-14 must supply a versioned golden dataset, configuration/version recording, category metrics, and approved thresholds over the restored corpus.
- **P1 — natural-language recall tuning.** The free-form Vietnamese Paracetamol smoke query did not clear the current lexical threshold. Exact product-name smoke passed through vector, lexical, and RRF. Treat recall thresholds as a measured evaluation concern, not as a reason to lower them without a golden dataset.

## BUILD-7C recovery outcome

BUILD-7C rebuilt a candidate OpenAI corpus deterministically from frozen V1
source filtered by Final Canonical V2: 3,556 active/approved legacy drug IDs,
six exclusions, and 14,423 chunks. Preflight signed source hash
`39ABC318DCEF1AD5D4817005DC4621DA328DE3DB26CDE56FED5A412092A2C2C0` and chunk
hash `E57B24693AE64F7B1514D820911C5804DCD71CB3AAF4CF45B17A2D87603E0C04`; the
estimate was 12,748,090 tokens / US$0.254962, below the US$0.29 authorization.

The recovery is fail-closed. After an interrupted execution and resume, the
durable PostgreSQL registry records 18,899,846 tokens / US$0.377997, exceeding
the approved cap. Its local final-run counter and generated manifest record
only 12,748,090 / US$0.254962. A response that arrives before its checkpoint
transaction can be billed yet remain pending; resume may embed it again. This
invalidates the cost and no-unnecessary-embedding guarantees. No rerun, SQL
regression, or paid retrieval smoke was performed after that gate failed.

Committed rows have 14,423 checkpoints, zero duplicate keys, zero missing or
unexpected drug IDs, and all vectors at 1,536 dimensions; this does not
override the cost gate. Canonical V2 TF-IDF artifacts were not modified.

## BUILD-7D reservation and reconciliation closeout

Alembic `0031` adds `rag_embedding_reservation`, keyed by deterministic batch
identity and storing corpus/version, ordered chunk keys, planned ceiling,
provider request/usage metadata, status, and a temporary staged response. The
runner commits a reservation before every provider request; a crash before a
durable response becomes `UNRESOLVED` and blocks retry, while a staged response
is committed into chunks/checkpoints without another embedding request. The
guard includes committed registry tokens plus `RESERVED`, `UNRESOLVED`, and
uncommitted provider-response liability.

The existing 0030 aggregate was reconciled truthfully as one
`HISTORICAL_RECONCILED` ledger record. Its final durable value is 18,899,846
tokens / US$0.377997, distinct from the original planned US$0.254962. A no-op
rerun created zero batches and made no embedding request. Database integrity is
14,423 rows / logical keys / complete checkpoints, with 14,423 non-null 1,536D
vectors. Both PostgreSQL SQL regressions pass.

A real post-remediation smoke used `text-embedding-3-small` for exact
Agiclovir and Paracetamol Kabi queries: both returned vector candidates,
lexical candidates, and RRF results containing the expected drug. The final
smoke request reported 22 tokens / US$0.00000044; it is operational query cost,
not corpus-ingestion usage and does not alter the durable corpus total.

## Conclusion

BUILD-7: PASS

RETRIEVAL GATEWAY: PASS

EMBEDDING: PASS (historical usage reconciled; future requests reservation-safe)

CONTEXT INTEGRATION: PASS

PROVENANCE: PASS

ISOLATION: PASS

EVAL HOOKS: PASS

REGRESSION: PASS

READY FOR BUILD-8: YES
