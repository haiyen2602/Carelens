"""APP-4 adapter between per-drug V2 occurrences and legacy grouped dose DTOs.

V2 remains one occurrence per medicine/time.  The existing patient API exposes
one grouped dose card per prescription/local time, so this adapter preserves
that shape without making a grouped row the source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.models import DoseOccurrence, Prescription, PrescriptionItem
from backend.services.safety_policy_domain.runtime import process_dose_safety_runtime
from backend.services.scheduling.dose_state import (
    CANCELLED,
    DELAYED,
    DOSE_WINDOW_HALF_WIDTH,
    DUE,
    MISSED,
    SCHEDULED,
    SKIPPED,
    TAKEN,
    transition_dose_occurrence,
)
from backend.services.scheduling.errors import DoseOccurrenceNotFoundError, InvalidDoseTransitionError

PENDING = "PENDING"
_V2_TO_LEGACY_STATUS = {SCHEDULED: PENDING, DUE: PENDING, CANCELLED: CANCELLED}
_ACTIONABLE_TARGETS = frozenset({TAKEN, DELAYED, MISSED, SKIPPED})
_SAFETY_ASSESSMENT_TARGETS = frozenset({DELAYED, MISSED})


@dataclass(frozen=True)
class DoseRuntimeGroup:
    """Legacy-compatible projection of one V2 occurrence group."""

    id: str
    patient_id: str
    prescription_id: str
    scheduled_at: datetime
    window_start: datetime
    window_end: datetime
    status: str
    expected_items: list[dict]
    occurrence_ids: tuple[str, ...]


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _group_id(item: PrescriptionItem, occurrence: DoseOccurrence) -> str:
    if occurrence.scheduled_local_date is None or occurrence.scheduled_local_time is None or not occurrence.timezone:
        raise InvalidDoseTransitionError(
            "V2 occurrence thiếu local scheduling context.", occurrence_id=occurrence.id
        )
    key = ":".join(
        (
            item.prescription_id,
            occurrence.scheduled_local_date.isoformat(),
            occurrence.scheduled_local_time.isoformat(),
            occurrence.timezone,
        )
    )
    return str(uuid5(NAMESPACE_URL, f"vmec04:dose-runtime-group:{key}"))


def _expected_item(item: PrescriptionItem, prescription: Prescription | None) -> dict:
    raw: dict = {}
    if (
        prescription is not None
        and item.migration_item_index is not None
        and isinstance(prescription.items, list)
        and 0 <= item.migration_item_index < len(prescription.items)
        and isinstance(prescription.items[item.migration_item_index], dict)
    ):
        raw = prescription.items[item.migration_item_index]
    return {
        "drug_id": item.legacy_drug_id or raw.get("drug_id", ""),
        "ten_thuoc": item.drug_display_name or raw.get("ten_thuoc", ""),
        "so_vien": raw.get("so_vien_moi_lan"),
        "dang_thuoc": raw.get("dang_thuoc", ""),
        "duong_dung": raw.get("duong_dung", ""),
    }


def _group_rows(db: Session, *, patient_id: str) -> list[DoseRuntimeGroup]:
    rows = list(
        db.execute(
            select(DoseOccurrence, PrescriptionItem)
            .join(PrescriptionItem, PrescriptionItem.id == DoseOccurrence.prescription_item_id)
            .where(DoseOccurrence.patient_id == patient_id)
            .order_by(DoseOccurrence.scheduled_at, DoseOccurrence.id)
        ).all()
    )
    prescriptions = {
        prescription.id: prescription
        for prescription in db.execute(
            select(Prescription).where(Prescription.id.in_({item.prescription_id for _, item in rows}))
        ).scalars()
    } if rows else {}
    grouped: dict[str, list[tuple[DoseOccurrence, PrescriptionItem]]] = {}
    for occurrence, item in rows:
        grouped.setdefault(_group_id(item, occurrence), []).append((occurrence, item))

    result: list[DoseRuntimeGroup] = []
    for group_id, members in grouped.items():
        # The public legacy DTO exposes an ordered ``expected_items`` array.
        # Preserve the original prescription item order instead of leaking the
        # V2 occurrence UUID/query order into photo and display consumers.
        members.sort(
            key=lambda pair: (
                pair[1].migration_item_index if pair[1].migration_item_index is not None else float("inf"),
                pair[0].id,
            )
        )
        statuses = {occurrence.status or SCHEDULED for occurrence, _ in members}
        if len(statuses) != 1:
            raise InvalidDoseTransitionError(
                "Nhóm liều V2 có trạng thái phân kỳ, không thể chiếu an toàn sang DTO legacy.",
                dose_group_id=group_id,
            )
        occurrence, item = members[0]
        scheduled_at = _utc(occurrence.scheduled_at)
        result.append(
            DoseRuntimeGroup(
                id=group_id,
                patient_id=patient_id,
                prescription_id=item.prescription_id,
                scheduled_at=scheduled_at,
                window_start=_utc(occurrence.window_start) if occurrence.window_start else scheduled_at - DOSE_WINDOW_HALF_WIDTH,
                window_end=_utc(occurrence.window_end) if occurrence.window_end else scheduled_at + DOSE_WINDOW_HALF_WIDTH,
                status=_V2_TO_LEGACY_STATUS.get(occurrence.status or SCHEDULED, occurrence.status or SCHEDULED),
                expected_items=[_expected_item(member_item, prescriptions.get(member_item.prescription_id)) for _, member_item in members],
                occurrence_ids=tuple(occurrence.id for occurrence, _ in members),
            )
        )
    return result


def list_v2_dose_groups(db: Session, *, patient_id: str) -> list[DoseRuntimeGroup]:
    """Return V2 rows in the unchanged legacy grouped-dose shape."""

    return _group_rows(db, patient_id=patient_id)


def get_v2_dose_group(db: Session, *, dose_group_id: str) -> DoseRuntimeGroup:
    """Resolve an opaque legacy-compatible V2 group ID.

    The returned ``DoseRuntimeGroup`` still carries ``occurrence_ids`` (real,
    per-item ``DoseOccurrence`` ids) on the dataclass; the legacy patient/photo
    API consumers of this function (``backend/api/dose_routes.py``) never read
    that field and only ever see the opaque group ``id``. BUILD-18B's Agent V2
    tool boundary (``backend/services/agent_read_only_tools.py``) is a
    deliberate, separate, server-authorized exception that does read it, since
    Safety Domain needs a real occurrence id and must never reinterpret the
    synthetic group id as one (see ``backend/agents/v2/orchestrator.py::
    AgentOrchestrator._resolve_occurrence``).
    """

    patient_ids = db.execute(select(DoseOccurrence.patient_id).distinct()).scalars().all()
    for patient_id in patient_ids:
        for group in _group_rows(db, patient_id=patient_id):
            if group.id == dose_group_id:
                return group
    raise DoseOccurrenceNotFoundError("Không tìm thấy nhóm liều V2.", dose_group_id=dose_group_id)


def transition_v2_dose_group(
    db: Session,
    *,
    dose_group_id: str,
    target_status: str,
    event_at: datetime,
    source: str,
    actor_type: str | None = None,
    actor_id: str | None = None,
) -> DoseRuntimeGroup:
    """Apply one patient command atomically to every occurrence in a group."""

    if target_status not in _ACTIONABLE_TARGETS:
        raise InvalidDoseTransitionError("Trạng thái dose V2 không hỗ trợ.", target_status=target_status)
    group = get_v2_dose_group(db, dose_group_id=dose_group_id)
    event_at = _utc(event_at)
    for occurrence_id in group.occurrence_ids:
        occurrence = db.get(DoseOccurrence, occurrence_id)
        if occurrence is None:
            raise DoseOccurrenceNotFoundError("Không tìm thấy liều V2.", occurrence_id=occurrence_id)
        if (occurrence.status or SCHEDULED) == SCHEDULED:
            transition_dose_occurrence(
                db,
                occurrence_id=occurrence_id,
                target_status=DUE,
                event_at=event_at,
                source=source,
                actor_type=actor_type,
                actor_id=actor_id,
            )
        transition_dose_occurrence(
            db,
            occurrence_id=occurrence_id,
            target_status=target_status,
            event_at=event_at,
            source=source,
            actor_type=actor_type,
            actor_id=actor_id,
        )
        if (
            target_status in _SAFETY_ASSESSMENT_TARGETS
            and get_settings().safety_runtime_mode == "shadow"
        ):
            process_dose_safety_runtime(db, occurrence_id=occurrence_id, evaluated_at=event_at)
    db.flush()
    return get_v2_dose_group(db, dose_group_id=dose_group_id)


__all__ = [
    "DoseRuntimeGroup",
    "get_v2_dose_group",
    "list_v2_dose_groups",
    "transition_v2_dose_group",
]
