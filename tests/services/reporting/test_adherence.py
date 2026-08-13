"""Kiểm chứng compute_adherence_pct (backend/services/reporting/adherence.py)
- 1 chỗ nối duy nhất cho ty le tuan thu, dung chung ca dashboard bac si
(reporting_routes.py) va man hinh caregiver (caregiver_routes.py).

DB gia toi thieu (cung pattern voi tests/services/scheduling/test_generator.py::
_Db) - compute_adherence_pct chi goi db.execute(select(...)).scalars().all(),
khong can Postgres that de kiem tra logic tinh ty le."""

from datetime import UTC, datetime

from backend.services.reporting.adherence import compute_adherence_pct

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)


class _FakeResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class _FakeDb:
    """Tra ve dung danh sach status da chuan bi san - compute_adherence_pct
    khong loc gi them trong Python (loc window_end da nam trong cau SQL that,
    o day gia lap ket qua da loc san, dung de kiem chung LOGIC TINH TY LE)."""

    def __init__(self, due_statuses):
        self._due_statuses = due_statuses

    def execute(self, *_args, **_kwargs):
        return _FakeResult(self._due_statuses)


def test_khong_co_lieu_nao_den_han_tra_ve_none():
    """Chua co du lieu de ket luan - KHONG duoc suy ra 0%."""
    db = _FakeDb([])
    assert compute_adherence_pct(db, "pat_1", now=NOW) is None


def test_tat_ca_da_uong_tra_ve_100():
    db = _FakeDb(["TAKEN", "TAKEN", "TAKEN"])
    assert compute_adherence_pct(db, "pat_1", now=NOW) == 100.0


def test_ty_le_hon_hop_tinh_dung():
    db = _FakeDb(["TAKEN", "TAKEN", "MISSED", "DELAYED"])
    # 2/4 = 50%
    assert compute_adherence_pct(db, "pat_1", now=NOW) == 50.0


def test_khong_co_lieu_nao_duoc_uong_tra_ve_0_khong_phai_none():
    """Khac voi truong hop KHONG CO lieu nao den han (test o tren) - o day CO
    lieu den han, chi la khong lieu nao duoc uong, nen phai la 0.0 (co du
    lieu de ket luan), khong phai None."""
    db = _FakeDb(["MISSED", "MISSED"])
    assert compute_adherence_pct(db, "pat_1", now=NOW) == 0.0


def test_ket_qua_la_float_khong_phai_int_chia_lam_tron():
    db = _FakeDb(["TAKEN", "MISSED", "MISSED"])
    result = compute_adherence_pct(db, "pat_1", now=NOW)
    assert result == (1 / 3) * 100


def test_now_mac_dinh_dung_datetime_now_khi_khong_truyen():
    """Khong truyen `now` van chay duoc (dung datetime.now(UTC) that ben
    trong) - chi kiem tra khong bi loi, khong kiem tra gia tri cu the vi phu
    thuoc thoi gian thuc te."""
    db = _FakeDb(["TAKEN"])
    result = compute_adherence_pct(db, "pat_1")
    assert result == 100.0
