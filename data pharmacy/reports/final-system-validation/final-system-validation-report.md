# Final System Validation - Docker + Agent V2

**Validation date:** 2026-08-16  
**Runtime image:** `vmec-final-v2-validation:local`  
**Dataset:** `canonical-v2-final-2026-08-16`

## Evidence

- Clean `docker build --no-cache` passed after Docker and Railway packaging were updated to include only Final Canonical V2 runtime artifacts and rebuilt RAG artifacts.
- Image inspection passed: `/app/.env` is absent; Final Canonical manifest, product/map/ingredient/knowledge JSONL, `v2_chunks.jsonl`, and `v2_embedding_index.jsonl` are present.
- In-container hashes match the final manifest for `drug_product.jsonl`, `drug_knowledge.jsonl`, and `rag/v2_chunks.jsonl`.
- V2 startup warmup passed in production-like container: `3556` products and `42588` chunks loaded in `8653.33 ms`; `/health` returned `200` and Docker health became `healthy`.
- HTTP E2E passed with no unexpected `5xx`: health, V2 catalog, patient registration, prescription create/update/approve, dose list, structured drug query, semantic/open query, red-flag safety, MISSED, DELAYED, ambiguous, nonexistent, and multiple-drug cases.
- Audit traces confirm post-confirmation routing: pregnancy query used `structured_lookup` with `PREGNANCY_LACTATION` and 2 results; open query used `rag_v2` with 5 results.
- Safety trace passed: red-flag request escalated; explicit MISSED and DELAYED requests classified correctly. Severity source remained `REVIEW_REQUIRED` with a safe fallback, without treating legacy severity metadata as a medical fact.
- All six excluded IDs were tested directly inside the running container. Each had no resolution, no catalog item, and zero retrieval results. Catalog HTTP queries also returned none of the excluded IDs.
- Final Search/RAG regression remains `Hit@5=100%`, `wrong-drug=0%`, and `wrong-type=0%` on its 18-case suite.
- Docker HTTP audit sample: 13 persisted requests, p50 `2488.60 ms`, p95 `4702.93 ms`. Model calls dominate chat latency; V2 warmup is paid at startup, not first request.

## Release Gaps

- LangSmith is not verifiable: `LANGCHAIN_API_KEY` is still a placeholder in the supplied environment. Validation ran with tracing disabled to prevent invalid-key `403` noise, so no authenticated HTTP-to-model trace can be inspected.
- V1 rollback mode starts and serves `/health`, but a clean validation database has no seeded V1 `drug`/`drug_chunks` corpus. Its catalog therefore returns zero records. This proves configuration rollback only, not functional data rollback.

```text
FINAL SYSTEM VALIDATION

STATUS:
PASS WITH ISSUES

DOCKER BUILD:
PASS

STARTUP/WARMUP:
PASS

HTTP E2E:
PASS

SAFETY:
PASS

PRESCRIPTION:
PASS

SEARCH/RAG:
PASS

EXCLUDED DRUG LEAK:
0

WRONG DRUG:
0 on Final V2 regression suite and excluded-record checks

WRONG TYPE:
0 on Final V2 regression suite

LANGSMITH:
BLOCKED - valid project/API key unavailable; no authenticated trace inspection

LATENCY:
Startup warmup 8653.33 ms; HTTP audit p50 2488.60 ms; p95 4702.93 ms

V1 ROLLBACK:
FAIL - mode startup passed, functional V1 corpus unavailable in clean Docker database

P0/P1:
P1 release gates: LangSmith trace evidence and functional V1 rollback evidence are missing

READY FOR RAILWAY PRODUCTION:
NO
```

No Railway deployment, V1 deletion, or Data Foundation modification was performed.
