"""Queries and CRUD operations for the Admin RAG drug management."""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections import defaultdict
from math import ceil

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from backend.db.models import Drug, DrugChunk, DrugIdMap, DrugProduct, DrugProductIngredient, Ingredient
from backend.models.admin_drug_schemas import (
    AdminDrugCreateRequest,
    AdminDrugDetailResponse,
    AdminDrugFiltersResponse,
    AdminDrugItem,
    AdminDrugListResponse,
    AdminDrugMapping,
    AdminDrugUpdateRequest,
    DrugSource,
    MappingStatus,
)

_STATUS_PRIORITY = {
    MappingStatus.AMBIGUOUS: 0,
    MappingStatus.UNMAPPED: 1,
    MappingStatus.RETIRED: 2,
    MappingStatus.ACTIVE: 3,
}
_LIKE_ESCAPE = "\\"


def _remove_accents(text: str) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    result = "".join(c for c in nfkd if not unicodedata.combining(c))
    result = result.replace("đ", "d").replace("Đ", "D")
    return result


def _generate_slug_id(name: str) -> str:
    cleaned = _remove_accents(name).lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned).strip("-")
    if not cleaned:
        cleaned = "drug"
    return f"{cleaned}-{uuid.uuid4().hex[:8]}"


def _escape_like(value: str) -> str:
    """Escape SQL LIKE metacharacters so admin search remains literal."""
    return (
        value.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", _LIKE_ESCAPE + "%")
        .replace("_", _LIKE_ESCAPE + "_")
    )


def get_admin_drug_filters(session: Session) -> AdminDrugFiltersResponse:
    """Return unique dosage forms and routes across drug catalog."""
    product_dosage_forms = session.scalars(
        select(DrugProduct.dosage_form)
        .where(DrugProduct.dosage_form.is_not(None), DrugProduct.dosage_form != "")
        .distinct()
    ).all()
    legacy_dosage_forms = session.scalars(
        select(Drug.dang_thuoc)
        .where(Drug.dang_thuoc.is_not(None), Drug.dang_thuoc != "")
        .distinct()
    ).all()

    product_routes = session.scalars(
        select(DrugProduct.route)
        .where(DrugProduct.route.is_not(None), DrugProduct.route != "")
        .distinct()
    ).all()
    legacy_routes = session.scalars(
        select(Drug.duong_dung)
        .where(Drug.duong_dung.is_not(None), Drug.duong_dung != "")
        .distinct()
    ).all()

    dosage_forms = sorted({df.strip() for df in product_dosage_forms + legacy_dosage_forms if df and df.strip()})
    routes = sorted({r.strip() for r in product_routes + legacy_routes if r and r.strip()})
    return AdminDrugFiltersResponse(dosage_forms=dosage_forms, routes=routes)


def list_admin_drugs(
    session: Session,
    q: str | None = None,
    dosage_form: str | None = None,
    route: str | None = None,
    mapping_status: MappingStatus | str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> AdminDrugListResponse:
    """Return one row per canonical product with deterministic collections."""
    query = select(DrugProduct)
    normalized_q = q.strip() if q else ""
    if normalized_q:
        pattern = f"%{_escape_like(normalized_q)}%"
        mapping_match = (
            select(DrugIdMap.id)
            .where(
                DrugIdMap.drug_product_id == DrugProduct.id,
                DrugIdMap.legacy_drug_id.ilike(pattern, escape=_LIKE_ESCAPE),
            )
            .exists()
        )
        query = query.where(
            or_(
                DrugProduct.display_name.ilike(pattern, escape=_LIKE_ESCAPE),
                DrugProduct.legacy_drug_id.ilike(pattern, escape=_LIKE_ESCAPE),
                mapping_match,
            )
        )

    if dosage_form and dosage_form != "__tat_ca__":
        query = query.where(DrugProduct.dosage_form == dosage_form)

    if route and route != "__tat_ca__":
        query = query.where(DrugProduct.route == route)

    if mapping_status is not None and mapping_status != "":
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
    product_ids = [product.id for product in products]
    ingredients, mappings = _load_collections(session, product_ids)
    extra_details = _load_drug_extras(session, products)
    items = [
        _build_item(
            product,
            ingredients[product.id],
            mappings[product.id],
            extra_details.get(product.id, {}),
        )
        for product in products
    ]

    # THEM 2026-08-21 (FB-14): noi them thuoc duyet qua `drug_request`, neu
    # khong admin duyet xong roi mo man hinh nay lai khong thay dau vet gi.
    ngoai_le = _liet_ke_ngoai_le(session, normalized_q, mapping_status)
    if ngoai_le:
        con_trong = page_size - len(items)
        if con_trong > 0:
            # Xep o CUOI toan bo danh sach, khong phai cuoi moi trang - noi duoi
            # tung trang thi cung mot dong se hien lai o moi trang.
            bat_dau = max(0, (page - 1) * page_size - total)
            items = [*items, *ngoai_le[bat_dau : bat_dau + con_trong]]
        total += len(ngoai_le)
    return AdminDrugListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=ceil(total / page_size) if total else 0,
    )


def _liet_ke_ngoai_le(
    session: Session,
    q: str,
    mapping_status: MappingStatus | str | None,
) -> list[AdminDrugItem]:
    """Thuoc da duyet qua `drug_request`, doi sang hinh dang cua man hinh nay.

    Bo qua khi admin dang loc theo mot trang thai anh xa CU THE khac UNMAPPED:
    thuoc ngoai le chua he co ban ghi trong `drug_id_map`, nen no khong thuoc
    ACTIVE/AMBIGUOUS/RETIRED. Coi no la UNMAPPED la cach doc dung nhat - va
    truong `source` o moi dong noi ro no khong phai du lieu canonical.
    """
    if mapping_status is not None and MappingStatus(mapping_status) is not MappingStatus.UNMAPPED:
        return []

    from backend.services.drug_requests.service import liet_ke_thuoc_da_duyet

    return [
        AdminDrugItem(
            id=yc.approved_drug_id,
            legacy_drug_id=yc.approved_drug_id,
            display_name=yc.ten_thuoc,
            dosage_form=yc.dang_thuoc,
            route=yc.duong_dung,
            strength_text=yc.ham_luong,
            category_id=None,
            # Bac si chi khai ten thuoc, khong khai hoat chat - de rong chu
            # khong doan tu ten.
            ingredients=[],
            mapping_status=MappingStatus.UNMAPPED,
            mappings=[],
            source=DrugSource.DRUG_REQUEST,
        )
        for yc in liet_ke_thuoc_da_duyet(session, tu_khoa=q)
    ]


def get_admin_drug(session: Session, drug_product_id: str) -> AdminDrugDetailResponse | None:
    """Return a canonical product and its collections with RAG chunks, or fallback to drug_request exception, or None when absent."""
    product = session.get(DrugProduct, drug_product_id)
    if product is not None:
        ingredients, mappings = _load_collections(session, [product.id])
        extra_details = _load_drug_extras(session, [product])
        base_item = _build_item(
            product,
            ingredients[product.id],
            mappings[product.id],
            extra_details.get(product.id, {}),
        )

        # Query RAG chunks
        lookup_ids = [product.id]
        if product.legacy_drug_id:
            lookup_ids.append(product.legacy_drug_id)
        for m in mappings[product.id]:
            if m.legacy_drug_id:
                lookup_ids.append(m.legacy_drug_id)

        chunks = session.scalars(
            select(DrugChunk).where(DrugChunk.drug_id.in_(lookup_ids))
        ).all()
        chunk_map = {c.field_group: c.noi_dung for c in chunks}

        return AdminDrugDetailResponse(
            **base_item.model_dump(),
            cong_dung=chunk_map.get("cong_dung"),
            cach_dung=chunk_map.get("cach_dung"),
            tac_dung_phu=chunk_map.get("tac_dung_phu"),
            bao_quan=chunk_map.get("bao_quan"),
        )

    # THEM 2026-08-21 (FB-14): khong thay trong canonical thi tra tiep bang
    # `drug_request`. Canonical LUON thang - khong bao gio de duong ngoai le ghi
    # de len du lieu co nguon (ADR-0012).
    ngoai_le = _liet_ke_ngoai_le(session, "", None)
    khop = next((item for item in ngoai_le if item.id == drug_product_id), None)
    return AdminDrugDetailResponse(**khop.model_dump()) if khop is not None else None


def create_admin_drug(
    session: Session,
    payload: AdminDrugCreateRequest,
) -> AdminDrugDetailResponse:
    """Create a new drug product, legacy drug entry, and associated RAG chunks."""
    product_id = _generate_slug_id(payload.display_name)
    mapping_status_val = (payload.mapping_status or MappingStatus.ACTIVE).value

    product = DrugProduct(
        id=product_id,
        legacy_drug_id=product_id,
        display_name=payload.display_name.strip(),
        dosage_form=payload.dosage_form.strip() if payload.dosage_form else "Chưa xác định",
        route=payload.route.strip() if payload.route else "Chưa xác định",
        strength_text=payload.strength_text.strip() if payload.strength_text else None,
        category_id=payload.category.strip() if payload.category else None,
        status="ACTIVE",
    )
    session.add(product)

    # Sync to Drug table for doctor prescriptions and lookups
    legacy_drug = Drug(
        id=product_id,
        ten_thuoc=payload.display_name.strip(),
        ten_thuoc_unaccent=_remove_accents(payload.display_name.strip()),
        dang_thuoc=payload.dosage_form.strip() if payload.dosage_form else "Chưa xác định",
        duong_dung=payload.route.strip() if payload.route else "Chưa xác định",
        ham_luong=payload.strength_text.strip() if payload.strength_text else None,
        tong_so_luong=payload.packaging.strip() if payload.packaging else None,
        danh_muc=payload.category.strip() if payload.category else None,
        muc_nghiem_trong=payload.severity.strip() if payload.severity else "Nhẹ",
    )
    session.add(legacy_drug)

    # Sync to DrugIdMap
    mapping = DrugIdMap(
        legacy_drug_id=product_id,
        drug_product_id=product_id,
        mapping_status=mapping_status_val,
    )
    session.add(mapping)

    # Add RAG chunks if provided
    rag_fields = [
        ("cong_dung", payload.cong_dung),
        ("cach_dung", payload.cach_dung),
        ("tac_dung_phu", payload.tac_dung_phu),
        ("bao_quan", payload.bao_quan),
    ]
    for field_group, content in rag_fields:
        if content and content.strip():
            chunk = DrugChunk(
                drug_id=product_id,
                ten_thuoc=payload.display_name.strip(),
                danh_muc=payload.category.strip() if payload.category else "Chung",
                muc_nghiem_trong=payload.severity.strip() if payload.severity else "Nhẹ",
                field_group=field_group,
                noi_dung=content.strip(),
                noi_dung_unaccent=_remove_accents(content.strip()),
                ten_thuoc_unaccent=_remove_accents(payload.display_name.strip()),
                embedding=[0.0] * 1536,
            )
            session.add(chunk)

    session.flush()
    result = get_admin_drug(session, product_id)
    if result is None:
        raise RuntimeError("Failed to retrieve created drug")
    return result


def update_admin_drug(
    session: Session,
    drug_product_id: str,
    *,
    display_name: str | None = None,
    dosage_form: str | None = None,
    route: str | None = None,
    strength_text: str | None = None,
    packaging: str | None = None,
    category: str | None = None,
    severity: str | None = None,
    mapping_status: MappingStatus | None = None,
    cong_dung: str | None = None,
    cach_dung: str | None = None,
    tac_dung_phu: str | None = None,
    bao_quan: str | None = None,
) -> AdminDrugDetailResponse | None:
    """Update canonical product attributes, legacy drug info, mapping status, and RAG chunks."""
    product = session.get(DrugProduct, drug_product_id)
    if product is None:
        return None

    if display_name is not None:
        product.display_name = display_name.strip()
    if dosage_form is not None:
        product.dosage_form = dosage_form.strip() if dosage_form else None
    if route is not None:
        product.route = route.strip() if route else None
    if strength_text is not None:
        product.strength_text = strength_text.strip() if strength_text else None
    if category is not None:
        product.category_id = category.strip() if category else None

    # Update corresponding Drug record if exists
    legacy_ids = [product.id]
    if product.legacy_drug_id:
        legacy_ids.append(product.legacy_drug_id)
    legacy_drug = session.scalars(select(Drug).where(Drug.id.in_(legacy_ids))).first()
    if legacy_drug:
        if display_name is not None:
            legacy_drug.ten_thuoc = display_name.strip()
            legacy_drug.ten_thuoc_unaccent = _remove_accents(display_name.strip())
        if dosage_form is not None:
            legacy_drug.dang_thuoc = dosage_form.strip() if dosage_form else "Chưa xác định"
        if route is not None:
            legacy_drug.duong_dung = route.strip() if route else "Chưa xác định"
        if strength_text is not None:
            legacy_drug.ham_luong = strength_text.strip() if strength_text else None
        if packaging is not None:
            legacy_drug.tong_so_luong = packaging.strip() if packaging else None
        if category is not None:
            legacy_drug.danh_muc = category.strip() if category else None
        if severity is not None:
            legacy_drug.muc_nghiem_trong = severity.strip() if severity else None

    if mapping_status is not None:
        mapping = session.scalars(
            select(DrugIdMap).where(DrugIdMap.drug_product_id == product.id)
        ).first()
        if mapping:
            mapping.mapping_status = mapping_status.value
        elif product.legacy_drug_id:
            session.add(
                DrugIdMap(
                    legacy_drug_id=product.legacy_drug_id,
                    drug_product_id=product.id,
                    mapping_status=mapping_status.value,
                )
            )

    # Update or insert RAG chunk sections if passed
    rag_updates = {
        "cong_dung": cong_dung,
        "cach_dung": cach_dung,
        "tac_dung_phu": tac_dung_phu,
        "bao_quan": bao_quan,
    }
    for field_group, content in rag_updates.items():
        if content is not None:
            chunk = session.scalars(
                select(DrugChunk).where(
                    DrugChunk.drug_id.in_(legacy_ids),
                    DrugChunk.field_group == field_group,
                )
            ).first()
            if chunk:
                chunk.noi_dung = content.strip()
                chunk.noi_dung_unaccent = _remove_accents(content.strip())
                if display_name is not None:
                    chunk.ten_thuoc = display_name.strip()
                    chunk.ten_thuoc_unaccent = _remove_accents(display_name.strip())
            elif content.strip():
                new_chunk = DrugChunk(
                    drug_id=product.id,
                    ten_thuoc=product.display_name,
                    danh_muc=product.category_id or "Chung",
                    muc_nghiem_trong="Nhẹ",
                    field_group=field_group,
                    noi_dung=content.strip(),
                    noi_dung_unaccent=_remove_accents(content.strip()),
                    ten_thuoc_unaccent=_remove_accents(product.display_name),
                    embedding=[0.0] * 1536,
                )
                session.add(new_chunk)

    session.flush()
    return get_admin_drug(session, product.id)


def delete_admin_drug(session: Session, drug_product_id: str) -> bool:
    """Delete a drug product and all its associated mappings, chunks, and legacy rows."""
    product = session.get(DrugProduct, drug_product_id)
    if product is None:
        return False

    legacy_ids = [product.id]
    if product.legacy_drug_id:
        legacy_ids.append(product.legacy_drug_id)

    mapping_legacy_ids = session.scalars(
        select(DrugIdMap.legacy_drug_id).where(DrugIdMap.drug_product_id == product.id)
    ).all()
    all_related_ids = list(set(legacy_ids + list(mapping_legacy_ids)))

    session.execute(
        delete(DrugProductIngredient).where(DrugProductIngredient.drug_product_id == product.id)
    )
    session.execute(
        delete(DrugIdMap).where(DrugIdMap.drug_product_id == product.id)
    )
    session.execute(
        delete(DrugChunk).where(DrugChunk.drug_id.in_(all_related_ids))
    )
    session.execute(
        delete(Drug).where(Drug.id.in_(all_related_ids))
    )
    session.delete(product)
    session.flush()
    return True


def _load_drug_extras(
    session: Session, products: list[DrugProduct]
) -> dict[str, dict]:
    """Load packaging (tong_so_luong), category name, severity from Drug table."""
    if not products:
        return {}
    lookup_ids: dict[str, str] = {}
    for p in products:
        lookup_ids[p.id] = p.id
        if p.legacy_drug_id:
            lookup_ids[p.legacy_drug_id] = p.id

    legacy_drugs = session.scalars(
        select(Drug).where(Drug.id.in_(list(lookup_ids.keys())))
    ).all()

    extras: dict[str, dict] = defaultdict(dict)
    for ld in legacy_drugs:
        prod_id = lookup_ids.get(ld.id, ld.id)
        extras[prod_id] = {
            "packaging": ld.tong_so_luong,
            "category_name": ld.danh_muc,
            "severity": ld.muc_nghiem_trong,
            "strength_text": ld.ham_luong,
        }
    return extras


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

    mapping_rows = session.scalars(select(DrugIdMap).where(DrugIdMap.drug_product_id.in_(product_ids)))
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
    extras: dict | None = None,
) -> AdminDrugItem:
    extras = extras or {}
    return AdminDrugItem(
        id=product.id,
        legacy_drug_id=product.legacy_drug_id,
        display_name=product.display_name,
        dosage_form=product.dosage_form,
        route=product.route,
        strength_text=product.strength_text or extras.get("strength_text"),
        packaging=extras.get("packaging"),
        category_id=product.category_id,
        category_name=extras.get("category_name") or product.category_id,
        severity=extras.get("severity"),
        ingredients=ingredients,
        mapping_status=mappings[0].mapping_status if mappings else None,
        mappings=mappings,
    )
