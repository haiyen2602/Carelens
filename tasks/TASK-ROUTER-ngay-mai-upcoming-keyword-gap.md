# TASK: Router misses "ngày mai" as an UPCOMING_DOSES keyword

**Found during:** BUILD-27 (BUDGET_EXCEEDED fix on "Ngay mai toi can uong
thuoc gi"), report `57-build-27-budget-exceeded-upcoming-doses.md`. Not
fixed there — out of that build's scope (the token-budget bug reproduces
regardless of routed intent, so it did not block that fix), tracked here so
it isn't lost.

## The gap

`backend/agents/v2/orchestrator.py`'s `_UPCOMING_KEYWORDS` is:

```python
_UPCOMING_KEYWORDS = ("sắp tới", "sap toi", "lịch uống", "lich uong", "upcoming", "sắp đến", "sap den")
```

"ngày mai" / "ngay mai" (tomorrow) is **not** in this tuple. A message like
"Ngày mai tôi cần uống thuốc gì" therefore matches none of
`_TODAY_KEYWORDS`/`_UPCOMING_KEYWORDS`/`_PRESCRIPTION_KEYWORDS`/etc. and
falls through `classify_intent`'s final `else` to `DRUG_INFORMATION` —
confirmed empirically in BUILD-27's own repro (`intent=DRUG_INFORMATION`
logged on every run of that exact message).

This is inconsistent with the router's own comment immediately above
`_TODAY_KEYWORDS` (`orchestrator.py` ~line 270), which cites "ngày mai" as
an example of a phrase "already correctly routed to UPCOMING_DOSES" (BUILD-
24D report 36, golden query_id 33) — that claim does not match what
`_UPCOMING_KEYWORDS` actually contains today. Either the keyword was
dropped in a later edit, or query_id 33 used different wording than a bare
"ngày mai" phrase; worth checking the golden set's own query 33 text before
changing anything.

## Why this matters beyond BUDGET_EXCEEDED

`OrchestrationIntent.UPCOMING_DOSES` is one of the intents in
`_GROUNDING_REQUIRED_INTENTS` (orchestrator.py). A "tomorrow" query
misrouted to `DRUG_INFORMATION` skips whatever grounding enforcement is
specific to the dose-schedule intents, and gets treated like a generic
drug-info question instead of a scheduling one. Whether this has caused any
visible defect on its own hasn't been checked — this task is to investigate
and fix the router gap itself, independent of BUILD-27.

## Suggested next step

1. Pull golden query_id 33 (source: `34-build-24c-golden-set-results.json`
   or later re-runs) and confirm its exact wording vs. what
   `_UPCOMING_KEYWORDS` actually catches today.
2. Add "ngày mai" / "ngay mai" (and any other missing bare-tomorrow
   phrasings, e.g. "mai" alone is too ambiguous/short to add safely) to
   `_UPCOMING_KEYWORDS`, following this router's own established evidence-
   based, narrow-keyword convention (see the file's own comments for
   precedent, e.g. BUILD-24G/24L).
3. Re-run the local 101-query golden retest
   (`scripts/agent_v2/local_golden_retest.py`) to confirm the change fixes
   the misroute without regressing any other query (a bare "mai" or
   similar could over-match something unrelated — check for that
   specifically).
4. Re-verify BUILD-27's own fix still holds once routing changes (the
   token-bound fix in `get_upcoming_doses` is intent-agnostic, so it should,
   but confirm with a real run once intent correctly reads UPCOMING_DOSES).

**Status:** open, not started.
