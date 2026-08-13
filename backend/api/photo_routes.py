"""
Nhận ảnh xác nhận liều thuốc, đối chiếu với đơn thuốc (ADR-0011).

`POST` trả `202` ngay — một lần gọi mô hình đo được 26 đến 265 giây (xem
`backend/services/photo_verification/vlm_bridge.py`), quá lâu để giữ trong một
request HTTP đồng bộ. Việc nặng chạy nền qua `BackgroundTasks` của FastAPI,
frontend hỏi lại kết quả bằng `GET`.

Tầng này CHỈ làm việc HTTP (đọc file, gọi service, map lỗi) — theo ADR-0004
§1, mọi quyết định nghiệp vụ (hết lượt chưa, xác minh được không, bước tiếp
theo là gì) nằm trong `verifier.py`.
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.security import require_internal_secret
from backend.config import get_settings
from backend.db.base import get_db
from backend.db.models import DoseEvent, PhotoVerification
from backend.models.schemas import PhotoSubmitResponse, PhotoVerificationOut
from backend.services.photo_verification import (
    MAX_ANH_BYTES,
    MAX_ATTEMPTS,
    HanMucVuotQuaError,
    KetQua,
    KhongXacMinhDuocError,
    hoan_tat_xac_minh,
    khoi_tao_xac_minh,
    xac_dinh_next_action,
)

photo_router = APIRouter()

# Trạng thái đã có kết quả đối chiếu thật — khác "dang_xu_ly" (còn chờ mô
# hình) và "loi_he_thong" (không có kết quả để đối chiếu).
_TRANG_THAI_DA_XONG = {KetQua.KHOP.value, KetQua.LECH.value, KetQua.KHONG_XAC_MINH_DUOC.value}


@photo_router.post(
    "/doses/{dose_id}/photo",
    response_model=PhotoSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_internal_secret)],
)
async def submit_photo(
    dose_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile,
    db: Session = Depends(get_db),
) -> PhotoSubmitResponse:
    dose_event = db.get(DoseEvent, dose_id)
    if dose_event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Không tìm thấy liều thuốc.")

    anh = await file.read()
    if not anh:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Ảnh gửi lên rỗng.")
    if len(anh) > MAX_ANH_BYTES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Ảnh quá lớn ({len(anh) // 1024}KB > {MAX_ANH_BYTES // 1024}KB).",
        )

    duong_dan = _duong_dan_moi(dose_id)
    try:
        xac_minh = khoi_tao_xac_minh(db, dose_event, duong_dan)
    except KhongXacMinhDuocError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except HanMucVuotQuaError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    # Ghi ảnh ra đĩa SAU KHI khoi_tao_xac_minh thành công: bị từ chối ở bước
    # trên (hết lượt / không xác minh được) thì không để lại rác trên đĩa.
    Path(duong_dan).write_bytes(anh)

    background_tasks.add_task(hoan_tat_xac_minh, xac_minh.id)

    return PhotoSubmitResponse(
        verification_id=xac_minh.id,
        status="dang_xu_ly",
        attempt=xac_minh.attempt,
        max_attempts=MAX_ATTEMPTS,
        message=xac_minh.thong_bao,
    )


@photo_router.get(
    "/photo-verifications/{verification_id}",
    response_model=PhotoVerificationOut,
    dependencies=[Depends(require_internal_secret)],
)
def get_photo_verification(verification_id: str, db: Session = Depends(get_db)) -> PhotoVerificationOut:
    row = db.get(PhotoVerification, verification_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Không tìm thấy lần xác minh này.")
    return _to_out(row)


@photo_router.get(
    "/doses/{dose_id}/photo-verifications",
    response_model=list[PhotoVerificationOut],
    dependencies=[Depends(require_internal_secret)],
)
def list_photo_verifications_for_dose(dose_id: str, db: Session = Depends(get_db)) -> list[PhotoVerificationOut]:
    """Lịch sử TẤT CẢ lần gửi ảnh của 1 liều (patient/history bấm vào 1 dòng
    lịch sử để xem lại) — sắp theo `attempt` tăng dần, không phải chỉ lần mới
    nhất như GET /photo-verifications/{id}."""
    rows = db.execute(
        select(PhotoVerification)
        .where(PhotoVerification.dose_event_id == dose_id)
        .order_by(PhotoVerification.attempt)
    ).scalars().all()
    return [_to_out(row) for row in rows]


@photo_router.get(
    "/photo-verifications/{verification_id}/image",
    dependencies=[Depends(require_internal_secret)],
)
def get_photo_verification_image(verification_id: str, db: Session = Depends(get_db)) -> FileResponse:
    row = db.get(PhotoVerification, verification_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Không tìm thấy lần xác minh này.")
    if not row.image_path or not Path(row.image_path).is_file():
        # Anh khong con tren dia (vd container restart, chua gan volume ben
        # ngoai) - phan biet voi 404 o tren (khong tim thay BAN GHI) bang loi
        # rieng de frontend hien dung thong bao.
        raise HTTPException(status.HTTP_410_GONE, detail="Ảnh không còn trên máy chủ.")
    return FileResponse(row.image_path, media_type="image/jpeg")


def _to_out(row: PhotoVerification) -> PhotoVerificationOut:
    matched: bool | None = None
    next_action: str | None = None
    if row.ket_qua in _TRANG_THAI_DA_XONG:
        ket_qua_enum = KetQua(row.ket_qua)
        matched = ket_qua_enum is KetQua.KHOP
        next_action = xac_dinh_next_action(ket_qua_enum, row.attempt)

    return PhotoVerificationOut(
        id=row.id,
        dose_event_id=row.dose_event_id,
        attempt=row.attempt,
        max_attempts=MAX_ATTEMPTS,
        status=row.ket_qua,
        matched=matched,
        expected_by_form=row.expected_by_form,
        detected_by_form=row.detected_by_form,
        confidence=row.confidence,
        next_action=next_action,
        message=row.thong_bao,
        created_at=row.created_at.isoformat(),
        has_image=bool(row.image_path and Path(row.image_path).is_file()),
    )


def _duong_dan_moi(dose_id: str) -> str:
    thu_muc = Path(get_settings().photo_storage_dir)
    thu_muc.mkdir(parents=True, exist_ok=True)
    return str(thu_muc / f"{dose_id}_{uuid.uuid4().hex}.jpg")
