# 13 Scheduling Domain Write Path (DB-4E)

Scope: implement the approved V2 scheduling write path from the doctor
prescription form. No DB migration was needed: it uses DB-4D revision `0026`.
This task does not generate `dose_occurrence`, add reminder/safety logic,
change Railway, or cut over the legacy prescription/dose-event runtime.

## Write path

`backend/services/scheduling/write_path.py` persists one legacy prescription
item as a deterministic V2 chain:

```text
prescription_item -> medication_plan -> schedule_rule -> schedule_rule_time*
                                                     -> schedule_rule_cycle?
```

The existing prescription service calls this code in the same transaction as
create/update. It uses UUIDv5 IDs derived from prescription ID and item index;
a retry updates the same `prescription_item`, plan, rule, normalized time rows,
and optional cycle instead of creating duplicates. The service does not commit
on its own, so its caller can roll back the legacy and V2 writes together.

## Form and compatibility mapping

The frontend now carries the form's existing `perDay` and cycle controls as
optional additive API fields: `doses_per_day`, `has_cycle`, `cycle_on_days`,
and `cycle_off_days`. Existing clients remain supported: absent
`doses_per_day` derives from `gio_nhac`; absent cycle fields mean no cycle.
The API contract documents this additive proposal and records it as awaiting
Architect/PM review; no response shape was changed.

| Form/legacy field | V2 target / behavior |
|---|---|
| `drug_id` | Resolve only an `ACTIVE` `drug_id_map` whose `drug_product` is also `ACTIVE`; otherwise retain legacy ID and require review. |
| `lieu_dung` | Raw `prescription_item.dose_text`; no clinical dose parsing is inferred. |
| `perDay` / `gio_nhac` | `doses_per_day`, `schedule_rule.frequency`, JSON compatibility `times_of_day`, and normalized distinct `schedule_rule_time` rows. |
| meal text | Controlled code plus original `meal_instruction_text`; unknown/missing code is not activated. |
| `startDate` + `durationDays` | Item local dates; `end_date = start_date + duration - 1`, inclusive. |
| optional on/off cycle | One `schedule_rule_cycle` anchored at item start date. |

## Validation and activation gate

Creation initially writes `DRAFT` only when all of the following are true:
canonical identity resolves, date/duration parses, timezone is valid, local
times are strict and unique, `doses_per_day` exactly matches the time count,
meal code is controlled, and any requested cycle has `on_days > 0` and
`off_days >= 0`. Otherwise item, plan, and rule are all `REVIEW_REQUIRED`.

The existing doctor approval transaction calls the V2 activation gate. It sets
only complete/resolved V2 chain rows to `ACTIVE`; uncertain rows remain
`REVIEW_REQUIRED`. No V2 occurrence is generated. The existing legacy
`dose_event` behavior remains untouched for API/runtime compatibility.

## Validation evidence

- Focused Python suite: `15 passed` — valid write, canonical mapping,
  inclusive end date, normalized times/cycle, review-required behavior,
  caller transaction rollback, retry idempotency, legacy request compatibility,
  and DB-4C/DB-4D regressions.
- `ruff check` and Python compilation passed for the changed backend/test
  files.
- Frontend TypeScript `tsc --noEmit` passed.
- Fresh disposable PostgreSQL 16 + pgvector Docker database: `alembic upgrade
  head` reached `0026`; a canonical synthetic input was written twice and
  activated. It produced one each of item/plan/rule/cycle, two normalized time
  rows, `end_date = 2026-08-23` for a seven-day start of 2026-08-17, and
  `dose_occurrence = 0`.

The repository-wide frontend ESLint command remains blocked by pre-existing
CRLF/Prettier violations across the frontend (including unchanged files).
This task did not bulk-format unrelated files; TypeScript and all DB-4E
focused checks passed.

## DB-4E: PASS

## WRITE PATH: PASS

## VALIDATION: PASS

Invalid/uncertain identity, meal, timezone, date, time, count, or cycle input
is fail-closed to `REVIEW_REQUIRED`.

## TRANSACTION: PASS

V2 writes participate in the create/update/approve transaction; the rollback
test leaves zero V2 rows.

## LEGACY COMPATIBILITY: PASS

Legacy clients/payloads remain accepted, `times_of_day` JSON remains present,
and no legacy runtime behavior was removed.

## P0/P1:

- P0: None.
- P1: Architect/PM review of the documented optional prescription API fields;
  resolve the repository-wide CRLF/Prettier baseline before claiming a full
  frontend ESLint pass; design a later supersession workflow for edits after
  V2 occurrence generation exists.

## READY FOR DOSE OCCURRENCE GENERATOR: YES

The generator can be designed as a separate task against validated active V2
plans/rules. It must retain its own approval, DST, idempotency, and safety
gates; DB-4E intentionally creates no occurrences.
