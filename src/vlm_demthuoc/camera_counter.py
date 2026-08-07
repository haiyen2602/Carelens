# -*- coding: utf-8 -*-
"""
Đếm thuốc trực tiếp từ webcam bằng VLM (Claude).

Cách chạy:
    cd vlm
    pip install -r requirements.txt
    python camera_counter.py

Vòng chạy mặc định (chế độ `stable`):

    1. Khung hình **đứng yên đủ 3 giây** (bạn đã đặt thuốc xong, không còn rung
       tay) thì chương trình tự chụp khung hình đó.
    2. Khung hình vừa chụp được **đóng băng** trên màn hình, gửi lên model đếm,
       rồi hiện kết quả ngay trên ảnh đó.
    3. Bấm **SPACE** để bỏ đóng băng. Đồng hồ 3 giây bắt đầu lại từ lúc bấm,
       nên cứ giữ yên thêm 3 giây là có lần đếm kế tiếp.

Đổi thời gian chờ bằng `--stable-seconds`, chỉnh độ nhạy bằng
`--motion-threshold` (tăng lên nếu camera nhiễu làm nó không bao giờ chịu chụp).
Chạy liên tục không cần bấm SPACE bằng `--no-wait-space`. Hai chế độ khác:
`--mode timer` (cứ N giây chụp một lần) và `--mode frames` (theo số khung hình).

Mọi khung hình được chụp để đếm đều được lưu vào thư mục `anh_thuoc/` với tên
theo mốc thời gian (capture_20260806_101530_412.jpg). Đổi chỗ lưu bằng
`--anh-dir`, tắt hẳn bằng `--no-save-anh`.

Kết quả mọi lần đếm được ghi vào `ket_qua.json` (mảng JSON, ghi lại sau mỗi lần
đếm). File **tích luỹ qua mọi lần chạy**: mở chương trình lần sau sẽ ghi tiếp
vào cuối chứ không xoá kết quả cũ. Trường `phien` cho biết bản ghi thuộc lần
chạy nào. Đổi chỗ bằng `--json-out`.

Phím tắt trong cửa sổ camera:
    e          : CHỤP NGAY, không cần chờ đứng yên (đang đóng băng cũng chụp)
    SPACE      : đang đóng băng -> chụp tiếp; đang chạy -> chụp ngay lập tức
    s          : lưu khung hình hiện tại vào anh_thuoc/ (không gọi API)
    q hoặc ESC : thoát
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

from config import Settings, load_api_key
from prompts import COUNT_KEYS, COUNT_LABELS_ASCII
from providers import BASE_URL_PRESETS, BackendError
from vlm_client import CountResult, PillCounter

# Terminal Windows hay dùng bảng mã cũ -> ép UTF-8 để in được tiếng Việt.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

VLM_DIR = Path(__file__).resolve().parent
# Mọi khung hình được chụp để đếm đều lưu lại đây, tiện xem lại / dựng bộ ảnh test.
ANH_THUOC_DIR = VLM_DIR / "anh_thuoc"
WINDOW_NAME = "VLM Pills Counter - e:chup ngay  SPACE:chup tiep  s:luu anh  q:thoat"

_CONFIDENCE_TEXT = {
    "cao": "cao",
    "trung_binh": "trung bình",
    "thap": "thấp",
}
_CONFIDENCE_COLOR = {  # BGR
    "cao": (80, 200, 80),
    "trung_binh": (60, 190, 230),
    "thap": (80, 80, 235),
}


# ---------------------------------------------------------------------------
# Phát hiện khung hình đứng yên
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Thông báo
# ---------------------------------------------------------------------------
def print_result(result: CountResult, index: int, image_path: Path | None = None) -> None:
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

    counts = result.counts
    print(f"[{stamp}] Lần đếm #{index}  ({result.latency_sec:.1f}s)")
    print(f"  Viên nang  : {counts['vien_nang']}")
    print(f"  Viên nén   : {counts['vien_nen']}")
    print(f"  Tuýp thuốc : {counts['tuyp_thuoc']}")
    print(f"  Lọ thuốc   : {counts['lo_thuoc']}")
    print(f"  Hộp thuốc  : {counts['hop_thuoc']}")
    print(f"  ---------------------------------")
    print(f"  Tổng số viên (nang + nén): {result.total_pills}")
    print(f"  Độ tin cậy : {_CONFIDENCE_TEXT.get(result.do_tin_cay, result.do_tin_cay)}")
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
        print(f"Không lưu được ảnh: {exc}", file=sys.stderr)
        return None
    return path


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
        print(f"Không đọc được {path.name} ({ly_do}). Giữ lại thành {backup.name} "
              "và bắt đầu file mới.", file=sys.stderr)
        try:
            path.replace(backup)
        except OSError:
            pass
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
        print(f"Không ghi được {path}: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Vẽ overlay lên cửa sổ camera (cv2.putText chỉ vẽ được ASCII)
# ---------------------------------------------------------------------------
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
    panel_h = 190
    # Vẽ lên bản sao: khung hình gốc còn được StabilityWatcher so sánh ở vòng
    # lặp sau, vẽ đè lên nó sẽ bị tính là chuyển động.
    frame = frame.copy()
    if frozen:  # viền vàng cho biết khung hình đang bị đóng băng
        cv2.rectangle(frame, (0, 0), (frame.shape[1] - 1, frame.shape[0] - 1),
                      (0, 215, 255), 6)
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (300, panel_h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

    y = 26
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
            y += 26
        cv2.putText(frame, f"Tong vien : {result.total_pills}", (12, y),
                    font, 0.6, (0, 255, 255), 2, cv2.LINE_AA)
        y += 26
        color = _CONFIDENCE_COLOR.get(result.do_tin_cay, (200, 200, 200))
        cv2.putText(frame, f"Do tin cay: {result.do_tin_cay}", (12, y),
                    font, 0.55, color, 1, cv2.LINE_AA)

    text, color = status
    cv2.putText(frame, text, (12, frame.shape[0] - 14),
                font, 0.55, color, 2, cv2.LINE_AA)
    return frame


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------
def open_camera(settings: Settings):
    backends = [cv2.CAP_DSHOW, cv2.CAP_ANY] if sys.platform == "win32" else [cv2.CAP_ANY]
    for backend in backends:
        cap = cv2.VideoCapture(settings.camera_index, backend)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, settings.frame_width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.frame_height)
            return cap
        cap.release()
    raise SystemExit(
        f"Không mở được camera index {settings.camera_index}.\n"
        "  - Kiểm tra webcam đã cắm và không bị ứng dụng khác chiếm dụng.\n"
        "  - Thử index khác: python camera_counter.py --camera 1"
    )


def parse_args() -> argparse.Namespace:
    defaults = Settings()
    parser = argparse.ArgumentParser(
        description="Đếm thuốc trực tiếp từ webcam bằng VLM (Claude).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--provider", choices=("claude", "openai"), default=defaults.provider,
                        help="claude = SDK anthropic; openai = mọi endpoint tương thích OpenAI")
    parser.add_argument("--base-url", default=defaults.base_url,
                        help=f"URL đầy đủ hoặc tên viết tắt: {', '.join(BASE_URL_PRESETS)}")
    parser.add_argument("--json-mode", choices=("schema", "object", "off"),
                        default=defaults.json_mode,
                        help="Cách ép JSON với endpoint OpenAI-compatible; tự hạ cấp nếu không hỗ trợ")
    parser.add_argument("--camera", type=int, default=defaults.camera_index,
                        help="Chỉ số camera")
    parser.add_argument("--mode", choices=("timer", "stable", "frames"),
                        default=defaults.trigger_mode,
                        help="timer = cứ N giây chụp 1 lần; stable = chụp khi khung hình "
                             "đứng yên; frames = chụp theo số khung")
    parser.add_argument("--timer-seconds", type=float, default=defaults.timer_seconds,
                        help="Bao nhiêu giây thì chụp 1 lần (chế độ timer)")
    parser.add_argument("--no-wait-space", action="store_true",
                        help="Chụp xong chạy tiếp luôn, không đóng băng chờ bấm SPACE")
    parser.add_argument("--stable-seconds", type=float, default=defaults.stable_seconds,
                        help="Phải đứng yên bao nhiêu giây thì chụp (chế độ stable)")
    parser.add_argument("--motion-threshold", type=float, default=defaults.motion_threshold,
                        help="Ngưỡng coi là đứng yên; tăng lên nếu camera nhiễu, giảm nếu quá nhạy")
    parser.add_argument("--interval", type=int, default=defaults.frame_interval,
                        help="Cứ bao nhiêu khung hình thì đếm 1 lần (chế độ frames)")
    parser.add_argument("--min-interval", type=float, default=defaults.min_interval_sec,
                        help="Khoảng cách tối thiểu giữa 2 lần gọi API (giây)")
    parser.add_argument("--model", default=defaults.model, help="Model dùng để đếm")
    parser.add_argument("--effort", default=defaults.effort,
                        help="Mức effort: low/medium/high/xhigh/max, để rỗng nếu model không hỗ trợ")
    parser.add_argument("--max-edge", type=int, default=defaults.max_image_edge,
                        help="Cạnh dài nhất của ảnh gửi lên API (pixel)")
    parser.add_argument("--no-blister", action="store_true",
                        help="Không đếm viên còn nằm trong vỉ")
    parser.add_argument("--no-window", action="store_true",
                        help="Chạy không cửa sổ (máy không có giao diện đồ hoạ)")
    parser.add_argument("--retries", type=int, default=defaults.retries,
                        help="Số lần gọi lại khi máy chủ trả phản hồi rỗng")
    parser.add_argument("--anh-dir", default=str(ANH_THUOC_DIR),
                        help="Thư mục lưu ảnh đã chụp")
    parser.add_argument("--no-save-anh", action="store_true",
                        help="Không lưu ảnh đã chụp (chỉ gọi API rồi bỏ ảnh đi)")
    parser.add_argument("--json-out", default=str(VLM_DIR / "ket_qua.json"),
                        help="File JSON lưu kết quả mọi lần đếm")
    parser.add_argument("--log", default="", help="Ghi thêm kết quả ra file .jsonl")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = Settings(
        provider=args.provider,
        model=args.model,
        base_url=args.base_url,
        json_mode=args.json_mode,
        effort=args.effort,
        camera_index=args.camera,
        trigger_mode=args.mode,
        timer_seconds=max(0.5, args.timer_seconds),
        wait_space=not args.no_wait_space,
        stable_seconds=max(0.0, args.stable_seconds),
        motion_threshold=max(0.0, args.motion_threshold),
        frame_interval=max(1, args.interval),
        min_interval_sec=max(0.0, args.min_interval),
        max_image_edge=args.max_edge,
        count_pills_in_blister=not args.no_blister,
        retries=max(1, args.retries),
    )

    api_key = load_api_key(settings.provider)
    try:
        counter = PillCounter(
            api_key=api_key,
            provider=settings.provider,
            model=settings.model,
            base_url=settings.base_url,
            json_mode=settings.json_mode,
            effort=settings.effort,
            max_tokens=settings.max_tokens,
            max_image_edge=settings.max_image_edge,
            jpeg_quality=settings.jpeg_quality,
            count_pills_in_blister=settings.count_pills_in_blister,
            retries=settings.retries,
        )
    except BackendError as exc:
        raise SystemExit(str(exc)) from exc

    log_path = Path(args.log).expanduser() if args.log else None
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)

    anh_dir = None if args.no_save_anh else Path(args.anh_dir).expanduser()
    if anh_dir:
        anh_dir.mkdir(parents=True, exist_ok=True)

    json_path = Path(args.json_out).expanduser() if args.json_out else None
    # Nạp kết quả những lần chạy trước rồi ghi tiếp, không bắt đầu lại từ đầu.
    records: list[dict] = load_results_json(json_path) if json_path else []
    phien = time.strftime("%Y-%m-%d %H:%M:%S")

    cap = open_camera(settings)
    show_window = not args.no_window

    # Không có cửa sổ thì không nhận được phím -> chờ SPACE sẽ treo vĩnh viễn.
    if settings.wait_space and not show_window:
        print("Không có cửa sổ nên không bấm được SPACE — tự chuyển sang chạy liên tục.",
              file=sys.stderr)
        settings.wait_space = False

    print(f"Model  : {counter.describe()}")
    print(f"Cấu hình: {settings.describe()}")
    print(f"Lưu ảnh: {anh_dir if anh_dir else 'tắt'}")
    print(f"Kết quả: {json_path if json_path else 'tắt'}"
          + (f" (đã có {len(records)} lần đếm cũ, sẽ ghi tiếp)" if records else ""))
    if settings.trigger_mode == "stable":
        print(f"Đặt thuốc vào khung hình và giữ yên {settings.stable_seconds:g} giây "
              "— chương trình sẽ tự chụp và đếm.", end=" ")
    elif settings.trigger_mode == "timer":
        print(f"Cứ {settings.timer_seconds:g} giây chụp một lần.", end=" ")
    if settings.trigger_mode in ("stable", "timer"):
        print("Chụp xong ảnh sẽ dừng lại, bấm SPACE để chụp tiếp."
              if settings.wait_space else "Chạy liên tục.")
    print("Đang chạy. Nhấn q (trong cửa sổ camera) hoặc Ctrl+C để dừng.", flush=True)

    watcher = (
        StabilityWatcher(settings.motion_threshold, settings.stable_seconds)
        if settings.trigger_mode == "stable"
        else None
    )

    executor = ThreadPoolExecutor(max_workers=1)
    pending: Future[CountResult] | None = None
    pending_path: Path | None = None  # ảnh ứng với lần đếm đang chờ kết quả
    last_result: CountResult | None = None
    last_sent = 0.0
    frame_index = 0
    # Đánh số tiếp nối file cũ để mỗi bản ghi mang một số riêng, không trùng.
    run_index = max(
        (r["lan"] for r in records if isinstance(r.get("lan"), int)), default=0
    )
    dem_phien = 0  # số lần đếm của riêng phiên chạy này

    # Ảnh đang bị đóng băng trên màn hình (None = đang chạy bình thường).
    frozen_frame: np.ndarray | None = None
    timer_start = time.monotonic()  # mốc đếm giờ của chế độ timer

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Mất tín hiệu camera, dừng lại.", file=sys.stderr)
                break

            frame_index += 1
            now = time.monotonic()
            if watcher is not None:
                watcher.update(frame, now)

            # Nhận kết quả nếu lần gọi trước đã xong.
            if pending is not None and pending.done():
                last_result = pending.result()
                pending = None
                run_index += 1
                dem_phien += 1
                print_result(last_result, run_index, pending_path)
                if log_path:
                    append_log(log_path, last_result)
                if json_path:
                    records.append(
                        build_record(last_result, run_index, pending_path, phien)
                    )
                    save_results_json(json_path, records)
                pending_path = None

            # --- Bàn phím ---
            force = False
            if show_window:
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
                if key == ord("e"):
                    # Chụp ngay, không cần chờ ổn định. Đang đóng băng thì bỏ
                    # đóng băng luôn rồi chụp, khỏi phải bấm SPACE trước.
                    frozen_frame = None
                    force = True
                if key == ord(" "):
                    if frozen_frame is not None:
                        # Đang đóng băng -> chạy tiếp, đếm lại từ đầu.
                        frozen_frame = None
                        timer_start = now
                        if watcher is not None:
                            watcher.rearm(now)
                    else:
                        force = True  # đang chạy -> chụp ngay
                if key == ord("s"):
                    saved = save_frame(frame, anh_dir or ANH_THUOC_DIR, prefix="thucong")
                    if saved:
                        print(f"Đã lưu {saved}", flush=True)

            # --- Tới lượt chụp chưa? ---
            if frozen_frame is not None:
                due = False  # đang đóng băng thì không tự chụp nữa
            elif settings.trigger_mode == "timer":
                due = (now - timer_start) >= settings.timer_seconds
            elif watcher is not None:
                due = watcher.ready(now)
            else:
                due = frame_index % settings.frame_interval == 0

            # Ở chế độ timer chính đồng hồ đã giãn cách các lần gọi API.
            cooled = (
                True if settings.trigger_mode == "timer"
                else (now - last_sent) >= settings.min_interval_sec
            )

            if (due or force) and pending is None and (cooled or force):
                if watcher is not None:
                    watcher.consume()
                shot = frame.copy()
                pending_path = save_frame(shot, anh_dir) if anh_dir else None
                pending = executor.submit(counter.count, shot)
                last_sent = now
                timer_start = now
                # Xoá kết quả cũ: để nguyên thì số của ảnh trước sẽ hiện đè lên
                # ảnh mới vừa chụp, rất dễ đọc nhầm.
                last_result = None
                if settings.wait_space:
                    frozen_frame = shot  # giữ nguyên ảnh vừa chụp cho tới khi bấm SPACE

            # --- Vẽ ---
            if show_window:
                remaining = settings.frame_interval - (frame_index % settings.frame_interval)
                hien = frame if frozen_frame is None else frozen_frame
                status = status_text(
                    watcher, settings, pending is not None, now, remaining,
                    frozen=frozen_frame is not None,
                    seconds_left=settings.timer_seconds - (now - timer_start),
                )
                cv2.imshow(
                    WINDOW_NAME,
                    draw_overlay(hien, last_result, status, frozen=frozen_frame is not None),
                )
    except KeyboardInterrupt:
        print("\nDừng theo yêu cầu người dùng.")
    finally:
        cap.release()
        if show_window:
            cv2.destroyAllWindows()
        executor.shutdown(wait=False, cancel_futures=True)

    print(f"Lần chạy này: {dem_phien} lần đếm.")
    if json_path and records:
        print(f"Tổng cộng {len(records)} lần đếm trong {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
