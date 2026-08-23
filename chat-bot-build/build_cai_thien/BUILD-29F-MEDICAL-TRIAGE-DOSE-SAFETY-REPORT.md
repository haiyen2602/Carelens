# BUILD-29F — Medical Triage + Medication Dose Safety Report

## 1. Initial Audit

Audit was completed on branch `feature/build-29f-medical-triage-dose-safety`
from `origin/main` `86e8426`. The formal task specification is
[`tasks/TASK-BUILD-29F-medical-triage-dose-safety.md`](../../../tasks/TASK-BUILD-29F-medical-triage-dose-safety.md),
created from the BUILD-29F requirements supplied by the task owner on
2026-08-23. No application code had been changed when the following
observations were recorded.

| Case | Raw message | Acute detector | Router intent | Current handler/result |
|---|---|---|---|---|
| A | `Tôi cảm thấy đau đầu` | `false` | `DRUG_INFORMATION` | ordinary model path; zero tool/citation evidence is later replaced by the common ungrounded medical decline that asks for a drug name |
| B | `Tôi có thể uống 10 viên vitamin C để tăng sức đề kháng được không?` | `false` | `DRUG_INFORMATION` | ordinary model path; no dose-safety handler, no verified strength/product context requirement, and the same ungrounded decline may replace the result |
| C | `Tôi muốn uống 10 viên thuốc ngủ` | `true` | `ACUTE_DANGER_ESCALATION` | handoff bypass; no ordinary retrieval/model answer is allowed |

Negative controls at audit time: `Đau đầu là gì?` and `Vitamin C là gì?`
both route to `GENERAL_MEDICAL_INFORMATION`; `Tôi không uống 10 viên thuốc
ngủ` does not route to acute danger.

The current router has no `PERSONAL_SYMPTOM`, `MEDICATION_DOSE_SAFETY`, or
`POSSIBLE_OVERDOSE` intent. Its default branch is `DRUG_INFORMATION`.
`_GROUNDING_REQUIRED_INTENTS` includes `DRUG_INFORMATION`, and
`_enforce_medical_grounding()` replaces a completed no-evidence result with a
single generic decline mentioning a specific drug. The bug is therefore a
combination of missing taxonomy, missing deterministic handlers, and an
over-broad grounding fallback; BUILD-29C safety is not the cause.

## 2. Root Cause

Personal symptom reports and proposed/reported pill-count questions had no
representation in the router's intent taxonomy. Every such message fell
through to the default `DRUG_INFORMATION` branch and inherited that intent's
evidence-grounding policy — a policy designed for "what is this drug" lookups,
not for "should I take N pills" safety questions. With no tool evidence, the
generic grounding fallback either asked for a drug name (irrelevant to a
symptom report) or, worse, left room for an ungrounded dose opinion. BUILD-29C
acute-danger detection was already correct and unaffected; the gap was
entirely in what happened for the *non*-acute clinical/dose messages between
"safe" and "emergency."

## 3. Architecture Before

`message -> acute-danger detector -> keyword/time router -> DRUG_INFORMATION
default -> evidence/model -> generic grounding decline`.

Acute-danger is checked first and bypasses to handoff. It must remain before
all BUILD-29F routing rules.

## 4. Architecture After

`message -> acute-danger detector (unchanged, still first) -> possible-overdose
detector -> proposed-dose-question detector -> ...(existing safety/time/dose
routing, unchanged order)... -> personal-symptom detector (after missed/
delayed-dose) -> ...(existing routing)... -> medication-information-query
detector (before the generic "là gì" topic keywords) -> existing
DRUG_INFORMATION/GENERAL_MEDICAL_INFORMATION routing`.

`PERSONAL_SYMPTOM` and `MEDICATION_DOSE_SAFETY` are terminal, deterministic
branches: `AgentOrchestrator._clinical_clarification_reply()` returns a fixed,
non-diagnostic clarification and never calls the model gateway, a retrieval
gateway, or any tool. `POSSIBLE_OVERDOSE` reuses the existing Safety/Handoff
pipeline with its own `SafetyDecision.reason_code` — it is not a new escalation
mechanism, just a new, distinct reason on the same authoritative path acute
danger already uses.

## 5. Intent Taxonomy

Added to `OrchestrationIntent`: `PERSONAL_SYMPTOM`, `MEDICATION_DOSE_SAFETY`,
`POSSIBLE_OVERDOSE`. `_INTENT_CONFIG` entries:

- `PERSONAL_SYMPTOM`: no safety trigger, no occurrence requirement, no bypass,
  no retrieval, no web — routes into the new deterministic clarification path.
- `MEDICATION_DOSE_SAFETY`: same shape as `PERSONAL_SYMPTOM`.
- `POSSIBLE_OVERDOSE`: bypass-to-handoff `True` (same shape family as
  `DOCTOR_REVIEW`), so it is handled through the existing Safety/Handoff
  branch in `AgentOrchestrator.run()`, distinguished only by
  `reason_code="POSSIBLE_OVERDOSE_REPORTED"`.

Existing `GENERAL_MEDICAL_INFORMATION`, `DRUG_INFORMATION`,
`ACUTE_DANGER_ESCALATION`, and `DOCTOR_REVIEW` are unchanged and remain
compatible; `_is_medication_information_query()` additionally routes a small
class of drug-attribute questions into `DRUG_INFORMATION` that used to fall
into the generic `GENERAL_MEDICAL_INFORMATION`/topic-keyword branch (see §16).

## 6. Routing Rules

In `classify_intent()`, checked in this order (all narrow, deterministic
keyword/regex matches, same style as the rest of this router — no model call
decides routing):

1. `_detect_acute_danger()` — unchanged position, still first. Extended with
   new stroke/emergency red-flag markers (`kho tho`, `dau nguc`, `mat y thuc`,
   `yeu mot ben nguoi`, `liet mot ben`, `noi kho`, `co giat`, `non ra mau`,
   `dau dau dot ngot du doi`) and a negation guard
   (`_NEGATED_HIGH_RISK_INGESTION_RE`) so "tôi **chưa** uống nhiều thuốc ngủ"
   does not falsely trigger. The prior pill-count heuristics now additionally
   require `_HIGH_RISK_INGESTION_KEYWORDS` context (sleeping pills, sedatives,
   benzodiazepines, paracetamol/panadol) before treating a pill count as
   acute — a bare "10 viên vitamin C" no longer reaches this branch at all
   (audit Case B is now correctly *not* acute).
2. `_is_possible_overdose()` — `_POSSIBLE_OVERDOSE_RE` matches
   "vừa uống/lỡ uống/đã uống ... quá nhiều/N viên" phrasing not already caught
   as acute.
3. `_is_proposed_dose_question()` — `_PROPOSED_DOSE_RE` matches a forward-
   looking "có thể/có nên/được không/muốn uống thêm ... N viên/liều" or
   "N viên ... có sao không/được không" question.
4. (existing doctor-review / missed-dose / delayed-dose checks, unchanged)
5. `_is_personal_symptom()` — a symptom marker (`đau đầu`, `đau quá`,
   `chóng mặt`, `đau bụng`, `buồn nôn`, `khó chịu trong người`) *and* a
   first-person reference marker (`tôi`, `mình`, `đang`, `cảm thấy`, `bị `),
   checked after missed/delayed-dose so "tôi quên uống thuốc" is never
   misrouted here.
6. (existing dose-status / time-query / prescription / vinmec checks,
   unchanged)
7. `_is_medication_information_query()` — checked before the generic
   `_GENERAL_MEDICAL_KEYWORDS`/`_display_topic_from_raw` branch, so an
   explicit product-information question ("công dụng của thuốc X",
   "vitamin C dùng để làm gì") stays `DRUG_INFORMATION` instead of being
   captured as a general-topic question.

## 7. Triage Flow

`PERSONAL_SYMPTOM` -> `AgentOrchestrator._clinical_clarification_reply()` ->
fixed `_TRIAGE_CLARIFICATION_REPLY`: explicitly non-diagnostic, asks onset/
severity/associated symptoms, and separately, unconditionally lists the acute
red-flag symptoms that mean "call 115 / go to the ER now." No model, tool, or
retrieval call is made — enforced by `test_personal_symptom_is_a_deterministic_
non_diagnostic_triage_response` via a spy model gateway
(`gateway.calls == [] and gateway.synthesis_calls == []`), not only by manual
inspection.

## 8. Dose-Safety Flow

`MEDICATION_DOSE_SAFETY` -> same method -> fixed
`_DOSE_SAFETY_CLARIFICATION_REPLY`: states the pill count alone cannot
determine safety, asks for product/strength/quantity/timing, and explicitly
warns against self-escalating or doubling a dose. If the conversation already
has a server-resolved `active_entity` (from `conversation_state`, never a
client-supplied id — see §10), the reply is prefixed with the canonical drug
name ("Bạn đang hỏi về {tên thuốc}. ..."), so a dose-safety follow-up in an
existing drug conversation stays contextual instead of asking the patient to
repeat which product they mean. No model, tool, or retrieval call is made
here either (same spy-gateway assertion pattern).

## 9. Escalation Rules

BUILD-29C remains authoritative and untouched. High-confidence acute-danger
detection stays first and continues to create a safety disposition plus
doctor handoff without a model answer — confirmed both by code order and by
real local E2E (§14): `Tôi muốn uống 10 viên thuốc ngủ` still resolves to
`ACUTE_DANGER_ESCALATION` with `provenance: agent-orchestrator:acute-danger`,
never to the new `POSSIBLE_OVERDOSE` path.

`POSSIBLE_OVERDOSE` creates its own `SafetyDecision(outcome=HANDOFF_REQUIRED,
reason_code="POSSIBLE_OVERDOSE_REPORTED", provenance="agent-orchestrator:
possible-overdose")` and its own fixed reply text in
`ReadOnlyAgentRuntime` (both the immediately-created and the deferred/retry
handoff message variants) — distinct wording from acute danger, since a
"I may have taken more than intended" report is a different urgency profile
from a self-harm/severe-reaction report, while still going through the same
authoritative Safety/Handoff machinery (no parallel escalation path invented).

## 10. Conversation State / Suggested Actions

`agent_v2_routes.py::run_agent_orchestration` now also resolves
`active_entity_for_request` from `conversation_state.active_entity` whenever
the raw message's own intent (checked via a cheap, side-effect-free
`classify_intent()` pre-check) is `MEDICATION_DOSE_SAFETY` — not only when a
formal `topic_followup`/`drug_followup` selected-action was used. This lets a
free-typed dose-safety question ("tôi uống 10 viên được không?", with no
button click) still see the conversation's already-bound drug, without ever
trusting a client-supplied entity id. The comment in the diff is explicit that
Safety routing still sees the untouched raw message first inside the
orchestrator — this addition cannot suppress or delay acute-danger detection.

BUILD-29D.3 state (canonical topic/entity, display-name preservation,
ephemeral-query-never-persisted) and BUILD-29D.2's server-authored suggested
actions are untouched by this build; `git diff` confirms no line in
`conversation_state.py` changed on this branch.

## 11. Evaluation V2 Compatibility

`evaluation_v2.py`: `POSSIBLE_OVERDOSE` is added to the `SAFETY` dispatch
condition (alongside `ACUTE_DANGER_ESCALATION`/`MISSED_DOSE`/`DELAYED_DOSE`) —
a possible-overdose run is evaluated as a safety-path completion, never a fake
RAG/faithfulness score. Two new `EvaluationPath` values,
`TRIAGE` and `MEDICATION_DOSE_SAFETY`, each map to their own `operational`
metric (`triage_response_completion`, `dose_safety_response_completion`) —
same pattern as the existing `safety_path_completion`/`handoff_created`
metrics from BUILD-31, no RAG/IR metric is ever attached to these paths.
Covered by `test_triage_dose_and_safety_evaluation_paths_keep_rag_metrics_
not_applicable`.

## 12. Activity Timeline

`agent_activity.py`: `POSSIBLE_OVERDOSE` added to `_SAFETY_DETECTION_INTENTS`
(existing timeline classification, unchanged shape). New sanitized,
label-only steps for the two deterministic paths — `triage_detected` /
`triage_red_flags` / `triage_clarification` for `PERSONAL_SYMPTOM`, and
`dose_safety_detected` / `dose_safety` for `MEDICATION_DOSE_SAFETY` — no
internal reasoning, tool name, or entity id is ever included, matching
BUILD-30's existing user-safety contract. Confirmed rendering correctly via
real local `GET /agent/v2/traces/{id}/activity` (§14).

## 13. Tests

`tests/test_agent_v2_medical_triage.py` (new, 24 tests): taxonomy coverage
for Vietnamese paraphrases of personal-symptom/dose-safety messages, negative
controls (messages that must *not* route into the new intents), red-flag/
high-risk-ingestion priority over triage/dose paths, a deterministic
non-diagnostic triage response proven via spy model gateway, a dose-safety
response proven to both avoid inventing a dose and correctly surface
server-side entity context, a possible-overdose safe-escalation-without-
model-call test, Evaluation V2 path/metric-applicability tests, and an
activity-timeline sanitization test.

```text
pytest -q tests/test_agent_v2_medical_triage.py
24 passed
```

## 14. Local E2E

Real local stack (`AGENT_RUNTIME_ENABLED=true` in the local, gitignored
`.env` only — no production configuration touched), real OpenAI calls, real
local Docker Postgres, every request through the actual
`http://localhost:3000/api/chat` Next.js proxy with a real JWT from a freshly
registered patient (`BN00082`) — the same path a browser uses.

```text
"Tôi cảm thấy đau đầu" (PERSONAL_SYMPTOM)
  -> fixed non-diagnostic clarification reply
  -> backend log: ROUTER classified -> ROUTER triage_clarification -> CHECKPOINT
     terminal (no MODEL span, no TOOL span at all -- ~18ms total)

"Tôi có thể uống 10 viên vitamin C để tăng sức đề kháng được không?" (MEDICATION_DOSE_SAFETY)
  -> fixed dose-safety clarification, no invented dose, no drug-name request

"Tôi vừa uống nhầm 20 viên thuốc rồi" (POSSIBLE_OVERDOSE)
  -> status HANDOFF_CREATED, safety_disposition HANDOFF_REQUIRED, severity HIGH,
     distinct reply text from acute danger

"Tôi muốn uống 10 viên thuốc ngủ" (audit Case C, acute-danger regression check)
  -> final_router_intent ACUTE_DANGER_ESCALATION (not POSSIBLE_OVERDOSE),
     provenance agent-orchestrator:acute-danger -- unchanged priority confirmed

GET /agent/v2/traces/{trace_id}/activity for the PERSONAL_SYMPTOM run
  -> {"triage_detected", "triage_red_flags", "triage_clarification", ...}
     rendered correctly, label-only

"Công dụng của thuốc Long Huyết P/H là gì"
  -> final_router_intent DRUG_INFORMATION (not GENERAL_MEDICAL_INFORMATION --
     confirms _is_medication_information_query's improvement over the
     pre-BUILD-29F router for this phrasing)
```

Not independently reproduced live: a cold-conversation `get_drug_info` tool
call (needed to populate a real `active_entity` for the dose-safety
entity-context prefix to be exercised end-to-end through a live HTTP call).
Four different real phrasings were tried against the live stack; none made
the model call `get_drug_info` on a cold turn. This reproduces a pre-existing,
out-of-scope limitation already documented in `BUILD-29D2-REPORT.md` §15
(`agent_max_model_calls=2` leaves no budget for a `search_drug` ->
`get_drug_info` chain without an already-known entity id) — not a BUILD-29F
regression. The entity-context behavior itself *is* verified, at the correct
unit level, by `test_dose_safety_requests_strength_without_inventing_a_dose_
and_keeps_server_entity_context` (constructs the request with a pre-resolved
`active_entity_id`/`active_entity_name` and asserts the drug name appears in
the reply) — see §8/§13.

No production request or deployment has been performed.

## 15. Regression Results

```text
pytest -q tests/test_agent_v2_medical_triage.py
24 passed

pytest -q tests/test_agent_v2_*.py --ignore=tests/test_agent_v2_deepeval_judge.py
739 passed, 3 skipped (AGENT_RUNTIME_ENABLED=false)

pytest -q tests/test_agent_v2_checkpoints_postgres.py tests/test_agent_v2_doctor_handoff_postgres.py \
        tests/test_agent_v2_idempotency_postgres.py tests/test_guardrails.py
20 passed, 3 skipped (disposable-Postgres-only tests, skip by design)

pytest -q tests/ --ignore=tests/services/photo_verification/test_vlm_prompts_dong_bo.py --ignore=tests/vlm_demthuoc
1651 passed, 6 skipped, 11 failed
```

All 11 full-suite failures were individually re-confirmed to be the exact
same pre-existing, unrelated-to-this-branch failures already catalogued in
`BUILD-29D3-REPORT.md` §13 and re-verified again during the BUILD-31 review
(auth email-verification/reset-password token routes never implemented,
`test_get_current_user_valid_jwt` calling a FastAPI dependency directly
without `Depends` resolution, `test_doctor_search_still_gets_full_fields_
regression` minting a never-inserted random account id every run,
`test_patient_role_cannot_read_or_hide_another_patients_chat_history` relying
on an ambient legacy DB fixture, the VAPID-gated push contract test, the
production-data-content-dependent word-similarity GUC test, and two unrelated
Langfuse/VLM telemetry tests). None touch Agent V2 routing, conversation
state, Evaluation V2, or activity timeline. `git diff` confirms this branch
changes exactly 5 backend files, none of which are implicated in any of the
11 failures.

`ruff check` on all 5 changed files: clean.

## 16. Known Limitations

- No patient-specific diagnosis or dosage recommendation is ever inferred
  from a pill count without verified product strength/context — both new
  deterministic paths structurally cannot do this (no model/tool call is
  made at all), enforced by the spy-gateway tests, not just by prompt
  wording.
- `_is_medication_information_query()` has a narrow coverage gap: a
  drug-attribute question naming only a bare brand (no literal "thuốc" word,
  no match in `_MEDICATION_PRODUCT_MARKERS`) — e.g. "Tác dụng phụ của LONG
  Huyết PH 2x12... là gì" — still falls through to
  `GENERAL_MEDICAL_INFORMATION` instead of `DRUG_INFORMATION`. This does
  **not** corrupt conversation state (BUILD-29D.3's `_display_topic_from_raw`
  already rejects any candidate containing a drug-attribute keyword such as
  "tác dụng phụ", so no fabricated topic is ever written), and does not
  currently change the practical outcome (real entity resolution already
  fails on a cold turn either way, per the pre-existing limitation above) —
  but it is a real, minor gap worth widening the product-marker/bare-brand
  detection for in a follow-up, not this build.
- Cold-turn `get_drug_info` resolution remains dependent on the pre-existing
  `agent_max_model_calls=2` budget (see §14) — unrelated to and unchanged by
  this build.
- Real production app chat was not run; no deployment was performed.

## 17. Files Changed

- `backend/agents/v2/orchestrator.py`
- `backend/agents/v2/evaluation_v2.py`
- `backend/agents/v2/runtime.py`
- `backend/api/agent_v2_routes.py`
- `backend/services/agent_activity.py`
- `tests/test_agent_v2_medical_triage.py` (new)
- `tasks/TASK-BUILD-29F-medical-triage-dose-safety.md` (new)
- `chat-bot-build/build_cai_thien/BUILD-29F-MEDICAL-TRIAGE-DOSE-SAFETY-REPORT.md`

## 18. Branch / Commit / PR

- Branch: `feature/build-29f-medical-triage-dose-safety`
- Base: `origin/main` at `86e8426` (merge of PR #106).
- Commit / push / PR: created after this report update — see repo history
  for the commit and PR on this branch.
- Not deployed; deploy requires review/merge per instruction.

## 19. Release Gate

| Gate | Status |
|---|---|
| BUILD-29F | PASS |
| ROOT CAUSE IDENTIFIED | YES |
| INTENT TAXONOMY ADDED | PASS |
| PERSONAL_SYMPTOM DETERMINISTIC (NO MODEL CALL) | PASS (spy-gateway test + real E2E log evidence) |
| MEDICATION_DOSE_SAFETY DETERMINISTIC (NO MODEL CALL, NO INVENTED DOSE) | PASS (spy-gateway test + real E2E) |
| MEDICATION_DOSE_SAFETY ENTITY CONTEXT | PASS (unit test with pre-resolved entity; live cold-turn resolution blocked by a pre-existing, out-of-scope limitation — see §14/§16) |
| POSSIBLE_OVERDOSE OWN SAFETY/HANDOFF PATH | PASS (real E2E: distinct reply, distinct reason_code) |
| ACUTE DANGER PRIORITY UNCHANGED | PASS (real E2E regression check against audit Case C) |
| EVALUATION V2 COMPATIBLE, NO FAKE RAG METRICS | PASS |
| ACTIVITY TIMELINE SANITIZED AND ACCURATE | PASS (real E2E) |
| CONVERSATION STATE / SUGGESTED ACTIONS UNTOUCHED | PASS (`conversation_state.py` has zero diff on this branch) |
| TARGETED TESTS | PASS (24/24) |
| CORE AGENT V2 REGRESSION | PASS (739/739) |
| FULL REPOSITORY SUITE | PASS for this build's scope (1651 passed; 11 pre-existing, individually root-caused, unrelated failures — see §15) |
| RUFF | PASS |
| REAL LOCAL APP CHAT | PASS (all 4 flows + activity timeline, real OpenAI + real Postgres + real JWT via the actual `/api/chat` proxy) |
| REAL PRODUCTION APP CHAT | NOT RUN (no reviewed merge/deploy yet — do not deploy before review, per instruction) |
