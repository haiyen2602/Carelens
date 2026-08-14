"""auto_watch_new_patient() (backend/services/doctor_watch.py) - benh nhan
MOI tao PHAI duoc TAT CA bac si dang co trong he thong theo doi ngay (yeu
cau PM 2026-08-14, sua bug "Cảnh báo mới nhất"/chuông thông báo luôn rỗng vì
benh nhan moi khong ai theo doi). Dung FAKE SESSION (khong can Postgres
that) - chi can gia lap dung `db.execute(select(...)).scalars().all()` va
`db.add(...)`, khong phu thuoc chi tiet SQLAlchemy select() thuc su."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db.models import DoctorWatch  # noqa: E402
from backend.services.doctor_watch import auto_watch_new_patient  # noqa: E402


class _FakeScalars:
    def __init__(self, values: list[str]) -> None:
        self._values = values

    def all(self) -> list[str]:
        return self._values


class _FakeResult:
    def __init__(self, values: list[str]) -> None:
        self._values = values

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self._values)


class _FakeSession:
    def __init__(self, doctor_ids: list[str]) -> None:
        self._doctor_ids = doctor_ids
        self.added: list[DoctorWatch] = []

    def execute(self, _stmt) -> _FakeResult:
        return _FakeResult(self._doctor_ids)

    def add(self, obj: DoctorWatch) -> None:
        self.added.append(obj)


def test_creates_one_doctor_watch_per_existing_doctor() -> None:
    db = _FakeSession(["doc-1", "doc-2", "doc-3"])
    auto_watch_new_patient(db, "BN00099")

    assert len(db.added) == 3
    pairs = {(row.doctor_id, row.patient_id) for row in db.added}
    assert pairs == {("doc-1", "BN00099"), ("doc-2", "BN00099"), ("doc-3", "BN00099")}


def test_no_doctors_adds_nothing_no_crash() -> None:
    db = _FakeSession([])
    auto_watch_new_patient(db, "BN00099")
    assert db.added == []


def test_dedupes_duplicate_doctor_ids() -> None:
    """Ve ly thuyet Account.doctor_id khong nen lap (moi bac si 1 tai khoan),
    nhung ham khong duoc tao 2 dong DoctorWatch trung (doctor_id, patient_id)
    NEU du lieu co trung - se vi pham unique constraint that o DB
    (uq_doctor_watch_doctor_patient, backend/db/models.py)."""
    db = _FakeSession(["doc-1", "doc-1", "doc-2"])
    auto_watch_new_patient(db, "BN00099")

    assert len(db.added) == 2
    pairs = {(row.doctor_id, row.patient_id) for row in db.added}
    assert pairs == {("doc-1", "BN00099"), ("doc-2", "BN00099")}
