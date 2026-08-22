"""Loi nghiep vu cua domain `drug_requests` (ADR-0004 §4).

Ke thua `VmecError` cua domain prescription, cung quy uoc voi
services/scheduling/errors.py - tang `api/` bat mot ho bang mot `except` va
map sang HTTP code theo api-contracts.md §10.
"""

from __future__ import annotations

from backend.services.prescription.errors import VmecError


class YeuCauThuocKhongTonTaiError(VmecError):
    ma_loi = "DRUG_REQUEST_NOT_FOUND"
    http_status = 404


class TrangThaiYeuCauKhongHopLeError(VmecError):
    """Duyet/tu choi mot yeu cau da duoc xu ly roi.

    409 chu khong phai 400: yeu cau dung hinh thuc, chi mau thuan voi trang
    thai hien tai - cung ly do voi TrangThaiKhongHopLeError cua phac do.
    """

    ma_loi = "INVALID_DRUG_REQUEST_STATE"
    http_status = 409


class ThuocBiKiemSoatError(VmecError):
    """Ten thuoc dinh danh sach chat bi kiem soat (FB-14).

    Tach rieng khoi ViPhamNghiepVuError de frontend phan biet duoc: day khong
    phai loi nhap lieu de sua lai, ma la tu choi co chu dich - va de moi lan
    dinh deu truy vet duoc bang `ma_loi` rieng.
    """

    ma_loi = "CONTROLLED_SUBSTANCE_BLOCKED"
    http_status = 422


class TrungThuocTrongDanhMucError(VmecError):
    """Da co thuoc nay trong danh muc - khong can yeu cau bo sung."""

    ma_loi = "DRUG_ALREADY_IN_CATALOG"
    http_status = 409


__all__ = [
    "ThuocBiKiemSoatError",
    "TrangThaiYeuCauKhongHopLeError",
    "TrungThuocTrongDanhMucError",
    "YeuCauThuocKhongTonTaiError",
]
