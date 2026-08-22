"""Dang ky/go thiet bi nhan Web Push (THEM 2026-08-20).

Luong: frontend dang ky Service Worker -> lay VAPID public key qua
GET /push/vapid-public-key -> pushManager.subscribe() -> POST ket qua len
POST /push/subscribe. Tu do backend (backend/services/dose_push_reminder.py)
gui duoc thong bao toi may benh nhan ke ca khi ho da dong han tab.

Public key phat qua endpoint thay vi bat frontend giu 1 ban sao trong
NEXT_PUBLIC_* env: 1 nguon duy nhat, doi khoa khong phai build lai frontend
(NEXT_PUBLIC_* la build-time, xem docs/DEPLOY.md).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, get_current_user
from backend.config import get_settings
from backend.db.base import get_db
from backend.db.models import PushSubscription
from backend.models.schemas import PushSubscribeRequest, PushVapidKeyResponse

push_router = APIRouter()


def _patient_id_cua(current_user: CurrentUser) -> str:
    """Chi benh nhan tu dang ky thiet bi CUA CHINH HO - luon doc tu JWT,
    khong nhan patient_id tu body (cung ly do voi list_pending_invites o
    caregiver_routes.py)."""
    if current_user.role != "patient" or not current_user.patient_id:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Chỉ bệnh nhân mới đăng ký nhận thông báo cho chính mình",
        )
    return current_user.patient_id


@push_router.get("/push/vapid-public-key", response_model=PushVapidKeyResponse)
def get_vapid_public_key() -> PushVapidKeyResponse:
    """Rong = chua cau hinh VAPID -> frontend tu bo qua buoc dang ky push,
    khong bao loi (push la tinh nang phu, xem backend/services/push.py)."""
    return PushVapidKeyResponse(public_key=get_settings().vapid_public_key)


@push_router.post(
    "/push/subscribe", status_code=http_status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None
)
def subscribe(
    body: PushSubscribeRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
    user_agent: str | None = Header(default=None),
) -> None:
    """UPSERT theo `endpoint` - endpoint chinh la danh tinh cua 1 thiet bi,
    dang ky lai tu cung may (vd sau khi xoa cache) phai cap nhat dong cu chu
    khong tao dong thu 2 roi ban trung 2 lan."""
    patient_id = _patient_id_cua(current_user)

    row = db.execute(
        select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
    ).scalars().first()

    if row is None:
        db.add(
            PushSubscription(
                patient_id=patient_id,
                endpoint=body.endpoint,
                p256dh=body.keys.p256dh,
                auth=body.keys.auth,
                user_agent=user_agent,
            )
        )
    else:
        # Cung 1 may co the doi tai khoan dang nhap - gan lai cho benh nhan
        # hien tai, neu khong nguoi moi se nhan nhac cua nguoi cu.
        row.patient_id = patient_id
        row.p256dh = body.keys.p256dh
        row.auth = body.keys.auth
        row.user_agent = user_agent

    db.commit()


@push_router.delete(
    "/push/subscribe", status_code=http_status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None
)
def unsubscribe(
    endpoint: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Go 1 thiet bi. Idempotent - go thiet bi khong ton tai van 204, khong
    404: nguoi dung bam tat thong bao 2 lan khong phai la loi."""
    patient_id = _patient_id_cua(current_user)
    row = db.execute(
        select(PushSubscription).where(
            PushSubscription.endpoint == endpoint,
            PushSubscription.patient_id == patient_id,
        )
    ).scalars().first()
    if row is not None:
        db.delete(row)
        db.commit()
