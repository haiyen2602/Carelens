"""generate_next_patient_id() (backend/services/patient_id.py) PHAI luon sinh
dung dang BNxxxxx (BN + it nhat 5 chu so), lay dung SO LON NHAT hien co (so
sanh theo GIA TRI SO, khong phai so sanh chuoi - "BN7" phai duoc hieu la 7,
lon hon "BN00002"), va bo qua moi ID khong khop dang nay (UUID, slug tu do
nhu "demo-patient-01"...). Dung FAKE SESSION (khong can Postgres that) - chi
can gia lap dung `db.execute(select(...)).scalars().all()`, khong phu thuoc
chi tiet cua SQLAlchemy select() thuc su tra ve gi."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services.patient_id import generate_next_patient_id  # noqa: E402


class _FakeScalars:
    def __init__(self, ids: list[str]) -> None:
        self._ids = ids

    def all(self) -> list[str]:
        return self._ids


class _FakeResult:
    def __init__(self, ids: list[str]) -> None:
        self._ids = ids

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self._ids)


class _FakeSession:
    """Chi can dung `.execute(stmt)` - noi dung `stmt` khong quan trong voi
    fake nay, function duoi test khong doc gi tu no ngoai goi execute()."""

    def __init__(self, existing_ids: list[str]) -> None:
        self._existing_ids = existing_ids

    def execute(self, _stmt) -> _FakeResult:
        return _FakeResult(self._existing_ids)


def test_empty_db_starts_at_bn00001() -> None:
    assert generate_next_patient_id(_FakeSession([])) == "BN00001"


def test_next_id_is_max_plus_one_not_count_plus_one() -> None:
    """Neu benh nhan BN00003 bi xoa (chi con BN00001, BN00002, BN00004), ID
    tiep theo phai la BN00005 (max+1), KHONG phai BN00003 (dem so luong+1) -
    tranh cap lai 1 ID cu co the van con tham chieu o noi khac (prescription/
    dose_event.patient_id, khong co FK rang buoc - xem docstring class
    Patient)."""
    existing = ["BN00001", "BN00002", "BN00004"]
    assert generate_next_patient_id(_FakeSession(existing)) == "BN00005"


def test_compares_by_numeric_value_not_string_order() -> None:
    """"BN7" (chua zero-pad, co the con sot tu du lieu demo cu) phai duoc
    hieu la so 7 - LON HON "BN00002" (=2) - neu so sanh nham theo CHUOI,
    "BN00002" > "BN7" (ky tu '0' < '7'), se sinh sai ID tiep theo."""
    existing = ["BN00002", "BN7"]
    assert generate_next_patient_id(_FakeSession(existing)) == "BN00008"


def test_ignores_ids_not_matching_bn_pattern() -> None:
    """UUID (duong /auth/register CU, da sua) va slug tu do (du lieu demo cu
    nhu "demo-patient-01") khong duoc tinh vao - chi Patient.id khop dung
    dang BN<so> moi anh huong ket qua."""
    existing = [
        "aeb7b709-4639-442b-9543-647373abcdef",
        "demo-patient-01",
        "BN00002",
    ]
    assert generate_next_patient_id(_FakeSession(existing)) == "BN00003"


def test_pads_to_at_least_five_digits() -> None:
    assert generate_next_patient_id(_FakeSession(["BN00001"])) == "BN00002"
    assert generate_next_patient_id(_FakeSession(["BN00099"])) == "BN00100"


def test_grows_digit_width_past_five_instead_of_truncating() -> None:
    """Vuot 99999 khong duoc cat ngan/quay lai 0 - phai tu mo rong thanh 6
    chu so tro len."""
    assert generate_next_patient_id(_FakeSession(["BN99999"])) == "BN100000"


def test_none_id_does_not_crash() -> None:
    """Phong thu - Patient.id ve ly thuyet khong nullable (primary_key), nhung
    ham khong duoc crash neu gap None trong danh sach (vd du lieu la/test
    dung sai)."""
    assert generate_next_patient_id(_FakeSession(["BN00001", None])) == "BN00002"  # type: ignore[list-item]
