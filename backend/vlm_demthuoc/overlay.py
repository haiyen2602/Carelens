"""
Vẽ thông tin lên cửa sổ camera.

Tách khỏi `camera_counter.py` để thay đổi cách hiển thị không phải đụng vào
vòng lặp điều khiển. Đây là nơi DUY NHẤT biết về `cv2.putText`/`cv2.rectangle`.

Mọi chữ vẽ ra đây đều KHÔNG DẤU: `cv2.putText` chỉ render được ASCII, tiếng
Việt có dấu sẽ ra ô vuông. Nhãn không dấu lấy từ `prompts.COUNT_LABELS_ASCII`.
"""

from __future__ import annotations

import cv2
from config import Settings
from prompts import COUNT_KEYS, COUNT_LABELS_ASCII, NON_DRUG_KEY
from stability import StabilityWatcher
from vlm_client import CountResult

# Màu theo mức độ tin cậy, hệ BGR của OpenCV.
CONFIDENCE_COLOR = {
    "cao": (80, 200, 80),
    "trung_binh": (60, 190, 230),
    "thap": (80, 80, 235),
}

_LINE_HEIGHT = 26  # chiều cao một dòng chữ trong panel


def status_text(
    watcher: StabilityWatcher | None,
    settings: Settings,
    busy: bool,
    now: float,
    frames_left: int,
    frozen: bool = False,
    seconds_left: float = 0.0,
) -> tuple[str, tuple[int, int, int]]:
    """Dòng trạng thái ở đáy cửa sổ (ASCII, vì cv2 không vẽ được dấu)."""
    if busy:
        return "DANG DEM...", (0, 200, 255)
    if frozen:
        return "DA DUNG - nhan SPACE de chup tiep", (0, 215, 255)
    if settings.trigger_mode == "timer":
        return f"Chup sau {max(0.0, seconds_left):.1f}s", (80, 220, 80)
    if watcher is None:
        return f"Dem sau {frames_left} khung", (180, 180, 180)
    if watcher.moving:
        return f"Dang chuyen dong (do lech {watcher.score:.1f})", (200, 200, 200)
    if not watcher.armed:
        return "Da dem xong - doi canh thay doi", (150, 150, 150)
    held = watcher.stable_for(now)
    return f"On dinh {held:.1f}/{settings.stable_seconds:g}s", (80, 220, 80)


def draw_overlay(
    frame,
    result: CountResult | None,
    status: tuple[str, tuple[int, int, int]],
    frozen: bool = False,
):
    font = cv2.FONT_HERSHEY_SIMPLEX
    # Panel cao vừa đủ số dòng thực sự vẽ: mỗi loại 1 dòng, cộng dòng tổng, dòng
    # độ tin cậy, và dòng "đã loại ra" chỉ xuất hiện khi có kẹo bị loại.
    show_non_drug = result is not None and result.ok and result.khong_phai_thuoc > 0
    panel_h = _LINE_HEIGHT * (len(COUNT_KEYS) + 2 + int(show_non_drug)) + 14
    # Vẽ lên bản sao: khung hình gốc còn được StabilityWatcher so sánh ở vòng
    # lặp sau, vẽ đè lên nó sẽ bị tính là chuyển động.
    frame = frame.copy()
    if frozen:  # viền vàng cho biết khung hình đang bị đóng băng
        cv2.rectangle(frame, (0, 0), (frame.shape[1] - 1, frame.shape[0] - 1),
                      (0, 215, 255), 6)
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (300, panel_h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

    y = _LINE_HEIGHT
    if result is None:
        cv2.putText(frame, "Chua co ket qua", (12, y),
                    font, 0.5, (230, 230, 230), 1, cv2.LINE_AA)
    elif not result.ok:
        cv2.putText(frame, "LOI - xem terminal", (12, y),
                    font, 0.55, (80, 80, 235), 2, cv2.LINE_AA)
    else:
        for key in COUNT_KEYS:
            cv2.putText(frame, f"{COUNT_LABELS_ASCII[key]:<11}: {result.counts[key]}",
                        (12, y), font, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
            y += _LINE_HEIGHT
        cv2.putText(frame, f"Tong vien : {result.total_pills}", (12, y),
                    font, 0.6, (0, 255, 255), 2, cv2.LINE_AA)
        y += _LINE_HEIGHT
        if show_non_drug:
            cv2.putText(
                frame,
                f"{COUNT_LABELS_ASCII[NON_DRUG_KEY]}: {result.khong_phai_thuoc} (loai ra)",
                (12, y), font, 0.5, (150, 150, 245), 1, cv2.LINE_AA,
            )
            y += _LINE_HEIGHT
        color = CONFIDENCE_COLOR.get(result.do_tin_cay, (200, 200, 200))
        cv2.putText(frame, f"Do tin cay: {result.do_tin_cay}", (12, y),
                    font, 0.55, color, 1, cv2.LINE_AA)

    text, color = status
    cv2.putText(frame, text, (12, frame.shape[0] - 14),
                font, 0.55, color, 2, cv2.LINE_AA)
    return frame
