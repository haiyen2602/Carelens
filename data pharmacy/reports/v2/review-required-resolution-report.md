# Review-Required Resolution

**Generated:** 2026-08-16T13:48:04.341860+00:00  
**Scope:** deterministic review of 44 existing `REVIEW_REQUIRED` records. No Canonical V2 promotion, index rebuild, deployment, or source crawl occurred.

## Decision Rules

- Route changes are approved only when the raw dosage form explicitly says infusion. A generic injection form retains Legacy.
- An ambiguous identity is approved only with exactly one captured search candidate matching name, ingredients/strength, dosage form, and package.
- A missing source result retains Legacy.
- All decisions include the snapshot, hash, URL, parser version, and source evidence in `review_required_resolution.jsonl`.

## Human Review

- `bisoprolol-stada-5mg-3x10`
- `esonix-40-3x10`
- `lucass-200-2x10`
- `pantogen-500ml`
- `scort-100-10x10`
- `vicometrim-960-10x10`

## Result

```text
REVIEW RESOLUTION RESULT

STATUS:
PASS WITH ISSUES

TOTAL: 44
APPROVE FRESH:
31
KEEP LEGACY:
7
HUMAN REVIEW:
6

AMBIGUOUS RESOLVED:
2
SOURCE CHANGES RESOLVED:
35
MISSING SOURCE:
1

P0/P1:
None

READY FOR CANONICAL PROMOTION:
NO
```
