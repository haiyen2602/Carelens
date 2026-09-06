"""Bot Telegram tra loi nhu chatbot tren web (THEM 2026-08-28, TASK-TELEGRAM-BOT Dot 2).

BOT KHONG CO BO NAO RIENG. Module nay chi lam ba viec: doi `chat_id` thanh
danh tinh, goi DUNG ham ma web goi (`run_agent_orchestration`), roi doi ket
qua thanh tin nhan Telegram. Moi luat an toan - guardrail, phan quyen,
doctor-takeover, safety - nam trong Agent V2 va tu dong ap dung cho ca hai
duong vao. Viet lai bat ky mieng nao trong so do o day se tao ra mot duong
vong lach qua chinh sach an toan, va no se lech dan theo thoi gian.

GOI THANG HAM ROUTE thay vi goi HTTP noi bo: `run_agent_orchestration` la
`def` thuan, nhan (request, db, actor) - goi truc tiep duoc. Di qua HTTP se
ton mot vong mang, mot lop serialize, va quan trong hon la de nguoi doc tuong
day la mot he thong khac.

NUT BAM DUNG ReplyKeyboard (bam = gui text) chu khong phai InlineKeyboard:
`_typed_action()` trong backend/agents/v2/conversation_state.py da khop san
theo NHAN hoac SO THU TU, nen text cua nut duoc server hieu y het mot cu bam
nut that. Doi lai ta khong phai xu ly callback_query, khong dung phai gioi
han 64 byte cua callback_data, va khong can bang luu tam danh sach action.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.rate_limit import _get_default_limiter
from backend.api.security import CurrentUser
from backend.db.models import Account, CaregiverLink, Patient, TelegramLink
from backend.models.schemas import AgentV2OrchestrateRequest
from backend.services.telegram import _goi_bot_api

logger = logging.getLogger("telegram_chat")

# Doi tuong dang duoc hoi toi, theo chat_id.
#
# GIU TRONG BO NHO co y (Dot 2): luu ben vung can them cot vao telegram_link,
# ma so migration hien dang vuong - nhanh drug-request chua commit da chiem
# 0061. Mat mat khi restart la nguoi cham NHIEU benh nhan phai chon lai mot
# lan; nguoi chi co mot doi tuong (tuyet dai da so) khong bao gio thay buoc
# nay. Se doi sang cot that o Dot 4 khi chuoi migration da on dinh.
_dang_hoi_ve: dict[int, str] = {}

_LOI_CHUNG = "Xin lỗi, mình đang gặp trục trặc. Bạn thử lại sau ít phút nhé."


def _gui(chat_id: int, text: str, nut: list[str] | None = None) -> None:
    """Gui tin, kem ban phim goi y neu co.

    `one_time_keyboard` de ban phim tu an sau khi bam - khong thi no che mat
    khung go, benh nhan muon hoi cau khac phai tu tim nut dong. `resize` de
    nut vua dung chieu cao thay vi chiem nua man hinh."""
    payload: dict = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if nut:
        payload["reply_markup"] = {
            "keyboard": [[{"text": n}] for n in nut],
            "resize_keyboard": True,
            "one_time_keyboard": True,
        }
    else:
        # Xoa ban phim cu di - de lai se khien benh nhan tuong cac nut do van
        # con hieu luc cho cau tra loi moi.
        payload["reply_markup"] = {"remove_keyboard": True}
    _goi_bot_api("sendMessage", payload)


def _bao_dang_go(chat_id: int) -> None:
    """Agent V2 mat vai giay - khong co tin hieu gi thi benh nhan tuong bot
    chet. Telegram tu tat trang thai nay sau ~5 giay hoac khi co tin moi."""
    _goi_bot_api("sendChatAction", {"chat_id": chat_id, "action": "typing"})


def _ung_vien(db: Session, account: Account) -> list[tuple[str, str]]:
    """Cac ho so tai khoan nay duoc phep hoi ve: (patient_id, ten hien thi).

    Ban than truoc, roi den nguoi dang theo doi. KHONG suy tu `Account.role`
    (chi giu duoc mot gia tri) - mot nguoi vua la benh nhan vua cham bo/me la
    chuyen binh thuong."""
    ds: list[tuple[str, str]] = []
    if account.patient_id:
        p = db.get(Patient, account.patient_id)
        if p is not None:
            ds.append((p.id, "Bản thân"))

    rows = db.execute(
        select(Patient.id, Patient.full_name)
        .join(CaregiverLink, CaregiverLink.patient_id == Patient.id)
        .where(
            CaregiverLink.caregiver_account_id == account.id,
            CaregiverLink.status == "accepted",
        )
        .order_by(Patient.full_name)
    ).all()
    ds.extend((pid, ten) for pid, ten in rows if pid != account.patient_id)
    return ds


def _hoi_chon_doi_tuong(chat_id: int, ung_vien: list[tuple[str, str]]) -> None:
    _gui(
        chat_id,
        "Bạn đang hỏi về ai?",
        nut=[ten for _, ten in ung_vien],
    )


def _chon_doi_tuong(chat_id: int, text: str, ung_vien: list[tuple[str, str]]) -> str | None:
    """Khop cau tra loi voi mot ung vien. None neu khong khop."""
    goc = text.strip().casefold()
    for pid, ten in ung_vien:
        if goc == ten.casefold():
            _dang_hoi_ve[chat_id] = pid
            return pid
    return None


def _render(reply: str, citations: list, safety: str | None) -> str:
    """Doi ket qua Agent V2 thanh mot doan text Telegram.

    Nguon tham khao gan o cuoi, dang danh sach ngan - Telegram khong co khung
    "nguon" rieng nhu web, nhung bo han di thi benh nhan mat duong kiem chung
    thong tin thuoc men."""
    phan = [reply]

    if safety and safety.upper() in {"EMERGENCY", "RED_FLAG", "ACUTE_DANGER"}:
        phan.insert(
            0,
            "🚨 <b>DẤU HIỆU NGUY HIỂM</b>\nNếu bạn thấy nguy cấp, hãy gọi <b>115</b> ngay "
            "hoặc nhờ người thân đưa đi cấp cứu.\n",
        )

    if citations:
        dong = []
        for c in citations[:3]:
            ten = getattr(c, "title", None) or "Nguồn"
            url = getattr(c, "url", None)
            dong.append(f'• <a href="{url}">{ten}</a>' if url else f"• {ten}")
        phan.append("\n<i>Nguồn tham khảo</i>\n" + "\n".join(dong))

    return "\n".join(phan)


def xu_ly_tin_chat(db: Session, *, chat_id: int, text: str) -> bool:
    """Xu ly mot tin nhan thuong (khong phai /start). Tra ve True neu da tra loi.

    KHONG commit - nguoi goi quyet dinh ranh gioi giao dich.
    """
    link = db.execute(
        select(TelegramLink).where(TelegramLink.chat_id == chat_id)
    ).scalars().first()
    if link is None:
        _gui(
            chat_id,
            "Mình chưa biết bạn là ai 🙈\nBạn vào CapyMedi trên web, mục "
            "<b>Cài đặt → Thông báo → Telegram → Kết nối</b> để ghép tài khoản nhé.",
        )
        return True

    account = db.get(Account, link.account_id)
    if account is None:
        logger.warning("telegram_link %s tro toi account khong ton tai", link.id)
        _gui(chat_id, _LOI_CHUNG)
        return True

    ung_vien = _ung_vien(db, account)
    if not ung_vien:
        _gui(
            chat_id,
            "Tài khoản của bạn chưa gắn với hồ sơ bệnh nhân nào nên mình chưa tra cứu được.",
        )
        return True

    lenh = text.strip().casefold()

    # Doi doi tuong: chi co nghia khi that su co nhieu hon mot.
    if lenh in {"/doi", "/doi@" + (account.full_name or "").casefold()} or lenh == "/doi":
        if len(ung_vien) == 1:
            _gui(chat_id, f"Bạn chỉ đang theo dõi <b>{ung_vien[0][1]}</b> thôi nhé.")
            return True
        _dang_hoi_ve.pop(chat_id, None)
        _hoi_chon_doi_tuong(chat_id, ung_vien)
        return True

    patient_id = _dang_hoi_ve.get(chat_id)
    hop_le = {pid for pid, _ in ung_vien}

    if patient_id not in hop_le:
        # Chua chon, hoac lua chon cu khong con hop le (lien ket bi go).
        if len(ung_vien) == 1:
            patient_id = ung_vien[0][0]
            _dang_hoi_ve[chat_id] = patient_id
        else:
            vua_chon = _chon_doi_tuong(chat_id, text, ung_vien)
            if vua_chon is None:
                _hoi_chon_doi_tuong(chat_id, ung_vien)
                return True
            ten = next(t for p, t in ung_vien if p == vua_chon)
            _gui(chat_id, f"Rồi, mình sẽ trả lời về <b>{ten}</b>. Bạn hỏi gì nào?")
            return True

    # Rate limit theo patient_id, DUNG bo dem ma web dang dung - bot de nhan
    # hon mo app nen day la cho de bi lam dung nhat.
    try:
        _get_default_limiter().check(patient_id)
    except HTTPException:
        _gui(chat_id, "Bạn hỏi hơi nhanh rồi 😅 Chờ một chút rồi hỏi lại giúp mình nhé.")
        return True

    _bao_dang_go(chat_id)

    # Import tai cho: backend.api.agent_v2_routes keo theo ca cum agent, import
    # o dau file se tao vong lap (routes -> services -> routes).
    from backend.api.agent_v2_routes import run_agent_orchestration

    actor = CurrentUser(
        id=account.id,
        role=account.role,
        patient_id=account.patient_id,
        doctor_id=account.doctor_id,
    )
    yeu_cau = AgentV2OrchestrateRequest(
        patient_id=patient_id,
        message=text.strip()[:5000],
        # Mot cuoc hoi thoai lien tuc cho moi (chat, doi tuong) - doi nguoi
        # duoc hoi phai la ngu canh moi, khong keo theo tri nho cua nguoi truoc.
        conversation_id=f"telegram:{chat_id}:{patient_id}",
    )

    try:
        kq = run_agent_orchestration(yeu_cau, db, actor)
    except HTTPException as exc:
        if exc.status_code == 403:
            _gui(chat_id, "Bạn không có quyền xem thông tin của người này.")
        elif exc.status_code == 404:
            _gui(chat_id, "Mình không tìm thấy hồ sơ bệnh nhân này.")
        else:
            logger.warning("Agent tra loi %s cho chat %s", exc.status_code, chat_id)
            _gui(chat_id, _LOI_CHUNG)
        return True
    except Exception:  # noqa: BLE001 - mot cau hoi loi khong duoc lam chet bot
        logger.exception("Loi khi chay Agent V2 cho chat %s", chat_id)
        _gui(chat_id, _LOI_CHUNG)
        return True

    nut = [a.label for a in (kq.suggested_actions or [])][:4]
    _gui(chat_id, _render(kq.reply, kq.citations, kq.safety_disposition), nut=nut or None)
    return True
