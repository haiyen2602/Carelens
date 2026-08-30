"""Gui tin nhac gio uong thuoc qua Telegram bot (THEM 2026-08-27).

Kenh THU HAI ben canh Web Push (backend/services/push.py), cung mot nguoi
goi: job dinh ky backend/services/dose_push_reminder.py. Ly do them kenh nay:
Web Push khong toi duoc iOS Safari tru khi benh nhan da cai PWA ra man hinh
chinh - mot dieu kien phan lon benh nhan cao tuoi khong bao gio lam.

GIOI HAN GOC CUA BOT API, doc ky truoc khi sua: bot KHONG gui duoc tin theo
so dien thoai hay email. `sendMessage` chi nhan `chat_id`, va chat_id chi ton
tai sau khi CHINH nguoi dung bam /start voi bot. Khong co endpoint nao tra
chat_id tu so dien thoai - day la co che chong spam co y cua Telegram. Vi vay
phai co buoc ghep tai khoan mot lan (xem doi_token_lay_link ben duoi) va bang
TelegramLink de nho ket qua.

FAIL MEM CO Y, cung idiom voi push.py: chua cau hinh token thi ham tra ve 0
va chi log 1 dong, KHONG raise. Thieu token khong phai lo hong bao mat - no
chi la "khong co kenh Telegram", app va cac kenh nhac khac van chay dung.
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.models import Account, CaregiverLink, Patient, TelegramLink, TelegramLinkToken

logger = logging.getLogger("telegram")

_API_BASE = "https://api.telegram.org"

# Telegram tra 403 khi benh nhan da CHAN bot (hoac xoa doan chat roi chan).
# Giu lai dong lien ket chi ton cong goi API moi phut -> xoa, dung tinh than
# voi _GONE_STATUS cua push.py. 400 KHONG nam trong nhom nay: no thuong la
# loi cu phap tin nhan cua chinh ta, xoa lien ket la mat oan.
_BLOCKED_STATUS = frozenset({403})

# Bot API co the treo lau neu mang loi; job chay moi 60 giay nen phai thoat
# som hon the nhieu, khong duoc de mot lan gui cham lam nghen ca vong quet.
_TIMEOUT_SECONDS = 10.0


def telegram_is_configured() -> bool:
    return bool(get_settings().telegram_bot_token)


def _goi_bot_api(method: str, payload: dict) -> httpx.Response | None:
    """Tra ve Response, hoac None neu khong goi duoc (mang loi/chua cau hinh).

    Gom vao 1 cho de moi duong goi ra Internet cua module nay deu di qua day
    - khop voi rang buoc trong backend/egress_allowlist.py."""
    settings = get_settings()
    if not settings.telegram_bot_token:
        return None
    url = f"{_API_BASE}/bot{settings.telegram_bot_token}/{method}"
    try:
        return httpx.post(url, json=payload, timeout=_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        logger.warning("Goi Telegram %s that bai: %s", method, exc)
        return None


def send_telegram_to_account(db: Session, account_id: str, title: str, body: str) -> int:
    """Gui toi tai khoan Telegram cua 1 ACCOUNT (benh nhan hay nguoi than deu
    dung ham nay). Tra ve so tin gui thanh cong.

    KHONG commit - de nguoi goi quyet dinh ranh gioi giao dich, cung idiom voi
    send_push_to_patient(). Rieng viec xoa lien ket da bi chan co flush ngay
    de lan gui ke tiep trong cung vong lap khong dung lai dong da chet."""
    if not telegram_is_configured():
        logger.debug("Chua cau hinh Telegram - bo qua tai khoan %s", account_id)
        return 0

    # Loc `enabled` NGAY TRONG CAU TRUY VAN, khong loc o Python sau do: da tat
    # thi khong duoc gui, va cung khong nen keo dong do ve lam gi.
    rows = db.execute(
        select(TelegramLink).where(
            TelegramLink.account_id == account_id,
            TelegramLink.enabled.is_(True),
        )
    ).scalars().all()
    if not rows:
        return 0

    # Telegram khong co truong "title" rieng nhu Web Push - gop lai thanh 1
    # doan text, in dam dong dau de van doc ra duoc dau la tieu de.
    text = f"<b>{title}</b>\n{body}"
    da_gui = 0

    for row in rows:
        resp = _goi_bot_api(
            "sendMessage",
            {"chat_id": row.chat_id, "text": text, "parse_mode": "HTML"},
        )
        if resp is None:
            continue
        if resp.status_code in _BLOCKED_STATUS:
            logger.info("Nguoi dung da chan bot (chat_id=%s) - xoa khoi telegram_link", row.chat_id)
            db.delete(row)
            db.flush()
            continue
        if resp.status_code != 200:
            # 1 tai khoan loi khong duoc chan cac tai khoan con lai.
            logger.warning("Gui Telegram toi %s that bai (HTTP %s)", row.chat_id, resp.status_code)
            continue
        da_gui += 1

    return da_gui


def _account_cua_benh_nhan(db: Session, patient_id: str) -> str | None:
    return db.execute(
        select(Account.id).where(Account.patient_id == patient_id, Account.role == "patient")
    ).scalars().first()


def send_telegram_to_patient(db: Session, patient_id: str, title: str, body: str) -> int:
    """Gui cho CHINH benh nhan. Giu nguyen chu ky cu de dose_push_reminder.py
    khong phai biet telegram_link da doi khoa sang account_id."""
    account_id = _account_cua_benh_nhan(db, patient_id)
    if account_id is None:
        # Benh nhan chua co tai khoan dang nhap (ho so do bac si/admin tao) -
        # khong phai loi, chi la khong co Telegram nao de gui.
        return 0
    return send_telegram_to_account(db, account_id, title, body)


def send_telegram_to_caregivers(db: Session, patient_id: str, title: str, body: str) -> int:
    """Gui canh bao cho MOI nguoi than dang theo doi benh nhan nay.

    CHI lay lien ket `accepted`: dong "pending" la loi moi chua duoc chap
    nhan, gui canh bao suc khoe toi do la ro ri thong tin y te cho nguoi chua
    duoc benh nhan dong y.

    Ten benh nhan duoc gan vao dau tin ngay tai day: 1 nguoi con co the theo
    doi ca bo lan me, nhan "Chua uong thuoc" ma khong biet cua ai thi canh bao
    thanh vo dung."""
    ten = db.execute(select(Patient.full_name).where(Patient.id == patient_id)).scalars().first()
    tieu_de = f"{title} — {ten}" if ten else title

    account_ids = db.execute(
        select(CaregiverLink.caregiver_account_id).where(
            CaregiverLink.patient_id == patient_id,
            CaregiverLink.status == "accepted",
        )
    ).scalars().all()

    da_gui = 0
    for account_id in account_ids:
        da_gui += send_telegram_to_account(db, account_id, tieu_de, body)
    return da_gui


def gio_dia_phuong(moc_utc: datetime) -> str:
    """Doi gio UTC sang gio hien thi trong tin Telegram.

    Web Push khong can ham nay (trinh duyet tu doi theo gio may benh nhan),
    nhung Telegram gui text tho: khong doi thi benh nhan doc "hen 14:00" cho
    lieu 21:00 cua chinh minh."""
    offset = get_settings().telegram_display_utc_offset_hours
    return moc_utc.astimezone(timezone(timedelta(hours=offset))).strftime("%H:%M")


# --- Ghep tai khoan (chay 1 lan cho moi benh nhan) --------------------------

def tao_token_ghep(db: Session, account_id: str) -> str:
    """Sinh ma dung 1 lan + link t.me de benh nhan bam. KHONG commit.

    `token_urlsafe(16)` chu khong phai so tang dan hay uuid4 doan duoc: ai
    doan trung token cua nguoi khac se noi duoc Telegram CUA HO vao tai khoan
    khac, tu do nhan het thong tin thuoc men - day la du lieu y te, khong
    duoc de doan."""
    settings = get_settings()
    token = secrets.token_urlsafe(16)
    db.add(
        TelegramLinkToken(
            token=token,
            account_id=account_id,
            expires_at=datetime.now(UTC) + timedelta(seconds=settings.telegram_link_token_ttl_seconds),
        )
    )
    return token


def link_ghep(token: str) -> str:
    return f"https://t.me/{get_settings().telegram_bot_username}?start={token}"


def doi_token_lay_link(db: Session, *, token: str, chat_id: int, username: str | None) -> str | None:
    """Doi token lay lien ket that. Tra ve account_id neu thanh cong, None
    neu token sai/het han/da dung. KHONG commit.

    Kiem tra han VA `used_at` rieng biet du ca hai deu tra None: goi y cua
    Telegram gui lai /start cu la chuyen thuong (benh nhan bam lai link cu
    trong lich su chat), khong duoc coi la tan cong."""
    row = db.execute(
        select(TelegramLinkToken).where(TelegramLinkToken.token == token)
    ).scalars().first()
    if row is None:
        logger.info("Token ghep Telegram khong ton tai")
        return None
    if row.used_at is not None:
        logger.info("Token ghep Telegram da duoc dung roi (account=%s)", row.account_id)
        return None
    if row.expires_at <= datetime.now(UTC):
        logger.info("Token ghep Telegram da het han (account=%s)", row.account_id)
        return None

    cu = db.execute(
        select(TelegramLink).where(TelegramLink.chat_id == chat_id)
    ).scalars().first()
    if cu is not None:
        # Cung 1 tai khoan Telegram ghep lai (doi tai khoan, hoac ghep nham
        # truoc do) - CHUYEN sang tai khoan moi thay vi tao dong thu 2, neu
        # khong se ban trung 2 lan.
        cu.account_id = row.account_id
        cu.username = username
        # Ghep lai = chu dong bam Ket noi = CO muon nhan. Neu truoc do ho tat
        # di roi ghep lai ma van im lang thi se tuong tinh nang hong.
        cu.enabled = True
    else:
        db.add(TelegramLink(account_id=row.account_id, chat_id=chat_id, username=username))

    row.used_at = datetime.now(UTC)
    return row.account_id


# --- Nhan /start tu benh nhan ----------------------------------------------

# Update da xu ly toi dau. GIU TRONG BO NHO co y, khong tao bang rieng: ghep
# tai khoan la thao tac IDEMPOTENT (token da dung -> bo qua; cung chat_id ->
# UPDATE dong cu), nen truong hop xau nhat khi backend khoi dong lai la xu ly
# lai vai update cu roi bo qua chung - khong sinh du lieu rac. Doi lay 1 bang
# + 1 migration it hon.
_offset: int | None = None

# Vua du de nhan het cac benh nhan bam /start trong 1 nhip 60 giay, vua tranh
# keo ve mot dong update rac neu bot bi spam.
_GIOI_HAN_UPDATE = 50


def _tra_loi(chat_id: int, text: str) -> None:
    _goi_bot_api("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "HTML"})


def xu_ly_start(db: Session, *, chat_id: int, username: str | None, text: str) -> bool:
    """Xu ly 1 tin "/start <token>". Tra ve True neu ghep thanh cong.

    Tach rieng khoi phan goi mang de test duoc truc tiep voi noi dung tin gia
    lap (khong can bot that) - cung tinh than voi tinh_moc() cua
    dose_push_reminder.py."""
    phan = text.strip().split(maxsplit=1)
    if not phan or phan[0] != "/start":
        return False

    if len(phan) == 1:
        _tra_loi(
            chat_id,
            "Chào bạn 👋\nĐể nhận nhắc giờ uống thuốc, hãy mở CapyMedi trên web "
            "và bấm <b>Kết nối Telegram</b> — đường link ở đó sẽ tự ghép tài khoản này.",
        )
        return False

    account_id = doi_token_lay_link(db, token=phan[1], chat_id=chat_id, username=username)
    if account_id is None:
        _tra_loi(
            chat_id,
            "Đường link này đã hết hạn hoặc đã được dùng rồi 😢\n"
            "Bạn vào lại CapyMedi trên web và bấm <b>Kết nối Telegram</b> để lấy link mới nhé.",
        )
        return False

    _tra_loi(
        chat_id,
        "Kết nối thành công! 🎉\nTừ giờ CapyMedi sẽ nhắn cho bạn ở đây mỗi khi tới giờ uống thuốc.",
    )
    return True


def quet_update_moi(db: Session) -> int:
    """Keo cac tin moi gui toi bot roi xu ly. Tra ve so tai khoan vua ghep.

    DUNG long-polling (`getUpdates`) chu khong phai webhook: khong can domain
    public nen chay duoc ngay tren docker compose o may tung nguoi. Khi len
    production co the doi sang webhook - luc do PHAI bo job nay di, Telegram
    tu choi getUpdates bang 409 neu da dat webhook (hai co che loai tru nhau).
    """
    global _offset
    if not telegram_is_configured():
        return 0

    payload: dict = {"timeout": 0, "limit": _GIOI_HAN_UPDATE, "allowed_updates": ["message"]}
    if _offset is not None:
        payload["offset"] = _offset

    resp = _goi_bot_api("getUpdates", payload)
    if resp is None:
        return 0
    if resp.status_code != 200:
        logger.warning("getUpdates that bai (HTTP %s): %s", resp.status_code, resp.text[:200])
        return 0

    updates = resp.json().get("result", [])
    da_ghep = 0
    for upd in updates:
        # Xac nhan da nhan NGAY CA khi tin loi/khong phai /start - neu khong,
        # 1 tin la se bi Telegram gui lai mai mai moi 60 giay.
        _offset = upd["update_id"] + 1
        msg = upd.get("message") or {}
        chat = msg.get("chat") or {}
        if chat.get("type") != "private":
            continue  # bot bi them vao nhom - khong ghep ho so y te o do
        noi_dung = msg.get("text")
        if not noi_dung:
            continue
        try:
            if xu_ly_start(
                db,
                chat_id=chat["id"],
                username=(msg.get("from") or {}).get("username"),
                text=noi_dung,
            ):
                da_ghep += 1
        except Exception:  # noqa: BLE001 - 1 tin loi khong duoc chan cac tin con lai
            logger.exception("Loi khi xu ly update Telegram %s", upd.get("update_id"))

    if da_ghep:
        db.commit()
    elif updates:
        db.commit()  # con luu used_at cua cac token da tieu thu nhung ghep hong
    return da_ghep
