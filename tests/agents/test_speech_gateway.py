"""SpeechGateway tests -- no real OpenAI credential/network call.

Covers what tests/api/test_voice_routes.py deliberately cannot: those tests
inject a fake gateway, so nothing there asserts what SpeechGateway itself
sends to OpenAI. The language/prompt options are the whole reason this file
exists -- silently dropping them is invisible at the route layer but is
exactly what made short Vietnamese clips ("Alo") transcribe as English.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from backend.agents.v2.speech_gateway import (
    EmptyTranscriptionError,
    MissingSpeechCredentialError,
    SpeechGateway,
)


class _FakeTranscriptions:
    def __init__(self, text: str = "Alo") -> None:
        self.calls: list[dict[str, Any]] = []
        self._text = text

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return SimpleNamespace(text=self._text)


class _FakeSpeech:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return SimpleNamespace(read=lambda: b"mp3-bytes")


class _FakeClient:
    def __init__(self, *, text: str = "Alo", **client_kwargs: Any) -> None:
        self.client_kwargs = client_kwargs
        self.audio = SimpleNamespace(transcriptions=_FakeTranscriptions(text), speech=_FakeSpeech())


def _gateway(**overrides: Any) -> tuple[SpeechGateway, list[_FakeClient]]:
    made: list[_FakeClient] = []
    # Pop before the constructor kwargs are assembled below -- this one steers
    # the fake's reply, it is not a SpeechGateway argument.
    text = overrides.pop("_text", "Alo")

    def factory(**kwargs: Any) -> _FakeClient:
        client = _FakeClient(text=text, **kwargs)
        made.append(client)
        return client

    options: dict[str, Any] = {
        "api_key": "sk-test",
        "transcribe_model": "gpt-4o-transcribe",
        "tts_model": "gpt-4o-mini-tts",
        "tts_voice": "alloy",
        "client_factory": factory,
    }
    options.update(overrides)
    return SpeechGateway(**options), made


def test_transcribe_sends_language_and_prompt_when_configured() -> None:
    gateway, made = _gateway(transcribe_language="vi", transcribe_prompt="Từ thường gặp: liều.")

    gateway.transcribe(audio_bytes=b"audio", filename="voice.webm", mime_type="audio/webm")

    sent = made[0].audio.transcriptions.calls[0]
    assert sent["language"] == "vi"
    assert sent["prompt"] == "Từ thường gặp: liều."
    assert sent["model"] == "gpt-4o-transcribe"


def test_transcribe_omits_language_and_prompt_when_blank() -> None:
    # Blank is a real choice (let OpenAI detect / send no prompt), so the keys
    # must be ABSENT -- the API rejects language="" outright.
    gateway, made = _gateway(transcribe_language="", transcribe_prompt="")

    gateway.transcribe(audio_bytes=b"audio", filename="voice.webm", mime_type="audio/webm")

    sent = made[0].audio.transcriptions.calls[0]
    assert "language" not in sent
    assert "prompt" not in sent


def test_from_settings_reads_language_and_prompt() -> None:
    settings = SimpleNamespace(
        openai_speech_api_key="sk-from-settings",
        voice_stt_model="gpt-4o-transcribe",
        voice_stt_language="vi",
        voice_stt_prompt="Hội thoại về thuốc.",
        voice_tts_model="gpt-4o-mini-tts",
        voice_tts_voice="alloy",
        voice_request_timeout_seconds=20.0,
    )

    gateway = SpeechGateway.from_settings(settings)

    assert gateway._transcribe_language == "vi"
    assert gateway._transcribe_prompt == "Hội thoại về thuốc."


def test_from_settings_keeps_blank_language_instead_of_defaulting() -> None:
    # An operator who blanks these wants detection back; a "or default" would
    # silently override that choice.
    settings = SimpleNamespace(
        openai_api_key="sk-fallback",
        voice_stt_language="",
        voice_stt_prompt="",
    )

    gateway = SpeechGateway.from_settings(settings)

    assert gateway._transcribe_language == ""
    assert gateway._transcribe_prompt == ""
    # Falls back to OPENAI_API_KEY, same idiom as the model workloads.
    assert gateway._api_key == "sk-fallback"


def test_transcribe_raises_on_blank_transcript() -> None:
    gateway, _ = _gateway(_text="   ")

    with pytest.raises(EmptyTranscriptionError):
        gateway.transcribe(audio_bytes=b"audio", filename="voice.webm", mime_type="audio/webm")


def test_missing_credential_raises_before_any_request() -> None:
    gateway, made = _gateway(api_key="")

    with pytest.raises(MissingSpeechCredentialError):
        gateway.transcribe(audio_bytes=b"audio", filename="voice.webm", mime_type="audio/webm")

    assert made == []


def test_speak_sends_model_voice_and_mp3_format() -> None:
    gateway, made = _gateway()

    audio = gateway.speak(text="Bạn cần uống liều tiếp theo.")

    sent = made[0].audio.speech.calls[0]
    assert audio == b"mp3-bytes"
    assert sent["model"] == "gpt-4o-mini-tts"
    assert sent["voice"] == "alloy"
    assert sent["response_format"] == "mp3"
