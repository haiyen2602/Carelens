"""Read-only admin endpoints for canonical Drug Knowledge V2 products."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, require_role
from backend.db.base import get_db
from backend.models.admin_drug_schemas import (
    AdminDrugDetailResponse,
    AdminDrugListResponse,
    MappingStatus,
)
from backend.services.admin_drugs import get_admin_drug, list_admin_drugs

admin_drug_router = APIRouter(prefix="/admin/drugs", tags=["admin-drugs"])


@admin_drug_router.get("", response_model=AdminDrugListResponse)
def list_drugs(
    q: Annotated[str | None, Query(max_length=200)] = None,
    mapping_status: MappingStatus | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
    _admin: CurrentUser = Depends(require_role("admin")),
) -> AdminDrugListResponse:
    return list_admin_drugs(db, q=q, mapping_status=mapping_status, page=page, page_size=page_size)


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
