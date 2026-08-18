# APP-6 - Shadow and Compatibility Validation

Date: 2026-08-17
Scope: local-only comparison of legacy and V2 runtime projections before Local E2E. No production scheduler/provider, Railway, Agent, or public API/DTO expansion.

## Runtime modes validated

The comparison used explicit local flags:

```text
DRUG_KNOWLEDGE_BACKEND=v2
PRESCRIPTION_V2_MODE=shadow
DOSE_RUNTIME_MODE=shadow
SAFETY_RUNTIME_MODE=legacy
```

In this configuration legacy remains the public read and user-visible action path. V2 writes deterministic schedule/occurrence sidecars only. Safety shadow is separately gated; when enabled it persists only audited V2 assessment/decision/outbox rows and never dispatches a provider notification.

## Comparison results

| Flow | Result | Classification | Evidence |
| --- | --- | --- | --- |
| Drug identity | Public `legacy_drug_id` remains the API/form value; V2 resolves its canonical product internally. | `EXPECTED_V2_CHANGE` | Clean import: 3556 products and 3556 active maps; manifest hashes unchanged on both runs. |
| Prescription and schedule | A two-drug, same-time, two-day prescription created two legacy grouped `DoseEvent` rows and four V2 per-drug occurrences. UTC schedule, group count, `PENDING` projection, and ordered `expected_items` matched. | `EXPECTED_V2_CHANGE` | New clean-PostgreSQL APP-6 comparison test. V2 generator re-run: `0 inserted`, `4 existing`. |
| Same-time item order | V2 adapter initially ordered members by occurrence UUID, not legacy item index. | `V2_BUG` - fixed | Adapter now orders by `migration_item_index`, then occurrence ID; comparison retest passed. |
| Dose state | Legacy `PENDING` is projected from V2 `SCHEDULED`/`DUE`; V2 accepts only audited state transitions and writes immutable event logs. | `EXPECTED_V2_CHANGE` | APP-4/APP-5 state, retry, rollback, and concurrency tests passed. |
| MISSED/DELAYED safety | V2 routes to DB-4H/DB-4I policy and escalation domains; reviewed policy can create an outbox row, while legacy/unreviewed/unknown cases require review. | `EXPECTED_V2_CHANGE` | APP-5 clean PostgreSQL tests cover reviewed, legacy-unreviewed, unknown, idempotency, rollback, and locking. |
| Legacy chat/photo/escalation semantics | These flows use existing legacy tables and services in SHADOW; no V2 result is presented to their DTOs. Clinical equivalence cannot be asserted because they do not share a reviewed policy model. | `REVIEW_REQUIRED` | Legacy regression suite passed; no implicit cross-domain cutover was made. |
| Auth-backed regression fixtures | Several legacy tests minted a JWT without persisting its `Account`, which correctly returned 401 on a clean database. | `LEGACY_BUG` - fixed | Fixtures now create/remove active test accounts; runtime authorization was not weakened. |
| Source artifacts | No canonical artifact mismatch or source mutation was found. | no `DATA_MISMATCH` | Importer hash verification passed before/after each run. |

No unresolved `V2_BUG` or `DATA_MISMATCH` remains from the clean comparison.

## API and frontend compatibility

- `GET /api/v1/doses` remains legacy-backed in `shadow`. In explicit `v2` mode, the adapter returns the unchanged grouped dose DTO and preserves legacy item order.
- Prescription, dose, chat, photo, and escalation frontend proxy routes forward their existing methods, request bodies, and response bodies; no frontend source was changed.
- Photo verification, chat, and legacy escalation regression passed while SHADOW was enabled. They continue to use `DoseEvent`, legacy chat/audit/escalation models, and their existing contracts.
- Browser E2E remains unavailable: the frontend has no Playwright/Cypress configuration and local frontend dependencies are not installed. This task did not add an E2E stack.

## Clean PostgreSQL validation

A disposable `pgvector/pgvector:pg16` container was created on port 5433 without a volume or reused database state.

- `alembic upgrade head` reached revision `0027`.
- First identity import created `3556 | 3556 | 1406 | 5287` operational rows; the second import created `0` rows.
- The 49 legacy category policy seed re-run created `0` rows.
- Final Canonical V2 manifest/artifact hashes were identical before and after import.
- The shadow/photo/escalation matrix passed `199` tests; chat compatibility passed `14` tests after the clean-auth fixture correction.
- `ruff check` and `git diff --check` passed.

## Side-effect boundary

SHADOW produced no duplicate public dose rows and no provider delivery. Legacy remains the visible dose/photo/chat/escalation source in this mode. V2 idempotency keys and row locks prevented duplicate sidecar occurrences, assessments, events, and notification jobs. No Railway, Agent, scheduler, or notification provider was enabled.

## Remaining review items

- `DOSE_RUNTIME_MODE=v2` returns opaque V2 dose-group IDs. The existing photo verification endpoints require legacy `DoseEvent` IDs and have no approved V2 photo bridge. Keep production/UI traffic in `legacy` or `shadow` until that bridge is designed; no fallback is implicit.
- Legacy chat/photo escalations and V2 missed-dose policy are intentionally separate safety sources. A future comparison needs approved shared clinical-policy/recipient semantics, not guessed equivalence.

## Conclusion

APP-6: PASS

SHADOW COMPARISON: PASS - identity, schedule timing, grouping, state-domain behavior, and safety boundaries were compared on clean PostgreSQL; the one V2 ordering defect was fixed and retested.

MISMATCHES: PASS - all observed differences are classified above; no unresolved V2 bug or artifact data mismatch remains.

API/DTO COMPATIBILITY: PASS - legacy public DTOs and SHADOW read paths remain unchanged; V2 grouped-dose projection preserves item order.

LEGACY REGRESSION: PASS - prescription/dose, photo, escalation, and chat focused regression suites passed with account-backed auth fixtures.

P0/P1:

- P0: none.
- P1: design and validate a V2 photo-verification bridge before enabling `DOSE_RUNTIME_MODE=v2` for the full patient UI.
- P1: reviewed shared policy/recipient semantics are required before asserting clinical equivalence between legacy chat/photo escalation and V2 missed-dose safety.
- P1: browser E2E tooling is absent; APP-7 remains local API/service E2E unless a browser stack is separately approved.

READY FOR APP-7 LOCAL E2E: YES
