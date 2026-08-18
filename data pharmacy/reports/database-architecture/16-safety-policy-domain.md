# 16 Safety Policy Domain (DB-4H)

Scope: DB-4H implements the isolated V2 policy resolver and persistence domain
for terminal `MISSED`/`DELAYED` occurrences. It does not modify legacy safety
or escalation runtime, send a real notification, integrate an Agent, create a
clinical catch-up-dose instruction, or deploy Railway.

## Implemented design

`backend/services/safety_policy_domain/service.py` resolves one occurrence in
this strict order:

```text
DRUG_PRODUCT -> INGREDIENT -> CATEGORY -> SYSTEM_DEFAULT
```

Only policies active at the evaluation timestamp participate. Within one scope,
`REVIEWED` wins, then the highest policy version. Multiple independently
matching ingredient policies are treated as ambiguous rather than picking one.
Unreviewed/review-required policies retain their risk level but always return
`REQUIRE_MEDICAL_REVIEW`; their stored action is not emitted as a clinical
instruction.

No identity, inactive/missing product, multiple ingredient policies, or missing
policy produces a fail-closed assessment: `risk_level=UNKNOWN` and
`recommended_action=REQUIRE_MEDICAL_REVIEW`. No dose state is changed by the
assessment service.

## Legacy fallback

`muc_nghiem_trong` is not copied into `drug_product` by DB-4B, intentionally.
The new manifest-verified local seed utility reads the preserved Final Canonical
V2 product artifact and creates only this shape:

```text
scope_type=CATEGORY
risk_type=MISSED_DOSE
source_type=LEGACY_CATEGORY_RULE
review_status=LEGACY_UNREVIEWED
action_policy=REQUIRE_MEDICAL_REVIEW
```

It verifies the artifact hash before reading, maps only the legacy labels to
`LOW`/`MODERATE`/`HIGH`, rejects any category with conflicting source risks,
and does not write source artifacts. The verified current artifact contains 49
unambiguous legacy categories. Legacy category policy is never used for
`DELAYED_DOSE` and never wins over product or ingredient policy.

## Assessment, event, and provenance

`assess_dose_safety` locks the occurrence and accepts only `MISSED` or
`DELAYED`. It writes atomically:

1. `missed_dose_assessment`, with risk/action/policy ID/reason and immutable
   source/review-status snapshots;
2. `dose_event_log(event_type=SAFETY_ASSESSMENT_CREATED)`; and
3. one idempotent `safety_event` for audit.

The existing assessment schema did not retain policy source and review status.
Additive migration `0027` adds nullable
`policy_source_type` and `policy_review_status` so an old assessment remains
auditable even if its linked policy is later superseded. No FK, NOT NULL, or
legacy-table hardening is added.

All three records use deterministic IDs/idempotency keys keyed by occurrence,
risk type, and evaluator version. A re-run returns the existing assessment and
creates no duplicate assessment, safety event, or dose log. Row locking plus
the unique keys is the intended PostgreSQL concurrency boundary.

## Validation completed

- `ruff check` passed for new service, seeder, migration, and tests.
- `py_compile` passed for the service, errors, seeder, and migration.
- Focused tests passed: 7 policy-domain tests, 2 seed-input tests, and the 14
  DB-4G scheduling regression tests.
- Tests cover product-over-category, ingredient-over-category, legacy fallback,
  no-policy fallback, ambiguous product identity, delayed policy, duplicate
  rerun, immutable assessment/event/dose-log transaction rollback, and source
  hash/conflict validation.
- `seed_legacy_category_safety_policies.py --dry-run` passed against Final
  Canonical V2 and reported `category_count=49`.
- Alembic static SQL for `0026 -> 0027` passed; it is exactly two additive
  nullable columns on `missed_dose_assessment`.
- Fresh PostgreSQL 16 + pgvector Docker container was run on port `5434` with
  no mounted volume. `alembic upgrade head` reached `0027 (head)`.
- Final Canonical V2 identity import created `3,556` products, `3,556` maps,
  `1,406` ingredients, and `5,287` valid product/ingredient links. The second
  import created zero rows and artifact hashes were unchanged.
- Legacy seed created 49 category policies on the first run and zero on the
  second.
- On PostgreSQL, product policy overrode category fallback; ingredient policy
  overrode category; an unreviewed legacy category policy remained unreviewed;
  missing identity produced the fail-closed system default; and a delayed-dose
  product policy resolved independently.
- Each assessment created exactly one `missed_dose_assessment`, one
  `dose_event_log`, and one `safety_event`. A forced transaction rollback left
  all three counts at zero. A rerun returned the existing assessment.
- In a two-session test, the second assessment blocked on the occurrence row;
  after the first transaction committed, it returned the existing assessment.
  The final occurrence had exactly one assessment, one safety event, and one
  dose log.

The root pytest collection also remains independently blocked before focused
tests by the pre-existing FastAPI assertion for a `204` route declaring a
response body in `backend/api/caregiver_routes.py`; it was not changed.

## DB-4H: PASS

## POLICY RESOLUTION: PASS

Product, ingredient, category, valid-window/review precedence, and conservative
system default are implemented and tested.

## LEGACY FALLBACK: PASS

The only seed/use path enforces `CATEGORY` / `MISSED_DOSE` /
`LEGACY_CATEGORY_RULE` / `LEGACY_UNREVIEWED`; Final Canonical V2 hash-verified
dry-run reports 49 source categories.

## ASSESSMENT: PASS

Assessments persist risk, action, policy, policy source/review snapshots, and
reason code transactionally with the occurrence's immutable dose log.

## SAFETY EVENT: PASS

Each assessment creates one idempotent audit event. Ambiguous drug identity
uses the explicit `AMBIGUOUS_DRUG` event type; no escalation is sent.

## FAIL-CLOSED: PASS

Unknown/ambiguous identity or policy produces `UNKNOWN` plus
`REQUIRE_MEDICAL_REVIEW`, never a low-risk assumption or dose advice.

## IDEMPOTENCY: PASS

Deterministic-key unit coverage and real PostgreSQL reruns created zero
duplicate imports, policies, assessments, safety events, or dose logs.

## P0/P1:

- P0: None.
- P1: The root pytest FastAPI `204` response-body assertion remains an
  unrelated collection blocker.

## READY FOR SAFETY ESCALATION / AGENT INTEGRATION: YES

The audited policy boundary is validated. Any later escalation/Agent task must
still obtain approved policy author/reviewer governance and approved escalation
actions; it must not interpret legacy category fallback as clinical advice.
