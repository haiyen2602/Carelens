# Drug Image UI/Media Fix — Railway Readiness Check

**Date:** 2026-08-27  
**Branch baseline:** `origin/main` `b451f03`  
**Scope:** patient medication-image presentation and chatbot image-selection UI. No production deployment, data import, schema change, or recognition enablement.

## Finding

The Railway services are online, but there is **no evidence that the B-03
catalog image artifact set and its `DrugImage` metadata were imported into the
production backend**.

The live patient screenshot shows the generic pill placeholder. In the shipped
client, that placeholder is rendered only when the authenticated dose API
returns `image.status = "NO_IMAGE"`; it is not a failed public-image request.
Thus, the current dose product did not resolve an exact validated primary image
from the production API response.

## Evidence reviewed

| Check | Result |
| --- | --- |
| Railway production FE | Online at `https://c3-app-067.up.railway.app` |
| Railway production BE | Online at `https://vmec-04be-production.up.railway.app` |
| BE visible persistent volume | `be-volume`, mounted for `photo_verifications` |
| B-03 expected catalog path | Separate `drug_image_storage_dir` (`./data/drug_images`) |
| B-03 artifact policy | B-02 binaries are intentionally ignored and require explicit manifest + artifact-root import |
| Local B-03 import evidence | 3,543 validated rows/files imported locally only |
| Exact production `drug_image` row/object count | `NOT_VERIFIED` — private Railway PostgreSQL query requires an SSH-key registration that was not authorized or performed |

The visible BE volume is not evidence of a persistent `drug_images` catalog
mount. Together with the exact-identity `NO_IMAGE` response observed in the
patient UI, the production catalog should be treated as **not ready** until a
controlled import and post-import verification are authorized.

## Safety and UI decision

- The patient UI must continue to render the generic placeholder for `NO_IMAGE`.
  It must not choose a product image by display name, brand text, OCR, or
  visual similarity.
- When an exact validated image is `AVAILABLE`, the patient can open a local
  preview from both the today card and the schedule list. The image remains
  fetched through the existing authenticated endpoint and Blob URL; no public
  storage route is introduced.
- Chat camera/upload choices use the existing B-07 API and retain the required
  candidate → explicit confirmation → canonical product boundary.
- B-08 remains controlling: `PRODUCTION RECOGNITION: NOT_APPROVED`. This UI
  branch does not enable, deploy, or make a production-quality claim for image
  recognition.

## Required controlled follow-up before production catalog images can appear

1. Obtain authorization and a deployment-equivalent access path for the
   production PostgreSQL database and backend volume/object store.
2. Provision persistent storage for `drug_image_storage_dir`, separate from
   private dose-photo storage.
3. Run the reviewed B-03 importer with the approved 3,545-row manifest and
   3,543 validated artifacts; do not infer ownership from display names.
4. Verify exact counts, checksums, `VALIDATED` primary-image uniqueness,
   active legacy mappings, and authenticated delivery for a prescribed pilot
   product.
5. Re-check the patient dose API returns `AVAILABLE` only for exact products;
   the two known upstream-410 products must remain `NO_IMAGE`.

This is a deployment-data operation and is intentionally outside this source
branch and outside the authorization given for this fix.

## Local verification

- `npm run test:drug-image-ui`: passed.
- Targeted ESLint and Prettier check for the changed frontend files: passed.
- `npm run build`: passed.
- `python -m pytest tests/services/test_drug_images.py
  tests/services/scheduling/test_runtime_adapter.py`: 14 passed. The run used
  process-local, non-production test secrets because the new worktree does not
  contain a committed `.env`; no production secret or database was used.
