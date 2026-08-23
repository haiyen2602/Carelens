"""Admin endpoints for canonical Drug Knowledge V2 products and RAG CRUD."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, require_role
from backend.db.base import get_db
from backend.models.admin_drug_schemas import (
    AdminDrugCreateRequest,
    AdminDrugDetailResponse,
    AdminDrugFiltersResponse,
    AdminDrugListResponse,
    AdminDrugUpdateRequest,
    MappingStatus,
)
from backend.services.admin_drugs import (
    create_admin_drug,
    delete_admin_drug,
    get_admin_drug,
    get_admin_drug_filters,
    list_admin_drugs,
    update_admin_drug,
)
from backend.services.audit import get_actor_display_name, log_system_event

admin_drug_router = APIRouter(prefix="/admin/drugs", tags=["admin-drugs"])


@admin_drug_router.get("/filters", response_model=AdminDrugFiltersResponse)
def get_filters(
    db: Session = Depends(get_db),
    _admin: CurrentUser = Depends(require_role("admin")),
) -> AdminDrugFiltersResponse:
    """Return available dosage forms and routes for filtering."""
    return get_admin_drug_filters(db)


@admin_drug_router.get("", response_model=AdminDrugListResponse)
def list_drugs(
    q: Annotated[str | None, Query(max_length=200)] = None,
    dosage_form: Annotated[str | None, Query(max_length=100)] = None,
    route: Annotated[str | None, Query(max_length=100)] = None,
    mapping_status: MappingStatus | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
    _admin: CurrentUser = Depends(require_role("admin")),
) -> AdminDrugListResponse:
    return list_admin_drugs(
        db,
        q=q,
        dosage_form=dosage_form,
        route=route,
        mapping_status=mapping_status,
        page=page,
        page_size=page_size,
    )


@admin_drug_router.post("", response_model=AdminDrugDetailResponse, status_code=status.HTTP_201_CREATED)
def create_drug(
    body: AdminDrugCreateRequest,
    db: Session = Depends(get_db),
    _admin: CurrentUser = Depends(require_role("admin")),
) -> AdminDrugDetailResponse:
    drug = create_admin_drug(db, body)
    target_id = drug.legacy_drug_id or drug.id
    actor_name = get_actor_display_name(db, _admin.id, _admin.role)
    log_system_event(
        db,
        actor_id=_admin.id,
        actor_name=actor_name,
        actor_role=_admin.role,
        action=f"Thêm mới dữ liệu thuốc {drug.display_name} vào RAG",
        target=target_id,
    )
    db.commit()
    return drug


@admin_drug_router.get("/{drug_product_id}", response_model=AdminDrugDetailResponse)
def get_drug(
    drug_product_id: str,
    db: Session = Depends(get_db),
    _admin: CurrentUser = Depends(require_role("admin")),
) -> AdminDrugDetailResponse:
    drug = get_admin_drug(db, drug_product_id)
    if drug is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy thuốc")
    return drug


@admin_drug_router.patch("/{drug_product_id}", response_model=AdminDrugDetailResponse)
def patch_drug(
    drug_product_id: str,
    body: AdminDrugUpdateRequest,
    db: Session = Depends(get_db),
    _admin: CurrentUser = Depends(require_role("admin")),
) -> AdminDrugDetailResponse:
    drug = update_admin_drug(
        db,
        drug_product_id,
        display_name=body.display_name,
        dosage_form=body.dosage_form,
        route=body.route,
        strength_text=body.strength_text,
        packaging=body.packaging,
        category=body.category,
        severity=body.severity,
        mapping_status=body.mapping_status,
        cong_dung=body.cong_dung,
        cach_dung=body.cach_dung,
        tac_dung_phu=body.tac_dung_phu,
        bao_quan=body.bao_quan,
    )
    if drug is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy thuốc")

    target_id = drug.legacy_drug_id or drug.id
    actor_name = get_actor_display_name(db, _admin.id, _admin.role)
    log_system_event(
        db,
        actor_id=_admin.id,
        actor_name=actor_name,
        actor_role=_admin.role,
        action=f"Cập nhật dữ liệu thuốc {drug.display_name} cho RAG",
        target=target_id,
    )
    db.commit()
    return drug


@admin_drug_router.delete("/{drug_product_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_drug(
    drug_product_id: str,
    db: Session = Depends(get_db),
    _admin: CurrentUser = Depends(require_role("admin")),
) -> Response:
    drug = get_admin_drug(db, drug_product_id)
    if drug is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy thuốc")

    target_id = drug.legacy_drug_id or drug.id
    drug_name = drug.display_name
    deleted = delete_admin_drug(db, drug_product_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy thuốc")

    actor_name = get_actor_display_name(db, _admin.id, _admin.role)
    log_system_event(
        db,
        actor_id=_admin.id,
        actor_name=actor_name,
        actor_role=_admin.role,
        action=f"Xóa dữ liệu thuốc {drug_name} khỏi RAG",
        target=target_id,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
