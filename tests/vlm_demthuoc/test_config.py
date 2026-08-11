"""Kiểm chứng nguồn cấu hình của VLM đếm thuốc sau khi chuyển sang `.env`.

Trọng tâm là THỨ TỰ ƯU TIÊN, không phải giá trị cụ thể. Từ lúc `config.py` gọi
`load_dotenv()`, thư mục này dùng chung `os.environ` với chatbot — mà chatbot có
`OPENAI_API_KEY` trỏ tới api.openai.com còn VLM trỏ tới một endpoint khác hẳn.
Chọn nhầm key giữa hai cái đó là lỗi 401 lúc chạy thật, không có cách nào phát
hiện sớm hơn ngoài mấy test dưới đây.

Không cần mạng, không cần webcam, không đụng tới `api_key.json` thật: mọi test
đều trỏ `config.KEY_FILE` sang `tmp_path`.
"""

import json

import pytest

import config

# Mọi biến môi trường mà config.py có thể đọc. Xoá sạch trước mỗi test để giá
# trị thật trong .env của máy đang chạy không lọt vào kết quả.
BIEN_MOI_TRUONG = (
    "VLM_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "VLM_PROVIDER",
    "VLM_MODEL",
    "VLM_BASE_URL",
    "VLM_JSON_MODE",
    "VLM_TIMEOUT",
    "VLM_RETRIES",
)


@pytest.fixture(autouse=True)
def moi_truong_sach(monkeypatch, tmp_path):
    """Không biến môi trường nào, và không có api_key.json."""
    for ten in BIEN_MOI_TRUONG:
        monkeypatch.delenv(ten, raising=False)
    monkeypatch.setattr(config, "KEY_FILE", tmp_path / "khong_ton_tai.json")


@pytest.fixture
def viet_json(monkeypatch, tmp_path):
    """Dựng một api_key.json giả rồi trỏ config sang đó."""

    def _viet(**noi_dung):
        path = tmp_path / "api_key.json"
        path.write_text(json.dumps(noi_dung, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(config, "KEY_FILE", path)
        return path

    return _viet


# ---------------------------------------------------------------------------
# Thứ tự các biến môi trường — phần dễ hỏng nhất
# ---------------------------------------------------------------------------
def test_vlm_api_key_thang_openai_api_key(monkeypatch):
    """Test này đỏ nghĩa là VLM sắp gửi key của chatbot tới endpoint của mình.

    Cả hai biến cùng nằm trong `.env` ở gốc repo. `VLM_API_KEY` là biến DÀNH
    RIÊNG cho thư mục này nên phải thắng `OPENAI_API_KEY` dùng chung — xem chú
    thích ở `config._ENV_KEYS`.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-cua-chatbot")
    monkeypatch.setenv("VLM_API_KEY", "sk-cua-vlm")
    assert config.load_api_key("openai") == "sk-cua-vlm"


def test_vlm_api_key_thang_anthropic_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-cua-nguoi-khac")
    monkeypatch.setenv("VLM_API_KEY", "sk-cua-vlm")
    assert config.load_api_key("claude") == "sk-cua-vlm"


def test_van_dung_duoc_openai_api_key_khi_khong_co_vlm_api_key(monkeypatch):
    """Bỏ VLM_API_KEY đi thì các tên quen thuộc vẫn còn tác dụng."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-cua-chatbot")
    assert config.load_api_key("openai") == "sk-cua-chatbot"


# ---------------------------------------------------------------------------
# Tương thích ngược với api_key.json
# ---------------------------------------------------------------------------
def test_khong_co_bien_moi_truong_thi_doc_api_key_json(viet_json):
    """Máy nào chưa điền .env vẫn chạy y như trước, không phải sửa gì."""
    viet_json(api_key="sk-trong-file")
    assert config.load_api_key("openai") == "sk-trong-file"


def test_bien_moi_truong_thang_api_key_json(monkeypatch, viet_json):
    viet_json(api_key="sk-trong-file")
    monkeypatch.setenv("VLM_API_KEY", "sk-trong-env")
    assert config.load_api_key("openai") == "sk-trong-env"


def test_key_placeholder_trong_json_coi_nhu_chua_dien(viet_json):
    viet_json(api_key="DAN_API_KEY")
    with pytest.raises(SystemExit):
        config.load_api_key("openai", allow_prompt=False)


def test_json_hong_khong_lam_chet_chuong_trinh(monkeypatch, tmp_path):
    """File JSON sai cú pháp chỉ bị bỏ qua kèm cảnh báo, không nổ ra ngoài."""
    path = tmp_path / "api_key.json"
    path.write_text("{ day khong phai json", encoding="utf-8")
    monkeypatch.setattr(config, "KEY_FILE", path)
    assert config.load_config_file() == {}


# ---------------------------------------------------------------------------
# Thông báo khi thiếu key
# ---------------------------------------------------------------------------
def test_thieu_key_thi_bao_dung_ten_bien_can_dien():
    """Thông báo lấy tên biến từ `_ENV_KEYS[...][0]` nên nó đi theo thứ tự trên."""
    with pytest.raises(SystemExit) as loi:
        config.load_api_key("openai", allow_prompt=False)
    assert "VLM_API_KEY" in str(loi.value)


# ---------------------------------------------------------------------------
# 4 giá trị còn lại, không chỉ mỗi key
# ---------------------------------------------------------------------------
def test_settings_doc_cau_hinh_tu_bien_moi_truong(monkeypatch):
    monkeypatch.setenv("VLM_PROVIDER", "openai")
    monkeypatch.setenv("VLM_BASE_URL", "https://vi-du.test/v1")
    monkeypatch.setenv("VLM_MODEL", "mot-model-nao-do")
    monkeypatch.setenv("VLM_JSON_MODE", "off")

    settings = config.Settings()

    assert settings.provider == "openai"
    assert settings.base_url == "https://vi-du.test/v1"
    assert settings.model == "mot-model-nao-do"
    assert settings.json_mode == "off"


def test_settings_van_doc_duoc_tu_api_key_json(viet_json):
    viet_json(
        provider="openai",
        base_url="https://trong-file.test/v1",
        model="model-trong-file",
        json_mode="off",
    )

    settings = config.Settings()

    assert settings.provider == "openai"
    assert settings.base_url == "https://trong-file.test/v1"
    assert settings.model == "model-trong-file"
    assert settings.json_mode == "off"


def test_bien_moi_truong_thang_json_cho_tung_gia_tri(monkeypatch, viet_json):
    viet_json(provider="claude", base_url="https://trong-file.test/v1")
    monkeypatch.setenv("VLM_PROVIDER", "openai")

    settings = config.Settings()

    assert settings.provider == "openai"  # env thắng
    assert settings.base_url == "https://trong-file.test/v1"  # json vẫn được dùng


# ---------------------------------------------------------------------------
# Thời gian chờ
# ---------------------------------------------------------------------------
def test_timeout_mac_dinh_du_rong_cho_mot_lan_dem_that():
    """Một lần đếm thật đo được ~26s. Mặc định phải rộng hơn thế nhưng không
    rộng tới mức người dùng tưởng chương trình chết (mặc định cũ của SDK là 120s).
    """
    assert 30.0 <= config.Settings().timeout <= 60.0


def test_timeout_doc_duoc_tu_bien_moi_truong(monkeypatch):
    monkeypatch.setenv("VLM_TIMEOUT", "12.5")
    assert config.Settings().timeout == 12.5


def test_timeout_sai_dinh_dang_thi_quay_ve_mac_dinh(monkeypatch):
    monkeypatch.setenv("VLM_TIMEOUT", "khong-phai-so")
    assert config.Settings().timeout == 45.0


# ---------------------------------------------------------------------------
# Đường dẫn tới .env
# ---------------------------------------------------------------------------
def test_repo_env_tro_ve_dung_goc_repo():
    """`config.py` nạp .env bằng đường dẫn tuyệt đối chứ không dò theo thư mục
    làm việc — `run.bat` chạy từ src/vlm_demthuoc còn pytest chạy từ gốc repo.
    """
    assert config.REPO_ENV.name == ".env"
    assert config.REPO_ENV.parent == config.VLM_DIR.parents[1]
    # `.env.example` là file luôn nằm cạnh `.env` thật — trỏ đúng chỗ nó nằm
    # tức là trỏ đúng chỗ `.env` sẽ nằm.
    assert (config.REPO_ENV.parent / ".env.example").is_file()
