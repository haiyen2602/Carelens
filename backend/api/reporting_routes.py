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

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, get_current_user, require_role
from backend.db.base import get_db
from backend.db.models import AuditLog, DoctorWatch, Escalation, Patient
from backend.models.schemas import (
    AuditLogOut,
    EscalationOut,
    PatientWatchOut,
    PatientWatchUpdateRequest,
    ReportingPatientOut,
)
from backend.services.reporting.adherence import compute_adherence_pct

reporting_router = APIRouter()

# Bang audit_log la append-only va co the rat lon theo thoi gian (BR-7.5,
# xem backend/db/models.py::AuditLog) - gioi han so dong tra ve de tranh 1
# request keo ca trieu dong ve FE. Dashboard chi can xem gan day nhat,
# khong phai toan bo lich su.
_AUDIT_LOG_LIMIT = 200


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

    if body.watch and existing is None:
        db.add(DoctorWatch(doctor_id=current_user.doctor_id, patient_id=patient_id))
        db.commit()
    elif not body.watch and existing is not None:
        db.delete(existing)
        db.commit()

    return PatientWatchOut(id=patient.id, watch=body.watch)


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
