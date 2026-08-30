"""Ghep/go tai khoan Telegram cua benh nhan (THEM 2026-08-27).

Luong ghep (xem them backend/services/telegram.py):
  1. Benh nhan bam "Kết nối Telegram" -> POST /telegram/link-token
  2. Frontend mo deep_link tra ve -> Telegram mo bot, benh nhan bam Start
  3. Job dinh ky (escalation_scheduler._run_telegram_updates) nhan
     "/start <token>", doi lay chat_id va ghi TelegramLink
  4. Tu do dose_push_reminder gui nhac gio uong thuoc qua ca kenh nay

KHONG co endpoint nhan webhook o day: ban nay dung long-polling de chay duoc
tren may local khong co domain public. Khi doi sang webhook thi them route o
day VA bo job poll di - hai co che loai tru nhau (Telegram tra 409).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, get_current_user
from backend.config import get_settings
from backend.db.base import get_db
from backend.db.models import TelegramLink
from backend.models.schemas import (
    TelegramLinkStartResponse,
    TelegramPreferenceRequest,
    TelegramStatusResponse,
)
from backend.services.notification_pref import dang_theo_doi_ai
from backend.services.telegram import link_ghep, tao_token_ghep, telegram_is_configured

telegram_router = APIRouter()


def _account_id_cua(db: Session, current_user: CurrentUser) -> str:
    """Luon lay danh tinh tu JWT, khong nhan tu body (cung ly do voi
    push_routes._patient_id_cua): nhan tu body la mo duong cho bat ky ai noi
    Telegram cua ho vao tai khoan khac roi doc duoc toan bo thong tin y te.

    Duoc ghep khi co IT NHAT MOT thu de nhan: lich uong thuoc cua chinh minh
    (`patient_id`), hoac dang theo doi ai do (nguoi than).

    KHONG kiem tra `role`: mot nguoi vua la benh nhan vua theo doi bo/me la
    chuyen binh thuong, ma `role` chi giu duoc MOT gia tri. Gate theo role se
    chan mat mot nua so nguoi dung hop le - dung loi da lam cong tac o man
    hinh Cai dat bi khoa. Bac si/admin thuan tuy van bi tu choi vi ho khong
    thoa ca hai dieu kien."""
    if not current_user.patient_id and not dang_theo_doi_ai(db, current_user.id):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Tài khoản này chưa có thông báo nào để nhận qua Telegram",
        )
    return current_user.id


@telegram_router.get("/telegram/status", response_model=TelegramStatusResponse)
def telegram_status(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> TelegramStatusResponse:
    account_id = _account_id_cua(db, current_user)
    row = db.execute(
        select(TelegramLink).where(TelegramLink.account_id == account_id)
    ).scalars().first()
    return TelegramStatusResponse(
        configured=telegram_is_configured(),
        linked=row is not None,
        username=row.username if row else None,
        enabled=bool(row.enabled) if row else False,
    )


@telegram_router.post("/telegram/link-token", response_model=TelegramLinkStartResponse)
def tao_link_ghep(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> TelegramLinkStartResponse:
    """503 khi server chua cau hinh bot - KHONG tra link rong: benh nhan bam
    vao link hong se thay Telegram bao loi kho hieu, con frontend da co
    /telegram/status de an nut di truoc do."""
    account_id = _account_id_cua(db, current_user)
    settings = get_settings()
    if not telegram_is_configured() or not settings.telegram_bot_username:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Máy chủ chưa cấu hình Telegram bot",
        )

    token = tao_token_ghep(db, account_id)
    db.commit()
    return TelegramLinkStartResponse(
        deep_link=link_ghep(token),
        expires_in_seconds=settings.telegram_link_token_ttl_seconds,
    )


@telegram_router.patch(
    "/telegram/link", status_code=http_status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None
)
def doi_tuy_chon(
    body: TelegramPreferenceRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Bat/tat nhac Telegram ma VAN giu lien ket - khac han DELETE ben duoi.

    404 khi chua ghep tai khoan nao: bat/tat mot thu chua ton tai la loi that
    o phia goi (frontend chi hien cong tac sau khi da linked), im lang tra 204
    se giau bug do di."""
    account_id = _account_id_cua(db, current_user)
    rows = db.execute(
        select(TelegramLink).where(TelegramLink.account_id == account_id)
    ).scalars().all()
    if not rows:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Chưa kết nối Telegram",
        )
    for row in rows:
        row.enabled = body.enabled
    db.commit()


@telegram_router.delete(
    "/telegram/link", status_code=http_status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None
)
def go_ket_noi(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Xoa MOI lien ket cua tai khoan. Khong 404 khi chua co lien ket nao -
    ket qua cuoi cung dung nhu nguoi dung muon ("khong con nhan Telegram"),
    cung idiom voi DELETE /push/subscribe."""
    account_id = _account_id_cua(db, current_user)
    rows = db.execute(
        select(TelegramLink).where(TelegramLink.account_id == account_id)
    ).scalars().all()
    for row in rows:
        db.delete(row)
    if rows:
        db.commit()
