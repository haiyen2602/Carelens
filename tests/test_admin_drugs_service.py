"""Tests for the canonical drug query and CRUD service."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.db.models import (
    Drug,
    DrugChunk,
    DrugIdMap,
    DrugProduct,
    DrugProductIngredient,
    DrugRequest,
    Ingredient,
)
from backend.models.admin_drug_schemas import AdminDrugCreateRequest, AdminDrugUpdateRequest, MappingStatus
from backend.services.admin_drugs import (
    create_admin_drug,
    delete_admin_drug,
    get_admin_drug,
    get_admin_drug_filters,
    list_admin_drugs,
    update_admin_drug,
)

TABLES = (
    DrugProduct.__table__,
    DrugIdMap.__table__,
    Ingredient.__table__,
    DrugProductIngredient.__table__,
    Drug.__table__,
    DrugChunk.__table__,
    # THEM 2026-08-21 (FB-14): list_admin_drugs/get_admin_drug doc them bang
    # nay de noi cac thuoc bac si xin bo sung da duoc duyet vao man hinh.
    DrugRequest.__table__,
)


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for table in TABLES:
        table.create(engine)
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _product(db: Session, product_id: str, name: str, legacy_id: str | None = None, dosage_form: str | None = None, route: str | None = None) -> None:
    db.add(
        DrugProduct(
            id=product_id,
            legacy_drug_id=legacy_id,
            display_name=name,
            dosage_form=dosage_form,
            route=route,
            status="ACTIVE",
        )
    )


def _mapping(db: Session, mapping_id: str, product_id: str, legacy_id: str, status: str) -> None:
    db.add(
        DrugIdMap(
            id=mapping_id,
            legacy_drug_id=legacy_id,
            drug_product_id=product_id,
            mapping_status=status,
        )
    )


def _ingredient(db: Session, product_id: str, ingredient_id: str, name: str) -> None:
    db.add(Ingredient(id=ingredient_id, name=name))
    db.add(
        DrugProductIngredient(
            id=f"link-{product_id}-{ingredient_id}",
            drug_product_id=product_id,
            ingredient_id=ingredient_id,
        )
    )


def test_list_aggregates_ingredients_and_mappings_with_stable_order(db: Session):
    _product(db, "prod-z", "Paracetamol 500mg", "legacy-product")
    _ingredient(db, "prod-z", "ingredient-z", "Paracetamol")
    _ingredient(db, "prod-z", "ingredient-a", "Acetaminophen")
    _mapping(db, "map-active", "prod-z", "para-500", "ACTIVE")
    _mapping(db, "map-ambiguous", "prod-z", "para", "AMBIGUOUS")
    db.commit()

    result = list_admin_drugs(db, page=1, page_size=20)

    assert result.total == 1
    assert result.total_pages == 1
    assert result.items[0].ingredients == ["Acetaminophen", "Paracetamol"]
    assert [mapping.id for mapping in result.items[0].mappings] == [
        "map-ambiguous",
        "map-active",
    ]
    assert result.items[0].mapping_status is MappingStatus.AMBIGUOUS


def test_list_searches_display_name_and_mapping_legacy_id(db: Session):
    _product(db, "prod-a", "Amlodipine 5mg")
    _product(db, "prod-p", "Paracetamol 500mg")
    _mapping(db, "map-a", "prod-a", "legacy-blood-pressure", "ACTIVE")
    db.commit()

    by_name = list_admin_drugs(db, q="PARACETAMOL", page=1, page_size=20)
    by_mapping = list_admin_drugs(db, q="blood-pressure", page=1, page_size=20)

    assert [item.id for item in by_name.items] == ["prod-p"]
    assert [item.id for item in by_mapping.items] == ["prod-a"]


@pytest.mark.parametrize(
    "query, product_id", [("100%", "prod-percent"), ("dose_1", "prod-underscore"), ("C:\\temp", "prod-backslash")]
)
def test_list_search_treats_like_metacharacters_as_literals(db: Session, query: str, product_id: str):
    _product(db, "prod-percent", "Dose 100%", "legacy-percent")
    _product(db, "prod-underscore", "Dose dose_1", "legacy-underscore")
    _product(db, "prod-backslash", r"Path C:\temp", "legacy-backslash")
    _product(db, "prod-other", "Dose 100X", "legacy-other")
    db.commit()

    result = list_admin_drugs(db, q=query, page=1, page_size=20)

    assert [item.id for item in result.items] == [product_id]


@pytest.mark.parametrize("status", list(MappingStatus))
def test_list_filters_products_having_requested_mapping_status(db: Session, status: MappingStatus):
    _product(db, f"prod-{status.value}", status.value.title())
    _product(db, "prod-unmapped-record", "No mapping record")
    _mapping(db, f"map-{status.value}", f"prod-{status.value}", status.value, status.value)
    db.commit()

    result = list_admin_drugs(db, mapping_status=status, page=1, page_size=20)

    assert [item.id for item in result.items] == [f"prod-{status.value}"]


def test_unmapped_product_is_visible_only_without_status_filter(db: Session):
    _product(db, "prod-no-map", "No Mapping")
    db.commit()

    unfiltered = list_admin_drugs(db, page=1, page_size=20)
    filtered = list_admin_drugs(db, mapping_status=MappingStatus.UNMAPPED, page=1, page_size=20)

    assert [item.id for item in unfiltered.items] == ["prod-no-map"]
    assert filtered.items == []


def test_list_has_stable_order_and_page_boundaries(db: Session):
    _product(db, "prod-b", "Same")
    _product(db, "prod-a", "Same")
    _product(db, "prod-c", "Zulu")
    db.commit()

    first = list_admin_drugs(db, page=1, page_size=2)
    second = list_admin_drugs(db, page=2, page_size=2)
    beyond = list_admin_drugs(db, page=3, page_size=2)

    assert [item.id for item in first.items] == ["prod-a", "prod-b"]
    assert [item.id for item in second.items] == ["prod-c"]
    assert beyond.items == []
    assert first.total == 3
    assert first.total_pages == 2


def test_detail_returns_complete_product_and_ignores_orphans(db: Session):
    _product(db, "prod-a", "Amlodipine")
    _ingredient(db, "prod-a", "ingredient-a", "Amlodipine besylate")
    _mapping(db, "map-a", "prod-a", "amlodipine-5", "ACTIVE")
    _mapping(db, "orphan-map", "missing-product", "orphan", "RETIRED")
    db.add(Ingredient(id="orphan-ingredient", name="Orphan"))
    db.add(
        DrugProductIngredient(
            id="orphan-link",
            drug_product_id="missing-product",
            ingredient_id="orphan-ingredient",
        )
    )
    db.commit()

    result = get_admin_drug(db, "prod-a")

    assert result is not None
    assert result.ingredients == ["Amlodipine besylate"]
    assert [mapping.id for mapping in result.mappings] == ["map-a"]
    assert get_admin_drug(db, "missing-product") is None


def test_crud_lifecycle_and_filters(db: Session):
    # Test Create
    create_req = AdminDrugCreateRequest(
        display_name="Ciprofloxacin 500mg",
        dosage_form="Viên nén",
        route="Uống",
        strength_text="500mg",
        packaging="Hộp 2 vỉ x 10 viên",
        category="Kháng sinh",
        cong_dung="Điều trị nhiễm khuẩn",
        cach_dung="Uống 1 viên/lần",
    )
    created = create_admin_drug(db, create_req)
    assert created.display_name == "Ciprofloxacin 500mg"
    assert created.dosage_form == "Viên nén"
    assert created.packaging == "Hộp 2 vỉ x 10 viên"
    assert created.cong_dung == "Điều trị nhiễm khuẩn"
    assert created.cach_dung == "Uống 1 viên/lần"

    # Test Filters
    filters = get_admin_drug_filters(db)
    assert "Viên nén" in filters.dosage_forms
    assert "Uống" in filters.routes

    # Test Update
    update_req = AdminDrugUpdateRequest(
        display_name="Ciprofloxacin 500mg Domesco",
        tac_dung_phu="Buồn nôn, tiêu chảy",
    )
    updated = update_admin_drug(
        db,
        created.id,
        display_name=update_req.display_name,
        tac_dung_phu=update_req.tac_dung_phu,
    )
    assert updated is not None
    assert updated.display_name == "Ciprofloxacin 500mg Domesco"
    assert updated.tac_dung_phu == "Buồn nôn, tiêu chảy"

    # Test Delete
    deleted = delete_admin_drug(db, created.id)
    assert deleted is True
    assert get_admin_drug(db, created.id) is None
