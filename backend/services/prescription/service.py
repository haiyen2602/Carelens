"""
Vòng đời phác đồ: `draft → approved → active → completed | stopped | rejected`.

Quy tắc nền, business-rules.md §1:

  BR-1.1  Agent CHỈ hoạt động trên phác đồ đã duyệt. `draft` không sinh liều,
          không nhắc, không chat theo liều.
  BR-1.3  Sửa phác đồ đang chạy chỉ sinh lại liều CHƯA tới hạn.
  BR-1.4  Dừng phác đồ -> mọi liều PENDING thành CANCELLED.
  BR-1.5  Mọi chuyển trạng thái ghi lại actor + thời điểm.

`approve()` là CỬA DUY NHẤT đưa phác đồ sang trạng thái chạy được (ADR-0010).
Không hàm nào khác trong module này set `status` thành `approved`/`active`.

KHÔNG TIN DỮ LIỆU TRÌNH DUYỆT GỬI LÊN. Frontend gửi `drug_id`, backend tra lại
bảng `drug` để lấy `dang_thuoc`/`duong_dung`. Hai trường đó quyết định một liều
có xác minh được bằng ảnh hay không — nhận bừa từ trình duyệt thì chỉ cần sửa
một giá trị trong DevTools là biến thuốc tiêm thành viên nén, và hệ thống sẽ
đòi bệnh nhân chụp ảnh một thứ không thể chụp.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.models import DoseEvent, Patient, Prescription, PrescriptionItem
from backend.services.drug_knowledge import lay_thuoc
from backend.services.prescription.errors import (
    KhongTimThayError,
    TrangThaiKhongHopLeError,
    ViPhamNghiepVuError,
)
from backend.services.scheduling.generator import huy_lieu_chua_toi_han, sinh_dose_event
from backend.services.scheduling.occurrence_generator import generate_prescription_dose_occurrences
from backend.services.scheduling.write_path import (
    activate_prescription_schedule,
    cancel_prescription_future_occurrences,
    stop_prescription_schedule,
    sync_prescription_schedule,
)

logger = logging.getLogger(__name__)

DRAFT = "draft"
ACTIVE = "active"
STOPPED = "stopped"
REJECTED = "rejected"

# Chỉ phác đồ đang ở draft mới duyệt được. Duyệt lại cái đang chạy là 409 chứ
# không phải lỗi im lặng — bác sĩ cần biết mình vừa bấm vào cái đã duyệt rồi.
CHO_DUYET = frozenset({DRAFT})
DANG_CHAY = frozenset({ACTIVE, "approved"})

# Form của bác sĩ chưa có ô "số ngày điều trị" (xem prescribe/page.tsx — form
# chỉ hỏi giờ uống trong MỘT ngày). Đặt mặc định ở đây, có tên rõ ràng, để khi
# form bổ sung trường đó thì xoá đúng một chỗ.
# TODO: xoá khi form có trường số ngày điều trị.
SO_NGAY_MAC_DINH = 7


def _shadow_v2_enabled() -> bool:
    return get_settings().prescription_v2_mode == "shadow"


def _v2_dose_runtime_enabled() -> bool:
    return get_settings().dose_runtime_mode in {"shadow", "v2"}


def _log_v2_shadow(db: Session, operation: str, prescription: Prescription) -> None:
    """Record redacted V2 reconciliation state without logging clinical data."""

    statuses = Counter(
        db.execute(
            select(PrescriptionItem.status).where(PrescriptionItem.prescription_id == prescription.id)
        ).scalars()
    )
    expected_items = len(prescription.items) if isinstance(prescription.items, list) else 0
    actual_items = sum(statuses.values())
    logger.info(
        "prescription_v2_shadow operation=%s prescription_id=%s expected_items=%d actual_items=%d mismatch=%s "
        "sidecar_statuses=%s",
        operation,
        prescription.id,
        expected_items,
        actual_items,
        expected_items != actual_items,
        dict(sorted(statuses.items())),
    )


def _chuan_hoa_item(db: Session, item: dict) -> dict:
    """Một dòng thuốc trong đơn, đã đối chiếu lại với danh mục.

    `drug_id` rỗng (bác sĩ tự gõ một tên không có trong danh mục) vẫn kê được:
    đơn thuốc vẫn hợp lệ, chỉ là liều đó không xác minh được bằng ảnh vì không
    biết dạng bào chế — sẽ rơi về nút bấm xác nhận. Chặn hẳn ở đây thì bác sĩ
    không kê nổi thuốc mới chưa kịp vào danh mục.
    """
    drug_id = str(item.get("drug_id") or "").strip()
    dang_thuoc = str(item.get("dang_thuoc") or "").strip()
    duong_dung = str(item.get("duong_dung") or "").strip()

    if drug_id:
        thuoc = lay_thuoc(db, drug_id)
        if thuoc is None:
            raise ViPhamNghiepVuError(f"Không tìm thấy thuốc {drug_id!r} trong danh mục.", drug_id=drug_id)
        # Danh mục thắng, luôn luôn.
        dang_thuoc, duong_dung = thuoc.dang_thuoc, thuoc.duong_dung
        item = {**item, "ten_thuoc": item.get("ten_thuoc") or thuoc.ten_thuoc}
    elif dang_thuoc:
        logger.info("Thuốc %r kê tay, không có trong danh mục.", item.get("ten_thuoc", "?"))

    return {
        "drug_id": drug_id,
        "ten_thuoc": str(item.get("ten_thuoc") or "").strip(),
        "dang_thuoc": dang_thuoc,
        "duong_dung": duong_dung,
        "ham_luong": str(item.get("ham_luong") or "").strip() or None,
        "lieu_dung": str(item.get("lieu_dung") or "").strip(),
        "thoi_diem_dung": str(item.get("thoi_diem_dung") or "").strip(),
        "so_vien_moi_lan": item.get("so_vien_moi_lan"),
        "gio_nhac": list(item.get("gio_nhac") or []),
        "doses_per_day": item.get("doses_per_day"),
        "has_cycle": bool(item.get("has_cycle")),
        "cycle_on_days": item.get("cycle_on_days"),
        "cycle_off_days": item.get("cycle_off_days"),
        # Khoang ngay rieng cua thuoc nay - None nghia la dung chung khoang
        # ngay cua ca phac do (xem PrescriptionItemIn trong schemas.py).
        "start_date": item.get("start_date") or None,
        "duration_days": item.get("duration_days"),
    }


def tao_phac_do(
    db: Session,
    *,
    patient_id: str,
    doctor_id: str,
    items: list[dict],
    note: str | None = None,
    start_date: str | None = None,
    duration_days: int | None = None,
) -> Prescription:
    """Tạo phác đồ mới. LUÔN ở `draft` — BR-1.1, ADR-0010.

    Không có tham số nào cho phép tạo thẳng ở trạng thái đã duyệt. Muốn chạy
    thì phải gọi `duyet_phac_do()`, và chỗ đó ghi lại ai duyệt lúc nào.
    """
    if not items:
        raise ViPhamNghiepVuError("Đơn thuốc phải có ít nhất một thuốc.")
    if db.get(Patient, patient_id) is None:
        raise KhongTimThayError(f"Không tìm thấy bệnh nhân {patient_id!r}.", patient_id=patient_id)

    try:
        presc = Prescription(
            patient_id=patient_id,
            doctor_id=doctor_id,
            status=DRAFT,
            items=[_chuan_hoa_item(db, item) for item in items],
            start_date=start_date or datetime.now(UTC).date().isoformat(),
            duration_days=duration_days or SO_NGAY_MAC_DINH,
            note=note or None,
        )
        db.add(presc)
        db.flush()
        if _shadow_v2_enabled():
            sync_prescription_schedule(db, presc)
            _log_v2_shadow(db, "create", presc)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Tạo phác đồ cho bệnh nhân %s thất bại, đã hoàn tác.", patient_id)
        raise
    db.refresh(presc)

    logger.info("Bác sĩ %s tạo phác đồ %s cho bệnh nhân %s (draft).", doctor_id, presc.id, patient_id)
    return presc


def lay_phac_do(db: Session, prescription_id: str, *, for_update: bool = False) -> Prescription:
    stmt = select(Prescription).where(Prescription.id == prescription_id)
    if for_update:
        stmt = stmt.with_for_update()
    presc = db.execute(stmt).scalar_one_or_none()
    if presc is None:
        raise KhongTimThayError(f"Không tìm thấy phác đồ {prescription_id!r}.", prescription_id=prescription_id)
    return presc


def liet_ke_phac_do(
    db: Session, *, patient_id: str | None = None, status: str | None = None, gioi_han: int = 100
) -> list[Prescription]:
    """Hàng đợi duyệt = lọc `status=draft`."""
    stmt = select(Prescription)
    if patient_id:
        stmt = stmt.where(Prescription.patient_id == patient_id)
    if status:
        stmt = stmt.where(Prescription.status == status)
    stmt = stmt.order_by(Prescription.created_at.desc()).limit(max(1, min(gioi_han, 500)))
    return list(db.execute(stmt).scalars().all())


def duyet_phac_do(db: Session, prescription_id: str, *, doctor_id: str) -> tuple[Prescription, int]:
    """Duyệt phác đồ và sinh lịch uống. Trả về (phác đồ, số liều đã tạo).

    Cửa duy nhất sang trạng thái chạy được (ADR-0010). Đổi trạng thái và sinh
    liều nằm trong CÙNG một giao dịch: duyệt xong mà lịch không sinh được sẽ để
    lại một phác đồ `active` không có liều nào, và không ai phát hiện cho tới
    khi bệnh nhân thắc mắc sao không thấy nhắc.
    """
    presc = lay_phac_do(db, prescription_id, for_update=True)

    if presc.status in DANG_CHAY:
        raise TrangThaiKhongHopLeError(
            "Phác đồ này đã được duyệt rồi.", prescription_id=prescription_id, status=presc.status
        )
    if presc.status not in CHO_DUYET:
        raise TrangThaiKhongHopLeError(
            f"Không duyệt được phác đồ đang ở trạng thái {presc.status!r}.",
            prescription_id=prescription_id,
            status=presc.status,
        )

    try:
        presc.status = ACTIVE
        presc.approved_by = doctor_id  # BR-1.5
        presc.approved_at = datetime.now(UTC)
        # DB-4E only activates V2 metadata that is fully validated and mapped.
        # It does not generate a V2 dose occurrence.
        if _shadow_v2_enabled():
            # A prescription may have been created while the server was in
            # LEGACY mode. Re-sync before activation so enabling SHADOW never
            # activates a missing or stale sidecar.
            sync_prescription_schedule(db, presc)
            activate_prescription_schedule(db, presc.id)
            if _v2_dose_runtime_enabled():
                generate_prescription_dose_occurrences(db, prescription_id=presc.id)
            _log_v2_shadow(db, "approve", presc)
        so_lieu = sinh_dose_event(db, presc)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Duyệt phác đồ %s thất bại, đã hoàn tác.", prescription_id)
        raise

    db.refresh(presc)
    logger.info("Bác sĩ %s duyệt phác đồ %s, sinh %d liều.", doctor_id, prescription_id, so_lieu)
    return presc, so_lieu


def sua_phac_do(
    db: Session, prescription_id: str, *, doctor_id: str, items: list[dict], note: str | None = None
) -> tuple[Prescription, int]:
    """Sửa thuốc/liều/giờ của một phác đồ `draft` hoặc `active` (BR-1.3).

    Sửa trực tiếp (ghi đè `items`), KHÔNG tạo bản ghi mới - khác `duyet_phac_do`
    (ADR-0010 chỉ áp cho việc CHUYỂN sang trạng thái chạy, không áp cho việc
    sửa thuốc trên một phác đồ bác sĩ phụ trách đã tự duyệt).

    Nếu đang `active`: sinh lại CHỈ các `dose_event` CHƯA TỚI HẠN (idempotent,
    xem sinh_dose_event/generator.py) - liều đã đóng (TAKEN/MISSED/...) giữ
    nguyên vì đó là lịch sử y tế, sửa phác đồ không được viết lại quá khứ.
    Nếu đang `draft`: chưa có liều nào để sinh (sinh lúc duyệt), trả 0.
    """
    if not items:
        raise ViPhamNghiepVuError("Đơn thuốc phải có ít nhất một thuốc.")

    presc = lay_phac_do(db, prescription_id, for_update=True)
    if presc.status not in (DRAFT, *DANG_CHAY):
        raise TrangThaiKhongHopLeError(
            f"Không sửa được phác đồ đang ở trạng thái {presc.status!r}.",
            prescription_id=prescription_id,
            status=presc.status,
        )

    try:
        event_at = datetime.now(UTC)
        if _shadow_v2_enabled() and presc.status in DANG_CHAY:
            cancel_prescription_future_occurrences(
                db,
                prescription_id=presc.id,
                event_at=event_at,
                source="PRESCRIPTION_EDIT",
                actor_type="DOCTOR",
                actor_id=doctor_id,
            )
        presc.items = [_chuan_hoa_item(db, item) for item in items]
        if note is not None:
            presc.note = note or None
        if _shadow_v2_enabled():
            sync_prescription_schedule(db, presc)
            _log_v2_shadow(db, "edit", presc)
        if presc.status in DANG_CHAY and _shadow_v2_enabled():
            activate_prescription_schedule(db, presc.id)
            if _v2_dose_runtime_enabled():
                generate_prescription_dose_occurrences(db, prescription_id=presc.id, now=event_at)
        so_lieu = sinh_dose_event(db, presc) if presc.status in DANG_CHAY else 0
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Sửa phác đồ %s thất bại, đã hoàn tác.", prescription_id)
        raise

    db.refresh(presc)
    logger.info("Bác sĩ %s sửa phác đồ %s, sinh lại %d liều.", doctor_id, prescription_id, so_lieu)
    return presc, so_lieu


def tu_choi_phac_do(db: Session, prescription_id: str, *, doctor_id: str) -> Prescription:
    """Từ chối phác đồ ở hàng đợi. Không sinh liều nào."""
    presc = lay_phac_do(db, prescription_id, for_update=True)
    if presc.status not in CHO_DUYET:
        raise TrangThaiKhongHopLeError(
            f"Chỉ từ chối được phác đồ đang chờ duyệt, phác đồ này đang {presc.status!r}.",
            prescription_id=prescription_id,
            status=presc.status,
        )

    presc.status = REJECTED
    presc.approved_by = doctor_id  # ai quyết định, dù là quyết định từ chối
    presc.approved_at = datetime.now(UTC)
    db.commit()
    db.refresh(presc)

    logger.info("Bác sĩ %s từ chối phác đồ %s.", doctor_id, prescription_id)
    return presc


def dung_phac_do(db: Session, prescription_id: str, *, doctor_id: str) -> tuple[Prescription, int]:
    """Dừng phác đồ đang chạy. Mọi liều chưa tới hạn thành CANCELLED (BR-1.4)."""
    presc = lay_phac_do(db, prescription_id, for_update=True)
    if presc.status not in DANG_CHAY:
        raise TrangThaiKhongHopLeError(
            f"Chỉ dừng được phác đồ đang chạy, phác đồ này đang {presc.status!r}.",
            prescription_id=prescription_id,
            status=presc.status,
        )

    try:
        so_huy = huy_lieu_chua_toi_han(db, prescription_id)
        if _shadow_v2_enabled():
            stop_prescription_schedule(
                db,
                prescription_id,
                event_at=datetime.now(UTC),
                actor_type="DOCTOR",
                actor_id=doctor_id,
            )
            _log_v2_shadow(db, "stop", presc)
        presc.status = STOPPED
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(presc)
    logger.info("Bác sĩ %s dừng phác đồ %s, huỷ %d liều.", doctor_id, prescription_id, so_huy)
    return presc, so_huy


def dem_lieu(db: Session, prescription_id: str) -> int:
    return len(
        db.execute(select(DoseEvent.id).where(DoseEvent.prescription_id == prescription_id)).scalars().all()
    )


__all__ = [
    "ACTIVE",
    "DRAFT",
    "REJECTED",
    "SO_NGAY_MAC_DINH",
    "STOPPED",
    "dem_lieu",
    "dung_phac_do",
    "duyet_phac_do",
    "lay_phac_do",
    "liet_ke_phac_do",
    "tao_phac_do",
    "tu_choi_phac_do",
]
