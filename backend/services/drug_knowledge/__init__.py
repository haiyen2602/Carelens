"""Domain `drug-knowledge` — dữ liệu thuốc có nguồn (specs/domains.md).

Đây là cửa công khai của domain. Các domain khác import từ đây, không đào vào
module con — theo ADR-0002: "Mỗi domain có một chủ sở hữu dữ liệu duy nhất;
domain khác không truy vấn thẳng bảng của domain khác."

Cụ thể: `prescription` cần `dang_thuoc` để ghi vào đơn thuốc thì gọi
`lay_thuoc()`, không tự viết SQL vào bảng `drug`.
"""

from backend.services.drug_knowledge.resolver import (
    GIOI_HAN_TOI_DA,
    NGUONG_GAN_GIONG,
    ThuocTimDuoc,
    lay_thuoc,
    tim_thuoc,
)

__all__ = ["GIOI_HAN_TOI_DA", "NGUONG_GAN_GIONG", "ThuocTimDuoc", "lay_thuoc", "tim_thuoc"]
