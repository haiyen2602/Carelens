# Final Data Promotion Gate

**Generated:** 2026-08-16T13:31:48.796933+00:00  
**Scope:** read-only review of Fresh candidates versus Legacy V1. No canonical promotion, RAG/index rebuild, deployment, or Legacy mutation occurred.

## Outputs

- `data pharmacy/v2/full_recrawl/promotion_decisions.jsonl` - one decision with provenance per legacy ID.
- `data pharmacy/v2/full_recrawl/changed_review.jsonl` - fresh/legacy/source comparison for all changed candidates.
- `data pharmacy/v2/full_recrawl/missing_field_review.jsonl` - evidence for every field fresh left empty while Legacy has content.
- `data pharmacy/v2/full_recrawl/unresolved_identity_review.jsonl` - ambiguous and missing-from-source records.
- `data pharmacy/v2/full_recrawl/ingredient_warning_review.jsonl` - raw ingredient warnings retained without inference.

## Changed Review

| Classification | Records |
|---|---:|
| `PARSER_ISSUE` | 2 |
| `SOURCE_CHANGE` | 35 |

All `CHANGED` records have a per-field Legacy value, Fresh value, raw-source evidence, source URL, content hash, snapshot ID, and parser version in `changed_review.jsonl`.

## Missing-Field Review

| Finding | Fields |
|---|---:|
| `PARSER_ISSUE` | 2 |

The `2` reviewed missing fields are all retained from Legacy for the gate decision. No blank Fresh field is treated as authoritative.

## Ingredient Warnings

`491` ingredient segments remain raw with their existing warning. This gate neither infers ingredient identity/strength nor changes parser output.

## FINAL DATA PROMOTION GATE

STATUS: **PASS WITH ISSUES**

APPROVED: 3516
KEEP LEGACY: 2
REVIEW REQUIRED: 44

CHANGED REVIEWED: 37/37
MISSING FIELDS REVIEWED: 2/2
AMBIGUOUS: 8
MISSING FROM SOURCE: 1
INGREDIENT WARNINGS: 491

P0/P1:
- None. All non-identical, unresolved, and parser-loss cases are fail-safe: kept from Legacy or marked `REVIEW_REQUIRED`; no Fresh candidate was promoted.

READY TO PROMOTE CANONICAL V2: NO
