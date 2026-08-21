"""Chan gia tri co the phi thuc te o TANG SCHEMA (FB-08, FB-09).

Vi sao test o day chu khong phai o frontend: rang buoc cu chi la `min`/`max`
tren the <input> HTML, ma HTML bo qua duoc bang DevTools hoac mot lenh curl.
Reviewer nhap chieu cao 18 cm van luu duoc. Nhom test nay kiem chinh cai chan
that - schema pydantic, thu ma khong client nao di vong qua duoc.

Test thang schema thay vi qua HTTP: chan nam o schema nen khong can dung app,
va moi endpoint nhan hai schema nay deu duoc bao ve cung luc.
"""

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from backend.models.schemas import (
    CAN_NANG_KG_MAX,
    CAN_NANG_KG_MIN,
    CHIEU_CAO_CM_MAX,
    CHIEU_CAO_CM_MIN,
    TUOI_TOI_DA,
    PatientHealthUpdateRequest,
    PatientProfileUpdateRequest,
)

# Ca hai schema deu phai chan giong nhau - bo sot mot cai la con duong vong.
SCHEMAS = [PatientHealthUpdateRequest, PatientProfileUpdateRequest]


@pytest.mark.parametrize("schema", SCHEMAS)
def test_chieu_cao_18cm_bi_tu_choi(schema):
    """Chinh xac truong hop reviewer neu trong FB-08."""
    with pytest.raises(ValidationError):
        schema(height_cm=18)


@pytest.mark.parametrize("schema", SCHEMAS)
@pytest.mark.parametrize(
    "gia_tri",
    [
        1.7,  # nham don vi: go met thay vi cm
        17,  # thieu mot chu so cua 170
        0,
        -170,
        CHIEU_CAO_CM_MIN - 0.1,
        CHIEU_CAO_CM_MAX + 0.1,
    ],
)
def test_chieu_cao_ngoai_khoang_bi_tu_choi(schema, gia_tri):
    with pytest.raises(ValidationError):
        schema(height_cm=gia_tri)


@pytest.mark.parametrize("schema", SCHEMAS)
@pytest.mark.parametrize("gia_tri", [CHIEU_CAO_CM_MIN, 50, 170, 170.5, CHIEU_CAO_CM_MAX])
def test_chieu_cao_trong_khoang_duoc_chap_nhan(schema, gia_tri):
    """Ca hai bien deu phai LOT - chan o dung bien, khong lech mot don vi.

    170.5 co trong danh sach co y: chieu cao cho phep mot chu so thap phan,
    khong ep so nguyen.
    """
    assert schema(height_cm=gia_tri).height_cm == gia_tri


@pytest.mark.parametrize("schema", SCHEMAS)
@pytest.mark.parametrize("gia_tri", [0, 0.5, -60, CAN_NANG_KG_MIN - 0.1, CAN_NANG_KG_MAX + 0.1])
def test_can_nang_ngoai_khoang_bi_tu_choi(schema, gia_tri):
    with pytest.raises(ValidationError):
        schema(weight_kg=gia_tri)


@pytest.mark.parametrize("schema", SCHEMAS)
@pytest.mark.parametrize("gia_tri", [CAN_NANG_KG_MIN, 3, 65, 52.3, CAN_NANG_KG_MAX])
def test_can_nang_trong_khoang_duoc_chap_nhan(schema, gia_tri):
    assert schema(weight_kg=gia_tri).weight_kg == gia_tri


@pytest.mark.parametrize("schema", SCHEMAS)
def test_bo_trong_van_hop_le(schema):
    """Partial update: None nghia la "khong doi", KHONG phai gia tri xau."""
    doi_tuong = schema()
    assert doi_tuong.height_cm is None
    assert doi_tuong.weight_kg is None


# ---------------------------------------------------------------------------
# Ngay sinh (FB-09 - "gate cho do tuoi")
# ---------------------------------------------------------------------------
def test_ngay_sinh_tuong_lai_bi_tu_choi():
    with pytest.raises(ValidationError):
        PatientProfileUpdateRequest(date_of_birth=date.today() + timedelta(days=1))


def test_ngay_sinh_qua_xa_bi_tu_choi():
    qua_xa = date.today().replace(year=date.today().year - TUOI_TOI_DA - 1)
    with pytest.raises(ValidationError):
        PatientProfileUpdateRequest(date_of_birth=qua_xa)


def test_ngay_sinh_hom_nay_van_hop_le():
    """Tre so sinh dang ky trong ngay - bien nay phai lot, khong duoc chan."""
    hom_nay = date.today()
    assert PatientProfileUpdateRequest(date_of_birth=hom_nay).date_of_birth == hom_nay


def test_ngay_sinh_hop_le_binh_thuong():
    ngay = date(1950, 3, 15)
    assert PatientProfileUpdateRequest(date_of_birth=ngay).date_of_birth == ngay
