"""Unit coverage for DB-4C legacy prescription backfill decisions."""

from __future__ import annotations

from datetime import date

import pytest

from scripts.data_v2.backfill_prescription_v2 import (
    DEFAULT_TIMEZONE,
    assert_local_postgres_url,
    build_backfill_plan,
    deterministic_id,
    parse_schedule_times,
)


def legacy_prescription(*, status: str = "active", items: object | None = None) -> dict[str, object]:
    """Return a valid one-item legacy prescription unless an override is supplied."""

    return {
        "id": "legacy-prescription-1",
        "patient_id": "patient-1",
        "status": status,
        "start_date": "2026-08-17",
        "duration_days": 7,
        "note": "Use after meals",
        "items": items
        if items is not None
        else [
            {
                "drug_id": "known-drug",
                "ten_thuoc": "Known Drug",
                "lieu_dung": "1 tablet",
                "duong_dung": "oral",
                "thoi_diem_dung": "after breakfast",
                "gio_nhac": ["20:00", "08:00"],
            }
        ],
    }


def test_backfill_maps_valid_item_and_creates_daily_schedule_rule() -> None:
    """A mapped active item with valid reminders is actionable but creates no dose."""

    plan = build_backfill_plan([legacy_prescription()], {"known-drug": "canonical-product-1"})

    assert plan.source_counts == {"legacy_items": 1}
    assert len(plan.prescription_items) == len(plan.medication_plans) == len(plan.schedule_rules) == 1
    item = plan.prescription_items[0]
    medication_plan = plan.medication_plans[0]
    rule = plan.schedule_rules[0]
    assert item["drug_product_id"] == "canonical-product-1"
    assert item["dose_text"] == "1 tablet"
    assert item["frequency_text"] == "after breakfast"
    assert item["instructions"] == "Use after meals"
    assert item["end_date"] == date(2026, 8, 23)
    assert medication_plan["status"] == "ACTIVE"
    assert medication_plan["timezone"] == DEFAULT_TIMEZONE
    assert rule["times_of_day"] == ["08:00", "20:00"]
    assert rule["status"] == "ACTIVE"


@pytest.mark.parametrize(
    ("gio_nhac", "reason"),
    [
        (None, "MISSING_OR_NON_LIST_GIO_NHAC"),
        ([], "MISSING_OR_NON_LIST_GIO_NHAC"),
        (["8:00"], "INVALID_GIO_NHAC_TIME"),
        (["08:00", "08:00"], "DUPLICATE_GIO_NHAC_TIME"),
    ],
)
def test_invalid_schedule_creates_review_plan_without_rule(gio_nhac: object, reason: str) -> None:
    """Missing or unsafe reminder data must never be silently scheduled."""

    prescription = legacy_prescription(items=[{"drug_id": "known-drug", "gio_nhac": gio_nhac}])
    plan = build_backfill_plan([prescription], {"known-drug": "canonical-product-1"})

    assert len(plan.prescription_items) == len(plan.medication_plans) == 1
    assert plan.medication_plans[0]["status"] == "REVIEW_REQUIRED"
    assert plan.schedule_rules == []
    assert plan.invalid_schedules[0].reason == reason


def test_unmapped_drug_is_preserved_without_guessed_product() -> None:
    """Backfill retains the legacy ID and marks its plan for review."""

    plan = build_backfill_plan([legacy_prescription()], {})

    assert plan.prescription_items[0]["legacy_drug_id"] == "known-drug"
    assert plan.prescription_items[0]["drug_product_id"] is None
    assert plan.medication_plans[0]["status"] == "REVIEW_REQUIRED"
    assert len(plan.schedule_rules) == 1
    assert plan.schedule_rules[0]["status"] == "DRAFT"
    assert plan.unmapped_drug_ids[0].reason == "NO_ACTIVE_DRUG_ID_MAP"


def test_malformed_active_items_are_reported_not_backfilled() -> None:
    """Malformed legacy JSON never becomes invented prescription data."""

    plan = build_backfill_plan([legacy_prescription(items="not-an-array")], {})

    assert plan.prescription_items == []
    assert plan.malformed_items[0].reason == "ITEMS_NOT_A_LIST"
    assert plan.active_prescriptions_without_items == ["legacy-prescription-1"]


def test_deterministic_target_ids_and_local_target_guard() -> None:
    """A re-run has stable IDs and cannot point at Railway/shared PostgreSQL."""

    assert deterministic_id("prescription-item", "p1", 0) == deterministic_id("prescription-item", "p1", 0)
    assert deterministic_id("prescription-item", "p1", 0) != deterministic_id("prescription-item", "p1", 1)
    assert parse_schedule_times(["08:00"]) == (["08:00"], None)
    assert_local_postgres_url("postgresql://vmec:vmec@localhost:5432/db4c")
    with pytest.raises(ValueError, match="local PostgreSQL"):
        assert_local_postgres_url("postgresql://vmec:vmec@railway.example:5432/db4c")
