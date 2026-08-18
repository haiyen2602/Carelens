"""Kiểm chứng `nen_anh` — resize + nén JPEG, không phụ thuộc DB/mạng."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from backend.services.photo_verification.image_processing import AnhKhongHopLeError, nen_anh


def _jpeg_bytes(width: int, height: int, color: tuple[int, int, int] = (200, 50, 50)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def test_anh_lon_hon_max_edge_bi_resize():
    goc = _jpeg_bytes(3000, 2000)

    ket_qua = nen_anh(goc, max_edge=1600, jpeg_quality=90)

    with Image.open(io.BytesIO(ket_qua)) as img:
        assert max(img.size) <= 1600
        # ti le khung hinh giu nguyen (3000/2000 = 1.5)
        assert img.size[0] / img.size[1] == pytest.approx(3000 / 2000, rel=0.02)


def test_anh_nho_hon_max_edge_khong_bi_phong_to():
    goc = _jpeg_bytes(800, 600)

    ket_qua = nen_anh(goc, max_edge=1600, jpeg_quality=90)

    with Image.open(io.BytesIO(ket_qua)) as img:
        assert img.size == (800, 600)


def test_output_luon_la_jpeg_hop_le():
    goc = _jpeg_bytes(2000, 2000)

    ket_qua = nen_anh(goc, max_edge=1600, jpeg_quality=90)

    with Image.open(io.BytesIO(ket_qua)) as img:
        assert img.format == "JPEG"


def test_bytes_hong_rem_loi_ro_rang():
    with pytest.raises(AnhKhongHopLeError):
        nen_anh(b"khong phai anh", max_edge=1600, jpeg_quality=90)


def test_bytes_rong_rem_loi_ro_rang():
    with pytest.raises(AnhKhongHopLeError):
        nen_anh(b"", max_edge=1600, jpeg_quality=90)
