# V1 Deprecation Audit & Plan

**Date:** 2026-08-16  
**Scope:** repository audit and removal plan only. No V1 code, `drug_chunks`, legacy files, API contract, or prescription data was changed.

## Audit conclusion

V2 is the default backend for *confirmed-drug knowledge lookup*, but V1 is still used by several live HTTP paths. Therefore, V1 cannot be deprecated yet. The audit itself is complete; the deprecation decision is blocked by the runtime dependencies and the deployment packaging gap below.

## Inventory and classification

| Dependency group | Classification | Evidence / reason |
|---|---|---|
| V1 `drug_chunks` candidate search | `ACTIVE_RUNTIME` | `/api/v1/chat` wires `build_drug_identity_resolution_node`; it calls V1 `fuzzy_name_search`, with V1 vector/lexical fallback in `backend/agents/nodes/drug_confirmation_nodes.py`. |
| V1 side-effect semantic retrieval | `ACTIVE_RUNTIME` | `build_side_effect_audit_node` and red-flag audit call `search_active_side_effect_chunks` against `drug_chunks`. This is safety-sensitive. |
| V1 severity source retrieval | `ACTIVE_RUNTIME` | `build_severity_node` calls `get_chunks_by_drug_id` and uses V1 field groups plus `muc_nghiem_trong`. |
| V1 `drug` catalog table | `ACTIVE_RUNTIME` | `GET /api/v1/drugs` uses `tim_thuoc`; prescription validation uses `lay_thuoc` to obtain trusted dosage form and administration route. Frontend consumes this endpoint. |
| V1 knowledge branch in `v2_agent.py` | `ROLLBACK_ONLY` | `DRUG_KNOWLEDGE_BACKEND=v1` returns `get_chunks_by_drug_id`; `shadow` returns V1 while comparing V2. |
| V1/shadow settings and HTTP validation scripts | `ROLLBACK_ONLY` / `TEST_ONLY` | `backend/config.py`, Cutover Gate, rollout, and stabilization scripts intentionally exercise both modes. |
| Legacy importer, compatibility mapper, and V1-vs-V2 evaluation | `MIGRATION_ONLY` | Required to reproduce the 3,562-ID mapping and comparative evidence; not called by application runtime. |
| `data pharmacy/*/thuoc.json` (11 files) | `MUST_KEEP` | Frozen Legacy V1 source, migration input, reproducibility evidence, and V1 rebuild source. It is not read by runtime deployment. |
| `data pharmacy/_chunks.jsonl` (36,125,717 bytes) | `MIGRATION_ONLY` | Ignored, derivable staging file; Phase 6 reads it for V1 comparison. Not a runtime input. |
| Legacy global hybrid node/tool (`build_retrieval_node`, `tra_cuu_thuoc_chung`) | `TEST_ONLY` / `SAFE_TO_REMOVE` candidate | It is no longer wired by `chat_routes.py`; current references are unit tests, its module, and tuning notes. Remove only after replacement V2 tests cover its safety invariants. |
| One-off V1 backfill and seed scripts | `MIGRATION_ONLY` | Preserve with the archive while V1 data or recovery remains supported; do not run against frozen legacy data. |
| `legacy_drug_id -> drug_product_id` mapping and public slug contract | `MUST_KEEP` | Prescription, API, frontend, and agent traces expose legacy `drug_id`; ADR-0012 explicitly preserves it. |

## API, prescription, frontend, and Agent

- **API:** public DTOs expose `drug_id` as the legacy slug. No public UUID is exposed. This contract must remain unchanged through deprecation.
- **Prescription:** no direct `drug_chunks` dependency, but `backend/services/prescription/service.py` validates non-empty `drug_id` against the V1 `drug` table. Removing that table now would break prescription creation/editing and trusted dosage-form lookup.
- **Frontend:** no direct V1 chunk access. It calls `/api/drugs`, then persists the returned legacy slug in prescription requests. It is indirectly dependent on the V1 catalog table.
- **Agent:** V2 is used after confirmed identity, but initial identity resolution, side-effect audit, and dose severity still use V1 retrieval. These are live, not rollback-only.

## Breaking risks and hard gates

1. **P1 - deployment packaging:** `.railwayignore` excludes all `data pharmacy/`, while `backend/main.py` warms V2 at startup and `v2_agent.py` loads JSONL from `data pharmacy/v2/`. The current `railway up` path can therefore start without V2 artifacts. Before changing V1 availability, prove a real deploy includes a versioned V2 artifact or move V2 data/index to a deployable DB/object-storage location.
2. **P1 - safety retrieval:** side-effect and severity flows still depend on `drug_chunks`. Replace them with V2 adapters and run focused safety/shadow HTTP evaluation before disabling V1.
3. **P1 - identity resolution:** the normal out-of-prescription resolver still searches V1 chunks. Move it to the V2 resolver/catalog before V1 removal.
4. **P1 - prescription catalog:** `/drugs` and prescription validation need a V2-backed catalog with the same slug contract and dosage-form fields.
5. **P2 - legacy severity metadata:** `muc_nghiem_trong` is V1 compatibility metadata, not a canonical medical fact. A V2 severity fallback requires a reviewed safety policy; it must not be silently inferred during migration.
6. **P2 - rollback:** deleting V1 eliminates immediate rollback. A retained, restorable V1 database snapshot and a tested rollback procedure are mandatory before any irreversible deletion.

## Recommended removal order

1. **Deprecate runtime use, not artifacts:** add V2 implementations for catalog lookup, identity resolution, active-drug adverse-effect lookup, and severity source selection; retain public legacy slugs and the compatibility map.
2. **Validate and declare a rollback window:** run V1/V2 shadow HTTP safety tests for each replaced path, deploy a V2 artifact through the real staging packaging route, and record exit metrics/owner/date. Keep `v1` and `shadow` available during this window.
3. **Archive V1 reproducibly:** create an immutable manifest plus database backup for `drug`, `drug_chunks`, index definitions, legacy JSON, `_chunks.jsonl` (or its derivation command), V1 embedding model/config, and the final V1 evaluation report. Verify restore in an isolated environment.
4. **Remove V1 runtime code in small changes:** first remove dead global hybrid code after test migration; then remove V1 catalog/retrieval call sites only after their V2 replacements pass. Remove `v1`/`shadow` modes last, together with rollback-specific tests and documentation updates.
5. **Remove data only after retention approval:** delete only redundant V1 DB tables/indexes and derived local staging data after the agreed rollback retention period. Keep the frozen legacy dataset and manifests as archived evidence for the project unless a separate data-retention decision authorizes deletion.

## Required evidence before a future removal PR

- V2 is available after a clean real staging deployment, including cold startup.
- HTTP safety suite covers identity, adverse effect, missed/delayed dose severity, pregnancy, contraindication, interaction, ambiguous, nonexistent, and multiple-drug cases with wrong-drug and wrong-type equal to zero.
- `/api/v1/drugs`, prescription create/edit, dose generation, and photo-verification form handling pass against V2-backed catalog data.
- V1 rollback drill has been executed from an archived snapshot; restore time and responsible owner are recorded.
- No runtime import/query of `backend.services.retrieval`, `drug_chunks`, or V1 `drug` remains, except explicitly approved archival tooling.

## V1 DEPRECATION AUDIT

```text
STATUS:
PASS

ACTIVE V1 DEPENDENCIES:
- drug_chunks: identity resolution, side-effect audit, dose severity
- drug table: /api/v1/drugs and prescription catalog validation

ROLLBACK-ONLY:
- DRUG_KNOWLEDGE_BACKEND=v1|shadow branches and their validation paths

SAFE TO REMOVE:
- legacy global hybrid retrieval node/tool after V2 test replacement
- derived _chunks.jsonl only after the V1 comparison archive is accepted

MUST KEEP:
- public legacy slug contract and drug_id_map
- frozen legacy dataset, provenance/manifests, V2 artifacts, and archive until retention approval

BREAKING RISKS:
- V1 is still live in three Agent paths and the catalog/prescription path
- Railway packaging currently excludes the V2 JSONL runtime artifact
- V1 severity fallback cannot be copied as a medical fact without review

RECOMMENDED REMOVAL ORDER:
1. Replace active V1 runtime paths with V2 and validate through real staging HTTP flow.
2. Keep v1/shadow for a defined rollback window, then archive and restore-test V1.
3. Remove V1 code/tests/config in reviewed increments; remove redundant data only after retention approval.

READY TO DEPRECATE V1:
NO

READY TO DELETE V1:
NO
```
