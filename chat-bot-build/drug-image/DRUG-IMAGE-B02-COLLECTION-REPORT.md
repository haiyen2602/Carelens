# DRUG IMAGE B-02 — COLLECTION REPORT

**Status:** PASS — validated offline reference-image dataset collected.
**Date:** 2026-08-26  
**Scope:** offline pipeline, frozen-source audit, local fixture tests, and dry-run only. No runtime DB/API/UI/chatbot/migration/deploy change was made.

## 1. Executive Summary

Implemented `scripts/data_v2/drug_image_collection.py`: a resumable B-02 collector which maps frozen Canonical V2 identity to the exact Long Chau raw snapshot and declared primary product image. It validates and normalizes only after an explicit rights gate; it writes offline JSONL manifest/queues and never accesses the runtime DB.

The collection resolves **3,545** eligible products, **2** `SOURCE_REVIEW`, and **9** `SOURCE_REDISCOVERY`. The six excluded IDs are not collected. With explicit project authorization for internal B-02 collection recorded in this task, bulk collection validated **3,543 / 3,545** primary images (99.94%); two source URLs returned terminal `HTTP 410`.

## 2. Parallel Workstream Safety

| Check | Result | Evidence |
|---|---|---|
| Dedicated branch/worktree | PASS | `feature/drug-image-b02-collection`, `H:/Vin AI/P-067-drug-image-b02` |
| B-02 baseline / origin/main | PASS | `fd2b1d815b6a7ecc65fd0e8320063c4e105ea4a8` |
| B-01 baseline recorded | PASS | `fa815e1cca91a1120a665e0b5eb8b3dbbe645c06` |
| Track A isolation | PASS | BUILD-41 worktree observed only; never reset/rebased/checked out/edited. |
| Runtime/production isolation | PASS | No DB connection, migration, deploy, Agent V2 runtime, UI, or chatbot change. |

The shared `main` worktree had pre-existing untracked files; they were not used or changed.

## 3. Source Audit and Data Contract

Source mapping is exact and name-search-free:

```text
final_canonical/drug_product.jsonl
  + final_canonical/final_promotion_decisions.jsonl
  + full_recrawl/raw_snapshots/nhathuoclongchau/{snapshot_id}.json
  -> props.pageProps.product.primaryImage.url
  -> product gallery item 0 only if primaryImage is absent
```

Only active `PROMOTED_FRESH` records are eligible. `KEEP_LEGACY` records enter `SOURCE_REDISCOVERY`; missing/malformed promoted source data enters `SOURCE_REVIEW`. `source_product_id` is the explicit Long Chau SKU, never inferred as a barcode.

Each offline `manifest.jsonl` record contains:

```text
image_record_id, drug_product_id, legacy_drug_id, source_product_id,
source_snapshot_id, source_page_url, original_image_url, retrieved_at,
source_content_hash, image_checksum_sha256, normalized_checksum_sha256,
mime_type, width, height, file_size, normalized_format,
storage_relative_path, view_type, is_primary, validation_status,
validation_reason, parser_version, collection_version
```

The stable record ID is UUIDv5 over product ID, snapshot ID, and original URL; derivative paths are `images/{drug_product_id}/primary.webp`.

## 4. Source Rights / Usage Status

| Item | Result |
|---|---|
| Source page / image host | `nhathuoclongchau.com.vn` / `cdn.nhathuoclongchau.com.vn` |
| Repo policy or permission grant | NOT FOUND |
| Public robots policy | Product paths are not disallowed; robots rules are not a licence. |
| Public content policy | Supplies product images/info as reference; no downstream copying, dataset, derivative, or redistribution grant found. |
| Internal B-02 dataset approval | APPROVED by task owner on 2026-08-26 |
| Public redistribution approval | NOT ESTABLISHED; not in B-02 scope |
| Status | Internal offline collection approved; no public redistribution |

The source pages checked were [robots.txt](https://nhathuoclongchau.com.vn/robots.txt) and [Chính sách nội dung](https://nhathuoclongchau.com.vn/chinh-sach/chinh-sach-noi-dung). The collector refuses HTTP unless both `--allow-source-download` and `--source-rights-status APPROVED` are passed; that guard is not legal approval.

## 5. Pipeline, Artifact Layout, and Validation

```text
frozen artifact -> source mapping -> URL validation -> rights gate
-> bounded/rate-limited HTTP -> type/size/decode/dimension/aspect validation
-> SHA-256 + URL/checksum dedup -> orientation-corrected RGB WebP
-> offline manifest + structured queues
```

The single-worker downloader is bounded, rate-limited to one second, uses a 20-second timeout and three exponential-backoff retries. It rejects HTML masquerading as image, corrupt files, invalid dimensions/aspect ratio, known placeholder URL/checksum, and never crops/upscales. It emits `DOWNLOAD_FAILED`, `INVALID_IMAGE`, `SOURCE_REVIEW`, `SOURCE_REDISCOVERY`, and `DUPLICATE_REVIEW` queues. Large binaries stay under the existing ignored `data/` policy; only code/tests/report are versioned.

The pre-merge hardening removes the former URL-to-raw-bytes cache. A duplicate URL keeps only lightweight manifest metadata and reuses the first persisted, checksum-verified WebP derivative by atomic file copy; source bytes are released after each individual candidate is validated. All artifact writes now use unique same-directory temporary files. A `.drug-image-collection.lock` OS lock enforces a single writer for the entire CLI artifact run and fails fast if another collector owns the same output directory.

## 6. Pilot, Bulk, and Validation Results

Source-network pilot is **PASS**: 25/25 downloads validated, with a manual derivative spot-check. Bulk collection is **PASS**. Offline fixture pilot is also **PASS**.

```json
{
  "TOTAL_ELIGIBLE": 3545,
  "ATTEMPTED": 3520,
  "DOWNLOADED": 3518,
  "RESUMED": 25,
  "SOURCE_REVIEW": 2,
  "SOURCE_REDISCOVERY": 9,
  "DUPLICATE_URL": 6,
  "DUPLICATE_CHECKSUM": 7,
  "HTTP_410": 2,
  "VALIDATED": 3543
}
```

There are two duplicate primary-URL groups with six extra records, and three duplicate-content groups with seven extra records. The two failed URLs are preserved as non-retryable `HTTP_410` failures. Duplicate content is only flagged for review and never merges drug products.

## 7. Idempotency Evidence

The second `--dry-run --resume` produced no duplicate manifest rows:

```json
{
  "manifest_rows": 3545,
  "unique_image_record_ids": 3545,
  "validated": 3543,
  "failed": 2,
  "resume_stat": "RESUMED=3543, SKIPPED_FAILED=2",
  "failure_queues": "DOWNLOAD_FAILED=2, DUPLICATE_REVIEW=7"
}
```

For approved collection, a valid existing derivative is checksum-verified and resumed without HTTP; failed records require `--retry-failed`. Both paths are fixture-tested.

## 8. Image Coverage and Downstream Readiness

Validated coverage is **3,543 / 3,545 (99.94%)**. B-06 may use only a validated `drug_product_id -> image` link; the two failed products must use its generic placeholder and never a substituted brand image.

Frozen snapshots reveal a B-01 discrepancy that needs review:

| Finding | Count |
|---|---:|
| Products with declared `primaryImage` | 3,545 |
| Products with source gallery length > 1 | 2,088 |
| Median gallery length / maximum | 4 / 26 |

B-02 intentionally collects only primary images, so collected multi-view coverage remains **0%**. This does not assert gallery items are validated product views.

| Check | Result |
|---|---|
| Reminder readiness | READY FOR B-03/B-06 INPUT — two products require generic placeholder |
| B-04 reference data | PARTIAL — primary reference coverage is high; no phone-photo/unknown dataset and B-02 collected primary view only |
| B-03 input | YES — offline validated artifacts and manifest are available |

## 9. Tests

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
python -m pytest --confcutdir=tests/data_v2 -p no:cacheprovider \
  tests/data_v2/test_drug_image_collection.py -q

14 passed (targeted B-02 suite)
ruff check --no-cache scripts/data_v2/drug_image_collection.py \
  tests/data_v2/test_drug_image_collection.py

All checks passed
```

Tests cover source mapping/exclusions, manifest fields, real local image I/O, corrupt image, placeholder handling, URL/checksum dedup, deterministic path, idempotency, resume, retry failed, interrupted-checkpoint manifest recovery, same-directory single-writer protection, and no-download dry-run. The duplicate-URL test verifies one normalization followed by persisted-derivative reuse, rather than retaining source bytes in RAM. The isolated invocation avoids unrelated runtime secrets and the preinstalled `deepeval` plugin.

## 10. Files Changed

- `scripts/data_v2/drug_image_collection.py`
- `tests/data_v2/test_drug_image_collection.py`
- `chat-bot-build/drug-image/DRUG-IMAGE-B02-COLLECTION-REPORT.md`

## 11. Pre-merge Fix and Release Gate

The B-02 pre-merge review found and resolved the raw-image memory retention risk. No re-collection was needed: the frozen source contract, existing 3,543/3,545 derivatives, manifest semantics, and queues are unchanged. A representative fixture pilot now exercises duplicate URL reuse, restart after the 25-record checkpoint, idempotent resume, and writer contention. The completed 25-product source pilot and 3,545-product bulk result above remain the current collection evidence; no bulk run remains outstanding.

| Gate | Result |
|---|---|
| DRUG IMAGE B-02 | PASS |
| PARALLEL WORKTREE ISOLATION / TRACK A UNTOUCHED / BASELINE | PASS |
| SOURCE CONTRACT VERIFIED | PASS |
| SOURCE RIGHTS STATUS RECORDED | PASS — internal B-02 collection authorized; redistribution excluded |
| PIPELINE / FIXTURE PILOT | PASS |
| SOURCE PILOT / BULK | PASS — 25/25 pilot; 3,543/3,545 bulk validated |
| IMAGE VALIDATION / CHECKSUM / URL+CONTENT DEDUP | PASS |
| IDEMPOTENCY / RESUME / FAILURE QUEUES | PASS |
| SOURCE_READY | `3,545 expected / 3,545 actual eligible` |
| VALIDATED PRODUCTS / COVERAGE | `3,543 / 3,545` / `99.94%` |
| MULTI_VIEW COVERAGE (B-02 collected) | `0%` |
| NO DB / MIGRATION / CHATBOT / UI / DEPLOY | PASS |
| REFERENCE DATA FOR B-04 | PARTIAL |
| B-03 READY | YES — B-03 storage/schema work remains a separate task |
| PRE-MERGE MEMORY / SINGLE-WRITER HARDENING | PASS — raw bytes are not retained across URLs; one writer per artifact directory |
| READY FOR PR | YES — technical pipeline is ready for review |

**Stop condition:** B-02 ends here. Do not merge/deploy, begin B-03/B-04, or alter Track A from this task.
