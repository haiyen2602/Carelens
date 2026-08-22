"""HTTP contract tests cho luong yeu cau bo sung thuoc (FB-14).

Vi sao can nhom test nay tach khoi test service: `drug_request` la mot CONG
AN TOAN. O tang service, "chi admin duyet" khong duoc bieu dien o dau ca -
no nam trong `Depends(require_role("admin"))` cua tang route. Test service
chay qua duoc 100% van khong chung minh duoc dieu do.

Mock tang service (giong tests/test_admin_drug_routes.py): muc tieu o day la
HOP DONG HTTP - phan quyen, hinh dang request/response, ma loi - khong phai
logic nghiep vu (da co tests/services/drug_requests/test_service_db.py chay
tren Postgres that).
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.api import drug_request_routes
from backend.api.security import CurrentUser, get_current_user
from backend.db.base import get_db
from backend.db.models import DrugRequest
from backend.main import app
from backend.services.drug_requests.errors import (
    ThuocBiKiemSoatError,
    TrangThaiYeuCauKhongHopLeError,
    YeuCauThuocKhongTonTaiError,
)

DOCTOR_ID = "bs-1"


async def _doctor() -> CurrentUser:
    return CurrentUser(id="acc-bs-1", role="doctor", patient_id=None, doctor_id=DOCTOR_ID)


async def _admin() -> CurrentUser:
    return CurrentUser(id="acc-admin-1", role="admin", patient_id=None, doctor_id=None)


async def _patient() -> CurrentUser:
    return CurrentUser(id="acc-bn-1", role="patient", patient_id="bn-1", doctor_id=None)


def _db():
    yield Mock()


def _row(**overrides) -> DrugRequest:
    """DrugRequest roi (khong gan session) - vua du de model_validate doc."""
    row = DrugRequest(
        id="yc-1",
        requested_by_doctor_id=DOCTOR_ID,
        ten_thuoc="Thuoc thu nghiem",
        dang_thuoc="Vien nen",
        duong_dung="Uong",
        ham_luong=None,
        tong_so_luong=None,
        ly_do=None,
        status="PENDING",
        reviewed_by_account_id=None,
        reviewed_at=None,
        review_note=None,
        approved_drug_id=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


@pytest.fixture(autouse=True)
def dependencies():
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _doctor
    yield
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


_PAYLOAD = {"ten_thuoc": "Thuoc thu nghiem", "dang_thuoc": "Vien nen", "duong_dung": "Uong"}


# ---------------------------------------------------------------------------
# Phan quyen - ly do chinh nhom test nay ton tai
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_benh_nhan_khong_gui_duoc_yeu_cau(client: AsyncClient):
    app.dependency_overrides[get_current_user] = _patient

    response = await client.post("/api/v1/drug-requests", json=_PAYLOAD)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_bac_si_khong_duyet_duoc_yeu_cau_cua_chinh_minh(client: AsyncClient):
    """Diem quan trong nhat cua ca file. Neu bac si vua gui vua duyet duoc thi
    cong duyet chi la mot cu bam thua, va FB-14 quay lai nguyen ven."""
    response = await client.post("/api/v1/admin/drug-requests/yc-1/approve", json={})

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_bac_si_khong_xem_duoc_ca_hang_doi(client: AsyncClient):
    response = await client.get("/api/v1/admin/drug-requests")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_bac_si_khong_tu_choi_duoc(client: AsyncClient):
    response = await client.post(
        "/api/v1/admin/drug-requests/yc-1/reject", json={"note": "khong hop le"}
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_khong_gui_duoc_yeu_cau(client: AsyncClient):
    """Endpoint gui yeu cau danh cho bac si. Admin tu gui roi tu duyet cung la
    mot nguoi lam ca hai dau."""
    app.dependency_overrides[get_current_user] = _admin

    response = await client.post("/api/v1/drug-requests", json=_PAYLOAD)

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# doctor_id lay tu JWT, KHONG nhan tu ben ngoai
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_doctor_id_lay_tu_jwt_khong_phai_tu_body(client: AsyncClient, monkeypatch):
    """Nhan doctor_id tu body la bac si A gui yeu cau duoi ten bac si B."""
    service = Mock(return_value=_row())
    monkeypatch.setattr(drug_request_routes, "tao_yeu_cau", service)

    response = await client.post(
        "/api/v1/drug-requests", json={**_PAYLOAD, "doctor_id": "bs-gia-mao"}
    )

    assert response.status_code == 201
    assert service.call_args.kwargs["doctor_id"] == DOCTOR_ID


@pytest.mark.asyncio
async def test_danh_sach_cua_toi_luon_loc_theo_jwt(client: AsyncClient, monkeypatch):
    service = Mock(return_value=[])
    monkeypatch.setattr(drug_request_routes, "liet_ke_yeu_cau", service)

    response = await client.get("/api/v1/drug-requests?doctor_id=bs-nguoi-khac")

    assert response.status_code == 200
    assert service.call_args.kwargs["doctor_id"] == DOCTOR_ID


# ---------------------------------------------------------------------------
# Hop dong loi (api-contracts.md §1e)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_chat_bi_kiem_soat_tra_422_kem_ma_loi_rieng(client: AsyncClient, monkeypatch):
    """Ma loi rieng de frontend phan biet duoc: day khong phai loi nhap lieu
    de sua lai ma la tu choi co chu dich."""
    monkeypatch.setattr(
        drug_request_routes,
        "tao_yeu_cau",
        Mock(side_effect=ThuocBiKiemSoatError("chua hoat chat bi kiem soat", chat="heroin")),
    )

    response = await client.post("/api/v1/drug-requests", json={**_PAYLOAD, "ten_thuoc": "Heroin"})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "CONTROLLED_SUBSTANCE_BLOCKED"


@pytest.mark.asyncio
async def test_duyet_lai_yeu_cau_da_xu_ly_tra_409(client: AsyncClient, monkeypatch):
    app.dependency_overrides[get_current_user] = _admin
    monkeypatch.setattr(
        drug_request_routes,
        "duyet_yeu_cau",
        Mock(side_effect=TrangThaiYeuCauKhongHopLeError("da xu ly roi", status="APPROVED")),
    )

    response = await client.post("/api/v1/admin/drug-requests/yc-1/approve", json={})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "INVALID_DRUG_REQUEST_STATE"


@pytest.mark.asyncio
async def test_yeu_cau_khong_ton_tai_tra_404(client: AsyncClient, monkeypatch):
    app.dependency_overrides[get_current_user] = _admin
    monkeypatch.setattr(
        drug_request_routes,
        "duyet_yeu_cau",
        Mock(side_effect=YeuCauThuocKhongTonTaiError("khong thay")),
    )

    response = await client.post("/api/v1/admin/drug-requests/khong-co/approve", json={})

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_tu_choi_thieu_ly_do_bi_chan_tu_schema(client: AsyncClient):
    """`note` min_length=1: bac si bi tu choi ma khong biet vi sao la mot
    nguoi bi ket. Chan ngay o schema, khong doi toi service."""
    app.dependency_overrides[get_current_user] = _admin

    response = await client.post("/api/v1/admin/drug-requests/yc-1/reject", json={"note": ""})

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Hinh dang response
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_response_mang_approved_drug_id_sau_khi_duyet(client: AsyncClient, monkeypatch):
    """`approved_drug_id` la gia tri FE gui lai trong PrescriptionItemIn.drug_id
    luc ke don - thieu no thi ca luong dut o day."""
    app.dependency_overrides[get_current_user] = _admin
    monkeypatch.setattr(
        drug_request_routes,
        "duyet_yeu_cau",
        Mock(return_value=_row(status="APPROVED", approved_drug_id="req-thuoc-abc123")),
    )

    response = await client.post("/api/v1/admin/drug-requests/yc-1/approve", json={})

    assert response.status_code == 200
    assert response.json()["approved_drug_id"] == "req-thuoc-abc123"
    assert response.json()["status"] == "APPROVED"
