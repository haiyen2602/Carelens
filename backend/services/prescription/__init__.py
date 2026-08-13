"""Domain `prescription` — vòng đời phác đồ (specs/domains.md).

Cửa công khai của domain. Domain khác import từ đây, không đào vào module con
(ADR-0002). Lỗi nghiệp vụ cũng xuất ở đây để tầng `api/` bắt được cả họ bằng
một `except VmecError`.
"""

from backend.services.prescription.errors import (
    KhongTimThayError,
    TrangThaiKhongHopLeError,
    ViPhamNghiepVuError,
    VmecError,
)
from backend.services.prescription.service import (
    ACTIVE,
    DRAFT,
    REJECTED,
    SO_NGAY_MAC_DINH,
    STOPPED,
    dem_lieu,
    dung_phac_do,
    duyet_phac_do,
    lay_phac_do,
    liet_ke_phac_do,
    sua_phac_do,
    tao_phac_do,
    tu_choi_phac_do,
)

__all__ = [
    "ACTIVE",
    "DRAFT",
    "REJECTED",
    "SO_NGAY_MAC_DINH",
    "STOPPED",
    "KhongTimThayError",
    "TrangThaiKhongHopLeError",
    "ViPhamNghiepVuError",
    "VmecError",
    "dem_lieu",
    "dung_phac_do",
    "duyet_phac_do",
    "lay_phac_do",
    "liet_ke_phac_do",
    "sua_phac_do",
    "tao_phac_do",
    "tu_choi_phac_do",
]
