# -*- coding: utf-8 -*-
"""
Đếm thuốc trong một khung hình bằng VLM.

File này lo phần dùng chung cho mọi nhà cung cấp: mã hoá ảnh, JSON schema, bóc
và làm sạch JSON trả về. Việc gọi API cụ thể nằm ở `providers.py`.
"""

from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from prompts import (
    CONFIDENCE_LEVELS,
    COUNT_KEYS,
    NON_DRUG_KEY,
    USER_PROMPT,
    build_system_prompt,
)
from providers import BackendError, create_backend

# ---------------------------------------------------------------------------
# JSON schema — phải khớp với mô tả trong system prompt.
# Lưu ý: structured outputs không hỗ trợ minimum/maximum/maxLength, nên giới hạn
# giá trị được diễn đạt trong prompt và kiểm tra lại ở phía client.
# ---------------------------------------------------------------------------
RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "vien_nang": {"type": "integer", "description": "Số viên nang (capsule)"},
        "vien_nen": {"type": "integer", "description": "Số viên nén (tablet)"},
        "tuyp_thuoc": {"type": "integer", "description": "Số tuýp thuốc bôi"},
        "lo_thuoc": {"type": "integer", "description": "Số chai/lọ thuốc"},
        "hop_thuoc": {"type": "integer", "description": "Số hộp giấy/carton"},
        "goi_thuoc": {
            "type": "integer",
            "description": "Số gói thuốc bột/cốm/sủi (sachet), bao bì mềm hàn kín mép",
        },
        NON_DRUG_KEY: {
            "type": "integer",
            "description": (
                "Số vật thể trông giống viên thuốc nhưng KHÔNG phải thuốc: kẹo cao su "
                "xylitol, kẹo bạc hà, kẹo ngậm, kẹo dẻo. Không cộng vào các trường trên."
            ),
        },
        "do_tin_cay": {
            "type": "string",
            "enum": list(CONFIDENCE_LEVELS),
            "description": "Mức độ tin cậy của kết quả đếm",
        },
        "ghi_chu": {
            "type": "string",
            "description": "Mô tả ngắn bằng tiếng Việt về tình trạng ảnh",
        },
    },
    "required": [*COUNT_KEYS, NON_DRUG_KEY, "do_tin_cay", "ghi_chu"],
    "additionalProperties": False,
}

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


@dataclass
class CountResult:
    """Kết quả một lần đếm."""

    ok: bool
    counts: dict[str, int] = field(default_factory=lambda: {k: 0 for k in COUNT_KEYS})
    # Kẹo / thực phẩm bị nhận nhầm thành thuốc. Tách riêng khỏi `counts` để không
    # bao giờ lọt vào tổng số viên.
    khong_phai_thuoc: int = 0
    do_tin_cay: str = "thap"
    ghi_chu: str = ""
    error: str = ""
    latency_sec: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    timestamp: float = field(default_factory=time.time)

    @property
    def total_pills(self) -> int:
        return self.counts["vien_nang"] + self.counts["vien_nen"]

    @property
    def total_objects(self) -> int:
        return sum(self.counts.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.counts,
            NON_DRUG_KEY: self.khong_phai_thuoc,
            "do_tin_cay": self.do_tin_cay,
            "ghi_chu": self.ghi_chu,
            "tong_vien": self.total_pills,
            "thoi_gian": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.timestamp)),
            "latency_sec": round(self.latency_sec, 2),
        }


def encode_frame(frame: np.ndarray, max_edge: int, jpeg_quality: int) -> str:
    """Thu nhỏ (nếu cần) và mã hoá khung hình BGR thành JPEG base64."""
    height, width = frame.shape[:2]
    longest = max(height, width)
    if longest > max_edge:
        scale = max_edge / float(longest)
        frame = cv2.resize(
            frame,
            (max(1, int(width * scale)), max(1, int(height * scale))),
            interpolation=cv2.INTER_AREA,
        )

    ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
    if not ok:
        raise ValueError("Không mã hoá được khung hình sang JPEG.")
    return base64.standard_b64encode(buffer.tobytes()).decode("ascii")


def extract_json(text: str) -> dict[str, Any]:
    """Bóc object JSON ra khỏi văn bản model trả về.

    Cần thiết khi nhà cung cấp không ép được schema: lúc đó model hay bọc JSON
    trong ```json ... ``` hoặc thêm câu dẫn phía trước.
    """
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
    """Tìm object JSON cân bằng ngoặc đầu tiên trong chuỗi."""
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
    """Ép một giá trị bất kỳ về số nguyên không âm."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        try:  # một số model trả "3.0" hoặc " 3 "
            number = int(float(str(value).strip()))
        except (TypeError, ValueError):
            number = 0
    return max(0, number)


def _coerce(payload: dict[str, Any]) -> tuple[dict[str, int], int, str, str]:
    """Ép kiểu / vệ sinh dữ liệu model trả về (phòng trường hợp bất thường)."""
    counts = {key: _to_count(payload.get(key, 0)) for key in COUNT_KEYS}
    non_drug = _to_count(payload.get(NON_DRUG_KEY, 0))

    confidence = str(payload.get("do_tin_cay", "")).strip().lower().replace(" ", "_")
    if confidence not in CONFIDENCE_LEVELS:
        confidence = "thap"

    note = str(payload.get("ghi_chu", "")).strip()
    return counts, non_drug, confidence, note


class PillCounter:
    """Bọc backend + prompt + schema thành một hàm `count(frame)`."""

    def __init__(
        self,
        api_key: str,
        provider: str = "claude",
        model: str = "claude-opus-5",
        base_url: str = "",
        json_mode: str = "schema",
        effort: str = "medium",
        max_tokens: int = 4000,
        max_image_edge: int = 1600,
        jpeg_quality: int = 90,
        count_pills_in_blister: bool = True,
        timeout: float = 120.0,
        retries: int = 5,
    ) -> None:
        self.backend = create_backend(
            provider,
            api_key=api_key,
            model=model,
            schema=RESULT_SCHEMA,
            base_url=base_url,
            json_mode=json_mode,
            effort=effort,
            max_tokens=max_tokens,
            timeout=timeout,
            retries=retries,
        )
        self.max_image_edge = max_image_edge
        self.jpeg_quality = jpeg_quality
        self.count_pills_in_blister = count_pills_in_blister
        self._system_cache: dict[bool, str] = {}

    def build_system(self, enforce_json_in_prompt: bool) -> str:
        """Dựng system prompt (có cache). Backend gọi hàm này khi cần."""
        if enforce_json_in_prompt not in self._system_cache:
            self._system_cache[enforce_json_in_prompt] = build_system_prompt(
                self.count_pills_in_blister,
                enforce_json_in_prompt=enforce_json_in_prompt,
            )
        return self._system_cache[enforce_json_in_prompt]

    def describe(self) -> str:
        return self.backend.describe()

    def count(self, frame: np.ndarray) -> CountResult:
        """Đếm thuốc trong một khung hình BGR. Không bao giờ ném exception."""
        started = time.monotonic()
        try:
            image_b64 = encode_frame(frame, self.max_image_edge, self.jpeg_quality)
        except Exception as exc:  # noqa: BLE001 - lỗi mã hoá ảnh, báo lại là đủ
            return CountResult(ok=False, error=f"Lỗi mã hoá ảnh: {exc}")

        try:
            completion = self.backend.complete(image_b64, self.build_system, USER_PROMPT)
        except BackendError as exc:
            return CountResult(ok=False, error=str(exc), latency_sec=time.monotonic() - started)
        except Exception as exc:  # noqa: BLE001 - không để vòng lặp camera chết
            return CountResult(
                ok=False,
                error=f"Lỗi không lường trước ({type(exc).__name__}): {exc}",
                latency_sec=time.monotonic() - started,
            )

        latency = time.monotonic() - started
        try:
            payload = extract_json(completion.text)
        except ValueError as exc:
            return CountResult(ok=False, error=f"Không đọc được JSON: {exc}", latency_sec=latency)

        counts, non_drug, confidence, note = _coerce(payload)
        return CountResult(
            ok=True,
            counts=counts,
            khong_phai_thuoc=non_drug,
            do_tin_cay=confidence,
            ghi_chu=note,
            latency_sec=latency,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
            cache_read_tokens=completion.cache_read_tokens,
        )
