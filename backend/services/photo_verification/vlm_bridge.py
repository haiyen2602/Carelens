"""
Gọi mô hình thị giác để đếm thuốc trong một ảnh — bản dùng ở tầng backend.

TRÙNG LẶP CÓ CHỦ ĐÍCH với `backend/vlm_demthuoc/providers.py` (lớp
`OpenAICompatBackend`) và phần bóc JSON trong `vlm_client.py`, cùng lý do đã
ghi ở `count_keys.py`/`vlm_prompts.py`: `.railwayignore` loại cả thư mục
`vlm_demthuoc/` khỏi gói upload lên Railway.

KHÁC BẢN GỐC MỘT ĐIỂM QUAN TRỌNG: không dùng `cv2`/`numpy`. Bản gốc cần chúng
để đọc khung hình webcam và resize trước khi mã hoá JPEG. Ở đây, ảnh đã là
JPEG hoàn chỉnh do trình duyệt/điện thoại gửi lên qua `UploadFile` — chỉ cần
mã hoá base64, không cần giải mã lại thành mảng pixel để resize. Đây là lý do
domain này không cần cài `opencv` (~60MB) lên server.

Đọc cấu hình qua `backend.config.get_settings()` (pydantic-settings), KHÔNG
qua `backend/vlm_demthuoc/config.py` — hàm đó đọc `os.environ` + `api_key.json`
+ hỏi người dùng qua `getpass`, hợp với CLI chạy dưới máy, không hợp với server
(không thể "hỏi người dùng" giữa lúc đang xử lý một request HTTP).

Logic thử lại khi phản hồi rỗng (`_goi_co_thu_lai`) và bóc nội dung từ SSE giả
(`gom_sse`) được PORT LẠI Y NGUYÊN từ bản gốc — đây là kết quả một buổi debug
thật trên api.vilao.ai (đo được: hỏng ~50% số lần gọi, mỗi lần hỏng gần như
tức thì, 5 lần thử cho ~97% thành công). Viết lại từ đầu sẽ phải khám phá lại
đúng những lỗi đó.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from backend.config import Settings, get_settings
from backend.services.photo_verification.count_keys import (
    CONFIDENCE_LEVELS,
    COUNT_KEYS,
    NON_DRUG_KEY,
)
from backend.services.photo_verification.vlm_prompts import (
    RESULT_SCHEMA,
    USER_PROMPT,
    build_system_prompt,
)

logger = logging.getLogger(__name__)

# Chặn trên dung lượng ảnh nhận vào — không resize được (không có cv2), nên
# chặn ở lối vào thay vì gửi nguyên một ảnh chụp gốc 20MB tới model, tốn tiền
# và tăng khả năng chạm giới hạn của nhà cung cấp.
MAX_ANH_BYTES = 8 * 1024 * 1024  # 8MB — dư sức cho ảnh JPEG từ điện thoại


class VlmBridgeError(RuntimeError):
    """Lỗi đã diễn giải thành thông báo tiếng Việt cho tầng gọi."""


@dataclass(frozen=True)
class KetQuaDemVlm:
    """Kết quả một lần gọi mô hình đếm thuốc."""

    ok: bool
    counts: dict[str, int] = field(default_factory=lambda: dict.fromkeys(COUNT_KEYS, 0))
    khong_phai_thuoc: int = 0
    do_tin_cay: str = "thap"
    ghi_chu: str = ""
    error: str = ""
    latency_sec: float = 0.0

    @property
    def tong_vien(self) -> int:
        return self.counts["vien_nang"] + self.counts["vien_nen"]


# ---------------------------------------------------------------------------
# Bóc nội dung từ luồng SSE giả — xem BackendError trong bản gốc.
# ---------------------------------------------------------------------------
def _gom_sse(raw: str) -> tuple[str, str]:
    """Gom nội dung từ một body Server-Sent Events. Trả (nội_dung, lỗi)."""
    parts: list[str] = []
    loi = ""
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("error"):
            loi = str(obj["error"].get("message") or obj["error"])
        for choice in obj.get("choices") or []:
            piece = (choice.get("delta") or {}).get("content") or (
                choice.get("message") or {}
            ).get("content")
            if piece:
                parts.append(piece)

    noi_dung = "".join(parts)
    if noi_dung:
        return noi_dung, ""
    if loi:
        return "", loi
    if parts or "data:" in raw:
        return "", "máy chủ trả về luồng SSE rỗng (model không sinh ra chữ nào)"
    return "", f"phản hồi không đọc được: {raw[:150]}"


def _doc_phan_hoi(response: Any) -> tuple[str, str]:
    """Bóc nội dung từ phản hồi. Trả (nội_dung, lỗi).

    Ba kiểu phản hồi hỏng gặp trên endpoint tương thích OpenAI, đều kèm HTTP
    200 nên SDK không hề ném exception — xem `gom_sse`.
    """
    if isinstance(response, str):
        return _gom_sse(response)

    choices = getattr(response, "choices", None)
    if not choices:
        extra = getattr(response, "model_extra", None) or {}
        loi = extra.get("error")
        if isinstance(loi, dict):
            return "", str(loi.get("message") or loi)
        if loi:
            return "", str(loi)
        return "", "máy chủ trả về phản hồi không có choices"

    choice = choices[0]
    if getattr(choice, "finish_reason", "") == "length":
        return "", "__MAX_TOKENS__"
    return (getattr(choice.message, "content", "") or ""), ""


# ---------------------------------------------------------------------------
# Bóc JSON ra khỏi văn bản model trả về.
# ---------------------------------------------------------------------------
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _extract_json(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if not candidate:
        raise ValueError("Model trả về chuỗi rỗng.")

    fenced = _FENCE_RE.search(candidate)
    if fenced:
        candidate = fenced.group(1).strip()

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        parsed = _first_json_object(candidate)

    if not isinstance(parsed, dict):
        raise ValueError("JSON trả về không phải object.")
    return parsed


def _first_json_object(text: str) -> Any:
    start = text.find("{")
    if start == -1:
        raise ValueError(f"Không tìm thấy JSON trong: {text[:200]!r}")

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : index + 1])

    raise ValueError(f"JSON bị thiếu dấu đóng ngoặc: {text[:200]!r}")


def _to_count(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        try:
            number = int(float(str(value).strip()))
        except (TypeError, ValueError):
            number = 0
    return max(0, number)


def _coerce(payload: dict[str, Any]) -> tuple[dict[str, int], int, str, str]:
    counts = {key: _to_count(payload.get(key, 0)) for key in COUNT_KEYS}
    non_drug = _to_count(payload.get(NON_DRUG_KEY, 0))

    confidence = str(payload.get("do_tin_cay", "")).strip().lower().replace(" ", "_")
    if confidence not in CONFIDENCE_LEVELS:
        confidence = "thap"

    note = str(payload.get("ghi_chu", "")).strip()
    return counts, non_drug, confidence, note


# ---------------------------------------------------------------------------
# Gọi endpoint tương thích OpenAI, thử lại khi phản hồi rỗng.
# ---------------------------------------------------------------------------
# CHI cac dau hieu chac chan noi ve response_format. TRUOC 2026-08-26 danh
# sach nay con co "not supported"/"unsupported"/"unknown parameter" chung
# chung, nen MOI loi 400 ve tham so KHAC cung bi hieu nham thanh "endpoint
# khong ho tro JSON mode" va lam thang hu cap schema->object->off - dot 3
# lan goi API cho mot van de khong lien quan (bat duoc that khi doi sang
# gpt-5.4-mini: loi that la "max_tokens is not supported", xem _MAX_TOKENS_KEYS).
_UNSUPPORTED_HINTS = ("response_format", "json_schema")

# gpt-5.x doi `max_completion_tokens`; cac model/endpoint cu (gpt-4o,
# api.vilao.ai) chi hieu `max_tokens`. Khong hardcode mot ben nao: thu ben
# mac dinh truoc, thay ten khi endpoint bao sai, de doi model qua lai giua
# hai the he ma khong phai sua code.
_MAX_TOKENS_KEYS = ("max_tokens", "max_completion_tokens")

# Ten tham so DA DO DUOC cho tung model, nho o muc MODULE chu khong phai
# instance: dem_thuoc_trong_anh() dung mot _OpenAICompatCaller MOI cho moi
# anh, nen nho o instance thi moi anh deu phai dam mot lan goi 400 roi moi
# doi ten - dung 25 lan goi thua trong mot lan chay golden set (do duoc
# 2026-08-26). Khoa theo ten model de doi model van tu do lai tu dau.
_MAX_TOKENS_KEY_DA_BIET: dict[str, str] = {}


class _OpenAICompatCaller:
    def __init__(self, settings: Settings) -> None:
        import openai  # đã có sẵn trong requirements.txt gốc, dùng chung với chatbot

        if not settings.vlm_model:
            raise VlmBridgeError("Chưa cấu hình VLM_MODEL trong .env.")

        self._openai = openai
        self.client = openai.OpenAI(
            api_key=settings.vlm_api_key or "not-needed",
            base_url=settings.vlm_base_url or None,
            timeout=settings.vlm_timeout,
            # max_retries=0: SDK openai mặc định tự thử lại 2 lần khi quá giờ,
            # âm thầm nhân thời gian chờ lên gấp 3. Tắt để chỉ còn MỘT cơ chế
            # thử lại — _goi_co_thu_lai bên dưới, viết đúng cho kiểu hỏng của
            # endpoint này (trả rỗng gần như tức thì, không phải quá giờ).
            max_retries=0,
        )
        self.model = settings.vlm_model
        self.json_mode = settings.vlm_json_mode
        self.retries = settings.vlm_retries
        self.retry_delay = settings.vlm_retry_delay
        # Ten tham so gioi han do dai tra loi - tu doi khi endpoint tu choi
        # (xem _MAX_TOKENS_KEYS). Doc tu cache muc module de chi phai do MOT
        # lan cho moi model, khong phai moi anh.
        self.max_tokens_key = _MAX_TOKENS_KEY_DA_BIET.get(self.model, _MAX_TOKENS_KEYS[0])

    def dem(self, image_b64: str) -> KetQuaDemVlm:
        started = time.monotonic()
        openai = self._openai
        user_content = [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
            {"type": "text", "text": USER_PROMPT},
        ]

        ladder = ["schema", "object", "off"]
        attempts = ladder[ladder.index(self.json_mode):]
        last_error = ""

        for mode in attempts:
            messages = [
                {"role": "system", "content": build_system_prompt(True, mode != "schema")},
                {"role": "user", "content": user_content},
            ]
            kwargs: dict[str, Any] = {"model": self.model, "messages": messages, self.max_tokens_key: 4000}
            response_format = self._response_format(mode)
            if response_format is not None:
                kwargs["response_format"] = response_format

            try:
                response = self._goi_co_thu_lai(kwargs)
            except openai.AuthenticationError as exc:
                return _loi(started, f"API key không hợp lệ với endpoint VLM: {exc}")
            except openai.NotFoundError as exc:
                return _loi(started, f"Không tìm thấy model '{self.model}': {exc}")
            except openai.RateLimitError as exc:
                return _loi(started, f"Bị giới hạn tốc độ (429): {exc}")
            except openai.BadRequestError as exc:
                message = str(getattr(exc, "message", "") or exc)
                if mode != "off" and self._looks_unsupported(message):
                    last_error = message
                    self.json_mode = ladder[ladder.index(mode) + 1]
                    logger.warning(
                        "Endpoint VLM không hỗ trợ json_mode=%r (%s). Chuyển sang %r.",
                        mode, message[:120], self.json_mode,
                    )
                    continue
                return _loi(started, f"Yêu cầu bị từ chối (400): {message}")
            except openai.APIStatusError as exc:
                return _loi(started, f"Lỗi API VLM {exc.status_code}: {exc}")
            except openai.APIConnectionError as exc:
                return _loi(started, f"Không kết nối được tới endpoint VLM: {exc}")

            text, loi = _doc_phan_hoi(response)
            if loi == "__MAX_TOKENS__":
                return _loi(started, "Trả lời bị cắt do hết max_tokens.")
            if not text:
                return _loi(started, f"Máy chủ VLM trả về phản hồi rỗng sau {self.retries} lần thử: {loi}")

            latency = time.monotonic() - started
            try:
                payload = _extract_json(text)
            except ValueError as exc:
                return _loi(started, f"Không đọc được JSON từ model: {exc}", latency)

            counts, non_drug, confidence, note = _coerce(payload)
            return KetQuaDemVlm(
                ok=True, counts=counts, khong_phai_thuoc=non_drug,
                do_tin_cay=confidence, ghi_chu=note, latency_sec=latency,
            )

        return _loi(started, f"Không chế độ JSON nào dùng được với endpoint VLM. Lỗi cuối: {last_error}")

    def _response_format(self, mode: str) -> dict[str, Any] | None:
        if mode == "schema":
            return {"type": "json_schema", "json_schema": {
                "name": "ket_qua_dem_thuoc", "strict": True, "schema": RESULT_SCHEMA,
            }}
        if mode == "object":
            return {"type": "json_object"}
        return None

    def _looks_unsupported(self, message: str) -> bool:
        lowered = message.lower()
        return any(hint in lowered for hint in _UNSUPPORTED_HINTS)

    def _doi_ten_max_tokens(self, kwargs: dict[str, Any], message: str) -> bool:
        """Đổi `max_tokens` ⇄ `max_completion_tokens` khi endpoint từ chối tên đang dùng.

        Trả về True nếu đã đổi (người gọi nên thử lại), False nếu lỗi 400 này
        không phải về tên tham số đó — lúc ấy đừng nuốt, để nó nổi lên."""
        lowered = message.lower()
        if "max_tokens" not in lowered and "max_completion_tokens" not in lowered:
            return False
        ten_cu = self.max_tokens_key
        ten_moi = next((k for k in _MAX_TOKENS_KEYS if k != ten_cu), None)
        if ten_moi is None or ten_cu not in kwargs:
            return False
        kwargs[ten_moi] = kwargs.pop(ten_cu)
        self.max_tokens_key = ten_moi
        _MAX_TOKENS_KEY_DA_BIET[self.model] = ten_moi
        logger.warning(
            "Endpoint VLM không nhận %r (%s). Chuyển sang %r.",
            ten_cu, message[:120], ten_moi,
        )
        return True

    def _goi_co_thu_lai(self, kwargs: dict[str, Any]) -> Any:
        """Gọi API, thử lại khi phản hồi rỗng/không parse được — xem docstring module."""
        cuoi_cung: Any = None
        da_doi_ten = False
        for lan in range(1, self.retries + 1):
            try:
                cuoi_cung = self.client.chat.completions.create(**kwargs)
            except self._openai.BadRequestError as exc:
                # Sai TÊN tham số giới hạn độ dài (gpt-5.x vs model cũ) —
                # đổi tên rồi thử lại NGAY, không tính vào hạn mức thử lại
                # vì lần gọi vừa rồi hỏng vì cấu hình, không phải vì endpoint.
                message = str(getattr(exc, "message", "") or exc)
                if not da_doi_ten and self._doi_ten_max_tokens(kwargs, message):
                    da_doi_ten = True
                    cuoi_cung = self.client.chat.completions.create(**kwargs)
                    text, loi = _doc_phan_hoi(cuoi_cung)
                    if text or loi == "__MAX_TOKENS__":
                        return cuoi_cung
                else:
                    raise
            except json.JSONDecodeError as exc:
                cuoi_cung = None
                loi = f"body không phải JSON ({exc})"
            else:
                text, loi = _doc_phan_hoi(cuoi_cung)
                if text or loi == "__MAX_TOKENS__":
                    return cuoi_cung

            if lan < self.retries:
                logger.info("Lần %d/%d gọi VLM hỏng (%s). Thử lại...", lan, self.retries, loi)
                time.sleep(self.retry_delay)

        if cuoi_cung is None:
            raise VlmBridgeError(
                f"Máy chủ VLM trả về body không đọc được sau {self.retries} lần thử."
            )
        return cuoi_cung


def _loi(started: float, thong_diep: str, latency: float | None = None) -> KetQuaDemVlm:
    logger.warning("Đếm thuốc bằng VLM thất bại: %s", thong_diep)
    return KetQuaDemVlm(
        ok=False, error=thong_diep, latency_sec=latency if latency is not None else time.monotonic() - started
    )


# ---------------------------------------------------------------------------
# Cửa vào công khai của module.
# ---------------------------------------------------------------------------
def dem_thuoc_trong_anh(image_bytes: bytes, settings: Settings | None = None) -> KetQuaDemVlm:
    """Đếm thuốc trong một ảnh JPEG. Không bao giờ ném exception ra ngoài —
    lỗi mạng/model đều gói vào `KetQuaDemVlm(ok=False, error=...)`, để tầng
    gọi (verifier.py, GĐ8) không phải bọc try/except riêng cho từng loại lỗi.

    `image_bytes` là JPEG THÔ, không phải mảng pixel — không resize (không có
    cv2 ở tầng backend), chỉ chặn trên dung lượng ở MAX_ANH_BYTES.
    """
    started = time.monotonic()
    if not image_bytes:
        return _loi(started, "Ảnh gửi lên rỗng.")
    if len(image_bytes) > MAX_ANH_BYTES:
        return _loi(started, f"Ảnh quá lớn ({len(image_bytes) // 1024}KB > {MAX_ANH_BYTES // 1024}KB).")

    settings = settings or get_settings()
    if settings.vlm_provider != "openai":
        return _loi(
            started,
            f"Nhà cung cấp VLM {settings.vlm_provider!r} chưa được hỗ trợ ở tầng server "
            "(chỉ mới cài 'openai'-compatible, dùng cho api.vilao.ai).",
        )

    image_b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    try:
        caller = _OpenAICompatCaller(settings)
    except VlmBridgeError as exc:
        return _loi(started, str(exc))
    except Exception as exc:  # noqa: BLE001 - lỗi khởi tạo SDK, không để văng ra request HTTP
        return _loi(started, f"Không khởi tạo được client VLM: {exc}")

    try:
        return caller.dem(image_b64)
    except Exception as exc:  # noqa: BLE001 - không để một request ảnh làm chết luồng gọi
        return _loi(started, f"Lỗi không lường trước ({type(exc).__name__}): {exc}")


__all__ = ["MAX_ANH_BYTES", "KetQuaDemVlm", "VlmBridgeError", "dem_thuoc_trong_anh"]
