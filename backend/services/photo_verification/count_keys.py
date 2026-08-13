"""
Sáu hình dạng mà mô hình thị giác đếm được — bản dùng ở tầng backend.

TRÙNG LẶP CÓ CHỦ ĐÍCH với `backend/vlm_demthuoc/prompts.py`. Bình thường hai
bản của cùng một danh sách là mùi code xấu, nhưng ở đây nó bắt buộc:

`.railwayignore` loại `backend/vlm_demthuoc/` khỏi gói upload lên Railway, và
ghi rõ thư mục đó "khong duoc backend/main.py hay bat ky module nao trong
backend/api|agents|services import". Lý do: nó là công cụ chạy độc lập bằng
`run.bat`, có `requirements.txt` riêng (opencv, numpy) mà backend không cài.

Import thẳng sang đó thì dưới máy vẫn chạy, nhưng lên production sẽ chết ngay
lúc khởi động vì thư mục ấy không tồn tại trên server — kiểu lỗi chỉ lộ ra sau
khi deploy, đúng lúc không ai muốn gặp.

Đổi lại, `tests/services/photo_verification/test_count_keys_dong_bo.py` so hai
bản với nhau. Test chạy trên CI, nơi có đủ cả repo, nên thêm/sửa một dạng thuốc
ở một bên mà quên bên kia là build đỏ ngay — chứ không âm thầm lệch nhau.

Nguồn sự thật về NỘI DUNG vẫn là `prompts.py`: nó là thứ đi vào prompt gửi cho
mô hình. File này chỉ soi lại đúng danh sách đó.
"""

from __future__ import annotations

# Thứ tự khớp `prompts.COUNT_KEYS` — có test kiểm chứng.
COUNT_KEYS: tuple[str, ...] = (
    "vien_nang",
    "vien_nen",
    "tuyp_thuoc",
    "lo_thuoc",
    "hop_thuoc",
    "goi_thuoc",
)

# Nhãn có dấu, dùng để dựng câu nói với bệnh nhân.
COUNT_LABELS_VI: dict[str, str] = {
    "vien_nang": "Viên nang",
    "vien_nen": "Viên nén",
    "tuyp_thuoc": "Tuýp thuốc",
    "lo_thuoc": "Lọ thuốc",
    "hop_thuoc": "Hộp thuốc",
    "goi_thuoc": "Gói thuốc",
}

# Trường đếm phụ — kẹo/thực phẩm bị nhận nhầm thành thuốc, KHÔNG cộng vào
# COUNT_KEYS. Khớp `prompts.NON_DRUG_KEY`.
NON_DRUG_KEY = "khong_phai_thuoc"

# Mức tin cậy model tự chấm cho một lần đếm. Khớp `prompts.CONFIDENCE_LEVELS`.
CONFIDENCE_LEVELS: tuple[str, ...] = ("cao", "trung_binh", "thap")

__all__ = ["CONFIDENCE_LEVELS", "COUNT_KEYS", "COUNT_LABELS_VI", "NON_DRUG_KEY"]
