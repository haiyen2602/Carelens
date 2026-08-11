# -*- coding: utf-8 -*-
"""
Lớp trung gian giữa chương trình và các nhà cung cấp model khác nhau.

Hai backend:
    - ClaudeBackend        : SDK `anthropic`, ép JSON bằng structured outputs.
    - OpenAICompatBackend  : SDK `openai`, dùng được với mọi endpoint tương thích
                             OpenAI (OpenRouter, Groq, Together, Ollama,
                             LM Studio, vLLM, và cả OpenAI gốc).

Phần prompt, JSON schema, logic đếm và vòng lặp camera dùng chung, không phụ
thuộc nhà cung cấp.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable

#: Hàm dựng system prompt. Tham số bool = "có nối thêm khối ép định dạng JSON
#: hay không". Backend tự quyết định vì chỉ nó biết đang dùng chế độ JSON nào —
#: kể cả sau khi đã tự hạ cấp giữa chừng.
SystemPromptBuilder = Callable[[bool], str]

# Base URL viết tắt cho các dịch vụ hay dùng. `--base-url` nhận cả tên viết tắt
# lẫn URL đầy đủ.
BASE_URL_PRESETS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    # Google AI Studio (Gemini) qua lớp tương thích OpenAI.
    # Dấu "/" cuối là bắt buộc, thiếu nó SDK sẽ ghép sai đường dẫn.
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "aistudio": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "ollama": "http://localhost:11434/v1",
    "lmstudio": "http://localhost:1234/v1",
}


def resolve_base_url(value: str) -> str:
    """Đổi tên viết tắt thành URL đầy đủ; URL đầy đủ thì giữ nguyên."""
    value = value.strip()
    return BASE_URL_PRESETS.get(value.lower(), value)


class BackendError(RuntimeError):
    """Lỗi đã được diễn giải thành thông báo tiếng Việt cho người dùng."""


def gom_sse(raw: str) -> tuple[str, str]:
    """Gom nội dung từ một body Server-Sent Events.

    Có endpoint (api.vilao.ai) trả về luồng SSE ngay cả khi không yêu cầu
    stream, và đặt sai luôn header content-type. Lúc đó SDK openai không parse
    được nên trả lại chuỗi thô — hàm này bóc nội dung ra.

    Trả về (nội_dung, thông_báo_lỗi). Nội dung rỗng nghĩa là lần sinh đó hỏng.
    """
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


@dataclass
class Completion:
    """Kết quả thô từ model, trước khi phân tích JSON."""

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    json_mode_used: str = ""


# ---------------------------------------------------------------------------
# Claude
# ---------------------------------------------------------------------------
class ClaudeBackend:
    """Gọi Claude qua SDK `anthropic`. Luôn ép JSON bằng structured outputs."""

    name = "claude"

    def __init__(
        self,
        api_key: str,
        model: str,
        schema: dict[str, Any],
        effort: str = "medium",
        max_tokens: int = 4000,
        timeout: float = 120.0,
        base_url: str = "",
        **_ignored: Any,
    ) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise BackendError("Chưa cài SDK: pip install anthropic") from exc

        self._anthropic = anthropic
        kwargs: dict[str, Any] = {"api_key": api_key, "timeout": timeout}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = anthropic.Anthropic(**kwargs)
        self.model = model
        self.schema = schema
        self.effort = effort.strip()
        self.max_tokens = max_tokens

    def describe(self) -> str:
        return f"claude · {self.model} · effort={self.effort or 'mặc định'} · json=schema"

    def complete(
        self, image_b64: str, build_system: SystemPromptBuilder, user: str
    ) -> Completion:
        output_config: dict[str, Any] = {
            "format": {"type": "json_schema", "schema": self.schema}
        }
        if self.effort:
            output_config["effort"] = self.effort

        # API đã ép schema ở mức giao thức -> không cần nhắc định dạng trong prompt.
        system = build_system(False)
        anthropic = self._anthropic
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                # cache_control: system prompt không đổi giữa các khung hình
                system=[
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                output_config=output_config,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": image_b64,
                                },
                            },
                            {"type": "text", "text": user},
                        ],
                    }
                ],
            )
        except anthropic.AuthenticationError as exc:
            raise BackendError("API key không hợp lệ hoặc đã bị thu hồi.") from exc
        except anthropic.NotFoundError as exc:
            raise BackendError(f"Không tìm thấy model '{self.model}'.") from exc
        except anthropic.RateLimitError as exc:
            raise BackendError(
                "Bị giới hạn tốc độ (429). Tăng --min-interval lên."
            ) from exc
        except anthropic.APIStatusError as exc:
            raise BackendError(f"Lỗi API {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise BackendError("Lỗi kết nối mạng tới API.") from exc

        if response.stop_reason == "refusal":
            raise BackendError("Model từ chối xử lý ảnh này (safety refusal).")
        if response.stop_reason == "max_tokens":
            raise BackendError("Trả lời bị cắt do hết max_tokens — tăng VLM_MAX_TOKENS.")

        usage = response.usage
        return Completion(
            text=next((b.text for b in response.content if b.type == "text"), ""),
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            json_mode_used="schema",
        )


# ---------------------------------------------------------------------------
# OpenAI-compatible
# ---------------------------------------------------------------------------
class OpenAICompatBackend:
    """Gọi bất kỳ endpoint nào tương thích Chat Completions của OpenAI.

    Mức độ hỗ trợ ép JSON rất khác nhau giữa các nhà cung cấp, nên có 3 chế độ,
    tự động tụt xuống mức thấp hơn khi máy chủ báo không hỗ trợ:

        schema : response_format = json_schema (chặt nhất, giống Claude)
        object : response_format = json_object (chỉ bảo đảm "là JSON")
        off    : không ép gì, tự bóc JSON ra khỏi văn bản trả về

    Ở mức `object` và `off`, system prompt được nối thêm khối ép định dạng
    (`enforce_json_in_prompt`) vì lúc này chỉ còn prompt để dựa vào.
    """

    name = "openai"

    #: Chuỗi xuất hiện trong thông báo lỗi khi máy chủ không hỗ trợ response_format
    _UNSUPPORTED_HINTS = (
        "response_format",
        "json_schema",
        "not supported",
        "unsupported",
        "unrecognized",
        "unknown parameter",
        "invalid_type",
    )

    def __init__(
        self,
        api_key: str,
        model: str,
        schema: dict[str, Any],
        base_url: str = "",
        json_mode: str = "schema",
        max_tokens: int = 4000,
        timeout: float = 120.0,
        retries: int = 5,
        retry_delay: float = 1.5,
        **_ignored: Any,
    ) -> None:
        try:
            import openai
        except ImportError as exc:
            raise BackendError("Chưa cài SDK: pip install openai") from exc

        if not model:
            raise BackendError(
                "Chưa chọn model. Endpoint tương thích OpenAI không có model mặc định.\n"
                '  Đặt "model" trong api_key.json, hoặc chạy với --model <tên-model>.\n'
                "  Model phải hỗ trợ ảnh (vision), model chỉ đọc văn bản sẽ không dùng được."
            )

        self._openai = openai
        self.base_url = resolve_base_url(base_url)
        self.client = openai.OpenAI(
            api_key=api_key or "not-needed",  # server local thường không cần key
            base_url=self.base_url or None,
            timeout=timeout,
        )
        self.model = model
        self.schema = schema
        self.json_mode = json_mode if json_mode in ("schema", "object", "off") else "schema"
        self.max_tokens = max_tokens
        self.retries = max(1, retries)
        self.retry_delay = max(0.0, retry_delay)

    def describe(self) -> str:
        where = self.base_url or "api mặc định của SDK"
        return (f"openai-compat · {self.model} · {where} · json={self.json_mode}"
                f" · thử lại {self.retries} lần")

    @staticmethod
    def _doc_phan_hoi(response: Any) -> tuple[str, str]:
        """Bóc nội dung từ phản hồi. Trả về (nội_dung, thông_báo_lỗi).

        Ba kiểu phản hồi hỏng gặp trên endpoint tương thích OpenAI, đều kèm mã
        HTTP 200 nên SDK không hề ném exception:
          - body là luồng SSE  -> SDK trả lại chuỗi thô
          - body là {"error": ...} -> ChatCompletion không có choices
          - choices rỗng
        """
        if isinstance(response, str):  # SDK không parse được -> chuỗi thô
            return gom_sse(response)

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

    def _response_format(self, mode: str) -> dict[str, Any] | None:
        if mode == "schema":
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": "ket_qua_dem_thuoc",
                    "strict": True,
                    "schema": self.schema,
                },
            }
        if mode == "object":
            return {"type": "json_object"}
        return None

    def _looks_unsupported(self, message: str) -> bool:
        lowered = message.lower()
        return any(hint in lowered for hint in self._UNSUPPORTED_HINTS)

    def complete(
        self, image_b64: str, build_system: SystemPromptBuilder, user: str
    ) -> Completion:
        openai = self._openai
        user_content = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
            },
            {"type": "text", "text": user},
        ]

        # Thử chế độ hiện tại, tụt dần nếu máy chủ không hỗ trợ.
        ladder = ["schema", "object", "off"]
        attempts = ladder[ladder.index(self.json_mode):]
        last_error = ""

        for mode in attempts:
            # Dựng lại prompt theo đúng chế độ đang thử: chỉ "schema" mới được
            # API bảo đảm, hai chế độ còn lại phải nhờ prompt ép định dạng.
            messages = [
                {"role": "system", "content": build_system(mode != "schema")},
                {"role": "user", "content": user_content},
            ]
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "max_tokens": self.max_tokens,
            }
            response_format = self._response_format(mode)
            if response_format is not None:
                kwargs["response_format"] = response_format

            try:
                response = self._goi_co_thu_lai(kwargs)
            except openai.AuthenticationError as exc:
                raise BackendError(
                    "API key không hợp lệ với endpoint này. Kiểm tra lại key và base_url."
                ) from exc
            except openai.NotFoundError as exc:
                raise BackendError(
                    f"Không tìm thấy model '{self.model}' tại {self.base_url or 'endpoint'}. "
                    "Kiểm tra lại tên model."
                ) from exc
            except openai.RateLimitError as exc:
                raise BackendError(
                    "Bị giới hạn tốc độ (429). Tăng --min-interval lên."
                ) from exc
            except openai.BadRequestError as exc:
                message = str(getattr(exc, "message", "") or exc)
                if mode != "off" and self._looks_unsupported(message):
                    last_error = message
                    # Máy chủ không hỗ trợ mức này -> hạ xuống mức sau và nhớ lại,
                    # để những lần gọi sau không phải thử lại từ đầu.
                    next_mode = ladder[ladder.index(mode) + 1]
                    print(
                        f"[provider] Endpoint không hỗ trợ json_mode='{mode}' "
                        f"({message[:120]}). Chuyển sang '{next_mode}'.",
                        flush=True,
                    )
                    self.json_mode = next_mode
                    continue
                raise BackendError(f"Yêu cầu bị từ chối (400): {message}") from exc
            except openai.APIStatusError as exc:
                raise BackendError(f"Lỗi API {exc.status_code}: {exc}") from exc
            except openai.APIConnectionError as exc:
                raise BackendError(
                    f"Không kết nối được tới {self.base_url or 'endpoint'}. "
                    "Kiểm tra mạng, hoặc server local đã bật chưa."
                ) from exc

            text, loi = self._doc_phan_hoi(response)
            if loi == "__MAX_TOKENS__":
                raise BackendError(
                    "Trả lời bị cắt do hết max_tokens — tăng VLM_MAX_TOKENS."
                )
            if not text:
                # Đã thử lại hết lượt trong _goi_co_thu_lai mà vẫn rỗng.
                raise BackendError(
                    f"Máy chủ trả về phản hồi rỗng sau {self.retries} lần thử: {loi}"
                )

            usage = getattr(response, "usage", None)
            return Completion(
                text=text,
                input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                json_mode_used=mode,
            )

        raise BackendError(f"Không chế độ JSON nào dùng được. Lỗi cuối: {last_error}")

    def _goi_co_thu_lai(self, kwargs: dict[str, Any]) -> Any:
        """Gọi API, thử lại khi phản hồi rỗng hoặc không parse được.

        Endpoint có thể hỏng ngẫu nhiên (api.vilao.ai hỏng ~50% số lần, trả về
        luồng SSE rỗng kèm HTTP 200). Các lỗi *cố định* — sai key, sai tên model,
        body bị từ chối — được ném thẳng ra ngoài để lớp trên xử lý, không thử
        lại vô ích.
        """
        cuoi_cung: Any = None
        for lan in range(1, self.retries + 1):
            try:
                cuoi_cung = self.client.chat.completions.create(**kwargs)
            except json.JSONDecodeError as exc:
                # Body không phải JSON (thường là SSE) -> SDK vỡ khi parse.
                cuoi_cung = None
                loi = f"body không phải JSON ({exc})"
            else:
                text, loi = self._doc_phan_hoi(cuoi_cung)
                if text or loi == "__MAX_TOKENS__":
                    return cuoi_cung

            if lan < self.retries:
                print(f"[provider] Lần {lan}/{self.retries} hỏng ({loi}). Thử lại...",
                      flush=True)
                time.sleep(self.retry_delay)

        if cuoi_cung is None:  # mọi lần đều vỡ khi parse
            raise BackendError(
                f"Máy chủ trả về body không đọc được sau {self.retries} lần thử. "
                "Endpoint này đang trả về SSE/không đúng chuẩn OpenAI."
            )
        return cuoi_cung


BACKENDS = {
    "claude": ClaudeBackend,
    "openai": OpenAICompatBackend,
}


def create_backend(provider: str, **kwargs: Any):
    try:
        backend_cls = BACKENDS[provider]
    except KeyError:
        raise BackendError(
            f"Nhà cung cấp không hợp lệ: '{provider}'. Chọn: {', '.join(BACKENDS)}"
        ) from None
    return backend_cls(**kwargs)
