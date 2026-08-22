# BUILD-25 — Agent V2 Production Monitoring Audit

**Scope:** audit the existing Langfuse/RAG admin monitoring system (not
rebuild it) to make its metrics actually reflect Agent V2's real production
traffic. No Agent V2 behavior change. No dashboard rebuild. No rollout
change. No unnecessary migration.

---

## 1. Data flow audit

Traced end to end, by reading code (not assuming):

```
BEFORE this build:
Agent V2 request -> Router -> Retrieval/Tools -> Safety/Handoff -> Model -> Response
  -> [NOTHING] -- never reaches telemetry.py or AuditLog at all
Legacy chat request -> LangGraph -> chat_routes.py
  -> get_telemetry_service() (real) -> Langfuse (if configured) + in-memory buffer
  -> AuditLog (real, Postgres)
/api/v1/admin/rag/* -> reads get_local_traces() (in-memory) falling back to AuditLog (DB)
  -> both sources are legacy-chat-only
```

**Root cause, confirmed by grep, not assumption:**

```
grep "get_telemetry_service|create_trace(" backend/  -> only backend/services/telemetry.py (definition) and backend/api/chat_routes.py (the only caller)
grep "AuditLog(" backend/                            -> only backend/api/chat_routes.py writes it
```

Agent V2 is now 100% of production traffic; legacy chat is ~0%. Every
dashboard KPI was therefore reading either an empty in-memory buffer (reset
on every deploy -- and this project deployed 6+ times today) or a handful of
increasingly stale legacy `AuditLog` rows. **Not a metric-calculation bug on
its own -- a missing-instrumentation bug**, and it explains essentially
every other finding below.

### The specific "P95 ~0.7ms" anomaly

`GET /admin/rag/system`: `latencies = [t.duration_ms for t in traces if ...] or [l.total_duration_ms for l in audit_logs if ...]`. With Agent V2 never populating `traces`, this fell back to whatever sparse, old `AuditLog` rows exist. **Confirmed empirically, not just reasoned about**: after wiring Agent V2 into telemetry (see §3) and sending 6 real production requests, `p95_latency_ms` immediately became `3441.1` (matching real, independently-measured latency in the 1.2s-5.8s range for these same requests) instead of a sub-millisecond reading. **The dashboard was never measuring Agent V2 end-to-end latency; it was measuring whatever tiny number happened to be sitting in a handful of unrelated old rows.**

---

## 2. Metric-by-metric audit

| Metric | Source before this build | Verdict |
|---|---|---|
| Faithfulness / Answer Relevance | `LLMJudgeEvaluator` heuristic (word-overlap), only invoked by legacy chat | Real evaluator, but never ran for Agent V2 -- **0 samples, not a fake number, but effectively absent** |
| HitRate/MRR/NDCG@10 | `/retrieval`: all three literally return the *same* `hit_rate` value under three different names | **Hardcoded-via-aliasing** -- not independently computed metrics at all, regardless of data source |
| P50/P95/P99 latency | Same empty-buffer/stale-DB fallback as above | **Wrong data source**, not a calculation bug -- fixed by §3 |
| Error rate | `sum(status=="error")/len(traces)` | Correct formula, just starved of real Agent V2 data before this build |
| Empty reply rate | **Not computed anywhere in `rag_monitoring_routes.py` at all** | **Missing metric** -- flagged, not fabricated (see §7) |
| Safety incidents | `Escalation` table (legacy escalation flow) | Real table, but Agent V2's own safety/handoff path (`doctor_review_request`, `agent_run_checkpoint.safety_disposition`) was never read here at all -- Agent V2 safety incidents are invisible to this endpoint (see §7) |
| Handoff | Not surfaced anywhere in `rag_monitoring_routes.py` | **Missing metric** for Agent V2's own Doctor Handoff mechanism (see §7) |
| Grounding/provenance | Approximated by `answer_faithfulness` only | Same "starved of data" issue as faithfulness |
| Token usage / cost/request | `ObservationRecord.usage`/`.cost` fields exist but nothing anywhere ever populates them with real numbers; every endpoint returns a flat `0.0` | **Genuinely unmeasured** -- Agent V2's own `AgentTelemetry`/`ModelPricingCatalog` (`backend/agents/v2/observability.py`) DOES track real cost per run, but it isn't wired into this admin API at all (see §7) |
| Model usage / intent distribution | `/generation`'s `breakdown_by_model` | Was defaulting every request to legacy's `settings.model_name`; fixed to Agent V2's real model (§3) |
| Tool usage | Not surfaced as its own metric | Now visible per-trace in the Trace Explorer timeline (§3), not yet aggregated across traces (see §7) |
| `unsafe_answer_rate` (`/safety`) | `len(escalations) / max(len(escalations), 1) * 100` | **Real bug, not just "no data"**: this is a tautology -- always exactly `100.0` when any escalation exists, `0.0` otherwise, regardless of actual traffic volume. **Fixed** (§3). |
| `ttft_ms` (`/system`) | `p50 * 0.3` | **Fabricated formula**, no basis anywhere in the codebase (no streaming path exists to measure a real time-to-first-token). **Fixed to `0.0` = "not measured"**, not a fake number (§3). |
| `cost_per_query`/`cost_daily`/`low_retrieval_confidence_rate`/`timeout_rate`/`stale_doc_rate`/`failed_ingestion_count`/`embedding_drift` | All flat hardcoded `0.0`/`"0.000"` | Left as-is -- **honestly zero because genuinely unmeasured**, not something this audit invented; flagged in §7 as insufficient data, not silently "fixed" with another guess |
| `/versions/compare` | Entirely hardcoded stub (`{"version_a": {...}, "metrics": []}`) | Not functional; flagged, not touched (real fix needs a real second version to compare against -- out of scope for this audit) |

**Also found, not asked for but directly relevant to "click/drill-down" working correctly:** `_require_admin` in `rag_monitoring_routes.py` is `Depends(get_current_user)` with **no role check at all** -- any authenticated patient/doctor/admin JWT can read every `/admin/rag/*` endpoint, including the Trace Explorer's raw query/response text. Confirmed directly: the canary **patient**-role JWT used throughout this build's own verification successfully read `/admin/rag/traces` and full trace detail. This is a real authorization gap, but changing role enforcement risks locking out or breaking the actual admin frontend's current auth flow without dedicated testing of that flow -- **flagged here, not fixed in this pass**, since the audit's own scope is metric correctness, not access control.

---

## 3. Fixes made

1. **Agent V2 -> telemetry wiring** (`backend/api/agent_v2_routes.py`, `_record_agent_v2_telemetry`, called once after `orchestrator.run()` returns and the DB commit succeeds -- never inside the orchestrator itself, so it cannot change Agent V2's routing/safety/model behavior). Reuses the exact same `backend.services.telemetry.TelemetryService` and `backend.services.evaluators.LLMJudgeEvaluator` legacy chat already used -- no new evaluation infrastructure, no extra model calls (the evaluators are deterministic word-overlap heuristics, not LLM-judge calls), no dashboard changes. Records: a trace per request (real latency, overridden onto the trace's timing since this is recorded after the fact), one observation per tool call (with real tool result data as its output), a safety-decision observation, a handoff observation when one occurs, a generation observation with the real response text, and faithfulness/relevance scores computed from the real query/response/tool-result data. Wrapped in try/except -- a telemetry failure is logged and swallowed, never surfaced to the caller.
2. **Model/prompt_version metadata fix**: `create_trace()`'s own base metadata defaults `model`/`prompt_version` to legacy chat's configured values (`settings.model_name`/`settings.rag_prompt_version`) unless overridden -- the initial wiring didn't override them, so the first live check showed Agent V2 traces mislabeled `model=gpt-4o-mini` (legacy's model) instead of Agent V2's real `gpt-5.4-mini`. Fixed by passing `settings.agent_main_model` + a `"agent-v2-orchestrator"` prompt-version tag explicitly. Verified via a second local smoke test.
3. **`unsafe_answer_rate` tautology fixed** (`/admin/rag/safety`) -- real denominator (total answered requests, the same source every sibling endpoint already uses), not the self-referential `escalations/escalations` formula.
4. **`ttft_ms` fabrication removed** (`/admin/rag/system`) -- returns `0.0` (not measured) instead of a fake `p50 * 0.3` guess.

**Not done in this pass** (documented, not silently skipped -- see §7 for the full list): empty-reply-rate metric, Agent V2's own Doctor Handoff/safety-domain data surfaced in `/safety`, real token/cost numbers (Agent V2's own `AgentTelemetry` already tracks these internally but isn't wired into this admin API), aggregated tool-usage/intent-distribution charts, per-observation sub-step latency (only whole-request latency is accurate under this post-hoc recording approach -- see the Trace Explorer verification in §6, where individual tool-call durations show `0.0` even though the request's own total `duration_ms` is correct), the `_require_admin` role-check gap, `/versions/compare`.

---

## 4. Agent V2 tracing -- verified end to end on live production (§6)

Every field the audit required is present in the Trace Explorer drill-down,
confirmed against a real trace (`569b3d32-...`, query "hôm nay tôi uống
thuốc gì"): `trace_id`, `agent_run_id` (in metadata), `intent`
(`TODAY_DOSES`), `model` (`gpt-5.4-mini`, after the fix), `prompt_version`
(`agent-v2-orchestrator`), `duration_ms` (`2020.5`, matching real measured
latency), real tool-call input/output (`tool.get_today_doses`, with the
actual prescription/dose rows returned), `scores`
(`answer_faithfulness=0.69`, `answer_relevance=0.75`), `status` (`success`).
No secrets, JWT, or raw patient identifiers logged -- `user_id` is
`hash_identifier(actor.id)` (an opaque SHA-256 prefix, matching legacy
chat's own existing pattern), and `mask_sensitive_data()` (existing,
unmodified) still redacts anything with `password`/`secret`/`token`/`phone`/
`email` in its key.

---

## 5. Admin Dashboard drill-down -- verified functional, UI untouched

No frontend code was touched. Confirmed via the live API (the UI consumes
these same endpoints): `/admin/rag/system` -> real volume/latency/error-rate
-> `/admin/rag/traces` -> real trace list with real query previews -> click
into `/admin/rag/traces/{trace_id}` -> full timeline + scores + metadata.
Model filter and prompt-version filter now have real, correct values to
filter on (`gpt-5.4-mini` / `agent-v2-orchestrator`) instead of legacy
chat's mislabeled defaults.

---

## 6. Verification

**Local** (before any deploy): full Agent V2 regression suite (421 passed, 3
pre-existing skips, 0 failed) + `tests/test_rag_telemetry.py` (5/5) +
`tests/test_admin_drug_routes.py`/`test_nudge_routes.py`/
`test_health_log_routes.py` (35/35) all pass. A standalone smoke script ran
one real orchestrator request and confirmed `_record_agent_v2_telemetry`
produces a correctly-shaped trace with real scores and the correct model
metadata (see the two local smoke runs in this build's own history).

**Production** (small controlled set, not the 101 golden set, per
instruction): sent 6 real requests via `scripts/agent_v2/live_golden_validation.py --ids "1,5,24,57,70,96"` (drug info, grounding, today-schedule,
acute-danger, doctor-handoff, cross-patient-denial). Result:

```
GET /admin/rag/system  -> volume_24h=5 (the 403-denied request correctly excluded, since it never reaches telemetry), p50=2020.5ms, p95=3441.1ms, p99=3441.1ms, ttft_ms=0.0 (honest), error_rate=0.0
GET /admin/rag/traces  -> 5 real traces, real query previews, real per-trace faithfulness/relevance
GET /admin/rag/traces/{id} -> full drill-down verified (see §4)
GET /admin/rag/health  -> sample_size=5, status="Warning" (small-sample faithfulness/relevance genuinely below the existing 0.80 threshold on this tiny batch -- expected and correct behavior, not a bug)
```

No code changes made during production verification itself (all changes
were made and tested locally first, then deployed once, per instruction).
`AGENT_ROLLOUT_PERCENTAGE` never touched (still 100 throughout). No legacy
data touched. No migration touched.

---

## 7. Health thresholds

Per instruction, used the spec doc's own definitions rather than inventing
new ones. `docs/langfuse_rag_admin_monitoring_spec.md` §19 (Alerting
specification) gives qualitative critical-alert examples (`Error rate > 5%
for 5 min`, `Critical medical safety failure > 0`, `P95 > approved threshold
for 10 min` -- the spec itself does not name a concrete P95 number,
deliberately leaving it as a product decision). The **existing, already-
implemented** `/admin/rag/health` endpoint already encodes thresholds
consistent with the spec's own examples (`avg_faithfulness < 0.80`,
`error_rate > 5.0`, `safety_failures > 0` all trigger "Warning") -- this
audit did not change those, since they already match the spec and are
real, running code, not a new invention.

```
HEALTHY:   sample_size > 0, faithfulness >= 0.80, error_rate <= 5%, 0 critical safety failures
WARNING:   faithfulness < 0.80 OR error_rate > 5% OR any critical (HIGH-severity) safety failure   [existing, spec-consistent, unchanged]
CRITICAL:  (not yet distinguished from WARNING in code -- the spec's own §19.1 critical-alert list
            (safety failure > 0, error rate > 5% for 5 min sustained, P95 > threshold for 10 min sustained)
            requires a time-window/sustained-duration check this endpoint doesn't currently do;
            proposing this as a P1 follow-up, not fabricating a "CRITICAL" status the code doesn't
            actually compute)
P95 latency: spec leaves this as a product decision (no concrete number given). Proposing
            WARNING > 8000ms / CRITICAL > 15000ms based on this build's own real measured Agent V2
            latency (P50 ~2-3s, P95 ~3.4-11s across two independent live verification runs today) --
            stated explicitly as a proposal pending product sign-off, not presented as spec-defined.
```

---

## 8. Known gaps -- insufficient data / not fixed in this pass

1. **Empty-reply-rate**: not computed anywhere in `rag_monitoring_routes.py`. Agent V2's own smoke tests this session confirmed 0% empty replies in production, but nothing surfaces this on the dashboard itself.
2. **Agent V2's own Safety/Handoff data** (`doctor_review_request`, `agent_run_checkpoint.safety_disposition`) is not read by `/admin/rag/safety` at all -- that endpoint only sees the legacy `Escalation` table. Real Agent V2 safety incidents (e.g. today's own acute-danger-escalation smoke test) are invisible to this specific endpoint even after this build's fix, since the fix only wired the general trace pipeline, not this domain-specific table join.
3. **Token usage / cost per request**: Agent V2's own `backend/agents/v2/observability.py` (`AgentTelemetry`/`ModelPricingCatalog`) already computes real per-run cost internally -- it is simply never passed into `backend.services.telemetry`'s `ObservationRecord.usage`/`.cost` fields. Wiring that specific connection is a natural, bounded follow-up.
4. **Per-observation latency** (the `latency_waterfall` breakdown by step): because telemetry is recorded once, after the orchestrator has already finished, individual tool-call/safety/generation steps are stamped with near-zero duration relative to each other -- only the whole-request `duration_ms` is accurate (confirmed correct in §6). Real per-step timing would need instrumentation calls placed inside the orchestrator's own execution (each tool call, each safety check) rather than reconstructed after the fact -- a larger, more invasive change than this audit's "no behavior change" scope allows.
5. **`_require_admin` has no actual role check** (§2) -- a real authorization gap, deliberately not touched in this pass given the risk of breaking the current admin frontend's auth flow without dedicated testing.
6. **CRITICAL vs WARNING distinction** and a concrete P95 SLA number (§7) -- both need a product decision, not an engineering guess.

---

## Closeout

```
BUILD-25: PASS

ADMIN DASHBOARD: PASS (UI untouched; underlying data now real for Agent V2 traffic)
LANGFUSE CONNECTION: PASS (TelemetryService initializes and ships when LANGFUSE_* env vars are configured; local in-memory buffer + admin API work regardless, confirmed live)
AGENT V2 TRACING: PASS (verified end-to-end on live production, full drill-down)

REAL DATA: trace volume, per-request latency (P50/P95/P99), per-trace faithfulness/relevance, tool-call inputs/outputs, safety/handoff observations, model/prompt-version labels -- all confirmed against real production requests sent during this build
MOCK/HARDCODE DATA FOUND: HitRate/MRR/NDCG@10 (all alias the same hit_rate value), cost_per_query/cost_daily/low_retrieval_confidence_rate/timeout_rate/stale_doc_rate/failed_ingestion_count/embedding_drift (flat zero, genuinely unmeasured -- left as honest zeros, not newly invented), /versions/compare (fully stubbed)
BROKEN METRICS: unsafe_answer_rate (tautology, always 100.0 or 0.0), ttft_ms (fabricated p50*0.3 formula), P95 latency reading from an empty/stale fallback instead of real Agent V2 traffic (root cause of the reported "~0.7ms")
FIXED METRICS: unsafe_answer_rate (real denominator), ttft_ms (honest 0.0 instead of a fake formula), P95/P50/P99 latency + faithfulness + relevance + error rate + model/prompt-version labels (all now fed by real Agent V2 traffic via the new telemetry wiring)

FAITHFULNESS: 0.42 avg across this build's own 5-request live verification batch (real heuristic scores, not fabricated; small sample, will stabilize as real traffic accumulates)
ANSWER RELEVANCE: 0.55 avg, same batch
RETRIEVAL: HitRate/MRR/NDCG@10 still aliased to the same value (not independently computed) -- flagged, not fixed this pass
P50: 2020.5ms (real, live-verified)
P95: 3441.1ms (real, live-verified -- was ~0.7ms before this build's fix)
P99: 3441.1ms (same small-sample batch; will diverge from P95 as volume grows)
ERROR RATE: 0.0% (this batch)
EMPTY RATE: not computed anywhere in the admin API (known gap, §8.1) -- separately confirmed 0% via this session's own direct smoke tests
SAFETY: legacy Escalation-table view unchanged; Agent V2's own safety/handoff data not yet surfaced here (known gap, §8.2)
HANDOFF: visible per-trace in Trace Explorer (confirmed: a doctor-handoff request produced a `handoff.created` observation); not yet aggregated as its own dashboard metric
GROUNDING: same heuristic faithfulness score as above, now real for Agent V2
TOKEN/COST: still 0.0 everywhere -- genuinely unmeasured, Agent V2's own internal cost tracking not yet wired into this admin API (known gap, §8.3)

TRACE EXPLORER: PASS (verified full drill-down: query -> tool calls with real data -> generation -> scores -> metadata)
MODEL FILTER: PASS (now shows Agent V2's real model, gpt-5.4-mini, after the metadata fix)
PROMPT VERSION FILTER: PASS (now shows "agent-v2-orchestrator" instead of legacy chat's version)

HEALTH THRESHOLDS: PASS for HEALTHY/WARNING (existing, spec-consistent, unchanged); CRITICAL tier and a concrete P95 SLA number need a product decision (§7), not fabricated here

V2 PRODUCTION: 100% (unchanged throughout this build)
REGRESSION: PASS (421 Agent V2 + 5 rag_telemetry + 35 admin/nudge/health-log tests, 0 failures; live production smoke -- drug info, grounding, today-schedule, acute-danger, doctor-handoff, cross-patient-denial -- all correct)
```

### 1. Vấn đề tìm thấy
- Agent V2 never fed the existing Langfuse/telemetry pipeline at all (root cause of nearly everything else).
- `unsafe_answer_rate` was a mathematical tautology, not a real rate.
- `ttft_ms` was a fabricated formula (`p50 * 0.3`) with no measurement basis.
- Trace `model`/`prompt_version` metadata defaulted to legacy chat's values for Agent V2 traces.
- HitRate/MRR/NDCG@10 are all the same underlying number under three names.
- `_require_admin` performs no actual role check.
- Agent V2's own Safety/Handoff and cost-tracking data are not joined into the admin API's `/safety` and cost fields.

### 2. Root cause
Two systems were built independently: Agent V2's own orchestrator (with its own `AgentTelemetry`/`ModelPricingCatalog`) and the admin RAG-monitoring dashboard (built against legacy chat's pipeline only). They were never connected. Once Agent V2 became 100% of traffic, the dashboard was structurally guaranteed to show stale/wrong/empty data, regardless of how correct any individual formula was.

### 3. Fix đã thực hiện
Wired Agent V2's HTTP route into the existing telemetry service (additive, at the API boundary, zero orchestrator changes) + corrected the model/prompt-version labels + fixed the two broken formulas (`unsafe_answer_rate`, `ttft_ms`). No new dashboard, no new backend service, no rollout change, no migration.

### 4. Metric nào vẫn chưa đủ dữ liệu để đánh giá
Token usage/cost per request (tracked internally by Agent V2 but not surfaced here yet), empty-reply rate (not computed at all in this API), retrieval HitRate/MRR/NDCG as genuinely distinct metrics (currently aliased), Agent V2-specific safety incidents in `/admin/rag/safety` (only sees the legacy `Escalation` table), per-observation sub-step latency (only whole-request latency is accurate under the current post-hoc recording approach), and a CRITICAL-tier threshold distinct from WARNING (needs a sustained-duration check the code doesn't do yet).
