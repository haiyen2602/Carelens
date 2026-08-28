"""B-07's private, deterministic boundary for package-image chat input.

This service owns upload validation and the durable candidate-confirmation
lifecycle.  It intentionally delegates recognition to B-05 and never stores a
query image, OCR text, embedding, or a model-derived drug fact.
"""

from __future__ import annotations

import io
import logging
import os
import secrets
import tempfile
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.db.models import DoctorReviewImageAttachment, DrugIdMap, DrugProduct, DrugRecognitionAttempt
from backend.services.doctor_handoff import MessageSenderRole, record_doctor_review_message
from backend.services.drug_image_recognition import (
    AMBIGUOUS_MATCH,
    HIGH_EVIDENCE_MATCH,
    INSUFFICIENT_EVIDENCE,
    RecognitionResult,
)

logger = logging.getLogger(__name__)

ATTEMPT_AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
ATTEMPT_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
ATTEMPT_CONFIRMED = "CONFIRMED"
ATTEMPT_SUPERSEDED = "SUPERSEDED"
ATTEMPT_EXPIRED = "EXPIRED"
ATTEMPT_FAILED = "FAILED"

ALLOWED_IMAGE_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}
_MIME_ALIASES = {"image/jpg": "image/jpeg"}
_ATTRIBUTE_MARKERS = (
    ("side_effects", ("tac dung phu", "tác dụng phụ")),
    ("contraindications", ("chong chi dinh", "chống chỉ định")),
    ("interactions", ("tuong tac", "tương tác")),
    ("warnings", ("luu y", "lưu ý", "canh bao", "cảnh báo")),
    ("dosage", ("lieu dung", "liều dùng", "bao nhieu vien", "bao nhiêu viên")),
    ("administration", ("cach dung", "cách dùng", "uống như thế nào", "dùng như thế nào")),
    ("drug_uses", ("cong dung", "công dụng", "dung de", "dùng để", "lam gi", "làm gì")),
)


class DrugImageChatError(ValueError):
    """Safe, stable error returned by the B-07 HTTP boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class RecognitionRunner(Protocol):
    def recognize(self, session: Session, image: Image.Image) -> RecognitionResult: ...


@dataclass(frozen=True)
class ValidatedUpload:
    payload: bytes
    mime_type: str
    width: int
    height: int


@dataclass(frozen=True)
class CandidatePresentation:
    action_id: str
    product_display_name: str
    strength_text: str | None
    rank: int


@dataclass(frozen=True)
class RecognitionAttemptPresentation:
    attempt_id: str
    outcome: str
    reply: str
    candidates: tuple[CandidatePresentation, ...]
    requested_attribute: str | None
    recognition_version: str


@dataclass(frozen=True)
class ConfirmedCandidate:
    attempt_id: str
    drug_product_id: str
    legacy_drug_id: str | None
    display_name: str
    requested_attribute: str | None
    already_confirmed: bool


@dataclass(frozen=True)
class RejectedCandidate:
    """A server-validated rejection that can never promote an active entity."""

    attempt_id: str


def persist_takeover_upload(
    session: Session,
    *,
    handoff_id: str,
    patient_id: str,
    actor_id: str,
    message: str,
    upload: ValidatedUpload,
    storage_dir: Path,
    ttl_seconds: int,
    now: datetime | None = None,
) -> DoctorReviewImageAttachment:
    """Persist an ACTIVE-takeover image as a private doctor-only artifact."""

    created_at = now or datetime.now(UTC)
    cleanup_expired_takeover_uploads(session, storage_dir=storage_dir, now=created_at)
    storage_dir.mkdir(parents=True, exist_ok=True)
    storage_key = f"takeover-{secrets.token_urlsafe(24)}.image"
    destination = _private_storage_path(storage_dir, storage_key)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".takeover-", suffix=".tmp", dir=storage_dir)
    temporary_path = Path(temporary_name)
    promoted = False
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(upload.payload)
        temporary_path.replace(destination)
        promoted = True
        review_message = record_doctor_review_message(
            session,
            handoff_id=handoff_id,
            patient_id=patient_id,
            sender_role=MessageSenderRole.PATIENT,
            actor_id=actor_id,
            content=message.strip() or "Da gui anh thuoc de bac si xem.",
            created_at=created_at,
        )
        attachment = DoctorReviewImageAttachment(
            handoff_id=handoff_id,
            message_id=review_message.id,
            patient_id=patient_id,
            storage_key=storage_key,
            mime_type=upload.mime_type,
            file_size=len(upload.payload),
            created_at=created_at,
            expires_at=created_at + timedelta(seconds=ttl_seconds),
        )
        session.add(attachment)
        session.flush()
        return attachment
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    finally:
        if not promoted:
            temporary_path.unlink(missing_ok=True)


def remove_takeover_upload(*, storage_dir: Path, storage_key: str) -> None:
    """Best-effort rollback cleanup for a private artifact not committed."""

    _private_storage_path(storage_dir, storage_key).unlink(missing_ok=True)


def private_takeover_upload_path(*, storage_dir: Path, storage_key: str) -> Path:
    """Resolve an opaque key while rejecting filesystem traversal."""

    return _private_storage_path(storage_dir, storage_key)


def cleanup_expired_takeover_uploads(
    session: Session,
    *,
    storage_dir: Path,
    now: datetime | None = None,
) -> int:
    """Remove expired private artifacts and their no-longer-usable references."""

    timestamp = now or datetime.now(UTC)
    expired = session.scalars(
        select(DoctorReviewImageAttachment).where(DoctorReviewImageAttachment.expires_at <= timestamp)
    ).all()
    removed = 0
    for attachment in expired:
        try:
            _private_storage_path(storage_dir, attachment.storage_key).unlink(missing_ok=True)
        except OSError:
            logger.warning("DRUG_IMAGE_UPLOAD_REJECTED error_code=PRIVATE_CLEANUP_FAILED")
            continue
        session.delete(attachment)
        removed += 1
    return removed


def _private_storage_path(storage_dir: Path, storage_key: str) -> Path:
    if Path(storage_key).name != storage_key:
        raise DrugImageChatError("PRIVATE_MEDIA_INVALID", "Tep rieng tu khong hop le.")
    root = storage_dir.resolve()
    candidate = (root / storage_key).resolve()
    if candidate.parent != root:
        raise DrugImageChatError("PRIVATE_MEDIA_INVALID", "Tep rieng tu khong hop le.")
    return candidate


def validate_upload(
    payload: bytes,
    *,
    claimed_mime_type: str | None,
    max_upload_bytes: int,
    max_dimension_px: int,
    max_pixels: int,
) -> ValidatedUpload:
    """Validate bytes by MIME, decoder format, dimensions and pixel bounds."""

    if not payload:
        raise DrugImageChatError("IMAGE_EMPTY", "Ảnh gửi lên trống. Hãy chọn lại ảnh gói thuốc.")
    if len(payload) > max_upload_bytes:
        raise DrugImageChatError("IMAGE_TOO_LARGE", "Ảnh vượt quá dung lượng cho phép. Hãy chọn ảnh nhỏ hơn.")
    declared = _MIME_ALIASES.get((claimed_mime_type or "").casefold(), (claimed_mime_type or "").casefold())
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(payload)) as image:
                actual = ALLOWED_IMAGE_TYPES.get(image.format or "")
                if actual is None:
                    raise DrugImageChatError("IMAGE_FORMAT_UNSUPPORTED", "Chỉ hỗ trợ ảnh JPEG, PNG hoặc WebP.")
                if declared and declared != actual:
                    raise DrugImageChatError("IMAGE_MIME_MISMATCH", "Định dạng ảnh không hợp lệ.")
                width, height = image.size
                if width <= 0 or height <= 0 or width > max_dimension_px or height > max_dimension_px:
                    raise DrugImageChatError("IMAGE_DIMENSIONS_INVALID", "Kích thước ảnh vượt quá giới hạn cho phép.")
                if width * height > max_pixels:
                    raise DrugImageChatError("IMAGE_PIXEL_LIMIT", "Ảnh có độ phân giải quá lớn. Hãy chọn ảnh nhỏ hơn.")
                image.load()
                return ValidatedUpload(payload=payload, mime_type=actual, width=width, height=height)
    except DrugImageChatError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, UnidentifiedImageError, OSError, ValueError) as exc:
        raise DrugImageChatError("IMAGE_UNREADABLE", "Không thể đọc ảnh. Hãy chụp lại ảnh gói thuốc rõ hơn.") from exc


def requested_attribute_for(message: str) -> str | None:
    """Persist only a bounded semantic aspect, never the raw chat text."""

    normalized = message.casefold()
    return next((value for value, markers in _ATTRIBUTE_MARKERS if any(marker in normalized for marker in markers)), None)


def create_attempt(
    session: Session,
    *,
    actor_id: str,
    patient_id: str,
    conversation_id: str,
    result: RecognitionResult,
    requested_attribute: str | None,
    ttl_seconds: int,
    now: datetime | None = None,
) -> RecognitionAttemptPresentation:
    """Supersede older attempts and persist only server-derived candidates."""

    created_at = now or datetime.now(UTC)
    session.execute(
        update(DrugRecognitionAttempt)
        .where(
            DrugRecognitionAttempt.actor_id == actor_id,
            DrugRecognitionAttempt.patient_id == patient_id,
            DrugRecognitionAttempt.conversation_id == conversation_id,
            DrugRecognitionAttempt.status == ATTEMPT_AWAITING_CONFIRMATION,
        )
        .values(status=ATTEMPT_SUPERSEDED, superseded_at=created_at)
    )
    # Only a HIGH_EVIDENCE_MATCH may offer a product for confirmation.  An
    # ambiguous visual result is useful telemetry, but it is not evidence that
    # a patient should choose between catalog products.  Keep it durable for
    # audit while exposing no product name/action to the client.
    if result.outcome != HIGH_EVIDENCE_MATCH or not result.candidates:
        attempt = DrugRecognitionAttempt(
            actor_id=actor_id,
            patient_id=patient_id,
            conversation_id=conversation_id,
            status=ATTEMPT_INSUFFICIENT_EVIDENCE,
            recognition_version=result.recognition_version,
            outcome=result.outcome if result.outcome == AMBIGUOUS_MATCH else INSUFFICIENT_EVIDENCE,
            candidates_json=[],
            requested_attribute=requested_attribute,
            created_at=created_at,
        )
        session.add(attempt)
        session.flush()
        return RecognitionAttemptPresentation(
            attempt_id=attempt.id,
            outcome=attempt.outcome,
            reply=(
                "Tôi chưa thể xác định chắc chắn thuốc trong ảnh. Hãy chụp rõ mặt trước hộp thuốc, "
                "thử lại với ánh sáng tốt hơn hoặc nhập tên thuốc."
                if attempt.outcome == AMBIGUOUS_MATCH
                else "Tôi chưa tìm được kết quả đủ đáng tin cậy. Hãy chụp rõ mặt trước hộp thuốc hoặc nhập tên thuốc."
            ),
            candidates=(),
            requested_attribute=requested_attribute,
            recognition_version=result.recognition_version,
        )

    candidates = []
    presentations = []
    for candidate in result.candidates[:1]:
        action_id = secrets.token_urlsafe(18)
        product = session.get(DrugProduct, candidate.drug_product_id)
        if product is None:
            continue
        active_mapping = session.scalars(
            select(DrugIdMap).where(
                DrugIdMap.drug_product_id == product.id,
                DrugIdMap.mapping_status == "ACTIVE",
            )
        ).first()
        candidates.append(
            {
                "action_id": action_id,
                "drug_product_id": product.id,
                "legacy_drug_id": active_mapping.legacy_drug_id if active_mapping is not None else product.legacy_drug_id,
                "display_name": product.display_name,
                "strength_text": product.strength_text,
                "rank": candidate.rank,
            }
        )
        presentations.append(
            CandidatePresentation(action_id, product.display_name, product.strength_text, candidate.rank))
    if not candidates:
        return create_attempt(
            session,
            actor_id=actor_id,
            patient_id=patient_id,
            conversation_id=conversation_id,
            result=RecognitionResult(
                outcome=INSUFFICIENT_EVIDENCE,
                candidates=(),
                evidence_summary=result.evidence_summary,
                quality_gate=result.quality_gate,
                model_version=result.model_version,
                recognition_version=result.recognition_version,
            ),
            requested_attribute=requested_attribute,
            ttl_seconds=ttl_seconds,
            now=created_at,
        )
    attempt = DrugRecognitionAttempt(
        actor_id=actor_id,
        patient_id=patient_id,
        conversation_id=conversation_id,
        status=ATTEMPT_AWAITING_CONFIRMATION,
        recognition_version=result.recognition_version,
        outcome=HIGH_EVIDENCE_MATCH,
        candidates_json=candidates,
        requested_attribute=requested_attribute,
        created_at=created_at,
        expires_at=created_at + timedelta(seconds=ttl_seconds),
    )
    session.add(attempt)
    session.flush()
    reply = "Ảnh có vẻ khớp với thuốc dưới đây. Bạn hãy xác nhận trước khi tôi tra cứu thông tin thuốc."
    return RecognitionAttemptPresentation(
        attempt_id=attempt.id,
        outcome=attempt.outcome,
        reply=reply,
        candidates=tuple(presentations),
        requested_attribute=requested_attribute,
        recognition_version=result.recognition_version,
    )


def confirm_attempt(
    session: Session,
    *,
    attempt_id: str,
    action_id: str,
    actor_id: str,
    patient_id: str,
    conversation_id: str,
    now: datetime | None = None,
) -> ConfirmedCandidate:
    """Accept exactly one server-issued candidate action for its own scope."""

    timestamp = now or datetime.now(UTC)
    attempt = session.get(DrugRecognitionAttempt, attempt_id)
    if (
        attempt is None
        or attempt.actor_id != actor_id
        or attempt.patient_id != patient_id
        or attempt.conversation_id != conversation_id
    ):
        raise DrugImageChatError("CONFIRMATION_FORBIDDEN", "Lựa chọn xác nhận không hợp lệ.")
    if attempt.status == ATTEMPT_CONFIRMED:
        selected = _candidate_for_selected(attempt)
        if selected is not None and selected["action_id"] == action_id:
            return _confirmed(attempt, selected, already_confirmed=True)
        raise DrugImageChatError("CONFIRMATION_REPLAY_REJECTED", "Lựa chọn xác nhận không hợp lệ.")
    if attempt.status == ATTEMPT_SUPERSEDED:
        raise DrugImageChatError("CONFIRMATION_STALE", "Ảnh này đã được thay bằng ảnh mới hơn. Hãy xác nhận lựa chọn mới.")
    if attempt.status != ATTEMPT_AWAITING_CONFIRMATION:
        raise DrugImageChatError("CONFIRMATION_NOT_AVAILABLE", "Lựa chọn này không còn hiệu lực.")
    expires_at = _as_utc(attempt.expires_at) if attempt.expires_at is not None else None
    if expires_at is not None and expires_at <= _as_utc(timestamp):
        attempt.status = ATTEMPT_EXPIRED
        raise DrugImageChatError("CONFIRMATION_EXPIRED", "Lựa chọn đã hết hạn. Hãy gửi lại ảnh để thử lại.")
    selected = next(
        (item for item in attempt.candidates_json if isinstance(item, dict) and item.get("action_id") == action_id), None
    )
    if selected is None:
        raise DrugImageChatError("CONFIRMATION_FORGED", "Lựa chọn xác nhận không hợp lệ.")
    product_id = selected.get("drug_product_id")
    if not isinstance(product_id, str) or session.get(DrugProduct, product_id) is None:
        attempt.status = ATTEMPT_FAILED
        raise DrugImageChatError("CONFIRMATION_PRODUCT_UNAVAILABLE", "Thông tin thuốc hiện không khả dụng. Hãy thử lại sau.")
    attempt.status = ATTEMPT_CONFIRMED
    attempt.selected_drug_product_id = product_id
    attempt.confirmed_at = timestamp
    return _confirmed(attempt, selected, already_confirmed=False)


def reject_attempt(
    session: Session,
    *,
    attempt_id: str,
    action_id: str,
    actor_id: str,
    patient_id: str,
    conversation_id: str,
    now: datetime | None = None,
) -> RejectedCandidate:
    """Invalidate one current server-issued candidate without binding state.

    ``SUPERSEDED`` is an existing terminal, database-constrained lifecycle
    state. Reusing it keeps the rejection durable without widening the
    production schema, and makes any later confirm call fail closed as stale.
    """

    timestamp = now or datetime.now(UTC)
    attempt = session.get(DrugRecognitionAttempt, attempt_id)
    if (
        attempt is None
        or attempt.actor_id != actor_id
        or attempt.patient_id != patient_id
        or attempt.conversation_id != conversation_id
    ):
        raise DrugImageChatError("CONFIRMATION_FORBIDDEN", "Lựa chọn xác nhận không hợp lệ.")
    if attempt.status == ATTEMPT_SUPERSEDED:
        raise DrugImageChatError("CONFIRMATION_STALE", "Ảnh này đã không còn hiệu lực. Hãy gửi lại ảnh để thử lại.")
    if attempt.status != ATTEMPT_AWAITING_CONFIRMATION:
        raise DrugImageChatError("CONFIRMATION_NOT_AVAILABLE", "Lựa chọn này không còn hiệu lực.")
    expires_at = _as_utc(attempt.expires_at) if attempt.expires_at is not None else None
    if expires_at is not None and expires_at <= _as_utc(timestamp):
        attempt.status = ATTEMPT_EXPIRED
        raise DrugImageChatError("CONFIRMATION_EXPIRED", "Lựa chọn đã hết hạn. Hãy gửi lại ảnh để thử lại.")
    selected = next(
        (item for item in attempt.candidates_json if isinstance(item, dict) and item.get("action_id") == action_id), None
    )
    if selected is None:
        raise DrugImageChatError("CONFIRMATION_FORGED", "Lựa chọn xác nhận không hợp lệ.")
    attempt.status = ATTEMPT_SUPERSEDED
    attempt.superseded_at = timestamp
    return RejectedCandidate(attempt_id=attempt.id)


def _candidate_for_selected(attempt: DrugRecognitionAttempt) -> dict | None:
    return next(
        (
            item
            for item in attempt.candidates_json
            if isinstance(item, dict) and item.get("drug_product_id") == attempt.selected_drug_product_id
        ),
        None,
    )


def _confirmed(attempt: DrugRecognitionAttempt, selected: dict, *, already_confirmed: bool) -> ConfirmedCandidate:
    product_id = selected.get("drug_product_id")
    display_name = selected.get("display_name")
    if not isinstance(product_id, str) or not isinstance(display_name, str):
        raise DrugImageChatError("CONFIRMATION_PRODUCT_UNAVAILABLE", "Thông tin thuốc hiện không khả dụng. Hãy thử lại sau.")
    legacy_id = selected.get("legacy_drug_id")
    return ConfirmedCandidate(
        attempt_id=attempt.id,
        drug_product_id=product_id,
        legacy_drug_id=legacy_id if isinstance(legacy_id, str) else None,
        display_name=display_name,
        requested_attribute=attempt.requested_attribute,
        already_confirmed=already_confirmed,
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


__all__ = [
    "ALLOWED_IMAGE_TYPES",
    "CandidatePresentation",
    "ConfirmedCandidate",
    "DrugImageChatError",
    "RecognitionAttemptPresentation",
    "RecognitionRunner",
    "confirm_attempt",
    "cleanup_expired_takeover_uploads",
    "create_attempt",
    "persist_takeover_upload",
    "private_takeover_upload_path",
    "reject_attempt",
    "RejectedCandidate",
    "remove_takeover_upload",
    "requested_attribute_for",
    "validate_upload",
]
