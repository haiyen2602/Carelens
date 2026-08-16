# V1 Runtime Replacement Report

**Date:** 2026-08-16  
**Scope:** replace active default-V2 runtime use of legacy retrieval/catalog data; retain `v1` and `shadow` rollback modes. No V1 artifact, legacy dataset, `drug` table, or `drug_chunks` data was deleted.

## Evidence

- V2 default HTTP stabilization: 64 cases, including 56 known-drug cases across all 10 knowledge types, 50 structured cases, 6 semantic/open queries, and 8 ambiguous/nonexistent/multiple-drug fail-closed cases.
- Stabilization results: wrong-drug `0`, wrong-type `0`, errors `0`, known-drug no-result `0`, structured-to-RAG regressions `0`, fail-closed `8/8` (100%). V1 rollback sample: `11` cases passed.
- Focused HTTP tests passed for `/api/v1/drugs`, prescription create/update, `SIDE_EFFECT`, `MISSED`, `DELAYED`, and the existing clinical red-flag route.
- Clean Docker image built successfully. It loaded V2 only from `/app/data/drug-knowledge-v2` and warmed `3,562` products and `42,654` knowledge chunks.
- Targeted regression suites: `7` chat/catalog HTTP tests, `1` V2 dose-safety HTTP test, and `41` resolver/side-effect/prescription/severity tests passed. The only test-environment warning is inability to write `.pytest_cache`.

## Replacement Inventory

| Former V1 default path | V2 replacement | Default-V2 behavior |
|---|---|---|
| Identity candidate lookup in `drug_chunks` | `V2AgentKnowledgeService.search_identity_candidates` | Deterministic normalized-name catalog resolution; ambiguous or unknown input stays fail-closed. |
| Active-drug side-effect/red-flag lookup in `drug_chunks` | `search_active_adverse_effects` filtered by product UUID and `ADVERSE_EFFECT` | No cross-drug chunk query in the V2 default path. |
| Severity source from V1 chunks and `muc_nghiem_trong` | V2 `INDICATION` + `ADVERSE_EFFECT` `SeveritySource` | Missing reviewed policy is `REVIEW_REQUIRED` with the existing medium fail-safe; legacy risk metadata is not promoted to a medical fact. |
| `/api/v1/drugs` and prescription catalog validation via `drug` | V2 catalog adapter over `drug_product` and `drug_product_ingredient` | Public `drug_id` remains the legacy slug; trusted dosage form/route and strength remain available. |
| Developer-local V2 JSONL path | explicit image artifact path `DRUG_KNOWLEDGE_V2_DIR=/app/data/drug-knowledge-v2` | Docker/Railway ignore rules include only the four required V2 artifacts. |

## Dependency Classification After Replacement

- `ACTIVE_RUNTIME` in the default `v2` HTTP flow: none of the replaced identity, side-effect, severity, catalog, or prescription paths query V1 `drug_chunks` or the V1 `drug` table.
- `ROLLBACK_ONLY`: local V1 imports in `v2_agent.py` execute only for `DRUG_KNOWLEDGE_BACKEND=v1|shadow`; `shadow` returns V1 while evaluating V2.
- `INACTIVE_LEGACY_COMPATIBILITY`: `tra_cuu_thuoc_chung`/`build_retrieval_node` is not wired by `chat_routes.py`; its V1 import is lazy so the V2 process does not load it on startup. It remains for rollback/history until a separate removal review.

## V1 RUNTIME REPLACEMENT

```text
STATUS:
PASS WITH ISSUES

ACTIVE V1 RUNTIME DEPENDENCIES:
- None in the default V2 HTTP paths replaced by this task.
- V1 retrieval remains reachable only through explicit v1|shadow rollback branches.

V2 REPLACEMENTS:
- Drug identity: V2 normalized resolver/catalog.
- Side effect and red-flag audit: V2 ADVERSE_EFFECT knowledge filtered to the active product.
- Severity source: V2 INDICATION + ADVERSE_EFFECT, REVIEW_REQUIRED plus fail-safe fallback.
- Drug catalog and prescription validation: V2 product/catalog adapter with legacy public drug_id.

DEPLOYMENT PACKAGING:
PASS
- Clean Docker image build and V2 warmup passed from /app/data/drug-knowledge-v2.

HTTP REGRESSION:
PASS
- 64 V2 default stabilization cases: wrong-drug=0, wrong-type=0, errors=0, fail-closed=8/8.
- Additional catalog/prescription and dose-safety HTTP paths passed.

PRESCRIPTION REGRESSION:
PASS
- Create/update preserve the legacy slug and overwrite untrusted dosage-form/route values from the V2 catalog.

SAFETY REGRESSION:
PASS
- SIDE_EFFECT uses V2 knowledge; MISSED/DELAYED use V2 severity sources; red-flag regression remains passing.

V1 ROLLBACK:
PASS
- 11-case V1 rollback sample passed in the HTTP stabilization suite.

READY TO DEPRECATE V1:
NO
```

## Open Issues

- A real Railway staging deployment and HTTP run was not performed: no staging service/project target was supplied, and this task must not deploy an unspecified environment. The clean-image verification removes the prior packaging dependency, but live staging remains the final gate.
- `494` ingredient parsing warnings and `21` unmapped headings remain `RAW_PRESERVED`/`REVIEW_REQUIRED`.
- `11` `NEW_PRODUCT` records remain in the review queue and were not added to the production corpus.
- Severity policy is intentionally conservative: it still needs medical review before replacing `REVIEW_REQUIRED` with a canonical severity policy.

V1, `drug_chunks`, frozen legacy data, the compatibility layer, and `v1|shadow` modes remain intact. No API or prescription contract changed.
