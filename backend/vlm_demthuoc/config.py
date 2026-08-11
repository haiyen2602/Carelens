"""
Cấu hình + nạp API key cho hệ thống VLM đếm thuốc.

Thông tin kết nối nằm trong `.env` ở GỐC REPO, cùng chỗ với phần còn lại của dự
án (trước đây thư mục này dùng riêng `api_key.json` — xem phần tương thích ngược
bên dưới):

    VLM_API_KEY=sk-...
    VLM_PROVIDER=openai                  # "openai" hoặc "claude"
    VLM_BASE_URL=https://api.vilao.ai/v1 # tên viết tắt hoặc URL đầy đủ
    VLM_MODEL=mn/ag/gemini-3.6-flash-high
    VLM_JSON_MODE=off                    # schema | object | off

Thứ tự ưu tiên: tham số dòng lệnh > biến môi trường (kể cả .env) > api_key.json
> mặc định.

TƯƠNG THÍCH NGƯỢC: `api_key.json` vẫn được đọc nếu biến môi trường trống, nên
máy nào đang dùng file đó vẫn chạy y nguyên, không cần sửa gì.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from getpass import getpass
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

VLM_DIR = Path(__file__).resolve().parent
KEY_FILE = VLM_DIR / "api_key.json"
REPO_ENV = VLM_DIR.parents[1] / ".env"

# Nạp .env của repo bằng ĐƯỜNG DẪN TUYỆT ĐỐI, không dùng find_dotenv(): `run.bat`
# làm `cd` vào backend/vlm_demthuoc rồi mới gọi python, còn pytest chạy từ gốc repo —
# hai thư mục làm việc khác nhau nên dò tương đối sẽ ra hai kết quả khác nhau.
#
# override=False: biến đã export sẵn ở shell vẫn thắng giá trị trong .env, giữ
# nguyên thứ tự ưu tiên cũ (dòng lệnh > biến môi trường > file).
load_dotenv(REPO_ENV, override=False)

_PLACEHOLDERS = {
    "",
    "DAN_API_KEY",
    "PASTE_YOUR_KEY_HERE",
    "sk-ant-...",
    "sk-...",
    "YOUR_KEY",
    "DAN_MODEL",
    "TEN_MODEL_CUA_BAN",
}

# Biến môi trường chứa key, theo từng nhà cung cấp. Tìm theo đúng thứ tự này,
# lấy cái đầu tiên có giá trị.
#
# VLM_API_KEY PHẢI ĐỨNG ĐẦU (sửa 2026-08-11, khi chuyển sang .env). Trước đây
# nó đứng cuối và vẫn chạy đúng, chỉ vì .env chưa bao giờ được nạp vào
# os.environ trong thư mục này. Từ lúc có load_dotenv() ở trên, OPENAI_API_KEY
# của chatbot (endpoint api.openai.com) nằm chung .env — để nó đứng trước thì
# key ấy sẽ bị gửi tới base_url của VLM và trả 401 ngay. VLM_API_KEY là biến
# DÀNH RIÊNG cho thư mục này nên nó phải thắng mọi biến dùng chung.
#
# tests/vlm_demthuoc/test_config.py khoá lại thứ tự này.
_ENV_KEYS = {
    "claude": ("VLM_API_KEY", "ANTHROPIC_API_KEY"),
    # GEMINI_API_KEY / GOOGLE_API_KEY là tên Google AI Studio dùng, để sẵn cho
    # ai đã export theo thói quen đó.
    "openai": ("VLM_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"),
}

_DEFAULT_MODEL = {"claude": "claude-opus-5", "openai": ""}


def load_config_file() -> dict[str, str]:
    """Đọc api_key.json. Giá trị placeholder được coi như chưa điền."""
    if not KEY_FILE.is_file():
        return {}
    try:
        raw = json.loads(KEY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("Không đọc được %s (%s). Bỏ qua file này.", KEY_FILE.name, exc)
        return {}
    if not isinstance(raw, dict):
        return {}

    cleaned: dict[str, str] = {}
    for key, value in raw.items():
        if key.startswith("_"):  # các trường ghi chú
            continue
        text = str(value).strip()
        if text not in _PLACEHOLDERS:
            cleaned[key] = text
    return cleaned


def _save_config_file(data: dict[str, str]) -> None:
    existing: dict[str, object] = {}
    if KEY_FILE.is_file():
        try:
            loaded = json.loads(KEY_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            existing = {}
    existing.update(data)
    KEY_FILE.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _restrict_permissions()


def _restrict_permissions() -> None:
    """Siết quyền đọc file key về riêng chủ sở hữu, nếu hệ điều hành cho phép.

    NÓI THẲNG VỚI NGƯỜI DÙNG KHI KHÔNG LÀM ĐƯỢC (sửa 2026-08-10, phản hồi
    review): `os.chmod(0o600)` chỉ có tác dụng thật trên hệ POSIX. Trên Windows
    nó *không báo lỗi* mà cũng *không siết quyền* — chỉ bật/tắt cờ read-only.
    Bản trước bọc nguyên khối trong `except OSError: pass`, nên người dùng
    Windows tưởng file đã được bảo vệ trong khi không hề.

    Bắt riêng theo `os.name` thay vì dựa vào exception chính vì lý do đó: trên
    Windows `chmod` *thành công*, nên không exception nào nổ ra để mà cảnh báo.

    Cũng theo ADR-0004 §4: không nuốt lỗi im lặng — mọi nhánh ở đây đều nói ra
    kết quả thật.
    """
    if os.name != "posix":
        logger.warning(
            "%s vừa được ghi nhưng KHÔNG siết được quyền truy cập trên hệ điều "
            "hành này. File đang dùng quyền mặc định của thư mục. Nếu máy có "
            "nhiều người dùng, hãy đặt key qua biến môi trường thay vì lưu file.",
            KEY_FILE.name,
        )
        return

    try:
        os.chmod(KEY_FILE, 0o600)
    except OSError as exc:
        logger.warning(
            "Không siết được quyền cho %s (%s). File có thể đọc được bởi người "
            "dùng khác trên máy này.",
            KEY_FILE.name, exc,
        )


def load_api_key(provider: str = "claude", allow_prompt: bool = True) -> str:
    """Lấy API key: biến môi trường -> api_key.json -> hỏi người dùng."""
    for name in _ENV_KEYS.get(provider, ("VLM_API_KEY",)):
        value = os.environ.get(name, "").strip()
        if value:
            return value

    key = load_config_file().get("api_key", "")
    if key:
        return key

    if not (allow_prompt and sys.stdin is not None and sys.stdin.isatty()):
        env_name = _ENV_KEYS.get(provider, ("VLM_API_KEY",))[0]
        raise SystemExit(
            f"Chưa có API key cho nhà cung cấp '{provider}'.\n"
            f'  Cách 1: điền "api_key" trong {KEY_FILE}\n'
            f"  Cách 2: set {env_name}=..."
        )

    print(f"Chưa tìm thấy API key cho nhà cung cấp '{provider}'.")
    print(f"Bạn có thể điền sẵn vào {KEY_FILE.name} để lần sau khỏi nhập.")
    key = getpass("Nhập API key (gõ/dán vào, màn hình sẽ không hiện): ").strip()
    if not key:
        raise SystemExit("Không nhập key, dừng chương trình.")

    answer = input(f"Lưu key vào {KEY_FILE.name} cho lần sau? [y/N]: ").strip().lower()
    if answer.startswith("y"):
        _save_config_file({"api_key": key})
        print(f"Đã lưu vào {KEY_FILE}. Đừng commit/chia sẻ file này.")

    return key


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, "").strip() or default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _cfg(key: str, env_name: str, default: str = "") -> str:
    """Ưu tiên biến môi trường, rồi tới api_key.json, rồi mặc định."""
    return _env(env_name) or load_config_file().get(key, "") or default


@dataclass
class Settings:
    """Tham số chạy. Đọc từ env + api_key.json, ghi đè được bằng dòng lệnh."""

    # --- Nhà cung cấp & model ---
    provider: str = field(
        default_factory=lambda: _cfg("provider", "VLM_PROVIDER", "claude").lower()
    )
    model: str = field(default_factory=lambda: _cfg("model", "VLM_MODEL"))
    base_url: str = field(default_factory=lambda: _cfg("base_url", "VLM_BASE_URL"))
    # schema | object | off — chỉ áp dụng cho endpoint tương thích OpenAI.
    json_mode: str = field(
        default_factory=lambda: _cfg("json_mode", "VLM_JSON_MODE", "schema").lower()
    )
    # low | medium | high | xhigh | max — chỉ áp dụng cho Claude.
    effort: str = field(default_factory=lambda: _env("VLM_EFFORT", "medium"))
    max_tokens: int = field(default_factory=lambda: _env_int("VLM_MAX_TOKENS", 4000))
    # Số lần gọi lại khi máy chủ trả phản hồi RỖNG/HỎNG NGAY LẬP TỨC. Cần với
    # endpoint chập chờn — api.vilao.ai hỏng khoảng một nửa số lần gọi, 5 lượt
    # cho ~97% thành công. Mỗi lượt hỏng kiểu này gần như không tốn thời gian,
    # nên để 5 vẫn rẻ. KHÔNG áp dụng cho lỗi quá giờ — xem `timeout` bên dưới.
    retries: int = field(default_factory=lambda: _env_int("VLM_RETRIES", 5))
    # Thời gian chờ tối đa cho MỘT lần gọi API (giây), tính cả lúc tải ảnh lên.
    # Một lần đếm thật mất ~25s nên 45s đã rất rộng rãi.
    #
    # Đây là chặn trên cho thời gian "treo" khi máy chủ nhận kết nối rồi im
    # lặng: quá giờ thì báo lỗi luôn chứ không thử lại. Thử lại một lần quá giờ
    # tốn trọn 45 giây mà khả năng thành công rất thấp — khác hẳn lỗi rỗng tức
    # thì ở `retries`. Người dùng đang ngồi trước camera, bấm `e` để đếm lại
    # nhanh hơn nhiều so với việc chương trình tự thử trong im lặng.
    timeout: float = field(default_factory=lambda: _env_float("VLM_TIMEOUT", 45.0))

    # --- Camera ---
    camera_index: int = field(default_factory=lambda: _env_int("VLM_CAMERA", 0))
    frame_width: int = field(default_factory=lambda: _env_int("VLM_FRAME_WIDTH", 1280))
    frame_height: int = field(default_factory=lambda: _env_int("VLM_FRAME_HEIGHT", 720))

    # --- Cơ chế kích hoạt chụp ---
    # "stable": khung hình đứng yên đủ `stable_seconds` giây thì chụp (mặc định).
    # "timer" : cứ `timer_seconds` giây thì chụp 1 lần, không quan tâm khung
    #           hình có đứng yên hay không.
    # "frames": cứ mỗi `frame_interval` khung hình thì chụp 1 lần.
    trigger_mode: str = field(
        default_factory=lambda: _env("VLM_TRIGGER_MODE", "stable").lower()
    )
    timer_seconds: float = field(
        default_factory=lambda: _env_float("VLM_TIMER_SECONDS", 3.0)
    )
    # Chụp xong thì đóng băng khung hình, phải bấm SPACE mới chụp tiếp. Tắt đi
    # nếu muốn chạy liên tục không cần người bấm.
    wait_space: bool = field(
        default_factory=lambda: _env("VLM_WAIT_SPACE", "1").lower()
        not in {"0", "false", "no"}
    )
    stable_seconds: float = field(
        default_factory=lambda: _env_float("VLM_STABLE_SECONDS", 3.0)
    )
    # Ngưỡng chuyển động: chênh lệch pixel trung bình giữa 2 khung liên tiếp
    # (thang 0–255). Dưới ngưỡng = coi như đứng yên. Nhiễu webcam thường 0.5–1.5.
    motion_threshold: float = field(
        default_factory=lambda: _env_float("VLM_MOTION_THRESHOLD", 2.0)
    )
    frame_interval: int = field(
        default_factory=lambda: _env_int("VLM_FRAME_INTERVAL", 15)
    )
    # Chặn dưới về thời gian giữa 2 lần gọi API (giây), áp dụng cho cả 2 chế độ.
    min_interval_sec: float = field(
        default_factory=lambda: _env_float("VLM_MIN_INTERVAL_SEC", 3.0)
    )

    # --- Ảnh gửi lên ---
    max_image_edge: int = field(
        default_factory=lambda: _env_int("VLM_MAX_IMAGE_EDGE", 1600)
    )
    jpeg_quality: int = field(default_factory=lambda: _env_int("VLM_JPEG_QUALITY", 90))

    # --- Prompt ---
    count_pills_in_blister: bool = field(
        default_factory=lambda: _env("VLM_COUNT_BLISTER", "1").lower()
        not in {"0", "false", "no"}
    )

    def __post_init__(self) -> None:
        if not self.model:
            self.model = _DEFAULT_MODEL.get(self.provider, "")

    def describe(self) -> str:
        if self.trigger_mode == "timer":
            trigger = f"chụp mỗi {self.timer_seconds:g}s"
        elif self.trigger_mode == "frames":
            trigger = f"chụp mỗi {self.frame_interval} khung hình"
        else:
            trigger = (
                f"chụp khi khung hình đứng yên {self.stable_seconds:g}s "
                f"(ngưỡng {self.motion_threshold:g})"
            )
        # Ở chế độ timer, chính đồng hồ đã giãn cách các lần gọi API rồi.
        if self.trigger_mode != "timer":
            trigger += f", cách nhau ≥ {self.min_interval_sec:g}s"
        return (
            f"camera={self.camera_index} | {trigger} | "
            f"{'chờ SPACE sau mỗi lần chụp' if self.wait_space else 'chạy liên tục'} | "
            f"ảnh≤{self.max_image_edge}px | "
            f"vỉ thuốc={'đếm' if self.count_pills_in_blister else 'bỏ qua'}"
        )
