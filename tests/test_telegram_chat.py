"""backend/services/telegram_chat.py - bot tra loi nhu chatbot tren web.

KHONG test lai Agent V2 o day: no da co bo test rieng va rat lon. Test o day
chi kiem tra DUNG phan module nay chiu trach nhiem - doi chat_id thanh danh
tinh, chon dung doi tuong duoc hoi, va doi ket qua thanh tin Telegram. Agent
duoc thay bang ban gia lap de test chay nhanh va khong goi LLM that.
"""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import (  # noqa: E402
    Account,
    CaregiverLink,
    Patient,
    TelegramLink,
)
from backend.services import telegram_chat as tc  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that")


class _KetQuaGia:
    def __init__(self, reply="Tra loi mau", actions=(), citations=(), safety=None):
        self.reply = reply
        self.suggested_actions = list(actions)
        self.citations = list(citations)
        self.safety_disposition = safety


class _ActionGia:
    def __init__(self, label):
        self.label = label


class _CitationGia:
    def __init__(self, title, url=None):
        self.title = title
        self.url = url


@pytest.fixture
def bot_gia(monkeypatch):
    """Ghi lai moi lenh gui Telegram thay vi goi mang that."""
    da_goi: list[tuple[str, dict]] = []
    monkeypatch.setattr(tc, "_goi_bot_api", lambda method, payload: da_goi.append((method, payload)))
    return da_goi


@pytest.fixture
def agent_gia(monkeypatch):
    """Thay Agent V2 - test o day khong kiem tra chat luong tra loi."""
    da_goi: list = []

    def _fake(yeu_cau, db, actor):
        da_goi.append(yeu_cau)
        return _KetQuaGia()

    monkeypatch.setattr("backend.api.agent_v2_routes.run_agent_orchestration", _fake)
    return da_goi


@pytest.fixture(autouse=True)
def _xoa_lua_chon():
    tc._dang_hoi_ve.clear()
    yield
    tc._dang_hoi_ve.clear()


class _BoiCanh:
    def __init__(self):
        self.account_ids: list[str] = []
        self.patient_ids: list[str] = []


@pytest.fixture
def boi_canh():
    bc = _BoiCanh()
    yield bc
    db = SessionLocal()
    try:
        if bc.account_ids:
            db.query(TelegramLink).filter(TelegramLink.account_id.in_(bc.account_ids)).delete(
                synchronize_session=False
            )
            db.query(CaregiverLink).filter(
                CaregiverLink.caregiver_account_id.in_(bc.account_ids)
            ).delete(synchronize_session=False)
            db.query(Account).filter(Account.id.in_(bc.account_ids)).delete(synchronize_session=False)
        if bc.patient_ids:
            db.query(Patient).filter(Patient.id.in_(bc.patient_ids)).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _tao_benh_nhan(db, bc, *, ten="Benh Nhan Test") -> tuple[str, str]:
    h = uuid.uuid4().hex[:8]
    pid, aid = f"TGC-{h}", f"tgc-{h}"
    db.add(Patient(id=pid, full_name=ten))
    db.add(
        Account(
            id=aid,
            full_name=ten,
            email=f"{aid}@test.local",
            password_hash="x",
            role="patient",
            patient_id=pid,
        )
    )
    bc.patient_ids.append(pid)
    bc.account_ids.append(aid)
    return pid, aid


def _noi_telegram(db, account_id: str, chat_id: int) -> None:
    db.add(TelegramLink(account_id=account_id, chat_id=chat_id, username=None))


def _text_da_gui(da_goi) -> list[str]:
    return [p["text"] for m, p in da_goi if m == "sendMessage"]


# --- Chua ghep tai khoan ---------------------------------------------------

def test_chua_ghep_thi_huong_dan_ket_noi(bot_gia, boi_canh):
    """Nguoi la nhan tin cho bot - khong duoc im lang, va tuyet doi khong
    duoc tra loi gi ve thuoc men."""
    db = SessionLocal()
    try:
        assert tc.xu_ly_tin_chat(db, chat_id=999001, text="tôi uống thuốc gì?") is True
        tins = _text_da_gui(bot_gia)
        assert len(tins) == 1
        assert "Kết nối" in tins[0]
    finally:
        db.close()


# --- Mot doi tuong: khong bao gio thay buoc chon ---------------------------

def test_chi_co_mot_doi_tuong_thi_hoi_thang(bot_gia, agent_gia, boi_canh):
    db = SessionLocal()
    try:
        pid, aid = _tao_benh_nhan(db, boi_canh)
        _noi_telegram(db, aid, 999002)
        db.commit()

        assert tc.xu_ly_tin_chat(db, chat_id=999002, text="hôm nay uống thuốc gì?") is True

        assert len(agent_gia) == 1, "phai goi thang Agent, khong hoi chon ai"
        assert agent_gia[0].patient_id == pid
        assert "Tra loi mau" in _text_da_gui(bot_gia)[-1]
    finally:
        db.close()


def test_conversation_id_gan_voi_chat_va_doi_tuong(bot_gia, agent_gia, boi_canh):
    """Doi nguoi duoc hoi phai la ngu canh moi - khong keo theo tri nho cua
    nguoi truoc."""
    db = SessionLocal()
    try:
        pid, aid = _tao_benh_nhan(db, boi_canh)
        _noi_telegram(db, aid, 999003)
        db.commit()

        tc.xu_ly_tin_chat(db, chat_id=999003, text="xin chào")
        assert agent_gia[0].conversation_id == f"telegram:999003:{pid}"
    finally:
        db.close()


# --- Nhieu doi tuong: phai hoi truoc --------------------------------------

def test_nhieu_doi_tuong_thi_hoi_chon_truoc(bot_gia, agent_gia, boi_canh):
    """Chi Ba vua uong thuoc cua minh vua cham me - bot khong duoc doan."""
    db = SessionLocal()
    try:
        me_id, _ = _tao_benh_nhan(db, boi_canh, ten="Mẹ Sáu")
        con_pid, con_aid = _tao_benh_nhan(db, boi_canh, ten="Chị Ba")
        db.add(
            CaregiverLink(
                caregiver_account_id=con_aid,
                patient_id=me_id,
                relationship="Con gái",
                status="accepted",
            )
        )
        _noi_telegram(db, con_aid, 999004)
        db.commit()

        tc.xu_ly_tin_chat(db, chat_id=999004, text="hôm nay uống thuốc gì?")
        assert agent_gia == [], "chua chon ai ma da goi Agent"

        method, payload = bot_gia[-1]
        assert "hỏi về ai" in payload["text"]
        nhan = [b[0]["text"] for b in payload["reply_markup"]["keyboard"]]
        assert nhan == ["Bản thân", "Mẹ Sáu"]
    finally:
        db.close()


def test_chon_xong_thi_nho_cho_cac_cau_sau(bot_gia, agent_gia, boi_canh):
    db = SessionLocal()
    try:
        me_id, _ = _tao_benh_nhan(db, boi_canh, ten="Mẹ Sáu")
        _, con_aid = _tao_benh_nhan(db, boi_canh, ten="Chị Ba")
        db.add(
            CaregiverLink(
                caregiver_account_id=con_aid,
                patient_id=me_id,
                relationship="Con gái",
                status="accepted",
            )
        )
        _noi_telegram(db, con_aid, 999005)
        db.commit()

        tc.xu_ly_tin_chat(db, chat_id=999005, text="hỏi gì đó")     # -> hoi chon
        tc.xu_ly_tin_chat(db, chat_id=999005, text="Mẹ Sáu")        # -> chon
        assert agent_gia == [], "buoc chon khong duoc tinh la cau hoi"

        tc.xu_ly_tin_chat(db, chat_id=999005, text="hôm nay uống thuốc gì?")
        assert len(agent_gia) == 1
        assert agent_gia[0].patient_id == me_id

        # Cau tiep theo KHONG duoc hoi lai.
        tc.xu_ly_tin_chat(db, chat_id=999005, text="còn tác dụng phụ?")
        assert len(agent_gia) == 2
        assert agent_gia[1].patient_id == me_id
    finally:
        db.close()


def test_lenh_doi_cho_chon_lai(bot_gia, agent_gia, boi_canh):
    db = SessionLocal()
    try:
        me_id, _ = _tao_benh_nhan(db, boi_canh, ten="Mẹ Sáu")
        _, con_aid = _tao_benh_nhan(db, boi_canh, ten="Chị Ba")
        db.add(
            CaregiverLink(
                caregiver_account_id=con_aid,
                patient_id=me_id,
                relationship="Con gái",
                status="accepted",
            )
        )
        _noi_telegram(db, con_aid, 999006)
        db.commit()

        tc.xu_ly_tin_chat(db, chat_id=999006, text="x")
        tc.xu_ly_tin_chat(db, chat_id=999006, text="Mẹ Sáu")
        tc.xu_ly_tin_chat(db, chat_id=999006, text="/doi")

        assert "hỏi về ai" in _text_da_gui(bot_gia)[-1]
        tc.xu_ly_tin_chat(db, chat_id=999006, text="Bản thân")
        tc.xu_ly_tin_chat(db, chat_id=999006, text="thuốc gì?")
        assert agent_gia[-1].patient_id != me_id
    finally:
        db.close()


def test_doi_khi_chi_co_mot_doi_tuong_thi_bao_ro(bot_gia, agent_gia, boi_canh):
    db = SessionLocal()
    try:
        _, aid = _tao_benh_nhan(db, boi_canh, ten="Ông Bảy")
        _noi_telegram(db, aid, 999007)
        db.commit()

        tc.xu_ly_tin_chat(db, chat_id=999007, text="/doi")
        assert "chỉ đang theo dõi" in _text_da_gui(bot_gia)[-1]
        assert agent_gia == []
    finally:
        db.close()


# --- Render ket qua --------------------------------------------------------

def test_nut_goi_y_thanh_ban_phim(bot_gia, boi_canh, monkeypatch):
    """`_typed_action()` khop theo NHAN nen text cua nut duoc server hieu y
    het mot cu bam nut that - khong can callback_query."""
    monkeypatch.setattr(
        "backend.api.agent_v2_routes.run_agent_orchestration",
        lambda y, d, a: _KetQuaGia(actions=[_ActionGia("Tác dụng phụ"), _ActionGia("Liều dùng")]),
    )
    db = SessionLocal()
    try:
        _, aid = _tao_benh_nhan(db, boi_canh)
        _noi_telegram(db, aid, 999008)
        db.commit()

        tc.xu_ly_tin_chat(db, chat_id=999008, text="paracetamol")
        payload = bot_gia[-1][1]
        nhan = [b[0]["text"] for b in payload["reply_markup"]["keyboard"]]
        assert nhan == ["Tác dụng phụ", "Liều dùng"]
    finally:
        db.close()


def test_canh_bao_nguy_hiem_len_dau_tin(bot_gia, boi_canh, monkeypatch):
    """Dau hieu nguy hiem phai o DAU tin - de cuoi thi benh nhan co the
    khong doc toi."""
    monkeypatch.setattr(
        "backend.api.agent_v2_routes.run_agent_orchestration",
        lambda y, d, a: _KetQuaGia(reply="Bạn nên đi khám.", safety="EMERGENCY"),
    )
    db = SessionLocal()
    try:
        _, aid = _tao_benh_nhan(db, boi_canh)
        _noi_telegram(db, aid, 999009)
        db.commit()

        tc.xu_ly_tin_chat(db, chat_id=999009, text="tôi đau ngực dữ dội")
        tin = _text_da_gui(bot_gia)[-1]
        assert tin.index("115") < tin.index("Bạn nên đi khám")
    finally:
        db.close()


def test_co_nguon_tham_khao(bot_gia, boi_canh, monkeypatch):
    monkeypatch.setattr(
        "backend.api.agent_v2_routes.run_agent_orchestration",
        lambda y, d, a: _KetQuaGia(citations=[_CitationGia("Vinmec", "https://vinmec.com/x")]),
    )
    db = SessionLocal()
    try:
        _, aid = _tao_benh_nhan(db, boi_canh)
        _noi_telegram(db, aid, 999010)
        db.commit()

        tc.xu_ly_tin_chat(db, chat_id=999010, text="paracetamol là gì")
        tin = _text_da_gui(bot_gia)[-1]
        assert "Nguồn tham khảo" in tin
        assert "https://vinmec.com/x" in tin
    finally:
        db.close()


def test_agent_loi_thi_bao_nhe_nhang_khong_no(bot_gia, boi_canh, monkeypatch):
    """Mot cau hoi loi khong duoc lam chet bot, va khong duoc do stack trace
    ra cho benh nhan."""
    def _no(y, d, a):
        raise RuntimeError("LLM hong")

    monkeypatch.setattr("backend.api.agent_v2_routes.run_agent_orchestration", _no)
    db = SessionLocal()
    try:
        _, aid = _tao_benh_nhan(db, boi_canh)
        _noi_telegram(db, aid, 999011)
        db.commit()

        assert tc.xu_ly_tin_chat(db, chat_id=999011, text="hỏi gì đó") is True
        tin = _text_da_gui(bot_gia)[-1]
        assert "trục trặc" in tin
        assert "RuntimeError" not in tin and "LLM hong" not in tin
    finally:
        db.close()


def test_khong_co_quyen_thi_bao_ro(bot_gia, boi_canh, monkeypatch):
    from fastapi import HTTPException

    def _cam(y, d, a):
        raise HTTPException(status_code=403, detail="x")

    monkeypatch.setattr("backend.api.agent_v2_routes.run_agent_orchestration", _cam)
    db = SessionLocal()
    try:
        _, aid = _tao_benh_nhan(db, boi_canh)
        _noi_telegram(db, aid, 999012)
        db.commit()

        tc.xu_ly_tin_chat(db, chat_id=999012, text="hỏi gì đó")
        assert "không có quyền" in _text_da_gui(bot_gia)[-1]
    finally:
        db.close()


def test_bao_dang_go_truoc_khi_goi_agent(bot_gia, agent_gia, boi_canh):
    """Agent mat vai giay - khong co tin hieu gi thi benh nhan tuong bot chet."""
    db = SessionLocal()
    try:
        _, aid = _tao_benh_nhan(db, boi_canh)
        _noi_telegram(db, aid, 999013)
        db.commit()

        tc.xu_ly_tin_chat(db, chat_id=999013, text="xin chào")
        assert bot_gia[0][0] == "sendChatAction"
        assert bot_gia[0][1]["action"] == "typing"
    finally:
        db.close()
