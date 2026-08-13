"""
Quan ly lien ket bac si<->benh nhan<->nguoi than (specs/user-roles.md: 1
benh nhan co 0..n nguoi than, 1 nguoi than co the gan voi nhieu benh nhan,
CHI admin duoc tao/xoa lien ket nay). THEM 2026-08-13.

3 endpoint dung CHUNG 1 duong dan GET /caregiver-links, phan nhanh theo query
param nao duoc truyen (patient_id de bac si xem "nguoi lien he gia dinh" cua
1 benh nhan, caregiver_account_id de chinh nguoi than xem "cac benh nhan
minh dang theo doi") - giong 1 tai nguyen (caregiver_link) nhin tu 2 huong
khac nhau, KHONG phai 2 khai niem rieng, nen gop lai 1 route thay vi tao 2
duong dan khac ten.

CHUA co trong api-contracts.md - endpoint moi, can Architect duyet truoc khi
coi la contract on dinh (ADR-0003), cung tinh trang voi reporting_routes.py."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, require_internal_secret, require_role
from backend.db.base import get_db
from backend.db.models import Account, CaregiverLink, DoseEvent, Escalation, Patient
from backend.models.schemas import (
    CaregiverLinkCreateRequest,
    CaregiverLinkForPatientOut,
    CaregiverLinkOut,
    CaregiverMonitoredPatientOut,
    DayAdherenceStatus,
    OpenEscalationBrief,
)
from backend.services.reporting.adherence import compute_adherence_pct

caregiver_router = APIRouter()

# So ngay lich su hien trong week_history (CaregiverMonitoredPatientOut) -
# tinh ca ngay hom nay, tuc lui 6 ngay ve truoc.
_WEEK_HISTORY_DAYS = 7


@caregiver_router.post(
    "/caregiver-links",
    response_model=CaregiverLinkOut,
    status_code=http_status.HTTP_201_CREATED,
)
def create_caregiver_link(
    body: CaregiverLinkCreateRequest,
    db: Session = Depends(get_db),
    _admin: CurrentUser = Depends(require_role("admin")),
) -> CaregiverLinkOut:
    link = CaregiverLink(
        caregiver_account_id=body.caregiver_account_id,
        patient_id=body.patient_id,
        relationship=body.relationship,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return CaregiverLinkOut(
        id=link.id,
        caregiver_account_id=link.caregiver_account_id,
        patient_id=link.patient_id,
        relationship=link.relationship,
        created_at=link.created_at.isoformat(),
    )


@caregiver_router.delete("/caregiver-links/{link_id}", status_code=http_status.HTTP_204_NO_CONTENT)
def delete_caregiver_link(
    link_id: str,
    db: Session = Depends(get_db),
    _admin: CurrentUser = Depends(require_role("admin")),
) -> None:
    link = db.get(CaregiverLink, link_id)
    if link is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Liên kết không tồn tại")

    db.delete(link)
    db.commit()


@caregiver_router.get("/caregiver-links", dependencies=[Depends(require_internal_secret)])
def list_caregiver_links(
    patient_id: str | None = Query(default=None),
    caregiver_account_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[CaregiverLinkForPatientOut] | list[CaregiverMonitoredPatientOut]:
    """Dung dung 1 trong 2 query param - xem docstring module cho ly do gop
    2 huong nhin vao 1 route. 400 neu ca 2 hoac khong co param nao duoc
    truyen (mo ho khong biet dang xem theo huong nao)."""
    if bool(patient_id) == bool(caregiver_account_id):
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Truyền đúng 1 trong 2: patient_id hoặc caregiver_account_id",
        )

    if patient_id:
        return _list_links_for_patient(db, patient_id)
    return _list_monitored_patients(db, caregiver_account_id)  # type: ignore[arg-type]


def _list_links_for_patient(db: Session, patient_id: str) -> list[CaregiverLinkForPatientOut]:
    rows = db.execute(select(CaregiverLink).where(CaregiverLink.patient_id == patient_id)).scalars().all()
    if not rows:
        return []

    caregiver_ids = {r.caregiver_account_id for r in rows}
    accounts = db.execute(select(Account).where(Account.id.in_(caregiver_ids))).scalars().all()
    name_by_id = {a.id: a.full_name for a in accounts}

    return [
        CaregiverLinkForPatientOut(
            id=r.id,
            caregiver_account_id=r.caregiver_account_id,
            caregiver_name=name_by_id.get(r.caregiver_account_id, r.caregiver_account_id),
            relationship=r.relationship,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]


def _list_monitored_patients(db: Session, caregiver_account_id: str) -> list[CaregiverMonitoredPatientOut]:
    links = db.execute(
        select(CaregiverLink).where(CaregiverLink.caregiver_account_id == caregiver_account_id)
    ).scalars().all()
    if not links:
        return []

    patient_ids = [link.patient_id for link in links]
    patients = db.execute(select(Patient).where(Patient.id.in_(patient_ids))).scalars().all()
    patient_by_id = {p.id: p for p in patients}

    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=_WEEK_HISTORY_DAYS - 1)

    result: list[CaregiverMonitoredPatientOut] = []
    for link in links:
        patient = patient_by_id.get(link.patient_id)
        if patient is None:
            # Lien ket tro toi mot patient_id khong (con) ton tai trong bang
            # patient - bo qua thay vi lam sap ca response (khong co FK that,
            # xem ghi chu tren CaregiverLink trong backend/db/models.py).
            continue

        today_doses = db.execute(
            select(DoseEvent.status).where(
                DoseEvent.patient_id == link.patient_id,
                DoseEvent.scheduled_at >= today_start,
                DoseEvent.scheduled_at < today_start + timedelta(days=1),
            )
        ).scalars().all()

        open_escalation_rows = db.execute(
            select(Escalation)
            .where(Escalation.patient_id == link.patient_id, Escalation.status == "OPEN")
            .order_by(Escalation.created_at.desc())
        ).scalars().all()

        week_doses = db.execute(
            select(DoseEvent.scheduled_at, DoseEvent.status).where(
                DoseEvent.patient_id == link.patient_id,
                DoseEvent.scheduled_at >= week_start,
                DoseEvent.scheduled_at < today_start + timedelta(days=1),
            )
        ).all()

        result.append(
            CaregiverMonitoredPatientOut(
                link_id=link.id,
                patient_id=patient.id,
                full_name=patient.full_name,
                year_of_birth=patient.year_of_birth,
                note=patient.note,
                relationship=link.relationship,
                adherence_pct=compute_adherence_pct(db, link.patient_id, now=now),
                dose_taken_today=sum(1 for status in today_doses if status == "TAKEN"),
                dose_total_today=len(today_doses),
                open_escalations=[
                    OpenEscalationBrief(
                        id=e.id, level=e.severity, title=e.reason, created_at=e.created_at.isoformat()
                    )
                    for e in open_escalation_rows
                ],
                week_history=_build_week_history(week_doses, today_start),
            )
        )

    return result


def _build_week_history(
    week_doses: list, today_start: datetime
) -> list[DayAdherenceStatus]:
    """Gop cac DoseEvent trong 7 ngay gan nhat theo tung ngay, suy ra trang
    thai cua ngay do: co MISSED -> "missed"; khong co MISSED nhung co
    DELAYED -> "late"; con lai (tat ca TAKEN) -> "taken". Ngay khong co lieu
    nao duoc lich (khong co dong nao) thi BO QUA - khong bia ra 1 trang thai
    gia cho ngay khong co du lieu (vd truoc khi phac do bat dau)."""
    statuses_by_day: dict[str, list[str]] = defaultdict(list)
    for scheduled_at, status in week_doses:
        day_key = scheduled_at.astimezone(UTC).date().isoformat()
        statuses_by_day[day_key].append(status)

    history: list[DayAdherenceStatus] = []
    for offset in range(_WEEK_HISTORY_DAYS - 1, -1, -1):
        day = (today_start - timedelta(days=offset)).date()
        day_key = day.isoformat()
        day_statuses = statuses_by_day.get(day_key)
        if not day_statuses:
            continue

        if "MISSED" in day_statuses:
            day_status = "missed"
        elif "DELAYED" in day_statuses:
            day_status = "late"
        elif all(s == "TAKEN" for s in day_statuses):
            day_status = "taken"
        else:
            # Con lieu PENDING/CANCELLED/AWAITING_CAREGIVER chua ket thuc
            # trong ngay - chua du du lieu de ket luan, bo qua ngay nay.
            continue

        history.append(DayAdherenceStatus(date=day_key, status=day_status))

    return history
