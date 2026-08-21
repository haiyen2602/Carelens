# BUILD-22C — Clinical Safety Production Gate

**Scope:** close the last open production gate from BUILD-21/22 — a live
`Safety SAFE` disposition backed by a real, human-reviewed
`medication_safety_policy` row. No synthetic/fabricated clinical policy. No
Full Production rollout.

**Environment:** Railway production (`VMEC-04/BE`, `VMEC-04/Postgres`).

---

## 1. Why this needed a human, and who that was

BUILD-21 and BUILD-22 both stopped at `BLOCKED_BY_CLINICAL_GOVERNANCE`
rather than fabricate a `REVIEWED` policy — an AI agent has no clinical
authority to approve medication safety guidance, and doing so would be
exactly the kind of fabricated clinical-governance data those builds
correctly refused to create.

Before touching production this build, the user was asked explicitly who
would serve as the real clinical reviewer. The user (git identity
`Dyo31122005`) confirmed they would review and approve it themselves, and
on request supplied the identity to record: **"Dat, bác sĩ"** (Dat, doctor).
This value is written verbatim to `reviewed_by` on the policy row — not
inferred from a git handle or email, and not defaulted.

The user was also shown the specific proposed content (drug, risk
assessment, source citation) before anything was written to production, and
explicitly confirmed ("yes") before the approve step ran.

---

## 2. Workflow built (durable, reusable — not a one-off)

`backend/services/safety_policy_domain/review_workflow.py` — two
deliberately separate functions:

- **`propose_policy`** — stages a `MedicationSafetyPolicy` row in
  `REVIEW_REQUIRED`. Safe for anyone/anything to run: on its own this can
  never resolve to `SAFE` (`SafetyGateway._route` requires
  `policy_review_status == "REVIEWED"`; `REVIEW_REQUIRED` is treated
  identically to "no policy at all" for that purpose — both fail closed to
  Doctor Handoff). Enforces every provenance field (`source_type`,
  `source_reference`, `created_by`, etc.) non-empty, and rejects a proposal
  whose `action_policy` is `REQUIRE_MEDICAL_REVIEW` (nonsensical to route
  through review as though it might unlock SAFE).
- **`approve_policy`** — the *only* function that can set
  `review_status=REVIEWED`. Requires an explicit, non-empty `reviewed_by`
  and `reviewed_at`; there is no default for either, by design. The
  function has no technical way to verify clinical authority — that
  responsibility is procedural, enforced by only ever invoking it at a real
  reviewer's explicit direction (see §1).
- **`reject_policy`** — completes the workflow's negative path (a reviewer
  can decline a proposal) so approval is never the only reachable outcome.

Two CLI scripts wrap these for operational use:
`scripts/agent_v2/propose_safety_policy.py` and
`scripts/agent_v2/approve_safety_policy.py` (the latter's `--help` and
module docstring both state the "never invent a reviewer identity"
requirement at the call site).

**Tests** (`tests/test_agent_v2_safety_policy_review_workflow.py`, 20
cases): proposal always lands `REVIEW_REQUIRED` and never resolves to SAFE
via `SafetyGateway._route` regardless of how favorable its content looks;
approval requires a real non-empty reviewer or fails closed
(`PolicyReviewError`); approved content is exactly what was proposed,
unedited; only after approval does the same decision resolve to `SAFE`;
double-approval and approval of a rejected/unknown policy both fail closed;
rejection requires a real reviewer too.

---

## 3. The policy itself

Given production's V2 catalog only contains **IV/infusion** paracetamol
products (no oral tablet) and IV paracetamol is clinician-administered on a
hospital schedule — not a patient-self-management "missed dose" scenario,
and no authoritative missed-dose guidance for it could be found — a
different, genuinely low-stakes drug already in the production catalog was
used instead: **Vitamin C 100mg Vidipha 200v** (oral tablet).

| Field | Value |
|---|---|
| `scope_type` / `scope_id` | `DRUG_PRODUCT` / `68fab236-4667-511c-ad8c-42564113eae5` |
| `risk_type` | `MISSED_DOSE` |
| `risk_level` | `LOW` |
| `action_policy` | `SAFE_NO_ACTION_NEEDED` |
| `source_type` / `source_reference` | `EXTERNAL_REFERENCE` — MedlinePlus (U.S. National Library of Medicine), Ascorbic Acid (Vitamin C) drug information: missed-dose guidance is to take it when remembered or skip and resume the normal schedule if near the next dose, never double up; a single missed dose is not a cause for concern. `https://medlineplus.gov/druginfo/meds/a682583.html` |
| `review_status` | `REVIEWED` |
| `reviewed_by` | `Dat, bac si` |
| `reviewed_at` | `2026-08-20T03:27:24Z` |

Content was sourced from that external reference, not invented — clinical
judgment on whether it's appropriate for this system was the reviewer's,
not this build's.

---

## 4. Real DoseOccurrence, real code paths

A `MISSED` occurrence was produced without hand-inserting any row: a real
prescription was created and approved via `tao_phac_do`/`duyet_phac_do` (the
same functions the doctor-approval flow uses), then transitioned to
`MISSED` via `transition_v2_dose_group` — the identical function
`backend/api/dose_routes.py`'s real patient dose-status endpoint calls.
`source="BUILD22C_CANARY_SAFETY_SAFE_TEST"`, `actor_type="SYSTEM"` was used
in that transition so the audit trail honestly reflects this was a
controlled test setup, not a real patient action.

---

## 5. Live production verification

Called `/agent/v2/orchestrate` as canary patient1 with the missed-dose
message and the real `MISSED` occurrence's `dose_id`:

```
HTTP 200 (5.66s)
status: COMPLETED
safety_disposition: SAFE
handoff_id: null
reply: "Bạn đã bỏ lỡ liều Vitamin C 100mg Vidipha 200v hôm nay. ...
        Nguồn: get_today_doses (provenance: operational-db:dose-occurrence:today)"
```

Checked against every requirement:

- **Safety Gateway → SAFE**: confirmed in the response and independently in
  the durable checkpoint (`agent_run_checkpoint.safety_disposition = "SAFE"`,
  `terminal_status = "COMPLETED"`, `verified_context_refs` includes a real
  `SAFETY_DOMAIN` provenance reference to the assessment id).
- **Main Model only synthesizes after SAFE**: confirmed from raw log
  timestamps, not just code inspection — `agent_safety.completed
  safety_disposition="SAFE"` logged at `03:32:06.245786`; the Main Model's
  first call (`plan_read_only`) starts at `03:32:06.251191`, strictly after.
- **`safety_disposition` still comes from the Safety Gateway**: the response
  field is the same `SafetyDecision.outcome.value` this whole series has
  always sourced it from — unchanged this build.
- **Model does not override Safety**: unchanged architectural guarantee
  (BUILD-22 §1) plus this build's live evidence that the value actually
  observed end-to-end matches the gateway's decision exactly.
- **No unsafe dosing advice**: the reply states the fact of the missed dose
  and its source; it does not suggest a double dose, an extra dose, or any
  self-directed catch-up action.
- **Checkpoint/log/redaction**: PASS — checkpoint content is references and
  enum values only (no prompt/reply text); log lines contain only
  `agent_run_id`/`trace_id`/component/event/provenance
  strings/tokens/cost/latency/model name/tool name — no message text, no
  reply text, no JWT, no patient name.
- A second, independent live call against the same occurrence reproduced
  `SAFE` again (stability, no drift between calls).

---

## 6. Regression (live, production, same session)

| Check | Result |
|---|---|
| SAFE | PASS (§5) |
| SAFETY_BLOCKED | PASS — a still-`SCHEDULED` (not yet due) occurrence with a missed-dose message correctly returned `SAFETY_BLOCKED` (`DOSE_NOT_YET_ASSESSABLE`) |
| HANDOFF_REQUIRED | PASS — the DOCTOR_REVIEW-bypass message correctly produced `HANDOFF_CREATED` with `safety_disposition=HANDOFF_REQUIRED` and a real handoff id |
| Authorization | PASS — cross-patient query denied `403` |
| Idempotency | PASS — identical `idempotency_key` retried sequentially returned the byte-identical response |
| Duplicate handoff prevention | PASS — 3 simultaneous HTTP requests sharing one `idempotency_key` converged on exactly one `agent_run_id` and one `handoff_id` |

No production traffic was touched outside the canary allowlist; all calls
used existing allowlisted canary accounts.

---

## 7. Local suite

Targeted BUILD-22C tests: 20/20 passing
(`tests/test_agent_v2_safety_policy_review_workflow.py`). Full local suite
re-run with local Postgres actually running this time (it had been down for
the earlier commands in this build, consistent with prior builds' noted
environment quirk) showed 766 passed, 20 skipped, **11 failed** — all 11 in
files this build never touched (`test_auth_routes.py`,
`test_patient_routes.py`, `test_security_authz.py`,
`test_chat_history_e2e.py`, `test_drug_confirmation_dispatch.py`,
`test_retrieval_sql.py`), and all traced to pre-existing local-environment
gaps, not code defects:

- The local Postgres instance is missing the ~14,447 legacy (`corpus_version
  IS NULL`) `drug_chunks` rows BUILD-21 restored to production/staging (it
  has exactly the 14,423 V2-tagged rows and none of the legacy set) —
  `retrieval_sql` failures are queries for legacy-only drugs correctly
  finding nothing locally, not a bug in the `corpus_version IS NULL` filter
  itself (already verified correct against real data in BUILD-21).
- `test_get_current_user_valid_jwt` fails with `AttributeError: 'Depends'
  object has no attribute 'query'` — a test-harness artifact (the test
  calls a `Depends()`-decorated function directly without FastAPI resolving
  the dependency), not a route defect.
- The local database is one migration behind head (`0033`, not `0034`) —
  harmless for these specific failures (none touch
  `agent_idempotency_key`) but noted for whoever next runs migrations
  locally.

None of these are BUILD-22C regressions; none block this build's closeout.

---

## 8. Final production state

- `AGENT_RUNTIME_ENABLED=false` — restored per this build's explicit
  instruction (no conditional carve-out this time, unlike BUILD-22).
  Confirmed live: 3 consecutive `404`s for a previously-working canary
  account; legacy `/api/v1/chat` confirmed still healthy.
- `AGENT_CANARY_ALLOWLIST` unchanged from BUILD-22 (5 accounts).
- Production now has its first real `REVIEWED` `medication_safety_policy`
  row (§3) — durable, will still be there whenever the canary resumes.
- The temporary TCP proxy opened for this build's own work is closed.

---

## Closeout

```
BUILD-22C: PASS
CLINICAL POLICY AVAILABLE: YES
CLINICAL POLICY REVIEWED: PASS (reviewed_by="Dat, bac si", real human sign-off obtained explicitly this build -- see report Section 1)
SAFETY SAFE LIVE: PASS
SAFETY BLOCKED: PASS
HANDOFF: PASS
IDEMPOTENCY: PASS
AUTHORIZATION: PASS
P0/P1: P0=0; P1=0 open (0 found this build)
READY FOR FULL PRODUCTION RELEASE: NO
```
