"""
Sinh `dose_event` từ một phác đồ đã duyệt.

Hai quy tắc quyết định toàn bộ thiết kế ở đây:

GỘP THEO GIỜ. Ba thuốc cùng uống 08:00 sinh ra MỘT `dose_event` với
`expected_items` ba phần tử, không phải ba `dose_event`. Bệnh nhân bày cả nắm
thuốc ra rồi chụp một ảnh — tách ra là bắt người ta chụp ba lần cho cùng một
nắm, và tầng đối chiếu sẽ so từng thuốc với cả nắm rồi báo thừa.

IDEMPOTENT (BR-2.3). Bấm Duyệt hai lần không được sinh hai bộ lịch. Ở đây làm
bằng cách xoá các liều CHƯA TỚI HẠN của phác đồ rồi sinh lại — liều đã đóng
(TAKEN/MISSED/DELAYED) giữ nguyên vì đó là lịch sử y tế, sửa phác đồ không được
viết lại quá khứ (BR-1.3).

`expected_items` mang theo `dang_thuoc` và `duong_dung` — hai trường không có
trong bản gốc của `dose_event`. Thêm vào để tầng đối chiếu ảnh biết mỗi thuốc
đếm theo đơn vị gì mà không phải join ngược về `prescription`/`drug`. Thêm
trường là thay đổi CỘNG THÊM, code cũ đọc bằng `.get()` nên không hỏng.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import DoseEvent, Prescription

logger = logging.getLogger(__name__)

# Cửa sổ uống thuốc: ±30 phút quanh giờ hẹn (business-rules.md §2).
NUA_CUA_SO = timedelta(minutes=30)

# Bac si chon "gio_nhac" (vd "08:00") tren form ke don nghi la gio Viet Nam,
# khong phai UTC. Khong dung ZoneInfo("UTC") de "combine" thang - lam vay
# doi 08:00 (y benh nhan uong 8h sang) thanh 08:00 UTC = 15:00 gio VN, lech
# dung 7 tieng o moi lieu (phat hien 2026-08-13, xem generator ben duoi).
GIO_VN = ZoneInfo("Asia/Ho_Chi_Minh")

# Trạng thái coi như "đã đóng" — không sinh lại, không xoá khi duyệt lại.
DA_DONG = frozenset({"TAKEN", "MISSED", "DELAYED", "SIDE_EFFECT", "CANCELLED"})

_GIO_MAC_DINH = "08:00"


def _doc_gio(chuoi: str) -> time | None:
    """"08:00" -> time(8, 0). Trả None nếu không đọc được."""
    try:
        gio, phut = (int(phan) for phan in str(chuoi).strip().split(":", 1))
    except (ValueError, AttributeError):
        return None
    return time(gio, phut) if 0 <= gio < 24 and 0 <= phut < 60 else None


def _expected_item(item: dict) -> dict:
    """Một phần tử `expected_items` của DoseEventDTO (api-contracts.md §3)."""
    return {
        "drug_id": item.get("drug_id", ""),
        "ten_thuoc": item.get("ten_thuoc", ""),
        "so_vien": item.get("so_vien_moi_lan"),
        "dang_thuoc": item.get("dang_thuoc", ""),
        "duong_dung": item.get("duong_dung", ""),
    }


def _gom_theo_gio(items: list[dict]) -> dict[time, list[dict]]:
    """Trả về {giờ uống: [các thuốc uống vào giờ đó]}.

    Một thuốc uống ngày 2 lần xuất hiện ở hai giờ khác nhau; hai thuốc cùng giờ
    nằm chung một danh sách.
    """
    theo_gio: defaultdict[time, list[dict]] = defaultdict(list)

    for item in items:
        gio_nhac = item.get("gio_nhac") or [_GIO_MAC_DINH]
        for chuoi in gio_nhac:
            gio = _doc_gio(chuoi)
            if gio is None:
                logger.warning(
                    "Giờ nhắc %r của thuốc %r không đọc được, bỏ qua.",
                    chuoi, item.get("ten_thuoc", "?"),
                )
                continue
            theo_gio[gio].append(_expected_item(item))

    return dict(theo_gio)


def _ngay_bat_dau(presc: Prescription) -> date:
    try:
        return date.fromisoformat(str(presc.start_date))
    except (ValueError, TypeError):
        logger.warning(
            "start_date %r của phác đồ %s không đọc được, dùng hôm nay.",
            presc.start_date, presc.id,
        )
        return datetime.now(UTC).date()


def sinh_dose_event(db: Session, presc: Prescription, *, bay_gio: datetime | None = None) -> int:
    """Sinh lịch uống cho cả đợt điều trị. Trả về số liều đã tạo.

    KHÔNG commit — để bên gọi quyết định ranh giới giao dịch, sao cho việc đổi
    trạng thái phác đồ và sinh lịch cùng thành công hoặc cùng thất bại. Duyệt
    xong mà lịch không sinh được sẽ để lại một phác đồ `active` không có liều
    nào, và không ai biết cho tới khi bệnh nhân thắc mắc sao không được nhắc.
    """
    bay_gio = bay_gio or datetime.now(UTC)
    theo_gio = _gom_theo_gio(presc.items or [])
    if not theo_gio:
        logger.warning("Phác đồ %s không có giờ uống nào hợp lệ, không sinh liều.", presc.id)
        return 0

    _xoa_lieu_chua_toi_han(db, presc.id, bay_gio)

    ngay_dau = _ngay_bat_dau(presc)
    so_ngay = max(int(presc.duration_days or 0), 0)
    da_tao = 0

    for thu_may in range(so_ngay):
        ngay = ngay_dau + timedelta(days=thu_may)
        for gio, expected_items in sorted(theo_gio.items()):
            hen = datetime.combine(ngay, gio, tzinfo=GIO_VN).astimezone(UTC)
            # Không sinh liều đã trôi qua: bấm Duyệt lúc 14h thì liều 08:00
            # sáng nay không còn ý nghĩa để nhắc, và tạo ra nó là lập tức có
            # một liều quá hạn mà bệnh nhân không có cơ hội nào để uống.
            if hen + NUA_CUA_SO <= bay_gio:
                continue

            db.add(
                DoseEvent(
                    prescription_id=presc.id,
                    patient_id=presc.patient_id,
                    scheduled_at=hen,
                    window_start=hen - NUA_CUA_SO,
                    window_end=hen + NUA_CUA_SO,
                    status="PENDING",
                    expected_items=expected_items,
                )
            )
            da_tao += 1

    logger.info("Phác đồ %s: sinh %d liều cho %d ngày.", presc.id, da_tao, so_ngay)
    return da_tao


def _xoa_lieu_chua_toi_han(db: Session, prescription_id: str, bay_gio: datetime) -> None:
    """Xoá các liều PENDING chưa tới hạn để sinh lại — nền tảng của BR-2.3.

    Chỉ đụng liều còn PENDING và còn ở tương lai. Liều đã đóng là lịch sử y tế:
    bệnh nhân đã uống hay đã bỏ lỡ là sự thật đã xảy ra, sửa phác đồ không được
    viết lại (BR-1.3).
    """
    lieu_cu = db.execute(
        select(DoseEvent).where(
            DoseEvent.prescription_id == prescription_id,
            DoseEvent.status == "PENDING",
            DoseEvent.window_end > bay_gio,
        )
    ).scalars().all()

    for lieu in lieu_cu:
        db.delete(lieu)

    if lieu_cu:
        logger.info("Phác đồ %s: xoá %d liều chưa tới hạn để sinh lại.", prescription_id, len(lieu_cu))


def huy_lieu_chua_toi_han(db: Session, prescription_id: str, *, bay_gio: datetime | None = None) -> int:
    """Dừng phác đồ: mọi liều PENDING chuyển CANCELLED (BR-1.4).

    Chuyển trạng thái chứ không xoá — bác sĩ dừng thuốc giữa chừng là một sự
    kiện y tế đáng ghi lại, xoá đi thì về sau không ai biết đã từng có lịch đó.
    """
    bay_gio = bay_gio or datetime.now(UTC)
    lieu = db.execute(
        select(DoseEvent).where(
            DoseEvent.prescription_id == prescription_id,
            DoseEvent.status == "PENDING",
            DoseEvent.window_end > bay_gio,
        )
    ).scalars().all()

    for mot_lieu in lieu:
        mot_lieu.status = "CANCELLED"
    return len(lieu)


__all__ = ["DA_DONG", "NUA_CUA_SO", "huy_lieu_chua_toi_han", "sinh_dose_event"]
