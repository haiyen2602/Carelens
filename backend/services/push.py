"""Gui Web Push toi thiet bi cua benh nhan (THEM 2026-08-20).

Day la thu DUY NHAT trong repo gui duoc thong bao khi benh nhan da DONG HAN
tab/trinh duyet - co che poll o client (frontend/src/components/capy/
capy-shell.tsx) chi song khi tab con mo. Nguoi goi la job dinh ky
backend/services/dose_push_reminder.py.

FAIL MEM CO Y: chua cau hinh VAPID thi ham tra ve 0 va chi log 1 dong, KHONG
raise. Thieu VAPID khong phai lo hong bao mat (khac internal_auth_secret/
jwt_secret von fail-closed) - no chi la "khong co tinh nang push", app va
nhac o client van chay dung. Bat app chet vi thieu no se lam vo moi truong
local cua ca nhom.
"""

from __future__ import annotations

import json
import logging

try:
    from pywebpush import WebPushException, webpush
except ImportError:  # pragma: no cover
    WebPushException = Exception  # type: ignore[misc,assignment]
    webpush = None  # type: ignore[assignment]

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.models import PushSubscription

logger = logging.getLogger("push")

# Dich vu day tra 2 ma nay = subscription DA CHET han (nguoi dung go quyen,
# go app, hoac trinh duyet tu huy). Giu lai chi ton cong gui moi lan -> xoa.
_GONE_STATUS = frozenset({404, 410})

# pywebpush mac dinh ttl=0 ("khong luu, chi gui neu thiet bi dang online
# ngay luc nay"). FCM (Chrome/Firefox) chap nhan gia tri nay, nhung WNS
# (endpoint notify.windows.com - Edge tren Windows) TU CHOI thang voi 400
# "Ttl value conflicts with X-WNS-Cache-Policy" - phat hien 2026-08-22 khi
# nhac gio uong thuoc khong toi duoc thiet bi Edge du subscription/VAPID deu
# dung. Dat TTL 30 phut: du de dich vu day giu ho neu thiet bi tam thoi mat
# mang, nhung khong qua dai vi qua moc do lieu thuoc coi nhu da tre
# (HET_HAN_NHAC_PHUT trong dose_push_reminder.py).
_PUSH_TTL_SECONDS = 1800


def push_is_configured() -> bool:
    settings = get_settings()
    return bool(settings.vapid_public_key and settings.vapid_private_key)


def send_push_to_patient(
    db: Session, patient_id: str, title: str, body: str, *, url: str = "/patient"
) -> int:
    """Gui toi MOI thiet bi benh nhan da dang ky. Tra ve so thiet bi gui
    thanh cong (0 neu chua cau hinh VAPID hoac benh nhan chua bat thong bao).

    KHONG commit - de nguoi goi quyet dinh ranh gioi giao dich, cung idiom
    voi sinh_dose_event(). Rieng viec xoa subscription chet co flush ngay ben
    duoi de lan gui ke tiep trong cung vong lap khong dung lai dong da chet.
    """
    if not push_is_configured():
        logger.debug("Chua cau hinh VAPID - bo qua push cho benh nhan %s", patient_id)
        return 0

    rows = db.execute(
        select(PushSubscription).where(PushSubscription.patient_id == patient_id)
    ).scalars().all()
    if not rows:
        return 0

    settings = get_settings()
    payload = json.dumps({"title": title, "body": body, "url": url}, ensure_ascii=False)
    da_gui = 0

    for row in rows:
        try:
            webpush(
                subscription_info={
                    "endpoint": row.endpoint,
                    "keys": {"p256dh": row.p256dh, "auth": row.auth},
                },
                data=payload,
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.vapid_subject},
                ttl=_PUSH_TTL_SECONDS,
            )
            da_gui += 1
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in _GONE_STATUS:
                logger.info(
                    "Subscription %s da chet (HTTP %s) - xoa khoi push_subscription", row.id, status
                )
                db.delete(row)
                db.flush()
            else:
                # 1 thiet bi loi (mang, dich vu day tam thoi 5xx) khong duoc
                # chan cac thiet bi con lai cua chinh benh nhan do.
                logger.warning("Gui push toi %s that bai (HTTP %s): %s", row.id, status, exc)
        except Exception:  # noqa: BLE001 - job dinh ky khong duoc chet vi 1 lan gui
            logger.exception("Loi khong luong truoc khi gui push toi subscription %s", row.id)

    return da_gui
