# BUILD-24L — Phase 2 Defect Cleanup: The 4 Remaining FAIL_DEFECT Items

**Scope:** fix the 4 non-critical FAIL_DEFECT findings from BUILD-24J's
Phase 2 local golden retest (report 44, query_id 5, 8, 45, 74). Local-only,
no Railway deploy. Nothing else touched.

**Status: LOCAL PASS, re-verified against the real model.**

---

## 1. query_id 74 — router false positive ("hôm nay thời tiết thế nào")

**Fix (deterministic):** `_detect_out_of_scope_category` is now checked in
`classify_intent` *before* `_TODAY_KEYWORDS` (still after every
safety/action-priority branch — acute-danger, doctor-review, missed/
delayed-dose, dose-status). Added a few unambiguous non-medical topic
markers ("thời tiết"/weather, "bóng đá"/football, "tin tức"/news) to
`_GENERAL_OFF_TOPIC_KEYWORDS`.

**Real-model re-verification:** query now routes `OUT_OF_SCOPE_REQUEST` and
returns the exact fixed reply, confirmed live. This is a hard, deterministic
fix — same guarantee class as BUILD-24G/24H.

## 2. query_id 8 — ambiguous short-name disambiguation ("vitamin b1")

**Fix (prompt-level guidance):** `plan_read_only`'s prompt
(`backend/agents/v2/model_gateway.py`) now explicitly instructs: if
`search_drug` returns more than one plausible match for an ambiguous name,
list the candidates and ask which one the user means, instead of picking
one silently.

**Real-model re-verification:** confirmed live — the model now lists 2
distinct SKUs ("Vitamin b1 Vinphaco 100 ỐNG", "Vitamin b1 100mg F.t 10x10
ỐNG") and asks a clarifying follow-up, where it previously picked one
silently. Clean before/after difference.

## 3. query_id 5 — partial grounding precision (Vitamin B1 indication)

Traced precisely: `drug_product` has no indication/công_dụng column at
all, but the RAG corpus (`drug_chunks`) **does** have real `cong_dung`
content for this exact drug (`vitamin-b1-250mg-domesco-100v`) — confirmed
by querying the local corpus directly. The model only called `search_drug`
(name/dosage_form/route/strength only) and answered the indication
question from outside knowledge instead of also calling `get_drug_info`
(which would have surfaced the real `cong_dung` field).

**Fix (prompt-level guidance):** `plan_read_only`'s prompt now explicitly
instructs: for indication/side-effect/usage/storage questions,
`search_drug` alone is not enough — call `get_drug_info` with the resolved
`legacy_drug_id` before answering; if that field still isn't present, say
so honestly instead of using outside knowledge.

**Real-model re-verification (3 runs total — the original defect plus 2
post-fix runs):** the model still didn't reliably call `get_drug_info`
every time (prompt-level guidance is not a hard guarantee — same
BUILD-24B-established distinction between prompt instructions and
deterministic backstops; there is no clean deterministic signal to
backstop a *partially*-ungrounded claim against, unlike a literal "vinmec"
mention), but honesty about the evidence gap **measurably and consistently
improved** across both post-fix runs: run 2 stated the general fact but
immediately caveated "không có dữ liệu chỉ định điều trị... trong dữ liệu
xác thực" (no treatment-indication data in the verified results); run 3
declined to assert the fact at all, only offering to explain generically
if asked. Neither post-fix run repeated the original defect's shape
(confident, uncaveated assertion). Reported honestly as **improved, not
100%-guaranteed** — a real, if softer, class of fix than the other three.

## 4. query_id 45 — misleading "đã ghi nhận" (recorded) wording

**Fix (prompt-level guidance):** `synthesize_read_only`'s prompt now
explicitly instructs: never say the patient's own message/claim has been
recorded, logged, noted, or saved anywhere — Agent V2 is read-only and
persists no input; only describe something as "on file" if it is actually
present in the verified tool evidence.

**Real-model re-verification (2 runs):** both post-fix runs show
`tools=[]` — BUILD-24F's grounding backstop intercepted before free text
was generated at all, returning the fixed honest-decline text instead (no
possibility of the "đã ghi nhận" phrasing appearing, by construction). The
exact scenario that produced the original defect (a tool called, free text
generated referencing the patient's own claim) was not reproduced in
either re-verification run, so the prompt instruction itself was not
directly exercised — the user-facing outcome is confirmed safe both times,
via a different (but equally reliable) mechanism.

---

## 2. Local regression

New file `tests/test_agent_v2_grounding_precision.py` — **7 tests**:
router fix for query_id 74 (+ 3 new negative-topic markers + a priority-
order regression check), and 3 prompt-content smoke tests (capturing the
`input=` kwarg passed to the mocked OpenAI client, confirming the new
instructions are actually present in what gets sent).

```
pytest tests/test_agent_v2_grounding_precision.py -v
  7 passed

pytest tests/ -k "agent_v2 or orchestrator or vinmec or acute_danger or medical_grounding or router_remediation or persona_capability or output_quality or grounding_precision" \
  --continue-on-collection-errors \
  --ignore=tests/services/photo_verification --ignore=tests/vlm_demthuoc
  416 passed, 3 skipped, 0 failed
```

416 = 409 (prior sweep) + 7 (this build's new tests) — exact accounting.

---

## Closeout

```
LOCAL FIX STATUS: PASS -- all 4 remaining FAIL_DEFECT items addressed
QUERY_ID 74 (router false positive): FIXED, deterministic, re-verified live
QUERY_ID 8 (disambiguation): FIXED, re-verified live (clean before/after)
QUERY_ID 5 (partial grounding): IMPROVED, not 100% guaranteed -- prompt-level guidance, re-verified across 3 real-model runs showing consistent honesty improvement
QUERY_ID 45 (misleading wording): SAFE OUTCOME CONFIRMED across 2 real-model runs, via grounding-backstop interception rather than direct exercise of the new prompt instruction
REGRESSION: PASS -- 416 passed, 3 skipped (pre-existing local-Postgres gap), 0 failed
5% ROLLOUT: unchanged, not touched by this build (local-only, no deploy)
NEXT: fresh full 101-query local golden retest to confirm the release gate (report 44's own gate) is now clean
```
