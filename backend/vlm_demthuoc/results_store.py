"""
Ghi kết quả đếm ra ngoài: in terminal, lưu ảnh, ghi file JSON/JSONL.

Tách khỏi `camera_counter.py` vì đổi định dạng lưu trữ không nên phải đụng vào
vòng lặp camera. Toàn bộ module này không phụ thuộc webcam nên kiểm thử được
bằng `tmp_path` của pytest (xem `tests/vlm_demthuoc/test_results_store.py`).

Quy ước in/log ở đây:
  - `print()` = nội dung dành cho NGƯỜI DÙNG đang ngồi trước màn hình (kết quả
    đếm). Đây là giao diện của chương trình, không phải log.
  - `logger` = dấu vết dành cho NGƯỜI SỬA LỖI (ghi file hỏng, ảnh không lưu
    được). Trước đây những dòng này dùng `print(file=sys.stderr)`.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import cv2
import numpy as np
from prompts import COUNT_KEYS, COUNT_LABELS_VI
from vlm_client import CountResult

logger = logging.getLogger(__name__)

# Chữ hiển thị cho từng mức tin cậy khi in ra terminal (có dấu).
CONFIDENCE_TEXT = {
    "cao": "cao",
    "trung_binh": "trung bình",
    "thap": "thấp",
}

# Bề rộng cột nhãn khi in bảng kết quả, đủ chứa nhãn dài nhất trong COUNT_KEYS.
_LABEL_WIDTH = max(len(COUNT_LABELS_VI[key]) for key in COUNT_KEYS) + 1


# ---------------------------------------------------------------------------
# In kết quả ra terminal
# ---------------------------------------------------------------------------
def print_result(result: CountResult, index: int, image_path: Path | None = None) -> None:
    """In một lần đếm ra terminal.

    Các dòng số lượng sinh ra TỪ `COUNT_KEYS` chứ không viết cứng từng loại —
    thêm một loại thuốc mới vào `prompts.COUNT_KEYS` là terminal tự có thêm
    dòng, giống cách `overlay.draw_overlay` vẫn làm.
    """
    stamp = time.strftime("%H:%M:%S", time.localtime(result.timestamp))
    anh = f"  Ảnh        : {image_path.name}" if image_path else ""
    print()
    print("=" * 52)
    if not result.ok:
        print(f"[{stamp}] Lần đếm #{index} — LỖI: {result.error}")
        if anh:
            print(anh)
        print("=" * 52, flush=True)
        return

    print(f"[{stamp}] Lần đếm #{index}  ({result.latency_sec:.1f}s)")
    for key in COUNT_KEYS:
        print(f"  {COUNT_LABELS_VI[key]:<{_LABEL_WIDTH}}: {result.counts[key]}")
    print("  ---------------------------------")
    print(f"  Tổng số viên (nang + nén): {result.total_pills}")
    if result.khong_phai_thuoc:
        print(f"  Đã loại ra : {result.khong_phai_thuoc} viên kẹo / không phải thuốc")
    print(f"  Độ tin cậy : {CONFIDENCE_TEXT.get(result.do_tin_cay, result.do_tin_cay)}")
    if result.ghi_chu:
        print(f"  Ghi chú    : {result.ghi_chu}")
    if anh:
        print(anh)
    print("=" * 52, flush=True)


# ---------------------------------------------------------------------------
# Lưu ảnh
# ---------------------------------------------------------------------------
def save_frame(frame: np.ndarray, folder: Path, prefix: str = "capture") -> Path | None:
    """Ghi khung hình ra `folder` với tên theo mốc thời gian.

    Dùng imencode + tofile thay cho cv2.imwrite vì cv2.imwrite không ghi được
    khi đường dẫn có ký tự tiếng Việt (thư mục dự án này nằm trong "Máy tính").
    Trả về đường dẫn đã ghi, hoặc None nếu ghi hỏng.
    """
    stamp = time.strftime("%Y%m%d_%H%M%S")
    millis = int((time.time() % 1) * 1000)
    path = folder / f"{prefix}_{stamp}_{millis:03d}.jpg"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        if not ok:
            raise ValueError("imencode thất bại")
        buffer.tofile(str(path))
    except Exception as exc:  # noqa: BLE001 - lưu ảnh hỏng không được làm chết vòng lặp
        logger.warning("Không lưu được ảnh %s: %s", path.name, exc)
        return None
    return path


# ---------------------------------------------------------------------------
# File kết quả
# ---------------------------------------------------------------------------
def append_log(path: Path, result: CountResult) -> None:
    record = result.to_dict() if result.ok else {
        "loi": result.error,
        "thoi_gian": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(result.timestamp)),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_results_json(path: Path) -> list[dict]:
    """Đọc kết quả của những lần chạy trước để ghi tiếp vào đó.

    File hỏng hoặc sai định dạng sẽ được đổi tên sang một bên chứ không bị ghi
    đè — mất dữ liệu cũ vì một lỗi đọc là điều không chấp nhận được.
    """
    if not path.is_file():
        return []

    ly_do = ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        data, ly_do = None, str(exc)
    else:
        if not isinstance(data, list):
            data, ly_do = None, "nội dung không phải mảng JSON"

    if data is None:
        backup = path.with_name(
            f"{path.stem}_hong_{time.strftime('%Y%m%d_%H%M%S')}{path.suffix}"
        )
        logger.warning(
            "Không đọc được %s (%s). Giữ lại thành %s và bắt đầu file mới.",
            path.name, ly_do, backup.name,
        )
        try:
            path.replace(backup)
        except OSError as exc:
            logger.warning("Không đổi tên được %s sang %s: %s", path.name, backup.name, exc)
        return []

    return [r for r in data if isinstance(r, dict)]


def build_record(
    result: CountResult, index: int, image_path: Path | None, phien: str = ""
) -> dict:
    """Một phần tử trong file kết quả JSON."""
    common = {
        "lan": index,
        "phien": phien,
        "anh": image_path.name if image_path else "",
        "thoi_gian": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(result.timestamp)),
    }
    if not result.ok:
        return {**common, "thanh_cong": False, "loi": result.error}
    detail = result.to_dict()
    detail.pop("thoi_gian", None)  # đã có trong common
    return {**common, "thanh_cong": True, **detail}


def save_results_json(path: Path, records: list[dict]) -> None:
    """Ghi đè toàn bộ danh sách kết quả ra file JSON.

    Ghi ra file tạm rồi mới đổi tên: tắt chương trình giữa chừng cũng không để
    lại file JSON dở dang.
    """
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(path)
    except OSError as exc:
        logger.error("Không ghi được %s: %s", path, exc)


def next_run_index(records: list[dict]) -> int:
    """Số thứ tự lần đếm kế tiếp, nối tiếp file cũ để không trùng số.

    Tách thành hàm riêng (trước đây là một biểu thức `max(...)` nằm giữa phần
    khởi tạo vòng lặp) để kiểm thử được trường hợp file cũ có bản ghi thiếu
    trường `lan` hoặc `lan` không phải số nguyên.
    """
    return max(
        (r["lan"] for r in records if isinstance(r.get("lan"), int)), default=0
    )
