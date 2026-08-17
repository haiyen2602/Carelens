"""Transactional DB-4E persistence for clinician-entered schedule intent.

This module writes V2 schedule metadata only. It must not generate a dose
occurrence or invoke the legacy reminder generator; those are later domains.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import (
    DrugIdMap,
    DrugProduct,
    MedicationPlan,
    Patient,
    Prescription,
    PrescriptionItem,
    ScheduleRule,
    ScheduleRuleCycle,
    ScheduleRuleTime,
)

DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"
WRITE_SOURCE = "DOCTOR_WRITE_PATH"
DAILY_AT_TIMES = "DAILY_AT_TIMES"
DRAFT = "DRAFT"
ACTIVE = "ACTIVE"
REVIEW_REQUIRED = "REVIEW_REQUIRED"

MEAL_CODES = {
    "Trước ăn": "BEFORE_MEAL",
    "Sau ăn": "AFTER_MEAL",
    "Cùng bữa ăn": "WITH_MEAL",
    "Không phụ thuộc bữa ăn": "ANYTIME",
    "Trước khi ngủ": "BEDTIME",
}


def _deterministic_id(kind: str, *parts: object) -> str:
    """Return a stable UUID so a retry updates, rather than duplicates, a row."""

    return str(uuid5(NAMESPACE_URL, f"vmec04:{kind}:" + ":".join(map(str, parts))))


def _text(value: object) -> str | None:
    normalized = str(value).strip() if value is not None else ""
    return normalized or None


def _date_range(prescription: Prescription, item: dict) -> tuple[date | None, date | None, bool]:
    raw_start = item.get("start_date") or prescription.start_date
    raw_duration = item.get("duration_days")
    if raw_duration in (None, ""):
        raw_duration = prescription.duration_days
    try:
        start = date.fromisoformat(str(raw_start))
        if isinstance(raw_duration, bool):
            raise ValueError
        duration = int(raw_duration)
        if duration <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return None, None, False
    return start, start + timedelta(days=duration - 1), True


def _times(value: object) -> tuple[list[time], list[str], bool]:
    if not isinstance(value, list) or not value:
        return [], [], False
    parsed: list[time] = []
    normalized: list[str] = []
    try:
        for raw in value:
            if not isinstance(raw, str) or len(raw) != 5:
                raise ValueError
            parsed_time = datetime.strptime(raw, "%H:%M").time()
            parsed.append(parsed_time)
            normalized.append(parsed_time.strftime("%H:%M"))
    except ValueError:
        return [], [str(raw) for raw in value], False
    if len(set(parsed)) != len(parsed):
        return [], normalized, False
    ordered = sorted(zip(parsed, normalized), key=lambda pair: pair[0])
    return [pair[0] for pair in ordered], [pair[1] for pair in ordered], True


def _doses_per_day(value: object, count: int) -> tuple[int | None, bool]:
    if value in (None, ""):
        return count, count > 0
    try:
        if isinstance(value, bool):
            raise ValueError
        doses = int(value)
    except (TypeError, ValueError):
        return None, False
    return doses, doses > 0 and doses == count


def _timezone(patient: Patient | None) -> tuple[str, bool]:
    candidate = _text(patient.timezone if patient is not None else None) or DEFAULT_TIMEZONE
    try:
        ZoneInfo(candidate)
    except ZoneInfoNotFoundError:
        return DEFAULT_TIMEZONE, False
    return candidate, True


def _identity(db: Session, legacy_drug_id: str | None) -> str | None:
    if legacy_drug_id is None:
        return None
    mapping = db.execute(
        select(DrugIdMap).where(
            DrugIdMap.legacy_drug_id == legacy_drug_id,
            DrugIdMap.mapping_status == "ACTIVE",
        )
    ).scalar_one_or_none()
    if mapping is None:
        return None
    product = db.get(DrugProduct, mapping.drug_product_id)
    return product.id if product is not None and product.status == "ACTIVE" else None


def _upsert(db: Session, model: type, row_id: str, **values: object):
    row = db.get(model, row_id)
    if row is None:
        row = model(id=row_id, **values)
        db.add(row)
    else:
        for key, value in values.items():
            setattr(row, key, value)
        if hasattr(row, "updated_at"):
            row.updated_at = datetime.now(UTC)
    return row


def _replace_rule_times(db: Session, rule_id: str, times: list[time]) -> None:
    existing = {
        row.local_time: row
        for row in db.execute(
            select(ScheduleRuleTime).where(ScheduleRuleTime.schedule_rule_id == rule_id)
        ).scalars()
    }
    wanted = set(times)
    for local_time, row in existing.items():
        if local_time not in wanted:
            db.delete(row)
    for local_time in wanted:
        _upsert(
            db,
            ScheduleRuleTime,
            _deterministic_id("schedule-rule-time", rule_id, local_time.isoformat()),
            schedule_rule_id=rule_id,
            local_time=local_time,
        )


def _replace_cycle(
    db: Session, rule_id: str, start_date: date | None, item: dict
) -> bool:
    has_cycle = bool(item.get("has_cycle"))
    existing = db.get(ScheduleRuleCycle, rule_id)
    if not has_cycle:
        if existing is not None:
            db.delete(existing)
        return True
    try:
        on_days = int(item.get("cycle_on_days"))
        off_days = int(item.get("cycle_off_days"))
        if isinstance(item.get("cycle_on_days"), bool) or isinstance(item.get("cycle_off_days"), bool):
            raise ValueError
        if start_date is None or on_days <= 0 or off_days < 0:
            raise ValueError
    except (TypeError, ValueError):
        if existing is not None:
            db.delete(existing)
        return False
    if existing is None:
        db.add(
            ScheduleRuleCycle(
                schedule_rule_id=rule_id,
                anchor_date=start_date,
                on_days=on_days,
                off_days=off_days,
            )
        )
    else:
        existing.anchor_date = start_date
        existing.on_days = on_days
        existing.off_days = off_days
        existing.updated_at = datetime.now(UTC)
    return True


def sync_prescription_schedule(db: Session, prescription: Prescription) -> None:
    """Write every current prescription item to V2 without committing.

    Callers own the surrounding transaction, so a failure rolls back the
    legacy prescription and every V2 row together. A re-run uses stable IDs.
    """

    patient = db.get(Patient, prescription.patient_id)
    timezone, timezone_valid = _timezone(patient)
    for index, item in enumerate(prescription.items or []):
        if not isinstance(item, dict):
            item = {}
        item_id = _deterministic_id("prescription-item", prescription.id, index)
        plan_id = _deterministic_id("medication-plan", item_id)
        rule_id = _deterministic_id("schedule-rule", plan_id)
        legacy_drug_id = _text(item.get("drug_id"))
        product_id = _identity(db, legacy_drug_id)
        start_date, end_date, dates_valid = _date_range(prescription, item)
        parsed_times, normalized_times, times_valid = _times(item.get("gio_nhac"))
        doses_per_day, doses_valid = _doses_per_day(item.get("doses_per_day"), len(parsed_times))
        meal_text = _text(item.get("thoi_diem_dung"))
        meal_code = MEAL_CODES.get(meal_text or "", "UNSPECIFIED" if meal_text is None else "OTHER")
        meal_valid = meal_code not in {"OTHER", "UNSPECIFIED"}
        cycle_valid = _replace_cycle(db, rule_id, start_date, item)
        valid = all((product_id is not None, dates_valid, times_valid, doses_valid, meal_valid, cycle_valid, timezone_valid))
        status = DRAFT if valid else REVIEW_REQUIRED
        start_at = (
            datetime.combine(start_date, time.min, tzinfo=ZoneInfo(timezone)).astimezone(UTC)
            if start_date is not None
            else None
        )
        end_at = (
            datetime.combine(end_date, time.min, tzinfo=ZoneInfo(timezone)).astimezone(UTC)
            if end_date is not None
            else None
        )

        _upsert(
            db,
            PrescriptionItem,
            item_id,
            prescription_id=prescription.id,
            patient_id=prescription.patient_id,
            drug_product_id=product_id,
            legacy_drug_id=legacy_drug_id,
            drug_display_name=_text(item.get("ten_thuoc")),
            dose_text=_text(item.get("lieu_dung")),
            dose_value=None,
            dose_unit=None,
            route=_text(item.get("duong_dung")),
            frequency_text=meal_text,
            instructions=_text(item.get("instructions")) or _text(prescription.note),
            start_date=start_date,
            end_date=end_date,
            doses_per_day=doses_per_day,
            meal_instruction_code=meal_code,
            meal_instruction_text=meal_text,
            status=status,
            migration_source=WRITE_SOURCE,
            migration_source_id=prescription.id,
            migration_item_index=index,
        )
        _upsert(
            db,
            MedicationPlan,
            plan_id,
            patient_id=prescription.patient_id,
            prescription_item_id=item_id,
            drug_product_id=product_id,
            legacy_drug_id=legacy_drug_id,
            status=status,
            timezone=timezone,
            start_at=start_at,
            end_at=end_at,
            instructions=_text(item.get("instructions")) or _text(prescription.note),
        )
        _upsert(
            db,
            ScheduleRule,
            rule_id,
            medication_plan_id=plan_id,
            rule_type=DAILY_AT_TIMES,
            frequency=doses_per_day,
            interval_value=1,
            interval_unit="DAY",
            times_of_day=normalized_times,
            days_of_week=None,
            day_of_month=None,
            start_at=start_at,
            end_at=end_at,
            timezone=timezone,
            status=status,
        )
        _replace_rule_times(db, rule_id, parsed_times if times_valid else [])
    db.flush()


def activate_prescription_schedule(db: Session, prescription_id: str) -> None:
    """Activate only complete, resolved V2 schedules after doctor approval."""

    items = db.execute(
        select(PrescriptionItem).where(
            PrescriptionItem.prescription_id == prescription_id,
            PrescriptionItem.migration_source == WRITE_SOURCE,
        )
    ).scalars()
    for item in items:
        plan_id = _deterministic_id("medication-plan", item.id)
        rule_id = _deterministic_id("schedule-rule", plan_id)
        plan = db.get(MedicationPlan, plan_id)
        rule = db.get(ScheduleRule, rule_id)
        time_count = db.execute(
            select(ScheduleRuleTime.id).where(ScheduleRuleTime.schedule_rule_id == rule_id)
        ).scalars().all()
        valid = (
            item.drug_product_id is not None
            and item.start_date is not None
            and item.end_date is not None
            and item.end_date >= item.start_date
            and item.doses_per_day is not None
            and item.doses_per_day > 0
            and len(time_count) == item.doses_per_day
            and item.meal_instruction_code not in {"OTHER", "UNSPECIFIED", None}
            and plan is not None
            and rule is not None
        )
        status = ACTIVE if valid else REVIEW_REQUIRED
        item.status = status
        if plan is not None:
            plan.status = status
        if rule is not None:
            rule.status = status
    db.flush()


__all__ = ["activate_prescription_schedule", "sync_prescription_schedule"]
