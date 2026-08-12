"""Kiểm chứng việc cộng dồn đơn thuốc và đối chiếu với số mô hình đếm được.

Sai ở đây dẫn tới hai hậu quả ngược nhau, đều nghiêm trọng: báo "đã uống đủ"
khi thực tế thiếu thuốc, hoặc bắt người già chụp đi chụp lại một liều vốn đã
đúng cho tới khi họ bỏ dùng app.

Không cần mạng, không cần DB, không cần webcam.
"""

from backend.services.photo_verification.matcher import (
    KetQua,
    doi_chieu,
    doi_chieu_don_thuoc,
    tinh_yeu_cau,
)


def thuoc(ten="Thuốc A", dang="Viên nén", so_vien=1, duong_dung="Uống"):
    """Một phần tử trong `dose_event.expected_items`."""
    return {
        "drug_id": "d1",
        "ten_thuoc": ten,
        "dang_thuoc": dang,
        "so_vien": so_vien,
        "duong_dung": duong_dung,
    }


# ---------------------------------------------------------------------------
# Cộng dồn nhiều thuốc trong một liều
# ---------------------------------------------------------------------------
def test_hai_thuoc_cung_dang_thi_cong_don_so_vien():
    """Bệnh nhân bày cả hai ra một lần rồi chụp một ảnh, nên số phải cộng lại."""
    yeu_cau = tinh_yeu_cau([thuoc("Amlodipine", so_vien=1), thuoc("Losartan", so_vien=2)])

    assert yeu_cau.so_luong == {"vien_nen": 3}


def test_thuoc_khac_dang_thi_dem_rieng_tung_dang():
    yeu_cau = tinh_yeu_cau(
        [thuoc("Amlodipine", dang="Viên nén", so_vien=2), thuoc("Omeprazole", dang="Viên nang cứng", so_vien=1)]
    )

    assert yeu_cau.so_luong == {"vien_nen": 2, "vien_nang": 1}


def test_tong_vien_cong_ca_nang_lan_nen():
    """Khớp cách `CountResult.total_pills` tính, để nói cùng một con số với bệnh nhân."""
    yeu_cau = tinh_yeu_cau(
        [thuoc(dang="Viên nén", so_vien=2), thuoc(dang="Viên nang mềm", so_vien=1), thuoc(dang="Siro")]
    )

    assert yeu_cau.tong_vien == 3  # lọ siro không phải viên


def test_hai_lo_nuoc_van_chi_can_thay_mot_lo():
    """PRESENCE không cộng dồn — ảnh không nói được bệnh nhân rót bao nhiêu ml."""
    yeu_cau = tinh_yeu_cau([thuoc("Siro ho", dang="Siro"), thuoc("Men tiêu hoá", dang="Dung dịch uống")])

    assert yeu_cau.so_luong == {"lo_thuoc": 1}


def test_lieu_rong_thi_khong_yeu_cau_gi():
    assert not tinh_yeu_cau([]).xac_minh_duoc_bang_anh


# ---------------------------------------------------------------------------
# Đối chiếu — khớp
# ---------------------------------------------------------------------------
def test_dung_so_luong_thi_khop():
    ket_qua = doi_chieu_don_thuoc(
        [thuoc(so_vien=2), thuoc(dang="Viên nang", so_vien=1)], {"vien_nen": 2, "vien_nang": 1}
    )

    assert ket_qua.ket_qua is KetQua.KHOP
    assert ket_qua.khop
    assert not ket_qua.thieu and not ket_qua.thua


def test_vo_hop_lot_vao_anh_khong_bi_tinh_la_thua():
    """Người già hay cầm cả vỏ hộp lên chụp. Tính là thừa thì ai cũng trượt."""
    ket_qua = doi_chieu_don_thuoc([thuoc(so_vien=2)], {"vien_nen": 2, "hop_thuoc": 1})

    assert ket_qua.khop


def test_thay_nhieu_lo_hon_van_khop():
    """PRESENCE chỉ hỏi "có lọ thuốc không", không hỏi "có mấy lọ"."""
    assert doi_chieu_don_thuoc([thuoc(dang="Siro")], {"lo_thuoc": 3}).khop


def test_khoa_vang_mat_trong_ket_qua_dem_duoc_coi_nhu_bang_khong():
    """Mô hình chỉ trả về dạng nó thấy — thiếu khoá nghĩa là không thấy cái nào."""
    ket_qua = doi_chieu_don_thuoc([thuoc(so_vien=1)], {})

    assert ket_qua.thieu == {"vien_nen": 1}


# ---------------------------------------------------------------------------
# Đối chiếu — lệch
# ---------------------------------------------------------------------------
def test_thieu_thuoc_thi_bao_thieu_dung_dang():
    ket_qua = doi_chieu_don_thuoc(
        [thuoc(dang="Viên nén", so_vien=2), thuoc(dang="Viên nang", so_vien=1)],
        {"vien_nen": 2, "vien_nang": 0},
    )

    assert ket_qua.ket_qua is KetQua.LECH
    assert ket_qua.thieu == {"vien_nang": 1}
    assert not ket_qua.thua


def test_thua_thuoc_thi_bao_thua():
    ket_qua = doi_chieu_don_thuoc([thuoc(so_vien=1)], {"vien_nen": 3})

    assert ket_qua.ket_qua is KetQua.LECH
    assert ket_qua.thua == {"vien_nen": 2}


def test_dang_thuoc_khong_co_trong_don_bi_tinh_la_thua():
    """Bày nhầm viên nang của liều khác vào — phải phát hiện được."""
    ket_qua = doi_chieu_don_thuoc([thuoc(dang="Viên nén", so_vien=1)], {"vien_nen": 1, "vien_nang": 2})

    assert ket_qua.ket_qua is KetQua.LECH
    assert ket_qua.thua == {"vien_nang": 2}


def test_khong_thay_lo_nuoc_thi_bao_thieu():
    assert doi_chieu_don_thuoc([thuoc(dang="Siro")], {"vien_nen": 0}).thieu == {"lo_thuoc": 1}


def test_lieu_tron_vien_va_nuoc_phai_dung_ca_hai_moi_khop():
    don = [thuoc("Amlodipine", dang="Viên nén", so_vien=1), thuoc("Siro ho", dang="Siro")]

    assert doi_chieu_don_thuoc(don, {"vien_nen": 1, "lo_thuoc": 1}).khop
    assert not doi_chieu_don_thuoc(don, {"vien_nen": 1, "lo_thuoc": 0}).khop
    assert not doi_chieu_don_thuoc(don, {"vien_nen": 0, "lo_thuoc": 1}).khop


# ---------------------------------------------------------------------------
# Liều không xác minh được bằng ảnh
# ---------------------------------------------------------------------------
def test_lieu_toan_thuoc_tiem_thi_khong_phai_la_lech():
    """Bệnh nhân không làm gì sai — hệ thống chỉ không có cách kiểm chứng."""
    ket_qua = doi_chieu_don_thuoc([thuoc("Insulin", dang="Dung dịch tiêm", duong_dung="Tiêm")], {})

    assert ket_qua.ket_qua is KetQua.KHONG_XAC_MINH_DUOC
    assert not ket_qua.khop
    assert "bấm nút xác nhận" in ket_qua.thong_bao


def test_thuoc_tiem_lan_trong_lieu_van_doi_chieu_phan_con_lai():
    """Bỏ qua đúng thuốc không kiểm được, không bỏ qua cả liều."""
    ket_qua = doi_chieu_don_thuoc(
        [thuoc("Amlodipine", dang="Viên nén", so_vien=2), thuoc("Insulin", dang="Dung dịch tiêm", duong_dung="Tiêm")],
        {"vien_nen": 2},
    )

    assert ket_qua.khop
    assert [t.ten_thuoc for t in ket_qua.yeu_cau.bo_qua] == ["Insulin"]
    assert "Insulin" in ket_qua.thong_bao  # phải nói ra phần chưa kiểm được


def test_don_khong_ghi_so_vien_thi_bo_qua_kem_ly_do_chu_khong_doan():
    for so_vien in [None, 0, -1, True, "hai viên", 1.5]:
        yeu_cau = tinh_yeu_cau([thuoc(so_vien=so_vien)])

        assert not yeu_cau.xac_minh_duoc_bang_anh, f"so_vien={so_vien!r} lẽ ra phải bị bỏ qua"
        assert "không ghi rõ số lượng" in yeu_cau.bo_qua[0].ly_do


# ---------------------------------------------------------------------------
# Câu nói với bệnh nhân (ADR-0011 quy tắc 7)
# ---------------------------------------------------------------------------
def test_thong_bao_neu_ro_lech_o_dang_nao_chu_khong_chi_bao_that_bai():
    ket_qua = doi_chieu_don_thuoc(
        [thuoc(dang="Viên nén", so_vien=2), thuoc(dang="Viên nang", so_vien=1)],
        {"vien_nen": 2, "vien_nang": 0},
    )

    assert "viên nang" in ket_qua.thong_bao.lower()
    assert "thiếu" in ket_qua.thong_bao.lower()


def test_thong_bao_luc_khop_nhac_lai_so_luong_da_dem():
    thong_bao = doi_chieu_don_thuoc([thuoc(so_vien=3)], {"vien_nen": 3}).thong_bao

    assert "3 viên nén" in thong_bao


def test_thong_bao_liet_ke_nhieu_dang_bang_tieng_viet_tu_nhien():
    thong_bao = doi_chieu_don_thuoc(
        [thuoc(dang="Viên nén", so_vien=2), thuoc(dang="Viên nang", so_vien=1)], {"vien_nen": 2, "vien_nang": 1}
    ).thong_bao

    assert "và" in thong_bao


def test_moi_ket_qua_deu_co_thong_bao_khong_rong():
    truong_hop = [
        ([thuoc(so_vien=1)], {"vien_nen": 1}),
        ([thuoc(so_vien=1)], {"vien_nen": 0}),
        ([thuoc(dang="Dung dịch tiêm", duong_dung="Tiêm")], {}),
        ([], {}),
    ]
    for expected_items, dem_duoc in truong_hop:
        assert doi_chieu_don_thuoc(expected_items, dem_duoc).thong_bao.strip()


# ---------------------------------------------------------------------------
# Bất biến
# ---------------------------------------------------------------------------
def test_khop_chi_dung_khi_khong_thieu_va_khong_thua():
    truong_hop = [
        ({"vien_nen": 2}, True),
        ({"vien_nen": 1}, False),
        ({"vien_nen": 3}, False),
        ({}, False),
    ]
    for dem_duoc, mong_doi in truong_hop:
        ket_qua = doi_chieu_don_thuoc([thuoc(so_vien=2)], dem_duoc)

        assert ket_qua.khop is mong_doi
        assert ket_qua.khop == (not ket_qua.thieu and not ket_qua.thua)


def test_doi_chieu_khong_sua_du_lieu_dau_vao():
    """Kết quả đi qua nhiều tầng — sửa lén đầu vào là lỗi rất khó lần ra."""
    dem_duoc = {"vien_nen": 2}
    yeu_cau = tinh_yeu_cau([thuoc(so_vien=2)])

    doi_chieu(yeu_cau, dem_duoc)

    assert dem_duoc == {"vien_nen": 2}
    assert yeu_cau.so_luong == {"vien_nen": 2}
