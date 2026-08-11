"""Kiểm chứng bộ phát hiện khung hình đứng yên.

`StabilityWatcher` nhận `now` làm tham số chứ không tự gọi `time.monotonic()`,
nên toàn bộ test ở đây điều khiển được thời gian mà không cần `sleep` — chạy
trong vài mili giây và không phụ thuộc tốc độ máy.

Không cần webcam: khung hình là mảng numpy dựng sẵn.
"""

import numpy as np
import pytest
from stability import StabilityWatcher

HEIGHT, WIDTH = 240, 320


def khung(gia_tri: int) -> np.ndarray:
    """Khung hình BGR đơn sắc. Hai khung khác `gia_tri` = có chuyển động."""
    return np.full((HEIGHT, WIDTH, 3), gia_tri, dtype=np.uint8)


def nhieu(seed: int = 0) -> np.ndarray:
    """Khung hình ngẫu nhiên — chênh lệch lớn, chắc chắn vượt mọi ngưỡng."""
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=(HEIGHT, WIDTH, 3), dtype=np.uint8)


@pytest.fixture
def watcher() -> StabilityWatcher:
    return StabilityWatcher(threshold=2.0, stable_seconds=3.0)


# ---------------------------------------------------------------------------
# Trạng thái ban đầu
# ---------------------------------------------------------------------------
def test_khung_dau_tien_chua_du_dieu_kien_chup(watcher):
    """Khung đầu tiên không có gì để so sánh — không được chụp ngay."""
    watcher.update(khung(100), now=0.0)
    assert not watcher.ready(0.0)


def test_moi_tao_ra_thi_dang_o_trang_thai_cho_phep_chup(watcher):
    assert watcher.armed


# ---------------------------------------------------------------------------
# Đứng yên đủ lâu thì cho chụp
# ---------------------------------------------------------------------------
def test_dung_yen_du_lau_thi_san_sang_chup(watcher):
    watcher.update(khung(100), now=0.0)
    watcher.update(khung(100), now=1.0)

    assert not watcher.ready(2.9), "chưa đủ 3 giây thì chưa được chụp"
    assert watcher.ready(3.0), "đủ 3 giây thì phải sẵn sàng"


def test_dung_yen_thi_khong_bao_cao_la_dang_chuyen_dong(watcher):
    watcher.update(khung(100), now=0.0)
    watcher.update(khung(100), now=0.5)

    assert not watcher.moving
    assert watcher.stable_for(2.0) == pytest.approx(2.0)


def test_chenh_lech_nho_hon_nguong_van_coi_la_dung_yen():
    """Nhiễu cảm biến webcam thường ở mức 0.5–1.5; ngưỡng mặc định 2.0 phải bỏ
    qua được mức đó, nếu không sẽ không bao giờ chịu chụp."""
    watcher = StabilityWatcher(threshold=2.0, stable_seconds=1.0)
    watcher.update(khung(100), now=0.0)
    watcher.update(khung(101), now=0.5)  # lệch 1 mức xám

    assert not watcher.moving
    assert watcher.ready(1.5)


# ---------------------------------------------------------------------------
# Có chuyển động thì đặt lại đồng hồ
# ---------------------------------------------------------------------------
def test_chuyen_dong_lam_dong_ho_dung_yen_chay_lai_tu_dau(watcher):
    watcher.update(khung(0), now=0.0)
    watcher.update(khung(0), now=2.9)  # sắp đủ 3 giây
    watcher.update(nhieu(), now=3.0)   # tay che ống kính

    assert watcher.moving
    assert not watcher.ready(3.0)
    assert watcher.stable_for(3.0) == 0.0

    watcher.update(nhieu(), now=3.1)
    watcher.update(nhieu(), now=3.2)   # đứng yên trở lại từ mốc 3.2
    assert not watcher.ready(5.0), "phải đếm lại đủ 3 giây kể từ lúc dừng"
    assert watcher.ready(6.2)


def test_score_phan_anh_do_lech_giua_hai_khung(watcher):
    watcher.update(khung(0), now=0.0)
    watcher.update(khung(0), now=0.1)
    assert watcher.score == pytest.approx(0.0, abs=0.01)

    watcher.update(khung(255), now=0.2)
    assert watcher.score > 2.0


# ---------------------------------------------------------------------------
# consume / rearm — chống đếm đi đếm lại cùng một cảnh
# ---------------------------------------------------------------------------
def test_chup_xong_thi_khong_tu_chup_lai_canh_cu(watcher):
    """Để thuốc yên một chỗ không được biến thành đếm liên tục — đây là lý do
    `_armed` tồn tại."""
    watcher.update(khung(100), now=0.0)
    watcher.update(khung(100), now=0.1)
    assert watcher.ready(3.0)

    watcher.consume()
    assert not watcher.armed
    assert not watcher.ready(10.0), "cảnh chưa đổi thì không được chụp nữa"


def test_canh_thay_doi_thi_cho_phep_chup_tro_lai(watcher):
    watcher.update(khung(100), now=0.0)
    watcher.update(khung(100), now=0.1)
    watcher.consume()

    watcher.update(nhieu(), now=1.0)     # cảnh đổi -> tự bật lại
    assert watcher.armed

    watcher.update(nhieu(), now=1.1)
    watcher.update(nhieu(), now=1.2)     # đứng yên lại từ 1.2
    assert watcher.ready(4.2)


def test_rearm_cho_chup_lai_ma_khong_can_xe_dich_thuoc(watcher):
    """Người dùng bấm SPACE = tín hiệu 'tôi sẵn sàng cho lần sau', nên không
    bắt họ phải nhấc thuốc lên đặt xuống."""
    watcher.update(khung(100), now=0.0)
    watcher.update(khung(100), now=0.1)
    watcher.consume()
    assert not watcher.ready(5.0)

    watcher.rearm(now=5.0)
    assert watcher.armed
    assert not watcher.ready(7.9), "rearm vẫn phải chờ đủ stable_seconds"
    assert watcher.ready(8.0)


# ---------------------------------------------------------------------------
# Tham số cấu hình
# ---------------------------------------------------------------------------
def test_stable_seconds_bang_0_thi_chup_ngay_khi_vua_dung_yen():
    watcher = StabilityWatcher(threshold=2.0, stable_seconds=0.0)
    watcher.update(khung(50), now=0.0)
    watcher.update(khung(50), now=0.1)

    assert watcher.ready(0.1)


def test_nguong_cao_hon_thi_bo_qua_duoc_chuyen_dong_manh_hon():
    """`--motion-threshold` tồn tại để tăng lên khi camera nhiễu."""
    nhay = StabilityWatcher(threshold=0.5, stable_seconds=1.0)
    lo_di = StabilityWatcher(threshold=200.0, stable_seconds=1.0)

    for w in (nhay, lo_di):
        w.update(khung(0), now=0.0)
        w.update(khung(60), now=0.5)

    assert nhay.moving, "ngưỡng thấp phải coi đây là chuyển động"
    assert not lo_di.moving, "ngưỡng cao phải bỏ qua"


def test_khung_hinh_lon_duoc_thu_nho_truoc_khi_so_sanh():
    """`work_width` giữ chi phí so sánh không đổi dù camera 4K."""
    watcher = StabilityWatcher(work_width=64)
    to = np.full((1080, 1920, 3), 128, dtype=np.uint8)

    watcher.update(to, now=0.0)
    watcher.update(to, now=0.1)

    assert not watcher.moving
    assert watcher.score == pytest.approx(0.0, abs=0.01)
