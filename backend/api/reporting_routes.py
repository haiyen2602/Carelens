"""
Dashboard bao cao cua bac si - danh sach benh nhan kem ty le tuan thu, danh
sach escalation, danh sach audit-log. THEM 2026-08-13, cung muc dich voi
patient_routes.py/dose_routes.py: frontend dang duoc xay song song can du
lieu that thay cho mock data, CHUA co trong api-contracts.md (endpoint moi,
can Architect duyet truoc khi coi la contract on dinh - ADR-0003).

Dung `require_internal_secret` (cung muc do tin cay voi patient_routes.py
hien nay) - khong loc theo bac si dang dang nhap: bat ky bac si nao cung xem
duoc toan bo benh nhan (khong con RBAC theo doctor_id), tim bang tham so
`search` (khop theo ID hoac ten), cung quy uoc voi patient_routes.py."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, require_role
from backend.db.base import get_db
from backend.db.models import AuditLog, DoctorWatch, DoseEvent, Escalation, Patient
from backend.models.schemas import (
    AuditLogOut,
    DoseDayOut,
    DoseSummaryOut,
    EscalationOut,
    MissedWindowOut,
    PatientWatchOut,
    PatientWatchUpdateRequest,
    ReportingPatientOut,
)
from backend.services.audit import log_action, patient_label
from backend.services.reporting.adherence import compute_adherence_pct

reporting_router = APIRouter()

# Bang audit_log la append-only va co the rat lon theo thoi gian (BR-7.5,
# xem backend/db/models.py::AuditLog) - gioi han so dong tra ve de tranh 1
# request keo ca trieu dong ve FE. Dashboard chi can xem gan day nhat,
# khong phai toan bo lich su.
_AUDIT_LOG_LIMIT = 200

# Lech gio Viet Nam so voi UTC. Dung so co dinh thay vi ZoneInfo("Asia/
# Ho_Chi_Minh") co y: Viet Nam KHONG co gio mua he va khong doi mui gio tu
# 1975, nen mot phep cong don gian la dung tuyet doi o day - doi lai khong
# phai keo them goi `tzdata` (bat buoc tren Windows, la moi truong dev cua du
# an nay) chi de lam mot viec ma so hang lam duoc.
#
# CAN mui gio o day chu khong duoc dung thang UTC: DoseEvent.scheduled_at luu
# UTC, ma mot lieu 20:30 gio Viet Nam la 13:30 UTC CUNG NGAY, con lieu 06:00
# gio Viet Nam la 23:00 UTC NGAY HOM TRUOC - gom nhom theo ngay UTC se day
# lieu buoi sang sang cot cua hom truoc, va bieu do "khung gio hay bo lo" se
# lech han 7 tieng (bo lo buoi toi hien thanh buoi chieu).
_GIO_VN = timedelta(hours=7)

# Ranh gioi 4 khung gio trong ngay (gio Viet Nam). "Toi" om phan con lai
# (18h -> 5h sang hom sau) nen khong nam trong bang nay.
_KHUNG_GIO = (
    ("morning", "Sáng", 5, 11),
    ("noon", "Trưa", 11, 14),
    ("afternoon", "Chiều", 14, 18),
)
_KHUNG_TOI = ("evening", "Tối")

# Chi 3 trang thai nay la "da co ket qua". PENDING/AWAITING_CAREGIVER (chua
# den han hoac dang cho nguoi than xac nhan) va CANCELLED (phac do da dung)
# deu khong noi len dieu gi ve viec benh nhan co uong thuoc hay khong - cung
# nguyen tac voi compute_adherence_pct().
_TRANG_THAI_CO_KET_QUA = ("TAKEN", "DELAYED", "MISSED")

_SO_NGAY_MAC_DINH = 7
_SO_NGAY_TOI_DA = 90


@reporting_router.get(
    "/reporting/patients",
    response_model=list[ReportingPatientOut],
)
def list_reporting_patients(
    search: str | None = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role("doctor", "admin")),
) -> list[ReportingPatientOut]:
    query = select(Patient)
    # KHONG loc theo doctor_id (quyet dinh PM 2026-08-14): bac si nao cung
    # xem duoc toan bo benh nhan de ke don/theo doi; "chi dinh rieng" la bac
    # si tu bam nut "Theo doi" - tu migration 0023, do la DoctorWatch (rieng
    # tung bac si), KHONG con la Patient.doctor_id.
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(Patient.id.ilike(pattern), Patient.full_name.ilike(pattern)))
    rows = db.execute(query.order_by(Patient.full_name)).scalars().all()

    # `watch` tra ve la "CURRENT_USER co dang theo doi benh nhan nay khong"
    # (rieng tung bac si, migration 0023) - admin luon thay watch=False (admin
    # khong co doctor_id, khong co khai niem "theo doi" rieng).
    watched_ids: set[str] = set()
    if current_user.role == "doctor" and current_user.doctor_id:
        watched_ids = set(
            db.execute(
                select(DoctorWatch.patient_id).where(DoctorWatch.doctor_id == current_user.doctor_id)
            ).scalars().all()
        )

    return [
        ReportingPatientOut(
            id=p.id,
            full_name=p.full_name,
            year_of_birth=p.year_of_birth,
            note=p.note,
            gender=p.gender,
            height_cm=p.height_cm,
            weight_kg=p.weight_kg,
            phone=p.phone,
            watch=p.id in watched_ids,
            adherence_pct=compute_adherence_pct(db, p.id),
        )
        for p in rows
    ]


@reporting_router.patch(
    "/reporting/patients/{patient_id}/watch",
    response_model=PatientWatchOut,
)
def update_patient_watch(
    patient_id: str,
    body: PatientWatchUpdateRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role("doctor")),
) -> PatientWatchOut:
    """Tu migration 0023: bat/tat theo doi la RIENG cho CURRENT_USER (bac si
    dang dang nhap), khong con la 1 co dung chung cho ca benh nhan. Chi
    role=doctor moi co doctor_id (dinh danh de ghi DoctorWatch) - admin
    khong con goi duoc endpoint nay (truoc day co the, nhung "admin theo
    doi" khong co y nghia ro rang - khong co dashboard rieng doc no)."""
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Bệnh nhân không tồn tại")

    existing = db.execute(
        select(DoctorWatch).where(
            DoctorWatch.doctor_id == current_user.doctor_id, DoctorWatch.patient_id == patient_id
        )
    ).scalar_one_or_none()

    # Chi ghi nhat ky khi trang thai THUC SU doi - bam lai nut "Theo dõi" khi
    # da theo doi roi la thao tac rong, ghi vao chi lam loang nhat ky.
    if body.watch and existing is None:
        db.add(DoctorWatch(doctor_id=current_user.doctor_id, patient_id=patient_id))
        log_action(db, current_user, "Bật theo dõi bệnh nhân", patient_label(db, patient_id))
        db.commit()
    elif not body.watch and existing is not None:
        db.delete(existing)
        log_action(db, current_user, "Tắt theo dõi bệnh nhân", patient_label(db, patient_id))
        db.commit()

    return PatientWatchOut(id=patient.id, watch=body.watch)


def _benh_nhan_trong_pham_vi(db: Session, current_user: CurrentUser) -> list[str] | None:
    """Danh sach patient_id ma bac si dang dang nhap duoc thong ke.

    Tra None nghia la "khong gioi han" (admin xem toan he thong). Tra list
    rong nghia la bac si chua theo doi ai - KHAC HAN None, nguoi goi phai
    phan biet hai truong hop nay.

    Cung quy tac pham vi voi GET /escalations o duoi: bac si chi thay du lieu
    cua benh nhan minh dang "Theo doi" (DoctorWatch), de trang Tong quan va
    Hop canh bao noi ve cung mot tap benh nhan.
    """
    if current_user.role == "doctor" and current_user.doctor_id:
        return list(
            db.execute(
                select(DoctorWatch.patient_id).where(
                    DoctorWatch.doctor_id == current_user.doctor_id
                )
            ).scalars().all()
        )
    return None


@reporting_router.get("/reporting/dose-summary", response_model=DoseSummaryOut)
def get_dose_summary(
    days: int = Query(default=_SO_NGAY_MAC_DINH, ge=1, le=_SO_NGAY_TOI_DA),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role("doctor", "admin")),
) -> DoseSummaryOut:
    """Gop du lieu cho 2 bieu do o trang "Tổng quan thông tin" cua bac si:
    tinh trang lieu theo tung ngay, va so lieu bo lo theo khung gio.

    Gop 1 endpoint vi ca hai deu quet CUNG mot tap DoseEvent - tach ra thanh
    2 endpoint se doc bang hai lan de ve cung mot man hinh.
    """
    patient_ids = _benh_nhan_trong_pham_vi(db, current_user)

    # Moc dau: 00:00 gio Viet Nam cua ngay dau tien trong khoang, doi nguoc
    # ve UTC de so sanh voi cot scheduled_at.
    bay_gio_vn = datetime.now(UTC) + _GIO_VN
    ngay_dau_vn = (bay_gio_vn - timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    moc_dau_utc = ngay_dau_vn - _GIO_VN

    # Khung ngay LUON du `days` dong ke ca ngay khong co lieu nao - bieu do
    # thieu ngay se lam nguoi doc tuong hom do khong co du lieu, trong khi that
    # ra la khong co lieu nao den han.
    ngay_theo_thu_tu = [
        (ngay_dau_vn + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)
    ]
    dem_theo_ngay = {ngay: {"TAKEN": 0, "DELAYED": 0, "MISSED": 0} for ngay in ngay_theo_thu_tu}
    dem_theo_khung = {key: 0 for key, _, _, _ in _KHUNG_GIO}
    dem_theo_khung[_KHUNG_TOI[0]] = 0

    # patient_ids == [] (bac si chua theo doi ai) thi bo qua truy van luon -
    # `IN ()` rong vua vo nghia vua khien Postgres quet ca bang.
    if patient_ids is None or patient_ids:
        query = select(DoseEvent.scheduled_at, DoseEvent.status).where(
            DoseEvent.scheduled_at >= moc_dau_utc,
            DoseEvent.status.in_(_TRANG_THAI_CO_KET_QUA),
        )
        if patient_ids is not None:
            query = query.where(DoseEvent.patient_id.in_(patient_ids))

        for scheduled_at, status in db.execute(query).all():
            # scheduled_at tu Postgres la timezone-aware; ep ve UTC truoc khi
            # cong lech gio de khong phu thuoc vao mui gio cua may chay app.
            luc_vn = scheduled_at.astimezone(UTC) + _GIO_VN
            ngay = luc_vn.strftime("%Y-%m-%d")
            if ngay in dem_theo_ngay:
                dem_theo_ngay[ngay][status] += 1

            if status == "MISSED":
                gio = luc_vn.hour
                khung = next(
                    (key for key, _, tu, den in _KHUNG_GIO if tu <= gio < den), _KHUNG_TOI[0]
                )
                dem_theo_khung[khung] += 1

    daily = [
        DoseDayOut(
            date=ngay,
            taken=dem_theo_ngay[ngay]["TAKEN"],
            delayed=dem_theo_ngay[ngay]["DELAYED"],
            missed=dem_theo_ngay[ngay]["MISSED"],
            total=sum(dem_theo_ngay[ngay].values()),
        )
        for ngay in ngay_theo_thu_tu
    ]
    missed_by_window = [
        MissedWindowOut(key=key, label=label, missed=dem_theo_khung[key])
        for key, label, _, _ in _KHUNG_GIO
    ] + [MissedWindowOut(key=_KHUNG_TOI[0], label=_KHUNG_TOI[1], missed=dem_theo_khung[_KHUNG_TOI[0]])]

    patient_count = (
        db.query(Patient).count() if patient_ids is None else len(patient_ids)
    )

    return DoseSummaryOut(
        days=days,
        patient_count=patient_count,
        daily=daily,
        missed_by_window=missed_by_window,
    )


@reporting_router.get(
    "/escalations",
    response_model=list[EscalationOut],
)
def list_escalations(
    patient_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role("doctor", "admin")),
) -> list[EscalationOut]:
    query = select(Escalation)
    if patient_id:
        # Xem canh bao cua 1 benh nhan CU THE (vd tab "Tuan thu" trong ho so
        # benh nhan, doctor/patients/page.tsx) - bac si nao cung xem duoc,
        # KHONG loc theo DoctorWatch (khac ban chat voi "Hop canh bao" tong
        # hop o duoi: day la xem ho so 1 nguoi cu the, khong phai feed chung).
        query = query.where(Escalation.patient_id == patient_id)
    elif current_user.role == "doctor" and current_user.doctor_id:
        # "Hop canh bao"/chuong thong bao (frontend/src/app/doctor/alerts,
        # doctor/layout.tsx) - THEM 2026-08-14 (quyet dinh PM, sua hieu lam
        # truoc do voi Web Push): bac si CHI thay canh bao cua benh nhan
        # dang "Theo doi" (DoctorWatch), KHONG phai toan bo benh nhan trong
        # he thong - khac voi "Quan ly benh nhan" (van thay tat ca de ke don).
        watched_patient_ids = db.execute(
            select(DoctorWatch.patient_id).where(DoctorWatch.doctor_id == current_user.doctor_id)
        ).scalars().all()
        if not watched_patient_ids:
            return []
        query = query.where(Escalation.patient_id.in_(watched_patient_ids))
    if status:
        query = query.where(Escalation.status == status)
    query = query.order_by(desc(Escalation.created_at))

    rows = db.execute(query).scalars().all()
    return [
        EscalationOut(
            id=r.id,
            patient_id=r.patient_id,
            dose_event_id=r.dose_event_id,
            severity=r.severity,
            trigger=r.trigger,
            raw_utterance=r.raw_utterance,
            reason=r.reason,
            created_at=r.created_at.isoformat(),
            status=r.status,
            notified=r.notified,
            reminder_count=r.reminder_count,
            last_reminder_at=r.last_reminder_at.isoformat() if r.last_reminder_at else None,
            resolved_at=r.resolved_at.isoformat() if r.resolved_at else None,
            resolved_by=r.resolved_by,
        )
        for r in rows
    ]


@reporting_router.get(
    "/audit-log",
    response_model=list[AuditLogOut],
)
def list_audit_log(
    patient_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role("doctor", "admin")),
) -> list[AuditLogOut]:
    query = select(AuditLog)
    if patient_id:
        query = query.where(AuditLog.patient_id == patient_id)
    query = query.order_by(desc(AuditLog.created_at)).limit(_AUDIT_LOG_LIMIT)

    rows = db.execute(query).scalars().all()
    return [
        AuditLogOut(
            id=r.id,
            patient_id=r.patient_id,
            dose_event_id=r.dose_event_id,
            utterance=r.utterance,
            created_at=r.created_at.isoformat(),
            trace=r.trace,
            final_response=r.final_response,
            total_duration_ms=r.total_duration_ms,
        )
        for r in rows
    ]
