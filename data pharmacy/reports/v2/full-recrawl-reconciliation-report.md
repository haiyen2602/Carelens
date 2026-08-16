# Full Re-crawl + Data Reconciliation

**Generated:** 2026-08-16T13:07:26.623612+00:00  
**Scope:** local source capture and candidate reconciliation only. Canonical V2, V1, RAG, and deployment were not changed.

## Reproducibility

- Runner: `scripts/data_v2/full_recrawl_reconciliation.py` (`full-recrawl-v2.0.0`)
- Resume: `python scripts/data_v2/full_recrawl_reconciliation.py`
- State: `data pharmacy/v2/full_recrawl/checkpoint.json`; append-only event log: `events.jsonl`.
- Raw snapshots are immutable filesystem JSON files with source URL, retrieval time, SHA-256 content hash, parser version, and provenance.

## Outputs

- `data pharmacy/v2/full_recrawl/inventory.jsonl`
- `data pharmacy/v2/full_recrawl/events.jsonl`
- `data pharmacy/v2/full_recrawl/reconciliation.jsonl`
- `data pharmacy/v2/full_recrawl/review_queue.jsonl`
- `data pharmacy/v2/full_recrawl/raw_snapshots/nhathuoclongchau/*.json`
- candidate JSONL tables under `data pharmacy/v2/full_recrawl/`

## Validation

| Check | Result |
|---|---:|
| Legacy corpus | 3562 |
| Attempted | 3562 |
| All legacy IDs reconciled | YES |
| Silent canonical overwrites | 0 |
| Candidate knowledge items | 42559 |
| Ingredient parse warnings | 491 |
| Validation errors | 0 |
| Provenance coverage (successful fetches) | 3553/3553 |
| Duplicate candidate product IDs | 0 |
| Duplicate candidate knowledge IDs | 0 |
| Fresh fields missing where Legacy had content | 38 |

## Final Integrity Check

- `3,562/3,562` reconciliation rows have a unique legacy ID and a terminal status.
- `7,115` event-to-raw references were opened; every referenced snapshot has source URL, retrieval timestamp, parser version, raw payload, and a matching SHA-256 content hash.
- The frozen Legacy V1 SHA-256 manifest matches all current `thuoc.json` files.
- The Phase 2 Canonical V2 output-hash manifest remains unchanged.
- Canonical V2, Legacy V1, production RAG/index, and deployment were not written by this run.

## Review Requirements

- 8 ambiguous identities are isolated in the review queue; no canonical row was overwritten.
- 1 source-missing records are isolated in the review queue; no canonical row was overwritten.
- 491 fresh ingredient segments were preserved raw with parse warnings.

## FULL RE-CRAWL RESULT

STATUS: **PASS WITH ISSUES**

LEGACY TOTAL: 3562
ATTEMPTED: 3562
FETCH SUCCESS: 3553
FETCH FAILED: 0

MATCHED: 3480
CHANGED: 73
NEW PRODUCT: 0
AMBIGUOUS: 8
MISSING FROM SOURCE: 1

PROVENANCE COVERAGE: 3553/3553

DATA CONFLICTS: `73` changed candidates; `38` fresh fields missing where Legacy had content; no candidate was promoted or overwrote Canonical V2.

P0/P1 ISSUES: None detected

READY FOR FINAL DATA PROMOTION: NO
