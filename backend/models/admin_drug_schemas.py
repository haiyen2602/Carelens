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


class DrugSource(StrEnum):
    """Dong nay den tu dau.

    THEM 2026-08-21 (FB-14). Truoc do man hinh Admin RAG chi co mot nguon nen
    khong can phan biet. Gio co hai, va tron chung ma khong danh dau thi chu
    "canonical" mat nghia - nguoi doc khong con biet dong nao thuc su den tu
    artifact Canonical V2 co provenance (ADR-0012).
    """

    CANONICAL = "CANONICAL"
    # Thuoc bac si xin bo sung, admin da duyet (bang `drug_request`). Chua co
    # trong artifact V2, chua co chunk RAG - xem models.py::DrugRequest.
    DRUG_REQUEST = "DRUG_REQUEST"


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
    # Mac dinh CANONICAL de client cu (chua doc truong nay) khong doi hanh vi.
    source: DrugSource = DrugSource.CANONICAL


class AdminDrugListResponse(BaseModel):
    items: list[AdminDrugItem] = Field(default_factory=list)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1, le=100)
    total: int = Field(..., ge=0)
    total_pages: int = Field(..., ge=0)


class AdminDrugDetailResponse(AdminDrugItem):
    pass


class AdminDrugUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    dosage_form: str | None = Field(default=None, max_length=100)
    route: str | None = Field(default=None, max_length=100)
    strength_text: str | None = Field(default=None, max_length=100)
    mapping_status: MappingStatus | None = None

