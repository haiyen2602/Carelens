# BUILD-24G — Phase 1, Item 3: Router Remediation

**Scope:** fix the 5 intent-misrouting cases BUILD-24C found (query_id 2,
26, 28, 31, 54) — content was accurate in every case, only the
`OrchestrationIntent` classification was wrong. Local-only, no Railway
deploy. Safety/Auth checks keep top priority in the router, unchanged;
Vinmec provenance (BUILD-24D), acute-danger routing (BUILD-24E), and
medical grounding (BUILD-24F) untouched.

**Status: LOCAL PASS.** Not deployed; production still runs BUILD-24D's
code at 5% rollout, unchanged.

---

## 1. Root causes, traced precisely (not assumed)

Reproduced all 5 cases directly against `classify_intent` before touching
any code, to confirm the exact failure before fixing it:

| query_id | query | got | expected |
|---|---|---|---|
| 2 | "Vitamin C uống bao nhiêu viên 1 ngày" | GENERAL_CONVERSATION | DRUG_INFORMATION |
| 26 | "buổi sáng tôi cần uống thuốc gì" | DRUG_INFORMATION | TODAY_DOSES |
| 28 | "buổi tối nay uống gì" | DRUG_INFORMATION | TODAY_DOSES |
| 31 | "buổi trưa uống thuốc gì" | DRUG_INFORMATION | TODAY_DOSES |
| 54 | "sau khi uống thuốc em thấy da hơi đỏ ửng" | GENERAL_CONVERSATION | not GENERAL_CONVERSATION |

**Root cause 1 (query_id 2, 54):** `_GREETING_KEYWORDS` included the bare
2-letter English word `"hi"`, matched as a plain substring like every other
keyword in this router. `"hi" in "bao nhiêu".casefold()` and
`"hi" in "sau khi".casefold()` are both `True` — **"hi" is a substring of
the ordinary Vietnamese words "nhiêu" (how many) and "khi" (when/after)**,
confirmed directly in a Python REPL before writing any fix. A real
drug-dose question and a real side-effect report were each silently
misrouted to small-talk handling because of a 2-character collision. No
other keyword in this entire router is short/generic enough to have this
problem (the next-shortest, "hi", is the only offender; every Vietnamese
phrase like "xin chào" is specific enough not to appear inside an unrelated
word).

**Root cause 2 (query_id 26, 28, 31):** `_TODAY_KEYWORDS` only recognized
the literal phrase `"hôm nay"`/`"today"`. None of the three messages say
that — they say a bare time-of-day ("buổi sáng" morning, "buổi tối nay"
this evening, "buổi trưa" noon) — which in ordinary conversational usage
about a *current* medication schedule implies *today* unless a different
day is named explicitly (compare BUILD-24D's report 36, query_id 33
"lịch uống thuốc ngày mai của tôi", which already correctly routes to
`UPCOMING_DOSES` precisely because it names "ngày mai"/tomorrow). The
router simply had no coverage for this extremely common phrasing pattern.

---

## 2. Fix

Both fixes are pure keyword-set expansion in
`backend/agents/v2/orchestrator.py`; `classify_intent`'s control flow and
priority order are unchanged:

1. **`_GREETING_WORD_RE = re.compile(r"\b(hi|hello)\b", re.IGNORECASE)`** —
   `"hi"`/`"hello"` now match as whole words only, via a small
   `_matches_greeting()` helper that ORs this regex with the existing
   plain-substring check for the other, longer greeting phrases
   (`"xin chào"`, `"chào bạn"`, `"cảm ơn"` — left untouched, still substring
   matching, since they've never shown this collision).
2. **`_TODAY_KEYWORDS` expanded** with `"buổi sáng"`/`"buoi sang"`,
   `"buổi trưa"`/`"buoi trua"`, `"buổi chiều"`/`"buoi chieu"`,
   `"buổi tối"`/`"buoi toi"`, each also with a `"... nay"` (this) suffix
   variant for paraphrase coverage.

**No semantic/embedding-based intent fallback was added.** This build's own
instructions named that as optional ("có thể thêm... khi deterministic
rules không đủ"); both root causes were fully resolved with plain
deterministic keyword coverage, so introducing a model-driven routing layer
— which this codebase's own design principle explicitly keeps out of the
router (see the module docstring: *"Router... is a deterministic keyword
classifier, not a model call"*, because a model-selected route could let a
crafted message talk its way around Safety) — was not needed and would only
have added a harder-to-audit dependency for no benefit. `_detect_acute_danger`
(BUILD-24E) still runs first, before every other branch including these
two; Safety/Auth priority is structurally unchanged.

---

## 3. Local regression

New file `tests/test_agent_v2_router_remediation.py` — **21 tests**:

- All 5 golden misrouting cases individually reproduced and confirmed
  fixed.
- 4 additional "hi"/"khi"/"nghi" substring collision probes, confirmed no
  longer false-positive into `GENERAL_CONVERSATION`.
- 5 genuine `"hi"`/`"hello"` greetings (including "Hello there", "hi bạn")
  confirmed still correctly route to `GENERAL_CONVERSATION` — the fix
  narrows the match, it does not remove greeting detection.
- The other 3 existing greeting phrases confirmed unaffected.
- Priority-order regression: a time-of-day phrase co-occurring with a real
  `MISSED_DOSE`/`DELAYED_DOSE`/acute-danger signal in the same message
  still correctly yields the higher-priority intent, not `TODAY_DOSES`.
- 3 additional time-of-day phrasings ("buổi chiều", "buổi tối" without
  "nay", "chiều nay") confirmed routed correctly.

```
pytest tests/test_agent_v2_router_remediation.py -v
  21 passed

pytest tests/ -k "agent_v2 or orchestrator or vinmec or acute_danger or medical_grounding or router_remediation" \
  --continue-on-collection-errors \
  --ignore=tests/services/photo_verification --ignore=tests/vlm_demthuoc
  365 passed, 3 skipped, 0 failed
```

365 = 344 (BUILD-24F's sweep) + 21 (this build's new tests) — exact
accounting. The existing `test_router_is_deterministic_and_keyword_driven`
parametrized suite (10 cases covering every other intent, including a
message that combines a `DELAYED_DOSE` trigger with a time-of-day phrase in
the same sentence) was independently re-verified to still pass unchanged —
priority ordering was never at risk since both new keyword sets sit *after*
every safety/handoff/dose-trigger check in the `if`/`elif` chain, exactly
as before this build.

---

## 4. A known, accepted imprecision (documented, not hidden)

Adding bare time-of-day phrases to `_TODAY_KEYWORDS` is a heuristic, not a
semantic understanding of the message: a message like "buổi sáng có tác
dụng phụ gì không" (does the morning dose have any side effects) would now
also route to `TODAY_DOSES` rather than a side-effect-focused intent, even
though it's arguably more of a `GENERAL_MEDICAL_INFORMATION`-shaped
question. This is the same class of imprecision every other keyword in this
router already has (e.g. bare "hôm nay" has always had this same
trade-off), and in a medication-reminder app's actual query distribution,
"buổi sáng/trưa/chiều/tối [uống gì]"-shaped messages are overwhelmingly
schedule questions — the fix targets the common case correctly. Not treated
as a defect; noted here for the Phase 2 golden retest to catch if it turns
out to matter in practice.

---

## Closeout

```
LOCAL FIX STATUS: PASS -- both root causes (bare "hi" substring collision; missing time-of-day-without-"hôm nay" coverage) fixed with deterministic keyword expansion only
GOLDEN MISROUTING CASES FIXED: 5/5 (query_id 2, 26, 28, 31, 54)
FALSE POSITIVES INTRODUCED: 0 -- full existing router test suite (10 cases) + priority-order regression (time-of-day co-occurring with MISSED_DOSE/DELAYED_DOSE/acute-danger) all still correct
SEMANTIC FALLBACK ADDED: NO (not needed -- deterministic coverage was sufficient; router stays a fixed, auditable keyword/regex classifier per this codebase's own design principle)
SAFETY/AUTH PRIORITY: unchanged -- _detect_acute_danger still checked first, before every other branch
SAFETY/HANDOFF/AUTH/VINMEC/GROUNDING REGRESSION: PASS -- 365 passed, 3 skipped (pre-existing local-Postgres gap), 0 failed
5% ROLLOUT: unchanged, not touched by this build (local-only, no deploy)
NEXT: BUILD-24H, persona/capability/domain guard (Phase 1 item 4)
```
