"""
Lỗi nghiệp vụ của domain `prescription`.

ADR-0004 §4: định nghĩa exception nghiệp vụ riêng trong `services/<domain>/
errors.py`, kế thừa từ một base chung; tầng `api/` bắt và map sang HTTP code
theo api-contracts.md §10.

Vì sao không dùng thẳng `HTTPException` trong service: ADR-0004 §1 yêu cầu
`services/` không import `fastapi`, để logic chạy được trong test mà không phải
dựng app. Một service ném `HTTPException` cũng khiến quy tắc nghiệp vụ dính
chặt vào giao thức HTTP — cùng quy tắc đó sau này gọi từ scheduler hay CLI sẽ
không còn nghĩa gì.

`ma_loi` là `code` trong contract lỗi (§10), tầng api dùng lại nguyên văn nên
frontend phân biệt được các tình huống mà không phải đọc câu chữ tiếng Việt.
"""

from __future__ import annotations


class VmecError(Exception):
    """Gốc cho mọi lỗi nghiệp vụ. Bắt được cả họ bằng một `except`."""

    ma_loi = "VMEC_ERROR"
    http_status = 400

    def __init__(self, thong_bao: str, **chi_tiet: object) -> None:
        super().__init__(thong_bao)
        self.thong_bao = thong_bao
        self.chi_tiet = chi_tiet

    def to_contract(self) -> dict:
        """Đúng hình dạng lỗi của api-contracts.md §10."""
        return {"error": {"code": self.ma_loi, "message": self.thong_bao, "details": self.chi_tiet}}


class KhongTimThayError(VmecError):
    ma_loi = "NOT_FOUND"
    http_status = 404


class TrangThaiKhongHopLeError(VmecError):
    """Chuyển trạng thái không cho phép — vd duyệt một phác đồ đã duyệt.

    409 chứ không phải 400: yêu cầu hợp lệ về hình thức, chỉ là mâu thuẫn với
    trạng thái hiện tại (api-contracts.md §10).
    """

    ma_loi = "INVALID_STATE"
    http_status = 409


class ViPhamNghiepVuError(VmecError):
    """Đúng hình thức nhưng vi phạm ràng buộc nghiệp vụ — 422 theo §10."""

    ma_loi = "BUSINESS_RULE_VIOLATION"
    http_status = 422


__all__ = ["KhongTimThayError", "TrangThaiKhongHopLeError", "ViPhamNghiepVuError", "VmecError"]
