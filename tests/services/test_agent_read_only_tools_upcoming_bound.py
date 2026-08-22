"""BUILD-27: get_upcoming_doses must stay bounded to a short forward window.

Regression coverage for the production BUDGET_EXCEEDED report on "Ngay mai
toi can uong thuoc gi" -- the tool used to return every future dose group
through the end of the patient's entire prescription (``scheduled_at >=
now``, no upper bound), which reproducibly blew a 60-day chronic regimen's
worth of data (179 groups) past the Agent V2 token budget. See
``backend/services/agent_read_only_tools.py::get_upcoming_doses`` and
``data pharmacy/reports/agent-architecture/57-build-27-budget-exceeded-upcoming-doses.md``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.db.models import DoseOccurrence, Prescription, PrescriptionItem
from backend.services.agent_read_only_tools import AgentReadOnlyDomainTools

PATIENT_ID = "patient-1"
NOW = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for table in (Prescription.__table__, PrescriptionItem.__table__, DoseOccurrence.__table__):
        table.create(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed_daily_doses(db: Session, *, n_days: int, local_time: time = time(20, 0)) -> None:
    """One dose group/day at a fixed local time, starting today, for n_days.

    20:00 is deliberately later than NOW's 09:00 so "today" itself still
    counts as upcoming (not already passed) in every test below."""

    item = PrescriptionItem(id="item-1", prescription_id="rx-1", patient_id=PATIENT_ID, drug_display_name="Thuoc A")
    db.add(item)
    for offset in range(n_days):
        local_date = NOW.date() + timedelta(days=offset)
        scheduled_at = datetime.combine(local_date, local_time, tzinfo=UTC)
        db.add(
            DoseOccurrence(
                id=f"occ-{offset}",
                prescription_item_id=item.id,
                patient_id=PATIENT_ID,
                scheduled_at=scheduled_at,
                scheduled_local_date=local_date,
                scheduled_local_time=local_time,
                timezone="UTC",
                status="SCHEDULED",
                generation_key=f"gen-{offset}",
            )
        )
    db.commit()


def test_get_upcoming_doses_is_bounded_not_the_whole_remaining_prescription(db: Session) -> None:
    """A 90-day regimen must NOT come back as 90 groups -- the exact shape of
    the production incident (60-day regimen -> 179 groups -> BUDGET_EXCEEDED)."""

    _seed_daily_doses(db, n_days=90)
    tools = AgentReadOnlyDomainTools(db, now=lambda: NOW, upcoming_window_days=1)

    result = tools.get_upcoming_doses(patient_id=PATIENT_ID)

    assert len(result["items"]) < 90
    assert len(result["items"]) == 2  # today (9:00 local dose, still upcoming) + tomorrow


def test_get_upcoming_doses_still_includes_tomorrow_regardless_of_default_window(db: Session) -> None:
    """The exact bug being fixed: "Ngay mai" (tomorrow) must never be clipped."""

    _seed_daily_doses(db, n_days=5)
    tools = AgentReadOnlyDomainTools(db, now=lambda: NOW)  # default window from settings

    result = tools.get_upcoming_doses(patient_id=PATIENT_ID)
    tomorrow = (NOW.date() + timedelta(days=1)).isoformat()

    assert any(item["scheduled_at"].startswith(tomorrow) for item in result["items"])


def test_get_upcoming_doses_excludes_already_passed_occurrences(db: Session) -> None:
    item = PrescriptionItem(id="item-1", prescription_id="rx-1", patient_id=PATIENT_ID, drug_display_name="Thuoc A")
    db.add(item)
    db.add(
        DoseOccurrence(
            id="occ-past",
            prescription_item_id=item.id,
            patient_id=PATIENT_ID,
            scheduled_at=NOW - timedelta(hours=1),
            scheduled_local_date=NOW.date(),
            scheduled_local_time=time(8, 0),
            timezone="UTC",
            status="TAKEN",
            generation_key="gen-past",
        )
    )
    db.commit()
    tools = AgentReadOnlyDomainTools(db, now=lambda: NOW, upcoming_window_days=1)

    result = tools.get_upcoming_doses(patient_id=PATIENT_ID)

    assert result["items"] == []


def test_get_today_doses_unaffected_by_the_upcoming_bound(db: Session) -> None:
    """get_today_doses's own exact-day filter is untouched by this fix."""

    _seed_daily_doses(db, n_days=5)
    tools = AgentReadOnlyDomainTools(db, now=lambda: NOW, upcoming_window_days=1)

    result = tools.get_today_doses(patient_id=PATIENT_ID)

    assert len(result["items"]) == 1
    assert result["items"][0]["scheduled_at"].startswith(NOW.date().isoformat())


def test_window_days_is_configurable(db: Session) -> None:
    _seed_daily_doses(db, n_days=10)
    tools = AgentReadOnlyDomainTools(db, now=lambda: NOW, upcoming_window_days=3)

    result = tools.get_upcoming_doses(patient_id=PATIENT_ID)

    assert len(result["items"]) == 4  # today + next 3 calendar days
