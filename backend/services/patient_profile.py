"""Quy tắc hoàn tất hồ sơ bệnh nhân dùng chung cho Auth và Patient API."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from backend.db.models import Account, Patient
from backend.services.doctor_watch import auto_watch_new_patient


def is_patient_profile_complete(patient: Patient) -> bool:
    """Chỉ hoàn tất khi sáu trường onboarding đều đã có giá trị hợp lệ.

    ``profile_completed`` cũ không đủ làm nguồn sự thật: trước khi chiều cao
    và cân nặng trở thành bắt buộc, một số hồ sơ có thể đã được đánh dấu xong
    dù còn thiếu một trong hai giá trị này.
    """

    return (
        isinstance(patient.date_of_birth, date)
        and bool(patient.phone and patient.phone.strip())
        and bool(patient.address and patient.address.strip())
        and bool(patient.gender and patient.gender.strip())
        and patient.height_cm is not None
        and patient.weight_kg is not None
    )


def ensure_patient_profile(db: Session, account: Account) -> bool:
    """Restore a missing profile for an authenticated patient account.

    Reuse a legacy ``patient_id`` when present so existing records and token
    claims continue to point at the same patient. Return whether data changed;
    the caller owns the transaction boundary.
    """
    if account.role != "patient":
        return False

    if not account.patient_id:
        from backend.services.patient_id import generate_next_patient_id

        patient_id = generate_next_patient_id(db)
        db.add(Patient(id=patient_id, full_name=account.full_name))
        account.patient_id = patient_id
        auto_watch_new_patient(db, patient_id)
        return True

    if db.get(Patient, account.patient_id) is not None:
        return False

    db.add(Patient(id=account.patient_id, full_name=account.full_name))
    auto_watch_new_patient(db, account.patient_id)
    return True
