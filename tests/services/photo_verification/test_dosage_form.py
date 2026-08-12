"""Kiểm chứng việc quy đổi dạng bào chế sang đơn vị mà mô hình thị giác đếm được.

Phân loại sai ở đây dẫn thẳng tới việc báo bệnh nhân đã uống đủ thuốc trong khi
không phải, nên test bám vào DỮ LIỆU THẬT: các giá trị `dang_thuoc` dưới đây lấy
từ `data pharmacy/` (3688 thuốc), không phải ví dụ bịa ra.

Không cần mạng, không cần DB, không gọi mô hình.
"""

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from backend.services.photo_verification.dosage_form import (
    MatchMode,
    classify,
    count_keys_hop_le,
)
from backend.vlm_demthuoc.prompts import COUNT_KEYS

REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Dạng đếm được từng cái — EXACT
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "dang_thuoc",
    [
        "Viên nén",
        "Viên nén bao phim",
        "Viên nén bao đường",
        "Viên nén bao tan trong ruột",
        "Viên nén bao phim tan trong ruột",
        "Viên nén phóng thích kéo dài",
    ],
)
def test_moi_bien_the_cua_vien_nen_deu_ve_cung_mot_khoa(dang_thuoc):
    """Sáu cách viết khác nhau, cùng một thứ người bệnh cầm trên tay."""
    form = classify(dang_thuoc)
    assert form.count_key == "vien_nen"
    assert form.mode is MatchMode.EXACT


@pytest.mark.parametrize("dang_thuoc", ["Hoàn cứng", "Hoàn mềm"])
def test_vien_hoan_thuoc_co_truyen_van_dem_duoc(dang_thuoc):
    """Thuốc y học cổ truyền vẫn là viên tròn cầm được, không phải dạng lạ."""
    form = classify(dang_thuoc)
    assert form.count_key == "vien_nen"
    assert form.mode is MatchMode.EXACT


@pytest.mark.parametrize("dang_thuoc", ["Viên nang", "Viên nang cứng", "Viên nang mềm"])
def test_vien_nang_khong_bi_xep_nham_thanh_vien_nen(dang_thuoc):
    """"Viên nang cứng" chứa cả chữ "viên" — luật viên nang phải thắng."""
    form = classify(dang_thuoc)
    assert form.count_key == "vien_nang"
    assert form.mode is MatchMode.EXACT


@pytest.mark.parametrize(
    "dang_thuoc",
    ["Bột pha hỗn dịch uống", "Cốm pha hỗn dịch uống", "Thuốc bột", "Gói bột"],
)
def test_bot_va_com_tinh_theo_goi_chu_khong_theo_lo(dang_thuoc):
    """Chứa "hỗn dịch" nhưng thứ bệnh nhân xé ra là GÓI, không phải lọ nước."""
    form = classify(dang_thuoc)
    assert form.count_key == "goi_thuoc"
    assert form.mode is MatchMode.EXACT


# ---------------------------------------------------------------------------
# Dạng chỉ xác minh được sự có mặt — PRESENCE
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "dang_thuoc",
    [
        "Dung dịch uống",
        "Hỗn dịch uống",
        "Siro",
        "Dung dịch nhỏ mắt",
        "Dung dịch dùng ngoài",
        "Lotion bôi da",
        "Cao lỏng",
        "Dạng dầu",
    ],
)
def test_thuoc_nuoc_chi_xac_minh_duoc_su_co_mat(dang_thuoc):
    """Một lọ siro không nói lên bệnh nhân rót 5ml hay 15ml (BR-4.1)."""
    form = classify(dang_thuoc)
    assert form.count_key == "lo_thuoc"
    assert form.mode is MatchMode.PRESENCE


@pytest.mark.parametrize("dang_thuoc", ["Kem", "Dạng kem", "Thuốc mỡ", "Gel", "Nhũ tương (Gel)"])
def test_thuoc_boi_chi_xac_minh_duoc_su_co_mat(dang_thuoc):
    form = classify(dang_thuoc)
    assert form.count_key == "tuyp_thuoc"
    assert form.mode is MatchMode.PRESENCE


# ---------------------------------------------------------------------------
# Dạng không xác minh được bằng ảnh — SKIP
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "dang_thuoc",
    ["Dung dịch tiêm", "Dung dịch tiêm truyền", "Thuốc tiêm", "Bột pha tiêm"],
)
def test_thuoc_tiem_khong_vao_luong_xac_minh_bang_anh(dang_thuoc):
    """"Bột pha tiêm" là cái bẫy: chứa "bột" nhưng không phải gói thuốc uống."""
    form = classify(dang_thuoc)
    assert form.mode is MatchMode.SKIP
    assert form.count_key is None
    assert not form.xac_minh_duoc_bang_anh


def test_duong_dung_tiem_thang_ca_khi_dang_thuoc_nghe_nhu_uong_duoc():
    """Đường dùng là nguồn thứ hai để bắt thuốc tiêm, và nó nghiêng về phía an toàn."""
    assert classify("Bột pha", duong_dung="Tiêm").mode is MatchMode.SKIP


def test_dang_bao_che_chua_biet_thi_tu_choi_chu_khong_doan(caplog):
    """Đoán bừa ở đây = báo bệnh nhân uống đủ thuốc trong khi không phải."""
    form = classify("Miếng dán giải phóng chậm qua da")

    assert form.mode is MatchMode.SKIP
    assert form.count_key is None
    assert not form.co_luat
    assert "Chưa có luật" in caplog.text  # phải nói ra để còn bổ sung luật


def test_phan_biet_duoc_thuoc_tiem_voi_dang_chua_biet():
    """Cả hai đều SKIP nhưng chỉ một cái là thiếu sót cần bổ sung luật.

    Người dùng cũng cần hai câu khác nhau: thuốc tiêm thì "bấm nút xác nhận",
    còn dạng chưa biết thì là hạn chế của hệ thống.
    """
    assert classify("Dung dịch tiêm").co_luat is True
    assert classify("Miếng dán qua da").co_luat is False


def test_dang_bao_che_rong_thi_bo_qua():
    assert classify("").mode is MatchMode.SKIP
    assert classify("   ", duong_dung="  ").mode is MatchMode.SKIP


# ---------------------------------------------------------------------------
# So khớp theo ranh giới từ
# ---------------------------------------------------------------------------
def test_khong_khop_khi_tu_khoa_chi_la_mot_phan_cua_chu_khac():
    """"thuoc moi" chứa hai ký tự "mo" nhưng không phải thuốc mỡ."""
    assert classify("Thuốc mới").count_key != "tuyp_thuoc"


@pytest.mark.parametrize("cach_viet", ["Viên nén", "viên nén", "VIÊN NÉN", "Vien nen", "  viên   nén  "])
def test_khong_phan_biet_hoa_thuong_va_dau(cach_viet):
    assert classify(cach_viet).count_key == "vien_nen"


# ---------------------------------------------------------------------------
# Bất biến — đúng với mọi đầu vào
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "dang_thuoc",
    ["Viên nén", "Viên nang cứng", "Siro", "Kem", "Bột pha hỗn dịch uống", "Thuốc tiêm", "Lạ hoắc"],
)
def test_skip_luon_di_kem_khoa_dem_rong_va_nguoc_lai(dang_thuoc):
    """Ràng buộc mà bước cộng dồn (GĐ2) dựa vào để khỏi phải kiểm tra None."""
    form = classify(dang_thuoc)
    assert (form.mode is MatchMode.SKIP) == (form.count_key is None)


def test_moi_khoa_tra_ve_deu_ton_tai_trong_count_keys_cua_mo_hinh():
    """Trả về khoá mà mô hình không đếm thì bước đối chiếu sẽ so với số 0 vĩnh viễn."""
    assert count_keys_hop_le() <= set(COUNT_KEYS)


def test_ly_do_luon_co_noi_dung_de_giai_thich_cho_nguoi_dung():
    for dang_thuoc in ["Viên nén", "Siro", "Thuốc tiêm", "Lạ hoắc"]:
        assert classify(dang_thuoc).ly_do.strip()


def test_ket_qua_bat_bien_khong_sua_duoc():
    """`DosageForm` được truyền qua nhiều tầng — sửa được là mở đường cho lỗi khó tìm."""
    with pytest.raises(FrozenInstanceError):
        classify("Viên nén").count_key = "lo_thuoc"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Đối chiếu với toàn bộ dữ liệu thuốc thật
# ---------------------------------------------------------------------------
def _moi_dang_thuoc_that() -> list[str]:
    thu_muc = REPO_ROOT / "data pharmacy"
    if not thu_muc.is_dir():
        return []
    ket_qua: list[str] = []
    for path in thu_muc.rglob("*.json"):
        try:
            noi_dung = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        for thuoc in noi_dung if isinstance(noi_dung, list) else [noi_dung]:
            if isinstance(thuoc, dict) and thuoc.get("dang_thuoc"):
                ket_qua.append(str(thuoc["dang_thuoc"]))
    return ket_qua


def test_phu_duoc_phan_lon_dang_bao_che_co_that_trong_kho_du_lieu():
    """Bảng luật phải phủ được thực tế, không chỉ phủ các ví dụ đã nghĩ ra.

    Ngưỡng 5%: phần còn lại là dạng hiếm (miếng dán, thuốc đặt...) — chấp nhận
    rơi vào SKIP vì chúng vốn không thuộc luồng "đã uống thuốc chưa". Test đỏ
    nghĩa là có một dạng phổ biến bị bỏ sót, phải thêm luật.
    """
    tat_ca = _moi_dang_thuoc_that()
    if not tat_ca:
        pytest.skip("Không có thư mục 'data pharmacy' trong repo")

    # Lọc theo `co_luat`, KHÔNG lọc theo `count_key is None`: thuốc tiêm cũng
    # có count_key rỗng nhưng đó là quyết định có chủ đích, không phải thiếu sót.
    chua_co_luat = [d for d in tat_ca if not classify(d).co_luat]
    ty_le = len(chua_co_luat) / len(tat_ca)

    assert ty_le < 0.05, f"{ty_le:.1%} dạng bào chế chưa có luật, ví dụ: {sorted(set(chua_co_luat))[:10]}"
