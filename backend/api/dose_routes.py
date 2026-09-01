"""
Danh sách liều thuốc trong ngày — cho trang bệnh nhân biết liều nào đang chờ
và cần thuốc gì để chụp ảnh xác nhận.

CHƯA CÓ TRONG api-contracts.md ở dạng đầy đủ (§3 có `reminder_level` và
`evidence`, hai trường không có cột tương ứng trong `dose_event` hiện tại —
`reminder_level` do escalation_reminder theo dõi trên bảng `escalation`, không
phải `dose_event`). `DoseSummary` chỉ trả đủ cho nhu cầu hiện tại; cần Architect
duyệt trước khi coi là ổn định (ADR-0003).

Chỉ ĐỌC. Không lọc theo bác sĩ/quan hệ liên kết — chưa có auth-api để biết ai
đang gọi (cùng giới hạn với patient_routes.py/prescription_routes.py).
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, get_current_user, require_internal_secret
from backend.config import get_settings
from backend.db.base import get_db
from backend.db.models import CaregiverLink, DoseEvent, Patient, PhotoVerification
from backend.models.schemas import DoseStatusUpdateRequest, DoseSummary
from backend.services import reward_catalog, reward_ledger
from backend.services.dose_lifecycle import chot_nhan_xac_nhan
from backend.services.drug_images import (
    drug_image_presentation,
    get_active_drug_product_ids_for_legacy_ids,
    get_primary_drug_images,
)
from backend.services.prescription.errors import VmecError
from backend.services.scheduling.runtime_adapter import (
    DoseRuntimeGroup,
    get_v2_dose_group,
    list_v2_dose_groups,
    transition_v2_dose_group,
)

dose_router = APIRouter()


@dose_router.get(
    "/doses",
    response_model=list[DoseSummary],
    dependencies=[Depends(require_internal_secret)],
)
def list_doses(
    patient_id: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
) -> list[DoseSummary]:
    if get_settings().dose_runtime_mode == "v2":
        return [_v2_dose_summary(group) for group in list_v2_dose_groups(db, patient_id=patient_id)]
    rows = (
        db.execute(select(DoseEvent).where(DoseEvent.patient_id == patient_id).order_by(DoseEvent.scheduled_at))
        .scalars()
        .all()
    )
    enriched_items = _legacy_expected_items_with_images(db, rows)
    co_anh = _dose_ids_co_anh(db, [row.id for row in rows])
    return [
        _dose_summary(row, expected_items=enriched_items[row.id], has_photo=row.id in co_anh)
        for row in rows
    ]


def _dose_ids_co_anh(db: Session, dose_ids: list[str]) -> set[str]:
    """Tap lieu da tung duoc xac nhan bang anh VA anh do van con.

    MOT truy van cho ca danh sach, khong phai mot truy van moi lieu. Dung
    DISTINCT thay vi JOIN vao chinh cau lay lieu: mot lieu co toi 3 lan gui
    anh (ADR-0011) nen JOIN 1-nhieu se nhan doi dong lieu tra ve.

    Bam theo `image_path IS NOT NULL` chu khong phai "co dong photo_verification
    nao khong": photo_cleanup.py xoa file het han va dat cot nay ve None nhung
    GIU dong lam audit trail, nen dem dong se bao "co anh" cho lieu bam vao
    khong con gi de xem.
    """
    if not dose_ids:
        return set()
    return set(
        db.execute(
            select(PhotoVerification.dose_event_id)
            .where(
                PhotoVerification.dose_event_id.in_(dose_ids),
                PhotoVerification.image_path.is_not(None),
            )
            .distinct()
        )
        .scalars()
        .all()
    )


def _dose_summary(
    r: DoseEvent,
    *,
    points_awarded: int = 0,
    expected_items: list[dict] | None = None,
    has_photo: bool = False,
) -> DoseSummary:
    return DoseSummary(
        id=r.id,
        prescription_id=r.prescription_id,
        scheduled_at=r.scheduled_at.isoformat(),
        window_start=r.window_start.isoformat(),
        window_end=r.window_end.isoformat(),
        status=r.status,
        expected_items=r.expected_items if expected_items is None else expected_items,
        # >0 chi khi PATCH nay VUA cong diem (xem _thuong_diem_neu_uong_du
        # ben duoi) - GET /doses (danh sach) khong truyen tham so nay nen
        # luon la 0, dung nhu y muon (khong phai "tong diem cua lieu").
        points_awarded=points_awarded,
        has_photo=has_photo,
    )


def _legacy_expected_items_with_images(db: Session, doses: list[DoseEvent]) -> dict[str, list[dict]]:
    """Add presentation-safe images with two batched queries, never name matching."""

    raw_items = [item for dose in doses for item in dose.expected_items if isinstance(item, dict)]
    product_ids = {value for item in raw_items if isinstance(value := item.get("drug_product_id"), str) and value}
    legacy_ids = {
        value
        for item in raw_items
        if not item.get("drug_product_id") and isinstance(value := item.get("drug_id"), str) and value
    }
    legacy_products = get_active_drug_product_ids_for_legacy_ids(db, legacy_ids)
    images = get_primary_drug_images(db, (*product_ids, *legacy_products.values()))
    enriched: dict[str, list[dict]] = {}
    for dose in doses:
        items: list[dict] = []
        for raw in dose.expected_items:
            if not isinstance(raw, dict):
                continue
            item = dict(raw)
            raw_product_id = item.get("drug_product_id")
            product_id = raw_product_id if isinstance(raw_product_id, str) and raw_product_id else None
            if product_id is None:
                legacy_id = item.get("drug_id")
                product_id = legacy_products.get(legacy_id) if isinstance(legacy_id, str) else None
            lookup = images.get(product_id) if product_id else None
            display_name = item.get("ten_thuoc") if isinstance(item.get("ten_thuoc"), str) else ""
            presentation = drug_image_presentation(lookup, display_name=display_name)
            item["drug_product_id"] = product_id
            item["image"] = {
                "status": presentation.status,
                "url": presentation.url,
                "alt": presentation.alt,
                "view_type": presentation.view_type,
            }
            items.append(item)
        enriched[dose.id] = items
    return enriched


def _v2_dose_summary(group: DoseRuntimeGroup) -> DoseSummary:
    """`has_photo` giu mac dinh False o nhanh v2 - CO Y, khong phai quen.
    photo_verification.dose_event_id tro toi bang `dose_event` (legacy), con
    o che do v2 lieu nam ben `dose_occurrence` nen khong co duong noi nao de
    tra loi cau hoi nay. Khi nhom bat dose_runtime_mode=v2 that: phai noi
    photo_verification sang dose_occurrence TRUOC, roi moi dien truong nay -
    cung ly do va cung khuon voi hook diem thuong o _update_v2_dose_status().
    """
    return DoseSummary(
        id=group.id,
        prescription_id=group.prescription_id,
        scheduled_at=group.scheduled_at.isoformat(),
        window_start=group.window_start.isoformat(),
        window_end=group.window_end.isoformat(),
        status=group.status,
        expected_items=group.expected_items,
    )


@dose_router.patch("/doses/{dose_id}", response_model=DoseSummary)
def update_dose_status(
    dose_id: str,
    body: DoseStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> DoseSummary:
    """Benh nhan/nguoi than/bac si tu cap nhat trang thai 1 lieu (vd tu bao
    "da uong" khong qua chatbot, hoac nguoi than duyet 1 lieu AWAITING_CAREGIVER
    sau khi xem anh - patient/family/[id]/page.tsx). Phan quyen (KHONG dung
    require_internal_secret - can biet DUNG ai dang goi de kiem tra quan he,
    xem cac nhanh ben duoi):
      - Lieu CUA CHINH MINH (dose_event.patient_id == current_user.patient_id):
        luon sua duoc, bat ke role - ap dung ca cho tai khoan role=patient
        dang tu bao trang thai lieu cua ho.
      - role=caregiver HOAC role=patient dang theo doi nguoi khac (1 benh
        nhan co the dong thoi la nguoi than cua benh nhan khac, xem ghi chu
        MonitoredRelative trong frontend/src/lib/proto-store.tsx): sua duoc
        lieu cua benh nhan co CaregiverLink DA CHAP NHAN (status=accepted)
        toi chinh tai khoan dang goi - loi moi con "pending" KHONG cho quyen
        gi (xem POST /caregiver-links/invites).
      - role=doctor: sua duoc lieu cua BAT KY benh nhan nao (khong con rang
        buoc theo patient.doctor_id - bac si quan ly toan bo benh nhan qua
        tim kiem theo ID, xem patient_routes.py).
    404 neu dose_event khong ton tai (kiem tra TRUOC 403 - khong lo thong tin
    "co ton tai nhung ban khong co quyen" cho lieu khong ton tai)."""
    if get_settings().dose_runtime_mode == "v2":
        return _update_v2_dose_status(dose_id, body, db, current_user)

    dose = db.get(DoseEvent, dose_id)
    if dose is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Liều thuốc không tồn tại")

    authorized = current_user.patient_id == dose.patient_id
    if not authorized and current_user.role == "doctor":
        authorized = db.get(Patient, dose.patient_id) is not None
    if not authorized:
        link = (
            db.query(CaregiverLink)
            .filter(
                CaregiverLink.caregiver_account_id == current_user.id,
                CaregiverLink.patient_id == dose.patient_id,
                CaregiverLink.status == "accepted",
            )
            .first()
        )
        authorized = link is not None

    if not authorized:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Không có quyền sửa liều này")

    # BACKEND chot nhan TAKEN/DELAYED, KHONG tin `body.status`. Truoc
    # 2026-08-31 dong nay la `dose.status = body.status` gan mu, ma frontend
    # luon gui cung mot chuoi "TAKEN" (patient/page.tsx::xacNhanKhongAnh) -
    # nen khong duong tu khai nao sinh ra DELAYED va man Lich su luon bao
    # "0 lan xac nhan muon" du khong ai dung gio. Duong chup anh
    # (photo_verification/verifier.py) da lam dung tu truoc; gio hai duong
    # dung chung mot ham.
    #
    # Chi dien giai lai nhan "da uong". Cac nhan khac la Y DINH RO RANG cua
    # nguoi bam (benh nhan chon "bo qua lieu nay" = MISSED, nguoi than huy =
    # CANCELLED) nen duoc ton trong nguyen ven.
    trang_thai_moi = (
        chot_nhan_xac_nhan(dose.window_end, datetime.now(UTC))
        if body.status == "TAKEN"
        else body.status
    )
    # Chup lai TRUOC khi gan trang thai moi - muc diem phu thuoc vao cach lieu
    # nay duoc xac nhan, ma tin hieu duy nhat con lai la trang thai CU.
    ty_le = _xac_dinh_ty_le_thuong(
        previous_status=dose.status,
        is_self_report=current_user.patient_id == dose.patient_id,
        la_muon=trang_thai_moi == "DELAYED",
    )
    dose.status = trang_thai_moi
    diem = _thuong_diem_neu_uong_du(
        db,
        dose_event_id=dose.id,
        patient_id=dose.patient_id,
        scheduled_at=dose.scheduled_at,
        pct=ty_le,
    )
    db.commit()
    db.refresh(dose)
    return _dose_summary(
        dose,
        points_awarded=diem,
        expected_items=_legacy_expected_items_with_images(db, [dose])[dose.id],
        has_photo=dose.id in _dose_ids_co_anh(db, [dose.id]),
    )


def _xac_dinh_ty_le_thuong(*, previous_status: str, is_self_report: bool, la_muon: bool = False) -> int:
    """PHAN TRAM diem GIU LAI, theo do tin cay cua cach xac nhan lieu nay
    (yeu cau nhom truong 2026-08-28). Xem reward_catalog cho tung muc.

    Chi suy ra tu TRANG THAI CU + ai dang goi, vi DoseEvent khong luu lai
    "lieu nay da duoc xac nhan bang cach nao":
      - AWAITING_CAREGIVER: chi co MOT duong dan toi day, la anh khong khop
        sau 3 lan (verifier.py), va tu 2026-08-28 chi khi benh nhan CO nguoi
        than - khong con phai kiem tra CaregiverLink lai o day nua.
      - PENDING + chinh benh nhan bam: tu bao da uong, khong qua anh.
      - Con lai (nguoi than/bac si tu sua ho ho so): giu nguyen 100%, khong
        phai loi tu khai cua benh nhan nen khong tru.
    """
    if previous_status == "AWAITING_CAREGIVER":
        pct = reward_catalog.PCT_CAREGIVER_APPROVED_AFTER_PHOTO_FAIL
    elif previous_status == "PENDING" and is_self_report:
        pct = reward_catalog.PCT_SELF_REPORT_NO_PHOTO
    else:
        pct = 100
    if la_muon:
        # Hai chieu DOC LAP nen NHAN voi nhau: muc o tren do do TIN CAY cua
        # bang chung, muc nay do THOI DIEM. Vd tu khai (50%) + muon (50%) =
        # 25%. Buoc phai gop thanh MOT ty le vi bang tru diem idempotent theo
        # dose_event_id - moi lieu chi ghi duoc dung mot dong phat
        # (reward_ledger::apply_confirmation_method_penalty).
        pct = round(pct * reward_catalog.PCT_LATE_CONFIRMATION / 100)
    return pct


def _thuong_diem_neu_uong_du(
    db: Session,
    *,
    dose_event_id: str,
    patient_id: str,
    scheduled_at: datetime,
    pct: int = 100,
) -> int:
    """Cong diem thuong khi benh nhan da uong DU thuoc cua ngay (BUILD-reward).

    Goi sau moi lan cap nhat trang thai, KHONG chi khi status=TAKEN: lieu
    cuoi cung trong ngay co the duoc chot qua mot duong khac, va ham ben
    duoi tu kiem tra dieu kien roi bo qua neu chua du - goi thua khong ton
    gi ngoai mot cau SELECT.

    `db.flush()` la BAT BUOC: SessionLocal dat autoflush=False
    (backend/db/base.py), nen thay doi `dose.status` o tren van con nam
    trong bo nho phien - khong flush thi cau SELECT dem lieu trong ngay se
    doc ra trang thai CU va khong bao gio thay du dieu kien.

    Diem tinh theo NGAY CUA LIEU (gio Viet Nam), khong phai ngay hien tai:
    benh nhan xac nhan lieu 23:50 hom truoc luc 00:10 hom sau van phai duoc
    tinh cho dung ngay cua lieu do.

    Tra ve so diem VUA cong (0 neu khong co) de nguoi goi dua vao response,
    benh nhan thay ngay "+N diem" ma khong phai mo trang Diem thuong."""
    db.flush()
    ngay_cua_lieu = reward_ledger.ngay_vn(scheduled_at)
    goc = reward_ledger.award_dose_on_time(db, patient_id, ngay_cua_lieu)
    if pct >= 100:
        return goc
    tru = reward_ledger.apply_confirmation_method_penalty(
        db,
        patient_id=patient_id,
        dose_event_id=dose_event_id,
        occurred_on=ngay_cua_lieu,
        pct=pct,
    )
    return goc - tru


def _update_v2_dose_status(
    dose_id: str, body: DoseStatusUpdateRequest, db: Session, current_user: CurrentUser
) -> DoseSummary:
    """Authorize and transition a grouped V2 dose through the scheduling boundary."""

    try:
        group = get_v2_dose_group(db, dose_group_id=dose_id)
    except VmecError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.to_contract()["error"]) from exc

    authorized = current_user.patient_id == group.patient_id
    if not authorized and current_user.role == "doctor":
        authorized = db.get(Patient, group.patient_id) is not None
    if not authorized:
        link = (
            db.query(CaregiverLink)
            .filter(
                CaregiverLink.caregiver_account_id == current_user.id,
                CaregiverLink.patient_id == group.patient_id,
                CaregiverLink.status == "accepted",
            )
            .first()
        )
        authorized = link is not None
    if not authorized:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Không có quyền sửa liều này")

    try:
        updated = transition_v2_dose_group(
            db,
            dose_group_id=dose_id,
            target_status=body.status,
            event_at=datetime.now(UTC),
            source="PATIENT_DOSE_API",
            actor_type=current_user.role.upper(),
            actor_id=current_user.id,
        )
        # CHUA cong diem thuong o nhanh v2 - CO Y, khong phai quen.
        # reward_ledger.da_uong_du_thuoc_trong_ngay() truy van bang
        # `dose_event` (legacy); o che do v2 lieu nam ben `dose_occurrence`
        # nen goi award_dose_on_time() o day se luon thay "ngay khong co
        # lieu nao" va tra ve False - mot hook nhin thi tuong da xu ly ma
        # thuc te khong bao gio cong duoc diem, con te hon la khong co.
        # Khi nhom bat dose_runtime_mode=v2 that: phai sua ledger doc
        # ca dose_occurrence TRUOC, roi moi gan hook vao day.
        db.commit()
    except VmecError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.http_status, detail=exc.to_contract()["error"]) from exc
    return _v2_dose_summary(updated)
