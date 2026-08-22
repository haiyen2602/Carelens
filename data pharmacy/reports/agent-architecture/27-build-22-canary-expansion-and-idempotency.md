# BUILD-22 — Canary Expansion & Production Gate Closeout

**Scope:** expand the BUILD-21 production canary in small, monitored batches
and close the two gates BUILD-21 left open (Safety SAFE live proof,
request-level idempotency) wherever that can be done honestly. Full
production rollout is explicitly **out of scope** for this build.

**Environment:** Railway production (`VMEC-04/BE`, `VMEC-04/Postgres`),
staging (`BE`, `Postgres-_hCI`) used to validate the new idempotency feature
before it touched production traffic.

---

## 1. Safety SAFE production proof — BLOCKED_BY_CLINICAL_GOVERNANCE

Re-queried production's `medication_safety_policy` fresh at the start of this
build: **0 rows**, same as BUILD-21. No `REVIEWED` policy exists for any
drug.

Per this build's explicit instruction, **this gate is stopped here**:

```
BLOCKED_BY_CLINICAL_GOVERNANCE
```

No synthetic "reviewed" policy row was created to force a pass. This remains
a real, pre-existing clinical-governance data gap outside Agent V2's own
code (see BUILD-21 §recommendations; still open).

What *could* be verified without live policy data — static/architectural
proof that the model cannot override a Safety result — was re-confirmed by
inspection: `backend/agents/v2/runtime.py`'s `_run` checks
`safety_decision.outcome` *before* any model call and returns immediately for
`SAFETY_BLOCKED`/`HANDOFF_REQUIRED` (the Main Model is never reached for
either); for `SAFE`, the model only composes reply text under an
already-fixed `SafetyContext.RESOLVED` state. The `safety_disposition` field
returned to every caller (`AgentOrchestrator.run` → `OrchestrationResult.
safety_decision`, unchanged by BUILD-22) is always sourced from the Safety
Gateway's `SafetyDecision`, never parsed or inferred from model output.

---

## 2. Request-level idempotency (built and shipped this build)

### 2.1 Design

`AgentV2OrchestrateRequest.idempotency_key` (new, optional — omitting it is
byte-for-byte the original BUILD-16 behavior). When present, the route
(`backend/api/agent_v2_routes.py`) derives a **deterministic**
`agent_run_id` from `(actor_id, patient_id, idempotency_key)` via
`backend/services/agent_idempotency.py::derive_agent_run_id` (uuid5), claims
it in a new `agent_idempotency_key` table (migration `0034`, unique on
`(actor_id, patient_id, idempotency_key)`), and:

- **First call** claims the row, runs the orchestrator with that
  `agent_run_id`, records the exact JSON response before the route's single
  outer commit.
- **Retry with the same key** (same actor, same patient): finds the
  `COMPLETED` claim and returns the identical stored response — the
  orchestrator is never invoked a second time, so a Doctor Handoff (or any
  other side effect) is never duplicated.
- **Concurrent duplicates**: the second `INSERT` blocks at the database level
  on the still-uncommitted first row (standard Postgres unique-index
  behavior) until the first request's single transaction commits or rolls
  back; a plain re-`SELECT` after that is sufficient (no `FOR UPDATE`
  polling needed) — see the module docstring for the full argument.
- **Different actor or different patient with the identical key string**:
  derives a completely different `agent_run_id` and a different DB row
  (different unique-constraint key) — structurally cannot replay or resume
  someone else's run, not just policy-checked.
- **TTL**: `Settings.agent_idempotency_ttl_seconds` (default 86400s / 24h). A
  claim older than the TTL is deleted and the same key starts a genuinely new
  run rather than replaying stale output forever.

This is intentionally layered *on top of*, not a replacement for, BUILD-12's
existing checkpoint/resume machinery (crash recovery of an interrupted run) —
those remain two different, complementary guarantees; see the module
docstring for exactly how they interact (a terminal checkpoint cannot itself
be "resumed", which is why this had to intercept *before* the orchestrator,
not inside it).

### 2.2 Verification (4 layers)

1. **Unit** (`tests/test_agent_v2_idempotency.py`, SQLite): derivation
   determinism/binding, claim→busy→replay state machine, TTL expiry,
   validation — all passing.
2. **Real Postgres concurrency** (`tests/test_agent_v2_idempotency_postgres.py`,
   opt-in via `BUILD22_TEST_DATABASE_URL`): 6 threads racing the identical
   claim — exactly one owner, the other 5 replay its exact result. Run
   against staging's real database: **passed**.
3. **Live staging HTTP**: sequential retry with the same key → identical
   response; different key → independent handoff; no key → unchanged
   legacy behavior; **3 simultaneous** HTTP requests with the same key → all
   3 converged on the same `agent_run_id`/`handoff_id`; verified directly in
   the database afterward: exactly **1** `agent_idempotency_key` row and
   exactly **1** matching `doctor_review_request` row for that key.
4. **Live production HTTP**, across real canary accounts, batches A–C: the
   same 4 checks repeated, plus a cross-actor binding check (patient1 and
   patient3 both supplying the literal same key string derived two
   completely different `agent_run_id`s and two independent handoffs — never
   cross-replayed).

Route-level regression tests were also added directly against
`run_agent_orchestration` with real independent SQLite sessions/commits
(`tests/test_agent_v2_transaction_durability.py`): retry-does-not-duplicate,
different-key-is-independent, no-key-is-unchanged, and
actor/patient-binding — closing the exact scope gap that file's own BUILD-21
comment had documented ("the HTTP route... does not yet expose a client
idempotency key").

**Duplicate Doctor Handoff prevention**: proven directly, live, multiple
times (staging 3-way concurrent, production sequential and cross-actor) —
in every case exactly one `doctor_review_request` row exists per genuinely
distinct `(actor, patient, key)` triple, verified by direct DB query, not
just by the HTTP response shape.

**Full local suite**: 76 targeted Agent V2 tests passing after the final
script-only edits below; broader run earlier in this build showed 191+
passing with only the pre-existing, environment-specific failures documented
in prior builds (local Postgres not running; unrelated `numpy`-dependent
photo-verification modules) — neither touched by this build's changes.

---

## 3. Canary expansion (3 batches, monitored after each)

| Batch | Accounts on `AGENT_CANARY_ALLOWLIST` | New this batch |
|---|---|---|
| A (baseline) | doctor, patient1 | — (BUILD-21 carryover, re-verified) |
| B | + patient3, patient4 | 2 new patients, one under the *same* doctor, one under a placeholder for batch C |
| C | + doctor2 | 1 new doctor (a genuinely second treating doctor) |

Legacy `/api/v1/chat` remained the default path throughout; nothing in this
build changes legacy routing.

### Batch A / stale canary data finding (found and fixed)

Re-running BUILD-21's canary seed script (idempotent by design) revealed it
never cleaned up DB Architecture V2 shadow-mode sidecar rows
(`PrescriptionItem`/`DoseOccurrence`) on reset — only the legacy
`Prescription`/`dose_event` rows. Every prior re-seed left the previous
run's V2 occurrences **orphaned but still live**, and Agent V2's dose tools
read from exactly that V2 table. By this build the canary patient had
**12** `dose_occurrence` rows where 6 were correct — silently doubled
context, which pushed the `prescription_multi_tool` scenario over its token
budget: reproducibly **100% BUDGET_EXCEEDED** (2/2 repeat calls), status
`"Agent run vuot gioi han token."`.

Not an Agent V2 orchestration defect — the token-budget fail-closed behavior
itself worked exactly as designed. Fixed at the source: all three seed
scripts (`seed_production_canary_data.py`, `seed_production_canary_batch2.py`,
and BUILD-18's `seed_staging_agent_v2_data.py`, which had the identical gap)
now also delete `DoseOccurrence`/`PrescriptionItem` rows on reset. Cleaned up
the orphaned rows on production, re-verified: **3/3 COMPLETED**, p95 back to
~4.9–5.2s, matching BUILD-21's original baseline.

### Batch B / seed script bugs found and fixed (both in this build's own new script)

1. **Diacritics typo**: `seed_production_canary_batch2.py` wrote the meal
   timing as `"Sau an"` instead of `"Sau ăn"`. `write_path.py`'s
   `MEAL_CODES` requires an exact match; the mismatch silently marked the
   prescription item `REVIEW_REQUIRED` instead of `ACTIVE`, which silently
   excluded it from V2 dose-occurrence generation — while the *legacy*
   `dose_event` path is not gated the same way, so `doses_generated=6`
   printed as if everything had succeeded. Found because patient3/patient4's
   live "today doses" replies both came back empty. Fixed the string, cleaned
   up, re-verified: both patients now correctly see today's doses.
2. **Missing `DoctorWatch` row**: Agent V2's own authorization boundary
   (`backend/services/agent_authorization.py::require_agent_patient_access`)
   grants a doctor read access via an explicit `DoctorWatch` row — a
   deliberately different, opt-in relationship from `Patient.doctor_id` (the
   "responsible doctor," used elsewhere for handoff assignment). The new
   fixture set `Patient.doctor_id` but never created the `DoctorWatch` row,
   so doctor2 was correctly **denied even for their own patient** — this is
   the authorization boundary working exactly as designed against an
   incomplete fixture, not a defect, but it also meant no canary build had
   ever exercised a doctor's *positive* Agent V2 read path before now (every
   prior doctor-role query in this whole series had been a denial case).
   Fixed by adding the `DoctorWatch` row; re-verified both directions live:
   doctor2 reading their own watched patient → `200 COMPLETED`; doctor2
   reading a different doctor's patient → `403`.

Cross-patient denial (patient1→patient3, patient3→patient4, both
directions) and cross-doctor denial (doctor2→patient3) were all confirmed
`403` throughout, both before and after the fixture fixes.

### Batch C

Doctor2 (a genuinely second treating doctor, distinct from batch A/B's
doctor) added to the allowlist; both the positive (own watched patient) and
negative (unwatched patient) authorization paths verified live, as above.

---

## 4. Monitoring (all batches combined)

| Dimension | Result |
|---|---|
| Error rate | **0/36** scripted perf calls (2 clean batches × 4 scenarios × ~4-5 reps); dozens of additional manual functional/authorization/idempotency calls across 3 batches, all correct (every non-200 response was either an expected `403` authorization denial, or a `401` from a JWT I let expire between steps of this session — never a system error) |
| Empty reply rate | **0/36** scripted calls; 0 across all manual calls |
| P95 latency | drug_information 3.9–8.5s; today_doses 3.4–3.5s; prescription_multi_tool 4.9–5.0s (after the stale-data fix); rag_query (GENERAL_MEDICAL_INFORMATION/retrieval path) 12.5–12.6s |
| Avg cost/request | **≈$0.00167** (20 real distinct requests sampled mid-session from live telemetry, grouped by `trace_id`; range $0.00088–$0.00348) — consistent with BUILD-21's smaller-sample figure |
| Safety/Handoff | `HANDOFF_CREATED`/`HANDOFF_REQUIRED` triggered correctly and idempotently across every batch; SAFE not reachable (§1) |
| Authorization | Cross-patient and cross-doctor denial confirmed repeatedly; idempotency key correctly actor/patient-bound (§2.2) |
| Persistence | `agent_idempotency_key` rows verified directly in the DB after every idempotency test — exactly one per genuinely distinct `(actor, patient, key)`, `COMPLETED` with the exact replayed response |
| Redaction | `railway logs` sampled after live traffic: only `agent_run_id`/`trace_id`/token counts/`estimated_cost_usd`/model name/latency — no message text, no reply text, no JWT, no drug/prescription content |

One quality observation, not a release-blocking defect: a `GENERAL_CONVERSATION`
reply during batch A testing contained a stray non-Vietnamese token
mid-sentence ("...đơn thuốc đang सक्रिय..." — Devanagari script appearing in an
otherwise-Vietnamese sentence). Isolated, not reproduced on retry; logged
here for visibility, not investigated further this build (model-generation
variance, not a code defect).

---

## 5. Vinmec Web

No code changes to this path this build. Not exercised by this build's own
live traffic (no test message classified into the `VINMEC_WEB_INFORMATION`
intent — the `rag_query` scenario used here hits the retrieval/RAG path via
`GENERAL_MEDICAL_INFORMATION`, not Vinmec Web). BUILD-21's live-verified
characterization stands unchanged: `AGENT_VINMEC_WEB_ENABLED=true`,
DEGRADED, honest zero-citation fallback, never blocks a clinical answer,
never fabricates a citation. Not redesigned this build, as instructed.

---

## 6. Release gates

- **P0** (would trigger immediate rollback): none found in Agent V2's own
  orchestration/safety/authorization/idempotency code this build.
- **P1** (safety/auth/data-integrity): none found in Agent V2's own code.
  Two P1-shaped issues were found and fixed, but both were in this build's
  *test fixtures* (seed scripts), not the product: the stale-dose-data bug
  (§3, Batch A) and the missing-`DoctorWatch` fixture gap (§3, Batch B) —
  neither ever reached a real user, both caught by this build's own
  monitoring before expansion continued, both fixed and re-verified before
  moving on.
- **P2** (carried from BUILD-21, still open): `medication_safety_policy` has
  0 reviewed rows (blocks live Safety SAFE proof); `agent_run_id` is not
  independently exposed as a raw HTTP contract field (superseded in
  practice by the new `idempotency_key`, which now provides the client-facing
  mechanism BUILD-21 flagged as missing).
- Kill switch: tested at the end of this build (§7) — works.

---

## 7. Kill-switch / rollback test

`AGENT_RUNTIME_ENABLED` flipped `true → false` on production, service
restarted. 3 consecutive live calls from a still-allowlisted account (valid
JWT) all returned `404 {"detail": "Agent V2 chua duoc kich hoat"}` —
identical to a fully-disabled deployment, exactly as designed. Legacy
`/api/v1/chat` confirmed still responding normally (401 for unauthenticated,
not a crash) immediately after.

---

## 8. Final production state

- `AGENT_RUNTIME_ENABLED=false` — per this build's explicit default ("unless
  an explicit decision keeps the canary running"); no such explicit decision
  was made, so the canary is paused, not expanded to live traffic beyond
  this build's own testing.
- `AGENT_CANARY_ALLOWLIST` left at the full 5 accounts reached this build
  (2 patients' original doctor + patient1 + patient3 + patient4 + doctor2) —
  harmless while the flag is off; documents the pre-approved set for
  whenever the canary resumes.
- `AGENT_VINMEC_WEB_ENABLED=true`, shadow-mode flags unchanged from BUILD-21.
- Migration `0034` (`agent_idempotency_key`) applied on both staging and
  production; all 3 seed-script fixes and the idempotency feature shipped to
  both environments.
- Both temporary TCP proxies opened during this build (production,
  staging-as-Postgres-concurrency-test-target) are closed.
- Staging's `AGENT_RUNTIME_ENABLED` was returned to its original `false`
  after this build's staging validation.

---

## Closeout

```
BUILD-22: PASS
SAFETY SAFE LIVE: BLOCKED
CLINICAL GOVERNANCE: BLOCKED_BY_CLINICAL_GOVERNANCE (0 reviewed medication_safety_policy rows in production; not fabricated -- see report Section 1)
REQUEST IDEMPOTENCY: PASS
DUPLICATE HANDOFF PREVENTION: PASS
AUTHORIZATION: PASS
CANARY EXPANSION: PASS (3 batches, 2 -> 4 -> 5 accounts, monitored after each)
P95 LATENCY: drug_information 3.9-8.5s; today_doses 3.4-3.5s; prescription_multi_tool 4.9-5.0s; rag_query (retrieval path) 12.5-12.6s -- see report Section 4
AVG COST/REQUEST: ~$0.00167 (20 live samples, range $0.00088-$0.00348)
ERROR RATE: 0/36 scripted perf calls (0%); 0 system errors across all manual UAT calls this build
EMPTY REPLY RATE: 0/36 scripted calls, 0 across all manual UAT calls (0%)
VINMEC WEB: DEGRADED (unchanged from BUILD-21; not exercised by this build's own traffic -- no code changes to this path)
ROLLBACK: PASS (3 consecutive live 404s confirmed after AGENT_RUNTIME_ENABLED=false; legacy chat confirmed healthy)
P0/P1/P2: P0=0; P1=0 open (2 found-and-fixed, both in test fixtures/seed scripts, never reached real users: stale V2 dose-data accumulation across re-seeds, missing DoctorWatch row for a new canary doctor); P2=2 open, carried from BUILD-21 (medication_safety_policy has 0 reviewed rows; no other change)
READY FOR FULL PRODUCTION RELEASE: NO
```
