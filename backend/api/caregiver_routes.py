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

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, get_current_user, require_internal_secret, require_role
from backend.db.base import get_db
from backend.db.models import Account, CaregiverLink, DoseEvent, Escalation, Patient
from backend.models.schemas import (
    CaregiverInviteCreateRequest,
    CaregiverLinkCreateRequest,
    CaregiverLinkForPatientOut,
    CaregiverLinkOut,
    CaregiverMonitoredPatientOut,
    DayAdherenceStatus,
    OpenEscalationBrief,
    PendingInviteOut,
)
from backend.services.escalation import friendly_escalation_title
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
    """Admin tao thang, KHONG can nguoi duoc theo doi dong y - admin da xac
    nhan quan he ngoai doi truoc khi tao (BR ngam dinh cua man hinh
    /admin/links), khac han POST /caregiver-links/invites ben duoi (tu benh
    nhan, can nguoi kia chap nhan)."""
    link = CaregiverLink(
        caregiver_account_id=body.caregiver_account_id,
        patient_id=body.patient_id,
        relationship=body.relationship,
        status="accepted",
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
        status=link.status,
    )


@caregiver_router.post(
    "/caregiver-links/invites",
    response_model=CaregiverLinkOut,
    status_code=http_status.HTTP_201_CREATED,
)
def create_caregiver_invite(
    body: CaregiverInviteCreateRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> CaregiverLinkOut:
    """Benh nhan dang dang nhap tu moi 1 benh nhan khac (`body.patient_id`)
    de theo doi - KHONG can quyen admin, nhung can that su dang nhap (JWT)
    vi `caregiver_account_id` lay tu chinh nguoi goi, khong tin body. Bat
    dau "pending" - chi co hieu luc (xuat hien o GET ?caregiver_account_id=)
    sau khi nguoi duoc theo doi tu chap nhan qua POST .../accept."""
    if db.get(Patient, body.patient_id) is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Không tìm thấy bệnh nhân")
    if current_user.patient_id == body.patient_id:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Không thể tự mời chính mình")

    link = CaregiverLink(
        caregiver_account_id=current_user.id,
        patient_id=body.patient_id,
        relationship=body.relationship,
        status="pending",
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
        status=link.status,
    )


@caregiver_router.get("/caregiver-links/pending", response_model=list[PendingInviteOut])
def list_pending_invites(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[PendingInviteOut]:
    """Loi moi dang cho CHINH nguoi dang dang nhap chap nhan (ho la nguoi SE
    DUOC theo doi) - luon doc theo `current_user.patient_id`, khong nhan
    patient_id tu query, cung ly do voi get_current_patient_id() o security.py
    (khong cho doc ho loi moi cua nguoi khac)."""
    if not current_user.patient_id:
        return []

    rows = db.execute(
        select(CaregiverLink).where(
            CaregiverLink.patient_id == current_user.patient_id,
            CaregiverLink.status == "pending",
        )
    ).scalars().all()
    if not rows:
        return []

    inviter_ids = {r.caregiver_account_id for r in rows}
    accounts = db.execute(select(Account).where(Account.id.in_(inviter_ids))).scalars().all()
    name_by_id = {a.id: a.full_name for a in accounts}

    return [
        PendingInviteOut(
            id=r.id,
            caregiver_account_id=r.caregiver_account_id,
            inviter_name=name_by_id.get(r.caregiver_account_id, r.caregiver_account_id),
            relationship=r.relationship,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]


@caregiver_router.post("/caregiver-links/{link_id}/accept", response_model=CaregiverLinkOut)
def accept_caregiver_invite(
    link_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> CaregiverLinkOut:
    """Chap nhan loi moi + tu dong tao chieu NGUOC LAI (nguoi vua chap nhan
    cung theo doi duoc lai nguoi da moi) - "nguoi than" trong app nay la quan
    he 2 chieu tu nhien (gia dinh theo doi lan nhau), khac han mo hinh
    bac si<->benh nhan von 1 chieu. Chi tao duoc chieu nguoc neu nguoi moi
    CUNG la 1 tai khoan benh nhan that (co Account.patient_id) - tai khoan
    role=caregiver/doctor/admin tu moi (qua /admin/links) khong co danh
    tinh benh nhan de duoc theo doi lai."""
    link = db.get(CaregiverLink, link_id)
    if link is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Lời mời không tồn tại")
    if link.patient_id != current_user.patient_id:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Không có quyền chấp nhận lời mời này")
    if link.status != "pending":
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail="Lời mời này đã được xử lý")

    link.status = "accepted"

    inviter = db.get(Account, link.caregiver_account_id)
    if inviter is not None and inviter.patient_id and current_user.patient_id:
        reverse = (
            db.query(CaregiverLink)
            .filter(
                CaregiverLink.caregiver_account_id == current_user.id,
                CaregiverLink.patient_id == inviter.patient_id,
            )
            .first()
        )
        if reverse is None:
            # Nhan "Nguoi than" chung chung - khong doan duoc quan he NGUOC
            # (vd "con gai" -> "me") tu 1 chuoi tu do nguoi dung go.
            db.add(
                CaregiverLink(
                    caregiver_account_id=current_user.id,
                    patient_id=inviter.patient_id,
                    relationship="Người thân",
                    status="accepted",
                )
            )
        elif reverse.status == "pending":
            # Ca 2 nguoi lo moi nhau cung luc (2 loi moi rieng) - chap nhan 1
            # ben thi coi nhu ben kia cung duoc dong y luon, khong bat nguoi
            # dung bam chap nhan lan thu 2 cho 1 quan he ho vua xac nhan roi.
            reverse.status = "accepted"

    db.commit()
    db.refresh(link)
    return CaregiverLinkOut(
        id=link.id,
        caregiver_account_id=link.caregiver_account_id,
        patient_id=link.patient_id,
        relationship=link.relationship,
        created_at=link.created_at.isoformat(),
        status=link.status,
    )


@caregiver_router.delete(
    "/caregiver-links/{link_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    response_model=None,
    response_class=Response,
)
def delete_caregiver_link(
    link_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Admin: go bat ky lien ket nao (quan tri). Ngoai admin, chi 2 phia CUA
    CHINH lien ket do duoc dong: nguoi duoc theo doi (tu choi loi moi / rut
    quyen xem) hoac chinh nguoi gui loi moi (huy loi moi / thoi theo doi) -
    khong ai khac duoc dong lien ket cua 2 nguoi kia."""
    link = db.get(CaregiverLink, link_id)
    if link is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Liên kết không tồn tại")

    la_admin = current_user.role == "admin"
    la_nguoi_duoc_theo_doi = current_user.patient_id == link.patient_id
    la_nguoi_gui_loi_moi = current_user.id == link.caregiver_account_id
    if not (la_admin or la_nguoi_duoc_theo_doi or la_nguoi_gui_loi_moi):
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Không có quyền gỡ liên kết này")

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
            status=r.status,
        )
        for r in rows
    ]


def _list_monitored_patients(db: Session, caregiver_account_id: str) -> list[CaregiverMonitoredPatientOut]:
    # Chi lien ket DA CHAP NHAN - loi moi con "pending" khong duoc coi la
    # dang theo doi that (xem POST /caregiver-links/invites), tranh benh
    # nhan chua dong y bi lo du lieu qua man hinh nay.
    links = db.execute(
        select(CaregiverLink).where(
            CaregiverLink.caregiver_account_id == caregiver_account_id,
            CaregiverLink.status == "accepted",
        )
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
            .where(
                Escalation.patient_id == link.patient_id,
                Escalation.status == "OPEN",
                # trigger=photo_mismatch (ADR-0011) da hien rieng qua lieu
                # AWAITING_CAREGIVER o tab "Duyet uong thuoc"
                # (frontend/src/app/patient/family/[id]/page.tsx) - loai
                # khoi day de tranh 1 su viec hien 2 noi (vua "Canh bao" vua
                # "Duyet uong thuoc") va bi dem trung trong badge "X viec can
                # xem" (demSoCanhBao() o frontend/src/app/patient/family/page.tsx).
                Escalation.trigger != "photo_mismatch",
            )
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
                        id=e.id,
                        level=e.severity,
                        # SUA 2026-08-14: KHONG con dung `e.reason` truc tiep -
                        # do la chuoi ky thuat cho audit/bac si (vd "SEVERITY=
                        # Trung bình tu classification='SIDE_EFFECT' (BR-3.1-
                        # 3.6)"), khong phai cho nguoi than doc. `title` la
                        # tieu de rieng, ngan gon, xem friendly_escalation_title().
                        title=friendly_escalation_title(e.trigger, e.severity),
                        created_at=e.created_at.isoformat(),
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
