# DRUG IMAGE B-06 — Medication Reminder UI Report

**Status:** Ready for PR review
**Task:** B-06 — Medication Reminder UI Integration
**Date:** 2026-08-26

## 1. Executive Summary

B-06 adds presentation-only catalog images to the existing patient **Hôm nay**
reminder surface. The backend resolves an image only from canonical product
identity, exposes `AVAILABLE` or `NO_IMAGE` in the existing dose response, and
delivers bytes through an authenticated route. The frontend uses a reusable
`MedicationImage` component with loading, missing-image, and failed-request
fallbacks. No recognition, OCR, user upload, medication fact generation,
database migration, deployment, or Track A work was added.

## 2. Parallel Workstream Safety

- Baseline was `origin/main` merge commit `3c27d6f6cf01f8d57c9c59b9a91db39f5ede161a` (B-05 merged).
- Worktree: `feature/drug-image-b06-reminder-ui`.
- Track A was not edited. No migrations were added; Alembic head remains `0053`.

## 3. Existing Patient Medication Flow Audit

The existing patient-facing medication/reminder surface is
`frontend/src/app/patient/page.tsx`: the next-dose hero and today's schedule
cards. There is no implemented medication list/detail route to invent. B-06
adds catalog-image support only to those existing surfaces; the existing dose
photo verification controls are unchanged and remain a separate patient-photo
flow.

## 4. Drug Identity Chain

The invariant is implemented and tested:

```text
DoseOccurrence / PrescriptionItem / MedicationPlan
  -> drug_product_id -> VALIDATED + is_primary DrugImage

legacy drug_id -> ACTIVE drug_id_map -> drug_product_id -> DrugImage
```

There is no lookup by display name, slug, checksum, OCR, OpenCLIP embedding, or
B-05 recognition result. Duplicate-content images remain owned by their own
canonical products.

## 5. Image Delivery Architecture

`GET /api/v1/drug-images/{drug_image_id}` accepts only an opaque image ID.
The backend selects only `VALIDATED` + `is_primary` metadata, resolves the
server-owned `storage_key` through `FileSystemStorageBackend.path_for`, and
returns trusted stored MIME metadata. It never accepts or exposes a storage
path, source URL, checksum, source snapshot, or dose-photo location.

Response headers are `Cache-Control: private, max-age=86400` and
`X-Content-Type-Options: nosniff`. The catalog route is separate from existing
photo-verification media routes.

## 6. Authorization

The route derives identity from JWT; it never trusts a request `patient_id`.
Access is granted only if the exact product appears in an authorized patient's
prescription item, medication plan, dose occurrence, or legacy dose JSON.

- patient: own JWT `patient_id` only;
- caregiver: accepted `CaregiverLink` only;
- doctor: patient where the JWT doctor is responsible or has `DoctorWatch`;
- admin/super-admin: catalog access remains allowed by the existing role model.

This replaced the older broad doctor/caregiver helper for this new route. A
missing authorization link fails closed with `403`.

## 7. API Contract

`specs/api-contracts.md` now documents additive per-item fields:

```json
{
  "drug_product_id": "...",
  "image": {
    "status": "AVAILABLE",
    "url": "/api/v1/drug-images/img_01",
    "alt": "Hình ảnh bao bì ...",
    "view_type": "front"
  }
}
```

`NO_IMAGE` always has `url: null`. Existing clients can ignore the new fields;
the response model continues to accept the legacy item shape.

## 8. Query / N+1 Strategy

V2 dose grouping batches canonical IDs once and legacy IDs once per dose-list
request. Legacy `DoseEvent` enrichment performs one active-map batch and one
primary-image batch for the full response. The no-image V2 legacy test records
three SQL statements for two medication items (occurrences/items, prescription,
and one map batch), rather than one image lookup per item.

The delivery route is one-image-at-a-time by design; it verifies the requested
opaque ID against the current caller's authorized medication set.

## 9. Frontend Component

`frontend/src/components/medication-image.tsx` fetches the protected binary
with the in-memory Bearer token, converts it to a short-lived browser Blob URL,
and revokes it on cleanup. This avoids making catalog images public solely so
an `<img>` element can load them.

States are explicit: `LOADING`, `AVAILABLE`, `NO_IMAGE`, and request/image
`ERROR`. Images have fixed dimensions, `loading="lazy"`, async decoding, and
`object-contain` so packaging is not distorted or cropped.

## 10. Placeholder, Accessibility, and Responsive Behavior

Missing/error states use generic `Pill`/`ImageOff` icon placeholders, never a
lookalike branded package. Placeholders and images have Vietnamese accessible
labels/alt text. Medication name, dose/quantity, time, and status remain visible
when the image is unavailable. The existing flex layouts wrap thumbnails for
long names and narrow screens.

## 11. Legacy and Missing-Image Behavior

Only `ACTIVE` legacy mappings resolve. Inactive/retired/missing mappings yield
`NO_IMAGE`, as do products without a validated primary image. B-02's two
terminal `HTTP 410` products have no `DrugImage`, therefore fall through to the
same generic placeholder without any substitute image.

## 12. Backend Verification

Executed successfully:

```text
python -m pytest \
  tests/services/test_drug_images.py \
  tests/services/scheduling/test_runtime_adapter.py \
  tests/api/test_drug_image_routes.py \
  tests/test_dose_summary.py \
  tests/test_v2_dose_runtime_http.py -q

27 passed
```

Coverage includes exact canonical lookup, no image, active/inactive legacy map,
no cross-product fallback, `VALIDATED` primary restriction, batch/no-N+1
behavior, patient/caregiver authorization, and existing V2 DTO compatibility.
The V2 HTTP regression test was corrected to send both its patient JWT and the
existing internal-secret header; it previously sent neither effective complete
header set for its list call.

`ruff format` and `ruff check` pass for all B-06 backend and test files.

## 13. Frontend Verification

- `npx prettier --check` with the repository's Windows CRLF convention passes
  for B-06 frontend files.
- `npm run build` passes (Next.js production compile and TypeScript check).
- `npm run test:admin-drugs` passes.

`npm run lint` currently fails across the pre-existing frontend repository
because its Prettier ESLint rule requires LF while tracked files use CRLF
(31,239 baseline formatting errors, including untouched files). This is a
repository lint-configuration issue, not a B-06 type/build failure; it is not
changed in this task to avoid an unrelated whole-repository line-ending rewrite.
No component-test runner is configured in `frontend/package.json`; production
build plus the stateful component implementation and backend contract tests are
the local verification available without adding a new test framework.

## 14. Local Catalog Pilot and Identity Evidence

Read-only pilot against the local B-04 catalog database/storage found:

```text
VALIDATED primary DrugImage rows: 3543
WebP artifacts under B-03 storage: 3543
Sample primary storage artifacts present: 3 / 3
```

The database currently contains 3,556 total `DrugProduct` rows, which is not
the frozen B-02 cohort. B-02/B-03 records remain the documented cohort of
**3,543 / 3,545** (two terminal HTTP 410 missing images); this pilot did not
re-run or mutate the 3,545-image collection/import.

## 15. Performance and Security

No full bulk was rerun. The batch query test guards the primary risk: list size
does not introduce a per-item image query. Catalog WebPs are reused as-is;
there is no new image-processing service or full-size duplicate download.

Security tests/implementation verify opaque-ID delivery, exact product
authorization, accepted caregiver links, inactive legacy rejection, and trusted
storage-key resolution. Log codes are limited to `IMAGE_NOT_FOUND`,
`IMAGE_UNAUTHORIZED`, and `IMAGE_STORAGE_MISSING`; no filesystem path or PHI is
logged. A corrupt binary reaches the frontend `onError` fallback without
blocking the reminder UI.

## 16. Notification Scope and B-07 Boundary

`NOTIFICATION_IMAGE = DEFERRED`. Push/email payloads are unchanged. B-06 does
not invoke recognition/OCR, add camera/gallery/upload controls, persist patient
images, or derive medical facts from catalog images. Those remain B-07 or
existing verification-domain work.

## 17. Release Gate

| Gate | Result |
|---|---|
| B-05 merged baseline / isolated worktree / Track A untouched | PASS |
| Canonical and ACTIVE legacy mapping only | PASS |
| Validated primary only / no fuzzy or cross-product fallback | PASS |
| Missing image and known B-02 HTTP 410 placeholder | PASS |
| Authenticated delivery / filesystem safety | PASS |
| API additive compatibility / no migration | PASS |
| No N+1 regression guard | PASS |
| Existing today-dose UI and text identity | PASS |
| Image available, missing, loading, and error states | PASS |
| Accessibility and responsive containment | PASS |
| Dose/adherence and notification logic unchanged | PASS |
| Recognition, OCR, upload, medical facts | NOT USED / NONE |
| Full frontend repository lint | BLOCKED BY PRE-EXISTING CRLF CONFIGURATION |
| Local build, targeted backend tests, catalog pilot | PASS |
| Production deploy / merge | NOT PERFORMED |
| B-07 ready | PARTIAL — B-06 intentionally provides no upload/recognition flow |
| Ready for PR | YES — subject to reviewer acknowledgement of frontend lint baseline |
