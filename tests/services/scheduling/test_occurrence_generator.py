"""DB-4F tests for bounded V2 dose-occurrence generation."""

from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest
from sqlalchemy import create_engine, select
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
from backend.services.scheduling.occurrence_generator import generate_dose_occurrences

TABLES = (
    DrugProduct.__table__,
    PrescriptionItem.__table__,
    MedicationPlan.__table__,
    ScheduleRule.__table__,
    ScheduleRuleTime.__table__,
    ScheduleRuleCycle.__table__,
    DoseOccurrence.__table__,
)


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for table in TABLES:
        table.create(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _active_chain(
    db: Session,
    *,
    name: str,
    timezone: str = "Asia/Ho_Chi_Minh",
    start: date = date(2026, 8, 17),
    end: date | None = date(2026, 8, 23),
    times: tuple[time, ...] = (time(8),),
    cycle: tuple[int, int] | None = None,
    product_status: str = "ACTIVE",
) -> tuple[MedicationPlan, ScheduleRule]:
    product_id = f"product-{name}"
    item_id = f"item-{name}"
    plan_id = f"plan-{name}"
    rule_id = f"rule-{name}"
    db.add(DrugProduct(id=product_id, display_name=name, status=product_status))
    db.add(
        PrescriptionItem(
            id=item_id,
            prescription_id=f"prescription-{name}",
            patient_id="patient-1",
            drug_product_id=product_id,
            start_date=start,
            end_date=end,
            doses_per_day=len(times),
            meal_instruction_code="AFTER_MEAL",
            status="ACTIVE",
        )
    )
    plan = MedicationPlan(
        id=plan_id,
        patient_id="patient-1",
        prescription_item_id=item_id,
        drug_product_id=product_id,
        legacy_drug_id=f"legacy-{name}",
        timezone=timezone,
        status="ACTIVE",
    )
    rule = ScheduleRule(
        id=rule_id,
        medication_plan_id=plan_id,
        rule_type="DAILY_AT_TIMES",
        frequency=len(times),
        interval_value=1,
        interval_unit="DAY",
        timezone=timezone,
        status="ACTIVE",
    )
    db.add_all((plan, rule))
    for index, local_time in enumerate(times):
        db.add(ScheduleRuleTime(id=f"time-{name}-{index}", schedule_rule_id=rule_id, local_time=local_time))
    if cycle is not None:
        db.add(
            ScheduleRuleCycle(
                schedule_rule_id=rule_id,
                anchor_date=start,
                on_days=cycle[0],
                off_days=cycle[1],
            )
        )
    db.commit()
    return plan, rule


def test_generator_writes_local_context_utc_and_retries_without_duplicates(db: Session) -> None:
    _active_chain(db, name="daily", times=(time(8), time(20)))

    first = generate_dose_occurrences(db, window_start=date(2026, 8, 16), window_end=date(2026, 8, 25))
    db.commit()
    second = generate_dose_occurrences(db, window_start=date(2026, 8, 16), window_end=date(2026, 8, 25))
    db.commit()
    rows = db.execute(select(DoseOccurrence).order_by(DoseOccurrence.scheduled_at)).scalars().all()

    assert (first.inserted, first.existing, first.invalid_rules) == (14, 0, 0)
    assert (second.inserted, second.existing) == (0, 14)
    assert len(rows) == 14
    assert rows[0].scheduled_local_date == date(2026, 8, 17)
    assert rows[0].scheduled_local_time == time(8)
    assert rows[0].timezone == "Asia/Ho_Chi_Minh"
    assert rows[0].scheduled_at.replace(tzinfo=UTC) == datetime(2026, 8, 17, 1, 0, tzinfo=UTC)
    assert rows[-1].scheduled_local_date == date(2026, 8, 23)


def test_generator_honors_cycle_and_inclusive_boundaries(db: Session) -> None:
    _active_chain(db, name="cycle", times=(time(8),), cycle=(2, 1))

    result = generate_dose_occurrences(db, window_start=date(2026, 8, 16), window_end=date(2026, 8, 25))
    dates = db.execute(
        select(DoseOccurrence.scheduled_local_date).order_by(DoseOccurrence.scheduled_local_date)
    ).scalars().all()

    assert result.inserted == 5
    assert dates == [date(2026, 8, 17), date(2026, 8, 18), date(2026, 8, 20), date(2026, 8, 21), date(2026, 8, 23)]


def test_generator_skips_dst_gap_and_overlap_without_guessing(db: Session) -> None:
    _active_chain(
        db,
        name="normal-dst",
        timezone="America/New_York",
        start=date(2026, 3, 7),
        end=date(2026, 3, 7),
        times=(time(8),),
    )
    _active_chain(
        db,
        name="gap-dst",
        timezone="America/New_York",
        start=date(2026, 3, 8),
        end=date(2026, 3, 8),
        times=(time(2, 30),),
    )
    _active_chain(
        db,
        name="overlap-dst",
        timezone="America/New_York",
        start=date(2026, 11, 1),
        end=date(2026, 11, 1),
        times=(time(1, 30),),
    )

    march = generate_dose_occurrences(db, window_start=date(2026, 3, 7), window_end=date(2026, 3, 8))
    november = generate_dose_occurrences(db, window_start=date(2026, 11, 1), window_end=date(2026, 11, 1))
    rows = db.execute(select(DoseOccurrence).order_by(DoseOccurrence.scheduled_at)).scalars().all()

    assert (march.inserted, march.skipped_local_dates) == (1, 1)
    assert (november.inserted, november.skipped_local_dates) == (0, 1)
    assert len(rows) == 1
    assert rows[0].scheduled_at.replace(tzinfo=UTC) == datetime(2026, 3, 7, 13, 0, tzinfo=UTC)


def test_generator_fails_closed_for_unresolved_active_chain(db: Session) -> None:
    _active_chain(db, name="retired-product", product_status="RETIRED")

    result = generate_dose_occurrences(db, window_start=date(2026, 8, 17), window_end=date(2026, 8, 17))

    assert (result.inserted, result.invalid_rules) == (0, 1)
    assert db.execute(select(DoseOccurrence)).scalars().all() == []


def test_generator_participates_in_caller_rollback(db: Session) -> None:
    _active_chain(db, name="rollback")

    with pytest.raises(RuntimeError), db.begin():
        generate_dose_occurrences(db, window_start=date(2026, 8, 17), window_end=date(2026, 8, 17))
        raise RuntimeError("force rollback")

    assert db.execute(select(DoseOccurrence)).scalars().all() == []


def test_generator_rejects_unbounded_or_reversed_windows(db: Session) -> None:
    _active_chain(db, name="window")

    with pytest.raises(ValueError, match="window_end"):
        generate_dose_occurrences(db, window_start=date(2026, 8, 18), window_end=date(2026, 8, 17))
