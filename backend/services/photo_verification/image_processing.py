"""Nén/resize ảnh xác nhận liều thuốc trước khi lưu đĩa và gửi VLM.

Hàm thuần, không phụ thuộc DB/HTTP — gọi 1 lần ở `photo_routes.py::submit_photo`
trước khi ghi file. `verifier.py::_hoan_tat_xac_minh` đọc lại đúng file đã ghi
để gửi VLM, nên nén 1 lần ở đây là đủ cho cả lưu trữ lẫn cuộc gọi VLM — không
cần sửa `vlm_bridge.py`.

Dùng Pillow, KHÔNG dùng cv2/numpy — giữ đúng tinh thần "backend nhẹ" đã nêu
trong `vlm_bridge.py` (thư mục `vlm_demthuoc/` mới cần cv2 vì đọc khung hình
webcam trực tiếp).
"""

from __future__ import annotations

import io

from PIL import Image, ImageOps, UnidentifiedImageError


class AnhKhongHopLeError(ValueError):
    """Ảnh gửi lên không đọc/giải mã được — báo lỗi ngay lúc submit (400)
    thay vì để trôi tới tận lúc gọi VLM mới phát hiện."""


def nen_anh(anh: bytes, max_edge: int, jpeg_quality: int) -> bytes:
    """Resize (nếu cạnh dài nhất > max_edge) + nén lại JPEG theo jpeg_quality.

    Ảnh nhỏ hơn max_edge chỉ bị nén lại, không phóng to. `exif_transpose` áp
    trước tiên vì ảnh chụp từ điện thoại thường lưu xoay theo cờ EXIF thay vì
    xoay pixel thật — bỏ qua bước này ảnh sẽ hiện sai chiều sau khi resize.
    """
    try:
        with Image.open(io.BytesIO(anh)) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            width, height = img.size
            longest = max(width, height)
            if longest > max_edge:
                scale = max_edge / float(longest)
                new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
                img = img.resize(new_size, Image.Resampling.LANCZOS)

            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=jpeg_quality)
            return buf.getvalue()
    except UnidentifiedImageError as exc:
        raise AnhKhongHopLeError("Không đọc được ảnh gửi lên — file có thể bị hỏng.") from exc
    except OSError as exc:
        raise AnhKhongHopLeError(f"Lỗi xử lý ảnh: {exc}") from exc


__all__ = ["AnhKhongHopLeError", "nen_anh"]
