"""Tuy chon thong bao cua benh nhan - man hinh Cai dat (THEM 2026-08-27).

Gop tuy chon cua CA HAI nguon (patient_notification_pref + telegram_link)
vao 1 endpoint doc: man hinh Cai dat ve mot khoi thong bao duy nhat, khong
co ly do gi bat frontend goi 2 noi roi tu ghep.

Rieng viec GHI tuy chon Telegram van o PATCH /telegram/link - no thuoc ve
vong doi cua lien ket (ghep lai thi tu bat lai), khong phai tuy chon chung.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, get_current_user
from backend.db.base import get_db
from backend.db.models import TelegramLink
from backend.models.schemas import NotificationPrefRequest, NotificationPrefResponse
from backend.services.notification_pref import (
    TuyChonThongBao,
    dang_theo_doi_ai,
    dat_tuy_chon,
    lay_tuy_chon,
)
from backend.services.telegram import telegram_is_configured

notification_router = APIRouter()


def _nguoi_goi(db: Session, current_user: CurrentUser) -> tuple[str, str | None]:
    """Tra ve (account_id, patient_id|None). Luon doc tu JWT, khong nhan tu
    body - cung ly do voi push_routes/telegram_routes.

    HAI VAI TRO KHONG LOAI TRU NHAU: mot nguoi vua co lich uong thuoc cua
    chinh minh, vua theo doi bo/me. `Account.role` chi giu duoc MOT gia tri
    nen KHONG dung no de gate - suy tu `patient_id` (co ho so benh nhan) va
    `dang_theo_doi_ai()` (co lien ket nguoi than)."""
    if not current_user.patient_id and not dang_theo_doi_ai(db, current_user.id):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Tài khoản này chưa có tuỳ chọn thông báo",
        )
    return current_user.id, current_user.patient_id


def _doc(db: Session, account_id: str, patient_id: str | None) -> NotificationPrefResponse:
    # Khong co ho so benh nhan (nguoi than thuan tuy): dung mac dinh, 2 cong
    # tac nhac uong thuoc se bi frontend an di (xem is_patient ben duoi).
    tuy_chon = lay_tuy_chon(db, patient_id) if patient_id else TuyChonThongBao()
    tg = db.execute(
        select(TelegramLink).where(TelegramLink.account_id == account_id)
    ).scalars().first()
    return NotificationPrefResponse(
        is_patient=patient_id is not None,
        is_caregiver=dang_theo_doi_ai(db, account_id),
        dose_reminder_enabled=tuy_chon.dose_reminder_enabled,
        web_push_enabled=tuy_chon.web_push_enabled,
        telegram_configured=telegram_is_configured(),
        telegram_linked=tg is not None,
        telegram_enabled=bool(tg.enabled) if tg else False,
        telegram_username=tg.username if tg else None,
    )


@notification_router.get("/notifications/preferences", response_model=NotificationPrefResponse)
def doc_tuy_chon(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> NotificationPrefResponse:
    account_id, patient_id = _nguoi_goi(db, current_user)
    return _doc(db, account_id, patient_id)


@notification_router.patch("/notifications/preferences", response_model=NotificationPrefResponse)
def doi_tuy_chon(
    body: NotificationPrefRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> NotificationPrefResponse:
    """Tra ve trang thai SAU khi doi, khong phai 204: man hinh Cai dat cap
    nhat lac quan roi doi chieu lai bang ket qua nay - mot vong goi it hon so
    voi 204 roi phai GET lai."""
    account_id, patient_id = _nguoi_goi(db, current_user)
    if patient_id is None:
        # Nguoi than khong co lich uong thuoc - khong co gi de doi o day.
        # 403 chu khong phai im lang 200: goi endpoint nay tu man hinh nguoi
        # than la bug o frontend, giau di se rat kho tim.
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Tài khoản này không có lịch uống thuốc để đổi tuỳ chọn",
        )
    dat_tuy_chon(
        db,
        patient_id,
        dose_reminder_enabled=body.dose_reminder_enabled,
        web_push_enabled=body.web_push_enabled,
    )
    db.commit()
    return _doc(db, account_id, patient_id)
