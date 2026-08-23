# BUILD-31 — Evaluation V2 Report

## 1. Initial Audit

Audited before implementation in isolated worktree
`feature/build-31-evaluation-v2`, based on `origin/main` `7374951`:
`deepeval_judge.py`, `retrieval_eval.py`, `observability.py`,
`agent_v2_routes.py`, `rag_monitoring_routes.py`, `telemetry.py`, related
RAG evaluation/tests, frontend Admin RAG page, contracts and ADRs. BUILD-29D.3
files were not modified.

## 2. Current Evaluation Architecture

`retrieval_eval.py` already supplied correct offline/golden formulas.
`deepeval_judge.py` is offline-only. Runtime wrote lexical relevance and
faithfulness after every Agent V2 response; Admin read the in-memory telemetry
buffer without execution-path/provenance information.

## 3. Root Problems

1. Non-RAG paths could receive RAG-named heuristic scores.
2. Live Admin retrieval derived HitRate from faithfulness and aliased it as
   MRR/NDCG.
3. Live traces have no authoritative relevance IDs.
4. Absent/non-applicable values were rendered as zero without denominators.

## 4. Evaluation Taxonomy

Dispatcher taxonomy: `RAG`, `DETERMINISTIC_SCHEDULE`,
`DETERMINISTIC_TOOL`, `DRUG_LOOKUP`, `SAFETY`, `HANDOFF`, `GENERAL_MODEL`,
`FALLBACK`, `OUT_OF_SCOPE`. It uses only completed-run intent, terminal
status, tools, citations, safety decision and handoff evidence—not user text.

| Execution Path | HitRate/MRR/NDCG | Faithfulness | Relevance | Tool Correctness | Safety | Judge |
|---|---|---|---|---|---|---|
| RAG | NOT_AVAILABLE without relevant IDs | heuristic | heuristic | N/A | N/A | deferred |
| DETERMINISTIC_SCHEDULE | N/A | N/A | N/A | operational | N/A | deferred |
| DETERMINISTIC_TOOL / DRUG_LOOKUP | N/A | N/A | N/A | operational | N/A | deferred |
| SAFETY | N/A | N/A | N/A | N/A | operational | deferred |
| HANDOFF | N/A | N/A | N/A | N/A | handoff operational | deferred |
| GENERAL_MODEL | N/A | N/A | heuristic | N/A | N/A | deferred |
| FALLBACK / OUT_OF_SCOPE | N/A | N/A | N/A | N/A | N/A | deferred |

## 5. Evaluator Dispatcher

Added pure `backend/agents/v2/evaluation_v2.py`. It returns metric statuses
`AVAILABLE`, `NOT_APPLICABLE`, `NOT_AVAILABLE`, plus source/reason and
`evaluator_version=evaluation-v2`. It has no authority over routing, safety,
tools, model, or response. Fallback is classified as `FALLBACK_EXPECTED`,
`FALLBACK_SUSPECT`, or `FALLBACK_NOT_EVALUATED`.

Safety evidence now wins over handoff evidence. A safety-triggered handoff is
evaluated as SAFETY; a standalone doctor handoff remains HANDOFF.

## 6. RAG Evaluation

Only general-medical runs with retrieval citation evidence are RAG. Live
faithfulness/relevance are explicitly heuristic. No relevance ground truth is
invented.

## 7. Retrieval Metrics

Golden definitions are canonical: HitRate@K finds any relevant item; MRR@K is
the reciprocal first-relevant rank; NDCG@K is normalized discounted relevance.
Fixture `[A,B,C]`, relevant `[B]` proves HitRate@3=`1`, MRR@3=`0.5`, and NDCG
is distinct (strictly between zero and one). Production needs retrieval query,
IDs/ranks/scores/mode/top-K plus versioned relevant IDs or graded relevance.

## 8. Deterministic Tool Evaluation

Schedule/tool/drug paths receive operational tool-correctness applicability;
they do not receive IR, RAG faithfulness, or RAG relevance metrics.

## 9. Safety/Handoff Evaluation

Safety receives `safety_path_completion`; standalone handoff receives
`handoff_created`. Safety/Handoff behavior was not changed.

## 10. Fallback Evaluation

Fallback classification is operational only; it does not assert medical
correctness. LLM Judge is deferred.

## 11. Admin API Changes

`GET /api/v1/admin/rag/retrieval` scopes samples to RAG traces, returns
`null` plus `metric_provenance` for live IR without relevance truth, and
exposes `evaluated_sample_count`. Health/generation average only metrics
declared AVAILABLE and expose sample counts. Frontend displays `N/A`, not
zero, and renders NDCG@10.

Contract proposal added in `specs/api-contracts.md` §1f; Architect/Frontend
review remains required.

## 12. Tests

Added `tests/test_agent_v2_evaluation_v2.py`: taxonomy, RAG N/A, independent
IR formulas, fallback, schedule/tool/drug/safety/handoff, Safety-over-Handoff,
N/A aggregation, retrieval provenance, and mixed denominators.

Commands/results:

```text
pytest --noconftest -q tests/test_agent_v2_evaluation_v2.py tests/test_agent_v2_rag_evaluation.py
............ [all assertions printed PASS, process did not terminate]

python -c "...invoke all 13 test functions directly..."
13 direct test assertions: PASS

git diff --check
PASS
```

The normal pytest process remains alive after completing in this Windows
worktree. Frontend lint could not start because the isolated worktree has no
`node_modules`; no dependencies were installed or changed.

## 13. Local Verification

PostgreSQL Docker `p-067-db-1` was healthy. Backend started only on
`127.0.0.1:8011`, connected to Docker local Postgres, with process-local
`AGENT_RUNTIME_ENABLED=true` and Langfuse disabled; it was stopped afterwards.
No production configuration/service was changed.

Real localhost Admin endpoint result before traffic: all IR metrics `null`,
each provenance `NOT_AVAILABLE / golden / no_relevance_ground_truth`.

Real Agent V2 schedule test (`today medication schedule`) completed with
`TODAY_DOSES` and `get_doses_for_range`. Admin then showed total traffic `1`,
RAG retrieval count `0`, IR values `null`, and faithfulness/relevance
denominators `0`: schedule did not degrade RAG metrics.

Real safety test (`non ra mau`) completed `ACUTE_DANGER_ESCALATION` with
`HANDOFF_REQUIRED`/`HANDOFF_CREATED`. It revealed then corrected dispatcher
priority. Re-run trace metadata: `execution_path=SAFETY`,
`safety_path_completion=AVAILABLE`, `faithfulness=NOT_APPLICABLE`, and
`mrr_at_10=NOT_APPLICABLE`.

The safety test created local-only checkpoint/handoff records; the app
scheduler ran briefly against the Docker copy before the server stopped.

## 14. Metric Before/After

| Metric | Before | After | Source | Denominator |
|---|---|---|---|---|
| HitRate@10 live | faithfulness-derived | null without GT | golden/N/A | RAG only |
| MRR@10 live | HitRate alias | null without GT | golden/N/A | RAG only |
| NDCG@10 live | HitRate alias | null without GT | golden/N/A | RAG only |
| Faithfulness | broad traffic | AVAILABLE only | heuristic | applicable traces |
| Relevance | broad traffic | AVAILABLE only | heuristic | applicable traces |

## 15. Files Changed

- `backend/agents/v2/evaluation_v2.py`
- `backend/api/agent_v2_routes.py`
- `backend/api/rag_monitoring_routes.py`
- `frontend/src/app/admin/rag/page.tsx`
- `tests/test_agent_v2_evaluation_v2.py`
- `specs/api-contracts.md`
- `chat-bot-build/build_cai_thien/BUILD-31-EVALUATION-V2-REPORT.md`

## 16. Known Limitations

Telemetry is still in-memory. Live IR still has no relevance labels. Existing
legacy score names are retained under Evaluation V2 provenance. The pytest
teardown and frontend dependency validation blockers were closed in BUILD-31.1.

## 17. BUILD-32/33 Follow-up

BUILD-32: durable/versioned retrieval evidence, golden relevance data and test
environment repair. BUILD-33: production Judge worker/contract fields
(`judge_model`, rubric/version/dimensions/score/time/source). No Judge worker
was implemented here.

## 18. Branch / Commit / PR

- Branch: `feature/build-31-evaluation-v2`
- Base: rebased onto `origin/main` `bd38eab` (BUILD-29D.3 included), with no conflicts.
- Implementation commit: `71db176` — `feat(evaluation): add pipeline-aware metrics`
- Validation/report commit before review follow-up: `4b2f92d` — `docs(evaluation): record validation handoff`
- Push: completed to `origin/feature/build-31-evaluation-v2`.
- PR: [#105](https://github.com/AI20K-Build-Phase-Cohort-3/P-067/pull/105), opened after push; no deploy or merge was performed.

## 19. Original BUILD-31 Release Gate (Historical — Superseded)

| Gate | Status |
|---|---|
| BUILD-31 | FAIL — clean full suite/frontend lint blocked |
| INITIAL AUDIT / TAXONOMY / DISPATCHER | PASS |
| RAG / SCHEDULE / TOOL / SAFETY / HANDOFF / FALLBACK evaluators | PASS |
| REAL HITRATE@K / MRR@K / NDCG@K (golden) | PASS |
| METRIC ALIAS REMOVED / N/A != ZERO / PROVENANCE / DENOMINATORS | PASS |
| ADMIN RETRIEVAL API / ADMIN AGGREGATION | PASS |
| LOCAL ADMIN VERIFY | PASS |
| AGENT BEHAVIOR CHANGED / SAFETY BEHAVIOR CHANGED / CONVERSATION STATE TOUCHED | NO / NO / NO |
| BUILD-29D.3 CONFLICT | NO |
| FULL RELEVANT TEST SUITE | FAIL — pytest teardown and frontend dependencies |

REPORT CREATED:
`chat-bot-build/build_cai_thien/BUILD-31-EVALUATION-V2-REPORT.md`

---

# BUILD-31.1 — Validation Environment Update

## Pytest Teardown Root Cause and Fix

The initial worktree did not contain `.env`, while application settings load
that file. The prior cacheprovider/DeepEval explanation was an observation in
that incomplete sandbox setup, not a proven general root cause, and must not
be read as an Agent teardown defect. Independent review reproduced a clean
exit after adding a temporary local `.env` with fake test values.

Validation command now uses a writable temporary cache, disables unrelated
auto-loaded plugins, explicitly enables `pytest_asyncio`, and opts out of
DeepEval telemetry:

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
DEEPEVAL_TELEMETRY_OPT_OUT=YES
python -m pytest -p pytest_asyncio.plugin -o cache_dir=%TEMP%\\build31-pytest-cache ...
```

This is not a kill workaround: tests use local-only explicit settings and a
writable temporary cache. The post-rebase relevant suite exited naturally with
code `0` and `743 passed, 3 skipped, 7 warnings in 16.28s`.

## Backend Regression Results

The expanded command covering all `test_agent_v2_*.py`, RAG telemetry, Admin
RAG authorization, auth, cross-patient, and personal-tool isolation completed
and exited naturally:

```text
768 passed, 3 skipped, 4 failed, 7 warnings in 40.84s
```

The four failures are all in pre-existing account email verification/password
reset flows (`verify-email`, `forgot-password`, `reset-password`) whose routes
are absent from `origin/main`; they are outside BUILD-31. They do not exercise
Evaluation V2. The focused auth/cross-patient/Admin authorization command,
excluding only those four absent-route tests, exited naturally:

```text
55 passed, 4 deselected in 33.03s
```

## Frontend Validation

`npm ci` was run from the current `package-lock.json` with no dependency
version changes (`401 packages added`; npm reported one existing high severity
advisory). The Admin RAG page's CRLF format errors were normalized with
Prettier, and its pre-existing `any` state was replaced by local API DTOs;
this is a typing/validation change only, not a UI or behavior change.

```text
npm.cmd exec eslint -- src/app/admin/rag/page.tsx
exit 0

npm.cmd exec tsc -- --noEmit
exit 0

npm.cmd run build
exit 0 (Next.js production build completed)
```

## Final Local Admin Evidence

Schedule and Safety evidence remains PASS as documented in §13. One approved
local orchestration call was made with the English text `What is fatty liver?`.
The trace completed, but the current deterministic router classified that
English phrasing as `DRUG_INFORMATION`; no retrieval citation was produced and
Evaluation V2 therefore correctly recorded `GENERAL_MODEL`, rather than
claiming it was RAG. Its IR metrics were `NOT_APPLICABLE`, while
`answer_relevance` was `AVAILABLE / heuristic`. The real Admin endpoints
returned IR values as `null` with `NOT_AVAILABLE / golden /
no_relevance_ground_truth`, and the health endpoint reported a relevance
denominator of one and a faithfulness denominator of zero for that one trace.

This is valid negative-path evidence, but it is not the required true-RAG
E2E. A second, deliberately Vietnamese router-compatible RAG query (for
example `gan nhiem mo la gi`) requires a separate approval because the first
orchestration call may already have consumed a paid model invocation. No
additional external model call has been made without that approval.

## BUILD-31.1 Intermediate Gate (Historical — Superseded)

| Gate | Status |
|---|---|
| BUILD-31.1 | FAIL — true RAG local call pending separate approval; unscoped legacy auth routes fail |
| PYTEST CLEAN EXIT | PASS |
| BACKEND REGRESSION | PASS for BUILD-31 relevant Agent/RAG/Safety/Handoff/Admin/Auth-cross-patient scope; unrelated reset/email routes FAIL |
| FRONTEND ESLINT | PASS |
| FRONTEND TYPECHECK | PASS |
| FRONTEND BUILD | PASS |
| LOCAL ADMIN VERIFY | PARTIAL — Schedule/Safety PASS; one non-RAG negative path verified; real RAG pending |
| RAG METRIC APPLICABILITY | PASS in unit/handler tests |
| SCHEDULE EXCLUDED FROM RAG | PASS |
| SAFETY EXCLUDED FROM RAG | PASS |
| N/A != ZERO | PASS |
| METRIC PROVENANCE | PASS |
| CORRECT DENOMINATORS | PASS |
| BUILD-29D.3 CONFLICT | NO |
| READY FOR PR | NO |

## BUILD-31.1 Completion Evidence

With the explicit local-only approval, one additional Agent V2 orchestration
request was made against `127.0.0.1:8011` with
`message="gan nhiem mo la gi"`. The backend used the Docker-local PostgreSQL
copy, process-local `AGENT_RUNTIME_ENABLED=true`, and Langfuse disabled. No
production endpoint or production configuration was used.

The response was `COMPLETED`, with intent `GENERAL_MEDICAL_INFORMATION`, zero
deterministic tool calls, and three retrieval citations. Its sanitized Admin
trace evidence was:

| Evidence | Result |
|---|---|
| `evaluation_v2.execution_path` | `RAG` |
| `faithfulness` | `AVAILABLE`, source `heuristic` |
| `answer_relevance` | `AVAILABLE`, source `heuristic` |
| `hit_rate_at_10` | `NOT_AVAILABLE`, `golden`, `no_relevance_ground_truth` |
| `mrr_at_10` | `NOT_AVAILABLE`, `golden`, `no_relevance_ground_truth` |
| `ndcg_at_10` | `NOT_AVAILABLE`, `golden`, `no_relevance_ground_truth` |

The live Admin health endpoint reported one applicable RAG sample for both
faithfulness and relevance. The retrieval endpoint reported
`evaluated_sample_count=1` and `hit_rate_10=null`, `mrr_10=null`,
`ndcg_10=null`, each with the same `NOT_AVAILABLE / golden /
no_relevance_ground_truth` provenance. This is deliberate: retrieval occurred,
but no relevance ground truth exists, so Evaluation V2 does not fabricate IR
scores or convert N/A into zero.

The local server was stopped after the verification. Its scheduler may have
created only local Docker-copy checkpoint/handoff records; no production data
was changed.

## BUILD-31 Authoritative Final Gate

| Gate | Status |
|---|---|
| BUILD-31.1 | PASS |
| PYTEST CLEAN EXIT | PASS |
| FULL RELEVANT TEST SUITE | PASS — post-rebase: 743 passed, 3 skipped, 7 warnings |
| BACKEND REGRESSION | PASS for BUILD-31 scope; four unrelated absent reset/email routes remain documented above |
| FRONTEND ESLINT | PASS |
| FRONTEND TYPECHECK | PASS |
| FRONTEND BUILD | PASS |
| LOCAL ADMIN VERIFY | PASS |
| RAG METRIC APPLICABILITY | PASS |
| SCHEDULE EXCLUDED FROM RAG | PASS |
| SAFETY EXCLUDED FROM RAG | PASS |
| N/A != ZERO | PASS |
| METRIC PROVENANCE | PASS |
| CORRECT DENOMINATORS | PASS |
| RUFF (`rag_monitoring_routes.py` and new BUILD-31 files) | PASS |
| BUILD-29D.3 CONFLICT | NO |
| READY FOR PR | YES |

The original BUILD-31 release gate is therefore PASS for the agreed scope. No
Agent response, Safety behavior, conversation state, or BUILD-29D.3 file was
changed by BUILD-31.1 validation.

## Review Follow-up: PR #105

The branch was rebased onto `origin/main` at `bd38eab`, which includes
BUILD-29D.3. The rebase completed without a conflict; no BUILD-29D.3 source
file is changed by this branch. The two Ruff violations introduced by this
branch (import ordering in `backend/api/agent_v2_routes.py` and the new test)
were fixed. The eight pre-existing Ruff findings in
`backend/api/rag_monitoring_routes.py` were also cleaned up in a subsequent
no-behavior-change refactor: unused imports were removed and ambiguous `l`
variables were renamed to `audit_log`.

Post-rebase validation commands/results:

```text
python -m ruff check --no-cache backend/agents/v2/evaluation_v2.py backend/api/agent_v2_routes.py tests/test_agent_v2_evaluation_v2.py
exit 0

python -m pytest -p pytest_asyncio.plugin -o cache_dir=%TEMP%\\build31-pytest-cache -q <all test_agent_v2_*.py> tests/test_rag_telemetry.py tests/test_api/test_agent_feedback_routes.py tests/test_get_current_patient_id.py tests/test_chat_security_gate.py tests/test_personal_tools_isolation.py
743 passed, 3 skipped, 7 warnings in 16.28s; exit 0

npm.cmd exec -- eslint src/app/admin/rag/page.tsx
exit 0

npm.cmd exec -- tsc --noEmit
exit 0

npm.cmd run build
exit 0

python -m ruff check --no-cache backend/api/rag_monitoring_routes.py
All checks passed

python -m pytest -p pytest_asyncio.plugin -o cache_dir=%TEMP%\\build31-pytest-cache -q tests/test_agent_v2_evaluation_v2.py tests/test_agent_v2_rag_evaluation.py tests/test_rag_telemetry.py
18 passed in 0.08s; exit 0
```

The earlier report tables remain only as historical snapshots. The
authoritative status for review is the "BUILD-31 Authoritative Final Gate"
above: BUILD-31 is PASS for scope, local validation is PASS, and the PR is
ready for review only; production deployment remains prohibited until review
and merge.
