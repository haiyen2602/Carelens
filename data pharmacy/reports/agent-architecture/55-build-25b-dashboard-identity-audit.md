# BUILD-25B — Admin Dashboard V2 Identity Audit

**Scope:** the Model/Prompt Version filters on the admin RAG monitoring UI
were cosmetic — audit and fix so they reflect and actually filter real
Agent V2 traffic. No dashboard rebuild (per BUILD-25's own constraint,
carried forward), no Agent V2 behavior change, no rollout change, no
unnecessary DB schema change.

---

## 1. Root cause: the filters never touched real data, in either direction

`frontend/src/app/admin/rag/page.tsx`, before this build:

```tsx
<select value={modelFilter} onChange={(e) => setModelFilter(e.target.value)}>
  <option value="all">Tất cả Models (gpt-4o-mini...)</option>
  <option value="gpt-4o-mini">gpt-4o-mini</option>
</select>
```

Two independent problems, both confirmed by reading the code, not assumed:

1. **The option list was 100% hardcoded** — not derived from any API response.
2. **`modelFilter`/`promptFilter` state was never read by `fetchDashboardData()`** — the six backend calls that populate every tab's data never passed these values as query params, and the backend endpoints didn't accept any such param anyway. Selecting a different dropdown value changed the `<select>`'s own displayed value and nothing else.

This explains BUILD-25's continued "gpt-4o-mini" sighting cleanly: BUILD-25 fixed the *trace metadata* to carry Agent V2's real model, but the *filter UI* was never wired to read metadata at all — it was an independent, parallel piece of hardcoded UI that BUILD-25's fix could not have touched.

## 2. Fix — real backend filtering, then real frontend wiring

**Backend (`backend/api/rag_monitoring_routes.py`)**:

- New `_filter_traces()` — applied to `/health`, `/retrieval`, `/generation`, `/safety`, `/system`, `/traces` via a shared `_filter_query_params` dependency (`?chatbot_version=&model=&prompt_version=`). A trace missing a requested metadata value never matches (fails closed).
- New `GET /admin/rag/filters` — real, currently-available option lists, built from **actual trace metadata** (`get_local_traces()`), falling back to **currently-configured** values (`settings.agent_main_model`, `settings.model_name`, etc.) only when the trace buffer is genuinely empty — never a hardcoded historical list either way.
- `AuditLog` fallback rows (used when the in-memory trace buffer is empty) are **always legacy chat's own data** (confirmed in BUILD-25: only `chat_routes.py` writes `AuditLog`) — excluded entirely from every endpoint the moment a filter asks for anything other than "legacy"/unfiltered, so an "agent-v2"-filtered view can never silently show legacy rows mislabeled as Agent V2's.
- Every trace is now tagged with an explicit `chatbot_version` (`"agent-v2"` in `agent_v2_routes.py`'s telemetry call, `"legacy"` in `chat_routes.py`'s) so the two systems are distinguishable in the data itself, not just by trace name.
- `agent_v2_routes.py`'s trace metadata now also carries `router_model`/`fallback_model`/`embedding_model` alongside the main model — the user's own 4-model breakdown (Router `gpt-5.4-nano`, Main `gpt-5.4-mini`, Fallback `gpt-5.4`, Embedding `text-embedding-3-small`).
- Fixed a second hardcode found while doing this: `/generation`'s `breakdown_by_prompt` unconditionally used legacy's own `settings.rag_prompt_version` regardless of which traces were actually being shown — now grouped by each trace's real `prompt_version`.

**Frontend (`frontend/src/app/admin/rag/page.tsx`)**:

- New `chatbotVersionFilter` state, **defaulting to `"agent-v2"`** — satisfies the instruction to separate/exclude legacy from the default production view, rather than mixing both systems' numbers together by default. Legacy is opt-in via the same dropdown ("Tất cả" or "Legacy Chatbot"), never silently blended in.
- `GET /admin/rag/filters` fetched alongside the other six calls; the three `<select>`s render `filterOptions.chatbot_versions/models/prompt_versions` — real, live values, never a hardcoded list.
- `fetchDashboardData()` now builds a real query string from all three filter values and sends it on every one of the six data fetches; `useEffect`'s dependency array includes all three filters, so changing any of them **re-fetches**, not just re-renders.
- New header badges: `Chatbot Version: Agent V2 / Production` (or `Legacy Chatbot` / `Tất cả hệ thống`, reflecting whichever filter is actually active) and `Environment: <real settings.app_env>` — both driven by the same real data, not static text.

## 3. Verification — proved the filter changes actual data, not just labels

Per the audit's own explicit warning ("UI không chỉ đổi label nhưng backend query vẫn sai"), verified both directions on **live production**, not just locally:

```
GET /admin/rag/filters                                    -> source: "current_config_fallback_no_traces_yet" (trace buffer was empty right after this build's own redeploy)
                                                               models: ["gpt-5.4-mini", "gpt-4o-mini"] -- both systems' real configured models

GET /admin/rag/system?chatbot_version=agent-v2             -> volume_24h: 0 (correctly empty -- no Agent V2 traffic had hit this fresh process yet; NOT fabricated data)
GET /admin/rag/system?chatbot_version=legacy               -> volume_24h: 100, p50=2030.6ms, p95=4245.1ms, p99=5732.8ms,
                                                               real per-step latency_waterfall (step.intent_classification,
                                                               step.answer_generation, step.drug_identity_resolution, ...)
                                                               -- from real persisted AuditLog rows, genuinely different data
                                                               from the agent-v2-filtered call immediately above

-- sent 1 real Agent V2 request via scripts/agent_v2/live_golden_validation.py --

GET /admin/rag/system?chatbot_version=agent-v2 (again)     -> volume_24h: 1, p50=4360.4ms (real, matches the request just sent)
GET /admin/rag/filters (again)                             -> source: "real_trace_metadata", models: ["gpt-5.4-mini"] only
                                                               (correctly excludes gpt-4o-mini now that the only real trace
                                                               in the buffer is Agent V2's -- reflects what's actually there)
```

This is definitive: the two filter values produced **completely different, independently-correct result sets** from the same live endpoint — not a relabeled version of the same underlying data. Confirmed locally first too (a standalone script populated one agent-v2-tagged and one legacy-tagged trace, verified `/filters` lists both, and `/traces`/`/system` filtered to exactly 1 result each when asked for one or the other).

## 4. Regression

Local: 456 passed (421 Agent V2 + 5 rag_telemetry + 30 admin/nudge/health-log), 3 pre-existing skips, 0 failed — unchanged from BUILD-25. TypeScript check on the modified frontend page: 0 errors (10 pre-existing, unrelated errors elsewhere in the tree — missing optional npm packages for Supabase/gsap integrations this session's `node_modules` wasn't installed for — confirmed none in `admin/rag/page.tsx` itself).

No Agent V2 behavior changed (all changes are in the admin-only `rag_monitoring_routes.py` and the dashboard's own React component). `AGENT_ROLLOUT_PERCENTAGE` never touched (100% throughout). No DB schema change — `chatbot_version` lives in the existing `TraceRecord.metadata` JSON field, nothing new added to the database.

---

## Closeout

```
BUILD-25B: PASS

CHATBOT VERSION FILTER: PASS (new, real values from /admin/rag/filters, defaults to "agent-v2", genuinely filters every endpoint)
MODEL FILTER: PASS (real values -- gpt-5.4-mini/gpt-5.4-nano/gpt-5.4/gpt-4o-mini depending on what's actually in the trace buffer -- not a hardcoded list; verified the option list itself changes as real traces arrive)
PROMPT VERSION FILTER: PASS (real values -- agent-v2-orchestrator / medication-chat-v1.0 -- and /generation's breakdown_by_prompt no longer hardcodes legacy's version)
LEGACY VALUES REMOVED/SEPARATED: PASS (default view is chatbot_version=agent-v2; legacy is opt-in, never silently mixed into the default numbers; AuditLog fallback rows -- always legacy data -- are excluded from any non-legacy-filtered view)
REAL TRACE DATA: PASS (verified live: chatbot_version=agent-v2 and =legacy return genuinely different, independently-correct volume/latency/waterfall data from the same production traffic window)
```
