"""DB-4F bounded, idempotent generation of V2 dose occurrences.

This is a persistence service, not a cron/reminder implementation. Callers
must supply a finite local-date window; no unbounded plan is ever expanded.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import (
    DoseOccurrence,
    DrugProduct,
    MedicationPlan,
    PrescriptionItem,
    ScheduleRule,
    ScheduleRuleCycle,
    ScheduleRuleTime,
)

ACTIVE = "ACTIVE"
DAILY_AT_TIMES = "DAILY_AT_TIMES"
SCHEDULED = "SCHEDULED"


@dataclass
class GenerationResult:
    """Counts from one bounded generator invocation."""

    inserted: int = 0
    existing: int = 0
    invalid_rules: int = 0
    skipped_local_dates: int = 0


def _occurrence_id(generation_key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"vmec04:dose-occurrence:{generation_key}"))


def _wall_time_to_utc(local_date: date, local_time: time, timezone: ZoneInfo) -> datetime | None:
    """Convert a wall time only when it maps to exactly one UTC instant.

    A DST gap has no round-trip candidate and a DST overlap has two. Both are
    intentionally skipped rather than guessing which clinical dose was meant.
    """

    naive = datetime.combine(local_date, local_time)
    instants: set[datetime] = set()
    for fold in (0, 1):
        localized = naive.replace(tzinfo=timezone, fold=fold)
        round_trip = localized.astimezone(UTC).astimezone(timezone)
        if round_trip.replace(tzinfo=None) == naive:
            instants.add(localized.astimezone(UTC))
    return next(iter(instants)) if len(instants) == 1 else None


def _cycle_applies(cycle: ScheduleRuleCycle | None, local_date: date) -> bool:
    if cycle is None:
        return True
    if local_date < cycle.anchor_date:
        return False
    cycle_length = cycle.on_days + cycle.off_days
    return cycle_length > 0 and (local_date - cycle.anchor_date).days % cycle_length < cycle.on_days


def _eligible_rule(
    db: Session, plan: MedicationPlan, rule: ScheduleRule
) -> tuple[PrescriptionItem, DrugProduct, ZoneInfo, list[time], ScheduleRuleCycle | None] | None:
    if (
        plan.prescription_item_id is None
        or plan.drug_product_id is None
        or rule.rule_type != DAILY_AT_TIMES
        or rule.interval_value != 1
        or rule.interval_unit != "DAY"
        or rule.timezone != plan.timezone
    ):
        return None
    item = db.get(PrescriptionItem, plan.prescription_item_id)
    product = db.get(DrugProduct, plan.drug_product_id)
    if (
        item is None
        or product is None
        or item.status != ACTIVE
        or item.drug_product_id != plan.drug_product_id
        or product.status != ACTIVE
        or item.start_date is None
        or item.doses_per_day is None
        or item.doses_per_day <= 0
        or item.end_date is not None and item.end_date < item.start_date
    ):
        return None
    try:
        timezone = ZoneInfo(plan.timezone or "")
    except ZoneInfoNotFoundError:
        return None
    times = list(
        db.execute(
            select(ScheduleRuleTime.local_time)
            .where(ScheduleRuleTime.schedule_rule_id == rule.id)
            .order_by(ScheduleRuleTime.local_time)
        ).scalars()
    )
    if rule.frequency != item.doses_per_day or len(times) != item.doses_per_day or not times:
        return None
    cycle = db.get(ScheduleRuleCycle, rule.id)
    if cycle is not None and (cycle.on_days <= 0 or cycle.off_days < 0 or cycle.anchor_date < item.start_date):
        return None
    return item, product, timezone, times, cycle


def _schedule_revision(
    *, item: PrescriptionItem, plan: MedicationPlan, rule: ScheduleRule, cycle: ScheduleRuleCycle | None, times: list[time]
) -> str:
    """Fingerprint executable schedule semantics, not mutable database timestamps.

    Editing a schedule must create a new future occurrence identity after the
    prior future occurrence has been cancelled.  A stable content fingerprint
    permits retries to reuse that new identity without reusing the old one.
    """

    values = (
        item.drug_product_id,
        item.legacy_drug_id,
        item.start_date.isoformat() if item.start_date else None,
        item.end_date.isoformat() if item.end_date else None,
        item.doses_per_day,
        plan.timezone,
        rule.rule_type,
        rule.frequency,
        rule.interval_value,
        rule.interval_unit,
        tuple(local_time.isoformat() for local_time in times),
        (cycle.anchor_date.isoformat(), cycle.on_days, cycle.off_days) if cycle else None,
    )
    return sha256(repr(values).encode("utf-8")).hexdigest()[:16]


def _generation_key(
    rule_id: str, schedule_revision: str, local_date: date, local_time: time, timezone: str
) -> str:
    return (
        f"rule:{rule_id}:revision:{schedule_revision}:local-date:{local_date.isoformat()}:"
        f"local-time:{local_time.isoformat()}:timezone:{timezone}"
    )


def _insert_occurrence(
    db: Session,
    *,
    plan: MedicationPlan,
    item: PrescriptionItem,
    rule: ScheduleRule,
    product: DrugProduct,
    local_date: date,
    local_time: time,
    timezone_name: str,
    scheduled_at: datetime,
    schedule_revision: str,
) -> bool:
    """Stage one row, returning False when a previous retry already wrote it."""

    generation_key = _generation_key(rule.id, schedule_revision, local_date, local_time, timezone_name)
    if db.execute(
        select(DoseOccurrence.id).where(DoseOccurrence.generation_key == generation_key)
    ).scalar_one_or_none() is not None:
        return False
    db.add(
        DoseOccurrence(
            id=_occurrence_id(generation_key),
            medication_plan_id=plan.id,
            prescription_item_id=item.id,
            patient_id=plan.patient_id,
            drug_product_id=product.id,
            legacy_drug_id=plan.legacy_drug_id,
            schedule_rule_id=rule.id,
            scheduled_at=scheduled_at,
            scheduled_local_date=local_date,
            scheduled_local_time=local_time,
            timezone=timezone_name,
            status=SCHEDULED,
            generation_key=generation_key,
            metadata_json={},
        )
    )
    return True


def generate_dose_occurrences(
    db: Session, *, window_start: date, window_end: date, medication_plan_ids: set[str] | None = None
) -> GenerationResult:
    """Generate active V2 occurrences in one explicit finite local-date window.

    The function never commits. Its caller owns atomicity with any surrounding
    task/transaction. It also deliberately has no default window, preventing
    accidental infinite expansion for open-ended plans.
    """

    if window_end < window_start:
        raise ValueError("window_end must be on or after window_start")
    result = GenerationResult()
    plan_query = select(MedicationPlan).where(MedicationPlan.status == ACTIVE)
    if medication_plan_ids is not None:
        if not medication_plan_ids:
            return GenerationResult()
        plan_query = plan_query.where(MedicationPlan.id.in_(medication_plan_ids))
    plans = db.execute(plan_query.with_for_update()).scalars()
    for plan in plans:
        rules = db.execute(
            select(ScheduleRule).where(
                ScheduleRule.medication_plan_id == plan.id,
                ScheduleRule.status == ACTIVE,
            )
        ).scalars()
        for rule in rules:
            eligible = _eligible_rule(db, plan, rule)
            if eligible is None:
                result.invalid_rules += 1
                continue
            item, product, timezone, times, cycle = eligible
            schedule_revision = _schedule_revision(item=item, plan=plan, rule=rule, cycle=cycle, times=times)
            range_start = max(window_start, item.start_date)
            range_end = min(window_end, item.end_date) if item.end_date is not None else window_end
            if range_end < range_start:
                continue
            local_date = range_start
            while local_date <= range_end:
                if _cycle_applies(cycle, local_date):
                    scheduled: list[tuple[time, datetime]] = []
                    for local_time in times:
                        utc_instant = _wall_time_to_utc(local_date, local_time, timezone)
                        if utc_instant is None:
                            scheduled = []
                            result.skipped_local_dates += 1
                            break
                        scheduled.append((local_time, utc_instant))
                    for local_time, utc_instant in scheduled:
                        if _insert_occurrence(
                            db,
                            plan=plan,
                            item=item,
                            rule=rule,
                            product=product,
                            local_date=local_date,
                            local_time=local_time,
                            timezone_name=timezone.key,
                            scheduled_at=utc_instant,
                            schedule_revision=schedule_revision,
                        ):
                            result.inserted += 1
                        else:
                            result.existing += 1
                local_date += timedelta(days=1)
    db.flush()
    return result


def generate_prescription_dose_occurrences(
    db: Session, *, prescription_id: str, now: datetime | None = None
) -> GenerationResult:
    """Generate one finite, prescription-scoped V2 schedule window.

    APP-3 writes an inclusive end date for every complete doctor schedule.
    An active row without that bound is intentionally not generated here; a
    future worker must provide its own explicit bounded window.
    """

    now = (now or datetime.now(UTC)).astimezone(UTC)
    pairs = list(
        db.execute(
            select(MedicationPlan, PrescriptionItem).join(
                PrescriptionItem, PrescriptionItem.id == MedicationPlan.prescription_item_id
            ).where(
                PrescriptionItem.prescription_id == prescription_id,
                PrescriptionItem.status == ACTIVE,
                MedicationPlan.status == ACTIVE,
            )
        ).all()
    )
    result = GenerationResult()
    for plan, item in pairs:
        if item.start_date is None or item.end_date is None:
            result.invalid_rules += 1
            continue
        try:
            current_local_date = now.astimezone(ZoneInfo(plan.timezone or "")).date()
        except ZoneInfoNotFoundError:
            result.invalid_rules += 1
            continue
        if item.end_date < current_local_date:
            continue
        generated = generate_dose_occurrences(
            db,
            window_start=max(item.start_date, current_local_date),
            window_end=item.end_date,
            medication_plan_ids={plan.id},
        )
        result.inserted += generated.inserted
        result.existing += generated.existing
        result.invalid_rules += generated.invalid_rules
        result.skipped_local_dates += generated.skipped_local_dates
    return result


__all__ = ["GenerationResult", "generate_dose_occurrences", "generate_prescription_dose_occurrences"]
