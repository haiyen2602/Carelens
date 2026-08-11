"""Cho phép import các module của `src/vlm_demthuoc/` trong test.

Thư mục đó là một chương trình CLI chạy độc lập (`run.bat` làm `cd` vào đúng
thư mục rồi mới gọi python), nên các file trong đó import phẳng — `from config
import Settings` chứ không phải `from src.vlm_demthuoc.config import Settings`.
Muốn test được mà không phải sửa import của chương trình, thêm thẳng thư mục đó
vào `sys.path` — cùng cách `tests/test_egress_allowlist.py` đã làm với thư mục
gốc của repo.
"""

import sys
from pathlib import Path

VLM_DIR = Path(__file__).resolve().parents[2] / "src" / "vlm_demthuoc"
if str(VLM_DIR) not in sys.path:
    sys.path.insert(0, str(VLM_DIR))
