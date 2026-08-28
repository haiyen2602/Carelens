"""Turn-based voice I/O adapter around Agent V2 -- audio in, transcript out;
text in, audio out. Purely additive: neither endpoint here calls or changes
`backend/agents/v2/orchestrator.py`. The transcript from `/voice/transcribe`
is only ever fed into the UNCHANGED `/api/v1/agent/v2/orchestrate` call by
the caller (see frontend/src/app/patient/assistant/page.tsx) -- Agent V2
keeps owning 100% of the reasoning, safety and intent classification.
"""

from __future__ import annotations

import logging
import time
from functools import lru_cache

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from backend.agents.v2.speech_gateway import (
    EmptyTranscriptionError,
    MissingSpeechCredentialError,
    SpeechGateway,
)
from backend.api.rate_limit import SlidingWindowRateLimiter
from backend.api.security import CurrentUser, get_current_user
from backend.config import get_settings
from backend.db.base import get_db
from backend.models.schemas import VoiceSpeakRequest, VoiceTranscribeOut
from backend.services.agent_authorization import require_agent_patient_access

voice_router = APIRouter(prefix="/voice", tags=["voice"])
logger = logging.getLogger(__name__)

_FALLBACK_MESSAGE = "Không thể nhận diện giọng nói lúc này. Bạn vẫn có thể gõ tin nhắn."
_UNCLEAR_MESSAGE = "Không nghe rõ, bạn có thể nói lại được không?"
_SPEAK_FALLBACK_MESSAGE = "Không thể đọc câu trả lời lúc này."


@lru_cache(maxsize=1)
def get_speech_gateway() -> SpeechGateway:
    """Lazy construction from settings; tests replace this dependency."""

    return SpeechGateway.from_settings(get_settings())


_voice_limiter: SlidingWindowRateLimiter | None = None


def _get_voice_limiter() -> SlidingWindowRateLimiter:
    """Lazy singleton, same shape as rate_limit.py's own `_get_default_limiter`
    -- a separate budget from ordinary chat/image endpoints since each call
    here costs real OpenAI audio usage, not just an LLM turn."""

    global _voice_limiter
    if _voice_limiter is None:
        settings = get_settings()
        _voice_limiter = SlidingWindowRateLimiter(
            max_requests=settings.voice_rate_limit_max_requests,
            window_seconds=settings.voice_rate_limit_window_seconds,
        )
    return _voice_limiter


def reset_voice_limiter_for_tests() -> None:
    """CHI dung trong test - xoa singleton de test sau khong bi anh huong
    boi state cua test truoc (cung tinh than voi rate_limit.py)."""

    global _voice_limiter
    _voice_limiter = None


@voice_router.post("/transcribe", response_model=VoiceTranscribeOut)
async def transcribe_voice(
    patient_id: str = Form(...),
    conversation_id: str = Form(default="", max_length=200),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    actor: CurrentUser = Depends(get_current_user),
    gateway: SpeechGateway = Depends(get_speech_gateway),
) -> VoiceTranscribeOut:
    """Validate, rate-limit, then transcribe. Never persists or logs raw
    audio/text -- only event names, conversation_id and latency (same
    posture as drug_image_chat_routes.py)."""

    patient_id = require_agent_patient_access(db, actor, patient_id)
    _get_voice_limiter().check(patient_id)

    settings = get_settings()
    raw = await file.read(settings.voice_max_upload_bytes + 1)
    if len(raw) > settings.voice_max_upload_bytes:
        logger.info("VOICE_TRANSCRIBE_REJECTED conversation_id=%s error_code=UPLOAD_TOO_LARGE", conversation_id)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Bản ghi âm quá dài. Hãy thử ghi âm ngắn hơn.",
        )
    if not raw:
        logger.info("VOICE_TRANSCRIBE_REJECTED conversation_id=%s error_code=EMPTY_UPLOAD", conversation_id)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_UNCLEAR_MESSAGE)

    started = time.monotonic()
    try:
        text = gateway.transcribe(audio_bytes=raw, filename=file.filename or "audio.webm", mime_type=file.content_type)
    except EmptyTranscriptionError:
        logger.info("VOICE_TRANSCRIBE_REJECTED conversation_id=%s error_code=EMPTY_TRANSCRIPT", conversation_id)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_UNCLEAR_MESSAGE) from None
    except MissingSpeechCredentialError:
        logger.warning("VOICE_TRANSCRIBE_FAILED conversation_id=%s error_code=MISSING_CREDENTIAL", conversation_id)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_FALLBACK_MESSAGE) from None
    except Exception:
        logger.warning("VOICE_TRANSCRIBE_FAILED conversation_id=%s error_code=STT_FAILED", conversation_id)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_FALLBACK_MESSAGE) from None

    latency_ms = round((time.monotonic() - started) * 1000, 2)
    # audio_bytes/mime alongside text_len (still never the audio or the text
    # itself): without the INPUT size, a short transcript is ambiguous between
    # "the recording was truncated" and "the model mis-heard a full recording"
    # -- the two have completely different fixes.
    logger.info(
        "VOICE_TRANSCRIBE_RESULT conversation_id=%s audio_bytes=%d mime=%s text_len=%d latency_ms=%s",
        conversation_id,
        len(raw),
        file.content_type or "unknown",
        len(text),
        latency_ms,
    )
    return VoiceTranscribeOut(status="OK", text=text)


@voice_router.post("/speak")
def speak_voice(
    request: VoiceSpeakRequest,
    db: Session = Depends(get_db),
    actor: CurrentUser = Depends(get_current_user),
    gateway: SpeechGateway = Depends(get_speech_gateway),
) -> Response:
    """Turn Agent V2's own reply text into audio. Failure here must never be
    treated as a chat failure by the caller -- the text reply was already
    shown before this endpoint is ever called (see assistant/page.tsx)."""

    patient_id = require_agent_patient_access(db, actor, request.patient_id)
    _get_voice_limiter().check(patient_id)

    max_chars = get_settings().voice_max_reply_chars
    if len(request.text) > max_chars:
        logger.info("VOICE_SPEAK_REJECTED patient_id=%s error_code=TEXT_TOO_LONG", patient_id)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_SPEAK_FALLBACK_MESSAGE)

    started = time.monotonic()
    try:
        audio_bytes = gateway.speak(text=request.text)
    except MissingSpeechCredentialError:
        logger.warning("VOICE_SPEAK_FAILED patient_id=%s error_code=MISSING_CREDENTIAL", patient_id)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_SPEAK_FALLBACK_MESSAGE) from None
    except Exception:
        logger.warning("VOICE_SPEAK_FAILED patient_id=%s error_code=TTS_FAILED", patient_id)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_SPEAK_FALLBACK_MESSAGE) from None

    latency_ms = round((time.monotonic() - started) * 1000, 2)
    logger.info("VOICE_SPEAK_RESULT patient_id=%s text_len=%d latency_ms=%s", patient_id, len(request.text), latency_ms)
    return Response(content=audio_bytes, media_type="audio/mpeg")


__all__ = ["voice_router", "get_speech_gateway", "reset_voice_limiter_for_tests"]
