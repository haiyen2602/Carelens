# BUILD-19 — Controlled Staging UAT

Date: 2026-08-19
Scope: controlled internal UAT of Agent V2 on the existing Railway `staging`
environment (BUILD-18/18B's), synthetic accounts only, no PHI. Production
was never modified. `AGENT_RUNTIME_ENABLED` was `true` on staging only for
the duration of this UAT and was rolled back to `false` at the end.

> **UPDATE (BUILD-19B, same date):** the single P1 finding below (empty
> `reply` on every tool-calling turn, including the specifically-flagged
> Safety SAFE case) has been fixed — the runtime now runs the required second
> "synthesis" model turn (User → Model → Tool Call → Tool Result → Model
> Synthesis → Final Reply) instead of returning the pre-tool planning text —
> tested with ten new regression scenarios, and re-verified live on this same
> staging environment: all four previously-empty-reply scenarios (drug
> information, today's doses, Safety SAFE, prescription query — including a
> genuine three-tool multi-call synthesis) now produce real, correct replies,
> with no Safety/Handoff/persistence/authorization regression. **BUILD-19
> FINAL: PASS.** See
> [24-build-19b-tool-result-synthesis-fix.md](24-build-19b-tool-result-synthesis-fix.md)
> for the fix, its tests, and the live re-verification. The three P2s
> reported below (Vinmec Cyrillic glitch, unclear `SAFETY_BLOCKED` wording,
> RAG/Vinmec latency) remain open — out of this fix's explicit scope. The
> closeout block below is left exactly as originally written, as the
> historical record of what this build found.

## Setup

Reused BUILD-18B's staging environment/Postgres/synthetic data (no new
provisioning). Flipped `AGENT_RUNTIME_ENABLED=true` (staging only; production
never read or written), re-minted JWTs locally with the unchanged staging
`JWT_SECRET` for the existing synthetic `agent-v2-staging-*` doctor/
caregiver/patient accounts, and confirmed via `railway variables` (not an
HTTP status guess — see BUILD-18B's own correction of that methodology).

## UAT scenarios run

`scripts/agent_v2/uat_staging_scenarios.py` (new) drove 10 live HTTP calls
against `/api/v1/agent/v2/orchestrate`, one more manual greeting call, and a
dedicated budget/timeout toggle — 12 total. Full JSON output for the 10
scripted calls is preserved for this report.

| # | Scenario | HTTP | Agent status | Intent | Tools | Latency | Reply |
| - | --- | --- | --- | --- | --- | ---: | --- |
| 1 | Drug information (paracetamol) | 200 | COMPLETED | DRUG_INFORMATION | `search_drug` | 1.4s | **empty** |
| 2 | RAG (open question, no product named) | 200 | COMPLETED | GENERAL_MEDICAL_INFORMATION | — | 9.8s | populated, good quality, 0 citations (legitimate no-match) |
| 3 | Memory recall (same conversation as #1) | 200 | COMPLETED | DRUG_INFORMATION | — | 1.7s | populated, **correctly references "paracetamol" from turn 1** |
| 4 | Patient dose query ("today's doses") | 200 | COMPLETED | TODAY_DOSES | `get_today_doses` | 1.2s | **empty** |
| 5 | Vinmec Web (diabetes) | 200 | COMPLETED | VINMEC_WEB_INFORMATION | — | 8.8s | populated, honest fallback, 0 citations (DEGRADED — see §Vinmec) |
| 6 | Safety SAFE (real MISSED occurrence, reviewed low-risk policy) | 200 | COMPLETED | MISSED_DOSE | `get_today_doses` | 1.5s | **empty** (the specifically-flagged concern) |
| 7 | Safety on a still-PENDING dose | 200 | SAFETY_BLOCKED | MISSED_DOSE | — | 0.4s | fixed fallback string (fail-closed; correct) |
| 8 | Doctor Handoff (dosage-change request) | 200 | HANDOFF_CREATED | DOCTOR_REVIEW | — | 0.4s | populated, correct |
| 9 | Cross-patient denial (caregiver, unlinked patient) | 403 | — | — | — | 0.4s | — |
| 10 | Prescription query | 200 | COMPLETED | PRESCRIPTION_INFORMATION | `get_active_prescriptions`, `get_today_doses`, `get_upcoming_doses` | 1.3s | **empty** |
| 11 | Greeting ("xin chào", no tool needed) | 200 | COMPLETED | GENERAL_CONVERSATION | — | — | populated, correct |
| 12 | Budget/timeout (staging-only `AGENT_TOKEN_BUDGET=10`) | 200 | BUDGET_EXCEEDED | DRUG_INFORMATION | — | — | fixed fallback string ("Agent run vuot gioi han token."); reverted after |

No P0 was found (see the explicit evaluation in §Issues), so UAT ran to its
full planned scope rather than stopping early; the runtime flag was rolled
back at the end exactly as planned either way.

## Issue: empty `reply` for every tool-calling turn (P1)

**Reproduced in 4/10 scenarios** (#1, #4, #6 — the one specifically flagged
— and #10), always and only when the Main Model's plan included at least one
tool call. Scenarios that reached the Main Model *without* a tool call (#3,
#11) and scenarios that never reach the Main Model with tools relevant
(#2/#5, which ground via injected retrieval/web evidence text rather than
the tool-calling mechanism) all returned a populated reply.

**Root cause, verified against source** (`backend/agents/v2/model_gateway.py:318`,
`backend/agents/v2/runtime.py:291`): `OpenAIModelGateway.plan_read_only()`
makes exactly **one** model call and returns that same call's `output_text`
as `ModelPlan.response`. When the OpenAI Responses API returns a
`function_call`, `output_text` for that turn is empty — this is standard,
documented behavior; a model turn that calls a tool does not simultaneously
produce synthesis text. `ReadOnlyAgentRuntime._run()` executes every
`tool_calls` entry and then returns `plan.response` — the text from *before*
the tools ran — as the final answer. **There is no second model turn that
feeds tool results back for a natural-language synthesis.** This has been
architecturally present since BUILD-2/3; it was invisible until now because
BUILD-2's own model smoke test only checks that a tool call is *returned*,
and every automated test since (BUILD-9 through BUILD-18B) uses a static/fake
model gateway that never exercises this real OpenAI turn-boundary behavior.

**Severity assessment (why P1, not P0):** the structured fields the response
already carries — `safety_disposition`, `handoff_id`, `citations`, `tools`,
`status` — are all independently correct in every reproduction above (cross-
checked against §Persistence). No wrong or dangerous clinical content is
ever produced; the failure mode is a **visibly empty response**, not a
silently confident wrong answer, and it does not touch authorization, data
integrity, or Safety Domain correctness. It does, however, make the
assistant's primary conversational value — answering drug/dose/prescription
questions in the tool-calling paths that are the app's core use cases —
effectively silent for a real user. That is a high-severity usability defect
that must be fixed before broader (non-internal) testing, but it is not a
safety, security, or data-integrity violation, so it does not meet this
build's P0 bar ("STOP UAT và tắt runtime staging").

RESPONSE QUALITY: **FAIL** (this defect alone is disqualifying for real user
traffic, even though every scenario that *did* produce text was good
quality — see the RAG/memory/handoff replies above)

## Issue: Vinmec Web — DEGRADED, not hidden

Consistent with BUILD-18B: `VinmecWebSearchService.search()` no longer
crashes (defect 1 fix holds), but the specific candidates vinmec.com's
static search page currently surfaces (`/chuyen-khoa/` specialty-center
navigation links, ~3,000 tokens each) exceed `AGENT_VINMEC_WEB_TOKEN_BUDGET`
(600), so `_within_budget()` correctly excludes them all → `NO_RESULTS` →
`citations: []`. The Main Model, given no Vinmec evidence, **honestly told
the user it could not search Vinmec directly** and offered general medical
knowledge instead — a safe, transparent degradation, not a silent failure or
a fabricated citation.

**New, minor observation this run:** the fallback reply for scenario 5
contained one word rendered in Cyrillic script instead of Latin ("Các **тип**
chính:" — Cyrillic т/и/п instead of Latin) — a small model-output anomaly,
cosmetic, does not affect the medical correctness of the surrounding text.
Logged as P2.

VINMEC WEB: **DEGRADED** (not FAIL — it never fabricates evidence and always
completes gracefully; not PASS — it produced zero real citations in this
UAT's only two live attempts across BUILD-18B and this build)

## Safety

Both dispositions exercised correctly:

- **SAFE** (#6): a real `MISSED` occurrence with a reviewed, low-risk policy
  → `safety_disposition: SAFE`. (Reply text empty — see the P1 above; the
  disposition itself is correct.)
- **SAFETY_BLOCKED** (#7): asking about a dose that is still `PENDING` (not
  actually due/missed yet) correctly fails closed rather than guessing —
  `assess_dose_safety` refuses to assess a non-missed/delayed occurrence, and
  `SafetyGateway` converts that refusal to `SAFETY_BLOCKED` rather than
  crashing or fabricating a disposition. **This is the safety mechanism
  working as designed**, not a defect. One P2 UX note: the reason surfaced
  to the user ("Khong the tra loi khi danh gia an toan chua duoc xac nhan.")
  does not distinguish "this dose isn't due yet" from "the safety domain is
  unavailable" — a real tester could read this as "the system is broken"
  rather than "you're asking too early." Worth a clearer message in a future
  build; not a safety defect (fail-closed is correct either way).

SAFETY: **PASS**

## Doctor Handoff

`HANDOFF_CREATED` with a real `handoff_id`, correct reply text, and — per
§Persistence — a genuinely new, durable `doctor_review_request` row (no
duplicate of BUILD-18B's earlier two).

HANDOFF: **PASS**

## Persistence

Checked directly against the staging database (fresh connection, not the
request's own session):

```
agent_run:              20 -> 33 rows  (+13, one per UAT-scenario call including the budget-exceeded run)
agent_run_checkpoint:    same +13
doctor_review_request:   2 -> 3 rows   (+1, exactly the one new handoff from scenario 8; no duplicates)
```

Every terminal status recorded matched the scripted scenario exactly, in the
correct order, with no missing or duplicate rows.

PERSISTENCE: **PASS**

## Authorization

Cross-patient denial (#9) returned `403` with the existing, unchanged
`require_agent_patient_access` message. No PHI/patient existence was leaked
in the error. No other authorization boundary was exercised beyond what
BUILD-18/18B already proved (single-patient-role and caregiver-role paths).

AUTHORIZATION: **PASS**

## Observability / redaction

`railway logs --service BE --environment staging --lines 200` was checked
during this UAT run — **the first time this could be checked at all**, since
BUILD-18B's fix (`logging.basicConfig` in `backend/main.py`) is now live.
110 structured `agent_run.*`/`agent_model.*`/`agent_span.*` events were found
across the 200-line window, e.g.:

```json
{"event":"agent_model.completed","model":"gpt-5.4-mini","model_role":"main","input_tokens":264,"output_tokens":45,"cached_input_tokens":0,"latency_ms":3662.78,"estimated_cost_usd":null,"provider_request_id":"req_...","trace_id":"...","agent_run_id":"..."}
{"event":"agent_run.finished","terminal_status":"COMPLETED","agent_steps":1,"tool_calls":0,"safety_disposition":null,"handoff_outcome":null,"latency_ms":3663.0,"trace_id":"...","agent_run_id":"..."}
```

Every field is metadata (ids, model name, token counts, latency, terminal
status) — no prompt, no message text, no patient name/id beyond the opaque
`agent_run_id`/`trace_id`, no secret. `estimated_cost_usd: null` throughout,
consistent with BUILD-17's documented "unknown price → `None`, never
fabricated `$0`" behavior (`AGENT_MODEL_PRICING_JSON` is still unset on
staging). No exception/error-level log line was found anywhere in this UAT
run (the only `"level":"error"` entries are uvicorn's own mislabeled startup
INFO lines, a Railway log-level tagging quirk, not an application error).

OBSERVABILITY: **PASS**

## Duplicate / error / exception tracking

No duplicate `doctor_review_request` (§Persistence: exactly +1 for exactly
1 handoff scenario). No exception or 5xx response anywhere in this run
(all HTTP statuses were `200`/`403`, all expected). No unhandled error in
the captured logs.

## Latency

Most calls: 350ms-1.7s. Two outliers: RAG (9.8s) and Vinmec Web (8.8s) — both
involve either an embedding call plus a longer generation (RAG) or several
sequential real HTTP fetches to vinmec.com (search page + up to 3 candidate
articles, each its own round-trip). Both complete correctly; neither hit any
configured timeout. Logged as a P2 UX observation (a real user may perceive
8-10s as sluggish for these two paths) rather than a defect — no configured
budget/timeout was violated.

## P0 / P1 / P2 issues

**P0: none.** Evaluated explicitly against this build's stop criterion
(safety-critical wrong/dangerous output, security violation, data
corruption/leak, or an outage that would make continuing the UAT unsafe) —
nothing found meets that bar, so the UAT was not stopped early and the
runtime was disabled through the normal end-of-UAT rollback instead.

**P1 (1):**
1. Empty `reply` text for every tool-calling turn (drug info, dose queries,
   prescription queries, and the Safety-SAFE path) — root cause identified
   and verified against source above. Must be fixed (a second model turn
   that synthesizes tool results into a final reply, or an equivalent
   composition step) before any broader/external UAT or production
   consideration. Not fixed in this build — this build's scope is UAT and
   issue triage, not remediation; per "không sửa architecture ... chỉ để
   PASS", this is reported, not patched, here.

**P2 (3):**
1. Vinmec Web fallback text occasionally mixes in a stray Cyrillic word
   (model output quality, cosmetic).
2. The `SAFETY_BLOCKED` message for a not-yet-due dose does not distinguish
   "too early to assess" from "safety domain unavailable" — fail-closed
   behavior itself is correct; only the user-facing wording could be
   clearer.
3. RAG and Vinmec Web latency (8-10s) is noticeably slower than the other
   paths (sub-2s); within configured budgets/timeouts, but worth watching
   as real usage scales.

No new P0/P1/P2 was found in authorization, persistence, checkpoint
behavior, or the budget/timeout fail-closed path — all reconfirmed exactly
as BUILD-18B left them.

## Rollback

```
railway variable set "AGENT_TOKEN_BUDGET=4096" (and the two related budget vars) --service BE --environment staging
railway variable set "AGENT_RUNTIME_ENABLED=false" --service BE --environment staging
```

```
$ curl ... -H "Authorization: Bearer <valid patient JWT>" -d '{"patient_id":"...","message":"xin chao"}'
HTTP 404
```

Confirmed with a real, authenticated request. Staging was left in this OFF
state. Production's `AGENT_RUNTIME_ENABLED` was never read or written.
Production re-verified byte-identical (same 3 service deployment
timestamps, same Postgres `DATABASE_URL` hash) as the final infrastructure
action of this build.

## New files

- `scripts/agent_v2/uat_staging_scenarios.py` — the UAT driver used above;
  makes no assertions itself (prints one JSON record per scenario), so it
  is reusable for a future UAT round without needing a fresh report to
  interpret its raw output.

No corpus, evaluation, or architecture file was changed. No new Railway
environment/database was provisioned — this build only exercised BUILD-18B's
existing staging deployment.

## Result

BUILD-19: **FAIL** (real, high-severity response-quality defect found; UAT
process itself — scenario coverage, persistence, authorization, safety,
observability, rollback — all executed correctly and are reported PASS
individually below)

UAT SCENARIOS: PASS (all 12 planned scenarios executed; no P0, no crash, no
unplanned early stop)

SAFETY: PASS

HANDOFF: PASS

PERSISTENCE: PASS

AUTHORIZATION: PASS

RESPONSE QUALITY: FAIL (empty `reply` on every tool-calling turn — P1, see above)

OBSERVABILITY: PASS

VINMEC WEB: DEGRADED

P0/P1/P2 ISSUES:
- P0: 0
- P1: 1 — empty `reply` for tool-calling turns (root cause identified; not fixed in this build)
- P2: 3 — Vinmec Cyrillic-character output glitch; unclear `SAFETY_BLOCKED` wording for a not-yet-due dose; RAG/Vinmec latency (8-10s)

READY FOR PRODUCTION HARDENING: NO — fix the P1 (tool-calling turns must
produce a real synthesized reply, not an empty string) before further UAT
rounds or any hardening work; the P2s should be triaged alongside it but do
not block starting that work once the P1 is fixed.

READY FOR PRODUCTION: NO
