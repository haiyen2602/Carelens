# DRUG IMAGE B-02 — COLLECTION REPORT

**Status:** BLOCKED — source-use rights review is required before external image download.  
**Date:** 2026-08-26  
**Scope:** offline pipeline, frozen-source audit, local fixture tests, and dry-run only. No runtime DB/API/UI/chatbot/migration/deploy change was made.

## 1. Executive Summary

Implemented `scripts/data_v2/drug_image_collection.py`: a resumable B-02 collector which maps frozen Canonical V2 identity to the exact Long Chau raw snapshot and declared primary product image. It validates and normalizes only after an explicit rights gate; it writes offline JSONL manifest/queues and never accesses the runtime DB.

The dry-run resolves **3,545** eligible products, **2** `SOURCE_REVIEW`, and **9** `SOURCE_REDISCOVERY`. The six excluded IDs are not collected. No source bytes were downloaded because neither repo policy nor the reviewed public source material grants internal dataset use, derivatives, or redistribution.

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
| Internal dataset / public redistribution approval | NOT ESTABLISHED |
| Status | `SOURCE_RIGHTS_REVIEW_REQUIRED` |

The source pages checked were [robots.txt](https://nhathuoclongchau.com.vn/robots.txt) and [Chính sách nội dung](https://nhathuoclongchau.com.vn/chinh-sach/chinh-sach-noi-dung). The collector refuses HTTP unless both `--allow-source-download` and `--source-rights-status APPROVED` are passed; that guard is not legal approval.

## 5. Pipeline, Artifact Layout, and Validation

```text
frozen artifact -> source mapping -> URL validation -> rights gate
-> bounded/rate-limited HTTP -> type/size/decode/dimension/aspect validation
-> SHA-256 + URL/checksum dedup -> orientation-corrected RGB WebP
-> offline manifest + structured queues
```

The single-worker downloader is bounded, rate-limited to one second, uses a 20-second timeout and three exponential-backoff retries. It rejects HTML masquerading as image, corrupt files, invalid dimensions/aspect ratio, known placeholder URL/checksum, and never crops/upscales. It emits `DOWNLOAD_FAILED`, `INVALID_IMAGE`, `SOURCE_REVIEW`, `SOURCE_REDISCOVERY`, and `DUPLICATE_REVIEW` queues. Large binaries stay under the existing ignored `data/` policy; only code/tests/report are versioned.

## 6. Pilot, Bulk, and Validation Results

Source-network pilot and bulk collection are **N/A**, intentionally blocked by rights review. Offline fixture pilot is **PASS**.

```json
{
  "TOTAL_ELIGIBLE": 3545,
  "ATTEMPTED": 3545,
  "PLANNED": 3545,
  "SOURCE_REVIEW": 2,
  "SOURCE_REDISCOVERY": 9,
  "DUPLICATE_URL": 6,
  "DOWNLOADED": 0,
  "VALIDATED": 0
}
```

There are two duplicate primary-URL groups with six extra records. Content-checksum, placeholder, HTTP, image-decode, and normalization results are **N/A**, not zero-success claims, because no bytes were downloaded. Duplicate content is only flagged for review and never merges drug products.

## 7. Idempotency Evidence

The second `--dry-run --resume` produced no duplicate manifest rows:

```json
{
  "manifest_rows": 3545,
  "unique_image_record_ids": 3545,
  "product_ids": 3545,
  "resume_stat": "RESUMED_PLANNED=3545"
}
```

For approved collection, a valid existing derivative is checksum-verified and resumed without HTTP; failed records require `--retry-failed`. Both paths are fixture-tested.

## 8. Image Coverage and Downstream Readiness

Validated coverage is **0 / 3,545 (0%)**. Planned rows must not be consumed as images. B-06 must use its generic placeholder if no validated `drug_product_id -> image` link exists; it must not substitute a different brand.

Frozen snapshots reveal a B-01 discrepancy that needs review:

| Finding | Count |
|---|---:|
| Products with declared `primaryImage` | 3,545 |
| Products with source gallery length > 1 | 2,088 |
| Median gallery length / maximum | 4 / 26 |

B-02 intentionally collects only primary images, so collected multi-view coverage remains **0%**. This does not assert gallery items are validated product views.

| Check | Result |
|---|---|
| Reminder readiness | NOT READY |
| B-04 reference data | NOT READY |
| B-03 input | PARTIAL — mapping/contract ready, validated storage data absent |

## 9. Tests

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
python -m pytest --confcutdir=tests/data_v2 -p no:cacheprovider \
  tests/data_v2/test_drug_image_collection.py -q

12 passed in 9.12s
ruff check --no-cache scripts/data_v2/drug_image_collection.py \
  tests/data_v2/test_drug_image_collection.py

All checks passed
```

Tests cover source mapping/exclusions, manifest fields, real local image I/O, corrupt image, placeholder handling, URL/checksum dedup, deterministic path, idempotency, resume, retry failed, and no-download dry-run. The isolated invocation avoids unrelated runtime secrets and the preinstalled `deepeval` plugin.

## 10. Files Changed

- `scripts/data_v2/drug_image_collection.py`
- `tests/data_v2/test_drug_image_collection.py`
- `chat-bot-build/drug-image/DRUG-IMAGE-B02-COLLECTION-REPORT.md`

## 11. B-03 Recommendation and Release Gate

Obtain written source approval covering internal dataset storage, derivative normalization, intended product use, retention, redistribution, and permitted rate/volume. Then explicitly authorize a 20–50 product source pilot, review samples/placeholders/duplicate groups, run bulk collection, and update this report with real coverage.

| Gate | Result |
|---|---|
| DRUG IMAGE B-02 | BLOCKED |
| PARALLEL WORKTREE ISOLATION / TRACK A UNTOUCHED / BASELINE | PASS |
| SOURCE CONTRACT VERIFIED | PASS |
| SOURCE RIGHTS STATUS RECORDED | PASS — review required |
| PIPELINE / FIXTURE PILOT | PASS |
| SOURCE PILOT / BULK | N/A — rights blocked |
| IMAGE VALIDATION / CHECKSUM / URL+CONTENT DEDUP | Pipeline PASS; source-run evidence N/A |
| IDEMPOTENCY / RESUME / FAILURE QUEUES | PASS |
| SOURCE_READY | `3,545 expected / 3,545 planned` |
| VALIDATED PRODUCTS / COVERAGE | `0 / 3,545` / `0%` |
| MULTI_VIEW COVERAGE (B-02 collected) | `0%` |
| NO DB / MIGRATION / CHATBOT / UI / DEPLOY | PASS |
| REFERENCE DATA FOR B-04 | NOT_READY |
| B-03 READY | PARTIAL |
| READY FOR PR | YES — technical pipeline plus explicit blocker is ready for review |

**Stop condition:** do not download, publish, deploy, begin B-03, or alter Track A until source rights and a source pilot are explicitly authorized.
