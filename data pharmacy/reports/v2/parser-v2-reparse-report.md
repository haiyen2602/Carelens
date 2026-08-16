# Parser V2 Fix + Re-parse Gate

**Generated:** 2026-08-16T13:31:48.810931+00:00  
**Scope:** raw-snapshot reparse only. No website recrawl, canonical promotion, RAG/index rebuild, deployment, or Legacy mutation occurred.

## Root Cause

- The earlier parser inferred `duong_dung` only from `dosageForm`.
- `38` blank Fresh routes were ambiguous forms (for example gel/emulsion/solution) whose raw `content.dosage` explicitly states the route.
- The remaining route differences had deterministic source route evidence that conflicts with Legacy taxonomy; they are kept for review rather than guessed or overwritten.

## Reparse Output

- `data pharmacy/v2/full_recrawl/reparse/reconciliation.jsonl`
- `data pharmacy/v2/full_recrawl/reparse/candidate_*.jsonl`
- `data pharmacy/v2/full_recrawl/reparse/promotion_decisions.jsonl`
- `data pharmacy/v2/full_recrawl/reparse/final_promotion_gate_summary.json`

## PARSER V2 RE-PARSE RESULT

STATUS: **PASS WITH ISSUES**

PARSER VERSION:
- `longchau-v2.1.0`

PARSER ISSUES BEFORE: 63
PARSER ISSUES AFTER: 2

MISSING FIELDS BEFORE: 38
MISSING FIELDS AFTER: 2

REGRESSION: PASS

REVIEW REQUIRED:
- 44 records: 8 ambiguous identities, 1 source-missing record(s), and 35 source-evidenced differences.
- Parser keeps Legacy route for `micospray-20mg-cpc1hn-15ml, nady-rosa-nadyphar-80g` because their raw dosage forms are not sufficient to infer the legacy route safely.
- `491` ingredient warnings remain raw and unchanged.

P0/P1:
- None. Blank Fresh values are not promoted; all remaining differences are preserved as `KEEP_LEGACY` or `REVIEW_REQUIRED`.

READY TO RE-RUN PROMOTION GATE: YES
