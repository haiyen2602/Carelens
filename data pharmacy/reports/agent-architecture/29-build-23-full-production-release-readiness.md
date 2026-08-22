# BUILD-23 — Full Production Release Readiness & Cutover Plan

**Scope:** audit everything BUILD-21/22/22C built, design and build the
mechanism a real gradual rollout needs, and produce an executable cutover
procedure. **No traffic percentage was turned on. No legacy data was
touched or deleted.**

**Environment:** Railway production (`VMEC-04/BE`, `VMEC-04/Postgres`).

---

## 1. Final production audit

| Item | Status | Evidence |
|---|---|---|
| Migrations at head | PASS | `alembic_version = 0034`, matches repo head |
| Model keys present | PASS | `OPENAI_API_KEY` set (see §7 — an incident occurred while checking this) |
| Pricing config | PASS | `AGENT_MODEL_PRICING_JSON` populated, all 5 models, unchanged since BUILD-21 |
| Safety policy governance | PASS with a scope caveat | 1 `REVIEWED` policy exists (BUILD-22C); see §5 for whether it's *sufficient*, not just *present* |
| Authorization | PASS | `DoctorWatch`-based boundary confirmed live with real data (385 rows); canary allowlist mechanism unchanged and tested |
| Idempotency / checkpoint | PASS | 150 `agent_run_checkpoint` rows, **0** stuck non-terminal; 9 `agent_idempotency_key` rows, **0** stuck `IN_PROGRESS` — every run from every prior build's testing terminalized cleanly, nothing orphaned |
| Doctor Handoff | PASS | 14 `doctor_review_request` rows, all from accounted-for canary testing, no unexplained duplicates |
| Observability / redaction | PASS | Unchanged from BUILD-22C's live-verified clean redaction; see §7 for an unrelated incident during *this build's own* audit tooling (not a redaction defect in the product) |
| Backup / rollback | **PARTIAL — see below** | |

**Backup**: application-level rollback (kill switch, legacy fallback) has now
been proven live and repeatedly across BUILD-21/22/22C. **Database-level
backup (point-in-time recovery) was not independently verified this
build** — the Railway CLI available here has no `backup` subcommand, and
`pg_dump` is not installed in this environment, so neither an automated-
backup-is-enabled check nor a manual dump could be executed directly.
**Action item, not fabricated as done**: confirm via the Railway dashboard
(Settings → Backups) that automated backups/PITR are enabled for the
production Postgres service before any cutover stage beyond the smallest
controlled one, or arrange a scripted `pg_dump` from an environment that has
Postgres client tools.

---

## 2. Data audit — corrected understanding of "V2 data"

Re-tracing every actual code path (not just re-stating BUILD-21's own
description of itself) surfaced that this codebase's "V2" has **three
distinct meanings**, and the prior reports' shorthand ("the V2 corpus")
blurred them. Correcting that here:

1. **DB Architecture V2 (relational)** — `drug_product`, `drug_id_map`,
   `drug_product_ingredient`, `prescription_item`, `dose_occurrence`,
   `agent_run`, etc. Genuinely V2-exclusive: legacy chat never touches these
   tables; every Agent V2 structured tool (`get_active_prescriptions`,
   `get_today_doses`, ...) reads only these, gated by
   `PRESCRIPTION_V2_MODE`/`DOSE_RUNTIME_MODE=shadow`. **No mixing — confirmed
   again this build.**

2. **Canonical V2 drug knowledge (file-backed)** —
   `backend/services/drug_knowledge/v2_agent.py`, reading
   `data pharmacy/v2/final_canonical/*.jsonl` baked into the Docker image
   (not a database table at all). This is what the `search_drug` tool
   actually calls (`get_v2_agent_knowledge_service().search_catalog(...)`),
   and `search_drug` is the tool behind `DRUG_INFORMATION` — the single most
   common intent in every scenario tested across this whole series.
   Governed by `drug_knowledge_backend` (default `"v2"`; confirmed **not
   overridden** on production, so the default is what's live). This is
   genuinely, exclusively V2 — legacy chat has no code path into this
   module at all. **No mixing.**

3. **The shared `drug_chunks` RAG table** — used by legacy `/api/v1/chat`
   *and* by Agent V2's `RetrievalGateway` (only for the `GENERAL_MEDICAL_
   INFORMATION` intent — open-ended questions not tied to a known drug).
   `backend/services/agent_retrieval.py`'s own docstring says this
   *"reuses the approved legacy pgvector + RRF retrieval"* — by original
   design, not by accident. BUILD-21 added `corpus_version IS NULL` to
   every query in `backend/services/retrieval.py`, which both callers go
   through identically — so there is **no cross-contamination between the
   two callers** (re-verified this build: every query still filters
   consistently, counts unchanged at 14,447 legacy / 14,423 other / 28,870
   total). But this table also holds a **second corpus generation**
   (`corpus_version = 'legacy-drug-chunks-openai-v1'`, restored in BUILD-21)
   that is a *deterministically-rebuilt copy of the same legacy corpus*
   (per `rag_corpus_recovery.py`'s own docstring: "recovery primitives for
   the OpenAI-backed **legacy** RAG corpus") — not a separate V2-only
   corpus. **Nothing live queries it today.** It is not a mixing risk (no
   query ever reads across both generations at once), but it is currently
   inert, restored capacity with no consumer.

**Net assessment**: "Agent V2 chỉ sử dụng Data/RAG V2" is **true for the two
genuinely V2-specific paths** (structured relational tools, and the
dominant `search_drug`/Canonical-V2 path) and **not applicable in the way
the question assumes** for the shared RAG table, which was designed to be
shared and has been kept safely, verifiably single-generation for both
callers rather than incorrectly mixed. **No corpus mixing exists anywhere
in the live system.** No legacy data was touched, deleted, or at risk.

**Archive plan (design only, not executed)**: once cutover is stable at
100% for an observation period (§6) and a decision is made on whether
`GENERAL_MEDICAL_INFORMATION` should ever move onto the recovered
`legacy-drug-chunks-openai-v1` generation instead of the original, the
*unused* generation — or, if that decision is made, the *original* one it
would replace — is the one to archive: `pg_dump --table=drug_chunks
--where="corpus_version = '<generation to retire>'"` to cold storage, then
delete only after a second, independent row-count/hash verification
(mirroring `restore_rag_corpus_into_populated_drug_chunks.py`'s own
before/after verification discipline). This build does not decide which
generation that will be — that's a retrieval-quality question for a future
build, not a production-safety one.

---

## 3. Release strategy — the gradual-rollout mechanism now exists

Before this build, the only two states were "flag off" and "flag on for an
explicit allowlist" — there was no way to route an arbitrary percentage of
real traffic at all. Built this build:

- `Settings.agent_rollout_percentage` (0–100, default 0 — inert).
- `backend/api/agent_v2_routes.py::_in_rollout_percentage`: deterministic
  `sha256(actor_id) mod 100 < percentage` bucketing. Stable per actor
  (same account always lands in the same bucket) and **monotonic** as the
  percentage grows — an account admitted at 5% stays admitted at every
  later, larger stage, never flip-flopping as the threshold moves. Not
  randomized per request (a fresh coin flip every call would make canary
  monitoring meaningless and "roll back a bad cohort" impossible).
- `_require_agent_v2_enabled` now grants access if the actor is on the
  allowlist **or** inside the rollout-percentage bucket, on top of the
  unchanged outer flag. **Zero behavior change when neither is configured**
  (both default empty/0) — every prior build's tests and UAT relied on the
  flag alone, and that is still exactly true.

9 new tests (`tests/test_agent_v2_route.py`): determinism, monotonic
inclusion across the full 1–100% range, a distribution sanity check (not a
statistical proof, just confirms the hash isn't degenerate), 100% admits
everyone, 0% + no allowlist is unchanged, the flag still overrides
everything, allowlist members are never bucket-dependent, and non-admitted
callers still get the identical indistinguishable-from-disabled 404. All
passing, alongside the full existing Agent V2 suite (no regressions).

Deployed to production **inert**: `agent_rollout_percentage` is unset
(defaults to 0); confirmed live that `AGENT_RUNTIME_ENABLED` is still
`false`. This build does not turn any percentage on.

### What monitoring after each stage means concretely

For every stage (5/20/50/100), the same battery already exercised live
across BUILD-21/22/22C applies: error rate, empty reply rate, P95/P99
latency, cost/request, Safety SAFE/BLOCKED/HANDOFF_REQUIRED distribution,
Doctor Handoff creation/dedup, authorization denials, RAG
`no_source_found`/budget-excluded rates, and `BUDGET_EXCEEDED`/`TIMEOUT`
counts — all already have working live measurement tooling
(`scripts/agent_v2/staging_performance_batch.py` and the ad hoc live-check
pattern used throughout this series). No new measurement tooling was
needed; the gap was strictly the routing mechanism itself.

---

## 4. Vinmec Web

**Does not block Full Production**, stated explicitly: Vinmec Web is
optional evidence for exactly one intent (`VINMEC_WEB_INFORMATION`); every
other intent — including all Safety-relevant ones — never calls it.
`AGENT_VINMEC_WEB_ENABLED=true`, DEGRADED (honest zero-citation fallback,
no fabricated citation, never blocks a clinical answer) — unchanged since
BUILD-21, not re-tested live this build (no code changes to this path; see
BUILD-22 §5 for the same carry-forward reasoning). This status is safe to
carry into every stage of the cutover plan as-is; DEGRADED is not, by
itself, a release blocker.

---

## 5. Clinical governance — is the current REVIEWED policy valid *for this*?

The one `REVIEWED` `medication_safety_policy` row (Vitamin C, BUILD-22C) is
**workflow-valid** by every check the system itself enforces: real
non-fabricated human identity (`reviewed_by = "Dat, bac si"`), real
timestamp, content sourced from an authoritative external reference
(MedlinePlus), unedited between proposal and approval, obtained through the
user's own explicit, deliberate confirmation in this engagement.

It is **not**, honestly, the same thing as an institutional clinical
governance process: no credential verification (medical license,
specialty, employment/affiliation), no second reviewer or committee
sign-off, no binding to a real authenticated `Account` row with a verified
`role=doctor`, and it covers exactly **one drug**. A real hospital-grade
deployment serving the general patient population at scale would normally
expect more than this before relying on it broadly.

**Why this does not, by itself, block starting the smallest cutover stage**:
the system's own fail-closed design means governance *breadth* directly
bounds blast radius. `SafetyGateway._route` only returns `SAFE` for a
policy that is `REVIEWED` — with exactly one such policy in existence,
**every other drug's missed/delayed dose still correctly resolves to
`HANDOFF_REQUIRED`, exactly as it did before this policy existed.** A wider
rollout does not multiply clinical risk from this gap; it only multiplies
exposure to the *one* reviewed, sourced, human-approved policy that
exists, plus more `HANDOFF_REQUIRED` deferrals for everything else — never
a fabricated `SAFE`.

**Recommendation, not a hard stop**: sufficient to justify a small,
closely-monitored first stage (5%); **before scaling past that**, get a
real institutional process in place — verified reviewer credentials, more
than one policy, and ideally a second reviewer or a defined clinical safety
sign-off procedure at the organization level. This is a recommendation for
the *next* build to act on, not a fabricated pass dressed as full
governance.

---

## 6. Cutover plan (procedure, not executed)

```
Stage 0 -- Legacy primary (current state)
  AGENT_RUNTIME_ENABLED=false
  Legacy /api/v1/chat serves 100% of traffic, unchanged.

Stage 1 -- V2 canary (already done, BUILD-21/22/22C)
  AGENT_RUNTIME_ENABLED=true
  AGENT_CANARY_ALLOWLIST=<explicit test/internal accounts>
  AGENT_ROLLOUT_PERCENTAGE unset (0)
  Legacy still serves every account not on the allowlist.

Stage 2 -- V2 5%
  AGENT_ROLLOUT_PERCENTAGE=5
  Monitor (see Section 3) for a defined minimum observation window
  (recommend >= 48h or a fixed minimum real-traffic sample size, whichever
  is longer, before advancing).
  Gate: any P0, or any Safety/Auth/Data-integrity P1 -> immediate rollback
  to Stage 1 (AGENT_ROLLOUT_PERCENTAGE=0), not just "pause".

Stage 3 -- V2 20%
  AGENT_ROLLOUT_PERCENTAGE=20
  Same monitoring + gate. Accounts already admitted at 5% remain admitted
  (monotonic bucketing -- no churn).

Stage 4 -- V2 50%
  AGENT_ROLLOUT_PERCENTAGE=50
  Same monitoring + gate. This is the first stage where legacy and V2 each
  serve a comparable share of real traffic -- watch cost/request and P95
  drift most closely here, since production-scale concurrency has not been
  exercised by any canary batch so far.

Stage 5 -- V2 100%
  AGENT_ROLLOUT_PERCENTAGE=100
  Legacy code path remains deployed and reachable -- this is "V2 primary",
  not "legacy removed".

Stage 6 -- Observation period at 100%
  Fixed minimum duration (recommend >= 1 week) before touching legacy code
  or data at all. This is the stage that actually earns "stable."

Stage 7 -- Legacy fallback readiness confirmed
  Re-run the exact kill-switch test from BUILD-21/22/22C
  (AGENT_RUNTIME_ENABLED=false -> 3 consecutive 404s, legacy /api/v1/chat
  still healthy) AT 100% traffic, not just during canary -- this has never
  actually been proven at full scale, only at the allowlist's tiny scale.
  Only after this passes is Stage 6 considered genuinely closed.

Stage 8 -- Legacy decommission planning (NOT decommissioning)
  Only after Stage 7 passes and a separate, explicit decision is made.
  This build explicitly does not schedule or approve this step.
```

Rollback at every stage is the same single action:
`AGENT_ROLLOUT_PERCENTAGE=0` (or `AGENT_RUNTIME_ENABLED=false` for a full
kill), both already live-tested primitives, not new mechanisms invented for
this plan.

---

## 7. Incident during this build's own audit

While checking model keys were present, a broken `sed` redaction pattern
printed the **full production `OPENAI_API_KEY`** in plaintext into this
session (my error, not a product defect — no application code logs or
exposes this key; this was this build's own audit tooling). The user was
told immediately and asked to rotate the key. **This value does not appear
anywhere in this report.** Whether rotation has completed should be
confirmed before treating "model keys present" as durably true, since the
key checked in §1 may since have been intentionally invalidated.

---

## Closeout

```
BUILD-23: PASS
V2 DATA READY: PASS
V2 ARCHITECTURE READY: PASS
CLINICAL GOVERNANCE: PASS (workflow-valid, real non-fabricated sign-off; scope is minimal -- one drug, one reviewer, no institutional credential process -- see report Section 5 for why this still safely bounds a 5% start but should widen before scaling further)
SECURITY/SAFETY: PASS
OBSERVABILITY: PASS (see Section 7 for an unrelated tooling incident this build, not a product redaction defect)
PERFORMANCE: PASS
COST: PASS
VINMEC WEB: DEGRADED
ROLLBACK: PASS (allowlist-scale proven repeatedly; NOT yet proven at 100% traffic scale -- see Section 6 Stage 7, which this build schedules but does not execute)
LEGACY FALLBACK: PASS (mechanism proven; full-scale proof deferred to Stage 7, after 100% cutover)
P0/P1: P0=0; P1=0 open in product code (0 found this build); 1 operational item open -- database backup/PITR status unverified with available tooling (Section 1); 1 incident this build's own audit caused and disclosed -- OPENAI_API_KEY printed in plaintext, rotation requested (Section 7)
READY TO START 5% PRODUCTION CUTOVER: YES
READY TO DELETE LEGACY DATA: NO
```
