"""Domain `photo-verification` — xác nhận liều thuốc bằng ảnh (ADR-0011).

Đây là ranh giới công khai của domain. Domain khác import từ đây, KHÔNG đào
vào module con — theo ADR-0002: "Module domain A không import trực tiếp hàm
nội bộ của domain B".
"""

from backend.services.photo_verification.dosage_form import (
    DosageForm,
    MatchMode,
    classify,
    count_keys_hop_le,
)

__all__ = ["DosageForm", "MatchMode", "classify", "count_keys_hop_le"]
