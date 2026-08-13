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

from backend.api.security import require_internal_secret
from backend.db.base import get_db
from backend.db.models import AuditLog, Escalation, Patient
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
    dependencies=[Depends(require_internal_secret)],
)
def list_reporting_patients(
    search: str | None = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
) -> list[ReportingPatientOut]:
    query = select(Patient)
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(Patient.id.ilike(pattern), Patient.full_name.ilike(pattern)))
    rows = db.execute(query.order_by(Patient.full_name)).scalars().all()
    return [
        ReportingPatientOut(
            id=p.id,
            full_name=p.full_name,
            year_of_birth=p.year_of_birth,
            note=p.note,
            gender=p.gender,
            height_cm=p.height_cm,
            weight_kg=p.weight_kg,
            watch=p.watch,
            adherence_pct=compute_adherence_pct(db, p.id),
        )
        for p in rows
    ]


@reporting_router.patch(
    "/reporting/patients/{patient_id}/watch",
    response_model=PatientWatchOut,
    dependencies=[Depends(require_internal_secret)],
)
def update_patient_watch(
    patient_id: str, body: PatientWatchUpdateRequest, db: Session = Depends(get_db)
) -> PatientWatchOut:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Bệnh nhân không tồn tại")

    patient.watch = body.watch
    db.commit()
    return PatientWatchOut(id=patient.id, watch=patient.watch)


@reporting_router.get(
    "/escalations",
    response_model=list[EscalationOut],
    dependencies=[Depends(require_internal_secret)],
)
def list_escalations(
    patient_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[EscalationOut]:
    query = select(Escalation)
    if patient_id:
        query = query.where(Escalation.patient_id == patient_id)
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
    dependencies=[Depends(require_internal_secret)],
)
def list_audit_log(
    patient_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
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
