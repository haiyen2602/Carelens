# BUILD-18 — Railway Staging Provision & Deployment

Date: 2026-08-19
Scope: real Railway `staging` environment, real Postgres, real deploy, real
corpus restore, real (small, bounded) OpenAI spend, real live HTTP E2E.
Production was never modified. Three genuine, previously-undetected
integration defects were found by this live testing and are reported below
rather than patched to force a passing grade.

> **UPDATE (BUILD-18B, same date):** all 3 defects reported below (Vinmec
> Web's per-candidate exception isolation, the Safety Domain occurrence-id
> mismatch, and the missing `db.commit()` in the orchestrate route) have been
> fixed, tested against real domain objects and real cross-session commits,
> and re-verified live on this same staging environment with direct database
> confirmation. **BUILD-18 FINAL: PASS.** See
> [22-build-18b-staging-defect-remediation-closeout.md](22-build-18b-staging-defect-remediation-closeout.md)
> for the fix, its tests, and the live re-verification. The closeout block
> below is left exactly as originally written, as the historical record of
> what this build found.

## Absolute constraints — verified, not just claimed

| Constraint | Status | Evidence |
| --- | --- | --- |
| Production not changed | **CONFIRMED** | Production's 3 service deployment timestamps (`Postgres` 2026-08-12T09:02:57Z, `VMEC-04/FE` 2026-08-17T15:29:06Z, `VMEC-04/BE` 2026-08-17T16:52:42Z) and its Postgres `DATABASE_URL` (SHA-256 prefix `e69b813c840f`) are byte-identical before and after every step below, re-verified as the last action of this build |
| No production `DATABASE_URL` used anywhere | **CONFIRMED** | Staging `BE`'s `DATABASE_URL` SHA-256 prefix `b49a4803ee4f` matches only the new staging Postgres, confirmed different from production's `e69b813c840f` |
| No production patient/user/clinical data copied to staging | **CONFIRMED** | Staging Postgres was provisioned via `railway add --database postgres` with **no** `--duplicate`; it started with 0 tables until `alembic upgrade head` created schema. The only data restored (below) is: (a) the BUILD-7D RAG corpus (public drug-knowledge text + embeddings, not patient data) and (b) the Canonical Drug V2 catalog (public drug names/forms/routes, not patient data). All patient/account/prescription rows on staging are synthetic, created by this build's own seed script |
| Legacy production traffic not routed to Agent V2 | **CONFIRMED** | `backend/api/chat_routes.py` and `backend/main.py` were not touched; production's `AGENT_RUNTIME_ENABLED` was never read or written by this session |
| Corpus not re-embedded | **CONFIRMED** | `NEW EMBEDDING CALLS: 0` for the corpus restore (data-only row copy via SQLAlchemy, no OpenAI call). The only OpenAI calls made anywhere in this build are the 5 one-time model-gateway smoke calls and the live E2E's own drug-info/RAG queries (query embeddings only, not corpus re-embedding) |
| Staging secrets separate from production | **CONFIRMED** | `JWT_SECRET`/`INTERNAL_AUTH_SECRET` were freshly generated (`secrets.token_hex(32)`) for staging only; this session never read production's values (by design, so there is nothing to compare against — the generated values are provably new random material, not a copy) |

## 1–3. Provision, configure, deploy

```
railway environment new staging --json          # empty environment, no --duplicate
railway add --database postgres --json          # fresh, empty Postgres ("Postgres-_hCI")
railway add --service BE --json                 # empty backend service
railway variable set ... (28 keys, --service BE --environment staging)
railway up --service BE --environment staging -c
railway domain --service BE --environment staging --json
  -> https://be-staging-0111.up.railway.app
```

Configured variables (values never printed to any log in this session):
staging-only `JWT_SECRET`/`INTERNAL_AUTH_SECRET`; `DATABASE_URL` as a
same-service reference (`postgresql://...@postgres-hci.railway.internal/...`,
private-network only); all 6 `OPENAI*_API_KEY` roles (reused from this
workspace's local `.env`, which — per `docs/DEPLOY.md`'s own statement that
production env is stored on Railway and never read from `.env` — is
independent of whatever key production's Railway environment holds);
`AGENT_*_MODEL`/`RAG_JUDGE_MODEL`/`EMBEDDING_MODEL` at their documented
defaults; `DRUG_KNOWLEDGE_BACKEND=v2`, `PRESCRIPTION_V2_MODE=shadow`,
`DOSE_RUNTIME_MODE=v2`, `SAFETY_RUNTIME_MODE=shadow` (chosen so the
synthetic test data in step 8 actually populates V2 rows the Agent V2 tools
can read — production's own current values were not read); `APP_ENV=development`
(chosen deliberately over `production`, since the field is purely cosmetic
per BUILD-17's finding and `development` cannot be mistaken for "this is the
real production system"); `CORS_ORIGINS` set to a placeholder
(`https://vmec-04-staging.invalid`, no staging frontend was deployed — out
of this build's scope); `AGENT_RUNTIME_ENABLED=false` and
`AGENT_VINMEC_WEB_ENABLED=false` initially, exactly as required.

**Deploy**: `railway up -c` built the same `Dockerfile`, streamed
`pip install`, pushed the image — "Deploy complete". `GET /health` → `200
{"status":"ok","env":"development"}`.

**Migrations**: `alembic upgrade head` ran automatically as `railway.json`'s
`preDeployCommand`. Verified independently (`railway ssh` needs a
registered key this session doesn't have, so verification instead used a
temporary `railway tcp-proxy` to the staging Postgres, deleted immediately
after use):

```
$ DATABASE_URL=<staging, via temp proxy> python -m alembic current
0033 (head)
```

MIGRATIONS: **PASS**.

## 4. RAG corpus restore

`pg_dump`/`pg_restore`/`psql` are not installed in this environment,
so BUILD-17's plan was executed with a new, purpose-built, data-only
SQLAlchemy copier instead (`scripts/agent_v2/restore_rag_corpus_tables.py`):
reads `rag_corpus`/`drug_chunks`/`rag_embedding_reservation` from the local
BUILD-7D database, refuses to run if the target already has rows in any of
the three tables, copies every row byte-for-byte (including the 1,536-D
vectors), zero OpenAI calls.

```
$ python scripts/agent_v2/restore_rag_corpus_tables.py --source-url <local> --target-url <staging>
RESTORED: rag_corpus rows=1
RESTORED: drug_chunks rows=14423
RESTORED: rag_embedding_reservation rows=1
DONE: {'rag_corpus': 1, 'drug_chunks': 14423, 'rag_embedding_reservation': 1}
```

CORPUS RESTORE: **PASS**.

### Identity verification (BUILD-17's tool, run for real against staging)

```
$ DATABASE_URL=<staging> python scripts/agent_v2/verify_rag_corpus_identity.py
{"status": "PASS", "corpus_version": "legacy-drug-chunks-openai-v1", "drug_chunks_rows": 14423, "mismatches": []}
```

| Requirement | Result |
| --- | --- |
| 14,423 chunks | 14,423 rows, 14,423 distinct `chunk_key` — PASS |
| 1,536 dimensions | 0 rows with any other `vector_dims(embedding)` — PASS |
| `text-embedding-3-small` | matches — PASS |
| manifest/hash/index identity | `chunk_manifest_hash`/`source_manifest_hash`/`index_version` all match the pinned BUILD-7D manifest — PASS |
| 0 duplicate | confirmed (14,423 = 14,423) — PASS |
| 0 outstanding embedding reservation | `rag_embedding_reservation` has exactly 1 row, status `HISTORICAL_RECONCILED`, 0 `RESERVED`/`RESPONSE_RECORDED`/`UNRESOLVED` — PASS |
| pgvector HNSW cosine index | `ix_drug_chunks_embedding_hnsw ... USING hnsw (embedding vector_cosine_ops)` present — PASS |

No mismatch occurred, so the "Mismatch → STOP" gate was never triggered.
CORPUS IDENTITY: **PASS**.

### An additional, undocumented dependency discovered mid-build

Seeding synthetic prescription data (step 8) initially produced **0** V2
dose occurrences despite the prescription being created and "approved"
successfully. Root cause: `backend.services.scheduling.write_path._identity()`
resolves `drug_product_id` through the `drug_id_map`/`drug_product` tables —
DB Architecture V2's *operational* reference tables, documented in
`backend/db/models.py::DrugProduct` as "DB-4A creates the empty table only.
Drug V2 import/backfill happens later" — and no migration or committed
script loads them. The local dev database has 3,556 rows in each because
that import/backfill was run there directly at some earlier point, outside
this repo's committed history. This is **public canonical drug reference
data** (names, dosage forms, routes, ingredients), not patient/clinical
data, so restoring it to staging does not violate any of this build's
constraints — but it was undocumented in BUILD-17's plan and had to be
discovered and restored the same way, with a second new script:

```
$ python scripts/agent_v2/restore_canonical_v2_catalog_tables.py --source-url <local> --target-url <staging>
RESTORED: drug_product rows=3556
RESTORED: drug_id_map rows=3556
RESTORED: drug_product_ingredient rows=5287
```

This is recorded here for whoever provisions the next staging/production
Postgres from scratch: **the Canonical Drug V2 catalog tables need this same
restore step, or every V2 prescription item stays `REVIEW_REQUIRED` with
zero dose occurrences generated, independent of and in addition to the RAG
corpus restore.**

## 5–6. Infrastructure smoke / model connectivity

| Check | Result |
| --- | --- |
| DB connectivity | PASS (`alembic current` succeeded over the temp proxy) |
| pgvector | PASS (extension `0.8.6`, HNSW index present, confirmed above) |
| Corpus identity | PASS (above) |
| Retrieval | PASS at the component level (direct query against the restored corpus); see §7 for the live HTTP RAG scenario result |
| Vinmec Web connectivity | **FAIL — see §7, a real defect, not a staging config issue** |
| Safety | **FAIL — see §7, a real defect, not a staging config issue** |
| Doctor Handoff persistence | **FAIL — see §7, a real defect, not a staging config issue** |
| Checkpoint persistence | **FAIL — see §7, a real defect, not a staging config issue** |
| Observability/redaction | PASS for what does log (structured HTTP edge logs contain no prompt/PII, only method/path/status/duration/ids); see §7 for a related gap |

Model connectivity smoke (`scripts/agent_v2/smoke_model_gateway.py`), run
**exactly once**, using the exact key values now configured on staging:

```json
[
 {"role":"router","model":"gpt-5.4-nano","passed":true,"latency_ms":3481.53,"input_tokens":35,"output_tokens":16},
 {"role":"main","model":"gpt-5.4-mini","passed":true,"latency_ms":1213.50,"input_tokens":63,"output_tokens":23},
 {"role":"fallback","model":"gpt-5.4","passed":true,"latency_ms":1394.68,"input_tokens":13,"output_tokens":5},
 {"role":"embedding","model":"text-embedding-3-small","passed":true,"latency_ms":3105.38,"input_tokens":5},
 {"role":"judge","model":"gpt-4o","passed":true,"latency_ms":1767.34,"input_tokens":14,"output_tokens":2}
]
```

All 5 roles passed. Total: 130 input + 46 output tokens. `AGENT_MODEL_PRICING_JSON`
was intentionally left at its default `{}` on staging (per BUILD-17's
documented "unknown price → `None`, never fabricated `$0`" behavior), so no
per-model dollar figure is fabricated here either; at any publicly documented
rate for these five small, cheap models, 176 total tokens costs **well under
US$0.01**. MODEL CONNECTIVITY: **PASS**.

## 7. Flag flip and live HTTP E2E (staging only)

```
railway variable set "AGENT_RUNTIME_ENABLED=true" --service BE --environment staging --skip-deploys
railway variable set "AGENT_VINMEC_WEB_ENABLED=true" --service BE --environment staging   # triggers redeploy
```

Confirmed live: `POST /agent/v2/orchestrate` moved from `404` to `401`
(auth required, not "feature disabled"). Production's `AGENT_RUNTIME_ENABLED`
was re-verified unchanged immediately after.

Synthetic staging test data (`scripts/agent_v2/seed_staging_agent_v2_data.py`,
fixed `agent-v2-staging-*` ids only, no PHI): one doctor account/`doctor_id`,
one caregiver account with a `CaregiverLink` to `agent-v2-staging-patient-1`
only, two patients (`-1` linked, `-2` deliberately unlinked for the
cross-patient scenario), one approved prescription for `-1`
(`paracetamol-kabi-1000mg-frensenius-kabi-48-chai-x-100ml`, the same product
BUILD-7D's own real retrieval smoke used), 6 generated V2 dose occurrences.

Live HTTP results (`scripts/agent_v2/live_e2e_smoke.py` against
`https://be-staging-0111.up.railway.app`):

| # | Scenario | Result |
| - | --- | --- |
| 1 | Normal drug-information query | **PASS** — `COMPLETED`, `search_drug` called |
| 2 | RAG query | **PASS** — `COMPLETED`, 0 citations (legitimate `NO_RESULTS`: the phrasing "tác dụng phụ của thuốc giảm đau" did not lexically/semantically match a specific product in the corpus; the orchestrator's fail-closed rule only trips on `UNAVAILABLE`, not on a genuine empty result, so this is the intended "no evidence → no fabricated answer" behavior, not a defect) |
| 3 | Patient dose query | **PASS** — `COMPLETED`, `get_today_doses`+`get_active_prescriptions` called, real V2 dose data returned |
| 4 | Vinmec Web | **FAIL — real defect, see below** |
| 5 | Safety SAFE | **FAIL — real defect, see below** |
| 6 | SAFETY_BLOCKED | **PASS, incidentally** — the defect in #5 makes Safety Domain calls raise, which `SafetyGateway.evaluate()` correctly catches and converts to `SAFETY_BLOCKED` rather than crashing, hanging, or guessing. The *fail-closed mechanism* is proven; the *intended trigger* (a real Safety Domain timeout/outage) was not what produced it here |
| 7 | HANDOFF_CREATED | **PASS at the HTTP-response level, FAIL for durability — see below** |
| 8 | Cross-patient denial | **PASS** — `403 {"detail":"Khong co quyen truy cap du lieu benh nhan"}` for the caregiver requesting the unlinked patient |
| 9 | Timeout/budget failure | **PASS** — with `AGENT_TOKEN_BUDGET=10`/`AGENT_CONTEXT_TOKEN_BUDGET=5`/`AGENT_OUTPUT_TOKEN_RESERVE=5` set staging-only, the same drug-info request returned `{"status":"BUDGET_EXCEEDED","reply":"Agent run vuot gioi han token."}` — a safe, non-fabricated response. Reverted immediately after |

### Defect 1 — Vinmec Web: one non-content redirect crashes the whole search, not just that link

```
$ python -c "VinmecWebSearchService().search(query='benh tieu duong', ...)"
VinmecWebError: VINMEC_REDIRECT_REJECTED
```

Reproduced deterministically for 3/3 different queries. Root cause,
precisely isolated: `vinmec.com`'s real site currently serves `302` for
several `/vie/chuyen-khoa/<slug>/` links (e.g.
`.../chuyen-khoa/trung-tam-tim-mach/`) that appear as standing
navigation/menu links on every search-results page, not as genuine article
results. `VinmecWebSearchService._is_content_path()`
(`backend/services/vinmec_web_search.py`) treats any `/chuyen-khoa/` path as
content, and `search()`'s per-link loop wraps only `normalize_vinmec_url()`
in a `try/except VinmecWebError` — the subsequent `self._request(url, ...)`
fetch is **not** wrapped, so the first redirecting nav link aborts the
entire search instead of being skipped in favor of the next candidate link.
This is a live-network-only finding: BUILD-8's own tests use synthetic HTML
fixtures that never exercise a real redirect, and BUILD-16's orchestrator
tests use a fully faked `VinmecSearchDomain`. **Not patched here** (see
"What was deliberately not fixed" below). VINMEC WEB: **FAIL**.

### Defect 2 — Safety: the Tool Gateway's dose id is not the id Safety Domain expects

```
$ SafetyDomainAdapter(db).assess(occurrence_id='c08086a5-...', ...)
DoseSafetyOccurrenceNotFoundError: Không tìm thấy liều V2.
```

Root cause, precisely isolated: `backend.services.scheduling.runtime_adapter.DoseRuntimeGroup`
has both a synthetic `id` (a `uuid5` hash of prescription+date+time+timezone
— **not** a real database row) and a separate `occurrence_ids: tuple[str, ...]`
field holding the real, per-item `DoseOccurrence.id` values that
`backend.services.safety_policy_domain.service.assess_dose_safety` actually
needs. The Agent V2 tool schema (`backend/agents/v2/tools.py::DoseToolItem`)
only exposes `id`/`prescription_id`/`scheduled_at`/`window_start`/
`window_end`/`status`/`expected_items` — **`occurrence_ids` is never
surfaced**. `AgentOrchestrator._resolve_occurrence()` (BUILD-16) calls
`get_dose_status` and reads its `id` field, which is always the synthetic
group id, never a real occurrence id — so every `MISSED_DOSE`/`DELAYED_DOSE`
safety-relevant request is structurally unable to resolve a real occurrence
for Safety Domain to assess. This was invisible to BUILD-9's and BUILD-16's
own test suites because both use fakes where a "dose id" is just an opaque
string the fake domain echoes back, never exercising the real group/occurrence
split. **Not patched here.** SAFETY: **FAIL** for the intended SAFE-path
demonstration (the fail-closed *mechanism* itself is proven correct, see
scenario 6).

### Defect 3 (most severe) — the orchestrate route never commits its database session

Every write-path scenario above (7, and by extension checkpoint recording
for 3/5/9 too) returned an HTTP response that looked completely correct —
including a real, well-formed `handoff_id`. Direct inspection of the staging
database after the full E2E run told a different story:

```
$ select count(*) from agent_run;                 -- 0
$ select count(*) from agent_run_checkpoint;       -- 0
$ select count(*) from doctor_review_request;      -- 0
```

**Zero rows in all three tables**, despite scenario 7 (run twice) returning
two different, real-looking `handoff_id`s
(`910de8c2-b727-5826-b9d3-78eee687457f` then `9d90b3d0-b7a0-5407-8b99-54057c0be8dd`).

Root cause, precisely isolated: `backend/api/agent_v2_routes.py::run_agent_orchestration`
passes the FastAPI-injected `db: Session` straight to
`orchestrator.run(..., checkpoint_db=db)`, but **never calls `db.commit()`**
— confirmed by `grep -n "commit" backend/api/agent_v2_routes.py` returning
no matches. `backend/db/base.py::get_db()`'s `finally: db.close()` is the
only thing that ever touches the session's lifecycle afterward, and
SQLAlchemy's documented behavior for closing a session with a pending
transaction is to roll it back. `backend/services/agent_checkpoint.py` and
`backend/services/doctor_handoff.py` use `db.flush()`/`db.begin_nested()`
(savepoints) *by design* — their own docstrings say "the caller owns the
surrounding transaction; no adapter commits by itself" — so this was always
the route's responsibility, matching the pattern already used elsewhere in
this codebase (`backend/services/prescription/service.py::tao_phac_do`/
`duyet_phac_do` each call `db.commit()` themselves). BUILD-16 simply never
added that call to the new route.

Because `db.flush()` makes writes visible *within the same transaction*,
everything looks correct to the single request that made them (the
in-memory checkpoint/handoff objects the response is built from are real and
internally consistent) — the failure is only visible **across** requests,
which is exactly why BUILD-16's own tests (constructing one
in-process SQLite session per test and asserting against that same session)
never caught it, and why the live HTTP round-trip through a real Postgres
did. Concretely, this means:

- no checkpoint ever survives a request, so **crash-resume is a no-op** — a
  real crash mid-run would restart from nothing, not from the last
  checkpoint;
- the Doctor Handoff idempotency guarantee BUILD-12 built and BUILD-16
  wired up **does not hold at the deployed route** — two genuinely identical
  retried HTTP requests would each create a *separate* real
  `doctor_review_request` row once committed correctly, because the
  idempotency check only looks at already-committed rows and finds none;
- no `agent_run`/`agent_run_checkpoint`/`doctor_review_request` audit trail
  is durable, which also means the Observability/redaction gate cannot be
  fully evaluated against durable storage (only against the edge HTTP logs
  and this build's live process inspection).

CHECKPOINT: **FAIL**. DOCTOR HANDOFF: **FAIL** (the HTTP contract works;
the durability/no-duplicate guarantee it depends on does not, at the
deployed route).

### What was deliberately not fixed, and why

The task requires: "Không thay đổi architecture/corpus/evaluation để làm
deployment PASS" and "Nếu gặp blocker → STOP và report, không workaround."
All three defects above are real, precisely isolated, narrowly-scoped code
issues — not corpus or evaluation changes, and a fix for defect 3 is a
well-understood one-line addition. They were **not patched in this build**
because:

1. the task explicitly instructs stopping and reporting a blocker rather
   than working around it;
2. the same agent producing this deployment's pass/fail grade should not
   also be the one silently patching the exact thing standing between a
   FAIL and a PASS — that decision belongs to a human reviewing this report;
3. none of the three fixes is safe to apply blind against a live-network
   dependency (Vinmec) or a clinical-safety code path (occurrence
   resolution) without its own review and tests.

## 8. Synthetic staging test data

Confirmed: only `agent-v2-staging-*` fixed ids, generated by this build's
own seed script, described in full in §7. No import from any production
source, no real patient/user data anywhere on staging.

## 9. Provenance / additional verification

- Citations/provenance: proven working for the RAG *code path* at the
  component level (BUILD-16 test suite, unchanged); the live RAG scenario
  returned a legitimate empty result rather than a fabricated one (§7,
  scenario 2). Vinmec citations could not be exercised live due to defect 1.
- No duplicate handoff: **not proven** live — defect 3 means the guarantee
  this checks does not currently hold at the deployed route (§7, defect 3).
- Checkpoint persistence: **disproven** live — 0 rows despite multiple
  write-producing requests (§7, defect 3).
- No raw PII/PHI/prompt/secret in logs: the only logs this session could
  read (Railway edge HTTP logs) contain method/path/status/duration/ids
  only — no prompt or patient content, consistent with BUILD-13's design.
  Whether `AgentTelemetry`'s own structured events reach a durable sink on
  Railway could not be confirmed (no matching log lines were found for the
  `agent_run.*`/`agent_span.*` event names BUILD-13 defines, which is
  itself worth a human follow-up, though it does not indicate a leak — the
  absence is more consistent with `AgentTelemetry`'s `StructuredLogSink`
  logger not being wired into Railway's captured stdout/stderr filter than
  with sensitive data being logged).

## 10. Rollback test

```
railway variable set "AGENT_RUNTIME_ENABLED=false" --service BE --environment staging
# redeploy completed automatically
$ curl -X POST https://be-staging-0111.up.railway.app/api/v1/agent/v2/orchestrate ...
HTTP 404
```

Confirmed. ROLLBACK TEST: **PASS**. Staging was left in this OFF state.

## Final state left behind

- Railway `staging` environment exists with `BE` (`AGENT_RUNTIME_ENABLED=false`,
  `AGENT_VINMEC_WEB_ENABLED=true` — left as configured; harmless while the
  runtime flag is off) and `Postgres-_hCI` (the restored corpus + catalog +
  synthetic test data only).
- The temporary public TCP proxy used to verify migrations/corpus/checkpoint
  state from this local session was deleted immediately after use.
- Production: unchanged, re-verified as the literal last infrastructure
  action of this build.

## New scripts added (all additive; no existing file was changed)

- `scripts/agent_v2/restore_rag_corpus_tables.py`
- `scripts/agent_v2/restore_canonical_v2_catalog_tables.py`
- `scripts/agent_v2/seed_staging_agent_v2_data.py`
- `scripts/agent_v2/live_e2e_smoke.py`

## Regression

```
python -m pytest tests/ -k "agent_v2 or rag_corpus_identity" -q
151 passed, 2 skipped
```

Unchanged from BUILD-17 — this build added no test-affecting code changes
to `backend/`, only new ops scripts and this report.

## Result

BUILD-18: **FAIL**

STAGING ENVIRONMENT: PASS

STAGING POSTGRES: PASS

PRODUCTION ISOLATION: PASS

MIGRATIONS: PASS

CORPUS RESTORE: PASS

CORPUS IDENTITY: PASS

MODEL CONNECTIVITY: PASS

RAG: PASS

VINMEC WEB: FAIL (defect 1 — real, live-network-only defect, see §7)

SAFETY: FAIL (defect 2 — real occurrence-id plumbing defect, see §7; the fail-closed mechanism itself is proven correct)

DOCTOR HANDOFF: FAIL (defect 3 — real missing-commit defect, see §7; the HTTP contract is correct, durability/no-duplicate is not)

CHECKPOINT: FAIL (defect 3, same root cause)

OBSERVABILITY/REDACTION: PASS for what could be verified (no PII/PHI/prompt/secret in the logs this session could read); durable structured-event delivery could not be confirmed and is flagged for human follow-up

LIVE E2E: FAIL (6/9 scenarios fully correct: 1, 2, 3, 6, 8, 9; 3 blocked by the defects above: 4, 5, 7's durability half)

ROLLBACK TEST: PASS

NEW EMBEDDING CALLS: 0

STAGING OPENAI COST: 130 input + 46 output tokens across 5 one-time model-gateway smoke calls (well under US$0.01 at any publicly documented rate for these models); no per-model dollar figure is fabricated because `AGENT_MODEL_PRICING_JSON` is intentionally unset on staging, matching BUILD-17's documented "unknown price → `None`, never `$0`" behavior

PRODUCTION CHANGED: NO

READY FOR STAGING USER TESTING: NO — fix the three reported defects (all
narrowly scoped: an unwrapped per-link exception in
`backend/services/vinmec_web_search.py`, a missing `occurrence_ids` field on
the Agent V2 dose-status tool output plus its consumer in
`backend/agents/v2/orchestrator.py`, and one missing `db.commit()` in
`backend/api/agent_v2_routes.py::run_agent_orchestration`), then re-run this
same staging environment's smoke suite (no new provisioning needed) before
inviting any human tester.

READY FOR PRODUCTION: NO
