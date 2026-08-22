# BUILD-24I — Phase 1, Item 5: Output-Quality Cleanup

**Scope:** duplicate-answer prevention; Unicode/confusable-script cleanup.
Local-only, no Railway deploy. Vinmec provenance (BUILD-24D), acute-danger
routing (BUILD-24E), medical grounding (BUILD-24F), router remediation
(BUILD-24G), and persona/capability guard (BUILD-24H) untouched. This is
the last item on BUILD-24C's Phase 1 fix list.

**Status: LOCAL PASS.** Not deployed; production still runs BUILD-24D's
code at 5% rollout, unchanged.

---

## 1. What's actually still live, re-checked before fixing anything

BUILD-24C flagged self-repeated text in query_id 46, 57, 58, and
foreign-script glitches in 46, 76, 92, 101. Before writing any fix, each
one was re-run through the current router (after BUILD-24E through 24H)
to see which are still reachable:

| query_id | defect | still reaches the Main Model? |
|---|---|---|
| 57, 58 | self-repeated text | **No** — both are `ACUTE_DANGER_ESCALATION` since BUILD-24E; the Main Model is never called for them any more |
| 76 | vendor leak + Tamil script | **No** — its own query ("bạn tên gì, ai tạo ra bạn") is `OUT_OF_SCOPE_REQUEST` since BUILD-24H |
| 46 | self-repeated text + Cyrillic | **Yes** — `DRUG_INFORMATION`, no bypass applies |
| 92 | foreign-script leak (prompt injection) | **Yes** — an injection attempt, correctly resisted, but still an ordinary Main Model turn |
| 101 | Cyrillic (obfuscated injection) | **Yes** — same as 92 |

So this build fixes what's actually still reachable (46, 92, 101) and keeps
the fix general enough to still protect 57/58/76 as defense in depth, in
case a future change ever routes a message back through the Main Model for
one of those categories.

**A finding beyond BUILD-24C's own report:** decoding query_id 92's raw
`actual_answer` JSON code point by code point (not just reading the
report's narrative) showed it carries **two** different foreign-script
leaks in the same reply — the Devanagari "सक्रिय" BUILD-24C's own report
named, *and* a Hebrew "בלבד" ("only") it didn't mention. Both are fixed
here.

---

## 2. Fix — three passes, one choke point

All three live in `backend/agents/v2/runtime.py`, composed into a single
`_clean_final_reply_text(text)` function called from `_result()` — the one
place every `RunResult` this runtime ever produces gets its text (updated
from the BUILD-20-era `_normalize_confusable_cyrillic(response)` call).
Purely a display/generation-quality cleanup; never runs on tool/retrieval
evidence, never touches `status`, and is a no-op on ordinary text that
doesn't exhibit the specific defect it targets.

1. **`_dedupe_self_repeated_reply`** (new): the Main Model occasionally
   regenerates its own answer a second time within one completion,
   back-to-back, sometimes with literally no separator
   (`"...thay đổi.Tôi không thể giúp lập kế hoạch..."` — the period from the
   first copy runs directly into the second copy's first word). Detected by
   finding the reply's own first sentence (8–200 chars, ending in
   `.`/`!`/`?`) reappearing verbatim later in the text; when found, the
   reply is truncated to its first occurrence. Deliberately requires an
   *exact* repeat of the opening sentence — narrow and high-confidence, not
   a general similarity detector, to avoid false-triggering on a reply that
   legitimately reuses a short phrase.
2. **`_CYRILLIC_HOMOGLYPHS` extended**: added lowercase `"к"→"k"` and
   `"в"→"v"` — the BUILD-20 table had the uppercase forms (`"К"`, `"В"`) but
   not lowercase, so `"aкtiвe"`/`"aкtiв"` (query_id 46, 101) passed through
   unnormalized before this build. This is a direct character-for-character
   substitution, same as the existing `"тип"→"tip"` precedent — it produces
   `"aktive"`/`"aktiv"`, not a semantically "corrected" `"active"`, which is
   the same behavior the existing table already has for every other entry.
3. **`_strip_disallowed_scripts`** (new): Tamil, Devanagari, and Hebrew have
   no single correct Latin substitution the way a homoglyph does — the
   model is inserting a whole foreign word with a different meaning, not a
   lookalike character. Any character in those three Unicode ranges is
   removed outright, with a follow-up whitespace/punctuation tidy-up
   (collapse a double space, close up `"word ."`→`"word."` and `"( word"`→`"(word"`)
   so the removal doesn't leave a visible seam.

---

## 3. Local regression

New file `tests/test_agent_v2_output_quality.py` — **12 tests**, all
exercising the real `ReadOnlyAgentRuntime.run()` end-to-end path (not just
the helper functions in isolation):

| Coverage | Tests |
|---|---|
| Golden query_id 46 exact reproduction — dedup + Cyrillic together | 1 |
| No-repetition text is left untouched | 1 |
| A short (<8 char) opening sentence never false-positives | 1 |
| Dedup requires an *exact* repeat, not just similar wording | 1 |
| Golden query_id 101 exact reproduction — lowercase Cyrillic | 1 |
| Lowercase `к`/`в` individually confirmed mapped | 2 |
| Existing uppercase/other-lowercase Cyrillic mappings unaffected | 1 |
| Golden query_id 92 exact reproduction — Devanagari *and* Hebrew both stripped | 1 |
| Tamil word leak stripped (golden query_id 76 shape) | 1 |
| Ordinary Vietnamese text with no foreign script is untouched | 1 |
| All three cleanups compose correctly on one adversarial reply | 1 |

```
pytest tests/test_agent_v2_output_quality.py -v
  12 passed

pytest tests/ -k "agent_v2 or orchestrator or vinmec or acute_danger or medical_grounding or router_remediation or persona_capability or output_quality" \
  --continue-on-collection-errors \
  --ignore=tests/services/photo_verification --ignore=tests/vlm_demthuoc
  409 passed, 3 skipped, 0 failed
```

409 = 397 (BUILD-24H's sweep) + 12 (this build's new tests) — exact
accounting. The pre-existing `test_confusable_cyrillic_in_the_final_reply_is_normalized_to_latin`
test (BUILD-20) was re-verified to still pass byte-for-byte unchanged.

---

## 4. Why Safety/Handoff/Auth/Vinmec/Grounding/Router/Persona are unaffected

Every change in this build is confined to `backend/agents/v2/runtime.py`'s
`_result()` text-cleanup pipeline — it only ever transforms the final reply
*string*, never `status`, `tool_results`, or `metrics`, and (per its own
long-standing BUILD-20 comment, unchanged) never runs on tool/retrieval
evidence or anything Safety Domain-authored. No file from BUILD-24D through
24H was modified by this build's diff (confirmed by inspection: only
`backend/agents/v2/runtime.py` plus the one new test file). The full
409-test sweep includes every prior build's suite, still fully passing.

---

## 5. Phase 1 complete — summary of all five items

| # | Item | Build | Status |
|---|---|---|---|
| 1 | Acute-danger Safety routing | BUILD-24E | LOCAL PASS / production deploy pending |
| 2 | Medical grounding enforcement | BUILD-24F | LOCAL PASS |
| 3 | Router remediation | BUILD-24G | LOCAL PASS |
| 4 | Persona/capability/domain guard | BUILD-24H | LOCAL PASS |
| 5 | Output-quality cleanup | BUILD-24I (this build) | LOCAL PASS |

All five isolated commits are on `feature/agent-architecture-v2`
(`a8d8bc1` bundles 24D+24E as the first-ever commit touching
`orchestrator.py`/`runtime.py`, then `8c9f142`, `b6b4cce`, `f1cc74a`, and
this build's commit each cleanly isolated on top). Next per the V2 Release
Candidate strategy: **Phase 2** — a full local re-run of all 101 golden
queries against this accumulated code (simulated locally, not against the
live production model, since production still runs only BUILD-24D), graded
PASS/FAIL_DEFECT/FAIL_SCOPE per the release-gate criteria the user
specified, before freezing a Release Candidate for the single Railway
validation pass (Phase 4).

---

## Closeout

```
LOCAL FIX STATUS: PASS -- self-repetition dedup and Cyrillic/Tamil/Devanagari/Hebrew script cleanup implemented
GOLDEN CASES FIXED (still live): 46 (dedup + Cyrillic), 92 (Devanagari + Hebrew), 101 (Cyrillic)
GOLDEN CASES ALREADY MOOT (fixed by earlier builds, reconfirmed here): 57, 58 (BUILD-24E acute-danger bypass), 76 (BUILD-24H out-of-scope bypass)
NEW FINDING BEYOND BUILD-24C's OWN REPORT: query_id 92 also leaks Hebrew ("בלבד"), not just Devanagari -- found by decoding the raw JSON directly; fixed in the same pass
FALSE POSITIVES: 0 (no-repetition and no-foreign-script text confirmed untouched; existing BUILD-20 Cyrillic test still passes byte-for-byte)
SAFETY/HANDOFF/AUTH/VINMEC/GROUNDING/ROUTER/PERSONA REGRESSION: PASS -- 409 passed, 3 skipped (pre-existing local-Postgres gap), 0 failed
5% ROLLOUT: unchanged, not touched by this build (local-only, no deploy)
PHASE 1: COMPLETE (all 5 items LOCAL PASS)
NEXT: Phase 2 -- full local 101-query golden retest, then Phase 3 (V2 Release Candidate freeze)
```
