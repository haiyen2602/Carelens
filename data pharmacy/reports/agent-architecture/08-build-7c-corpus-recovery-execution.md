# BUILD-7C — RAG Corpus Recovery Execution

Date: 2026-08-18  
Scope: recovery execution only. `AGENT_RUNTIME_ENABLED=false` was retained. No
BUILD-8 work, runtime cutover, or modification of the Canonical V2 TF-IDF index
was made.

## Deterministic preflight

The frozen V1 source (`data pharmacy/data-version1/*/thuoc.json`) was rebuilt
deterministically and filtered by Final Canonical V2 `drug_id_map.jsonl` and
`manifest.json`. It selected 3,556 active/approved legacy drug IDs and omitted
exactly the six Canonical V2 excluded IDs. The resulting corpus contains 14,423
chunks:

| Field group | Chunks |
| --- | ---: |
| `bao_quan` | 3,508 |
| `cach_dung` | 3,560 |
| `cong_dung` | 3,556 |
| `tac_dung_phu` | 3,799 |

The source manifest hash is
`39ABC318DCEF1AD5D4817005DC4621DA328DE3DB26CDE56FED5A412092A2C2C0`; the
ordered chunk manifest hash is
`E57B24693AE64F7B1514D820911C5804DCD71CB3AAF4CF45B17A2D87603E0C04`.
Preflight estimated 12,748,090 tokens / US$0.254962 for
`text-embedding-3-small` (1,536 dimensions), under the US$0.29 authorization.

Recursive Git attributes now require LF for Canonical V2 JSON/JSONL artifacts;
the existing nested RAG artifacts were verified against their manifest raw
SHA-256 values. No Canonical V2 TF-IDF index was changed.

## Execution evidence and fail-closed result

The first execution was deliberately stopped after a process interruption. Its
committed checkpoints permitted a resume. The resumed command completed all
14,423 database rows and produced the expected structural validation:

- checkpoints complete: 14,423;
- duplicate `chunk_key`: 0;
- missing/unexpected active drug IDs: 0;
- invalid vector dimensions: 0 (all 1,536D).

However, PostgreSQL's durable `rag_corpus` registry records **18,899,846 actual
tokens / US$0.377997**. This exceeds the approved US$0.29 maximum. The local
counter emitted by the final resumed process, and consequently its generated
manifest, shows only 12,748,090 / US$0.254962 and is not an authoritative total
across interruptions.

Cause: the implementation marks and accounts a checkpoint only after the
embedding response is received. If the process is interrupted between the API
request/response and the checkpoint transaction, the resumed process cannot
prove whether that request was billed and may embed the pending chunk again.
This violates both the cost cap and the "0 unnecessary embedding on rerun"
requirement. The gate requires a durable request reservation and provider usage
reconciliation before another paid attempt; the report does not alter registry
or manifest data to hide the discrepancy.

Per the task's cost rule, execution stopped at this gate. I did not run the
paid real retrieval smoke, a second paid/no-op execution, or the two SQL
regressions after the gate failed.

## Required remediation before a retry

1. Record a durable, uniquely keyed request reservation before an OpenAI call,
   including planned token ceiling and corpus/version/chunk keys.
2. Atomically transition it to a provider-response/accounted state before
   insertion; reconcile unknown in-flight requests using the provider request
   ID/usage rather than re-embedding them.
3. Derive the global cost guard from committed plus reserved/unreconciled
   usage, not from a process-local counter.
4. Reconcile the registry and generated manifest truthfully, then obtain a new
   spending authorization before any additional API request.

## Conclusion

BUILD-7C: FAIL

CORPUS: PASS (deterministic source/filter/count/hash preflight; committed row integrity passes)

EMBEDDING: FAIL (actual durable usage exceeded approved cap)

IDEMPOTENCY: FAIL (interruption/resume can re-embed uncheckpointed billable work)

PGVECTOR: PASS (14,423 stored vectors; all dimensions = 1536; no duplicate keys; active-ID membership validated)

SQL REGRESSION: NOT RUN (fail-closed cost gate)

REAL RETRIEVAL SMOKE: NOT RUN (would incur further API cost after gate failure)

ACTUAL TOKENS: 18,899,846 (durable registry; final-process local counter was 12,748,090)

ACTUAL COST: US$0.377997 (durable registry; exceeds US$0.29)

BUILD-7 FINAL: FAIL

READY FOR BUILD-8: NO
