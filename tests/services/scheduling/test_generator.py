"""Kiểm chứng sinh `dose_event` từ phác đồ.

Hai quy tắc, hai loại hậu quả nếu sai:
  - không gộp theo giờ  -> bệnh nhân phải chụp nhiều ảnh cho một nắm thuốc
  - không idempotent    -> duyệt lại một phác đồ nhân đôi lịch nhắc

Dùng đối tượng `Prescription` dựng tay (không cần DB thật) — `sinh_dose_event`
chỉ đọc thuộc tính, không tự query.
"""

from datetime import UTC, datetime, timedelta

from backend.services.scheduling.generator import huy_lieu_chua_toi_han, sinh_dose_event

# "Ngày mai" tính động, không hardcode ngày cụ thể: các test không tự truyền
# `bay_gio` mặc định gọi `sinh_dose_event(db, presc)` với bay_gio=None ->
# datetime.now(UTC) thật. Hardcode một ngày cố định sẽ ăn may lúc viết test rồi
# hỏng khi chạy lại sau giờ 08:30 — chính logic "không sinh liều đã trôi qua"
# mà NHÓM TEST NÀY đang kiểm sẽ tự lọc bỏ liều của một ngày đã qua giờ hẹn.
NGAY_MAI = (datetime.now(UTC) + timedelta(days=1)).date().isoformat()


class _Db:
    """DB giả tối thiểu: `add` gom vào danh sách, không chạm mạng/đĩa."""

    def __init__(self):
        self.them = []
        self.xoa = []

    def add(self, obj):
        self.them.append(obj)

    def delete(self, obj):
        self.xoa.append(obj)

    def execute(self, *_a, **_kw):
        class _Rong:
            def scalars(self):
                return self

            def all(self):
                return []
        return _Rong()


class _Presc:
    def __init__(self, id="presc_1", items=None, start_date=None, duration_days=2):
        start_date = start_date or NGAY_MAI
        self.id = id
        self.patient_id = "pat_1"
        self.items = items or []
        self.start_date = start_date
        self.duration_days = duration_days


def thuoc(ten="A", gio_nhac=("08:00",), dang="Viên nén", duong="Uống", so_vien=1):
    return {
        "drug_id": "d1", "ten_thuoc": ten, "dang_thuoc": dang, "duong_dung": duong,
        "so_vien_moi_lan": so_vien, "gio_nhac": list(gio_nhac),
    }


def _gio(db):
    """{scheduled_at: [tên thuốc trong liều đó]}."""
    ra = {}
    for d in db.them:
        ra.setdefault(d.scheduled_at, []).append(d.expected_items)
    return ra


# ---------------------------------------------------------------------------
# Gộp theo giờ
# ---------------------------------------------------------------------------
def test_hai_thuoc_cung_gio_gop_thanh_mot_lieu():
    presc = _Presc(items=[thuoc("A"), thuoc("B")], duration_days=1)
    db = _Db()

    so = sinh_dose_event(db, presc)

    assert so == 1, "hai thuốc cùng 08:00 phải ra đúng một dose_event"
    assert len(db.them[0].expected_items) == 2


def test_thuoc_uong_ngay_2_lan_ra_hai_lieu_rieng():
    presc = _Presc(items=[thuoc("A", gio_nhac=("08:00", "20:00"))], duration_days=1)
    db = _Db()

    assert sinh_dose_event(db, presc) == 2


def test_ba_ngay_mot_gio_moi_ngay_ra_ba_lieu():
    presc = _Presc(items=[thuoc("A")], duration_days=3)
    db = _Db()

    assert sinh_dose_event(db, presc) == 3


def test_moi_lieu_co_dung_cua_so_30_phut():
    presc = _Presc(items=[thuoc("A")], duration_days=1)
    db = _Db()
    sinh_dose_event(db, presc)

    lieu = db.them[0]
    assert (lieu.scheduled_at - lieu.window_start).total_seconds() == 30 * 60
    assert (lieu.window_end - lieu.scheduled_at).total_seconds() == 30 * 60


def test_expected_items_mang_theo_dang_thuoc_va_duong_dung():
    """Đây là mắt xích với tầng đối chiếu ảnh — thiếu 1 trong 2 trường là
    dosage_form.classify() không phân loại được."""
    presc = _Presc(items=[thuoc("A", dang="Siro", duong="Uống")], duration_days=1)
    db = _Db()
    sinh_dose_event(db, presc)

    item = db.them[0].expected_items[0]
    assert item["dang_thuoc"] == "Siro"
    assert item["duong_dung"] == "Uống"


# ---------------------------------------------------------------------------
# Bỏ qua giờ đọc không được, không làm chết cả liều
# ---------------------------------------------------------------------------
def test_gio_sai_dinh_dang_bi_bo_qua_khong_lam_hong_thuoc_khac():
    presc = _Presc(items=[thuoc("A", gio_nhac=("không phải giờ",)), thuoc("B", gio_nhac=("08:00",))], duration_days=1)
    db = _Db()

    assert sinh_dose_event(db, presc) == 1
    assert len(db.them[0].expected_items) == 1
    assert db.them[0].expected_items[0]["ten_thuoc"] == "B"


def test_khong_co_gio_nao_hop_le_thi_khong_sinh_gi():
    presc = _Presc(items=[thuoc("A", gio_nhac=("bậy bạ",))], duration_days=5)
    db = _Db()

    assert sinh_dose_event(db, presc) == 0
    assert db.them == []


# ---------------------------------------------------------------------------
# Không sinh liều đã trôi qua
# ---------------------------------------------------------------------------
def test_khong_sinh_lieu_da_qua_cua_so():
    """Duyệt lúc 14h thì liều 08:00 sáng nay không còn ý nghĩa để nhắc."""
    presc = _Presc(items=[thuoc("A")], start_date="2026-08-12", duration_days=1)
    db = _Db()
    bay_gio = datetime(2026, 8, 12, 14, 0, tzinfo=UTC)

    assert sinh_dose_event(db, presc, bay_gio=bay_gio) == 0


def test_lieu_con_trong_cua_so_van_duoc_sinh():
    presc = _Presc(items=[thuoc("A")], start_date="2026-08-12", duration_days=1)
    db = _Db()
    bay_gio = datetime(2026, 8, 12, 8, 10, tzinfo=UTC)  # còn trong ±30'

    assert sinh_dose_event(db, presc, bay_gio=bay_gio) == 1


# ---------------------------------------------------------------------------
# Idempotent — bấm Duyệt hai lần không nhân đôi lịch
# ---------------------------------------------------------------------------
def test_xoa_lieu_pending_chua_toi_han_truoc_khi_sinh_lai():
    class _LieuCu:
        status = "PENDING"

    class _DbCoDuLieuCu(_Db):
        def execute(self, *_a, **_kw):
            cu = [_LieuCu()]

            class _KetQua:
                def scalars(self):
                    return self

                def all(self):
                    return cu
            return _KetQua()

    presc = _Presc(items=[thuoc("A")], duration_days=1)
    db = _DbCoDuLieuCu()

    sinh_dose_event(db, presc)

    assert len(db.xoa) == 1, "phải xoá liều PENDING cũ trước khi sinh lại"


# Test "liều đã đóng (TAKEN/MISSED) không bị đụng khi sinh lại" cần DB thật để
# xác nhận câu SELECT lọc đúng — xem tests/services/prescription/
# test_service_db.py::test_duyet_lai_khong_dung_den_lieu_da_dong.


# ---------------------------------------------------------------------------
# Dừng phác đồ (BR-1.4)
# ---------------------------------------------------------------------------
def test_huy_lieu_chua_toi_han_tra_ve_so_luong():
    class _Lieu:
        def __init__(self):
            self.status = "PENDING"

    class _DbCoLieu(_Db):
        def execute(self, *_a, **_kw):
            cu = [_Lieu(), _Lieu()]

            class _KetQua:
                def scalars(self):
                    return self

                def all(self):
                    return cu
            return _KetQua()

    db = _DbCoLieu()
    so = huy_lieu_chua_toi_han(db, "presc_1")

    assert so == 2
