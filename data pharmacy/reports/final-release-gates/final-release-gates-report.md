# Final Release Gates

**Assessment date:** 2026-08-16  
**Scope:** local Docker release gates only; no Railway deployment.

## Evidence Collected

- The prior Final System Validation verified the promoted Canonical V2 image: clean build, warmup (`3556` active products / `42588` knowledge chunks), healthcheck, HTTP E2E, prescription flow, safety routing, and excluded-record checks all passed.
- Final V2 Search/RAG regression remains `Hit@5=100%`, `wrong-drug=0%`, and `wrong-type=0%` on the 18-case suite.
- The current environment has an OpenAI key configured, but no usable LangSmith credential: `LANGSMITH_API_KEY` is absent and `LANGCHAIN_API_KEY` is a placeholder. The configured project/tracing flags alone cannot authenticate a trace.
- The frozen V1 source has catalog records and textual chunks under `data pharmacy/data-version1/`; `_chunks.jsonl` does not contain embeddings. The existing V1 ingestion path therefore needs the legacy source plus a reproducible embedding/load run before vector retrieval can work in an empty database.
- Prior clean-Docker validation proved `DRUG_KNOWLEDGE_BACKEND=v1` can start, but the clean database had no V1 `drug` or `drug_chunks` rows. It is configuration rollback only, not functional rollback.

## Blockers

1. Authenticated LangSmith validation cannot be run without a valid `LANGSMITH_API_KEY` or `LANGCHAIN_API_KEY` supplied through the local Docker environment or secret manager. No key value was printed or recorded.
2. Docker daemon access is unavailable in this session because the workspace approval service reported exhausted workspace credits. A clean build/run cannot be performed to seed and validate V1 rollback.
3. Reconstructing V1 `drug_chunks` requires embeddings, which are not present in the frozen JSONL. It must be done as an explicit, reproducible seed operation using an authorized embedding credential, then validated in clean Docker.

## Required Next Run

1. Provide a valid LangSmith project/API key to the local Docker secret source, then enable tracing and inspect a real chat trace end-to-end without logging secrets or unnecessary patient content.
2. Run a deterministic V1 seed into a fresh database: frozen catalog plus legacy chunks with their real embeddings; verify catalog, known-drug retrieval, safety retrieval, and HTTP flow in `v1` mode.
3. Repeat the V2 HTTP smoke suite after the two gates pass. Keep `v1`, `v2`, and `shadow` modes available.

```text
FINAL RELEASE GATES

STATUS:
BLOCKED

LANGSMITH:
BLOCKED - no valid LangSmith API key is configured; authenticated trace evidence is unavailable.

V1 FUNCTIONAL ROLLBACK:
BLOCKED - frozen V1 chunks require an embedding/seed run, and clean Docker validation cannot run in this session.

V2 REGRESSION:
PASS - prior Final System Validation: HTTP E2E, safety, prescription, and Final V2 Search/RAG regression all passed.

P0/P1:
P1 - authenticated LangSmith trace evidence missing.
P1 - functional V1 rollback corpus/HTTP evidence missing.

READY FOR RAILWAY PRODUCTION:
NO
```

No Railway deployment, V1 deletion/deprecation, or Data Foundation modification was performed.
