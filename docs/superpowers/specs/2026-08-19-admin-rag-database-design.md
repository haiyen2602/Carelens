# Admin RAG Database-backed Drug View

## Goal

Replace the Admin RAG medicines mock dataset with read-only data loaded from the
canonical Drug Data V2 tables in PostgreSQL.

## Scope

- Backend endpoint `GET /api/v1/admin/drugs`.
- Backend endpoint `GET /api/v1/admin/drugs/{drug_product_id}`.
- Frontend Admin RAG page consumes these endpoints instead of `admin-mock` medicine data.
- Rows represent canonical `drug_product` records and include ingredients plus all
  `drug_id_map` records and their statuses (`ACTIVE`, `AMBIGUOUS`, `RETIRED`,
  `UNMAPPED`).
- Search, mapping-status filtering, stable sorting, pagination, loading, error and
  empty states are required.

## Explicit Non-goals

- No reindex endpoint, button, worker, or simulated indexing state.
- No create/update/delete mapping operation.
- No migration unless implementation proves an existing schema field is missing;
  missing fields must be reported for review rather than guessed.
- No change to `DRUG_KNOWLEDGE_BACKEND`, RAG retrieval, public `Thuoc` schema, or
  prescription backfill.

## Data Flow

Admin frontend -> admin API -> SQLAlchemy session -> `drug_product`,
`drug_product_ingredient`, `ingredient`, and `drug_id_map`.

The list endpoint returns one stable row per canonical product. Mapping records are
aggregated under that product, while the detail endpoint returns the complete
mapping and ingredient collections. The API must not expose records from a product
that does not exist.

## API Shape

List query parameters:

- `q` optional text search over canonical display name and legacy drug id.
- `mapping_status` optional enum filter.
- `page` one-based page number, default 1.
- `page_size` bounded page size, default 20.

The response contains `items`, `page`, `page_size`, `total`, and `total_pages`.
Each item contains canonical identity, display fields available in the schema,
ingredient names, mapping status summary, and mapping records.

Detail returns the same canonical identity with all ingredients and mappings.
Unauthorized callers receive the repository's standard authorization response.

## UI Behavior

The page removes the mock warning, mock-only actions, and the `Index lại` column.
It renders API data with explicit loading, request-error, empty-result, and
pagination states. Mapping statuses remain visible and filterable; no UI action
mutates database state.

## Testing

- Backend: query joins, aggregation, search, status filter, pagination, stable
  ordering, missing-product safety, and admin authorization.
- Frontend: API rendering, loading/error/empty states, status filter, pagination,
  and absence of reindex controls.
- Contract/OpenAPI response is reviewed against `specs/api-contracts.md` before
  implementation changes are merged.

## Open Constraints

The existing API contract is Draft for admin APIs. Implementation must add the
contract entry and record the change history before relying on the new endpoints.
