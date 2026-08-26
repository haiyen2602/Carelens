# DRUG IMAGE B-03 — STORAGE & DATA MODEL REPORT

**Status:** PASS — local-only schema, storage, and import validation complete.
**Date:** 2026-08-26
**Scope:** B-03 runtime metadata/storage contract only. No recognition, chatbot, UI, production import, or deploy.

## 1. Executive Summary

B-03 adds a traceable `DrugImage` model owned strictly by canonical `drug_product_id`, a filesystem `StorageBackend`, and a resumable importer for validated B-02 manifest rows. Binary WebP derivatives are stored outside Postgres; Postgres stores identity, checksum, dimensions, deterministic storage key, source provenance, and primary-image state.

The local validation database imported all **3,543** validated B-02 rows. The two B-02 `HTTP_410` failures were excluded and no cross-product image fallback exists.

## 2. Parallel Workstream Safety and Baseline

| Check | Result | Evidence |
|---|---|---|
| B-03 branch/worktree | PASS | `feature/drug-image-b03-storage-schema`, `H:/Vin AI/P-067-drug-image-b03` |
| Baseline | PASS | `60311de490c22b65b0e98f920498b4b0f3acb156` (`origin/main`) |
| B-02 merged | PASS | PR #126 merged; `a9bbaf8` is reachable from `origin/main` |
| Alembic baseline | PASS | one head, `0051`, before this task |
| Track A isolation | PASS | BUILD-43 worktree observed only; its existing untracked `follow_up.py` was not accessed or changed |
| Runtime/production isolation | PASS | no production DB, deploy, Agent V2, UI, or chatbot mutation |

## 3. Existing Storage Audit

The repository has no S3, GCS, Supabase Storage, signed-URL abstraction, or public static-image policy. Existing `photo_storage_dir` is a local/Railway-volume filesystem convention for PHI-bearing dose photos and is delivered only through a protected API route. B-03 reuses that filesystem/volume approach but adds the separate `drug_image_storage_dir` (`./data/drug_images`) because catalog images are not dose-photo data.

The B-02 binaries are intentionally ignored artifacts and remained in their B-02 worktree. The importer requires explicit `--manifest` and `--artifact-root`; it never assumes binaries are committed to the runtime repository.

## 4. Final Data Model and Identity Rules

`DrugImage` has `id` (the stable B-02 `image_record_id`), `drug_product_id`, storage key, B-02 source URL/page/snapshot/product IDs, both checksums, MIME/dimensions/file size, view/primary/status/version, source retrieval time, and audit timestamps. `legacy_drug_id` is debug provenance only.

Ownership is never inferred from a name, filename, SKU, barcode, or fuzzy text. `drug_product_id` is a non-null FK to `drug_product`.

Constraints:

- `uq_drug_image_source_identity`: `drug_product_id + source_snapshot_id + source_url + checksum_sha256 + view_type`.
- `storage_key` is unique.
- partial unique index: one `is_primary=true`, `VALIDATED` image per `drug_product_id + collection_version`.
- immutable identity conflict returns importer `FAILED`; only page URL/product-ID/legacy provenance and retrieval time are mutable.

`DrugPackagingVariant` is deferred: B-02 provides source SKU as provenance but does not provide a separate, validated packaging identity or owner contract. SKU is never treated as a barcode.

## 5. Storage and Delivery Architecture

`FileSystemStorageBackend` atomically copies to:

```text
drug-images/{collection_version}/{drug_product_id}/{view_type}/{image_record_id}.webp
```

Including collection/product/view/image-record identity supports future versions, replacement, rollback, and non-primary views without overwriting old content. Duplicate binary checksums remain separate product-image rows and separate deterministic product paths; products are never merged.

Pre-merge hardening keeps the uniquely-created temporary file descriptor open while bytes are copied, flushes and syncs it, then atomically replaces the target. This removes the prior close-and-reopen path window; failed writes clean up their temporary file.

No public/signed URL policy was invented. The internal lookup returns a storage key and metadata; a future reviewed delivery/API task must decide exposure policy.

## 6. Importer, Dry-run, and Idempotency

Flow:

```text
B-02 manifest → schema/status validation → exact product lookup
→ derivative path/checksum verification → deterministic filesystem copy
→ metadata upsert → primary invariant
```

The importer rejects non-`VALIDATED` rows, missing products/artifacts, checksum mismatch, traversal paths, and immutable identity conflicts. It accepts only an explicit local PostgreSQL URL and supports `--dry-run`, which makes zero database/storage mutations.

Full local dry-run:

```json
{"TOTAL_MANIFEST":3545,"VALIDATED_INPUT":3543,"INVALID_INPUT":2,
 "PRODUCT_NOT_FOUND":0,"IMAGE_FILE_MISSING":0,"CHECKSUM_MISMATCH":0,
 "WOULD_CREATE":3543,"WOULD_UPDATE":0,"WOULD_SKIP":0,"FAILED":0}
```

Full local import produced `drug_image=3543`, validated primary images `=3543`, and storage objects `=3543`. The second full run produced `WOULD_SKIP=3543`, `WOULD_CREATE=0`, `WOULD_UPDATE=0`; no duplicate metadata rows or binary uploads were needed.

## 7. Reminder Lookup Readiness and Provenance

`get_primary_drug_image(drug_product_id)` returns only a validated primary image for the exact canonical parent. `get_primary_drug_image_for_legacy_id(legacy_drug_id)` first requires an `ACTIVE` `drug_id_map` mapping. Missing product/mapping/image returns `None` (`NO_IMAGE` for a later consumer), never another product's image.

The two `HTTP_410` products remain absent from `DrugImage`; B-06 must render its generic placeholder later. B-02 source URL, page URL, source snapshot, collection version, retrieval timestamp, and checksums are preserved without retaining raw source pages in runtime DB.

## 8. Migration and Tests

Migration `0052_drug_image_storage` is additive, has one parent (`0051`), and creates only `drug_image` plus focused indexes/constraints. On an isolated local PostgreSQL database, `alembic upgrade 0051 → 0052 → downgrade 0051` passed.

Targeted unit suite covers valid mapping, deterministic key, descriptor-backed atomic file copy, dry-run zero mutation, missing product/artifact, checksum mismatch, idempotent rerun, duplicate checksum across products, primary uniqueness, failed B-02 exclusion, canonical and legacy lookup, and no wrong-product fallback.

## 9. Known Limitations and Readiness

- Storage remains local-volume backed; public/signed delivery needs a later reviewed contract.
- B-02 has primary views only; multi-view coverage remains 0%.
- B-04 recognition input is partial: validated reference images are available, but no patient-photo/unknown/golden recognition corpus exists.
- B-06 can consume exact validated primary images; the two missing products require a generic placeholder.

| Release gate | Result |
|---|---|
| DRUG IMAGE B-03 | PASS |
| STORAGE ARCHITECTURE / DRUG_IMAGE MODEL / PROVENANCE | PASS |
| OWNERSHIP / PRIMARY INVARIANT / DUPLICATE CONTENT SAFE | PASS |
| ADDITIVE MIGRATION / UPGRADE-DOWNGRADE | PASS |
| IMPORTER / DRY-RUN / CHECKSUM / IDEMPOTENCY | PASS |
| EXPECTED VALIDATED B-02 / LOCAL IMPORTED | `3543 / 3543` |
| PRODUCTS WITH PRIMARY IMAGE | `3543` |
| NO WRONG BRAND SUBSTITUTION | PASS |
| REMINDER LOOKUP CHAIN | READY |
| B-04 INPUT | PARTIAL |
| B-06 INPUT | READY (two generic placeholders required) |
| NO RECOGNITION / CHATBOT / PRODUCTION DEPLOY | PASS |
| READY FOR PR | YES |

**Stop condition:** B-03 ends here. Do not merge/deploy or begin B-04/B-06 from this task.
