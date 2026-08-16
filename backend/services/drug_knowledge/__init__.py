"""Domain `drug-knowledge` — dữ liệu thuốc có nguồn (specs/domains.md).

Đây là cửa công khai của domain. Các domain khác import từ đây, không đào vào
module con — theo ADR-0002: "Mỗi domain có một chủ sở hữu dữ liệu duy nhất;
domain khác không truy vấn thẳng bảng của domain khác."

Cụ thể: `prescription` cần `dang_thuoc` để ghi vào đơn thuốc thì gọi
`lay_thuoc()`, không tự viết SQL vào bảng `drug`.
"""

import logging

from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.services.drug_knowledge.resolver import (
    GIOI_HAN_TOI_DA,
    NGUONG_GAN_GIONG,
    ThuocTimDuoc,
)
from backend.services.drug_knowledge.resolver import (
    lay_thuoc as _legacy_lay_thuoc,
)
from backend.services.drug_knowledge.resolver import (
    tim_thuoc as _legacy_tim_thuoc,
)
from backend.services.drug_knowledge.v2_agent import DrugCatalogItem, get_v2_agent_knowledge_service

logger = logging.getLogger(__name__)


def tim_thuoc(db: Session, tu_khoa: str, gioi_han: int = 20) -> list[DrugCatalogItem | ThuocTimDuoc]:
    """Search the V2 catalog by default while retaining V1/shadow rollback behavior."""

    mode = get_settings().drug_knowledge_backend
    if mode == "v1":
        return _legacy_tim_thuoc(db, tu_khoa, gioi_han)

    v2_results = get_v2_agent_knowledge_service().search_catalog(tu_khoa, gioi_han)
    if mode == "shadow":
        v1_results = _legacy_tim_thuoc(db, tu_khoa, gioi_han)
        logger.info("drug_catalog_shadow v1_count=%s v2_count=%s", len(v1_results), len(v2_results))
        return v1_results
    return v2_results


def lay_thuoc(db: Session, drug_id: str) -> DrugCatalogItem | ThuocTimDuoc | None:
    """Resolve the public legacy slug through Canonical V2 by default."""

    mode = get_settings().drug_knowledge_backend
    if mode == "v1":
        return _legacy_lay_thuoc(db, drug_id)

    v2_result = get_v2_agent_knowledge_service().get_catalog_item(drug_id)
    if mode == "shadow":
        v1_result = _legacy_lay_thuoc(db, drug_id)
        logger.info("drug_catalog_shadow id=%s v1_found=%s v2_found=%s", drug_id, bool(v1_result), bool(v2_result))
        return v1_result
    return v2_result

__all__ = ["GIOI_HAN_TOI_DA", "NGUONG_GAN_GIONG", "ThuocTimDuoc", "lay_thuoc", "tim_thuoc"]
