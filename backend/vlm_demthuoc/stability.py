"""
Phát hiện khung hình đứng yên để quyết định lúc nào chụp.

Tách khỏi `camera_counter.py` vì đây là logic tất định thuần tuý — không đụng
tới camera, không gọi API, không vẽ gì lên màn hình. Nhờ vậy nó kiểm thử được
bằng mảng numpy dựng sẵn mà không cần webcam (xem
`tests/vlm_demthuoc/test_stability.py`).
"""

from __future__ import annotations

import cv2
import numpy as np


class StabilityWatcher:
    """Theo dõi chuyển động giữa 2 khung hình liên tiếp.

    Quy tắc kích hoạt:
      - Chênh lệch pixel trung bình < `threshold`  -> coi là đứng yên.
      - Đứng yên liên tục đủ `stable_seconds` giây -> báo sẵn sàng chụp.
      - Sau khi đã chụp, phải có chuyển động trở lại (cảnh thay đổi) thì mới
        cho phép chụp lần tiếp theo. Nhờ vậy để thuốc yên một chỗ sẽ không bị
        đếm đi đếm lại.
    """

    def __init__(
        self,
        threshold: float = 2.0,
        stable_seconds: float = 3.0,
        work_width: int = 320,
    ) -> None:
        self.threshold = threshold
        self.stable_seconds = stable_seconds
        self.work_width = work_width
        self._prev: np.ndarray | None = None
        self._stable_since: float | None = None
        self._armed = True
        self.score = 0.0

    def _prepare(self, frame: np.ndarray) -> np.ndarray:
        height, width = frame.shape[:2]
        if width > self.work_width:
            scale = self.work_width / float(width)
            frame = cv2.resize(
                frame,
                (self.work_width, max(1, int(height * scale))),
                interpolation=cv2.INTER_AREA,
            )
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # Làm mờ nhẹ để nhiễu cảm biến không bị tính là chuyển động.
        return cv2.GaussianBlur(gray, (5, 5), 0)

    def update(self, frame: np.ndarray, now: float) -> None:
        current = self._prepare(frame)
        if self._prev is None:
            self._prev = current
            self._stable_since = now
            return

        self.score = float(cv2.absdiff(current, self._prev).mean())
        self._prev = current

        if self.score > self.threshold:  # đang chuyển động
            self._stable_since = None
            self._armed = True  # cảnh đã đổi -> cho phép đếm lần nữa
        elif self._stable_since is None:  # vừa dừng lại
            self._stable_since = now

    @property
    def moving(self) -> bool:
        return self._stable_since is None

    @property
    def armed(self) -> bool:
        return self._armed

    def stable_for(self, now: float) -> float:
        return 0.0 if self._stable_since is None else now - self._stable_since

    def ready(self, now: float) -> bool:
        return self._armed and self.stable_for(now) >= self.stable_seconds

    def consume(self) -> None:
        """Đánh dấu đã chụp cho cảnh hiện tại."""
        self._armed = False

    def rearm(self, now: float) -> None:
        """Cho phép chụp lại ngay mà không cần chờ cảnh thay đổi.

        Dùng khi người dùng bấm SPACE: lúc đó chính cú bấm là tín hiệu "tôi sẵn
        sàng cho lần đếm sau", nên không bắt phải xê dịch thuốc nữa. Mốc đứng
        yên cũng đặt lại về hiện tại để vẫn phải chờ đủ `stable_seconds` giây.
        """
        self._armed = True
        self._stable_since = now
