"""Khoá hai bản danh sách hình dạng thuốc không được lệch nhau.

`backend/services/` giữ một bản riêng thay vì import thẳng từ
`backend/vlm_demthuoc/prompts.py`, vì `.railwayignore` loại thư mục VLM khỏi
gói upload lên Railway và cấm các module trong `backend/api|agents|services`
import sang đó. Import thẳng thì dưới máy vẫn chạy, nhưng production chết lúc
khởi động — kiểu lỗi chỉ lộ ra sau khi deploy.

Cái giá của việc tách bản là hai danh sách có thể trôi xa nhau. File test này
là chỗ trả giá đó: thêm một dạng thuốc vào `prompts.COUNT_KEYS` mà quên bản
backend thì build đỏ ngay, thay vì mô hình đếm ra một dạng mà tầng đối chiếu
không biết là gì.

Test được phép import module VLM vì `tests/` chỉ chạy dưới máy và trên CI —
nơi có đủ cả repo — chứ không bao giờ được deploy.
"""

from backend.services.photo_verification import count_keys
from backend.vlm_demthuoc import prompts


def test_danh_sach_hinh_dang_giong_het_ca_thu_tu():
    """Thứ tự cũng phải khớp, không chỉ tập hợp.

    Bản của backend soi lại đúng `prompts.COUNT_KEYS` — nguồn sự thật về nội
    dung vẫn là bên VLM, vì đó là thứ đi vào prompt gửi cho mô hình.
    """
    assert count_keys.COUNT_KEYS == prompts.COUNT_KEYS


def test_moi_hinh_dang_deu_co_nhan_tieng_viet_giong_nhau():
    for khoa in prompts.COUNT_KEYS:
        assert count_keys.COUNT_LABELS_VI[khoa] == prompts.COUNT_LABELS_VI[khoa], (
            f"nhãn của {khoa!r} lệch giữa hai bản"
        )


def test_ban_backend_khong_thua_khoa_nao():
    """Thừa cũng nguy hiểm như thiếu: một khoá không tồn tại bên VLM sẽ không
    bao giờ được đếm, và mọi liều dùng nó sẽ mãi mãi báo thiếu thuốc.
    """
    assert set(count_keys.COUNT_LABELS_VI) == set(prompts.COUNT_KEYS)
