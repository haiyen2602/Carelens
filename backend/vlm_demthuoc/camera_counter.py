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

Cấu trúc file trong thư mục này:
    camera_counter.py  - CLI + vòng lặp điều khiển (file này)
    stability.py       - phát hiện khung hình đứng yên
    overlay.py         - vẽ lên cửa sổ camera
    results_store.py   - in kết quả, lưu ảnh, ghi file JSON
    config.py          - tham số chạy + nạp API key
    vlm_client.py      - mã hoá ảnh, gọi model, làm sạch JSON trả về
    providers.py       - chi tiết từng nhà cung cấp (Claude / OpenAI-compatible)
    prompts.py         - system prompt + danh mục loại thuốc
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from config import Settings, load_api_key
from overlay import draw_overlay, status_text
from providers import BASE_URL_PRESETS, BackendError
from results_store import (
    append_log,
    build_record,
    load_results_json,
    next_run_index,
    print_result,
    save_frame,
    save_results_json,
)
from stability import StabilityWatcher
from vlm_client import CountResult, PillCounter

# Terminal Windows hay dùng bảng mã cũ -> ép UTF-8 để in được tiếng Việt.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

logger = logging.getLogger(__name__)

VLM_DIR = Path(__file__).resolve().parent
# Mọi khung hình được chụp để đếm đều lưu lại đây, tiện xem lại / dựng bộ ảnh test.
ANH_THUOC_DIR = VLM_DIR / "anh_thuoc"
WINDOW_NAME = "VLM Pills Counter - e:chup ngay  SPACE:chup tiep  s:luu anh  q:thoat"


# ---------------------------------------------------------------------------
# Trạng thái
# ---------------------------------------------------------------------------
@dataclass
class OutputPaths:
    """Ba nơi ghi kết quả, mỗi cái tắt được độc lập."""

    anh_dir: Path | None = None   # thư mục lưu ảnh đã chụp (None = không lưu)
    json_path: Path | None = None  # file JSON tích luỹ mọi lần đếm
    log_path: Path | None = None   # file .jsonl ghi thêm (tuỳ chọn)


@dataclass
class LoopState:
    """Toàn bộ trạng thái thay đổi trong vòng lặp camera.

    Gom lại một chỗ thay vì rải 9 biến rời rạc: nhìn vào đây là biết vòng lặp
    có những gì, và thấy được cặp nào luôn đi cùng nhau — `pending` với
    `pending_path` luôn được đặt và xoá cùng lúc (ảnh ứng với lần đếm đang chờ
    kết quả), quan hệ này trước đây chỉ nằm trong đầu người viết.
    """

    # Lần gọi API đang chờ kết quả, và ảnh tương ứng với nó.
    pending: Future[CountResult] | None = None
    pending_path: Path | None = None
    # Kết quả mới nhất đang hiển thị trên overlay.
    last_result: CountResult | None = None

    last_sent: float = 0.0        # mốc lần gọi API gần nhất, để giãn cách
    frame_index: int = 0          # tổng số khung đã đọc (chế độ frames dùng)
    run_index: int = 0            # số thứ tự lần đếm, nối tiếp file cũ
    dem_phien: int = 0            # số lần đếm của riêng phiên chạy này

    # Ảnh đang bị đóng băng trên màn hình (None = đang chạy bình thường).
    frozen_frame: np.ndarray | None = field(default=None, repr=False)
    timer_start: float = 0.0      # mốc đếm giờ của chế độ timer

    @property
    def busy(self) -> bool:
        return self.pending is not None

    @property
    def frozen(self) -> bool:
        return self.frozen_frame is not None


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


# ---------------------------------------------------------------------------
# Tham số dòng lệnh
# ---------------------------------------------------------------------------
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
    parser.add_argument("--timeout", type=float, default=defaults.timeout,
                        help="Chờ tối đa bao nhiêu giây cho một lần gọi API")
    parser.add_argument("--anh-dir", default=str(ANH_THUOC_DIR),
                        help="Thư mục lưu ảnh đã chụp")
    parser.add_argument("--no-save-anh", action="store_true",
                        help="Không lưu ảnh đã chụp (chỉ gọi API rồi bỏ ảnh đi)")
    parser.add_argument("--json-out", default=str(VLM_DIR / "ket_qua.json"),
                        help="File JSON lưu kết quả mọi lần đếm")
    parser.add_argument("--log", default="", help="Ghi thêm kết quả ra file .jsonl")
    return parser.parse_args()


def build_settings(args: argparse.Namespace) -> Settings:
    """Dòng lệnh ghi đè lên giá trị đọc từ env/api_key.json.

    Các `max(...)` ở đây là chặn dưới cho giá trị vô nghĩa (thời gian âm, số
    khung bằng 0) — giữ nguyên như bản trước, không phải kiểm tra mới.
    """
    return Settings(
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
        timeout=max(5.0, args.timeout),
    )


def prepare_paths(args: argparse.Namespace) -> OutputPaths:
    """Dựng sẵn các thư mục cần ghi, để lỗi quyền ghi lộ ra ngay lúc khởi động
    chứ không phải sau lần đếm đầu tiên."""
    paths = OutputPaths()

    if args.log:
        paths.log_path = Path(args.log).expanduser()
        paths.log_path.parent.mkdir(parents=True, exist_ok=True)

    if not args.no_save_anh:
        paths.anh_dir = Path(args.anh_dir).expanduser()
        paths.anh_dir.mkdir(parents=True, exist_ok=True)

    if args.json_out:
        paths.json_path = Path(args.json_out).expanduser()

    return paths


def create_counter(settings: Settings) -> PillCounter:
    api_key = load_api_key(settings.provider)
    try:
        return PillCounter(
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
            timeout=settings.timeout,
        )
    except BackendError as exc:
        raise SystemExit(str(exc)) from exc


def print_banner(
    counter: PillCounter, settings: Settings, paths: OutputPaths, records: list[dict]
) -> None:
    """Vài dòng giới thiệu lúc khởi động: đang dùng model nào, ghi kết quả vào
    đâu, và phải làm gì tiếp theo."""
    print(f"Model  : {counter.describe()}")
    print(f"Cấu hình: {settings.describe()}")
    print(f"Lưu ảnh: {paths.anh_dir if paths.anh_dir else 'tắt'}")
    print(f"Kết quả: {paths.json_path if paths.json_path else 'tắt'}"
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


# ---------------------------------------------------------------------------
# Các bước trong một vòng lặp
# ---------------------------------------------------------------------------
def collect_result(
    state: LoopState, paths: OutputPaths, records: list[dict], phien: str
) -> None:
    """Thu kết quả nếu lần gọi API trước đã xong, rồi in + ghi file.

    `pending.result()` ở đây không cần bọc try: `PillCounter.count` cam kết
    không bao giờ ném exception (xem docstring của nó) — mọi lỗi đều quay về
    dưới dạng `CountResult(ok=False, error=...)`.
    """
    if state.pending is None or not state.pending.done():
        return

    state.last_result = state.pending.result()
    state.pending = None
    state.run_index += 1
    state.dem_phien += 1

    print_result(state.last_result, state.run_index, state.pending_path)
    if paths.log_path:
        append_log(paths.log_path, state.last_result)
    if paths.json_path:
        records.append(
            build_record(state.last_result, state.run_index, state.pending_path, phien)
        )
        save_results_json(paths.json_path, records)
    state.pending_path = None


def handle_key(
    key: int,
    frame: np.ndarray,
    state: LoopState,
    watcher: StabilityWatcher | None,
    paths: OutputPaths,
    now: float,
) -> tuple[bool, bool]:
    """Xử lý một phím bấm. Trả về (thoát chương trình?, chụp ngay?)."""
    if key in (ord("q"), 27):
        return True, False

    force = False
    if key == ord("e"):
        # Chụp ngay, không cần chờ ổn định. Đang đóng băng thì bỏ đóng băng
        # luôn rồi chụp, khỏi phải bấm SPACE trước.
        state.frozen_frame = None
        force = True
    if key == ord(" "):
        if state.frozen:
            # Đang đóng băng -> chạy tiếp, đếm lại từ đầu.
            state.frozen_frame = None
            state.timer_start = now
            if watcher is not None:
                watcher.rearm(now)
        else:
            force = True  # đang chạy -> chụp ngay
    if key == ord("s"):
        saved = save_frame(frame, paths.anh_dir or ANH_THUOC_DIR, prefix="thucong")
        if saved:
            print(f"Đã lưu {saved}", flush=True)

    return False, force


def should_capture(
    state: LoopState, settings: Settings, watcher: StabilityWatcher | None, now: float
) -> bool:
    """Đã tới lượt chụp chưa (chưa tính tới phím bấm cưỡng bức)."""
    if state.frozen:
        return False  # đang đóng băng thì không tự chụp nữa
    if settings.trigger_mode == "timer":
        return (now - state.timer_start) >= settings.timer_seconds
    if watcher is not None:
        return watcher.ready(now)
    return state.frame_index % settings.frame_interval == 0


def is_cooled(state: LoopState, settings: Settings, now: float) -> bool:
    """Đã đủ giãn cách tối thiểu giữa 2 lần gọi API chưa.

    Ở chế độ timer chính đồng hồ đã giãn cách các lần gọi API rồi.
    """
    if settings.trigger_mode == "timer":
        return True
    return (now - state.last_sent) >= settings.min_interval_sec


class BackgroundCounter:
    """Gọi `PillCounter.count` trên luồng nền để vòng lặp camera không đứng hình.

    KHÔNG DÙNG `ThreadPoolExecutor` (sửa 2026-08-11): luồng của nó là non-daemon
    và `concurrent.futures` đăng ký sẵn một `atexit` chờ mọi luồng xong mới cho
    trình thông dịch thoát. Hậu quả: bấm Ctrl+C giữa lúc đang gọi API thì cửa sổ
    đóng, dòng "Dừng theo yêu cầu người dùng." in ra, nhưng terminal treo tiếp
    cho tới khi máy chủ trả lời. `shutdown(wait=False, cancel_futures=True)`
    không cứu được vì `cancel_futures` chỉ huỷ việc CHƯA bắt đầu.

    Luồng ở đây là daemon nên Ctrl+C trả lại dấu nhắc ngay; cuộc gọi dở dang bị
    bỏ lại và chết cùng tiến trình.

    Vẫn trả về `Future` để phần còn lại của vòng lặp không phải đổi gì. Mỗi lúc
    chỉ có một việc chạy — vòng lặp đã tự bảo đảm điều đó bằng `state.pending is
    None` trước khi gọi `submit_capture`.
    """

    def __init__(self, counter: PillCounter) -> None:
        self._counter = counter

    def submit(self, frame: np.ndarray) -> Future[CountResult]:
        future: Future[CountResult] = Future()
        future.set_running_or_notify_cancel()
        threading.Thread(
            target=self._run, args=(future, frame), name="vlm-count", daemon=True
        ).start()
        return future

    def _run(self, future: Future[CountResult], frame: np.ndarray) -> None:
        # `count()` tự hứa không ném exception, nhưng nếu lời hứa đó vỡ thì lỗi
        # phải đi được sang luồng chính — nuốt ở đây là treo `pending` vĩnh viễn.
        try:
            future.set_result(self._counter.count(frame))
        except BaseException as exc:  # noqa: BLE001
            future.set_exception(exc)


def submit_capture(
    frame: np.ndarray,
    state: LoopState,
    settings: Settings,
    watcher: StabilityWatcher | None,
    paths: OutputPaths,
    runner: BackgroundCounter,
    now: float,
) -> None:
    """Chụp khung hình hiện tại và gửi đi đếm."""
    if watcher is not None:
        watcher.consume()
    shot = frame.copy()
    state.pending_path = save_frame(shot, paths.anh_dir) if paths.anh_dir else None
    state.pending = runner.submit(shot)
    state.last_sent = now
    state.timer_start = now
    # Xoá kết quả cũ: để nguyên thì số của ảnh trước sẽ hiện đè lên ảnh mới vừa
    # chụp, rất dễ đọc nhầm.
    state.last_result = None
    if settings.wait_space:
        state.frozen_frame = shot  # giữ nguyên ảnh vừa chụp cho tới khi bấm SPACE


def render(
    frame: np.ndarray,
    state: LoopState,
    settings: Settings,
    watcher: StabilityWatcher | None,
    now: float,
) -> None:
    remaining = settings.frame_interval - (state.frame_index % settings.frame_interval)
    hien = frame if state.frozen_frame is None else state.frozen_frame
    status = status_text(
        watcher, settings, state.busy, now, remaining,
        frozen=state.frozen,
        seconds_left=settings.timer_seconds - (now - state.timer_start),
    )
    cv2.imshow(WINDOW_NAME, draw_overlay(hien, state.last_result, status, frozen=state.frozen))


# ---------------------------------------------------------------------------
# Vòng lặp chính
# ---------------------------------------------------------------------------
def run_loop(
    cap,
    counter: PillCounter,
    settings: Settings,
    watcher: StabilityWatcher | None,
    paths: OutputPaths,
    records: list[dict],
    phien: str,
    show_window: bool,
) -> int:
    """Chạy tới khi người dùng thoát. Trả về số lần đếm của phiên này."""
    runner = BackgroundCounter(counter)
    state = LoopState(
        run_index=next_run_index(records),
        timer_start=time.monotonic(),
    )

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                logger.error("Mất tín hiệu camera, dừng lại.")
                break

            state.frame_index += 1
            now = time.monotonic()
            if watcher is not None:
                watcher.update(frame, now)

            collect_result(state, paths, records, phien)

            force = False
            if show_window:
                key = cv2.waitKey(1) & 0xFF
                quit_now, force = handle_key(key, frame, state, watcher, paths, now)
                if quit_now:
                    break

            due = should_capture(state, settings, watcher, now)
            cooled = is_cooled(state, settings, now)
            if (due or force) and state.pending is None and (cooled or force):
                submit_capture(frame, state, settings, watcher, paths, runner, now)

            if show_window:
                render(frame, state, settings, watcher, now)
    except KeyboardInterrupt:
        if state.busy:
            print("\nDừng theo yêu cầu người dùng — bỏ lần đếm đang chờ máy chủ.")
        else:
            print("\nDừng theo yêu cầu người dùng.")
    finally:
        cap.release()
        if show_window:
            cv2.destroyAllWindows()
        # Không chờ luồng nền: nó là daemon, chết cùng tiến trình. Xem
        # BackgroundCounter để biết vì sao việc "chờ cho gọn gàng" lại là bug.

    return state.dem_phien


def main() -> int:
    # Chẩn đoán (không đọc được file, mất camera…) đi ra stderr; kết quả đếm
    # vẫn dùng print() vì đó là giao diện của chương trình, không phải log.
    logging.basicConfig(
        level=logging.WARNING, format="[%(levelname)s] %(message)s", stream=sys.stderr
    )

    args = parse_args()
    settings = build_settings(args)
    counter = create_counter(settings)
    paths = prepare_paths(args)

    # Nạp kết quả những lần chạy trước rồi ghi tiếp, không bắt đầu lại từ đầu.
    records: list[dict] = load_results_json(paths.json_path) if paths.json_path else []
    phien = time.strftime("%Y-%m-%d %H:%M:%S")

    cap = open_camera(settings)
    show_window = not args.no_window

    # Không có cửa sổ thì không nhận được phím -> chờ SPACE sẽ treo vĩnh viễn.
    if settings.wait_space and not show_window:
        logger.warning(
            "Không có cửa sổ nên không bấm được SPACE — tự chuyển sang chạy liên tục."
        )
        settings.wait_space = False

    print_banner(counter, settings, paths, records)

    watcher = (
        StabilityWatcher(settings.motion_threshold, settings.stable_seconds)
        if settings.trigger_mode == "stable"
        else None
    )

    dem_phien = run_loop(
        cap, counter, settings, watcher, paths, records, phien, show_window
    )

    print(f"Lần chạy này: {dem_phien} lần đếm.")
    if paths.json_path and records:
        print(f"Tổng cộng {len(records)} lần đếm trong {paths.json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
