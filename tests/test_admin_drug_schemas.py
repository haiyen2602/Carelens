import pytest
from pydantic import ValidationError

from backend.models.admin_drug_schemas import (
    AdminDrugDetailResponse,
    AdminDrugItem,
    AdminDrugListResponse,
    AdminDrugMapping,
    MappingStatus,
)


def _mapping(**overrides):
    data = {
        "id": "map-1",
        "legacy_drug_id": "paracetamol-500",
        "drug_product_id": "prod-1",
        "mapping_status": "ACTIVE",
        "source_manifest_version": None,
    }
    data.update(overrides)
    return data


def _item(**overrides):
    data = {
        "id": "prod-1",
        "legacy_drug_id": None,
        "display_name": "Paracetamol 500mg",
        "dosage_form": None,
        "route": None,
        "strength_text": None,
        "packaging": None,
        "category_id": None,
        "category_name": None,
        "severity": None,
        "ingredients": [],
        "mapping_status": None,
        "mappings": [],
    }
    data.update(overrides)
    return data


def test_admin_drug_list_serializes_pagination_and_nullable_canonical_fields():
    response = AdminDrugListResponse(
        items=[AdminDrugItem(**_item())], page=1, page_size=20, total=1, total_pages=1
    )

    assert response.model_dump() == {
        "items": [_item()],
        "page": 1,
        "page_size": 20,
        "total": 1,
        "total_pages": 1,
    }


def test_admin_drug_detail_serializes_all_mappings():
    mapping = AdminDrugMapping(**_mapping())
    response = AdminDrugDetailResponse(**_item(mappings=[mapping]))

    assert response.id == "prod-1"
    assert response.mappings[0].mapping_status is MappingStatus.ACTIVE
    assert response.mappings[0].source_manifest_version is None


def test_mapping_status_rejects_unknown_values():
    with pytest.raises(ValidationError):
        AdminDrugMapping(**_mapping(mapping_status="PROCESSING"))


@pytest.mark.parametrize("field", ["page", "page_size"])
def test_pagination_fields_must_be_positive(field):
    with pytest.raises(ValidationError):
        AdminDrugListResponse(**{"items": [], "page": 1, "page_size": 20, "total": 0, "total_pages": 0, field: 0})


def test_page_size_has_a_bounded_upper_limit():
    with pytest.raises(ValidationError):
        AdminDrugListResponse(items=[], page=1, page_size=101, total=0, total_pages=0)
