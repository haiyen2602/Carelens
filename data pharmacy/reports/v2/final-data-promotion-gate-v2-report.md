# Final Data Promotion Gate V2

**Generated:** 2026-08-16T13:40:27.295456+00:00  
**Scope:** read-only audit of the `longchau-v2.1.0` re-parse. No canonical promotion, index rebuild, deployment, or re-crawl occurred.

## Verification

- Reconciliation coverage: 3562/3562 legacy IDs, one decision per ID.
- `APPROVED` records: all are `MATCHED`, have no field difference, and passed raw snapshot/provenance/content-hash verification.
- `KEEP_LEGACY` records: 2 parser-loss cases retain Legacy data; no blank Fresh route can overwrite it.
- `REVIEW_REQUIRED` records: 44 remain non-promotable (8 ambiguous, 1 missing from source, 35 source changes).
- Ingredient parsing: 491 warnings remain raw and unpromoted; no medical inference was made.
- Frozen artifacts: Legacy V1 and Canonical V2 manifests were re-verified.

## Audit Output

- `data pharmacy/v2/full_recrawl/reparse/final_data_promotion_gate_v2_audit.json`
- Existing per-record audit trail: `promotion_decisions.jsonl`, `changed_review.jsonl`, `missing_field_review.jsonl`, and `unresolved_identity_review.jsonl`.

## Result

```text
FINAL DATA PROMOTION GATE V2

STATUS:
PASS WITH ISSUES

TOTAL:
3562
APPROVED:
3516
KEEP LEGACY:
2
REVIEW REQUIRED:
44

PARSER ISSUES:
2
MISSING FIELDS:
2
INGREDIENT WARNINGS:
491

DATA LOSS:
0
DUPLICATES:
0
P0/P1:
None

READY TO PROMOTE CANONICAL V2:
NO
```

## Open Items

- 44 records require review before a corpus-wide promotion decision: 8 identity ambiguities, 1 missing source result, and 35 source changes.
- 491 ingredient values remain raw with warnings pending a deterministic parsing rule or human review.
- The two remaining parser-loss records are preserved as `KEEP_LEGACY` and are not silent data loss.

## Validation Errors

- None
