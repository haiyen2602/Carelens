"""Model-level checks for the additive DB-4D schedule schema."""

from __future__ import annotations

from backend.db.models import DoseOccurrence, PrescriptionItem, ScheduleRuleCycle, ScheduleRuleTime


def test_prescription_item_exposes_nullable_schedule_intent_fields() -> None:
    """DB-4D preserves raw prescription compatibility while adding schedule intent."""

    columns = PrescriptionItem.__table__.c
    assert columns.doses_per_day.nullable
    assert columns.meal_instruction_code.nullable
    assert columns.meal_instruction_text.nullable
    assert columns.end_date.nullable


def test_normalized_rule_tables_have_the_approved_unique_and_cycle_keys() -> None:
    """One local time per rule and one optional cycle per rule are representable."""

    time_columns = ScheduleRuleTime.__table__.c
    cycle_columns = ScheduleRuleCycle.__table__.c
    assert not time_columns.schedule_rule_id.nullable
    assert not time_columns.local_time.nullable
    assert cycle_columns.schedule_rule_id.primary_key
    assert frozenset({"schedule_rule_id", "local_time"}) in {
        frozenset(constraint.columns.keys()) for constraint in ScheduleRuleTime.__table__.constraints
    }


def test_occurrence_keeps_nullable_local_generation_context() -> None:
    """No occurrence is generated, but future scheduling can retain local context."""

    columns = DoseOccurrence.__table__.c
    assert columns.scheduled_local_date.nullable
    assert columns.scheduled_local_time.nullable
    assert columns.timezone.nullable
    assert "ix_dose_occurrence_patient_local_schedule" in {
        index.name for index in DoseOccurrence.__table__.indexes
    }
