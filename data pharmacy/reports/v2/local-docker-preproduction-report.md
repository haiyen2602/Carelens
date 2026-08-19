# Local Docker Pre-Production Report

**Date:** 2026-08-16  
**Scope:** clean local Docker validation only. Railway was not contacted for a deployment and production was not changed.

## Container Configuration

- Build command: `docker build --no-cache -t vmec-v2-preproduction:local .`
- Runtime mode: `APP_ENV=production`, `DRUG_KNOWLEDGE_BACKEND=v2`.
- Backend container: isolated `vmec-v2-preproduction` on local port `18000`, connected to the local compose Postgres network only.
- Container inspection: `health=healthy`, `mounts=[]`. No host `data pharmacy/` directory was bind-mounted.
- Packaged runtime path: `/app/data/drug-knowledge-v2`.

## Startup and Restart Evidence

| Start | Health | Products | Knowledge chunks | Warmup |
|---|---|---:|---:|---:|
| Initial cold start | healthy | 3,562 | 42,654 | 7,278.56ms |
| Restart 1 | healthy | 3,562 | 42,654 | 7,029.13ms |
| Restart 2 | healthy | 3,562 | 42,654 | 7,031.06ms |

`GET /health` returned `{"status":"ok","env":"production"}` after startup and after the restart sequence. Application logs showed clean shutdown/startup around every restart.

## Regression Evidence

- In-container V2 HTTP stabilization: `64` V2-default cases, including `56` known-drug cases, `50` structured lookups across all ten knowledge types, `6` semantic/RAG cases, and `8` ambiguous/nonexistent/multiple-drug cases.
- Stabilization metrics: wrong-drug `0`, wrong-type `0`, errors `0`, known-drug no-result `0`, structured-to-RAG regressions `0`, fail-closed `8/8` (100%).
- In-container V1 rollback sample: `11` cases passed.
- Targeted clean-image tests: `8 passed` covering chat safety/red-flag, `SIDE_EFFECT`, `MISSED`, `DELAYED`, catalog lookup, and prescription behavior.
- Real loopback TCP requests to the running container passed: `/api/v1/drugs=200`, prescription create `201`, prescription update `200`. The public `drug_id` remained `3b-agi-neurin-agimexpharm-10x10`.

## Failure Handling

- V2 directory set to a missing location: process exited `1` with clear `FileNotFoundError` for `drug_product.jsonl`.
- V2 directory with corrupt `drug_product.jsonl`: process exited `1` with clear `JSONDecodeError`.
- Neither case fell back silently to host data, V1, or another artifact location.

## LOCAL DOCKER PRE-PRODUCTION

```text
STATUS:
PASS WITH ISSUES

CLEAN BUILD:
PASS

STARTUP/WARMUP:
PASS

HTTP REGRESSION:
PASS

RESTART/COLD START:
PASS

FAILURE HANDLING:
PASS

V1 ROLLBACK:
PASS

BREAKING CHANGE:
NO

READY FOR RAILWAY PRODUCTION DEPLOY:
NO

OPEN ISSUES:
- LangSmith tracing attempted to send telemetry after the in-container tests and received HTTP 403. It did not affect app HTTP responses or test outcomes, but production tracing credentials/configuration should be fixed or tracing disabled deliberately.
- This is a local technical-staging result. The Railway staging gate remains blocked because the Railway project still has only the production environment.
- Migration-only technical-debt metadata is intentionally absent from the runtime image; the stabilization validator now treats it as optional rather than requiring non-runtime artifacts.
```

V1, `drug_chunks`, the frozen legacy dataset, compatibility layer, and `v1|shadow` modes remain intact. No Railway deployment, public API contract change, or full recrawl was performed.
