"""Response DTOs for the read-only admin canonical drug API."""

from enum import StrEnum

from pydantic import BaseModel, Field


class MappingStatus(StrEnum):
    ACTIVE = "ACTIVE"
    AMBIGUOUS = "AMBIGUOUS"
    RETIRED = "RETIRED"
    UNMAPPED = "UNMAPPED"


class AdminDrugMapping(BaseModel):
    id: str
    legacy_drug_id: str
    drug_product_id: str
    mapping_status: MappingStatus
    source_manifest_version: str | None = None


class AdminDrugItem(BaseModel):
    id: str
    legacy_drug_id: str | None = None
    display_name: str
    dosage_form: str | None = None
    route: str | None = None
    strength_text: str | None = None
    category_id: str | None = None
    ingredients: list[str] = Field(default_factory=list)
    mapping_status: MappingStatus | None = None
    mappings: list[AdminDrugMapping] = Field(default_factory=list)


class AdminDrugListResponse(BaseModel):
    items: list[AdminDrugItem] = Field(default_factory=list)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1, le=100)
    total: int = Field(..., ge=0)
    total_pages: int = Field(..., ge=0)


class AdminDrugDetailResponse(AdminDrugItem):
    pass
