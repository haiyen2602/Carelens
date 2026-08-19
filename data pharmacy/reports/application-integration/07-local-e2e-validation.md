# APP-7 - Local End-to-End Validation

Date: 2026-08-17
Scope: local-only, reproducible PostgreSQL validation of the V2 application path. No Railway, Agent, production scheduler, notification provider, frontend change, or browser-E2E installation.

## Runtime boundary

The validation used the safe compatibility configuration below:

```text
DRUG_KNOWLEDGE_BACKEND=v2
PRESCRIPTION_V2_MODE=shadow
DOSE_RUNTIME_MODE=shadow
SAFETY_RUNTIME_MODE=shadow
```

`DOSE_RUNTIME_MODE=v2` was deliberately not enabled for full patient UI traffic. The photo verification routes still require legacy `DoseEvent` identifiers and there is no approved V2 photo bridge. In `shadow`, legacy remains the visible DTO/read path while V2 records deterministic sidecars and safety outbox rows only.

## Clean, reproducible database

A disposable `pgvector/pgvector:pg16` container was started without a Docker volume or reused state.

| Gate | Result |
| --- | --- |
| Alembic | `alembic upgrade head` reached `0027` |
| Canonical Drug Identity import, first run | `3556 drug_product`, `3556 drug_id_map`, `1406 ingredient`, `5287 drug_product_ingredient` created |
| Canonical import, second run | `0 / 0 / 0 / 0` created |
| Legacy category safety seed, first run | `49` created |
| Legacy category safety seed, second run | `0` created, `49` existing |
| Manifest integrity | PASS: all five Final Canonical V2 hashes were identical before and after both imports |
| Source artifacts | PASS: no artifact was changed |

The canonical source contains 5,779 product-ingredient source links. Its approved manifest identifies 5,287 importable links, 491 links skipped because no canonical ingredient is available, and one duplicate valid pair; the imported count reconciles to that manifest.

## Automated E2E evidence

All tests below used the clean PostgreSQL database above. No test used patient data from a Docker volume or committed any PII.

| Validation area | Evidence | Result |
| --- | --- | --- |
| Doctor create, approve, V2 sidecar, same-time multi-drug grouping, two daily times, legacy DTO order | `test_app6_shadow_compatibility.py`, `test_v2_catalog_prescription_http.py`, prescription service tests | PASS |
| Active plan to finite V2 occurrence generation; inclusive end-date; open-ended bounded window; on/off cycle | occurrence generator unit and PostgreSQL suites | PASS |
| Patient dose projection and actions `SCHEDULED -> DUE -> TAKEN / DELAYED / MISSED / SKIPPED` | V2 dose-runtime HTTP, state-machine, and runtime-adapter suites | PASS |
| Reviewed policy safety assessment, event log, escalation decision and outbox-only notification job | safety runtime/service/escalation unit and PostgreSQL suites | PASS |
| Legacy-unreviewed category fallback and unknown policy | safety runtime/service/escalation suites | PASS: fail-closed; no automatic clinical escalation |
| Retry/idempotency | importer/seed second run; occurrence generator; state, safety, and escalation idempotency tests | PASS: no duplicate sidecar/event/assessment/outbox rows |
| Edit/stop future scheduling | prescription service and V2 write-path suites | PASS: future work is cancelled/superseded; terminal history is retained |
| Invalid schedule and unresolved drug identity | V2 write-path and prescription service suites | PASS: V2 remains `REVIEW_REQUIRED`; no guessed ACTIVE schedule |
| Transaction rollback and locking/concurrency | PostgreSQL occurrence, safety-runtime, and escalation suites | PASS |
| Legacy/shadow regression | APP-6 comparison plus catalog/prescription/dose API regression | PASS |

Executed commands:

```text
pytest -q \
  tests/test_app6_shadow_compatibility.py \
  tests/test_v2_dose_runtime_http.py \
  tests/test_v2_dose_safety_http.py \
  tests/services/scheduling/test_occurrence_generator.py \
  tests/services/scheduling/test_occurrence_generator_postgres.py \
  tests/services/scheduling/test_dose_state.py \
  tests/services/scheduling/test_runtime_adapter.py \
  tests/services/scheduling/test_safety_runtime_adapter.py \
  tests/services/safety_policy_domain/test_service.py \
  tests/services/safety_policy_domain/test_runtime.py \
  tests/services/safety_policy_domain/test_runtime_postgres.py \
  tests/services/safety_policy_domain/test_escalation.py \
  tests/services/safety_policy_domain/test_escalation_postgres.py
# 43 passed, 3 skipped, 179 warnings

pytest -q \
  tests/services/prescription/test_service_db.py \
  tests/services/scheduling/test_write_path.py \
  tests/test_v2_catalog_prescription_http.py \
  tests/test_dose_status_update.py \
  tests/data_v2/test_backfill_prescription_v2.py
# 46 passed, 182 warnings

ruff check backend tests
git diff --check
# both passed
```

The three skips are conditional cases in the selected collection, not test failures; the PostgreSQL-specific occurrence, runtime, and escalation suites did execute on the disposable database.

## Post-validation correction: short catalog autocomplete

During the manual local session, the Doctor form correctly forwarded `q=a` to the V2 catalog but received zero results. This was a V2 catalog-search defect: the safety-oriented name scorer intentionally ignores tokens shorter than four characters, while the doctor combobox searches after every keystroke.

The catalog boundary now treats a single one-to-three-character query as deterministic token-prefix browsing, limited by the existing request limit. It does not alter `search_identity_candidates`, fuzzy matching, canonical mapping, or prescription validation; the clinician still explicitly selects the returned canonical item. A local frontend-proxy verification now returns eight canonical suggestions for `q=a`.

Regression evidence after the correction:

```text
pytest -q tests/services/drug_knowledge/test_v2_catalog.py tests/test_v2_catalog_prescription_http.py
# 3 passed
```

The regression covers one-character catalog suggestions, the maximum result limit, preservation of strict identity-candidate behavior, and the canonical catalog-to-prescription write path.

## End-to-end outcome

The automated local path is validated as:

```text
Doctor create/approve (legacy API contract)
  -> deterministic V2 prescription/schedule sidecar
  -> bounded per-drug occurrences
  -> legacy-compatible grouped patient-dose projection
  -> audited state transition
  -> MISSED/DELAYED safety assessment
  -> provenance-gated escalation decision
  -> idempotent notification outbox row only
```

The database still holds one occurrence per medicine per intended time. The UI grouping is only an adapter projection, including when multiple medicines have the same local time.

## Manual frontend acceptance checklist

Browser E2E tooling is not present and was intentionally not installed. Run this checklist against local frontend/backend only, with the shadow configuration above. Do not switch `DOSE_RUNTIME_MODE` to `v2`.

- [ ] Doctor signs in, selects a patient, searches/selects two canonical drugs, and creates a prescription with two times per day.
- [ ] Doctor confirms the displayed meal instruction, times, inclusive end date, and optional cycle fields round-trip after save/edit.
- [ ] Doctor approves the prescription; the existing prescription and dose UI remain usable with unchanged DTO shape.
- [ ] Patient sees same-time medicines grouped in one legacy dose card, in prescription-item order.
- [ ] Patient confirms a dose; refresh shows the legacy-compatible result with no duplicate card/action.
- [ ] Exercise delayed/missed presentation through the supported local UI path and confirm it does not expose unreviewed-policy clinical advice.
- [ ] Edit an active prescription and verify only future doses change; completed/terminal dose history remains visible.
- [ ] Stop the prescription and verify pending future cards disappear/cancel while terminal history remains.
- [ ] Enter an unresolved/manual drug and invalid time/count combination; confirm legacy form behavior remains compatible and no active V2 schedule is implied.
- [ ] Upload/photo-verify a legacy dose card in `shadow`; confirm this still uses its legacy `DoseEvent` identifier. Do not test this under `DOSE_RUNTIME_MODE=v2`.
- [ ] Check browser console and backend logs for no 5xx responses or accidental provider delivery.

Manual frontend acceptance: PASS (2026-08-18). The local tester completed the available frontend flow and reported it operating correctly after the catalog-autocomplete correction. Doctor flow manual: PASS. Patient dose flow manual: PASS. No 5xx, duplicate, or material user-visible regression was identified in this test session. This is manual evidence only; browser automation remains absent.

## P0/P1

- P0: none found in the clean local automated validation.
- P1: build and separately approve a V2 photo-verification bridge before enabling `DOSE_RUNTIME_MODE=v2` for the complete patient UI.
- P1: browser automation is absent. Manual acceptance is recorded above; retain it as the required evidence until a separately approved browser-E2E suite exists.
- P1: shared reviewed clinical-policy and recipient-resolution semantics are still needed before comparing V2 safety outcomes with legacy chat/photo escalation as clinical equivalents.

## Conclusion

APP-7: PASS

CLEAN DB: PASS - disposable PostgreSQL reached migration `0027`; canonical artifacts and 49 legacy safety policies imported idempotently with unchanged hashes.

AUTOMATED E2E: PASS - 89 tests passed across the API/service, V2 scheduling, state, safety, escalation, and regression matrix; 3 conditional cases skipped and 0 failed.

DOCTOR FLOW: PASS - create, approve, edit, stop, invalid/unresolved handling, and legacy contract compatibility are covered in `shadow`.

PATIENT DOSE FLOW: PASS - bounded per-drug generation, same-time grouping, date/cycle boundaries, terminal actions, retry, and concurrency are covered.

SAFETY FLOW: PASS - reviewed policy reaches durable assessment, event, provenance-gated escalation, and outbox; legacy-unreviewed and unknown policy fail closed.

LEGACY/SHADOW REGRESSION: PASS - public legacy DTO/read behavior remains intact; no provider delivery or duplicate user-visible dose rows occurred.

MANUAL FRONTEND ACCEPTANCE: PASS

DOCTOR FLOW MANUAL: PASS

PATIENT DOSE FLOW MANUAL: PASS

P0/P1:

- P0: none.
- P1: V2 photo bridge, browser automation, and approved shared policy/recipient semantics remain outside this task.

READY FOR APP-8: YES - local automated and manual acceptance gates have passed. This does not authorize `DOSE_RUNTIME_MODE=v2` full UI traffic, Railway deployment, a production scheduler/provider, or clinical-policy/recipient cutover.
