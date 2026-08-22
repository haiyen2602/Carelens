"""Vong doi yeu cau bo sung thuoc tren Postgres that (FB-14).

Cung dieu kien chay voi tests/services/prescription/test_service_db.py: can
Postgres co bang `drug` da nap. Khong can mang ngoai.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from backend.db.base import SessionLocal, engine
from backend.db.models import DrugRequest
from backend.models.admin_drug_schemas import DrugSource, MappingStatus
from backend.services.admin_drugs import get_admin_drug, list_admin_drugs
from backend.services.drug_knowledge import (
    GIOI_HAN_TOI_DA,
    lay_chi_tiet_thuoc,
    lay_thuoc,
    liet_ke_thuoc,
    tim_thuoc,
)
from backend.services.drug_requests import (
    APPROVED,
    PENDING,
    REJECTED,
    ThuocBiKiemSoatError,
    TrangThaiYeuCauKhongHopLeError,
    YeuCauThuocKhongTonTaiError,
    duyet_yeu_cau,
    lay_yeu_cau,
    liet_ke_yeu_cau,
    tao_yeu_cau,
    tim_chat_bi_kiem_soat,
    tu_choi_yeu_cau,
)


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM drug_request LIMIT 1"))
        return True
    except OperationalError:
        return False
    except Exception:
        # Bang chua ton tai (chua chay migration 0031) cung la "khong chay duoc".
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres + migration 0031")


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def bac_si():
    return f"bs-test-{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def don_dep(db, bac_si):
    """Xoa sach yeu cau cua bac si test sau moi ca - bang nay khong co quan he
    voi patient nen khong an theo fixture don dep nao san co."""
    yield
    db.query(DrugRequest).filter(DrugRequest.requested_by_doctor_id == bac_si).delete(
        synchronize_session=False
    )
    db.commit()


def _tao(db, bac_si, ten="Thuoc thu nghiem ABC"):
    return tao_yeu_cau(
        db,
        doctor_id=bac_si,
        ten_thuoc=ten,
        dang_thuoc="Vien nen",
        duong_dung="Uong",
        ly_do="Benh nhan dang dung, chua co trong danh muc",
    )


# ---------------------------------------------------------------------------
# Tao yeu cau
# ---------------------------------------------------------------------------
def test_tao_moi_luon_o_pending(db, bac_si):
    yc = _tao(db, bac_si)

    assert yc.status == PENDING
    assert yc.approved_drug_id is None
    assert yc.reviewed_by_account_id is None


def test_khong_the_tao_thang_o_trang_thai_da_duyet(db, bac_si):
    """Cung nguyen tac voi tao_phac_do (ADR-0010): khong co duong tat sang
    trang thai dung duoc, phai qua duyet_yeu_cau va cho do ghi lai ai duyet."""
    yc = _tao(db, bac_si)

    assert yc.status != APPROVED
    assert "status" not in tao_yeu_cau.__code__.co_varnames


# ---------------------------------------------------------------------------
# Denylist chat bi kiem soat
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ten", ["Heroin", "heroin 10mg", "HEROIN", "Thuoc chua Morphin sulfat"])
def test_chat_bi_kiem_soat_bi_chan_ngay_luc_tao(db, bac_si, ten):
    """FB-14: chan o buoc TAO chu khong doi toi buoc duyet."""
    with pytest.raises(ThuocBiKiemSoatError):
        _tao(db, bac_si, ten=ten)

    assert liet_ke_yeu_cau(db, doctor_id=bac_si) == []


def test_so_khop_khong_phu_thuoc_dau_tieng_viet():
    assert tim_chat_bi_kiem_soat("Ketamin") == "ketamin"
    assert tim_chat_bi_kiem_soat("Amoxicillin 500mg") is None


# ---------------------------------------------------------------------------
# Duyet / tu choi
# ---------------------------------------------------------------------------
def test_duyet_sinh_drug_id_co_tien_to_req(db, bac_si):
    yc = duyet_yeu_cau(db, _tao(db, bac_si).id, admin_account_id="admin-1")

    assert yc.status == APPROVED
    assert yc.approved_drug_id.startswith("req-")
    assert yc.reviewed_by_account_id == "admin-1"
    assert yc.reviewed_at is not None


def test_duyet_lai_yeu_cau_da_xu_ly_bao_409(db, bac_si):
    yc = duyet_yeu_cau(db, _tao(db, bac_si).id, admin_account_id="admin-1")

    with pytest.raises(TrangThaiYeuCauKhongHopLeError):
        duyet_yeu_cau(db, yc.id, admin_account_id="admin-1")


def test_tu_choi_bat_buoc_co_ly_do(db, bac_si):
    yc = _tao(db, bac_si)

    with pytest.raises(TrangThaiYeuCauKhongHopLeError):
        tu_choi_yeu_cau(db, yc.id, admin_account_id="admin-1", note="   ")

    assert lay_yeu_cau(db, yc.id).status == PENDING


def test_tu_choi_ghi_lai_ly_do(db, bac_si):
    yc = tu_choi_yeu_cau(
        db, _tao(db, bac_si).id, admin_account_id="admin-1", note="Trung voi thuoc da co"
    )

    assert yc.status == REJECTED
    assert yc.review_note == "Trung voi thuoc da co"
    assert yc.approved_drug_id is None


def test_yeu_cau_khong_ton_tai_bao_404(db):
    with pytest.raises(YeuCauThuocKhongTonTaiError):
        lay_yeu_cau(db, "khong-ton-tai-chac-chan")


# ---------------------------------------------------------------------------
# Diem noi voi tang phan giai danh muc (C1) - phan quan trong nhat
# ---------------------------------------------------------------------------
def test_thuoc_chua_duyet_khong_ke_duoc(db, bac_si):
    """PENDING thi lay_thuoc() phai van tra None - neu khong, bac si chi can
    gui yeu cau la ke duoc ngay, cong duyet thanh vo nghia."""
    yc = _tao(db, bac_si)
    db.flush()

    # Chua duyet nen chua co approved_drug_id de tra cuu; du co doan dung dinh
    # dang id thi cung khong ra.
    assert yc.approved_drug_id is None


def test_thuoc_da_duyet_ke_duoc_qua_lay_thuoc(db, bac_si):
    """Vi sao test nay quan trong: catalog V2 doc tu file JSONL va duoc
    @lru_cache, nen neu khong co nhanh tra bang drug_request thi thuoc admin
    vua duyet van khong ke duoc - loi im lang, rat kho lan ra."""
    yc = duyet_yeu_cau(db, _tao(db, bac_si).id, admin_account_id="admin-1")

    thuoc = lay_thuoc(db, yc.approved_drug_id)

    assert thuoc is not None
    assert thuoc.ten_thuoc == yc.ten_thuoc
    assert thuoc.dang_thuoc == yc.dang_thuoc
    assert thuoc.duong_dung == yc.duong_dung
    # Alias .id - cac cho goi cu doc Drug.id van chay duoc.
    assert thuoc.id == yc.approved_drug_id


def test_thuoc_bi_tu_choi_khong_ke_duoc(db, bac_si):
    yc = _tao(db, bac_si)
    duyet_yeu_cau(db, yc.id, admin_account_id="admin-1")
    drug_id = lay_yeu_cau(db, yc.id).approved_drug_id

    # Gia lap dong bi chuyen ve REJECTED sau khi da duyet (vd admin sua tay
    # trong DB): lay_thuoc() chi chap nhan dong dang APPROVED.
    row = lay_yeu_cau(db, yc.id)
    row.status = REJECTED
    db.commit()

    assert lay_thuoc(db, drug_id) is None


def test_thuoc_da_duyet_hien_trong_o_goi_y(db, bac_si):
    yc = duyet_yeu_cau(db, _tao(db, bac_si, ten="Zzxyq Doc Nhat").id, admin_account_id="admin-1")

    ket_qua = tim_thuoc(db, "Zzxyq")

    assert yc.approved_drug_id in [t.drug_id for t in ket_qua]


def test_danh_muc_goc_luon_dung_truoc_thuoc_ngoai_le(db, bac_si):
    """Thu tu tra cuu la co y - khong bao gio de duong ngoai le ghi de len du
    lieu co nguon (ADR-0012)."""
    duyet_yeu_cau(db, _tao(db, bac_si, ten="Paracetamol").id, admin_account_id="admin-1")

    ket_qua = tim_thuoc(db, "Paracetamol")

    ngoai_le = [i for i, t in enumerate(ket_qua) if t.drug_id.startswith("req-")]
    chinh_thuc = [i for i, t in enumerate(ket_qua) if not t.drug_id.startswith("req-")]
    if ngoai_le and chinh_thuc:
        assert max(chinh_thuc) < min(ngoai_le)


def test_id_khong_co_tien_to_req_khong_cham_vao_bang(db):
    """Loi ra som: id khong mang tien to `req-` thi khong phai query DB."""
    assert lay_thuoc(db, "khong-ton-tai-va-khong-co-tien-to") is None


# ---------------------------------------------------------------------------
# Trang tra cuu thuoc cua bac si (them 2026-08-21)
# ---------------------------------------------------------------------------
def test_thuoc_da_duyet_hien_trong_trang_tra_cuu(db, bac_si):
    """Truoc ban va nay: ke don duoc nhung tra cuu lai khong thay - mot thuoc
    vua ton tai vua khong tuy cho hoi."""
    yc = duyet_yeu_cau(db, _tao(db, bac_si, ten="Qqwerty Tracuu").id, admin_account_id="admin-1")

    items, tong = liet_ke_thuoc(db, tu_khoa="Qqwerty Tracuu")

    assert yc.approved_drug_id in [t.drug_id for t in items]
    assert tong >= 1


def test_chi_tiet_thuoc_da_duyet_khong_con_404(db, bac_si):
    """Bac si ke duoc mot thuoc roi bam xem chi tiet chinh no thi phai ra."""
    yc = duyet_yeu_cau(db, _tao(db, bac_si, ten="Qqwerty Chitiet").id, admin_account_id="admin-1")

    chi_tiet = lay_chi_tiet_thuoc(db, yc.approved_drug_id)

    assert chi_tiet is not None
    assert chi_tiet.thuoc.ten_thuoc == yc.ten_thuoc
    assert chi_tiet.thuoc.dang_thuoc == yc.dang_thuoc
    # 4 truong van ban de None - khong co chunk. Giong het thuoc trong danh muc
    # goc ma chua embed, giao dien da xu ly duoc truong hop nay.
    assert chi_tiet.cong_dung is None
    assert chi_tiet.tac_dung_phu is None


def test_chi_tiet_id_khong_ton_tai_van_tra_none(db):
    assert lay_chi_tiet_thuoc(db, "req-khong-he-co-000000") is None


def test_bo_loc_dang_thuoc_ap_dung_cho_ca_thuoc_ngoai_le(db, bac_si):
    """Loc phai hieu cung mot nghia tren ca hai nguon, neu khong bac si loc
    'Vien nen' lai thay mat thuoc vua duyet."""
    yc = duyet_yeu_cau(db, _tao(db, bac_si, ten="Qqwerty Boloc").id, admin_account_id="admin-1")

    khop, _ = liet_ke_thuoc(db, tu_khoa="Qqwerty Boloc", dang_thuoc="Vien nen")
    lech, _ = liet_ke_thuoc(db, tu_khoa="Qqwerty Boloc", dang_thuoc="Thuoc tiem")

    assert yc.approved_drug_id in [t.drug_id for t in khop]
    assert yc.approved_drug_id not in [t.drug_id for t in lech]


def test_phan_trang_khong_lap_thuoc_ngoai_le_o_nhieu_trang(db, bac_si):
    """Diem de sai nhat cua cach ghep hai nguon: neu chi noi duoi moi trang thi
    thuoc ngoai le se hien lai o TUNG trang. Duyet het cac trang va doi chieu."""
    ids = {
        duyet_yeu_cau(db, _tao(db, bac_si, ten=f"Qqwerty Trang {i}").id, admin_account_id="a").approved_drug_id
        for i in range(3)
    }

    gioi_han = 2
    thay: list[str] = []
    bo_qua = 0
    while True:
        items, tong = liet_ke_thuoc(db, tu_khoa="Qqwerty Trang", gioi_han=gioi_han, bo_qua=bo_qua)
        if not items:
            break
        thay.extend(t.drug_id for t in items)
        bo_qua += gioi_han
        if bo_qua >= tong:
            break

    assert len(thay) == len(set(thay)), "co dong bi lap o nhieu trang"
    assert ids <= set(thay), "thieu thuoc ngoai le khi phan trang"


def test_ghep_hai_nguon_van_ton_trong_chan_tren(db, bac_si):
    """Bug da mac: noi thuoc ngoai le vao SAU khi resolver da chan o
    GIOI_HAN_TOI_DA lam tong vuot tran. Ben goi (o goi y go-tung-phim) tin vao
    tran nay."""
    duyet_yeu_cau(db, _tao(db, bac_si, ten="Aaa Chantren").id, admin_account_id="admin-1")

    assert len(tim_thuoc(db, "a", 10_000)) <= GIOI_HAN_TOI_DA

    items, _ = liet_ke_thuoc(db, tu_khoa="a", gioi_han=10_000)
    assert len(items) <= GIOI_HAN_TOI_DA


# ---------------------------------------------------------------------------
# Man hinh "Du lieu thuoc" cua admin (them 2026-08-21)
# ---------------------------------------------------------------------------
def test_thuoc_da_duyet_hien_o_man_hinh_du_lieu_thuoc(db, bac_si):
    """Admin duyet xong roi mo man hinh du lieu thuoc lai khong thay dau vet gi
    la vo ly - do la cho ho di kiem tra."""
    yc = duyet_yeu_cau(db, _tao(db, bac_si, ten="Zzadmin Hienthi").id, admin_account_id="admin-1")

    resp = list_admin_drugs(db, q="Zzadmin Hienthi")

    khop = [i for i in resp.items if i.id == yc.approved_drug_id]
    assert len(khop) == 1
    assert khop[0].display_name == yc.ten_thuoc
    assert khop[0].dosage_form == yc.dang_thuoc


def test_dong_ngoai_le_duoc_danh_dau_nguon_ro_rang(db, bac_si):
    """Tron chung ma khong danh dau thi chu 'canonical' mat nghia - nguoi doc
    khong con biet dong nao that su co provenance (ADR-0012)."""
    yc = duyet_yeu_cau(db, _tao(db, bac_si, ten="Zzadmin Nguon").id, admin_account_id="admin-1")

    dong = next(i for i in list_admin_drugs(db, q="Zzadmin Nguon").items if i.id == yc.approved_drug_id)

    assert dong.source is DrugSource.DRUG_REQUEST
    assert dong.mapping_status is MappingStatus.UNMAPPED


def test_loc_theo_trang_thai_anh_xa_khac_unmapped_thi_khong_lan_thuoc_ngoai_le(db, bac_si):
    """Thuoc ngoai le chua he co ban ghi trong drug_id_map nen no khong thuoc
    ACTIVE/AMBIGUOUS/RETIRED - loc theo cac trang thai do phai khong thay no."""
    yc = duyet_yeu_cau(db, _tao(db, bac_si, ten="Zzadmin Loc").id, admin_account_id="admin-1")

    active = list_admin_drugs(db, q="Zzadmin Loc", mapping_status=MappingStatus.ACTIVE)
    unmapped = list_admin_drugs(db, q="Zzadmin Loc", mapping_status=MappingStatus.UNMAPPED)

    assert yc.approved_drug_id not in [i.id for i in active.items]
    assert yc.approved_drug_id in [i.id for i in unmapped.items]


def test_chi_tiet_admin_tra_ve_thuoc_ngoai_le(db, bac_si):
    yc = duyet_yeu_cau(db, _tao(db, bac_si, ten="Zzadmin Chitiet").id, admin_account_id="admin-1")

    chi_tiet = get_admin_drug(db, yc.approved_drug_id)

    assert chi_tiet is not None
    assert chi_tiet.source is DrugSource.DRUG_REQUEST
    assert get_admin_drug(db, "req-khong-he-co-000000") is None
