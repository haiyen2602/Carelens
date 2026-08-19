"""Read-only queries for the Admin RAG canonical drug view."""

from __future__ import annotations

from collections import defaultdict
from math import ceil

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.db.models import DrugIdMap, DrugProduct, DrugProductIngredient, Ingredient
from backend.models.admin_drug_schemas import (
    AdminDrugDetailResponse,
    AdminDrugItem,
    AdminDrugListResponse,
    AdminDrugMapping,
    MappingStatus,
)


_STATUS_PRIORITY = {
    MappingStatus.AMBIGUOUS: 0,
    MappingStatus.UNMAPPED: 1,
    MappingStatus.RETIRED: 2,
    MappingStatus.ACTIVE: 3,
}


def list_admin_drugs(
    session: Session,
    q: str | None = None,
    mapping_status: MappingStatus | str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> AdminDrugListResponse:
    """Return one row per canonical product with deterministic collections."""
    query = select(DrugProduct)
    normalized_q = q.strip() if q else ""
    if normalized_q:
        pattern = f"%{normalized_q}%"
        mapping_match = (
            select(DrugIdMap.id)
            .where(
                DrugIdMap.drug_product_id == DrugProduct.id,
                DrugIdMap.legacy_drug_id.ilike(pattern),
            )
            .exists()
        )
        query = query.where(
            or_(
                DrugProduct.display_name.ilike(pattern),
                DrugProduct.legacy_drug_id.ilike(pattern),
                mapping_match,
            )
        )

    if mapping_status is not None:
        status_value = MappingStatus(mapping_status).value
        status_match = (
            select(DrugIdMap.id)
            .where(
                DrugIdMap.drug_product_id == DrugProduct.id,
                DrugIdMap.mapping_status == status_value,
            )
            .exists()
        )
        query = query.where(status_match)

    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    products = list(
        session.scalars(
            query.order_by(func.lower(DrugProduct.display_name), DrugProduct.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    ingredients, mappings = _load_collections(session, [product.id for product in products])
    items = [
        _build_item(product, ingredients[product.id], mappings[product.id])
        for product in products
    ]
    return AdminDrugListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=ceil(total / page_size) if total else 0,
    )


def get_admin_drug(session: Session, drug_product_id: str) -> AdminDrugDetailResponse | None:
    """Return a canonical product and its collections, or None when absent."""
    product = session.get(DrugProduct, drug_product_id)
    if product is None:
        return None
    ingredients, mappings = _load_collections(session, [product.id])
    return AdminDrugDetailResponse(
        **_build_item(product, ingredients[product.id], mappings[product.id]).model_dump()
    )


def _load_collections(
    session: Session, product_ids: list[str]
) -> tuple[dict[str, list[str]], dict[str, list[AdminDrugMapping]]]:
    ingredients: dict[str, list[str]] = defaultdict(list)
    mappings: dict[str, list[AdminDrugMapping]] = defaultdict(list)
    if not product_ids:
        return ingredients, mappings

    ingredient_rows = session.execute(
        select(DrugProductIngredient.drug_product_id, Ingredient.name)
        .join(Ingredient, Ingredient.id == DrugProductIngredient.ingredient_id)
        .where(DrugProductIngredient.drug_product_id.in_(product_ids))
        .order_by(DrugProductIngredient.drug_product_id, func.lower(Ingredient.name), Ingredient.id)
    )
    for product_id, name in ingredient_rows:
        ingredients[product_id].append(name)

    mapping_rows = session.scalars(
        select(DrugIdMap).where(DrugIdMap.drug_product_id.in_(product_ids))
    )
    for row in mapping_rows:
        mappings[row.drug_product_id].append(
            AdminDrugMapping(
                id=row.id,
                legacy_drug_id=row.legacy_drug_id,
                drug_product_id=row.drug_product_id,
                mapping_status=row.mapping_status,
                source_manifest_version=row.source_manifest_version,
            )
        )
    for product_mappings in mappings.values():
        product_mappings.sort(
            key=lambda mapping: (
                _STATUS_PRIORITY[mapping.mapping_status],
                mapping.legacy_drug_id.casefold(),
                mapping.id,
            )
        )
    return ingredients, mappings


def _build_item(
    product: DrugProduct,
    ingredients: list[str],
    mappings: list[AdminDrugMapping],
) -> AdminDrugItem:
    return AdminDrugItem(
        id=product.id,
        legacy_drug_id=product.legacy_drug_id,
        display_name=product.display_name,
        dosage_form=product.dosage_form,
        route=product.route,
        strength_text=product.strength_text,
        category_id=product.category_id,
        ingredients=ingredients,
        mapping_status=mappings[0].mapping_status if mappings else None,
        mappings=mappings,
    )
