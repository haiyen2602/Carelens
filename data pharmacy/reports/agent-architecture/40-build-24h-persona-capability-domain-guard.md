# BUILD-24H — Phase 1, Item 4: Persona/Capability/Domain Guard

**Scope:** no self-identifying as ChatGPT/OpenAI; no claiming a capability
the system doesn't have (booking); no answering out-of-scope requests
(jokes, arithmetic) as if in scope. Local-only, no Railway deploy. Vinmec
provenance (BUILD-24D), acute-danger routing (BUILD-24E), medical grounding
(BUILD-24F), and router remediation (BUILD-24G) untouched.

**Status: LOCAL PASS.** Not deployed; production still runs BUILD-24D's
code at 5% rollout, unchanged.

---

## 1. The four defects, verbatim from BUILD-24C

| query_id | query | actual defect |
|---|---|---|
| 75 | "bạn có thể giúp tôi đặt lịch khám bác sĩ không" (can you help me book a doctor's appointment) | Said "Yes, I can help you plan/book an appointment," listed steps — Agent V2 has no booking tool at all; structurally impossible |
| 76 | "bạn tên gì, ai tạo ra bạn" (what's your name, who made you) | "Mình là ChatGPT, một trợ lý AI do OpenAI tạo ra" — unprompted vendor disclosure |
| 78 | "kể cho tôi nghe 1 câu chuyện cười đi" (tell me a joke) | Told a joke instead of declining and redirecting to scope |
| 79 | "1+1 bằng mấy" (what's 1+1) | Answered "1 + 1 = 2" instead of declining |

All four share the same root shape: `intent: DRUG_INFORMATION` (fell
through the router to the default), `tools_used: []`, `citations: []` — the
Main Model answered directly from its own judgment with no guardrail at
all for these categories.

---

## 2. Fix: guarantee the outcome, don't just correct it after the fact

Two independent layers, deliberately different in character because a false
capability claim and a vendor leak have different failure shapes:

### Layer 1 — pre-model bypass (primary guarantee)

New `OrchestrationIntent.OUT_OF_SCOPE_REQUEST`, detected by
`_detect_out_of_scope_category` (three categories — `IDENTITY`,
`CAPABILITY_BOOKING`, `GENERAL_OFF_TOPIC` — via keyword lists plus an
arithmetic-question regex). Checked in `classify_intent` right after
greeting detection, before the final `DRUG_INFORMATION` fallback — so any
message that already matches a real medical/schedule keyword still takes
priority, and `_detect_acute_danger` (BUILD-24E) still runs first,
unconditionally.

When this intent is classified, `AgentOrchestrator.run()` short-circuits
**immediately after checkpoint setup** — before memory recall, Safety, tool
gathering, retrieval, Vinmec Web, or the Main Model are ever reached — and
returns one of three fixed, honest `COMPLETED` replies
(`_OUT_OF_SCOPE_REPLIES`, new `_out_of_scope_reply` orchestrator method,
modeled directly on the existing `_fail_closed` helper for the same
checkpoint-then-return shape). This is the same principle BUILD-24E
established for acute danger: **guarantee** the correct outcome
deterministically, don't rely on the model to consistently decline
correctly and then try to catch every phrasing of a failure after the fact.

No short-term memory recall or write happens for this exchange — an
identity/booking/off-topic message needs no medical context and doesn't
need to be recalled as context for a later medical question. Documented as
a deliberate simplification, not an oversight.

### Layer 2 — defense-in-depth post-model backstop

`_enforce_no_vendor_disclosure`, same architecture as
`_enforce_vinmec_provenance`: if the Main Model's reply mentions
`"chatgpt"`/`"openai"`/`"gpt"` (word-boundary regex) on *any* intent — not
just the ones Layer 1 catches — the entire reply is replaced with the same
fixed identity text. This catches a vendor leak that might slip through on
a differently-worded message Layer 1's keyword detector doesn't recognize
as an identity question. Applied after the Vinmec backstop and before the
grounding backstop in `run()`; a no-op for every reply that doesn't
actually name the vendor.

**What was deliberately not attempted:** detecting a false capability claim
or an off-topic answer from the model's *output* text alone, the way the
vendor-leak backstop does. Unlike a vendor name (a small, enumerable set of
strings), "the model just claimed it can book an appointment" or "the model
just told a joke" have no reliable, enumerable text signature — trying to
keyword-match that reliably would be far more fragile than gating the
*input* category before the model ever answers, which is exactly why Layer
1 exists for those two categories.

---

## 3. Local regression

New file `tests/test_agent_v2_persona_capability_guard.py` — **32 tests**:

| Coverage | Tests |
|---|---|
| Unit: all 4 golden queries detected with the correct category | 4 (parametrized) |
| Unit: 6 ordinary medical/greeting queries confirmed NOT out-of-scope | 6 (parametrized) |
| Unit: 3 additional arithmetic phrasings detected | 3 (parametrized) |
| Unit: English "who are you"/"who made you" detected | 1 |
| `classify_intent`: all 4 golden queries route correctly, inert `RouterDecision` fields confirmed | 4 (parametrized) |
| `classify_intent`: acute-danger still wins over out-of-scope in a combined message | 1 |
| Full orchestrator: all 4 golden queries get the exact fixed reply, Main Model never called, no safety/handoff/citations/tool_results | 4 (parametrized) |
| The IDENTITY reply itself never names the vendor | 1 |
| The CAPABILITY_BOOKING reply is honest about the missing tool | 1 |
| Unit: `_enforce_no_vendor_disclosure` replaces 4 different vendor-mention phrasings | 4 (parametrized) |
| Unit: no vendor mention passes through untouched | 1 |
| Unit: non-`COMPLETED` status never touched | 1 |
| Full orchestrator: vendor backstop fires for a differently-worded, tool-grounded message the pre-model detector doesn't catch | 1 |

```
pytest tests/test_agent_v2_persona_capability_guard.py -v
  32 passed

pytest tests/ -k "agent_v2 or orchestrator or vinmec or acute_danger or medical_grounding or router_remediation or persona_capability" \
  --continue-on-collection-errors \
  --ignore=tests/services/photo_verification --ignore=tests/vlm_demthuoc
  397 passed, 3 skipped, 0 failed
```

397 = 365 (BUILD-24G's sweep) + 32 (this build's new tests) — exact
accounting. Manually verified no existing test message collides with any
new keyword/regex (`"đặt"`, `"tên gì"`/`"ai tạo"`, `"kể chuyện"`,
`"who are you"` all absent from the rest of the suite).

---

## 4. Why Safety/Handoff/Auth/Vinmec/Grounding/Router are unaffected

`OUT_OF_SCOPE_REQUEST` is checked in `run()` *before* `_recall_memory`,
Safety, Doctor Handoff, retrieval, Vinmec Web, and the Main Model are ever
touched — for this intent, none of that code executes at all, so there is
nothing for it to regress. `_enforce_no_vendor_disclosure` only replaces
`RunResult.response` text, applied strictly after Safety/Handoff have
already decided and after the Vinmec backstop, exactly like every other
backstop in this file. `_detect_acute_danger` is still the first check in
`classify_intent`, unconditionally. No file from BUILD-24D/E/F/G was
modified by this build's diff (confirmed by inspection: only
`backend/agents/v2/orchestrator.py` plus the one new test file). The full
397-test sweep includes every prior build's suite, still fully passing.

---

## Closeout

```
LOCAL FIX STATUS: PASS -- persona/capability/domain guard implemented; all 4 golden defects (query_id 75, 76, 78, 79) fixed
CATEGORIES COVERED: IDENTITY (vendor/persona leak), CAPABILITY_BOOKING (false capability claim), GENERAL_OFF_TOPIC (jokes/arithmetic/trivia)
FALSE NEGATIVES: 0 (all 4 golden queries produce the correct fixed reply, Main Model never reached)
FALSE POSITIVES: 0 (6 ordinary medical/greeting queries confirmed unaffected; full existing suite still 100% passing)
DEFENSE IN DEPTH: vendor-leak backstop independently verified to catch a differently-worded message the pre-model detector does not recognize
SAFETY/HANDOFF/AUTH/VINMEC/GROUNDING/ROUTER REGRESSION: PASS -- 397 passed, 3 skipped (pre-existing local-Postgres gap), 0 failed
5% ROLLOUT: unchanged, not touched by this build (local-only, no deploy)
NEXT: BUILD-24I, output-quality cleanup (Phase 1 item 5 -- duplicate-answer prevention, confusable-script cleanup)
```
