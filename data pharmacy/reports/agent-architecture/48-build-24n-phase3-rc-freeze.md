# BUILD-24N — Phase 3: V2 Release Candidate Freeze

**Scope:** freeze the current, gate-clean code as the V2 Release Candidate
(RC1), per the user's own Phase 3 instruction: record commit/hash/config/
model versions; no code changes during the benchmark from this point.
Local-only, no Railway deploy this build — this is a documentation/tagging
step, not a code change.

---

## 1. What's frozen

```
Git tag:        agent-v2-rc1 (annotated)
Commit hash:    739307eef881de59c11ac556cab45efc19b7bfb4
Commit subject: "Agent V2: BUILD-24M - Phase 2 closure, release gate clean (local only)"
Branch:         feature/agent-architecture-v2
Tagged:         2026-08-21
```

This commit contains the full, isolated BUILD-24D → 24M fix history (each
build its own commit, per the standing "isolate every fix" instruction):
`a8d8bc1` (24D+24E), `8c9f142` (24F), `b6b4cce` (24G), `f1cc74a` (24H),
`9da435c` (24I), `072a8cb` (24K), `22d942d` (24J, Phase 2 harness+results),
`268475e` (24L), `739307e` (24M, final gate-clean results) — 9 commits.

## 2. Working-tree completeness — stated honestly, not glossed over

Consistent with every prior build in this project (`railway up` deploys
the local working tree directly, never a git ref — see memory
`railway-deploy-no-ci`), the git tag above captures **Agent V2's own
incremental fix history**, not a from-scratch clean checkout of the entire
backend. The following remain outside git history at freeze time, exactly
as they have been since BUILD-1 (this build did not attempt to
retroactively commit them, for two reasons: (a) several are pre-existing
modifications to shared files this session did not create and cannot
verify are complete/non-conflicting — per memory `concurrent-team-deploys`,
other teammates/agents work on the same services concurrently — and
committing them presumptuously on this build's own authority would be the
wrong call; (b) `backend/agents/v2/*`'s own supporting modules
(`checkpoint.py`, `context.py`, `handoff.py`, `safety.py`, `tools.py`,
`vinmec_web.py`, etc.), `backend/services/agent_*.py`, and migrations
0030–0034 are BUILD-1 through BUILD-24C's foundational work, entirely
untouched by this fix cycle, and retroactively splitting 24 builds' worth
of already-shipped, already-live-verified code into new isolated commits
now would manufacture a false sense of granularity this build has no way
to make accurate):

- Untracked: `backend/agents/v2/{__init__,authorization,checkpoint,context,deepeval_judge,handoff,long_term_memory,observability,rag_evaluation,retrieval,retrieval_eval,safety,short_term_memory,tools,vinmec_web}.py`, `backend/api/agent_v2_routes.py`, `backend/services/agent_{authorization,checkpoint,doctor_handoff,idempotency,read_only_tools,retrieval,safety}.py`, `backend/services/{doctor_handoff,rag_corpus_recovery,vinmec_web_search}.py`, `backend/services/safety_policy_domain/review_workflow.py`, `migrations/versions/003{0,1,2,3,4}_*.py`, `scripts/agent_v2/*.py` (except this build's own `local_golden_retest.py`, already committed in `22d942d`), the full `tests/test_agent_v2_*.py`/`tests/test_rag_corpus_*.py` suite (except the files this fix cycle's own commits already added), and reports `01`–`35`.
- Modified-but-uncommitted (pre-existing since before this session started, not created by this build): `.env.example`, `.gitattributes`, `backend/config.py`, `backend/db/models.py`, `backend/egress_allowlist.py`, `backend/main.py`, `backend/models/schemas.py`, `backend/services/retrieval.py`, `backend/services/safety_policy_domain/errors.py`, `backend/services/scheduling/runtime_adapter.py`, `requirements.txt`, `tests/test_retrieval_sql.py`, and the RAG corpus data files (`data pharmacy/v2/final_canonical/rag/v2_{chunks,embedding_index}.jsonl`).

**What this means in practice:** the RC, as actually deployable, is
"checkout `agent-v2-rc1`, then apply the current working tree's remaining
untracked/modified files on top" — exactly the same deploy shape every
prior build (BUILD-1 through 24M) has used and been live-verified under.
Phase 4's Railway deploy will `railway up` the working tree at deploy time
(picking up this build's own fix commits plus everything above), not a
bare `git checkout agent-v2-rc1`. This is stated explicitly here so a
future reader does not assume `agent-v2-rc1` alone is sufficient to
reproduce the tested system.

## 3. Config / model versions actually exercised by Phase 2's testing

Read from `backend/config.py`'s own defaults (no environment override was
set locally for any of these during Phase 2's testing, confirmed by
checking `.env` directly):

```
agent_router_model:    gpt-5.4-nano
agent_main_model:      gpt-5.4-mini
agent_fallback_model:  gpt-5.4
agent_embedding_model: text-embedding-3-small
rag_judge_model:       gpt-4o (not exercised this cycle -- RAG-judge evaluation is a separate, already-closed-out BUILD-14/15 concern)
```

Local test environment:

```
Python:            3.14.6
openai SDK:         2.53.0
Postgres:            pgvector/pgvector:pg16 (Docker)
Alembic migration:   0034 (head)
Canonical catalog:   3,556 drug_product rows
RAG corpus:          14,423 drug_chunks rows
```

Production's own current state (reconfirmed unchanged, not part of this
freeze — production still runs BUILD-24D only):

```
AGENT_RUNTIME_ENABLED:      true
AGENT_ROLLOUT_PERCENTAGE:   5
AGENT_CANARY_ALLOWLIST:     agent-v2-canary-patient1-account,agent-v2-canary-doctor-account,agent-v2-canary-patient3-account,agent-v2-canary-patient4-account,agent-v2-canary-doctor2-account
```

## 4. Gate status carried forward from BUILD-24M (report 47), unchanged

```
PASS: 64/101 (63.4%)
FAIL_SCOPE: 37
FAIL_DEFECT: 0
CRITICAL: 0
Release gate: CLEAN (all 6 criteria MET)
```

No code was changed to produce this freeze — BUILD-24N is a
documentation/tagging step only. Local regression suite unchanged from
BUILD-24M: 416 passed, 3 skipped (pre-existing local-Postgres gap), 0
failed.

---

## 5. What Phase 4 needs, stated for whoever picks this up

1. Confirm the Railway/Google Cloud incident that blocked BUILD-24E's
   original deploy attempt has cleared (`status.railway.com`) and API
   quota is available.
2. `railway up --service "VMEC-04/BE" --environment production -c` from
   this exact working tree (do not `git checkout agent-v2-rc1` into a bare
   worktree and deploy that — see §2, it would be missing the untracked/
   modified supporting files this RC actually depends on to run).
3. Verify the deploy actually landed — the CLI can hang silently even
   after success (see memory `railway-deploy-no-ci`); check
   `railway logs -b <deployment-id>` and `railway status --json`, then a
   live `/health` curl.
4. Reconfirm `AGENT_ROLLOUT_PERCENTAGE=5` unchanged (the user's own Phase
   4 instruction: golden-test accounts go through Agent V2 via the
   existing canary allowlist mechanism, not by raising the real-user
   rollout percentage).
5. Re-run all 101 golden queries **live against Railway** (a new script in
   the shape of `scripts/agent_v2/live_e2e_smoke.py`, hitting
   `/api/v1/agent/v2/orchestrate` over HTTPS with a real canary-account
   JWT — not the local in-process harness this Phase 2 used). Collect
   PASS/FAIL, P50/P95/P99, cost/query, Safety/Handoff/Auth/Grounding/
   Provenance, exactly as BUILD-24C's own report 35 did the first time.
6. No code changes during that benchmark run, per the user's own
   instruction ("Không patch giữa benchmark").
7. Phase 5 cutover decision based on that result.

---

## Closeout

```
V2 RC READY: YES (confirmed, this is the freeze)
RC TAG: agent-v2-rc1
RC COMMIT: 739307eef881de59c11ac556cab45efc19b7bfb4
LOCAL GOLDEN RESULT (carried forward, unchanged): PASS 64/101, FAIL_SCOPE 37, FAIL_DEFECT 0, CRITICAL 0
RELEASE GATE: CLEAN
CODE CHANGES THIS BUILD: 0 (documentation/tagging only)
5% ROLLOUT: unchanged, not touched by this build (local-only, no deploy)
NEXT: Phase 4 -- single Railway deploy of this RC + live 101-query validation (not yet started; blocked on Railway/API-quota availability, see §5)
```
