"""Khoá bản prompt/schema của backend không được lệch bản gốc — trừ MỘT chỗ
lệch có chủ đích.

Cùng lý do trùng lặp với count_keys.py: `.railwayignore` loại
`backend/vlm_demthuoc/` khỏi gói upload Railway, nên backend giữ bản riêng của
prompt + JSON schema thay vì import thẳng.

CHỈ so khớp `RESULT_SCHEMA` và `build_system_prompt()` (12 quy tắc đếm R1-R12,
tiêu chí "do_tin_cay") — phần này không nhắc gì tới cách ảnh được chụp nên
đúng nghĩa dùng chung được giữa webcam và ảnh bệnh nhân tự chụp.

KHÔNG so khớp `USER_PROMPT`: câu đầu tiên của nó tả bối cảnh chụp ("webcam máy
tính bị mờ do chuyển động" ở bản gốc), và bối cảnh đó SAI với backend — ảnh ở
đây là bệnh nhân tự chụp bằng điện thoại để xác nhận uống thuốc, không phải
khung hình webcam liên tục. Ép giống nhau ở đây là ép sai, không phải đồng bộ.
"""

import sys
from pathlib import Path

from backend.services.photo_verification import vlm_prompts
from backend.vlm_demthuoc import prompts as goc

# vlm_client.py dùng import phẳng ("from prompts import ...") — chỉ nạp được
# khi chính thư mục vlm_demthuoc/ nằm trong sys.path, cùng cách
# tests/vlm_demthuoc/conftest.py đã làm cho thư mục test đó. File này nằm ở
# thư mục test khác nên phải tự thêm, không thừa hưởng conftest kia.
_VLM_DIR = Path(__file__).resolve().parents[3] / "backend" / "vlm_demthuoc"
if str(_VLM_DIR) not in sys.path:
    sys.path.insert(0, str(_VLM_DIR))

from vlm_client import RESULT_SCHEMA as SCHEMA_GOC  # noqa: E402


def test_json_schema_giong_het_ban_goc():
    assert vlm_prompts.RESULT_SCHEMA == SCHEMA_GOC


def test_system_prompt_giong_het_khi_dem_ca_vi_thuoc():
    assert vlm_prompts.build_system_prompt(True, False) == goc.build_system_prompt(True, False)


def test_system_prompt_giong_het_khi_bo_qua_vi_thuoc():
    """Nhánh còn lại của quy tắc vỉ thuốc — dễ quên khi chỉ test một nhánh."""
    assert vlm_prompts.build_system_prompt(False, False) == goc.build_system_prompt(False, False)


def test_system_prompt_giong_het_khi_ep_dinh_dang_json_trong_prompt():
    """Nhánh json_mode='off'/'object' — nối thêm JSON_FORMAT_BLOCK."""
    assert vlm_prompts.build_system_prompt(True, True) == goc.build_system_prompt(True, True)


def test_user_prompt_co_y_khac_ban_goc_ve_boi_canh_chup():
    """Test này XANH nghĩa là hai bên VẪN khác nhau như dự định. Nếu ai đó lỡ
    tay sửa vlm_prompts.USER_PROMPT thành giống hệt bản webcam, test đỏ để hỏi
    lại có thật sự muốn xoá câu tả đúng bối cảnh (ảnh điện thoại) hay không."""
    assert vlm_prompts.USER_PROMPT != goc.USER_PROMPT
    assert "điện thoại" in vlm_prompts.USER_PROMPT
    assert "webcam" not in vlm_prompts.USER_PROMPT.lower()
