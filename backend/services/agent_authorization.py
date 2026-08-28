"""Server-side actor/patient authorization boundary for Agent V2 reads."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser
from backend.db.models import CaregiverLink, DoctorWatch, Patient


def require_agent_patient_access(db: Session, actor: CurrentUser, patient_id: str) -> str:
    """Return an authorized patient ID or fail closed before any Agent tool read."""
    if not patient_id or db.get(Patient, patient_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay benh nhan")

    if actor.role == "patient" and actor.patient_id == patient_id:
        return patient_id

    # KHONG gate bang `actor.role == "caregiver"` (SUA 2026-08-28): `role` chi
    # giu duoc MOT gia tri, trong khi mot nguoi vua la benh nhan cua chinh
    # minh vua cham bo/me la chuyen binh thuong. Gate theo role khien nguoi
    # con (role="patient") bi 403 khi hoi ve me du co CaregiverLink hop le.
    # Su that nam o BANG LIEN KET, khong o cot role.
    #
    # Chi tinh `accepted`: dong "pending" la loi moi chua duoc dong y - cho
    # doc du lieu y te tu do se bien viec gui loi moi thanh cach lay thong tin.
    link = db.execute(
        select(CaregiverLink.id).where(
            CaregiverLink.caregiver_account_id == actor.id,
            CaregiverLink.patient_id == patient_id,
            CaregiverLink.status == "accepted",
        )
    ).scalar_one_or_none()
    if link is not None:
        return patient_id

    if actor.role == "doctor" and actor.doctor_id:
        watch = db.execute(
            select(DoctorWatch.id).where(
                DoctorWatch.doctor_id == actor.doctor_id,
                DoctorWatch.patient_id == patient_id,
            )
        ).scalar_one_or_none()
        if watch is not None:
            return patient_id

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Khong co quyen truy cap du lieu benh nhan")
