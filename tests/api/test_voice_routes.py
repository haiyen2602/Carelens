"""Voice I/O route tests -- no real OpenAI credential/network call. Mirrors
tests/api/test_drug_image_chat_routes.py's style: call route handlers
directly (monkeypatching module-level collaborators) rather than a full
TestClient/DB integration, since auth/db plumbing is already covered
elsewhere (require_agent_patient_access itself, get_current_user)."""

from __future__ import annotations

import asyncio
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from backend.agents.v2.speech_gateway import EmptyTranscriptionError, MissingSpeechCredentialError
from backend.api import voice_routes as routes


def _audio_upload(content: bytes = b"fake-audio-bytes") -> UploadFile:
    return UploadFile(filename="voice.webm", file=BytesIO(content), headers=Headers({"content-type": "audio/webm"}))


def _settings(**overrides) -> SimpleNamespace:
    values = {
        "voice_max_upload_bytes": 1024,
        "voice_max_reply_chars": 2000,
        "voice_rate_limit_max_requests": 20,
        "voice_rate_limit_window_seconds": 60.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _FakeGateway:
    def __init__(self, *, text: str | None = "Liều tiếp theo lúc mấy giờ", speak_bytes: bytes = b"mp3-bytes", raise_: Exception | None = None):
        self._text = text
        self._speak_bytes = speak_bytes
        self._raise = raise_
        self.transcribe_calls: list[dict] = []
        self.speak_calls: list[dict] = []

    def transcribe(self, *, audio_bytes: bytes, filename: str, mime_type: str | None) -> str:
        self.transcribe_calls.append({"audio_bytes": audio_bytes, "filename": filename, "mime_type": mime_type})
        if self._raise is not None:
            raise self._raise
        if not self._text:
            raise EmptyTranscriptionError("no text")
        return self._text

    def speak(self, *, text: str) -> bytes:
        self.speak_calls.append({"text": text})
        if self._raise is not None:
            raise self._raise
        return self._speak_bytes


def _route_defaults(monkeypatch: pytest.MonkeyPatch, *, settings: SimpleNamespace | None = None) -> None:
    monkeypatch.setattr(routes, "get_settings", lambda: settings or _settings())
    monkeypatch.setattr(routes, "require_agent_patient_access", lambda _db, _actor, patient_id: patient_id)
    routes.reset_voice_limiter_for_tests()


def test_transcribe_success_returns_text(monkeypatch: pytest.MonkeyPatch) -> None:
    _route_defaults(monkeypatch)
    gateway = _FakeGateway(text="Liều tiếp theo lúc mấy giờ")

    response = asyncio.run(
        routes.transcribe_voice(
            patient_id="patient-a",
            conversation_id="conversation-a",
            file=_audio_upload(),
            db=object(),
            actor=SimpleNamespace(id="actor-a"),
            gateway=gateway,
        )
    )

    assert response.status == "OK"
    assert response.text == "Liều tiếp theo lúc mấy giờ"
    assert len(gateway.transcribe_calls) == 1


def test_transcribe_rejects_oversized_upload_without_calling_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    _route_defaults(monkeypatch, settings=_settings(voice_max_upload_bytes=4))
    gateway = _FakeGateway()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            routes.transcribe_voice(
                patient_id="patient-a",
                conversation_id="conversation-a",
                file=_audio_upload(b"way-too-large-for-the-cap"),
                db=object(),
                actor=SimpleNamespace(id="actor-a"),
                gateway=gateway,
            )
        )

    assert exc_info.value.status_code == 422
    # The size cap must short-circuit BEFORE any OpenAI call -- this is the
    # cost control, so the fake gateway must never have been invoked.
    assert gateway.transcribe_calls == []


def test_transcribe_empty_upload_rejected_without_calling_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    _route_defaults(monkeypatch)
    gateway = _FakeGateway()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            routes.transcribe_voice(
                patient_id="patient-a",
                conversation_id="conversation-a",
                file=_audio_upload(b""),
                db=object(),
                actor=SimpleNamespace(id="actor-a"),
                gateway=gateway,
            )
        )

    assert exc_info.value.status_code == 422
    assert gateway.transcribe_calls == []


def test_transcribe_empty_transcript_returns_422(monkeypatch: pytest.MonkeyPatch) -> None:
    _route_defaults(monkeypatch)
    gateway = _FakeGateway(text=None)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            routes.transcribe_voice(
                patient_id="patient-a",
                conversation_id="conversation-a",
                file=_audio_upload(),
                db=object(),
                actor=SimpleNamespace(id="actor-a"),
                gateway=gateway,
            )
        )

    assert exc_info.value.status_code == 422


def test_transcribe_missing_credential_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    _route_defaults(monkeypatch)
    gateway = _FakeGateway(raise_=MissingSpeechCredentialError("no key"))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            routes.transcribe_voice(
                patient_id="patient-a",
                conversation_id="conversation-a",
                file=_audio_upload(),
                db=object(),
                actor=SimpleNamespace(id="actor-a"),
                gateway=gateway,
            )
        )

    assert exc_info.value.status_code == 503


def test_transcribe_stt_failure_returns_503_not_500(monkeypatch: pytest.MonkeyPatch) -> None:
    _route_defaults(monkeypatch)
    gateway = _FakeGateway(raise_=RuntimeError("network blip"))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            routes.transcribe_voice(
                patient_id="patient-a",
                conversation_id="conversation-a",
                file=_audio_upload(),
                db=object(),
                actor=SimpleNamespace(id="actor-a"),
                gateway=gateway,
            )
        )

    assert exc_info.value.status_code == 503


def test_speak_returns_audio_mpeg_response(monkeypatch: pytest.MonkeyPatch) -> None:
    _route_defaults(monkeypatch)
    gateway = _FakeGateway(speak_bytes=b"fake-mp3-bytes")

    from backend.models.schemas import VoiceSpeakRequest

    response = routes.speak_voice(
        VoiceSpeakRequest(patient_id="patient-a", text="Bạn đã uống thuốc sáng nay."),
        db=object(),
        actor=SimpleNamespace(id="actor-a"),
        gateway=gateway,
    )

    assert response.media_type == "audio/mpeg"
    assert response.body == b"fake-mp3-bytes"
    assert gateway.speak_calls == [{"text": "Bạn đã uống thuốc sáng nay."}]


def test_speak_failure_returns_503_and_never_blocks_text_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    _route_defaults(monkeypatch)
    gateway = _FakeGateway(raise_=RuntimeError("tts down"))

    from backend.models.schemas import VoiceSpeakRequest

    with pytest.raises(HTTPException) as exc_info:
        routes.speak_voice(
            VoiceSpeakRequest(patient_id="patient-a", text="Bạn đã uống thuốc sáng nay."),
            db=object(),
            actor=SimpleNamespace(id="actor-a"),
            gateway=gateway,
        )

    # 503 here is the ONLY contract this endpoint owes -- the caller
    # (frontend) is responsible for treating this as non-fatal to the
    # already-rendered text reply; nothing to assert about that at this
    # unit-test layer beyond "this never surfaces as an unhandled 500".
    assert exc_info.value.status_code == 503


def test_speak_rejects_overlong_text_without_calling_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    _route_defaults(monkeypatch, settings=_settings(voice_max_reply_chars=10))
    gateway = _FakeGateway()

    from backend.models.schemas import VoiceSpeakRequest

    with pytest.raises(HTTPException) as exc_info:
        routes.speak_voice(
            VoiceSpeakRequest(patient_id="patient-a", text="x" * 11),
            db=object(),
            actor=SimpleNamespace(id="actor-a"),
            gateway=gateway,
        )

    assert exc_info.value.status_code == 422
    # Cost control: the cap must short-circuit BEFORE any OpenAI TTS call.
    assert gateway.speak_calls == []


def test_voice_rate_limit_blocks_after_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    _route_defaults(monkeypatch, settings=_settings(voice_rate_limit_max_requests=1))
    gateway = _FakeGateway()

    asyncio.run(
        routes.transcribe_voice(
            patient_id="patient-a",
            conversation_id="conversation-a",
            file=_audio_upload(),
            db=object(),
            actor=SimpleNamespace(id="actor-a"),
            gateway=gateway,
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            routes.transcribe_voice(
                patient_id="patient-a",
                conversation_id="conversation-a",
                file=_audio_upload(),
                db=object(),
                actor=SimpleNamespace(id="actor-a"),
                gateway=gateway,
            )
        )

    assert exc_info.value.status_code == 429
