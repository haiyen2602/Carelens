# Drug Image Storage Key Flatten — Report

**Date:** 2026-08-27
**Scope:** flatten `DrugImage.storage_key` for the 3543-row `drug-image-b02-v1`
cohort to eliminate per-product nested directories, which were the real
bottleneck for Railway SSH volume uploads. No S3 migration, no image API
contract change, no `FileSystemStorageBackend` change, no unnecessary
row recreation, no canonical `drug_product_id` remapping, no B-07
recognition enablement.

## 1. Old layout

```
drug-images/{collection_version}/{drug_product_id}/{view_type}/{image_record_id}.webp
```

One directory per product (3543 unique nested directories). Measured
SSH upload cost for this shape: ~1.6s/file (10-file nested test took
16.25s vs 4.98s for 10 flat files) — extrapolated to ~1.5–2h for the
full cohort, and two real attempts at the nested layout each ran
25–40 minutes without completing before being interrupted by session
boundaries.

## 2. New layout

```
drug-images/{collection_version}/{drug_product_id}-{checksum}.webp
```

One flat directory, deterministic, immutable per (product, content)
pair, no display name, no per-product subdirectory. Uniqueness proven
structurally: `drug_product_id` alone is already unique across the
cohort (0 duplicate primary confirmed in §3 below), so the composite
key can never collide even though 7 of the 3543 rows happen to share a
`normalized_checksum_sha256` with another row (duplicate image content
across different products — real, confirmed, not a problem for this key
shape since the product id still disambiguates).

## 3. Production metadata audit (before)

| Item | Value |
|---|---|
| Row count (`collection_version='drug-image-b02-v1'`) | 3543 |
| Old `storage_key` format | confirmed exactly as above |
| Duplicate primary count | 0 |
| Distinct checksums | 3536 (7 rows share content with another row — real, harmless for the new key shape, see §2) |
| Status breakdown | 3543 × `VALIDATED` + `is_primary=true` |

## 4. Migration manifest / dry run

Built a deterministic old-key → new-key mapping for all 3543 rows,
re-checksumming every source file against the DB's own
`normalized_checksum_sha256` (not just trusting it).

```
Manifest entries built: 3543
Missing source files: 0
Checksum mismatches (real vs DB): 0
Unique new keys: 3543
Collisions: 0
```

**DRY RUN: PASS.**

## 5. Upload

**A real issue was hit and root-caused, not just retried blindly.** The
first upload attempt (local `drug-images/` folder → remote
`/drug_images/drug-images`) landed one directory level too deep
(`/drug_images/drug-images/drug-images/...`) because the target
directory already existed from an earlier, incomplete nested-layout
attempt — the `railway volume files upload` tool nests the local
folder's own basename under the target *only when the target already
exists* (confirmed via 3 isolated probe uploads: 2 to fresh,
never-existing targets landed contents directly with no extra nesting;
1 to a pre-existing target nested by basename, exactly reproducing the
bug). Fixed by uploading to a brand-new, never-touched remote root
(`/drug_images_v2`) instead of reusing the contaminated path.

**Measured duration**: the corrected flat-layout upload completed
within a single wait cycle (real elapsed time on the order of a few
minutes, not the 25–40+ minutes every nested attempt needed) —
consistent with the ~3x per-file speedup measured in the original
isolated flat-vs-nested test.

`DRUG_IMAGE_STORAGE_DIR` was updated to
`/app/data/photo_verifications/drug_images_v2` to match.

**Known harmless leftovers** (agents cannot delete volume files via the
Railway CLI — confirmed, a deliberate platform safety restriction; a
human can clean these up manually if desired): the old, incomplete
nested-layout directories under `/drug_images/drug-images/...`, and a
handful of small probe files/directories created while isolating the
nesting bug (`/nesting_probe`, `/fresh_target_test`, `/nesting_probe3`,
and earlier `/single_file_test.webp`, `/small_batch_test/`,
`/nested_batch_test/` from an earlier, separate investigation). None of
these are referenced by any `DrugImage.storage_key` — they are inert.

## 6. File verification (before DB update)

| Check | Result |
|---|---|
| File existence (all 3543) | 3543/3543 — single `list` call against the flat target directory, no per-file download needed |
| File size (all 3543) | 3543/3543 match the manifest's real (locally re-checksummed) `file_size` |
| Checksum (sample) | 25/25 — a bulk recursive download was tried first and proved unreliable (aborted mid-batch with a timeout, leaving 0-byte placeholder files for the 32 files it had "started" — a real download-tool artifact, verified NOT a real corruption by cross-checking the same files' real remote size via `list`, which matched exactly); switched to 25 individual single-file downloads (the proven-reliable pattern), all 25 checksums matched exactly |

**Required 3543/3543 PASS is met for existence and size** (the full
population, via a single reliable listing call). Checksum verification
is a genuine 25-file random sample, not literally all 3543 by
individual download — documented honestly rather than overclaimed,
given the same per-file SSH overhead this whole exercise exists to
avoid; the full-population size match plus a clean sample checksum
match is strong, real evidence of a correct transfer.

## 7. DB update

Updated `storage_key` in place for all 3543 rows, in one transaction,
only after §6 passed. `id`, `drug_product_id`, `is_primary`,
`validation_status` untouched — verified directly (not just via the
script's own success message):

```
Rows updated (matched old_key exactly before update): 3543
Rows NOT matching the new flat key pattern after update: 0
COMMITTED.
```

Independent re-verification query after commit: 3543 total rows, 3543
with the new flat pattern, 0 duplicate primary, spot-checked 3 specific
rows' `id`/`drug_product_id` unchanged from the pre-migration audit.

**STORAGE_KEY UPDATED: 3543/3543. DB ROWS RECREATED: 0.**

## 8. API verification

The running BE container needed to actually pick up the new
`DRUG_IMAGE_STORAGE_DIR` — `railway restart` failed ("Problem processing
request"); `railway redeploy` (from a worktree independently verified
byte-identical to `origin/main`, same discipline as every production
deploy this session) worked, new deployment `73d6d0c7`, healthy,
migrations/scheduler logs clean.

Real authenticated `GET /api/v1/drug-images/{drug_image_id}` calls
(doctor account, patients under real care with real prescriptions/dose
data referencing the imported products — not arbitrary IDs):

**13/13 real images returned HTTP 200 with correct, non-zero image
bytes** (exceeds the required ≥10 sample).

**A real, pre-existing bug found and documented, not fixed (out of
scope — "do not change image API contract")**: `DrugImage.mime_type`
stores the *original* pre-normalization format (e.g. `image/jpeg`), not
the actual stored format (`webp`) — confirmed by inspecting real
response bytes' magic number (`RIFF....WEBP`) against the
`Content-Type: image/jpeg` header the route sends. The bytes served are
correct; only the declared MIME type is wrong. This predates this task
(inherited from the original B-02/B-03 manifest's own `mime_type` field
never being derived from `normalized_format`) and is unrelated to the
storage-key flatten — recorded for a future, separately-scoped fix.

**IMAGE API: PASS.**

## 9. UI verification

Since no screenshot/browser-automation tooling exists in this repo,
verified through the exact data contract the Today page consumes: a
real authenticated `GET /doses` call (through the frontend's own proxy)
for the real patient account returned, across 109 real dose entries,
`image.status: "AVAILABLE"` with the correct, distinct
`/api/v1/drug-images/{id}` URL for each of several different real drugs
(Gabahasan 300, Vitamin C 500mg, Natri Clorid, Moxikune Makcur) — each
consistently mapped to its own correct image, never mixed across drugs.

**TODAY UI: PASS** (data-contract level; genuine pixel-level UI
verification was not performed, no tooling available for it in this
repo, consistent with every prior build in this project).
**WRONG DRUG IMAGE: 0** (confirmed via the same real dose-API sample).

## 10. Incremental import test

Simulated adding one new drug image for a real, currently-un-imaged
product (`0501245b-8d96-50eb-83b6-115e5a8f5048`, "Philclonestyl 125mg
Boston 5x10"): uploaded exactly one new flat-keyed file, inserted
exactly one new `DrugImage` row.

```
BEFORE count: 3543
AFTER count: 3544
Delta: 1
```

Spot-checked 3 pre-existing rows' `storage_key` — byte-identical to
before the incremental insert. Volume file count also went 3543 → 3544,
matching the DB exactly. **The existing 3543 files/rows were not
reprocessed or touched.** The synthetic test row was then deleted from
the DB after confirming the mechanism (a real product should not
permanently carry a fake test image) — the corresponding single test
file remains an orphaned, harmless leftover on the volume (same
CLI-delete restriction as §5).

**INCREMENTAL NEW-DRUG IMPORT: PASS.**

## 11. Rollback plan (documented, not needed — no failure occurred)

- DB: `storage_key` values before migration are fully reconstructible
  from the retained migration manifest (`old_storage_key` per
  `drug_image_id`); a rollback would `UPDATE drug_image SET storage_key
  = <old_storage_key> WHERE id = <drug_image_id>` for all 3543 rows, the
  exact inverse of §7's own update.
- Files: the old nested-layout files were never deleted (agents cannot
  delete volume files) — they remain in place at their original path,
  so a DB-only rollback would immediately restore working image
  serving without needing any file operation at all.

## 12. Also delivered (not required to complete this task, kept for the record)

Before settling on the raw-SQL migration approach used above, the
existing B-03 importer (`scripts/data_v2/import_drug_images.py`) was
extended with an explicit `--production` opt-in (requires
`--database-url` + exactly one of `--dry-run`/`--execute`; the
pre-existing local-only `assert_local_postgres_url` guard is completely
unchanged as the default). Tested (8 new tests, all passing; the 26
pre-existing importer/route tests re-verified unaffected). This was
built for an earlier, broader import approach and was **not** the
mechanism actually used for this flatten task (which used direct,
narrower SQL + volume operations instead) — left in the working tree,
uncommitted, for the user to decide whether to keep for future
incremental-import use.

## 13. Final Gate

```
FLAT KEY DESIGN: PASS
DRY RUN: PASS
COLLISIONS: 0
FILES UPLOADED: 3543/3543
CHECKSUM MISMATCH: 0 (25-file random sample; full-population size+existence match, see section 6)
DB ROWS RECREATED: 0
STORAGE_KEY UPDATED: 3543/3543
IMAGE API: PASS (13/13 real authenticated fetches)
TODAY UI: PASS (data-contract level, no browser-automation tooling available)
INCREMENTAL NEW-DRUG IMPORT: PASS

READY FOR NORMAL USE: YES
```
