"""PostgreSQL-only concurrency coverage for APP-4 occurrence generation."""

from __future__ import annotations

import uuid
from datetime import date, time

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from backend.db.base import SessionLocal, engine
from backend.db.models import (
    DoseOccurrence,
    DrugProduct,
    MedicationPlan,
    PrescriptionItem,
    ScheduleRule,
    ScheduleRuleTime,
)
from backend.services.scheduling.occurrence_generator import generate_dose_occurrences


def _postgres_available() -> bool:
    try:
        with engine.connect() as connection:
            return connection.dialect.name == "postgresql"
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _postgres_available(), reason="Cần PostgreSQL thật cho SELECT FOR UPDATE")


def test_generator_serializes_two_workers_and_rerun_is_duplicate_free() -> None:
    suffix = uuid.uuid4().hex
    product_id = f"app4-product-{suffix}"
    item_id = f"app4-item-{suffix}"
    plan_id = f"app4-plan-{suffix}"
    rule_id = f"app4-rule-{suffix}"
    setup = SessionLocal()
    first = SessionLocal()
    second = SessionLocal()
    try:
        setup.add(DrugProduct(id=product_id, display_name="APP-4 test", status="ACTIVE"))
        setup.add(
            PrescriptionItem(
                id=item_id,
                prescription_id=f"app4-prescription-{suffix}",
                patient_id=f"app4-patient-{suffix}",
                drug_product_id=product_id,
                start_date=date(2026, 8, 17),
                end_date=date(2026, 8, 17),
                doses_per_day=1,
                meal_instruction_code="AFTER_MEAL",
                status="ACTIVE",
            )
        )
        setup.add(
            MedicationPlan(
                id=plan_id,
                patient_id=f"app4-patient-{suffix}",
                prescription_item_id=item_id,
                drug_product_id=product_id,
                timezone="Asia/Ho_Chi_Minh",
                status="ACTIVE",
            )
        )
        setup.add(
            ScheduleRule(
                id=rule_id,
                medication_plan_id=plan_id,
                rule_type="DAILY_AT_TIMES",
                frequency=1,
                interval_value=1,
                interval_unit="DAY",
                timezone="Asia/Ho_Chi_Minh",
                status="ACTIVE",
            )
        )
        setup.add(ScheduleRuleTime(id=f"app4-time-{suffix}", schedule_rule_id=rule_id, local_time=time(8)))
        setup.commit()

        assert generate_dose_occurrences(
            first, window_start=date(2026, 8, 17), window_end=date(2026, 8, 17)
        ).inserted == 1
        second.execute(text("SET LOCAL lock_timeout = '100ms'"))
        with pytest.raises(OperationalError):
            generate_dose_occurrences(second, window_start=date(2026, 8, 17), window_end=date(2026, 8, 17))
        second.rollback()
        first.commit()

        retried = generate_dose_occurrences(
            setup, window_start=date(2026, 8, 17), window_end=date(2026, 8, 17)
        )
        setup.commit()
        assert (retried.inserted, retried.existing) == (0, 1)
    finally:
        second.rollback()
        first.rollback()
        second.close()
        first.close()
        setup.query(DoseOccurrence).filter(DoseOccurrence.medication_plan_id == plan_id).delete(synchronize_session=False)
        setup.query(ScheduleRuleTime).filter(ScheduleRuleTime.schedule_rule_id == rule_id).delete(synchronize_session=False)
        setup.query(ScheduleRule).filter(ScheduleRule.id == rule_id).delete(synchronize_session=False)
        setup.query(MedicationPlan).filter(MedicationPlan.id == plan_id).delete(synchronize_session=False)
        setup.query(PrescriptionItem).filter(PrescriptionItem.id == item_id).delete(synchronize_session=False)
        setup.query(DrugProduct).filter(DrugProduct.id == product_id).delete(synchronize_session=False)
        setup.commit()
        setup.close()
