# APP-2 — V2 Integration Design

**Ngày:** 2026-08-17
**Scope:** thiết kế runtime integration sau APP-1.1. Không sửa frontend, API, runtime, migration, feature flag, canonical artifact, Railway hay Agent.

## Decision summary

Doctor Prescription là flow đầu tiên. V2 không thay thế ngay `Prescription` legacy: trong APP-3, legacy prescription vẫn là compatibility envelope và lifecycle contract công khai; V2 trở thành nguồn chuẩn cho **canonical drug identity và executable per-item scheduling intent**. Mọi write phải đi qua application boundary gọi domain service, không route/UI ghi V2 ORM trực tiếp.

`V2_PRIMARY` trong phase này chỉ có nghĩa là primary for the V2 scheduling-intent write boundary for a fully resolved prescription. `GET /prescriptions`, legacy `Prescription.items[]`, legacy status và grouped `DoseEvent` vẫn là read/compatibility source cho đến APP-4. Không có cutover dose runtime trong APP-3.

## RUNTIME MODES

| Flow | `LEGACY` | `SHADOW` | `V2_PRIMARY` | `V2_WITH_LEGACY_FALLBACK` |
| --- | --- | --- | --- | --- |
| Drug search/select | `DRUG_KNOWLEDGE_BACKEND=v1`; legacy catalog result | Existing `shadow`: return V1 and log V1/V2 counts | Existing `v2`: Canonical JSONL catalog returns legacy-compatible DTO | Chưa thêm implicit fallback. V2 catalog outage không được âm thầm trộn nguồn; rollback là explicit `v1` flag. |
| Prescription create/edit/approve | Legacy `Prescription` + generator only; no V2 write for an emergency rollback | One atomic transaction writes legacy plus deterministic V2 sidecar; response/read remains legacy; V2 never generates occurrences | Same atomic transaction; complete resolved V2 item/plan/rule becomes `ACTIVE` on approval and is authoritative for future APP-4 scheduling | Only a known **data disposition** (`REVIEW_REQUIRED`) may retain legacy behavior while V2 remains review-only. Infrastructure/domain exception never auto-falls-back after an uncertain commit. |
| Prescription read/display | Legacy `PrescriptionOut` and `items[]` | Same legacy response; compare normalized V2 representation internally | Same legacy response in APP-3; no V2 read endpoint yet | Same as legacy; fallback reason is observable only in safe technical/audit logging. |
| Stop/cancel | Current legacy stop/cancel future `DoseEvent` | Legacy stop plus V2 plan/rule stop in one transaction; APP-3 invariant: V2 occurrence count is zero | Same; no V2 occurrence cancellation is claimed before APP-4 | If V2 stop write fails, roll back the whole transaction; do not silently stop only legacy after an unknown V2 outcome. |
| Dose/state, reminder, safety/escalation | Remain legacy runtime | No runtime shadow in APP-3 | Not enabled in APP-3 | Not applicable until APP-4/APP-5 adapters and their own gates. |

Proposed server-only configuration names (design only):

- `PRESCRIPTION_V2_MODE=legacy|shadow|v2_primary|v2_with_legacy_fallback`
- `PRESCRIPTION_V2_MISMATCH_LOGGING=true|false` (must be true in `shadow` and `v2_primary`)
- `PRESCRIPTION_V2_FALLBACK_ENABLED=true|false` (permits only known validation disposition, never exception fallback)

Invalid/missing mode must fail configuration validation rather than silently choosing V2. Initial default for any newly introduced flag is `legacy`; enabling a mode is explicit and local-only. These flags are independent of the existing `DRUG_KNOWLEDGE_BACKEND` catalog flag.

## PRESCRIPTION OWNERSHIP

| Command | Legacy compatibility owner | V2 owner / source of truth | Required transaction result |
| --- | --- | --- | --- |
| Create | Creates `Prescription` in `draft`; preserves original JSON item fields and legacy response | `sync_prescription_schedule` creates/upserts deterministic item → plan → rule → normalized times/cycle | One commit only. Valid V2 rows are `DRAFT`; uncertain rows are `REVIEW_REQUIRED`. |
| Edit | Updates legacy items/note and preserves current API response | Recomputes the same deterministic V2 IDs from prescription ID + item index; replaces normalized time/cycle intent | One commit only. APP-3 permits edit only while no V2 occurrences exist; otherwise fail closed until APP-4 supersession design exists. |
| Approve | Retains current HITL lifecycle and legacy grouped `DoseEvent` generation | `activate_prescription_schedule` activates only every complete/resolved V2 chain; V2 does not generate occurrences in APP-3 | One commit only. A complete prescription can enter `V2_PRIMARY`; a review-required item never becomes V2-active. |
| Reject | Legacy status remains contract owner | V2 draft/review rows remain traceable but inactive | No V2 occurrence or notification. |
| Stop | Legacy status becomes `stopped` and future legacy `DoseEvent` are cancelled | V2 item/plan/rule scheduling intent is marked `STOPPED`; never delete traceability rows | One commit only; APP-3 requires zero V2 occurrences for the prescription. |

### Approval disposition

The adapter returns one internal disposition, never a guessed mapping:

- `COMPLETE`: active `drug_id_map` and active `drug_product`; positive duration; controlled meal code; valid timezone; distinct strict `HH:MM` times; count matches `doses_per_day`; valid optional cycle. Eligible for V2 activation.
- `REVIEW_REQUIRED`: any uncertain identity/schedule/meal/date/time/cycle. Preserve raw legacy data (`drug_id`, display text, dose/frequency/instructions), retain V2 review rows, and create **no V2 schedule/occurrence**.
- `FATAL`: persistence failure, invalid configuration, locking/conflict, or an invariant failure. Roll back legacy and V2 together; return the existing error boundary. No automatic fallback retry.

For a multi-item prescription, `V2_PRIMARY` requires every intended executable item to be `COMPLETE`. If any item is `REVIEW_REQUIRED`, the whole request is classified `V2_WITH_LEGACY_FALLBACK`; no partial V2-primary dose path is declared. This avoids a patient-facing mixture before APP-4 has a V2 dose read adapter.

## STOP/CANCEL DESIGN

APP-3 is deliberately before V2 occurrence generation. Its stop invariant is therefore:

```text
stopped prescription -> V2 item/plan/rule STOPPED -> V2 occurrence count = 0
```

`STOPPED` is a scheduling-intent status for `prescription_item`, `medication_plan`, and `schedule_rule`; it means generator eligibility is removed. It is not a deletion and it must not alter prior history. The service locks the legacy prescription and its V2 chain before changing either side, executes legacy future-`DoseEvent` cancellation, marks V2 schedule intent stopped, and commits once.

The audited V2 occurrence state machine does **not** currently permit occurrence `CANCELLED` (its `CANCELLED` constant is for notification jobs). Therefore APP-3 must not invent an occurrence transition. Before APP-4, a stop finding any V2 occurrence is a fail-closed conflict and requires the future APP-4 cancellation/supersession decision:

- `SCHEDULED`/`DUE` future occurrences need an explicit system cancellation terminal state, immutable cancellation event, and queued-job cancellation;
- `TAKEN`, `DELAYED`, `MISSED`, and `SKIPPED` remain immutable;
- no cancellation creates safety assessment or clinical advice.

This is a precondition for V2 dose-runtime activation, not a reason to block APP-3's no-occurrence write-path integration.

## API COMPATIBILITY

APP-3 retains the current endpoints, methods, proxy paths, response bodies, legacy status vocabulary and JSON field names. No V2 table ID/status appears in public output.

| Legacy contract | Adapter rule |
| --- | --- |
| `drug_id`, `ten_thuoc`, `dang_thuoc`, `ham_luong`, `duong_dung` | `drug_id` resolves only through active map/product; raw legacy values remain display/trace data. Free text never becomes a product ID. |
| `lieu_dung`, `thoi_diem_dung`, `note` | Store raw `dose_text`, meal text/frequency/instructions. Map meal code only from controlled vocabulary; unknown/missing value is review-required. |
| `gio_nhac[]`, optional `doses_per_day` | Parse only strict unique `HH:MM`; sort and write both compatible `times_of_day` JSON and normalized `schedule_rule_time`. If count mismatches doses/day, review-required. |
| `start_date`, `duration_days` | Canonical `end_date = start_date + duration_days - 1` and is inclusive. `duration_days` must be a positive integer. A future public `end_date` must either be absent or exactly agree; it cannot silently override duration. |
| optional cycle fields | All absent/`has_cycle=false` means no cycle. `has_cycle=true` requires `on_days > 0`, `off_days >= 0`, anchor = canonical item start date. |

The documented optional `doses_per_day`/cycle request fields remain additive and Draft pending Architect/PM review. APP-3 may consume the already accepted legacy-compatible fields but must not add a response field or endpoint without contract approval. The doctor UI's immediate create-then-approve behavior is unchanged in this task.

## TRANSACTION, RETRY, AND MISMATCH DESIGN

The APP-3 application service owns a single SQLAlchemy transaction; lower domain services flush but do not commit. Mutations lock the prescription before update/approve/stop. Order is:

```text
validate mode and command
  -> lock existing aggregate where applicable
  -> write/normalize legacy compatibility projection
  -> flush stable prescription ID
  -> V2 deterministic sync or activation/stop
  -> legacy generator only where current contract requires it
  -> reconcile invariants
  -> commit once
```

Any exception before commit rolls back both representations. After a confirmed commit, a rollback flag affects only new requests: existing V2 rows are retained for traceability and ignored by legacy read/runtime; they are never mass-deleted. Operators reconcile by deterministic prescription/item IDs and then choose an explicit repair, not an automatic destructive rollback.

V2 write retries for the same legacy prescription use existing deterministic IDs and unique keys. Existing create API has no persisted request id/idempotency key, so it cannot safely promise exactly-once creation after an unknown network outcome. `V2_PRIMARY` create promotion requires an approved additive request-id persistence design; until then create may run only `LEGACY` or atomic `SHADOW`, and clients must not retry unknown create outcomes blindly.

Mismatch logging is structured, redacted and local-only: correlation ID, mode, operation, deterministic prescription/item reference, disposition, legacy/V2 status codes, normalized time count, and one of `IDENTITY_UNRESOLVED`, `SCHEDULE_INVALID`, `SEMANTIC_DIVERGENCE`, `STATUS_DIVERGENCE`, `PERSISTENCE_FAILURE`, or `INVARIANT_FAILURE`. Do not log patient names, raw dose/instructions, free-text drug name, or source artifact contents. Known data review is not an exception; it is a measurable `REVIEW_REQUIRED` outcome.

## Rollback

| Situation | Safe action |
| --- | --- |
| Pre-commit V2/legacy error | Roll back the single transaction; return existing safe error contract. |
| Known unresolved/invalid V2 data | In fallback mode commit legacy compatibility behavior and V2 review-only trace; record disposition; never activate V2 schedule. |
| Unknown persistence/lock/config error | Do not automatic-fallback after uncertain write; return failure and require outcome check/retry discipline. |
| Flag rollback after successful V2 writes | Set new traffic to `legacy`; preserve V2 rows/audit, do not delete/rewrite history; reconcile by deterministic IDs. |
| V2/legacy mismatch | Keep legacy response authoritative in APP-3, record redacted mismatch, classify before remediation. No user-visible side effect is duplicated. |

## APP-3 acceptance criteria

APP-3 may begin only with the following scope and gates:

1. Disposable PostgreSQL from repo migrations reaches `0027`; manifest-verified identity import and 49-policy seed rerun idempotently.
2. Server-only mode flag defaults to `legacy`; each of `legacy`, `shadow`, `v2_primary`, and known-data fallback has explicit tests. No invalid mode silently selects V2.
3. Valid create/edit/approve writes one deterministic V2 item/plan/rule/time/cycle chain per legacy item; rerun/edit creates no duplicates and leaves existing legacy response unchanged.
4. `end_date` inclusive, duration conversion, meal/text preservation, strict times, time count, cycle and timezone are asserted at the adapter boundary.
5. Unresolved/ambiguous/inactive drug mapping and every uncertain schedule produces V2 `REVIEW_REQUIRED`, preserves raw trace fields, activates no V2 rule, and creates no V2 occurrence.
6. Transaction-failure tests prove no partial legacy/V2 mutation. Update/approve/stop use row locking and idempotent command behavior.
7. Stop test proves future legacy events are cancelled, V2 intent becomes `STOPPED`, V2 occurrence count is zero, and no V2 history is deleted. If occurrence count is nonzero, return conflict rather than invent cancellation.
8. Compatibility tests cover current frontend payload/proxy and response schemas, including create-then-approve; no frontend/API contract expansion is made.
9. Redacted mismatch logging and reconciliation queries cover expected V2 differences without PII. Canonical artifacts remain unchanged.
10. `V2_PRIMARY` create is held behind the approved exactly-once request-id design. APP-3 can pass its shadow/sidecar integration gate without enabling that promotion.

## P0/P1

- **P0:** None for the design-only APP-2 gate. APP-1.1 verified clean local `0027`, import/seed, backend startup and focused V2 tests.
- **P1:** Exactly-once create needs an approved persisted request-id/idempotency-key design before V2-primary promotion.
- **P1:** V2 occurrence cancellation/supersession must be designed in APP-4 before a stopped prescription can have generated V2 occurrences.
- **P1:** Optional prescription fields are still Draft in `api-contracts.md`; keep compatibility shape unchanged pending review.
- **P1:** Full root test collection still lacks optional VLM `numpy`/`cv2`; it does not authorize skipping APP-3 focused/API/clean-DB gates.

---

# APP-2: PASS

**RUNTIME MODES:** Defined per flow: `LEGACY`, atomic `SHADOW`, eligible `V2_PRIMARY`, and known-data-only `V2_WITH_LEGACY_FALLBACK`.

**PRESCRIPTION OWNERSHIP:** Legacy `Prescription` owns public lifecycle/compatibility; V2 owns canonical per-item scheduling intent. One transaction owns both writes.

**STOP/CANCEL DESIGN:** Stop marks V2 intent `STOPPED` only while occurrence count is zero; occurrence cancellation is explicitly deferred to APP-4, fail-closed meanwhile.

**API COMPATIBILITY:** Existing frontend/API DTOs and responses remain unchanged; inclusive dates and normalized V2 fields are adapter-internal.

**ROLLBACK:** Pre-commit atomic rollback; post-commit flag rollback preserves trace rows; no automatic fallback after uncertain persistence outcome.

**P0/P1:** No P0. P1 promotion gates: exactly-once create and post-occurrence cancellation; contract review and optional VLM test extras remain tracked.

**READY FOR APP-3: YES** — begin with `LEGACY`/`SHADOW` sidecar integration and all listed acceptance criteria. `V2_PRIMARY` create remains disabled until its idempotency gate is approved and implemented.
