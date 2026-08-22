"""Read-only domain adapters consumed by the isolated Agent V2 Tool Gateway.

This service is the only BUILD-6 adapter allowed to assemble data from the
Drug Knowledge, Prescription, and Scheduling domains for Agent V2.  The Agent
package receives typed projections only; it never imports ORM models or emits
SQL itself.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.models import Prescription
from backend.services.drug_knowledge.v2_agent import (
    get_confirmed_drug_knowledge,
    get_v2_agent_knowledge_service,
)
from backend.services.scheduling.runtime_adapter import (
    get_v2_dose_group,
    list_v2_dose_groups,
)
from backend.services.scheduling.write_path import DEFAULT_TIMEZONE

# BUILD-27B: hard ceiling regardless of what the router ever resolves --
# defense in depth against the exact class of bug BUILD-27 fixed (an
# unbounded/near-unbounded date span serialized wholesale into the model
# prompt). No feature this build implements asks for more than ~1 week.
_MAX_RANGE_SPAN_DAYS = 31
_DISPLAY_TIMEZONE = ZoneInfo(DEFAULT_TIMEZONE)


class AgentReadOnlyDomainTools:
    """Authorize at the Tool Gateway, then project domain-owned read models."""

    def __init__(
        self, db: Session, *, now: Callable[[], datetime] | None = None, upcoming_window_days: int | None = None
    ) -> None:
        self._db = db
        self._now = now or (lambda: datetime.now(UTC))
        # BUILD-27: defaulted from settings (not hardcoded) so it stays
        # tunable without a code change, same as every other Agent V2 budget
        # knob. See get_upcoming_doses below for why this bound exists.
        self._upcoming_window_days = (
            upcoming_window_days if upcoming_window_days is not None else get_settings().agent_upcoming_doses_window_days
        )

    def search_drug(self, *, query: str, limit: int) -> dict[str, Any]:
        items = get_v2_agent_knowledge_service().search_catalog(query, limit=limit)
        return {
            "items": [
                {
                    "legacy_drug_id": item.drug_id,
                    "name": item.ten_thuoc,
                    "dosage_form": item.dang_thuoc,
                    "route": item.duong_dung,
                    "strength": item.ham_luong,
                }
                for item in items
            ]
        }

    def get_drug_info(self, *, legacy_drug_id: str, query: str) -> dict[str, Any]:
        lookup = get_confirmed_drug_knowledge(self._db, legacy_drug_id, query, mode="v2")
        return {
            "legacy_drug_id": legacy_drug_id,
            "results": [
                {"field": row.field_group, "content": row.noi_dung, "source": row.source}
                for row in lookup.results
            ],
            "trace": lookup.trace,
        }

    def get_active_prescriptions(self, *, patient_id: str) -> dict[str, Any]:
        rows = self._db.execute(
            select(Prescription)
            .where(Prescription.patient_id == patient_id, Prescription.status.in_(("active", "approved")))
            .order_by(Prescription.approved_at.desc(), Prescription.id)
        ).scalars().all()
        return {
            "items": [
                {
                    "id": row.id,
                    "status": row.status,
                    "note": row.note,
                    "start_date": row.start_date,
                    "duration_days": row.duration_days,
                }
                for row in rows
            ]
        }

    def get_today_doses(self, *, patient_id: str) -> dict[str, Any]:
        today = self._as_local(self._now()).date()
        return {
            "items": [
                self._dose_group(group)
                for group in self._groups(patient_id)
                if self._as_local(group.scheduled_at).date() == today
            ]
        }

    def get_upcoming_doses(self, *, patient_id: str) -> dict[str, Any]:
        # BUILD-27: bounded to a forward window (see
        # settings.agent_upcoming_doses_window_days for the empirical sizing
        # rationale), unlike the unbounded ``scheduled_at >= now`` this
        # replaced. That returned every future dose group through the end of
        # the patient's ENTIRE prescription -- for an ordinary 60-day chronic
        # regimen this was 179 groups / 100KB+ of JSON, reproducibly 47,487
        # real tokens against a 4,096 token budget (11x over) on "Ngay mai
        # toi can uong thuoc gi". This tool's own description ("Read the
        # authorized patient's upcoming doses") never promised the full
        # remaining prescription. See report
        # 57-build-27-budget-exceeded-upcoming-doses.md.
        now = self._as_utc(self._now())
        # Local-calendar-date bound (like get_today_doses), not a raw now+N hours
        # cutoff -- that would clip "tomorrow" itself whenever "now" is late
        # in the day. This always fully covers today's remainder through
        # window_days calendar days ahead, regardless of what time it is now.
        horizon_date = self._as_local(now).date() + timedelta(days=self._upcoming_window_days)
        return {
            "items": [
                self._dose_group(group)
                for group in self._groups(patient_id)
                if self._as_utc(group.scheduled_at) >= now
                and self._as_local(group.scheduled_at).date() <= horizon_date
            ]
        }

    def get_doses_for_range(self, *, patient_id: str, start_date: date, end_date: date) -> dict[str, Any]:
        """Bounded past/future date-range read for BUILD-27B time-aware queries.

        Only ever reachable with a router-resolved range (see
        ``AuthorizedToolContext.resolved_date_range`` / ``ToolExecutionError
        ("DATE_RANGE_NOT_RESOLVED")`` in ``backend/agents/v2/tools.py``) --
        never an arbitrary model-supplied span.

        Buckets by the patient's LOCAL calendar date. BUILD-27C applies the
        same rule to ``get_today_doses`` and ``get_upcoming_doses`` so a dose
        between 00:00-06:59 Asia/Ho_Chi_Minh is never assigned to the prior
        UTC calendar date in a patient-facing response.
        """
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")
        if (end_date - start_date).days + 1 > _MAX_RANGE_SPAN_DAYS:
            raise ValueError("date range exceeds the maximum allowed span")
        return {
            "items": [
                self._dose_group(group)
                for group in self._groups(patient_id)
                if start_date <= self._as_local(group.scheduled_at).date() <= end_date
            ]
        }

    def get_dose_status(self, *, patient_id: str, dose_id: str) -> dict[str, Any]:
        group = get_v2_dose_group(self._db, dose_group_id=dose_id)
        # Do not disclose whether another patient's opaque group identifier
        # exists. The gateway converts this into one safe, generic error code.
        if group.patient_id != patient_id:
            raise LookupError("dose group does not belong to authorized patient")
        return self._dose_group(group)

    def _groups(self, patient_id: str):
        return list_v2_dose_groups(self._db, patient_id=patient_id)

    @classmethod
    def _dose_group(cls, group: Any) -> dict[str, Any]:
        return {
            "id": group.id,
            "prescription_id": group.prescription_id,
            # Dose times are presentation data for Agent V2. Persisted values
            # remain UTC; this projection is the sole UTC -> local conversion
            # boundary for every user-facing dose tool response.
            "scheduled_at": cls._as_local(group.scheduled_at).isoformat(),
            "window_start": cls._as_local(group.window_start).isoformat(),
            "window_end": cls._as_local(group.window_end).isoformat(),
            "status": group.status,
            "expected_items": group.expected_items,
            # BUILD-18B defect 2: the real per-item occurrence ids Safety
            # Domain assesses, distinct from ``id`` (the synthetic group id).
            "occurrence_ids": list(group.occurrence_ids),
        }

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @classmethod
    def _as_local(cls, value: datetime) -> datetime:
        return cls._as_utc(value).astimezone(_DISPLAY_TIMEZONE)
