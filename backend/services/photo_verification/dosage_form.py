"""
Quy đổi dạng bào chế của thuốc sang đơn vị mà mô hình thị giác đếm được.

Bài toán: đơn thuốc ghi "1 viên", "1 gói bột", "5ml siro" — còn mô hình chỉ
biết đếm SÁU HÌNH DẠNG (`prompts.COUNT_KEYS`). Module này là cầu nối giữa hai
cách nói đó, và là nơi DUY NHẤT trong hệ thống biết dạng thuốc nào đếm được,
dạng nào chỉ xác minh được là "có mặt", dạng nào không xác minh được bằng ảnh.

Ba chế độ đối chiếu, và vì sao bắt buộc phải tách ra:

  EXACT     Viên nén, viên nang, gói bột. Đếm được từng cái nên so bằng số:
            đơn 3 viên thì ảnh phải có đúng 3 viên.

  PRESENCE  Lọ, tuýp. Đếm được VẬT CHỨA nhưng KHÔNG suy ra được liều — một lọ
            siro trong ảnh không nói lên bệnh nhân sẽ rót 5ml hay 15ml. Gộp nó
            chung với viên nén là nói quá về độ tin cậy của bằng chứng, trái
            BR-4.1 (các mức bằng chứng khác nhau không được gộp làm một).

  SKIP      Thuốc tiêm/truyền. Ảnh thuốc bày ra trên bàn không chứng minh được
            gì về việc đã tiêm hay chưa. Những liều này chỉ xác nhận bằng nút
            bấm (ADR-0011 quy tắc 2).

Dạng thuốc chưa biết thì KHÔNG đoán bừa — trả `SKIP` kèm cảnh báo. Đoán sai ở
đây nghĩa là báo bệnh nhân đã uống đủ thuốc trong khi thực tế không phải, nên
thà từ chối xác minh còn hơn xác minh nhầm (ADR-0004 §4: không nuốt lỗi im lặng).

Dữ liệu thật (`data pharmacy/`, 3688 thuốc) có hơn 100 biến thể `dang_thuoc`
viết tự do — "Viên nén bao phim tan trong ruột", "Bột pha hỗn dịch uống"... nên
so khớp theo TỪ KHOÁ chứ không theo danh sách giá trị cố định.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from backend.vlm_demthuoc.prompts import COUNT_KEYS

logger = logging.getLogger(__name__)


class MatchMode(StrEnum):
    """Cách đối chiếu số lượng đếm được với số lượng trong đơn thuốc."""

    EXACT = "exact"
    PRESENCE = "presence"
    SKIP = "skip"


@dataclass(frozen=True)
class DosageForm:
    """Kết quả phân loại một dạng bào chế.

    `count_key` là khoá trong `prompts.COUNT_KEYS` — luôn là `None` khi
    `mode` là `SKIP`, và luôn khác `None` trong hai chế độ còn lại.

    `ly_do` dùng để giải thích cho bệnh nhân/bác sĩ vì sao liều này không xác
    minh được, nên viết bằng tiếng Việt đời thường chứ không phải thuật ngữ.
    """

    count_key: str | None
    mode: MatchMode
    ly_do: str
    # False = không luật nào khớp, tức hệ thống CHƯA BIẾT dạng này. Khác hẳn
    # thuốc tiêm — cũng SKIP nhưng là quyết định có chủ đích. Hai trường hợp
    # cần nói với người dùng bằng hai câu khác nhau, và chỉ một trong hai là
    # dấu hiệu cần bổ sung luật.
    co_luat: bool = True

    @property
    def xac_minh_duoc_bang_anh(self) -> bool:
        return self.mode is not MatchMode.SKIP


@dataclass(frozen=True)
class _Luat:
    mau: re.Pattern[str]
    count_key: str | None
    mode: MatchMode
    ly_do: str


def _mau(*tu_khoa: str) -> re.Pattern[str]:
    """Ghép các từ khoá (đã bỏ dấu) thành một mẫu khớp theo RANH GIỚI TỪ.

    Không dùng `in` để so chuỗi con: từ khoá "mo" (thuốc mỡ) sẽ khớp nhầm mọi
    chữ có chứa hai ký tự đó, và "goi" (gói) cũng vậy. Ranh giới từ khiến
    "thuoc mo" khớp còn "mot lan" thì không.
    """
    return re.compile(r"\b(?:" + "|".join(tu_khoa) + r")\b")


# THỨ TỰ CÁC LUẬT LÀ MỘT PHẦN CỦA LOGIC, không phải sắp cho đẹp.
#
#   - Luật tiêm/truyền phải đứng ĐẦU: "Bột pha tiêm" chứa cả "bot pha" lẫn
#     "tiem". Để luật gói đứng trước thì thuốc tiêm bị xếp thành gói bột uống,
#     và hệ thống sẽ bắt bệnh nhân chụp ảnh một thứ không thể chụp.
#   - Luật viên nang phải đứng trước luật viên: "Viên nang cứng" chứa "vien".
#   - Luật gói/bột phải đứng trước luật dung dịch: "Bột pha hỗn dịch uống" và
#     "Cốm pha hỗn dịch uống" chứa "hon dich" — thứ đếm được ở đây là GÓI BỘT
#     người bệnh xé ra, không phải lọ dung dịch.
#
# Không có luật nào trả `hop_thuoc`: bác sĩ kê theo viên/gói/lọ chứ không kê
# "1 hộp". Khoá đó tồn tại trong COUNT_KEYS để mô hình có chỗ xếp cái hộp nó
# nhìn thấy trong ảnh, chứ không phải để đối chiếu với đơn thuốc.
_LUAT: tuple[_Luat, ...] = (
    _Luat(
        _mau("tiem", "truyen"),
        None,
        MatchMode.SKIP,
        "thuốc tiêm/truyền — ảnh thuốc bày ra không xác minh được, dùng nút xác nhận",
    ),
    _Luat(
        _mau("nang"),
        "vien_nang",
        MatchMode.EXACT,
        "viên nang đếm được từng viên",
    ),
    _Luat(
        # "hoàn" = viên hoàn của thuốc y học cổ truyền ("Hoàn cứng", "Hoàn mềm").
        # Vẫn là viên tròn cầm được nên đếm được như viên nén.
        _mau("vien", "hoan"),
        "vien_nen",
        MatchMode.EXACT,
        "viên thuốc đếm được từng viên",
    ),
    _Luat(
        _mau("bot", "com", "goi"),
        "goi_thuoc",
        MatchMode.EXACT,
        "gói thuốc đếm được từng gói",
    ),
    _Luat(
        _mau("kem", "mo", "gel", "nhu tuong", "thuoc mo"),
        "tuyp_thuoc",
        MatchMode.PRESENCE,
        "thuốc bôi — ảnh chỉ xác minh được là đã lấy đúng tuýp, không xác minh được lượng bôi",
    ),
    _Luat(
        _mau("siro", "dung dich", "hon dich", "nho", "xit", "lotion", "cao long", "dang dau"),
        "lo_thuoc",
        MatchMode.PRESENCE,
        "thuốc nước — ảnh chỉ xác minh được là đã lấy đúng lọ, không xác minh được lượng uống",
    ),
)

_KHONG_RO = DosageForm(
    count_key=None,
    mode=MatchMode.SKIP,
    ly_do="chưa biết dạng bào chế của thuốc này nên không đối chiếu ảnh được",
    co_luat=False,
)


def _bo_dau(text: str) -> str:
    """Bỏ dấu tiếng Việt, viết thường, gộp khoảng trắng.

    So khớp trên chuỗi đã bỏ dấu để một luật phủ được mọi cách gõ: "Viên nén",
    "viên nén", "VIEN NEN" đều về cùng một dạng. `đ` không bị tách bởi NFD nên
    phải thay tay trước.
    """
    text = text.replace("đ", "d").replace("Đ", "D")
    khong_dau = "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))
    return " ".join(khong_dau.lower().split())


def classify(dang_thuoc: str, duong_dung: str = "") -> DosageForm:
    """Phân loại một dạng bào chế thành (khoá đếm, chế độ đối chiếu).

    `duong_dung` được ghép vào cùng chuỗi so khớp chứ không xét riêng: nó là
    nguồn thứ hai để bắt thuốc tiêm khi `dang_thuoc` không nói rõ (vd
    `dang_thuoc="Bột pha"` + `duong_dung="Tiêm"`). Ghép vào chỉ khiến kết quả
    nghiêng về phía an toàn hơn — SKIP — chứ không bao giờ biến một liều không
    xác minh được thành xác minh được.
    """
    van_ban = _bo_dau(f"{dang_thuoc} {duong_dung}")
    if not van_ban:
        return _KHONG_RO

    for luat in _LUAT:
        if luat.mau.search(van_ban):
            return DosageForm(luat.count_key, luat.mode, luat.ly_do)

    # Không khớp luật nào: nói ra để còn bổ sung luật, đừng để lọt im lặng.
    logger.warning(
        "Chưa có luật cho dạng bào chế %r (đường dùng %r) — bỏ qua xác minh bằng ảnh.",
        dang_thuoc,
        duong_dung,
    )
    return _KHONG_RO


def count_keys_hop_le() -> frozenset[str]:
    """Tập khoá đếm mà `classify` có thể trả về. Dùng cho test và cho bước cộng dồn."""
    return frozenset(luat.count_key for luat in _LUAT if luat.count_key is not None)


# Kiểm tra ngay lúc nạp module: mọi khoá trong bảng luật phải là khoá mà mô hình
# thực sự đếm được. Gõ nhầm một khoá (vd "vien_nem") sẽ khiến bước đối chiếu so
# số đếm với 0 vĩnh viễn — liều nào cũng "thiếu thuốc", không exception nào nổ
# ra, và phải lần ngược từ báo cáo sai mới tìm được. Chặn ở đây thì hỏng ngay
# lúc khởi động, ồn ào và đúng chỗ.
_KHOA_LA = count_keys_hop_le() - set(COUNT_KEYS)
if _KHOA_LA:
    raise RuntimeError(
        f"Bảng luật dosage_form dùng khoá không có trong prompts.COUNT_KEYS: {sorted(_KHOA_LA)}"
    )

__all__ = ["DosageForm", "MatchMode", "classify", "count_keys_hop_le"]
