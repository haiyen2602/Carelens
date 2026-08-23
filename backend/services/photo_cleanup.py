"""Xoá FILE ảnh xác nhận liều thuốc đã quá hạn giữ — KHÔNG xoá dòng DB.

Hàm thuần (không đụng APScheduler) để test không cần scheduler thật — cùng
cách tách `escalation_reminder.py` khỏi `escalation_scheduler.py`. Dòng
`PhotoVerification` được giữ lại làm audit trail; chỉ `image_path` bị đặt về
`None`, đúng tín hiệu "không còn ảnh" mà `photo_routes.py::_to_out()` đã dùng
sẵn (`has_image = bool(image_path and Path(image_path).is_file())`).

Hạn giữ chia theo `ket_qua` (xem `backend/config.py::Settings` các trường
`photo_retention_days_*`) vì mức độ cần bằng chứng khác nhau:
  - `khop`  : ngắn nhất, chỉ để gia đình xem lại gần đây.
  - `lech`  : dài hơn, có thể là bằng chứng khi escalate cho người thân/bác sĩ
              sau `MAX_ATTEMPTS` lần lệch (xem verifier.py::_escalate_photo_mismatch).
  - `dang_xu_ly`/`loi_he_thong`/`do_tin_cay_thap`: ngắn nhất — các dòng này lẽ
              ra chuyển trạng thái nhanh (hoặc, với do_tin_cay_thap, chỉ là 1
              lượt xin chụp lại miễn phí bị bỏ dở), còn kẹt lâu là rác, không
              phải bằng chứng.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import Settings, get_settings
from backend.db.models import PhotoVerification
from backend.services.photo_verification.matcher import KetQua
from backend.services.photo_verification.verifier import (
    TRANG_THAI_DANG_XU_LY,
    TRANG_THAI_DO_TIN_CAY_THAP,
    TRANG_THAI_LOI_HE_THONG,
)

logger = logging.getLogger(__name__)


def _tang_han_dung(now: datetime, settings: Settings) -> list[tuple[list[str], datetime]]:
    """[(danh_sach_ket_qua, moc_thoi_gian_cu_hon_la_qua_han), ...]."""
    return [
        ([KetQua.KHOP.value], now - timedelta(days=settings.photo_retention_days_khop)),
        ([KetQua.LECH.value], now - timedelta(days=settings.photo_retention_days_lech)),
        (
            [TRANG_THAI_DANG_XU_LY, TRANG_THAI_LOI_HE_THONG, TRANG_THAI_DO_TIN_CAY_THAP],
            now - timedelta(days=settings.photo_retention_days_stuck),
        ),
    ]


def xoa_anh_het_han(db: Session, now: datetime | None = None, settings: Settings | None = None) -> int:
    """Xoá file ảnh của các dòng `PhotoVerification` đã quá hạn giữ.

    Trả về số file đã xoá. Không bao giờ ném exception vì 1 file lỗi (thiếu
    quyền, đã bị xoá tay từ trước) — log và xử lý tiếp các dòng còn lại.
    """
    now = now or datetime.now(UTC)
    settings = settings or get_settings()

    so_da_xoa = 0
    for ket_qua_list, moc in _tang_han_dung(now, settings):
        rows = db.execute(
            select(PhotoVerification).where(
                PhotoVerification.image_path.is_not(None),
                PhotoVerification.ket_qua.in_(ket_qua_list),
                PhotoVerification.created_at < moc,
            )
        ).scalars().all()

        for row in rows:
            try:
                Path(row.image_path).unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Không xoá được file ảnh %s: %s", row.image_path, exc)
                continue
            row.image_path = None
            db.add(row)
            so_da_xoa += 1

    if so_da_xoa:
        db.commit()
    return so_da_xoa


__all__ = ["xoa_anh_het_han"]
