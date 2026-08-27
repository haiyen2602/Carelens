"""Tu dong tao `DoctorWatch` cho benh nhan MOI TAO - theo yeu cau PM
2026-08-14 (tiep noi quyet dinh cung ngay da chon DoctorWatch lam "dich loc"
DUY NHAT cho Hộp cảnh báo/chuông thông báo, xem docstring class DoctorWatch,
`backend/db/models.py`, va `list_escalations()` trong
`backend/api/reporting_routes.py`).

Truoc thay doi nay: benh nhan MOI tao khong ai theo doi ca (0 dong
DoctorWatch), nen Cảnh báo mới nhất/chuông thông báo cua MOI bac si deu
rong cho tan khi co ai do tu bam "Theo dõi" - xac nhan la bug that qua bao
cao kem anh chup man hinh (2026-08-14). Sua: benh nhan MOI mac dinh duoc
TAT CA bac si dang co trong he thong theo doi ngay luc tao - bac si nao
khong can theo doi 1 benh nhan cu the thi TU bam "Bỏ theo dõi"
(PATCH /reporting/patients/{id}/watch, watch=false), khong phai nguoc lai."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Account, DoctorWatch


def auto_watch_new_patient(db: Session, patient_id: str) -> None:
    """Goi NGAY SAU khi `db.add()` 1 dong `Patient` MOI (chi khi THAT SU la
    benh nhan moi - khong goi khi lien ket toi 1 `patient_id` DA CO SAN, xem
    `account_routes.py::create_account()`) - tao 1 dong `DoctorWatch` cho MOI
    tai khoan role=doctor dang co (`Account.doctor_id` khong rong) tro toi
    `patient_id` nay.

    KHONG tu `db.commit()` o day - nguoi goi (`auth_routes.py::register()`/
    `account_routes.py::create_account()`) tu quyet dinh diem commit, dung
    CHUNG 1 transaction voi viec tao Account/Patient - tranh trang thai "nua
    vien" (co Patient nhung thieu DoctorWatch) neu loi xay ra giua chung."""
    doctor_ids = (
        db.execute(select(Account.doctor_id).where(Account.role == "doctor", Account.doctor_id.is_not(None)))
        .scalars()
        .all()
    )
    watched_doctor_ids = set(
        db.execute(select(DoctorWatch.doctor_id).where(DoctorWatch.patient_id == patient_id))
        .scalars()
        .all()
    )
    for doctor_id in set(doctor_ids) - watched_doctor_ids:
        db.add(DoctorWatch(doctor_id=doctor_id, patient_id=patient_id))
