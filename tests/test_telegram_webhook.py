"""POST /api/v1/telegram/webhook (backend/api/telegram_routes.py) - test qua
FastAPI TestClient that, cung pattern voi tests/test_push_routes.py.

Route nay khac moi route khac trong repo: nguoi goi la TELEGRAM chu khong
phai nguoi dung da dang nhap, nen khong co get_current_user. Lop bao ve duy
nhat la secret trong header - vi vay phan xac thuc phai duoc test ky hon binh
thuong: route nam tren Internet cong khai, thung o day nghia la bat ky ai
cung gia duoc "tin nhan cua benh nhan".
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from backend.config import get_settings  # noqa: E402

_SECRET = "secret-test-webhook-khong-doan-duoc"
_URL = "/api/v1/telegram/webhook"


@pytest.fixture
def che_do_webhook(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "telegram_update_mode", "webhook")
    monkeypatch.setattr(settings, "telegram_webhook_secret", _SECRET)
    return settings


@pytest.mark.asyncio
async def test_dung_secret_thi_nhan_200(client, che_do_webhook, monkeypatch):
    """Update hop le nhung khong phai /start - van phai 200 de Telegram thoi
    gui lai (xem docstring route)."""
    from backend.services import telegram as tg

    monkeypatch.setattr(tg, "_goi_bot_api", lambda method, payload: None)
    body = {"update_id": 1, "message": {"chat": {"id": 5, "type": "private"}, "text": "xin chao"}}
    resp = await client.post(_URL, json=body, headers={"X-Telegram-Bot-Api-Secret-Token": _SECRET})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_thieu_secret_thi_403(client, che_do_webhook):
    body = {"update_id": 2, "message": {"chat": {"id": 5, "type": "private"}, "text": "hi"}}
    resp = await client.post(_URL, json=body)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_sai_secret_thi_403(client, che_do_webhook):
    body = {"update_id": 3, "message": {"chat": {"id": 5, "type": "private"}, "text": "hi"}}
    resp = await client.post(
        _URL, json=body, headers={"X-Telegram-Bot-Api-Secret-Token": "sai-be-bet"}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_server_chua_dat_secret_thi_403(client, monkeypatch):
    """Secret rong = tu choi TAT CA, khong phai "bo qua kiem tra". Neu de lot,
    ai cung POST duoc tin gia vao he thong."""
    settings = get_settings()
    monkeypatch.setattr(settings, "telegram_update_mode", "webhook")
    monkeypatch.setattr(settings, "telegram_webhook_secret", "")

    body = {"update_id": 4, "message": {"chat": {"id": 5, "type": "private"}, "text": "hi"}}
    resp = await client.post(_URL, json=body, headers={"X-Telegram-Bot-Api-Secret-Token": ""})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_dang_chay_polling_thi_404(client, monkeypatch):
    """Che do polling ma van co request toi day = cau hinh sai hoac nguoi la
    do cua. Tu choi thay vi xu ly hai lan."""
    settings = get_settings()
    monkeypatch.setattr(settings, "telegram_update_mode", "polling")
    monkeypatch.setattr(settings, "telegram_webhook_secret", _SECRET)

    body = {"update_id": 5, "message": {"chat": {"id": 5, "type": "private"}, "text": "hi"}}
    resp = await client.post(_URL, json=body, headers={"X-Telegram-Bot-Api-Secret-Token": _SECRET})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_body_khong_phai_json_van_200(client, che_do_webhook):
    """Body la khong duoc lam Telegram gui lai mai mai."""
    resp = await client.post(
        _URL,
        content=b"khong-phai-json",
        headers={
            "X-Telegram-Bot-Api-Secret-Token": _SECRET,
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_xu_ly_loi_van_tra_200(client, che_do_webhook, monkeypatch):
    """Loi khi xu ly cung phai tra 200: Telegram coi ma khac 200 la "chua
    nhan duoc" va gui lai update do lien tuc - 1 tin loi thanh vong lap."""
    from backend.services import telegram as tg

    def _no(db, upd):
        raise RuntimeError("hong")

    monkeypatch.setattr(tg, "xu_ly_mot_update", _no)
    monkeypatch.setattr("backend.api.telegram_routes.xu_ly_mot_update", _no)

    body = {"update_id": 6, "message": {"chat": {"id": 5, "type": "private"}, "text": "hi"}}
    resp = await client.post(_URL, json=body, headers={"X-Telegram-Bot-Api-Secret-Token": _SECRET})
    assert resp.status_code == 200
