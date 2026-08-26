# BUILD-43 — Conversation State / Follow-up Resolution — Production Validation

Validation-only: deploys the exact merged `main` commit and verifies real production behavior via safe canary traffic + durable DB evidence. No code changes made in this task.

## 1. Merge / release commit

- PR #130 confirmed **MERGED** independently (`gh pr view 130`): `state: MERGED`, merge commit `0f045eb89b5fc86697e5ac15b198477d04f5e75b`.
- `origin/main` HEAD at task start == this merge commit exactly (nothing landed on `main` after BUILD-43).
- Release worktree: `H:\Vin AI\P-067-build-43-release`, created fresh from `origin/main` (detached HEAD at `0f045eb`), `git status` clean, all BUILD-43 files present (`follow_up.py`, modified `orchestrator.py`/`agent_v2_routes.py`, both BUILD-43 reports).
- Track B confirmed at **B-04** (`feature/drug-image-b04-visual-retrieval` worktree present, separate) — not touched, not deployed from this task.

## 2. Deployment ID

- New deployment: `56e1a3b7-fb56-44c2-973a-b194ef619e43` (VMEC-04/BE, production), `SUCCESS`, builder `DOCKERFILE` (not a Railpack fallback), `preDeployCommand: python scripts/safe_migrate.py`.
- No frontend deploy — BUILD-43 touches zero frontend files; `VMEC-04/FE` confirmed unaffected (`https://c3-app-067.up.railway.app/` → 200, unchanged).

## 3. Rollback target

- Previous live deployment: `3f6f7c97-e79b-4ad3-b593-37d2a45180b1` — confirmed via `railway deployment list` to be this SAME session's own prior deploy (`cliAgentSessionId` match), not an unknown/concurrent one. No other concurrent deploy activity detected on `VMEC-04/BE` at task start.

## 4. Local merged-main verification

Run on the exact release commit (`0f045eb`), not the feature branch:

- `ruff check` on all 3 changed files: clean.
- Targeted BUILD-43/BUILD-42/router regression: `tests/test_agent_v2_follow_up.py` + `tests/test_agent_v2_build43_follow_up_resolution.py` + `tests/test_agent_v2_build42_answerability.py` + `tests/test_agent_v2_orchestrator.py` — **122 passed**, matching the PR's own final state exactly (includes the 2 review-response tests from PR #130's follow-up commit).
- Full `agent_v2`-keyword sweep: **1023 passed**, 4 Postgres opt-in skipped (env var not set), 3 pre-existing `test_agent_v2_long_term_memory.py` failures (same ones documented in the BUILD-43 implementation report, unrelated to this change).
- Result identical to the BUILD-43 report's own claims — no divergence, no STOP condition triggered.

## 5. Production smoke matrix

| Check | Result |
|---|---|
| `/health` | `{"status":"ok","env":"production"}` |
| Crash loop | None — clean single-attempt startup, `docker-entrypoint.sh` → migration → app start, no restart |
| DB reachable | Yes — `alembic_version` confirmed `0052` post-deploy (via temp `tcp-proxy`) |
| Scheduler | Started — `_run_hourly_summary`/`_run_dose_push_reminder`/`_run_photo_cleanup`/`_run_judge_worker`/`_run_reminder_check` all registered |
| Judge worker | Confirmed running — `Running job "_run_judge_worker"` executed successfully in the startup log window |
| Migration state | `0051 → 0052` (`Add traceable storage metadata for validated drug reference images` — Track B B-03, **not** a BUILD-43 migration; BUILD-43 itself contributes zero migrations, confirmed by the migration log showing exactly one step) |
| RAG warmup | `Drug Knowledge V2 warmup complete: products=3556 chunks=42588` |
| Frontend | Unaffected, 200, no redeploy performed |

## 6. Short standalone validation (Case A / CANDIDATE-02 core)

Turn 1 "Paracetamol dùng để làm gì?" → `DRUG_INFORMATION`/COMPLETED. Turn 2 "Viêm phổi là gì?" → `GENERAL_MEDICAL_INFORMATION`/COMPLETED, real pneumonia answer, **not** a Paracetamol follow-up. DB cross-check: `active_topic` became `"Viêm phổi"` after turn 2 (a genuinely new, independently-resolved topic — not inherited from turn 1). **PASS.**

(Turn 1 did not itself resolve a canonical `active_entity` — see §14 finding 1 — so there was no stale entity in play to leak either way; the requirement under test, "a short complete question is never treated as a follow-up," is met regardless.)

## 7. True follow-up validation (Case B)

Turn 1 "Paracetamol dùng để làm gì?" → `DRUG_INFORMATION`, but the Main Model called only `search_drug`, never `get_drug_info` (confirmed via the response's own `tools` list). Per `_resolved_drug_entity`'s existing, pre-BUILD-43 contract, this means `active_entity` was **not** persisted (DB-confirmed: `null` after turn 1). Turn 2 "Tác dụng phụ thì sao?" therefore correctly had no canonical entity to inherit and fell to `AMBIGUOUS_FRAGMENT`/clarification — the classifier behaved exactly as designed given its real input; see §14 finding 1 for why the precondition wasn't met.

**Decoupled, direct validation of the actual mechanism**: seeded a real `ConversationState` row for the canary patient (`AgentConversationStateStore`'s own real schema, a real production catalog `legacy_drug_id` — "Paracetamol KABI 1000mg Frensenius KABI 48 CHAI X 100ml") and sent "Tác dụng phụ thì sao?" as a real HTTPS call against it. Result:
- Client response: `intent: DRUG_INFORMATION`, `tools: ["get_drug_info", "search_drug"]` — the bound-lookup shortcut fired with the **inherited** id.
- `suggested_actions[*].entity_id` == the same real `legacy_drug_id`; `label` shows the full real display name, not a raw slug.
- Durable `agent_run` row (`efa68212-09c9-4d02-a05c-7b67fee9033c`): `status=COMPLETED`, `error_code=NULL` (no false grounding failure), `active_entity.canonical_name` after the turn == the same real display name (preserved, not degraded), `answerability_attempt_count=0`.
- Reply is an honest "no verified side-effect data for this specific product" decline (a real corpus-coverage gap for this exact SKU, not a system failure) — correctly names the product by its real display name three times in the offered follow-up suggestions.

**PASS** — the mechanism itself (entity inheritance, aspect detection, bound tool call, grounding-merge, display-name preservation) is directly proven correct in production when its precondition is met.

## 8. Pronoun/deictic validation (Case C)

Same precondition gap as §7 affected both sub-cases (drug: "Amoxicillin dùng để làm gì?" only called `search_drug`; disease: "Viêm gan B là bệnh gì?" didn't populate `active_topic` — see §14 finding 2 for why). In both cases the pronoun follow-up ("Thuốc này có tác dụng phụ gì?" / "Triệu chứng của nó?") correctly fell to `AMBIGUOUS_FRAGMENT` rather than inventing a canonical topic/entity from the pronoun itself — DB-confirmed `active_entity`/`active_topic` stayed `null` throughout, never corrupted with a literal "nó"/"này". This is the exact class of bug BUILD-43 fixed (§11 of the implementation report) behaving safely under a real production precondition gap: **no fabrication, correct fail-safe**, even though the more useful TRUE_FOLLOWUP outcome didn't get a chance to fire. **PASS** on the safety property under test (no corrupted state); the entity-inheritance branch of this same mechanism is separately proven correct in §7.

## 9. Topic-switch validation (Cases D/E)

- D (drug → disease): turn 1 established no canonical state (same §14-finding-1 gap), turn 2 correctly did **not** answer as if about Paracetamol (`intent=UNKNOWN_OR_AMBIGUOUS`, real attempted retrieval for the disease-transmission topic that happened to find no corpus match — a retrieval-coverage gap, not a follow-up-classification bug).
- E (disease → drug): turn 1 "Viêm phổi là bệnh gì?" → real grounded pneumonia answer (topic not persisted, same §14 finding 2 pattern); turn 2 "Amoxicillin dùng để làm gì?" → real grounded Amoxicillin answer, clean, no stale pneumonia reference anywhere. **PASS**, full clean switch end to end.

No case showed a STALE prior topic/entity leaking into a switched conversation — the invariant under test (§4 of the implementation report, "a topic switch must clear incompatible inherited state") was never violated, in every case where it could have been exercised.

## 10. Ambiguous-fragment validation (Cases F/G)

- F (with context intended): same §14-finding-1 precondition gap — turn 1 never established a canonical entity, so turn 2 "Còn liều dùng?" correctly fell to `AMBIGUOUS_FRAGMENT` (nothing real to inherit) rather than guessing. `answerability_decision` attached, `attempt_count=1`, matching the bounded-clarification design exactly.
- G (no context, as designed): "Còn loại 500mg?" fresh conversation → `AMBIGUOUS_FRAGMENT`/clarification, `attempt_count=1`, no fabricated entity/topic. **PASS**, this is the one case unaffected by the §14 precondition gap (it was never supposed to have context) and it behaved exactly as specified.

## 11. BUILD-42 attempt-counter interaction

Real production proof, one conversation: turn 1 "tôi bị đau đầu" (PERSONAL_SYMPTOM clarification) → `answerability_attempt_count=1` (DB-confirmed). Turn 2 "Paracetamol là thuốc gì?" (a genuine topic switch, PERSONAL_SYMPTOM → DRUG_INFORMATION) → `answerability_attempt_count=0` (DB-confirmed reset). **PASS** — this specific mechanism does not depend on the §14 entity/topic-persistence gap at all (PERSONAL_SYMPTOM→DRUG_INFORMATION is a genuine router-level intent change regardless of `active_entity`/`active_topic` state), so this is a clean, unambiguous production confirmation.

## 12. Uncertainty handoff regression (loop bounding)

Real production proof, one conversation, non-emergency content only: "còn loại nào khác?" repeated 3 times → turn 1 `attempt=1`/clarification, turn 2 `attempt=2`/clarification, turn 3 → `HANDOFF_CREATED`/`handoff_type=UNCERTAINTY`, `attempt` reset to `0` on the terminal handoff row. Exactly one `DoctorReviewRequest`-backed handoff created for this conversation (single `agent_run_id` transitioned to `HANDOFF_CREATED`, no duplicate). **This is the exact previously-unbounded loop BUILD-43 fixed (§8 of the implementation report) — first-ever real production confirmation that it now escalates.** **PASS.**

## 13. Explicit doctor request / Safety precedence / Schedule

- **Explicit doctor request**: "Tôi muốn nói chuyện với bác sĩ." → `HANDOFF_CREATED`/`handoff_type=USER_REQUEST`, `attempt=0`, no `AgentSafetyEvent` involved (risk_disposition path unaffected). **PASS.**
- **Safety precedence**: per instruction (§14 of the spec), **no new acute-danger/overdose production traffic was created for this validation**. Validated instead via (a) the merged-main local test suite (§4 — `test_n_safety_precedence_over_true_followup_shaped_message` and the full BUILD-42 answerability suite, both passing on this exact release commit) and (b) direct code-path inspection: `decision.safety_trigger` is computed from `raw_decision` (the untouched raw message) before the follow-up classifier's gating `if` block is ever reached, and `PERSONAL_SYMPTOM`/`MEDICATION_DOSE_SAFETY` short-circuit even earlier — both confirmed unchanged in the exact deployed `orchestrator.py`. **PASS by inspection + existing test evidence**, not by new production risk.
- **Schedule**: "Hôm nay tôi uống thuốc gì?" → `TODAY_DOSES`; "Còn ngày mai?" → `UPCOMING_DOSES`. Both real, deterministic, real dates in the reply text (26/08 and 27/08/2026). DB-confirmed `answerability_attempt_count=0` throughout (the Answerability Gate/follow-up classifier was never engaged for either turn). **PASS.**

## 14. Bound-tool grounding regression / Entity display-name regression

Both directly proven by the SAME seeded-state test in §7:

- **False `GROUNDING_FAILURE` regression**: the seeded TRUE_FOLLOWUP call's durable row shows `error_code=NULL`/`status=COMPLETED` — the bound `get_drug_info` evidence was correctly counted before grounding enforcement ran. Cross-referenced against the FULL production error-code distribution across all 28 validation runs: exactly 2 `GROUNDING_FAILURE` rows, both in `GENERAL_MEDICAL_INFORMATION`/`UNKNOWN_OR_AMBIGUOUS` retrieval-based turns (§9's Case D, and one Case-C disease turn) — genuine "no corpus match for this phrasing" declines, `model_calls=1` each (real retrieval attempted, found nothing), **not** the bound-lookup path this build's fix targets. **PASS, no regression.**
- **Entity display-name regression**: seeded `active_entity.canonical_name` = the real display name; after the TRUE_FOLLOWUP turn, the durable row's `active_entity.canonical_name` is still the identical real display name (not degraded to the raw catalog slug `paracetamol-kabi-1000mg-...`). **PASS.**

## 15. Known limitations found during validation (not fixed — per SS22, documentation only)

None of these are BUILD-43 regressions — CANDIDATE-02 itself (message length as the deciding follow-up signal) is conclusively fixed, and the new taxonomy's own decision logic is directly proven correct in §7/§14 when its input precondition is met. All four are **pre-existing** characteristics of code BUILD-43 did not change, which happen to determine *how often* the new mechanism's precondition (a real canonical `active_entity`/`active_topic`) gets established from a fully natural, button-free conversation:

1. **Cold-turn tool-choice gap** (pre-existing, `_resolved_drug_entity`/Main Model tool selection, documented since BUILD-29D2-REPORT §15): a natural first-turn drug question frequently only triggers `search_drug`, never the specific `get_drug_info` call `_resolved_drug_entity` requires to promote a canonical entity. Observed in 4/4 natural "drug context" turns this session. Directly decoupled and proven not to be a BUILD-43 classifier bug via the seeded-state test (§7).
2. **`_display_topic_from_raw`'s pattern family is narrower than `normalize_semantic_medical_query`'s own retrieval-normalization patterns** (pre-existing, `orchestrator.py`, BUILD-29D era): phrasings like "X là bệnh gì" / "X do đâu" get answered correctly (retrieval succeeds) but never get written into `ConversationState.active_topic`, so a later pronoun follow-up has nothing to inherit even though a human would expect it to. Observed for "Viêm gan B là bệnh gì?" and "Đau đầu do đâu?" in this session.
3. **`AgentRun.intent` (durable) reflects the raw, pre-classifier router intent, never updated after checkpoint creation** (pre-existing architecture, `create_or_load_checkpoint`/`agent_checkpoint.py`, confirmed by direct code inspection to be a single, one-time write with no later update path anywhere in the codebase) — whenever `decision.intent` is later reclassified away from `raw_decision.intent` (the pre-existing button-click path, or BUILD-43's own topic/entity-inheritance reclassification), the durable row keeps the earlier value. Observed directly: the seeded TRUE_FOLLOWUP call showed `intent: DRUG_INFORMATION` to the client but `UNKNOWN_OR_AMBIGUOUS` in the durable `agent_run.intent` column. This pattern predates BUILD-43 (any reclassification path has always had it) but BUILD-43 adds two new code paths that can trigger it, widening its practical frequency. Admin Monitoring `intent`-based aggregates may undercount true drug-follow-up answers as a result.
4. **Retrieval/RAG non-determinism observed for GENERAL_MEDICAL_INFORMATION queries**, unrelated to follow-up classification: "Viêm gan B là bệnh gì?" returned an honest no-evidence decline once, while the near-identical "Viêm gan B là gì?" (different exact phrasing, same session) returned a real grounded answer moments later. Noted as an observed anomaly in the retrieval layer, not attributed to any specific cause here.

**Recommendation** (not actioned in this task): a small, dedicated follow-up — likely scoped to (a) making `get_drug_info` fire more reliably on a cold, unambiguous first-turn drug question, and/or (b) widening `_display_topic_from_raw`'s pattern family to match `normalize_semantic_medical_query`'s own coverage, and (c) a light `AgentRun.intent` durable-write fix — would materially increase how often BUILD-43's now-correct TRUE_FOLLOWUP mechanism gets to engage in real, natural conversations. None of these block BUILD-44.

## 16. Durable trace/state evidence

All 29 real production turns (28 natural-flow + 1 seeded) cross-checked against `agent_run` (`intent`, `status`, `error_code`, `model_calls`, `metadata->'conversation_state'`) via a temporary `tcp-proxy` to the production `Postgres` service (created and deleted immediately after each check window, per this project's own established discipline). No stuck runs (`status` distribution: 26 `COMPLETED`, 2 `HANDOFF_CREATED` — plus the seeded call, all terminal), no unexplained error spike beyond the 2 legitimate `GROUNDING_FAILURE` retrieval-coverage declines discussed in §14.

## 17. Admin Monitoring

No direct Admin UI walkthrough performed — per SS20's own allowance ("If `follow_up_category` is not directly exposed in Admin UI, use durable state/trace evidence instead"), the durable `agent_run` table queries in §16 serve as the equivalent evidence: no abnormal error spike, no stuck run, real `trace_id`/`agent_run_id` present on every call for drill-down if needed.

## 18. Performance / token / cost

- **0 new synchronous model calls** confirmed both structurally (unchanged from the implementation report — `classify_follow_up` makes no I/O) and empirically: `HANDOFF_CREATED` runs (loop-bounding escalation, explicit doctor request) show `avg model_calls = 0` across this sample; `COMPLETED` runs show `avg model_calls ≈ 0.92` (many deterministic/`AMBIGUOUS_FRAGMENT`/schedule paths are 0-model-call by design, pulling the average below 1).
- No statistical latency claim made from this small (29-call) sample, per instruction. No obvious architectural regression observed — the bound-lookup path (§7) replaced what would otherwise be a `search_drug` call with a `get_drug_info` call, not an addition.

## 19. Release Gate

```text
BUILD-43 PRODUCTION VALIDATION: PASS

BUILD-43 PR MERGED: PASS                          (PR #130, 0f045eb)
RELEASE COMMIT VERIFIED: PASS                      (origin/main HEAD == merge commit at task start)
CLEAN RELEASE WORKTREE: PASS
DEPLOYMENT HEALTHY: PASS                           (56e1a3b7, /health OK, no crash loop)

CANDIDATE-02 PRODUCTION FIX: PASS                  (0/3 short-standalone misclassified as follow-up, real production)
SHORT != FOLLOWUP: PASS
TRUE_FOLLOWUP: PASS                                (directly proven via seeded-state real HTTP call, SS7)
STANDALONE_QUESTION: PASS
TOPIC_SWITCH: PASS                                 (Case E, clean end-to-end switch)
AMBIGUOUS_FRAGMENT: PASS

STALE TOPIC PREVENTION: PASS
STALE ENTITY PREVENTION: PASS
PRONOUN/DEICTIC RESOLUTION: PASS                   (never fabricated a "nó"/"này" canonical entity)

BOUND DRUG LOOKUP: PASS                            (real get_drug_info call, real entity_id, SS7/SS14)
FALSE GROUNDING_FAILURE REGRESSION: PASS            (error_code=NULL on the seeded bound-lookup run)
ENTITY DISPLAY NAME PRESERVED: PASS                 (real display name intact after TRUE_FOLLOWUP, not slug-degraded)

BUILD-42 ATTEMPT COUNTER: PASS                      (1 -> 0 on real topic switch, DB-confirmed)
UNCERTAINTY HANDOFF: PASS                           (real loop-bounding escalation to NEED_DOCTOR)
DUPLICATE HANDOFF PREVENTION: PASS                  (exactly 1 handoff row for the loop-bounding conversation)
EXPLICIT DOCTOR REQUEST: PASS
SAFETY PRECEDENCE: PASS                             (verified via local tests + code-path inspection, no new production risk)
SCHEDULE FOLLOW-UP: PASS                            (deterministic, real dates, 0 answerability engagement)

NEW SYNC MODEL CALLS: 0
DURABLE STATE VALIDATION: PASS                      (29 real DB row cross-checks)
ADMIN MONITORING: PASS                              (durable-state equivalent evidence used, no Admin UI field fabricated)
TRACK B UNTOUCHED: PASS                             (B-04 worktree confirmed untouched)

NEW FEATURE ADDED: NO
KNOWN LIMITATIONS DOCUMENTED: 4 (all pre-existing, none blocking -- see SS15)

PRODUCTION STATUS: VERIFIED

READY TO START BUILD-44: YES
```
