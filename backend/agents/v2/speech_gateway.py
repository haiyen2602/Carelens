"""Turn-based OpenAI speech I/O for the voice adapter (backend/api/voice_routes.py).

Deliberately NOT the Realtime WebSocket API: `transcribe()`/`speak()` are
one-shot REST calls (`audio.transcriptions.create` / `audio.speech.create`).
Agent V2's own reasoning (backend/agents/v2/orchestrator.py) is untouched --
this module only ever converts audio<->text around it, mirroring
OpenAIModelGateway's (backend/agents/v2/model_gateway.py) credential/client
idioms rather than the reasoning-model contract itself.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import openai


def _setting(settings: Any, name: str) -> str:
    return str(getattr(settings, name, "") or "").strip()


class MissingSpeechCredentialError(RuntimeError):
    """Raised before a request when no usable OpenAI credential is configured."""


class EmptyTranscriptionError(ValueError):
    """Raised when OpenAI STT returns no (or only whitespace) text."""


class SpeechGateway:
    """OpenAI STT/TTS client wrapper. `client_factory` is injectable so tests
    can pass a fake exposing fake `audio.transcriptions`/`audio.speech`
    namespaces, same pattern as OpenAIModelGateway."""

    def __init__(
        self,
        *,
        api_key: str,
        transcribe_model: str,
        tts_model: str,
        tts_voice: str,
        transcribe_language: str = "",
        transcribe_prompt: str = "",
        client_factory: Callable[..., Any] = openai.OpenAI,
        request_timeout_seconds: float = 20.0,
    ) -> None:
        self._api_key = api_key
        self._transcribe_model = transcribe_model
        self._tts_model = tts_model
        self._tts_voice = tts_voice
        self._transcribe_language = transcribe_language
        self._transcribe_prompt = transcribe_prompt
        self._client_factory = client_factory
        self._request_timeout_seconds = request_timeout_seconds

    @classmethod
    def from_settings(cls, settings: Any) -> SpeechGateway:
        # Same fallback-to-OPENAI_API_KEY idiom as build_model_workloads()
        # (backend/agents/v2/model_gateway.py) -- a workload-specific key
        # wins, OPENAI_API_KEY is a local-dev fallback only.
        api_key = _setting(settings, "openai_speech_api_key") or _setting(settings, "openai_api_key")
        return cls(
            api_key=api_key,
            transcribe_model=_setting(settings, "voice_stt_model") or "gpt-4o-transcribe",
            # No "or <default>" fallback for these two: an empty value is a
            # MEANINGFUL choice (detect the language / send no prompt), not an
            # unset one to be filled in.
            transcribe_language=_setting(settings, "voice_stt_language"),
            transcribe_prompt=_setting(settings, "voice_stt_prompt"),
            tts_model=_setting(settings, "voice_tts_model") or "gpt-4o-mini-tts",
            tts_voice=_setting(settings, "voice_tts_voice") or "alloy",
            request_timeout_seconds=float(getattr(settings, "voice_request_timeout_seconds", 20.0)),
        )

    def _client(self) -> Any:
        if not self._api_key:
            raise MissingSpeechCredentialError(
                "OPENAI_SPEECH_API_KEY (or OPENAI_API_KEY for local development) is required"
            )
        # SDK retries disabled so the caller owns the retry/timeout budget,
        # same reasoning as OpenAIModelGateway._client_for.
        return self._client_factory(api_key=self._api_key, max_retries=0, timeout=self._request_timeout_seconds)

    def transcribe(self, *, audio_bytes: bytes, filename: str, mime_type: str | None) -> str:
        client = self._client()
        # Both are omitted entirely when unset rather than sent as "" -- the API
        # rejects an empty language, and an empty prompt would still cost tokens.
        options: dict[str, Any] = {}
        if self._transcribe_language:
            options["language"] = self._transcribe_language
        if self._transcribe_prompt:
            options["prompt"] = self._transcribe_prompt
        result = client.audio.transcriptions.create(
            model=self._transcribe_model,
            # Mac dinh KHONG duoi thay vi "audio.webm": OpenAI doc dinh dang theo
            # DUOI ten file, nen dat bua .webm cho mot file khong phai webm se
            # hong chac chan ("Audio file might be corrupted or unsupported").
            # Khong duoi thi no tu do noi dung va van nhan dung (da do thuc te).
            file=(filename or "audio", audio_bytes, mime_type or "application/octet-stream"),
            **options,
        )
        text = str(getattr(result, "text", "") or "").strip()
        if not text:
            raise EmptyTranscriptionError("transcription returned no text")
        return text

    def speak(self, *, text: str) -> bytes:
        client = self._client()
        response = client.audio.speech.create(
            model=self._tts_model,
            voice=self._tts_voice,
            input=text,
            response_format="mp3",
        )
        return response.read()
