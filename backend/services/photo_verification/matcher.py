"""
Cộng dồn đơn thuốc thành "số cần thấy trong ảnh", rồi đối chiếu với số đếm được.

Một liều có thể gồm nhiều thuốc uống cùng giờ, và bệnh nhân bày tất cả ra rồi
chụp MỘT ảnh. Module này gộp các thuốc đó lại theo dạng bào chế, ra một bảng
"cần thấy bao nhiêu cái mỗi dạng", rồi so với bảng mô hình đếm được.

GỘP THEO DẠNG, KHÔNG THEO THUỐC — đây là điểm quan trọng nhất:

    Mô hình thị giác chỉ đếm được SÁU HÌNH DẠNG. Nó không phân biệt được
    Amlodipine với Panadol, cả hai đều là "viên nén". Nên một liều gồm hai
    thuốc viên nén khác nhau, mỗi thứ 1 viên, chỉ kiểm chứng được ở mức "trong
    ảnh phải có 2 viên nén" — không kiểm chứng được bệnh nhân bày đúng mỗi loại
    một viên hay bày 2 viên cùng một loại.

    Đây là giới hạn cố hữu của bằng chứng bằng ảnh, không phải thiếu sót của
    code. Phải nói thẳng khi trình bày sản phẩm (ADR-0011).

Module nhận `dict[str, int]` chứ không nhận `CountResult`: `vlm_client` kéo theo
`cv2` và `numpy`, mà logic đối chiếu thì không cần thư viện thị giác nào. Tách
ra để chạy test trong vài mili giây và không phụ thuộc webcam. Việc chuyển đổi
`CountResult` -> dict thuộc về tầng cầu nối.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from backend.services.photo_verification.count_keys import COUNT_LABELS_VI
from backend.services.photo_verification.dosage_form import MatchMode, classify

logger = logging.getLogger(__name__)

# Hộp thuốc xuất hiện trong ảnh KHÔNG bị tính là thừa. Không luật nào trong
# `dosage_form` sinh ra khoá này (bác sĩ kê theo viên/gói/lọ chứ không kê "1
# hộp"), nên nếu tính nó là thừa thì mọi bệnh nhân chụp kèm vỏ hộp — chuyện
# rất thường — đều bị báo sai. Vỏ hộp là bao bì, không phải liều thuốc.
_KHONG_TINH_LA_THUA = frozenset({"hop_thuoc"})


class KetQua(StrEnum):
    """Ba kết cục của một lần đối chiếu, không phải hai."""

    KHOP = "khop"
    LECH = "lech"
    # Không thuốc nào trong liều xác minh được bằng ảnh (vd toàn thuốc tiêm).
    # KHÁC HẲN "lệch": bệnh nhân không làm gì sai, hệ thống chỉ không có cách
    # kiểm chứng. Gộp vào `lech` là bắt người ta chụp lại một thứ vô nghĩa.
    KHONG_XAC_MINH_DUOC = "khong_xac_minh_duoc"


@dataclass(frozen=True)
class ThuocBoQua:
    """Một thuốc trong liều nhưng không tham gia đối chiếu ảnh."""

    ten_thuoc: str
    ly_do: str


@dataclass(frozen=True)
class YeuCauDem:
    """Số lượng cần thấy trong ảnh, đã gộp theo dạng bào chế."""

    so_luong: Mapping[str, int]
    che_do: Mapping[str, MatchMode]
    bo_qua: tuple[ThuocBoQua, ...] = ()

    @property
    def xac_minh_duoc_bang_anh(self) -> bool:
        return bool(self.so_luong)

    @property
    def tong_vien(self) -> int:
        """Tổng viên nang + viên nén — cùng cách tính `CountResult.total_pills`.

        Dùng làm con số chính trong câu nói với bệnh nhân ("cháu đếm được 3
        viên"), vì đó là thứ người ta đếm bằng mắt được.
        """
        return self.so_luong.get("vien_nang", 0) + self.so_luong.get("vien_nen", 0)


@dataclass(frozen=True)
class KetQuaDoiChieu:
    ket_qua: KetQua
    yeu_cau: YeuCauDem
    dem_duoc: Mapping[str, int]
    thieu: Mapping[str, int]
    thua: Mapping[str, int]
    thong_bao: str

    @property
    def khop(self) -> bool:
        return self.ket_qua is KetQua.KHOP


def _so_vien(item: Mapping) -> int | None:
    """Số viên mỗi lần, hoặc `None` nếu đơn không ghi rõ.

    `bool` bị loại tay vì trong Python nó là một loại `int` — `True` sẽ lọt qua
    thành "1 viên" nếu chỉ kiểm tra kiểu.
    """
    gia_tri = item.get("so_vien")
    if isinstance(gia_tri, bool) or not isinstance(gia_tri, int) or gia_tri <= 0:
        return None
    return gia_tri


def tinh_yeu_cau(expected_items: Iterable[Mapping]) -> YeuCauDem:
    """Gộp các thuốc trong một liều thành bảng "cần thấy bao nhiêu cái mỗi dạng"."""
    so_luong: defaultdict[str, int] = defaultdict(int)
    che_do: dict[str, MatchMode] = {}
    bo_qua: list[ThuocBoQua] = []

    for item in expected_items:
        ten_thuoc = str(item.get("ten_thuoc") or "thuốc không rõ tên")
        form = classify(str(item.get("dang_thuoc") or ""), str(item.get("duong_dung") or ""))

        if form.mode is MatchMode.SKIP or form.count_key is None:
            bo_qua.append(ThuocBoQua(ten_thuoc, form.ly_do))
            continue

        if form.mode is MatchMode.EXACT:
            so = _so_vien(item)
            if so is None:
                logger.warning("Thuốc %r không có số viên hợp lệ, bỏ qua khi đối chiếu ảnh.", ten_thuoc)
                bo_qua.append(ThuocBoQua(ten_thuoc, "đơn thuốc không ghi rõ số lượng"))
                continue
            so_luong[form.count_key] += so
            # EXACT luôn thắng nếu hai thuốc khác dạng lại cùng khoá đếm: so
            # bằng số chặt hơn so "có mặt", và ở đây chặt hơn nghĩa là an toàn hơn.
            che_do[form.count_key] = MatchMode.EXACT
        else:
            # PRESENCE không cộng dồn: hai lọ siro khác nhau vẫn chỉ cần thấy
            # có lọ thuốc trong ảnh. Số ml uống bao nhiêu thì ảnh không nói được.
            so_luong[form.count_key] = max(so_luong[form.count_key], 1)
            che_do.setdefault(form.count_key, MatchMode.PRESENCE)

    return YeuCauDem(dict(so_luong), che_do, tuple(bo_qua))


def doi_chieu(yeu_cau: YeuCauDem, dem_duoc: Mapping[str, int]) -> KetQuaDoiChieu:
    """So bảng cần đếm với bảng mô hình đếm được."""
    dem_duoc = {khoa: int(so or 0) for khoa, so in dem_duoc.items()}

    if not yeu_cau.xac_minh_duoc_bang_anh:
        return KetQuaDoiChieu(
            KetQua.KHONG_XAC_MINH_DUOC, yeu_cau, dem_duoc, {}, {}, _thong_bao_khong_xac_minh(yeu_cau)
        )

    thieu: dict[str, int] = {}
    thua: dict[str, int] = {}

    for khoa, can in yeu_cau.so_luong.items():
        co = dem_duoc.get(khoa, 0)
        if yeu_cau.che_do[khoa] is MatchMode.EXACT:
            if co < can:
                thieu[khoa] = can - co
            elif co > can:
                thua[khoa] = co - can
        elif co < 1:
            # PRESENCE: thấy 2 lọ cũng không sao — bệnh nhân có thể cầm cả vỏ
            # hộp lẫn lọ. Chỉ "không thấy lọ nào" mới là vấn đề.
            thieu[khoa] = 1

    for khoa, co in dem_duoc.items():
        if co > 0 and khoa not in yeu_cau.so_luong and khoa not in _KHONG_TINH_LA_THUA:
            thua[khoa] = co

    ket_qua = KetQua.KHOP if not thieu and not thua else KetQua.LECH
    return KetQuaDoiChieu(ket_qua, yeu_cau, dem_duoc, thieu, thua, _thong_bao(ket_qua, yeu_cau, thieu, thua))


def doi_chieu_don_thuoc(expected_items: Iterable[Mapping], dem_duoc: Mapping[str, int]) -> KetQuaDoiChieu:
    """Đường tắt cho tầng gọi: từ `dose_event.expected_items` thẳng ra kết quả."""
    return doi_chieu(tinh_yeu_cau(expected_items), dem_duoc)


# ---------------------------------------------------------------------------
# Câu nói với bệnh nhân
#
# ADR-0011 quy tắc 7: phải nói RÕ lệch ở đâu ("cháu đếm được 2 viên nhưng đơn
# là 1 viên"), không được chỉ báo "thất bại". Mọi câu dưới đây sinh từ hiệu số
# và từ `COUNT_LABELS_VI`, không viết cứng — thêm một dạng thuốc mới vào
# `prompts.COUNT_KEYS` là câu tự có, không phải sửa ở đây.
# ---------------------------------------------------------------------------
def _mo_ta(so_luong: Mapping[str, int]) -> str:
    """{"vien_nen": 2, "vien_nang": 1} -> "2 viên nén và 1 viên nang"."""
    phan = [f"{so} {COUNT_LABELS_VI[khoa].lower()}" for khoa, so in sorted(so_luong.items()) if so > 0]
    if not phan:
        return "không có gì"
    if len(phan) == 1:
        return phan[0]
    return ", ".join(phan[:-1]) + " và " + phan[-1]


def _thong_bao_khong_xac_minh(yeu_cau: YeuCauDem) -> str:
    if not yeu_cau.bo_qua:
        return "Liều này không có thuốc nào để đối chiếu bằng ảnh ạ."
    ly_do = yeu_cau.bo_qua[0].ly_do
    ten = ", ".join(thuoc.ten_thuoc for thuoc in yeu_cau.bo_qua)
    return f"Liều này ({ten}) không kiểm tra bằng ảnh được — {ly_do}. Bác bấm nút xác nhận giúp cháu nhé."


def _thong_bao(ket_qua: KetQua, yeu_cau: YeuCauDem, thieu: Mapping[str, int], thua: Mapping[str, int]) -> str:
    if ket_qua is KetQua.KHOP:
        cau = f"Cháu đếm được đúng {_mo_ta(yeu_cau.so_luong)} như trong đơn thuốc ạ."
    else:
        chi_tiet = []
        if thieu:
            chi_tiet.append(f"còn thiếu {_mo_ta(thieu)}")
        if thua:
            chi_tiet.append(f"thừa {_mo_ta(thua)}")
        cau = (
            f"Đơn thuốc của bác cần {_mo_ta(yeu_cau.so_luong)}, "
            f"nhưng trong ảnh {' và '.join(chi_tiet)}. Bác xem lại giúp cháu nhé."
        )

    if yeu_cau.bo_qua:
        ten = ", ".join(thuoc.ten_thuoc for thuoc in yeu_cau.bo_qua)
        cau += f" (Cháu chưa kiểm tra được {ten} qua ảnh.)"
    return cau


__all__ = [
    "KetQua",
    "KetQuaDoiChieu",
    "ThuocBoQua",
    "YeuCauDem",
    "doi_chieu",
    "doi_chieu_don_thuoc",
    "tinh_yeu_cau",
]
