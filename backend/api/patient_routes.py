"""
Danh sách bệnh nhân — cho form kê đơn của bác sĩ chọn người nhận.

CHƯA CÓ TRONG api-contracts.md, cùng lý do với drug_routes.py: cần thêm vào
§2 và review trước khi coi là ổn định.

Bác sĩ nào cũng xem được toàn bộ bệnh nhân (quyết định PM 2026-08-14 - kê
đơn/theo dõi không giới hạn theo `patient.doctor_id`; "chỉ định riêng" là
bác sĩ tự bấm nút "Theo dõi" trên dashboard báo cáo, xem `watch` ở
reporting_routes.py, KHÔNG phải lọc theo doctor_id ở đây). Tìm bằng tham số
`search` (khớp theo ID hoặc tên).
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, get_current_user, require_role
from backend.db.base import get_db
from backend.db.models import Account, Patient
from backend.models.schemas import (
    PatientHealthUpdateRequest,
    PatientProfileOut,
    PatientProfileUpdateRequest,
    PatientSummary,
)
from backend.services.audit import log_action, patient_label
from backend.services.patient_profile import ensure_patient_profile, is_patient_profile_complete

patient_router = APIRouter()


def _to_profile(p: Patient) -> PatientProfileOut:
    return PatientProfileOut(
        id=p.id,
        full_name=p.full_name,
        date_of_birth=p.date_of_birth,
        year_of_birth=p.year_of_birth,
        phone=p.phone,
        address=p.address,
        gender=p.gender,
        height_cm=p.height_cm,
        weight_kg=p.weight_kg,
        profile_completed=is_patient_profile_complete(p),
        photo_capture_enabled=p.photo_capture_enabled,
    )


def _get_current_patient(db: Session, current_user: CurrentUser) -> Patient | None:
    """Return the profile referenced by JWT, repairing only its own stale link."""
    if not current_user.patient_id:
        return None

    patient = db.get(Patient, current_user.patient_id)
    if patient is not None:
        return patient

    account = db.get(Account, current_user.id)
    if (
        account is None
        or account.role != "patient"
        or account.patient_id != current_user.patient_id
        or not ensure_patient_profile(db, account)
    ):
        return None

    db.commit()
    return db.get(Patient, current_user.patient_id)


def _to_summary(p: Patient, *, full: bool = True) -> PatientSummary:
    if not full:
        # SUA 2026-08-14: dung cho nguoi goi role=patient (xem list_patients
        # ben duoi) - KHONG tra ve note/gender/height_cm/weight_kg, day la
        # thong tin suc khoe nhay cam cua 1 benh nhan KHAC, khong duoc lo qua
        # 1 o tim kiem "moi nguoi than theo doi nhau".
        return PatientSummary(id=p.id, full_name=p.full_name, year_of_birth=p.year_of_birth)
    return PatientSummary(
        id=p.id,
        full_name=p.full_name,
        year_of_birth=p.year_of_birth,
        note=p.note,
        gender=p.gender,
        height_cm=p.height_cm,
        weight_kg=p.weight_kg,
    )


@patient_router.get(
    "/patients",
    response_model=list[PatientSummary],
)
def list_patients(
    search: str | None = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
    # SUA 2026-08-14: mo them role=patient - form "Gửi lời mời theo dõi"
    # (frontend/src/app/patient/family/page.tsx) can tim patient_id/ten benh
    # nhan KHAC de moi theo doi nhau, truoc do goi thang endpoint chi
    # doctor/admin nay nen luon 403, khien o tim kiem luon rong va khong ai
    # moi duoc (bug bao cao that qua UI 2026-08-14). Buc tuong rieng: benh
    # nhan KHONG duoc tra ve day du PatientSummary nhu doctor/admin - xem
    # _to_summary(full=False) o duoi.
    current_user: CurrentUser = Depends(require_role("doctor", "admin", "patient")),
) -> list[PatientSummary]:
    query = select(Patient)
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(Patient.id.ilike(pattern), Patient.full_name.ilike(pattern)))
    rows = db.execute(query.order_by(Patient.full_name)).scalars().all()

    if current_user.role == "patient":
        # Khong can tu tim/tu moi chinh minh - loai khoi ket qua o tang
        # server (khong chi dua vao frontend loc, cung nguyen tac IDOR da
        # dung xuyen suot du an).
        rows = [p for p in rows if p.id != current_user.patient_id]
        return [_to_summary(p, full=False) for p in rows]

    return [_to_summary(p) for p in rows]


@patient_router.get(
    "/patients/me",
    response_model=PatientProfileOut,
)
def get_my_patient_profile(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PatientProfileOut:
    """Benh nhan tu xem ho so CA NHAN day du cua CHINH minh (ten, ngay sinh,
    sdt, dia chi, gender, height/weight, profile_completed) - phan hoi review
    2026-08-14: trang patient/health/page.tsx tung goi list_patients() (chi
    doctor/admin) de tim ho so chinh minh, luon 403 voi role=patient nen
    "tuoi · ghi chu" o dau trang luon rong (xac nhan qua DB production,
    BN-0000). Route rieng nay dung current_user.patient_id tu JWT (khong
    nhan patient_id tu client) - cung nguyen tac chong IDOR da dung o
    get_current_patient_id(), khong mo lai duong doc patient_id song song.
    KHONG dung require_role("doctor","admin") nhu list_patients() - bat ky
    role nao co patient_id gan voi tai khoan (thuc te chi role=patient) deu
    xem duoc DUNG ho so cua chinh minh, khong xem duoc nguoi khac.

    SUA 2026-08-23: doi tu PatientSummary sang PatientProfileOut (cung shape
    voi PATCH ben duoi) - man hinh "Doi thong tin ca nhan" (frontend/src/
    components/edit-personal-info-dialog.tsx) can doc lai sdt/ngay sinh/dia
    chi hien co de do vao form, PatientSummary khong co may truong nay."""
    if not current_user.patient_id:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN, detail="Tài khoản không gắn với hồ sơ bệnh nhân nào"
        )
    patient = _get_current_patient(db, current_user)
    if patient is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Bệnh nhân không tồn tại")
    return _to_profile(patient)


@patient_router.patch(
    "/patients/me",
    response_model=PatientProfileOut,
)
def update_my_profile(
    body: PatientProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role("patient")),
) -> PatientProfileOut:
    """Onboarding: benh nhan tu dien thong tin ca nhan (migration 0023, xem
    Patient.date_of_birth/phone/address/profile_completed). Sau khi luu,
    `profile_completed=True` - trang onboarding (frontend/src/app/
    onboarding/profile/page.tsx) khong hoi lai nua, nhung van co the sua lai
    sau qua man hinh Cai dat (goi lai endpoint nay).

    Dang SAU "/patients/me" (GET, xem get_my_patient_profile o tren) trong
    file nay - Starlette khop route theo METHOD rieng, PATCH/GET tren cung 1
    path khong xung dot, nhung van dang truoc "/patients/{patient_id}" (co
    y): neu doi cho, PATCH /patients/me se roi vao update_patient_health voi
    patient_id="me" (403 vi endpoint do chi cho doctor/admin)."""
    patient = _get_current_patient(db, current_user)
    if patient is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Bệnh nhân không tồn tại")

    next_date_of_birth = body.date_of_birth if body.date_of_birth is not None else patient.date_of_birth
    next_phone = body.phone if body.phone is not None else patient.phone
    next_address = body.address if body.address is not None else patient.address
    next_gender = body.gender if body.gender is not None else patient.gender
    next_height_cm = body.height_cm if body.height_cm is not None else patient.height_cm
    next_weight_kg = body.weight_kg if body.weight_kg is not None else patient.weight_kg

    profile_after_update = Patient(
        date_of_birth=next_date_of_birth,
        phone=next_phone,
        address=next_address,
        gender=next_gender,
        height_cm=next_height_cm,
        weight_kg=next_weight_kg,
    )
    if not is_patient_profile_complete(profile_after_update):
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Vui lòng nhập ngày sinh, số điện thoại, địa chỉ, giới tính, chiều cao và cân nặng.",
        )

    # `photo_capture_enabled` KHONG nam trong `profile_after_update` o tren:
    # no la tuy chon chup anh xac nhan lieu, khong phai mot truong cua "ho so
    # da day du chua" - dua vao kiem tra se chan mat nguoi dung chi muon tat
    # chup anh.
    for field in ("phone", "address", "gender", "height_cm", "weight_kg", "photo_capture_enabled"):
        value = getattr(body, field)
        if value is not None:
            setattr(patient, field, value)

    if body.date_of_birth is not None:
        patient.date_of_birth = body.date_of_birth
        patient.year_of_birth = body.date_of_birth.year

    patient.profile_completed = True

    db.commit()
    db.refresh(patient)
    return _to_profile(patient)


@patient_router.patch(
    "/patients/{patient_id}",
    response_model=PatientSummary,
)
def update_patient_health(
    patient_id: str,
    body: PatientHealthUpdateRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role("doctor", "admin")),
) -> PatientSummary:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Bệnh nhân không tồn tại")

    # Liet ke DUNG nhung truong that su doi - nhat ky "Cập nhật hồ sơ" khong
    # noi ro doi gi thi khong dung de doi chieu duoc khi can truy lai.
    da_doi: list[str] = []
    for field, nhan in (
        ("note", "bệnh nền"),
        ("gender", "giới tính"),
        ("height_cm", "chiều cao"),
        ("weight_kg", "cân nặng"),
    ):
        value = getattr(body, field)
        if value is not None and value != getattr(patient, field):
            setattr(patient, field, value)
            da_doi.append(nhan)

    if da_doi:
        log_action(
            db,
            current_user,
            f"Cập nhật hồ sơ sức khoẻ ({', '.join(da_doi)})",
            patient_label(db, patient_id),
        )

    db.commit()
    db.refresh(patient)
    return _to_summary(patient)
