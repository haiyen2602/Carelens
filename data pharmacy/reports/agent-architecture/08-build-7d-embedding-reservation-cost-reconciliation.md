# BUILD-7D — Embedding Reservation & Cost Reconciliation

Date: 2026-08-18  
Scope: remediation of BUILD-7C cost/idempotency P0 only. `AGENT_RUNTIME_ENABLED=false`
remains unchanged. No Vinmec Search, Doctor Handoff, Long-term Memory, or
BUILD-8 work was performed.

## Durable reservation boundary

Alembic revision `0031` adds `rag_embedding_reservation`. Before each paid
embedding call, the runner commits a deterministic reservation containing:

- corpus version and deterministic batch key;
- ordered chunk keys;
- planned token ceiling;
- lifecycle status and timestamps;
- provider request ID and API-reported input usage after response;
- temporary validated 1,536D response vectors until they are atomically
  applied to `drug_chunks` and checkpoints.

The lifecycle is `RESERVED → RESPONSE_RECORDED → COMMITTED`. A restart changes
a leftover `RESERVED` record to `UNRESOLVED`; it must be manually reconciled and
cannot be re-embedded automatically. A `RESPONSE_RECORDED` batch is resumed by
committing its staged response, without another OpenAI request. The global cost
guard evaluates committed `rag_corpus.actual_tokens` plus all outstanding
reserved/unresolved planned ceilings and uncommitted provider-reported usage.

## Historical reconciliation

BUILD-7C's historical aggregate is retained verbatim, not adjusted to make the
earlier budget appear to pass. A single `HISTORICAL_RECONCILED` ledger record
links to the registry's durable total:

| Measure | Value |
| --- | ---: |
| Active Canonical V2 drugs | 3,556 |
| Canonical exclusions | 6 |
| Stored chunks/checkpoints | 14,423 / 14,423 COMPLETE |
| Stored 1,536D vectors | 14,423 |
| Duplicate logical keys | 0 |
| Historical durable tokens | 18,899,846 |
| Historical durable cost | US$0.377997 |

The prior provider response IDs were not retained by BUILD-7C, so this is an
honest durable-ledger reconciliation, not a claim of invoice-level recovery.
Future requests record provider ID/usage before checkpoint application.

## Validation

- `alembic upgrade head` reached `0031`.
- A post-remediation corpus rerun had `pending_batches=0`; it made no embedding
  call, inserted no chunk, and preserved the durable total above.
- Registry cost recomputation (`actual_tokens × US$0.02 / 1M`) equals
  US$0.377997. Reservation status is one accounted historical reconciliation;
  there are no reserved, response-recorded, or unresolved rows.
- Corpus rows, distinct `chunk_key`, valid vectors, and checkpoints are all
  14,423.
- SQL regressions `test_word_similarity_threshold_guc_is_set_not_just_similarity_threshold`
  and `test_lexical_search_finds_exact_drug_name_match`: PASS.
- Focused regression suite: 25 passed.
- The final passing real retrieval smoke used one approved OpenAI request with
  22 input tokens / US$0.00000044. Both exact-product cases produced vector
  candidates, lexical candidates, and RRF results containing the expected ID:
  `agiclovir-5-agimexpharm` and
  `paracetamol-kabi-1000mg-frensenius-kabi-48-chai-x-100ml`.

An earlier approved 2-query natural-language smoke request did not satisfy the
current Paracetamol lexical threshold; its process exited before it emitted the
provider usage field. Its preflight ceiling was 42 tokens / US$0.00000084; with
the 22-token passing request, the combined smoke maximum is 64 tokens /
US$0.00000128, safely within the US$0.0001 authorization. No code path was
bypassed. The failed natural-language case is retained as a P1 recall-evaluation
finding, not treated as a failed exact-product retrieval gate.

## Conclusion

BUILD-7D: PASS

RESERVATION: PASS

COST RECONCILIATION: PASS (historical durable total retained as US$0.377997)

IDEMPOTENCY/RESUME: PASS

RERUN NO-OP: PASS

SQL REGRESSION: PASS

REAL RETRIEVAL SMOKE: PASS

FINAL DURABLE TOKENS: 18,899,846

FINAL DURABLE COST: US$0.377997

BUILD-7 FINAL: PASS

READY FOR BUILD-8: YES
