# 09 Drug Identity Import

Scope: Database Architecture V2, DB-4B and DB-4B.1. This report records the
local-only import of Final Canonical V2 drug identity references. No Drug
Knowledge/Search/RAG runtime setting, prescription/dose data, Railway service,
or shared database was changed.

## Verified baseline

- Branch at start: `feature/database-architecture-v2`
- Start commit: `e516de87311769d1143a801cc016883e00c00b9b`
- Current Alembic head: `0025` (`0024 -> 0025` adds the V2 schema). The
  earlier DB-4A reference to `0023` is historical and must not be forced.
- Canonical-data provenance commit: `29d601a` (`feat(data): rebuild drug data
  as Canonical V2 with source provenance (TASK-001)`).
- Manifest: `canonical-v2-final-2026-08-16`; `quality_status=PASS`,
  `rag_status=PASS`, `active_canonical=3556`.

The verified Final Canonical V2 identity artifacts are:

| Artifact | Source rows | Canonical SHA-256 |
|---|---:|---|
| `drug_product.jsonl` | 3,556 | `32E996934876899A861D207F3C786D0D19CB4E60AAE3E7D4FE82A11171D756C6` |
| `drug_id_map.jsonl` | 3,556 | `E44AAD49DAAF2D7B3B2A3DF1F08CBCAE725ED47D1DDCA6D4C3899719C4BD8ADB` |
| `ingredient.jsonl` | 1,406 | `CAA232B7647B3C995FD16A2D5C5B5673B552FFBFC5149B18F4F069DF5125F657` |
| `drug_product_ingredient.jsonl` | 5,779 | `2CC3148E8D324DE1B428903963D3AD6CE5F123590D8F06C70A213312A4BE54E6` |

All four hashes match both `manifest.json` and the Git blob bytes at the
provenance commit. The manifest itself hashes to
`567FEDBA30DE141A9BA970E8C02E641BA105BD16025949BF73F0716E01075A26`.

## Reproducibility investigation and resolution

The initial mismatch was not an artifact/provenance mismatch. Git global
configuration has `core.autocrlf=true`; Git therefore checked the LF canonical
JSONL blobs out as CRLF on Windows. The working-tree byte hashes differed while
the Git blobs and manifest hashes matched exactly.

No manifest was regenerated and no hash was changed to bypass validation.
Instead:

- `.gitattributes` pins the Final Canonical V2 JSONL files and manifest to LF
  checkout, so a clone of the resulting commit gets canonical bytes.
- The importer computes the JSONL manifest hash over the canonical LF byte
  representation. It accepts only CRLF/LF checkout variation; any content-byte
  change still fails closed against the manifest.
- The importer re-hashes every source artifact after import. Both validation
  runs returned the manifest hashes unchanged.

This makes Git plus the manifest the source of truth rather than a Docker volume
or a machine-local checkout setting.

## Import mapping and source exceptions

| Source artifact | Target | Imported handling |
|---|---|---|
| `drug_product.jsonl` | `drug_product` | Canonical ID and identity fields; `category -> category_id`; `status=ACTIVE`. `strength_text` remains `NULL` because package text is not a safe strength equivalent. |
| `drug_id_map.jsonl` | `drug_id_map` | Stable UUIDv5 row ID, `mapping_status=ACTIVE`, and source manifest version. Source has no ambiguous or retired mapping-status record. |
| `ingredient.jsonl` | `ingredient` | Canonical ID and `canonical_name -> name`. |
| `drug_product_ingredient.jsonl` | `drug_product_ingredient` | Stable UUIDv5 pair ID and only valid unique product/ingredient pairs. |

Of 5,779 source relationship rows, 5,287 unique valid pairs are imported.
491 `WARNING` rows have no canonical `ingredient_id` and are reported as
`MISSING_CANONICAL_INGREDIENT`; they are never guessed or inserted. One valid
pair is duplicated: `lonsurf-15mg-6-14mg-taiho-2x10` has two raw-strength /
sequence variants but the additive pair table has no columns that can preserve
that distinction. It is reported as `DUPLICATE_PRODUCT_INGREDIENT_PAIR`, not
silently converted into clinical data.

## Clean local PostgreSQL validation

Validation used an ephemeral local `pgvector/pgvector:pg16` Docker container
named `p067-db4b-clean`, port `5433`, with no mounted volume. `alembic upgrade
head` ran from an empty database to revision `0025`.

| Table | Source rows | Importable rows | After run 1 | Created run 1 | Created run 2 |
|---|---:|---:|---:|---:|---:|
| `drug_product` | 3,556 | 3,556 | 3,556 | 3,556 | 0 |
| `drug_id_map` | 3,556 | 3,556 | 3,556 | 3,556 | 0 |
| `ingredient` | 1,406 | 1,406 | 1,406 | 1,406 | 0 |
| `drug_product_ingredient` | 5,779 | 5,287 | 5,287 | 5,287 | 0 |

Read-only database checks after the second run:

| Check | Result |
|---|---:|
| Duplicate active `legacy_drug_id` | 0 |
| `drug_id_map` references missing product | 0 |
| Product without active mapping | 0 |
| Ingredient without product relationship | 0 |
| Product/ingredient link references missing product | 0 |
| Product/ingredient link references missing ingredient | 0 |

The importer uses primary-key upserts for product, mapping, and ingredient;
deterministic IDs; and `uq_drug_product_ingredient_pair` for junction pairs.
The second run created zero rows in every target table.

## Implementation and test evidence

- `scripts/data_v2/import_drug_identity_v2.py` validates manifest/source
  integrity before database access, permits only local PostgreSQL URLs, writes
  identity tables only, reports skipped/duplicate relationships, and emits a
  machine-readable summary with full exceptions.
- `tests/data_v2/test_import_drug_identity_v2.py` covers hash failure,
  LF/CRLF portability, unresolved mappings, unmapped and duplicate junction
  relationships, deterministic IDs, and local-target protection.

```powershell
python -m pytest --noconftest tests/data_v2/test_import_drug_identity_v2.py -q
ruff check scripts/data_v2/import_drug_identity_v2.py tests/data_v2/test_import_drug_identity_v2.py
python -m py_compile scripts/data_v2/import_drug_identity_v2.py
```

Result: `6 passed`; Ruff and bytecode compilation passed. The root pytest
bootstrap still has an unrelated FastAPI validation failure: a 204 route is
configured with a response body. It is outside this task.

## DB-4B DRUG IDENTITY IMPORT

IMPORT:

PASS. Final Canonical V2 identity data was imported into a clean local
PostgreSQL database at Alembic `0025`; no runtime/backend, prescription, dose,
Railway, or shared-database action occurred.

IDEMPOTENCY:

PASS. Re-running the importer created `0` product, mapping, ingredient, and
product/ingredient-pair rows.

COUNT RECONCILIATION:

PASS. Imported counts are `drug_product=3556`, `drug_id_map=3556`,
`ingredient=1406`, and `drug_product_ingredient=5287`. The 492-row difference
from the 5,779 relationship artifacts is fully accounted for by 491 unresolved
ingredient rows plus one duplicate valid pair.

ACTIVE MAPPING:

PASS. All 3,556 source mappings are active; duplicate active legacy IDs are 0;
maps to missing products are 0. `AMBIGUOUS=0` and `RETIRED=0` in the source
mapping artifact.

ORPHANS:

PASS. All database orphan checks returned 0.

AMBIGUOUS/UNMAPPED:

`AMBIGUOUS=0`; `RETIRED=0`; `UNMAPPED_INGREDIENT_RELATIONSHIPS=491`;
`DUPLICATE_VALID_PRODUCT_INGREDIENT_PAIRS=1`. The importer did not auto-map
or otherwise change any source exception.

P0/P1:

P0: none.

P1: 491 relationship rows need a canonical ingredient decision, and one
duplicate pair needs a schema/provenance decision if its raw-strength variants
must be retained separately. These were deliberately not backfilled.

REPRODUCIBILITY: PASS

MANIFEST INTEGRITY: PASS

IMPORT: PASS

IDEMPOTENCY: PASS

READY FOR PRESCRIPTION BACKFILL: YES
