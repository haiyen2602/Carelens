# BUILD-24K — Found During Phase 2: Neutral-Phrase Diacritics Fix

**Scope:** a single, narrow text fix found while grading Phase 2's real
101-query local golden retest (report 44). Not a new defect category from
BUILD-24C's own list — a fresh finding, made possible only by testing
against the real model instead of synthetic unit tests. Local-only, no
Railway deploy.

---

## 1. The finding

Grading Phase 2's real results showed 13/101 replies containing the literal
ASCII string `"du lieu noi bo da xac minh"` (no Vietnamese diacritics)
dropped mid-sentence into otherwise fully-accented Vietnamese text the
model generated, e.g. (query_id 7, "vizicin"):

> "...Lưu ý: mình **không tìm thấy nguồn du lieu noi bo da xac minh**
> trong dữ liệu đã cung cấp, nên không thể nói đây là thông tin từ **du
> lieu noi bo da xac minh**."

Traced precisely: this is `_strip_false_vinmec_claim`
(`backend/agents/v2/orchestrator.py`, BUILD-24D) doing exactly its job —
the Main Model is *still* biased toward narrating internal/canonical-drug-v2
data as "Vinmec"-sourced even for a bare drug-name lookup with no Vinmec
intent at all (the exact live-observed pattern BUILD-24C's report 35
section 4.1 first found, and BUILD-24D fixed the *outcome* of). The
substitution itself is functionally correct — no false Vinmec claim reaches
the user — but `_NEUTRAL_SOURCE_PHRASE` was a bare-ASCII string
(`"du lieu noi bo da xac minh"`), while every other fixed string in this
module that gets inserted into free text keeps the project's ASCII-only
convention *consistently across an entire self-contained reply*. This
phrase is different: it is spliced into the middle of a sentence the model
already wrote with full diacritics, so the ASCII fragment reads as a
jarring, mixed-script insert — confusing, though never factually wrong.

This is precisely the kind of defect that could not have been found by
BUILD-24D's own synthetic unit tests (which construct exact, controlled
sentences) — it only showed up once the real model, with its own real
phrasing habits, was exercised at volume.

## 2. Fix

One-line change: `_NEUTRAL_SOURCE_PHRASE` now carries its own correct
Vietnamese diacritics — `"dữ liệu nội bộ đã xác minh"` instead of
`"du lieu noi bo da xac minh"`. The capitalization logic in
`_strip_false_vinmec_claim` (`phrase[0].upper()`) is unaffected since the
first character `"d"` has no diacritic of its own. No other fixed string in
this module was touched — every other one is a complete, self-consistent
ASCII reply, not a mid-sentence splice, so BUILD-20/24B/24D/24F/24H/24I's
own convention there is correctly left alone.

## 3. Verification

- `tests/test_agent_v2_vinmec_provenance.py`'s
  `test_strip_false_vinmec_claim_preserves_surrounding_text_and_capitalizes_sentence_starts`
  updated to assert the new accented phrase. 21/21 passing.
- Full sweep: 409 passed, 3 skipped (pre-existing local-Postgres gap), 0
  failed — identical count to before this fix (a pure string-content
  change, no test added/removed).
- **Re-ran all 13 originally-affected queries against the real model**:
  0/13 now show the old ASCII phrase; 8/13 still trigger the backstop
  (the model still occasionally claims "Vinmec") but now render with
  correct diacritics matching the surrounding text; the other 5 didn't
  mention "Vinmec" at all on this run (ordinary LLM run-to-run
  non-determinism — not something this fix needs to or can eliminate, only
  ensure the correction reads cleanly whenever it does fire). Merged into
  the Phase 2 results file (report 44) before grading continued.

---

## Closeout

```
LOCAL FIX STATUS: PASS -- _NEUTRAL_SOURCE_PHRASE now uses correct Vietnamese diacritics, matching the accented text it gets spliced into
FOUND VIA: Phase 2's real 101-query local golden retest (13/101 affected), not previously catchable by synthetic unit tests
FUNCTIONAL GUARANTEE UNCHANGED: still exactly one fixed, deterministic word-level substitution; no false Vinmec claim reaches the user, same as BUILD-24D
REGRESSION: PASS -- 409 passed, 3 skipped (pre-existing local-Postgres gap), 0 failed
REAL-MODEL RE-VERIFICATION: PASS -- 0/13 originally-affected queries show the old ASCII phrase after the fix
5% ROLLOUT: unchanged, not touched by this build (local-only, no deploy)
```
