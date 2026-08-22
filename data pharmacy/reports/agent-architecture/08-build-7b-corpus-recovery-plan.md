# BUILD-7B — RAG Corpus Recovery Plan

Date: 2026-08-18  
Scope: read-only corpus audit and recovery plan. No embedding request, database write, artifact regeneration, or bulk API cost was incurred.

## Corpus audit

There are three distinct assets; they must not be conflated.

| Asset | Status | Suitable for OpenAI pgvector recovery? |
| --- | --- | --- |
| `data pharmacy/data-version1/*/thuoc.json` | 11 frozen source files, 3,562 drug records | **Yes.** This is the reproducible source for the legacy `drug_chunks` contract. |
| `data pharmacy/data-version1/_chunks.jsonl` | 14,200-line historical staging output | No. It is stale: a fresh deterministic chunk build produces 14,447 chunks. |
| `data pharmacy/v2/final_canonical/rag/*` | 42,588 Canonical V2 chunks plus `local-tfidf-hash-v1` 512D index | No. This is a separate, file-backed V2 retrieval artifact, not a `text-embedding-3-small` (1,536D) pgvector index. |

The approved recovery source is the frozen V1 JSON corpus, processed directly by the existing `scripts/chunk_drugs.py` rules. It has 11 source files, 3,562 records, and a fresh chunk result of 14,447 rows:

```text
cong_dung:      3,562
tac_dung_phu:   3,805
cach_dung:      3,566
bao_quan:       3,514
```

The deterministic chunk payload hash under the current chunker is:

```text
SHA-256: 5E154E639FE5579C233A3169DD596D1F68120F3CC13B6B2951585029CDEB23FE
chunker script SHA-256: 347B000CFBE90FB7282357AB2F58E9F3F482C457249A6F7D24F733E74BBA7D94
```

The currently committed Canonical V2 manifest validates its top-level artifacts and `rag/eval_results.json`. The two nested RAG JSONL files have byte-hash mismatches in this Windows checkout solely because Git has converted their LF bytes to CRLF: their committed Git blobs match the manifest hashes exactly. `.gitattributes` currently matches only `final_canonical/*.jsonl`, not nested `final_canonical/rag/*.jsonl`. A recursive LF rule and a clean-checkout hash gate are required before any new corpus manifest is approved.

## Exact estimate

The estimate was calculated locally using `tiktoken.encoding_for_model("text-embedding-3-small")` over every fresh chunk payload; it made no API call.

| Measure | Value |
| --- | ---: |
| Total chunks | 14,447 |
| Estimated input tokens | 12,772,895 |
| Token range per chunk | 47–7,500 |
| Chunks at or above 7,000 tokens | 122 |
| OpenAI model price used for estimate | US$0.02 / 1M input tokens |
| Estimated embedding cost | **US$0.255458** (about **US$0.26**) |
| 10% retry contingency ceiling | **US$0.281004** (about **US$0.29**) |

The model page currently lists `text-embedding-3-small` at US$0.02 per 1M tokens. The API-reported `usage` remains the billing source of truth; this tokenizer estimate is a pre-approval ceiling, not an invoice. [Official OpenAI model documentation](https://developers.openai.com/api/docs/models/text-embedding-3-small)

## Batch and time plan

The old count-only batch size of 100 yields 145 requests, but individual batches range from 37,010 to 187,889 tokens. It is therefore not a portable rate-limit strategy.

Use deterministic source order and a token-capped batcher instead:

- Default preflight cap: 30,000 input tokens/batch, maximum 100 chunks/batch.
- Result: 449 batches, each 22,626–30,000 tokens; one worker initially.
- Query the configured embedding credential's actual RPM/TPM before starting; use a token-bucket limiter and record the discovered limits in the run manifest. Never assume a paid tier.
- At the currently documented Free-tier 40,000 TPM, the token-only lower bound is about 5h20m. At 1,000,000 TPM, it is about 13 minutes. Allow additional request, PostgreSQL, and retry time; no duration is promised until preflight reads the account limits.
- Commit each successful batch transactionally. Stop on any non-retryable error; do not skip a chunk or lower the model/dimension.

## Versioning and immutable manifest

The recovery implementation must create a new OpenAI corpus namespace; it must not overwrite Canonical V2's TF-IDF artifacts or pretend they share an index.

Proposed identifiers:

```text
corpus_version:       legacy-drug-chunks-openai-v1
source_snapshot:      data-version1 at pinned Git commit + per-file SHA-256
chunking_version:     chunk-drugs-sha256-347B…7D94
chunk_manifest_sha256: 5E154E…23FE
embedding_model:      text-embedding-3-small
embedding_dimensions: 1536
embedding_version:    explicit configured model snapshot/alias + API response metadata
index_version:        pgvector-hnsw-cosine-v1 + migration/DDL hash
retrieval_version:    legacy-hybrid-rrf-v1 + threshold configuration
```

The generated manifest must be written with LF bytes and include: source Git commit; every source-file hash; deterministic ordering; chunk count and field-group counts; canonical payload hash; tokenizer/version; embedding model and dimensions; batch/token configuration; index DDL/configuration; ingestion run ID; timestamps; OpenAI usage totals; and the SHA-256 of every generated artifact. It is approved only after a clean checkout recomputes the same hashes. `.gitattributes` must protect both root and recursive RAG JSONL paths before this gate.

## Idempotent, resumable ingestion design

This requires a small additive persistence design before execution; the current `drug_chunks` schema has neither a corpus version nor a logical uniqueness key.

1. Generate chunks in deterministic `(relative source path, legacy_drug_id, field_group, split_ordinal)` order. Compute `chunk_key = SHA-256(canonical UTF-8 JSON payload)`.
2. Store a corpus registry/manifest record and an ingestion checkpoint keyed by `(corpus_version, chunk_key, embedding_model, embedding_dimensions)`. Enforce that tuple as a database unique key (either additive columns plus a partial unique index on `drug_chunks`, or a sidecar mapping table that references each inserted `drug_chunks.id`).
3. Before an API request, query completed keys; embed only absent/pending keys. Persist the request batch ID and ordered keys.
4. After a response, validate one non-empty 1,536-dimensional vector per key, insert/upsert chunks and mark every key complete in **one database transaction**.
5. On restart, resume only incomplete keys in original order. An ambiguous network result remains `PENDING` and may re-embed at most its bounded token batch; it must never create duplicate rows. A rerun after `COMPLETE` must send zero chunks and insert zero rows.
6. The corpus becomes `READY` only after all validation gates pass. Keep prior corpus versions immutable; no delete/rebuild-in-place operation is part of recovery.

## Validation plan

Preflight must fail closed if source count, source/chunk hashes, canonical line endings, configured model, API availability, or token/cost approval differs from the signed plan.

After a run, validate:

- `14,447` rows for the exact corpus/version and the four field-group counts above;
- every vector has dimension `1536`, is non-null/non-empty, and carries the recorded model/version;
- zero duplicate logical keys; zero missing source keys; zero unexpected source IDs; and no checkpoint left pending;
- source traceability for every row back to the signed source file and `chunk_key`;
- a second ingestion run sends/inserts `0` rows;
- the two real PostgreSQL regressions pass: `test_word_similarity_threshold_guc_is_set_not_just_similarity_threshold` and `test_lexical_search_finds_exact_drug_name_match`;
- real embedding → vector/lexical/RRF retrieval smoke returns a grounded result for the known Agiclovir and Paracetamol cases, with expected chunk metadata and no raw error;
- manifest hashes reproduce from a fresh clone, not from an old Docker volume.

Canonical V2 currently has 3,556 active products and explicitly excludes six legacy IDs. The legacy source contains 24 chunks for those six IDs. Recovery must not silently include or discard them for the Agent path: product/clinical owners must choose either (a) a strict legacy-compatibility corpus with server-side canonical-status filtering, or (b) an approved active-only corpus with new expected counts and regressions. Until that decision is recorded, the Agent V2 retriever cannot safely expose the recovered corpus.

## Preconditions before execution

1. Approve the maximum US$0.29 embedding budget and the credential/project to charge.
2. Approve the legacy-versus-active corpus policy for the six excluded IDs.
3. Fix and verify recursive LF enforcement for all manifest-hashed JSONL files, then obtain a clean-checkout hash PASS.
4. Implement/review the additive corpus registry, logical unique key, checkpoint, and deterministic seed command; dry-run must reproduce this report's counts and estimate.
5. Run only against a clean local PostgreSQL database; no Railway or runtime cutover.

## Conclusion

BUILD-7B: PASS

CORPUS SOURCE: `data pharmacy/data-version1/*/thuoc.json` (3,562 records; direct deterministic chunking)

TOTAL CHUNKS: 14,447

ESTIMATED TOKENS: 12,772,895

ESTIMATED EMBEDDING COST: US$0.255458 baseline; US$0.281004 with 10% retry contingency

VERSIONING: PASS — specified; implementation and clean-checkout LF gate pending

IDEMPOTENT INGESTION: PASS — specified; additive implementation pending

VALIDATION PLAN: PASS

READY TO RUN FULL EMBEDDING: NO
