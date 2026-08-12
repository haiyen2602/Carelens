"""Domain `photo-verification` — xác nhận liều thuốc bằng ảnh (ADR-0011).

Đây là ranh giới công khai của domain. Domain khác import từ đây, KHÔNG đào
vào module con — theo ADR-0002: "Module domain A không import trực tiếp hàm
nội bộ của domain B".

Đường dùng thông thường chỉ cần một hàm:

    from backend.services.photo_verification import doi_chieu_don_thuoc

    ket_qua = doi_chieu_don_thuoc(dose_event.expected_items, so_dem_tu_vlm)
    if ket_qua.khop:
        ...
"""

from backend.services.photo_verification.dosage_form import (
    DosageForm,
    MatchMode,
    classify,
    count_keys_hop_le,
)
from backend.services.photo_verification.matcher import (
    KetQua,
    KetQuaDoiChieu,
    ThuocBoQua,
    YeuCauDem,
    doi_chieu,
    doi_chieu_don_thuoc,
    tinh_yeu_cau,
)

__all__ = [
    "DosageForm",
    "KetQua",
    "KetQuaDoiChieu",
    "MatchMode",
    "ThuocBoQua",
    "YeuCauDem",
    "classify",
    "count_keys_hop_le",
    "doi_chieu",
    "doi_chieu_don_thuoc",
    "tinh_yeu_cau",
]
