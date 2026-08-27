# Railway Drug Image Production Import Report

**Date:** 2026-08-27  
**Baseline:** `origin/main` / `d09f3e650054377871e33c6df14c60f52a686362`  
**Release-agent scope:** pre-import audit only  
**Result:** `STOPPED BEFORE PRODUCTION MUTATION`

## 1. Executive summary

No production import, upload, restart, redeploy, database mutation, or
recognition enablement was performed. The task stop rule was reached: the
Railway BE service has no persistent volume mounted at the configured drug
image storage path.

The frozen B-02 cohort is complete and checksum-clean locally. It cannot be
safely imported with the current production storage configuration, and the
existing B-03 command deliberately refuses non-local PostgreSQL URLs.

## 2. Production pre-import audit

| Item | Observed result |
| --- | --- |
| Railway project/environment | `VMEC-04` / `production` |
| BE service | `VMEC-04/BE` (`7523d6d4-7c4a-4551-9a17-13619c74680a`) |
| Current BE deployment | `bf9b0c92-cf4a-449c-b971-90749d5dc88b`, `SUCCESS`, 2026-08-27T09:00:55Z |
| Current BE volume | `vmec-04/be-volume`, 86.33 MB used, mount `/app/data/photo_verifications` |
| Drug image storage mount | `MISSING` — no volume at `/app/data/drug_images` |
| Runtime file listing of `/app/data/drug_images` | `NOT_VERIFIED` — Railway file access requires a registered loadable SSH key; none was added |
| Production `DrugProduct` / `DrugImage` / primary counts | `NOT_VERIFIED` — private PostgreSQL access is unavailable without registering a Railway SSH key or another approved access path |
| Three product → metadata → file samples | `NOT_RUN` — depends on the blocked database/filesystem access |

The current BE volume is designated for `photo_verifications`; it is not
evidence of a persistent B-03 catalog-image directory. A container-local
`./data/drug_images` path would be ephemeral and therefore fails the task's
persistence requirement.

## 3. Source dataset verification

| Check | Result |
| --- | --- |
| Manifest | `H:/Vin AI/P-067-drug-image-b02/data/drug-images/v1/manifest.jsonl` |
| Manifest SHA-256 | `CD49F88759409DCDB3452EB8F84843DFD3E00C74B906F19852A6D2545887AB2D` |
| Source cohort | `3545 / 3545` records |
| Validated artifacts | `3543 / 3543` |
| Known missing | `2 / 2`, both `HTTP_410` |
| Unique canonical `drug_product_id` among validated rows | `3543` |
| Missing WebP artifact referenced by validated manifest | `0` |
| Full normalized WebP SHA-256 sweep | `3543` checked, `0` mismatches |

All image ownership comes from the manifest's canonical `drug_product_id`;
there was no display-name, fuzzy, OCR, or cross-product mapping.

## 4. Existing importer audit

`scripts/data_v2/import_drug_images.py` reuses the B-03 `import_manifest`
service and supports manifest/artifact-root validation, checksum validation,
deterministic storage keys, dry-run, and idempotent upsert behavior.

It also calls `assert_local_postgres_url`, which rejects every database URL not
hosted at `localhost`, `127.0.0.1`, or `::1`. This is an intentional B-03 safety
guard. Therefore it **cannot be used against production** without a separately
reviewed release mechanism; no second importer was created in this audit.

## 5. Backup, rollback, dry-run, and import

These steps were not run because the persistent-volume gate failed before any
production mutation.

| Step | Result |
| --- | --- |
| Database metadata export/count snapshot | `NOT_RUN` — approved production DB access unavailable |
| Existing volume file-count snapshot | `NOT_RUN` — catalog mount absent |
| Rollback manifest | `NOT_PREPARED` — no safe production import plan exists yet |
| Production dry-run | `NOT_RUN` — stop rule |
| Production import | `NOT_RUN` — stop rule |
| Second idempotency import | `NOT_RUN` — stop rule |
| DB/storage/API/frontend/restart canaries | `NOT_RUN` — stop rule |

## 6. Required approved configuration before resuming

1. Attach a persistent Railway BE volume at the exact configured catalog path,
   preferably `/app/data/drug_images`, and set `DRUG_IMAGE_STORAGE_DIR` to that
   mounted path. Keep it separate from private dose-photo storage.
2. Provide an approved, auditable production PostgreSQL access path that allows
   read-only preflight counts and a controlled import transaction. Do not
   register a new SSH key or expose credentials without explicit authorization.
3. Review and approve a production-only release wrapper for the B-03 importer
   (or another approved mechanism) that preserves its canonical-ID/checksum/
   idempotency guards and writes only to the new volume.
4. Before the first write, export `DrugImage` metadata, capture file counts and
   deployment ID, record this manifest hash, and agree exact rollback commands
   targeting only manifest-listed rows/files.
5. Resume at production dry-run. Continue only if the dry-run reports zero
   unexpected missing artifacts, checksum mismatches, mapping conflicts, and
   cross-product conflicts.

## 7. Known missing products

The two frozen `HTTP_410` records remain absent by design and must return
`NO_IMAGE`; they must never receive another product's image.

## 8. Release gate

| Gate | Result |
| --- | --- |
| SOURCE DATASET | `PASS` |
| SOURCE VALIDATED IMAGES | `3543 / 3543` |
| KNOWN HTTP410 | `2 / 2` |
| RAILWAY PERSISTENT VOLUME | `FAIL` |
| PRE-IMPORT DrugImage | `NOT_VERIFIED` |
| PRE-IMPORT FILES | `NOT_VERIFIED` |
| DRY RUN | `NOT_RUN` |
| IMPORT | `NOT_RUN` |
| PRODUCTION DRUG IMAGE DATA | `PARTIAL` — source verified, production not imported/verified |
| READY FOR NORMAL PRODUCTION USE | `NO` |

`PRODUCTION RECOGNITION: NOT_APPROVED` from B-08 remains unchanged. This task
does not enable recognition and does not authorize a production application
deploy.
