"""backend/services/telegram.py - kenh nhac uong thuoc + canh bao nguoi than.

Tach 2 tang giong test_dose_push_reminder.py: xu_ly_start()/gio_dia_phuong()
test duoc voi noi dung gia lap (khong can bot that), con phan ghep token va
gui theo tai khoan can DB that.

KHONG co test nao goi ra api.telegram.org: moi duong ra ngoai deu di qua
_goi_bot_api(), test monkeypatch dung ham do - vua nhanh vua khong phu thuoc
mang, va van kiem tra duoc dung payload da dinh gui.

Tu migration 0059, telegram_link khoa theo ACCOUNT chu khong theo patient:
nguoi than cung phai nhan duoc canh bao ma ho khong co patient_id.
"""

import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.config import get_settings  # noqa: E402
from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import (  # noqa: E402
    Account,
    CaregiverLink,
    DoseEvent,
    Escalation,
    Patient,
    PatientNotificationPref,
    PushReminderSent,
    TelegramLink,
    TelegramLinkToken,
)
from backend.services import telegram as tg  # noqa: E402


class _FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {"ok": True, "result": []}
        self.text = str(self._payload)

    def json(self) -> dict:
        return self._payload


@pytest.fixture
def bot_gia(monkeypatch):
    """Thay _goi_bot_api bang ban ghi lai lenh - moi test dung chung."""
    da_goi: list[tuple[str, dict]] = []

    def _fake(method: str, payload: dict):
        da_goi.append((method, payload))
        return _FakeResponse()

    monkeypatch.setattr(tg, "_goi_bot_api", _fake)
    monkeypatch.setattr(tg, "telegram_is_configured", lambda: True)
    return da_goi


# --- Tang 1: khong can DB --------------------------------------------------

def test_gio_dia_phuong_doi_sang_gio_viet_nam(monkeypatch):
    """Bug that se xay ra neu quen buoc nay: benh nhan doc "hen 14:00" cho
    lieu 21:00 cua chinh minh, vi Telegram gui TEXT THO chu khong phai
    Web Push (trinh duyet tu doi theo gio may)."""
    settings = get_settings()
    monkeypatch.setattr(settings, "telegram_display_utc_offset_hours", 7)
    moc = datetime(2026, 8, 27, 14, 0, tzinfo=UTC)
    assert tg.gio_dia_phuong(moc) == "21:00"


def test_start_khong_kem_token_chi_huong_dan(bot_gia):
    """Nguoi dung tu tim thay bot roi bam Start (khong qua link tren web) -
    khong ghep duoc, nhung phai chi ho cach lam chu khong im lang."""
    assert tg.xu_ly_start(None, chat_id=1, username="a", text="/start") is False
    assert len(bot_gia) == 1
    method, payload = bot_gia[0]
    assert method == "sendMessage"
    assert "Kết nối Telegram" in payload["text"]


def test_tin_khong_phai_start_thi_bo_qua(bot_gia):
    assert tg.xu_ly_start(None, chat_id=1, username="a", text="xin chao") is False
    assert bot_gia == [], "khong duoc tra loi lung tung moi tin nhan gui toi bot"


# --- Tang 2: can DB that ---------------------------------------------------

def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


db_required = pytest.mark.skipif(
    not _db_available(), reason="Can Postgres that (docker compose up -d db)"
)


class _BoiCanh:
    """Gom cac id da tao de don sach o cuoi test."""

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
            db.query(TelegramLinkToken).filter(
                TelegramLinkToken.account_id.in_(bc.account_ids)
            ).delete(synchronize_session=False)
            db.query(CaregiverLink).filter(
                CaregiverLink.caregiver_account_id.in_(bc.account_ids)
            ).delete(synchronize_session=False)
            db.query(Account).filter(Account.id.in_(bc.account_ids)).delete(
                synchronize_session=False
            )
        if bc.patient_ids:
            for model in (DoseEvent, PushReminderSent, PatientNotificationPref, Escalation):
                db.query(model).filter(model.patient_id.in_(bc.patient_ids)).delete(
                    synchronize_session=False
                )
            db.query(Patient).filter(Patient.id.in_(bc.patient_ids)).delete(
                synchronize_session=False
            )
        db.commit()
    finally:
        db.close()


def _tao_benh_nhan(db, bc: _BoiCanh, *, ten: str = "Benh Nhan Test") -> tuple[str, str]:
    """Tao Patient + Account role=patient. Tra ve (patient_id, account_id)."""
    hau_to = uuid.uuid4().hex[:8]
    patient_id = f"TGT-{hau_to}"
    account_id = f"acc-{hau_to}"
    db.add(Patient(id=patient_id, full_name=ten))
    db.add(
        Account(
            id=account_id,
            full_name=ten,
            email=f"{account_id}@test.local",
            password_hash="x",
            role="patient",
            patient_id=patient_id,
        )
    )
    bc.patient_ids.append(patient_id)
    bc.account_ids.append(account_id)
    return patient_id, account_id


def _tao_nguoi_than(db, bc: _BoiCanh, patient_id: str, *, status: str = "accepted") -> str:
    hau_to = uuid.uuid4().hex[:8]
    account_id = f"cg-{hau_to}"
    db.add(
        Account(
            id=account_id,
            full_name="Nguoi Than Test",
            email=f"{account_id}@test.local",
            password_hash="x",
            role="caregiver",
        )
    )
    db.add(
        CaregiverLink(
            caregiver_account_id=account_id,
            patient_id=patient_id,
            relationship="Con gái",
            status=status,
        )
    )
    bc.account_ids.append(account_id)
    return account_id


# --- Ghep tai khoan --------------------------------------------------------

@db_required
def test_ghep_tai_khoan_thanh_cong(bot_gia, boi_canh):
    db = SessionLocal()
    try:
        _, account_id = _tao_benh_nhan(db, boi_canh)
        db.commit()

        token = tg.tao_token_ghep(db, account_id)
        db.commit()

        assert tg.xu_ly_start(db, chat_id=987654321, username="benhnhan", text=f"/start {token}")
        db.commit()

        link = db.query(TelegramLink).filter(TelegramLink.account_id == account_id).one()
        assert link.chat_id == 987654321
        assert link.username == "benhnhan"
        assert link.enabled is True
    finally:
        db.close()


@db_required
def test_token_chi_dung_duoc_1_lan(bot_gia, boi_canh):
    """Bam lai link cu trong lich su chat la chuyen thuong - phai tu choi
    nhung bao ro, khong duoc ghep them lan nua."""
    db = SessionLocal()
    try:
        _, account_id = _tao_benh_nhan(db, boi_canh)
        db.commit()
        token = tg.tao_token_ghep(db, account_id)
        db.commit()

        assert tg.xu_ly_start(db, chat_id=111, username=None, text=f"/start {token}") is True
        db.commit()
        assert tg.xu_ly_start(db, chat_id=222, username=None, text=f"/start {token}") is False
        db.commit()

        assert db.query(TelegramLink).filter(TelegramLink.account_id == account_id).count() == 1
    finally:
        db.close()


@db_required
def test_token_het_han_thi_tu_choi(bot_gia, boi_canh):
    db = SessionLocal()
    try:
        _, account_id = _tao_benh_nhan(db, boi_canh)
        db.add(
            TelegramLinkToken(
                token="token-da-het-han-test",
                account_id=account_id,
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
        db.commit()

        assert tg.xu_ly_start(db, chat_id=333, username=None, text="/start token-da-het-han-test") is False
        db.commit()
        assert db.query(TelegramLink).filter(TelegramLink.account_id == account_id).count() == 0
    finally:
        db.close()


@db_required
def test_ghep_lai_cung_chat_id_thi_chuyen_tai_khoan(bot_gia, boi_canh):
    """Neu tao dong thu 2, nguoi dung se nhan TRUNG 2 tin cho moi lieu thuoc -
    dung loi da tung xay ra o ban client (xem dose_push_reminder.py)."""
    chat_id = 444555666
    db = SessionLocal()
    try:
        _, acc1 = _tao_benh_nhan(db, boi_canh)
        _, acc2 = _tao_benh_nhan(db, boi_canh)
        db.commit()

        t1 = tg.tao_token_ghep(db, acc1)
        t2 = tg.tao_token_ghep(db, acc2)
        db.commit()

        assert tg.xu_ly_start(db, chat_id=chat_id, username="x", text=f"/start {t1}") is True
        db.commit()
        assert tg.xu_ly_start(db, chat_id=chat_id, username="x", text=f"/start {t2}") is True
        db.commit()

        assert db.query(TelegramLink).filter(TelegramLink.chat_id == chat_id).count() == 1
        assert db.query(TelegramLink).filter(TelegramLink.account_id == acc1).count() == 0
        assert db.query(TelegramLink).filter(TelegramLink.account_id == acc2).count() == 1
    finally:
        db.close()


# --- Gui tin ---------------------------------------------------------------

@db_required
def test_gui_toi_tai_khoan_chua_ghep_thi_tra_0(bot_gia, boi_canh):
    """Chua bat kenh Telegram KHONG phai loi - vong quet nhac thuoc van chay
    binh thuong, chi la khong co gi de gui."""
    db = SessionLocal()
    try:
        assert tg.send_telegram_to_account(db, f"acc-khong-ton-tai-{uuid.uuid4().hex[:6]}", "T", "B") == 0
        assert bot_gia == []
    finally:
        db.close()


@db_required
def test_benh_nhan_chan_bot_thi_xoa_lien_ket(monkeypatch, boi_canh):
    """403 = da chan bot. Giu lai dong nay chi ton cong goi API moi phut."""
    monkeypatch.setattr(tg, "telegram_is_configured", lambda: True)
    monkeypatch.setattr(tg, "_goi_bot_api", lambda method, payload: _FakeResponse(403))

    db = SessionLocal()
    try:
        _, account_id = _tao_benh_nhan(db, boi_canh)
        db.add(TelegramLink(account_id=account_id, chat_id=777888999, username=None))
        db.commit()

        assert tg.send_telegram_to_account(db, account_id, "T", "B") == 0
        db.commit()
        assert db.query(TelegramLink).filter(TelegramLink.account_id == account_id).count() == 0
    finally:
        db.close()


@db_required
def test_send_to_patient_tim_duoc_tai_khoan_tu_patient_id(bot_gia, boi_canh):
    """dose_push_reminder.py van goi theo patient_id - lop bao ngoai phai tu
    tra ra account tuong ung, neu khong ca kenh Telegram im lang."""
    db = SessionLocal()
    try:
        patient_id, account_id = _tao_benh_nhan(db, boi_canh)
        db.add(TelegramLink(account_id=account_id, chat_id=123123123, username=None))
        db.commit()

        assert tg.send_telegram_to_patient(db, patient_id, "Tieu de", "Noi dung") == 1
        assert bot_gia[0][1]["chat_id"] == 123123123
    finally:
        db.close()


@db_required
def test_benh_nhan_khong_co_tai_khoan_thi_khong_loi(bot_gia, boi_canh):
    """Ho so do bac si/admin tao, benh nhan chua bao gio dang nhap - khong co
    Telegram de gui, nhung KHONG duoc nem loi lam chet vong quet."""
    db = SessionLocal()
    try:
        patient_id = f"TGT-mo-coi-{uuid.uuid4().hex[:6]}"
        db.add(Patient(id=patient_id, full_name="Khong co tai khoan"))
        boi_canh.patient_ids.append(patient_id)
        db.commit()

        assert tg.send_telegram_to_patient(db, patient_id, "T", "B") == 0
        assert bot_gia == []
    finally:
        db.close()


# --- Canh bao nguoi than ---------------------------------------------------

@db_required
def test_canh_bao_toi_moi_nguoi_than_da_chap_nhan(bot_gia, boi_canh):
    db = SessionLocal()
    try:
        patient_id, _ = _tao_benh_nhan(db, boi_canh, ten="Bà Tư")
        cg1 = _tao_nguoi_than(db, boi_canh, patient_id)
        cg2 = _tao_nguoi_than(db, boi_canh, patient_id)
        db.commit()

        db.add(TelegramLink(account_id=cg1, chat_id=901, username=None))
        db.add(TelegramLink(account_id=cg2, chat_id=902, username=None))
        db.commit()

        assert tg.send_telegram_to_caregivers(db, patient_id, "⚠️ Cảnh báo", "Chưa uống thuốc") == 2
        chat_ids = sorted(p["chat_id"] for _, p in bot_gia)
        assert chat_ids == [901, 902]
    finally:
        db.close()


@db_required
def test_canh_bao_khong_gui_cho_loi_moi_chua_chap_nhan(bot_gia, boi_canh):
    """Dong "pending" la loi moi chua duoc dong y - gui canh bao suc khoe toi
    do la ro ri thong tin y te cho nguoi benh nhan chua cho phep."""
    db = SessionLocal()
    try:
        patient_id, _ = _tao_benh_nhan(db, boi_canh)
        cg = _tao_nguoi_than(db, boi_canh, patient_id, status="pending")
        db.commit()
        db.add(TelegramLink(account_id=cg, chat_id=903, username=None))
        db.commit()

        assert tg.send_telegram_to_caregivers(db, patient_id, "⚠️ Cảnh báo", "Chưa uống thuốc") == 0
        assert bot_gia == []
    finally:
        db.close()


@db_required
def test_canh_bao_co_ten_benh_nhan_trong_tin(bot_gia, boi_canh):
    """1 nguoi con theo doi ca bo lan me - nhan "Chua uong thuoc" ma khong
    biet cua ai thi canh bao thanh vo dung."""
    db = SessionLocal()
    try:
        patient_id, _ = _tao_benh_nhan(db, boi_canh, ten="Ông Bảy")
        cg = _tao_nguoi_than(db, boi_canh, patient_id)
        db.commit()
        db.add(TelegramLink(account_id=cg, chat_id=904, username=None))
        db.commit()

        tg.send_telegram_to_caregivers(db, patient_id, "⚠️ Cảnh báo", "Chưa uống thuốc")
        assert "Ông Bảy" in bot_gia[0][1]["text"]
    finally:
        db.close()


@db_required
def test_tao_canh_bao_tu_dong_day_telegram(bot_gia, boi_canh):
    """Test tich hop: tao_canh_bao_cho_nguoi_than() phai GUI THAT, khong chi
    ghi DB roi danh dau notified=['caregiver'] nhu truoc."""
    from backend.services.caregiver_escalation import tao_canh_bao_cho_nguoi_than

    db = SessionLocal()
    try:
        patient_id, _ = _tao_benh_nhan(db, boi_canh, ten="Cụ Năm")
        cg = _tao_nguoi_than(db, boi_canh, patient_id)
        db.commit()
        db.add(TelegramLink(account_id=cg, chat_id=905, username=None))
        db.commit()

        tao_canh_bao_cho_nguoi_than(
            db,
            patient_id=patient_id,
            severity="MEDIUM",
            trigger="dose_unconfirmed",
            reason="Chưa xác nhận uống Paracetamol sau 3 lần nhắc",
        )
        db.commit()

        assert len(bot_gia) == 1, "canh bao khong duoc day toi nguoi than"
        assert "Cụ Năm" in bot_gia[0][1]["text"]
        assert db.query(Escalation).filter(Escalation.patient_id == patient_id).count() == 1
    finally:
        db.close()


@db_required
def test_gui_telegram_hong_van_ghi_duoc_canh_bao(monkeypatch, boi_canh):
    """Canh bao PHAI vao DB du Telegram loi mang - man hinh Gia dinh van la
    duong nhan tin cuoi cung."""
    from backend.services.caregiver_escalation import tao_canh_bao_cho_nguoi_than

    monkeypatch.setattr(tg, "telegram_is_configured", lambda: True)

    def _no(method, payload):
        raise RuntimeError("mang loi")

    monkeypatch.setattr(tg, "_goi_bot_api", _no)

    db = SessionLocal()
    try:
        patient_id, _ = _tao_benh_nhan(db, boi_canh)
        cg = _tao_nguoi_than(db, boi_canh, patient_id)
        db.commit()
        db.add(TelegramLink(account_id=cg, chat_id=906, username=None))
        db.commit()

        tao_canh_bao_cho_nguoi_than(
            db,
            patient_id=patient_id,
            severity="HIGH",
            trigger="safety_redflag",
            reason="Dấu hiệu nguy hiểm",
        )
        db.commit()

        assert db.query(Escalation).filter(Escalation.patient_id == patient_id).count() == 1
    finally:
        db.close()


# --- Bat/tat + hai tang tuy chon -------------------------------------------

@db_required
def test_tat_thi_khong_gui_nhung_van_giu_lien_ket(bot_gia, boi_canh):
    """Diem khac biet chinh voi DELETE /telegram/link: tat di van con dong
    trong bang, bat lai chi la 1 cu gat chu khong phai lam lai ca luong ghep."""
    db = SessionLocal()
    try:
        _, account_id = _tao_benh_nhan(db, boi_canh)
        db.add(TelegramLink(account_id=account_id, chat_id=555000111, username=None, enabled=False))
        db.commit()

        assert tg.send_telegram_to_account(db, account_id, "T", "B") == 0
        assert bot_gia == [], "da tat ma van goi Bot API"
        assert db.query(TelegramLink).filter(TelegramLink.account_id == account_id).count() == 1
    finally:
        db.close()


@db_required
def test_ghep_lai_thi_tu_bat_lai(bot_gia, boi_canh):
    """Nguoi dung tat di, sau do vao web bam Ket noi lai - phai nhan duoc tin
    ngay. Neu giu nguyen enabled=False ho se tuong tinh nang hong."""
    chat_id = 555000333
    db = SessionLocal()
    try:
        _, account_id = _tao_benh_nhan(db, boi_canh)
        db.add(TelegramLink(account_id=account_id, chat_id=chat_id, username=None, enabled=False))
        db.commit()

        token = tg.tao_token_ghep(db, account_id)
        db.commit()
        assert tg.xu_ly_start(db, chat_id=chat_id, username="x", text=f"/start {token}") is True
        db.commit()

        assert db.query(TelegramLink).filter(TelegramLink.chat_id == chat_id).one().enabled is True
    finally:
        db.close()


@db_required
def test_tat_tang_1_thi_khong_kenh_nao_gui(bot_gia, boi_canh, monkeypatch):
    """Tat "Nhac uong thuoc" phai chan CA Web Push lan Telegram, du tung kenh
    van dang bat - dung thu tu nguoi dung thay tren man hinh Cai dat."""
    from backend.services import dose_push_reminder as dpr

    da_gui_push: list[str] = []
    monkeypatch.setattr(dpr, "send_push_to_patient", lambda db, pid, t, b: da_gui_push.append(pid) or 0)

    now = datetime.now(UTC)
    slot = now - timedelta(minutes=2)
    db = SessionLocal()
    try:
        patient_id, account_id = _tao_benh_nhan(db, boi_canh)
        db.add(TelegramLink(account_id=account_id, chat_id=666000111, username=None))
        db.add(PatientNotificationPref(patient_id=patient_id, dose_reminder_enabled=False))
        db.add(
            DoseEvent(
                prescription_id="presc-test-pref",
                patient_id=patient_id,
                scheduled_at=slot,
                window_start=slot - timedelta(minutes=30),
                window_end=slot + timedelta(minutes=30),
                status="PENDING",
                expected_items=[{"drug_id": "x", "ten_thuoc": "Thuoc A", "so_vien": 1}],
            )
        )
        db.commit()

        # Van tra 1: moc DA duoc xu ly (co ghi PushReminderSent), chi la khong
        # gui gi - neu tra 0 thi vong quet moi 60 giay se lam lai mai.
        assert dpr.quet_va_day_nhac(db, now=now) == 1
        assert da_gui_push == [], "tat tang 1 ma van gui Web Push"
        assert bot_gia == [], "tat tang 1 ma van gui Telegram"
    finally:
        db.close()


@db_required
def test_tat_web_push_van_gui_telegram(bot_gia, boi_canh, monkeypatch):
    """Tang 2: tat rieng 1 kenh khong duoc lam chet kenh con lai."""
    from backend.services import dose_push_reminder as dpr

    da_gui_push: list[str] = []
    monkeypatch.setattr(dpr, "send_push_to_patient", lambda db, pid, t, b: da_gui_push.append(pid) or 0)

    now = datetime.now(UTC)
    slot = now - timedelta(minutes=2)
    db = SessionLocal()
    try:
        patient_id, account_id = _tao_benh_nhan(db, boi_canh)
        db.add(TelegramLink(account_id=account_id, chat_id=666000222, username=None))
        db.add(
            PatientNotificationPref(
                patient_id=patient_id, dose_reminder_enabled=True, web_push_enabled=False
            )
        )
        db.add(
            DoseEvent(
                prescription_id="presc-test-pref",
                patient_id=patient_id,
                scheduled_at=slot,
                window_start=slot - timedelta(minutes=30),
                window_end=slot + timedelta(minutes=30),
                status="PENDING",
                expected_items=[{"drug_id": "x", "ten_thuoc": "Thuoc A", "so_vien": 1}],
            )
        )
        db.commit()

        assert dpr.quet_va_day_nhac(db, now=now) == 1
        assert da_gui_push == [], "da tat Web Push ma van gui"
        assert len(bot_gia) == 1, "tat Web Push khong duoc lam chet Telegram"
    finally:
        db.close()


@db_required
def test_chua_co_dong_tuy_chon_thi_mac_dinh_bat_het():
    """Nguoi dung chua bao gio vao Cai dat phai duoc nhac binh thuong - mac
    dinh TAT se tao ra loi im lang khong ai bao cao duoc."""
    from backend.services.notification_pref import lay_tuy_chon

    db = SessionLocal()
    try:
        tc = lay_tuy_chon(db, f"test-chua-ton-tai-{uuid.uuid4().hex[:8]}")
        assert tc.dose_reminder_enabled is True
        assert tc.web_push_enabled is True
    finally:
        db.close()


@db_required
def test_dat_tung_truong_khong_ghi_de_truong_kia(boi_canh):
    """Gat 1 cong tac khong duoc lam doi cong tac con lai (2 tab cung mo)."""
    from backend.services.notification_pref import dat_tuy_chon, lay_tuy_chon

    db = SessionLocal()
    try:
        patient_id, _ = _tao_benh_nhan(db, boi_canh)
        db.commit()

        dat_tuy_chon(db, patient_id, web_push_enabled=False)
        db.commit()
        dat_tuy_chon(db, patient_id, dose_reminder_enabled=False)
        db.commit()

        tc = lay_tuy_chon(db, patient_id)
        assert tc.web_push_enabled is False, "bi ghi de mat"
        assert tc.dose_reminder_enabled is False
    finally:
        db.close()


# --- Hai vai tro tren cung 1 tai khoan -------------------------------------

@db_required
def test_vua_la_benh_nhan_vua_la_nguoi_than(bot_gia, boi_canh):
    """Bug that: gate theo Account.role cat mat mot nua vai tro. Nguoi con
    vua uong thuoc cua chinh minh vua theo doi me - phai nhan CA HAI loai tin
    tren cung 1 Telegram."""
    from backend.services.notification_pref import dang_theo_doi_ai

    db = SessionLocal()
    try:
        me_id, _ = _tao_benh_nhan(db, boi_canh, ten="Mẹ Sáu")
        con_patient_id, con_account_id = _tao_benh_nhan(db, boi_canh, ten="Chị Ba")
        # Chinh tai khoan benh nhan "con" cung theo doi "me".
        db.add(
            CaregiverLink(
                caregiver_account_id=con_account_id,
                patient_id=me_id,
                relationship="Con gái",
                status="accepted",
            )
        )
        db.add(TelegramLink(account_id=con_account_id, chat_id=808001, username=None))
        db.commit()

        assert dang_theo_doi_ai(db, con_account_id) is True, "khong nhan ra vai tro nguoi than"

        # Vai tro benh nhan: nhac uong thuoc cua CHINH minh
        assert tg.send_telegram_to_patient(db, con_patient_id, "Nhắc", "Uống thuốc") == 1
        # Vai tro nguoi than: canh bao ve me
        assert tg.send_telegram_to_caregivers(db, me_id, "⚠️ Cảnh báo", "Chưa uống thuốc") == 1

        assert len(bot_gia) == 2
        assert all(p["chat_id"] == 808001 for _, p in bot_gia), "ca hai loai tin ve cung 1 Telegram"
        assert "Mẹ Sáu" in bot_gia[1][1]["text"], "canh bao phai ghi ro la ve ai"
    finally:
        db.close()


@db_required
def test_nguoi_than_thuan_tuy_van_duoc_nhan_dien(boi_canh):
    """Nguoi than khong co ho so benh nhan (patient_id = None) van phai qua
    duoc cua - truoc day bi 403 vi role khong khop."""
    from backend.services.notification_pref import dang_theo_doi_ai

    db = SessionLocal()
    try:
        patient_id, _ = _tao_benh_nhan(db, boi_canh)
        cg = _tao_nguoi_than(db, boi_canh, patient_id)
        db.commit()

        assert dang_theo_doi_ai(db, cg) is True
    finally:
        db.close()


@db_required
def test_loi_moi_pending_khong_tinh_la_nguoi_than(boi_canh):
    """Chua chap nhan loi moi thi chua duoc coi la nguoi than - neu khong,
    bat ky ai gui loi moi cung mo duoc kenh nhan tin y te."""
    from backend.services.notification_pref import dang_theo_doi_ai

    db = SessionLocal()
    try:
        patient_id, _ = _tao_benh_nhan(db, boi_canh)
        cg = _tao_nguoi_than(db, boi_canh, patient_id, status="pending")
        db.commit()

        assert dang_theo_doi_ai(db, cg) is False
    finally:
        db.close()
