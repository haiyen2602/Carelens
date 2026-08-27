"""Authenticated delivery of validated catalog images for prescribed products."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import or_, select, union
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, get_current_user
from backend.config import get_settings
from backend.db.base import get_db
from backend.db.models import (
    CaregiverLink,
    DoctorWatch,
    DoseEvent,
    DoseOccurrence,
    DrugIdMap,
    DrugImage,
    MedicationPlan,
    Patient,
    PrescriptionItem,
)
from backend.services.drug_images import VALIDATION_STATUS, FileSystemStorageBackend

drug_image_router = APIRouter()
logger = logging.getLogger(__name__)


@drug_image_router.get("/drug-images/{drug_image_id}")
def get_prescribed_drug_image(
    drug_image_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> FileResponse:
    """Return bytes only when the exact image belongs to an authorized medication.

    The client supplies an opaque image ID, never a storage key.  Product access
    is derived server-side from prescription/plan/occurrence identity, including
    ACTIVE legacy mappings, so a catalog image cannot become an arbitrary browser.
    """

    image = db.scalar(
        select(DrugImage).where(
            DrugImage.id == drug_image_id,
            DrugImage.is_primary.is_(True),
            DrugImage.validation_status == VALIDATION_STATUS,
        )
    )
    if image is None:
        logger.warning("IMAGE_NOT_FOUND image_id=%s", drug_image_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy hình ảnh thuốc")
    if not _is_authorized_for_product(db, drug_product_id=image.drug_product_id, current_user=current_user):
        logger.warning("IMAGE_UNAUTHORIZED image_id=%s account_id=%s", image.id, current_user.id)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền xem hình ảnh thuốc này")

    path = FileSystemStorageBackend(Path(get_settings().drug_image_storage_dir)).path_for(image.storage_key)
    if not path.is_file():
        logger.warning("IMAGE_STORAGE_MISSING image_id=%s", image.id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hình ảnh thuốc hiện không khả dụng")
    return FileResponse(
        path,
        media_type=image.mime_type,
        headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"},
    )


def _is_authorized_for_product(db: Session, *, drug_product_id: str, current_user: CurrentUser) -> bool:
    """Check exact product ownership through a real patient relationship.

    The image ID is deliberately not sufficient authorization. A caller must
    first be linked to a patient, then that patient's V2 medication records or
    legacy dose JSON must identify this exact canonical product.
    """

    patient_ids = _authorized_patient_ids(db, current_user)
    if not patient_ids:
        return False

    mapped_legacy_ids = select(DrugIdMap.legacy_drug_id).where(
        DrugIdMap.drug_product_id == drug_product_id,
        DrugIdMap.mapping_status == "ACTIVE",
    )
    item_match = or_(
        PrescriptionItem.drug_product_id == drug_product_id,
        PrescriptionItem.legacy_drug_id.in_(mapped_legacy_ids),
    )
    plan_match = or_(
        MedicationPlan.drug_product_id == drug_product_id,
        MedicationPlan.legacy_drug_id.in_(mapped_legacy_ids),
    )
    occurrence_match = or_(
        DoseOccurrence.drug_product_id == drug_product_id,
        DoseOccurrence.legacy_drug_id.in_(mapped_legacy_ids),
    )
    v2_patient_id = union(
        select(PrescriptionItem.patient_id).where(PrescriptionItem.patient_id.in_(patient_ids), item_match),
        select(MedicationPlan.patient_id).where(MedicationPlan.patient_id.in_(patient_ids), plan_match),
        select(DoseOccurrence.patient_id).where(DoseOccurrence.patient_id.in_(patient_ids), occurrence_match),
    ).limit(1)
    if db.scalar(v2_patient_id) is not None:
        return True

    active_legacy_ids = set(db.scalars(mapped_legacy_ids).all())
    return _has_legacy_dose_for_product(
        db,
        patient_ids=patient_ids,
        drug_product_id=drug_product_id,
        active_legacy_ids=active_legacy_ids,
    )


def _authorized_patient_ids(db: Session, current_user: CurrentUser) -> set[str]:
    """Resolve patients reachable by the authenticated actor's actual link."""

    if current_user.role in {"admin", "super_admin"}:
        return set(db.scalars(select(Patient.id)).all())
    if current_user.role == "patient":
        return {current_user.patient_id} if current_user.patient_id else set()
    if current_user.role == "caregiver":
        return set(
            db.scalars(
                select(CaregiverLink.patient_id).where(
                    CaregiverLink.caregiver_account_id == current_user.id,
                    CaregiverLink.status == "accepted",
                )
            ).all()
        )
    if current_user.role == "doctor" and current_user.doctor_id:
        return set(
            db.scalars(
                select(Patient.id)
                .where(Patient.doctor_id == current_user.doctor_id)
                .union(select(DoctorWatch.patient_id).where(DoctorWatch.doctor_id == current_user.doctor_id))
            ).all()
        )
    return set()


def _has_legacy_dose_for_product(
    db: Session,
    *,
    patient_ids: set[str],
    drug_product_id: str,
    active_legacy_ids: set[str],
) -> bool:
    """Match legacy JSON exactly; it is deliberately never name-matched."""

    dose_items = db.execute(select(DoseEvent.expected_items).where(DoseEvent.patient_id.in_(patient_ids))).scalars()
    for items in dose_items:
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("drug_product_id") == drug_product_id:
                return True
            if item.get("drug_id") in active_legacy_ids:
                return True
    return False
