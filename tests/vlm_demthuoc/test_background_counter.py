"""Kiểm chứng luồng nền gọi API của vòng lặp camera.

Lý do có file này: bản trước dùng `ThreadPoolExecutor`, và bấm Ctrl+C giữa lúc
đang gọi API thì terminal treo tới khi máy chủ trả lời — `concurrent.futures`
đăng ký một `atexit` chờ mọi luồng của nó xong mới cho trình thông dịch thoát.
Sửa bằng cách tự chạy luồng daemon. Cờ `daemon` chính là thứ quyết định, nên nó
được khoá lại ở đây thay vì tin vào mắt người đọc code.

Không cần webcam, không gọi mạng: `PillCounter` được thay bằng vật giả đứng chờ
một `Event` — chính là mô phỏng cảnh máy chủ ngâm không trả lời.
"""

import threading

import numpy as np
import pytest
from camera_counter import BackgroundCounter

KHUNG = np.zeros((4, 4, 3), dtype=np.uint8)
CHO_TOI_DA = 5.0  # giây; test đúng thì chạm ngưỡng này là hỏng, không phải chậm


class CounterGiaCham:
    """Đứng im cho tới khi test cho phép đi tiếp — giả cảnh máy chủ ngâm."""

    def __init__(self) -> None:
        self.da_bat_dau = threading.Event()
        self.cho_phep_tra_ve = threading.Event()

    def count(self, frame):
        self.da_bat_dau.set()
        self.cho_phep_tra_ve.wait(timeout=CHO_TOI_DA)
        return "ket qua"


@pytest.fixture
def counter_cham():
    stub = CounterGiaCham()
    yield stub
    stub.cho_phep_tra_ve.set()  # đừng để luồng nào còn treo sau test


def test_luong_nen_phai_la_daemon(counter_cham):
    """Test này đỏ nghĩa là Ctrl+C sẽ treo terminal cho tới khi API trả lời."""
    BackgroundCounter(counter_cham).submit(KHUNG)
    assert counter_cham.da_bat_dau.wait(timeout=CHO_TOI_DA)

    dang_chay = [t for t in threading.enumerate() if t.name == "vlm-count"]
    assert dang_chay, "không tìm thấy luồng nền nào đang chạy"
    assert all(t.daemon for t in dang_chay)


def test_khong_chan_luong_chinh(counter_cham):
    """`submit` phải trả về ngay, chưa có kết quả — đó là lý do có luồng nền."""
    future = BackgroundCounter(counter_cham).submit(KHUNG)
    assert counter_cham.da_bat_dau.wait(timeout=CHO_TOI_DA)
    assert not future.done()


def test_tra_ve_dung_ket_qua_cua_counter(counter_cham):
    future = BackgroundCounter(counter_cham).submit(KHUNG)
    counter_cham.cho_phep_tra_ve.set()
    assert future.result(timeout=CHO_TOI_DA) == "ket qua"


def test_loi_bat_ngo_di_duoc_sang_luong_chinh():
    """`count()` hứa không ném exception. Nếu lời hứa vỡ, `pending` phải kết
    thúc kèm lỗi chứ không treo mãi — vòng lặp camera chờ `done()` để đi tiếp.
    """

    class CounterVo:
        def count(self, frame):
            raise RuntimeError("hong that")

    future = BackgroundCounter(CounterVo()).submit(KHUNG)
    with pytest.raises(RuntimeError, match="hong that"):
        future.result(timeout=CHO_TOI_DA)


def test_moi_lan_submit_la_mot_future_rieng(counter_cham):
    runner = BackgroundCounter(counter_cham)
    assert runner.submit(KHUNG) is not runner.submit(KHUNG)
