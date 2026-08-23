"""HTTP contract tests for the canonical admin drug routes."""

from collections.abc import AsyncIterator
from unittest.mock import Mock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.api import admin_drug_routes
from backend.api.security import CurrentUser, get_current_user
from backend.db.base import get_db
from backend.main import app
from backend.models.admin_drug_schemas import (
    AdminDrugDetailResponse,
    AdminDrugFiltersResponse,
    AdminDrugListResponse,
    MappingStatus,
)


async def _admin() -> CurrentUser:
    return CurrentUser(id="admin-1", role="admin", patient_id=None, doctor_id=None)


async def _caregiver() -> CurrentUser:
    return CurrentUser(id="caregiver-1", role="caregiver", patient_id=None, doctor_id=None)


def _db():
    yield Mock()


@pytest.fixture(autouse=True)
def dependencies():
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _admin
    yield
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_list_requires_admin_role(client: AsyncClient):
    app.dependency_overrides[get_current_user] = _caregiver

    response = await client.get("/api/v1/admin/drugs")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_forwards_filters_and_returns_response_shape(client: AsyncClient, monkeypatch):
    expected = AdminDrugListResponse(items=[], page=2, page_size=10, total=0, total_pages=0)
    service = Mock(return_value=expected)
    monkeypatch.setattr(admin_drug_routes, "list_admin_drugs", service)

    response = await client.get(
        "/api/v1/admin/drugs",
        params={
            "q": "para",
            "dosage_form": "Viên nén",
            "route": "Uống",
            "mapping_status": "ACTIVE",
            "page": 2,
            "page_size": 10,
        },
    )

    assert response.status_code == 200
    assert response.json() == expected.model_dump(mode="json")
    service.assert_called_once()
    assert service.call_args.kwargs == {
        "q": "para",
        "dosage_form": "Viên nén",
        "route": "Uống",
        "mapping_status": MappingStatus.ACTIVE,
        "page": 2,
        "page_size": 10,
    }


@pytest.mark.asyncio
async def test_filters_endpoint(client: AsyncClient, monkeypatch):
    expected = AdminDrugFiltersResponse(dosage_forms=["Viên nén"], routes=["Uống"])
    monkeypatch.setattr(admin_drug_routes, "get_admin_drug_filters", Mock(return_value=expected))

    response = await client.get("/api/v1/admin/drugs/filters")

    assert response.status_code == 200
    assert response.json() == {"dosage_forms": ["Viên nén"], "routes": ["Uống"]}


@pytest.mark.asyncio
async def test_create_drug_returns_created_and_logs(client: AsyncClient, monkeypatch):
    expected = AdminDrugDetailResponse(id="new-prod-1", display_name="Amlodipine 5mg")
    monkeypatch.setattr(admin_drug_routes, "create_admin_drug", Mock(return_value=expected))
    log_mock = Mock()
    monkeypatch.setattr(admin_drug_routes, "log_system_event", log_mock)

    response = await client.post(
        "/api/v1/admin/drugs",
        json={
            "display_name": "Amlodipine 5mg",
            "dosage_form": "Viên nén",
            "route": "Uống",
            "strength_text": "5mg",
        },
    )

    assert response.status_code == 201
    assert response.json()["id"] == "new-prod-1"
    log_mock.assert_called_once()


@pytest.mark.asyncio
async def test_detail_returns_product(client: AsyncClient, monkeypatch):
    expected = AdminDrugDetailResponse(id="prod-1", display_name="Paracetamol")
    monkeypatch.setattr(admin_drug_routes, "get_admin_drug", Mock(return_value=expected))

    response = await client.get("/api/v1/admin/drugs/prod-1")

    assert response.status_code == 200
    assert response.json()["id"] == "prod-1"


@pytest.mark.asyncio
async def test_missing_detail_returns_404(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(admin_drug_routes, "get_admin_drug", Mock(return_value=None))

    response = await client.get("/api/v1/admin/drugs/missing")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_patch_drug_updates_and_logs(client: AsyncClient, monkeypatch):
    expected = AdminDrugDetailResponse(id="prod-1", display_name="Paracetamol 500mg")
    monkeypatch.setattr(admin_drug_routes, "update_admin_drug", Mock(return_value=expected))
    log_mock = Mock()
    monkeypatch.setattr(admin_drug_routes, "log_system_event", log_mock)

    response = await client.patch(
        "/api/v1/admin/drugs/prod-1",
        json={"display_name": "Paracetamol 500mg"},
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "Paracetamol 500mg"
    log_mock.assert_called_once()


@pytest.mark.asyncio
async def test_delete_drug_deletes_and_logs(client: AsyncClient, monkeypatch):
    drug = AdminDrugDetailResponse(id="prod-1", display_name="Paracetamol")
    monkeypatch.setattr(admin_drug_routes, "get_admin_drug", Mock(return_value=drug))
    monkeypatch.setattr(admin_drug_routes, "delete_admin_drug", Mock(return_value=True))
    log_mock = Mock()
    monkeypatch.setattr(admin_drug_routes, "log_system_event", log_mock)

    response = await client.delete("/api/v1/admin/drugs/prod-1")

    assert response.status_code == 204
    log_mock.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page_size": 0},
        {"page_size": 101},
        {"mapping_status": "INDEXED"},
    ],
)
async def test_invalid_list_query_returns_422(client: AsyncClient, params):
    response = await client.get("/api/v1/admin/drugs", params=params)

    assert response.status_code == 422


def test_openapi_exposes_crud_routes():
    paths = app.openapi()["paths"]

    assert set(paths["/api/v1/admin/drugs"]) == {"get", "post"}
    assert set(paths["/api/v1/admin/drugs/{drug_product_id}"]) == {"get", "patch", "delete"}
    assert set(paths["/api/v1/admin/drugs/filters"]) == {"get"}
    assert not any("reindex" in path.casefold() for path in paths)
