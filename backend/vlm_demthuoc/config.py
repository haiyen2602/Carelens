# -*- coding: utf-8 -*-
"""
Cấu hình + nạp API key cho hệ thống VLM đếm thuốc.

Toàn bộ thông tin kết nối nằm trong MỘT file: `vlm/api_key.json`.

    {
      "provider": "openai",                          // "openai" hoặc "claude"
      "api_key":  "sk-...",
      "base_url": "openrouter",                      // tên viết tắt hoặc URL đầy đủ
      "model":    "google/gemini-2.5-flash"
    }

Thứ tự ưu tiên: tham số dòng lệnh > biến môi trường > api_key.json > mặc định.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from getpass import getpass
from pathlib import Path

VLM_DIR = Path(__file__).resolve().parent
KEY_FILE = VLM_DIR / "api_key.json"

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

# Biến môi trường chứa key, theo từng nhà cung cấp.
_ENV_KEYS = {
    "claude": ("ANTHROPIC_API_KEY", "VLM_API_KEY"),
    # GEMINI_API_KEY / GOOGLE_API_KEY là tên Google AI Studio dùng, để sẵn cho
    # ai đã export theo thói quen đó.
    "openai": ("OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "VLM_API_KEY"),
}

_DEFAULT_MODEL = {"claude": "claude-opus-5", "openai": ""}


def load_config_file() -> dict[str, str]:
    """Đọc api_key.json. Giá trị placeholder được coi như chưa điền."""
    if not KEY_FILE.is_file():
        return {}
    try:
        raw = json.loads(KEY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"Cảnh báo: không đọc được {KEY_FILE.name} ({exc}). Bỏ qua file này.",
              file=sys.stderr)
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
    try:  # trên Linux/macOS thì siết quyền; Windows bỏ qua
        os.chmod(KEY_FILE, 0o600)
    except OSError:
        pass


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
    # Số lần gọi lại khi máy chủ trả phản hồi rỗng/hỏng. Cần với endpoint chập
    # chờn — api.vilao.ai hỏng khoảng một nửa số lần gọi, 5 lượt cho ~97% thành
    # công. Endpoint lành mạnh không bao giờ chạm tới cơ chế này nên không tốn gì.
    retries: int = field(default_factory=lambda: _env_int("VLM_RETRIES", 5))

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
