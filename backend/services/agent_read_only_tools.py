"""Read-only domain adapters consumed by the isolated Agent V2 Tool Gateway.

This service is the only BUILD-6 adapter allowed to assemble data from the
Drug Knowledge, Prescription, and Scheduling domains for Agent V2.  The Agent
package receives typed projections only; it never imports ORM models or emits
SQL itself.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Prescription
from backend.services.drug_knowledge.v2_agent import (
    get_confirmed_drug_knowledge,
    get_v2_agent_knowledge_service,
)
from backend.services.scheduling.runtime_adapter import (
    get_v2_dose_group,
    list_v2_dose_groups,
)


class AgentReadOnlyDomainTools:
    """Authorize at the Tool Gateway, then project domain-owned read models."""

    def __init__(self, db: Session, *, now: Callable[[], datetime] | None = None) -> None:
        self._db = db
        self._now = now or (lambda: datetime.now(UTC))

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
        today = self._as_utc(self._now()).date()
        return {"items": [self._dose_group(group) for group in self._groups(patient_id) if group.scheduled_at.date() == today]}

    def get_upcoming_doses(self, *, patient_id: str) -> dict[str, Any]:
        now = self._as_utc(self._now())
        return {"items": [self._dose_group(group) for group in self._groups(patient_id) if group.scheduled_at >= now]}

    def get_dose_status(self, *, patient_id: str, dose_id: str) -> dict[str, Any]:
        group = get_v2_dose_group(self._db, dose_group_id=dose_id)
        # Do not disclose whether another patient's opaque group identifier
        # exists. The gateway converts this into one safe, generic error code.
        if group.patient_id != patient_id:
            raise LookupError("dose group does not belong to authorized patient")
        return self._dose_group(group)

    def _groups(self, patient_id: str):
        return list_v2_dose_groups(self._db, patient_id=patient_id)

    @staticmethod
    def _dose_group(group: Any) -> dict[str, Any]:
        return {
            "id": group.id,
            "prescription_id": group.prescription_id,
            "scheduled_at": group.scheduled_at.isoformat(),
            "window_start": group.window_start.isoformat(),
            "window_end": group.window_end.isoformat(),
            "status": group.status,
            "expected_items": group.expected_items,
            # BUILD-18B defect 2: the real per-item occurrence ids Safety
            # Domain assesses, distinct from ``id`` (the synthetic group id).
            "occurrence_ids": list(group.occurrence_ids),
        }

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
