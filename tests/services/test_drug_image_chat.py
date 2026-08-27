"""B-07 deterministic upload and server-issued confirmation lifecycle tests."""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from PIL import Image
from sqlalchemy.orm import Session

from backend.db.models import (
    DoctorReviewImageAttachment,
    DoctorReviewMessage,
    DoctorReviewRequest,
    DrugIdMap,
    DrugProduct,
    DrugRecognitionAttempt,
)
from backend.services.drug_image_chat import (
    ATTEMPT_CONFIRMED,
    ATTEMPT_SUPERSEDED,
    DrugImageChatError,
    confirm_attempt,
    create_attempt,
    persist_takeover_upload,
    private_takeover_upload_path,
    validate_upload,
)
from backend.services.drug_image_recognition import (
    HIGH_EVIDENCE_MATCH,
    INSUFFICIENT_EVIDENCE,
    ImageQuality,
    RecognitionCandidate,
    RecognitionResult,
)


def _session() -> Session:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    DrugProduct.__table__.create(engine)
    DrugIdMap.__table__.create(engine)
    DrugRecognitionAttempt.__table__.create(engine)
    DoctorReviewRequest.__table__.create(engine)
    DoctorReviewMessage.__table__.create(engine)
    DoctorReviewImageAttachment.__table__.create(engine)
    session = Session(engine)
    now = datetime.now(UTC)
    session.add(
        DrugProduct(
            id="product-a",
            legacy_drug_id="legacy-a",
            display_name="Thuốc A 500 mg",
            strength_text="500 mg",
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    return session


def _result(*, outcome: str = HIGH_EVIDENCE_MATCH) -> RecognitionResult:
    candidates = ()
    if outcome != INSUFFICIENT_EVIDENCE:
        candidates = (
            RecognitionCandidate(
                rank=1,
                visual_rank=1,
                drug_product_id="product-a",
                drug_image_id="image-a",
                product_display_name="untrusted candidate label",
                visual_score=0.99,
                fused_score=0.99,
                text_evidence=(),
                conflicts=(),
            ),
        )
    return RecognitionResult(
        outcome=outcome,
        candidates=candidates,
        evidence_summary=("OCR_STATUS:OCR_OK",),
        quality_gate=ImageQuality("PASS", (), 100, 100),
        model_version="test-model",
    )


def _png_bytes() -> bytes:
    image = Image.new("RGB", (100, 100), "red")
    try:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    finally:
        image.close()


def _image_bytes(image_format: str) -> bytes:
    image = Image.new("RGB", (100, 100), "red")
    try:
        buffer = io.BytesIO()
        image.save(buffer, format=image_format)
        return buffer.getvalue()
    finally:
        image.close()


@pytest.mark.parametrize(
    ("image_format", "content_type"),
    (("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")),
)
def test_upload_validation_accepts_each_supported_image_format(image_format: str, content_type: str) -> None:
    upload = validate_upload(
        _image_bytes(image_format),
        claimed_mime_type=content_type,
        max_upload_bytes=1024 * 1024,
        max_dimension_px=200,
        max_pixels=40_000,
    )
    assert upload.mime_type == content_type


def test_upload_validation_uses_decoder_format_not_filename_or_claimed_mime() -> None:
    upload = validate_upload(
        _png_bytes(),
        claimed_mime_type="image/png",
        max_upload_bytes=1024 * 1024,
        max_dimension_px=200,
        max_pixels=40_000,
    )
    assert upload.mime_type == "image/png"
    with pytest.raises(DrugImageChatError, match="Định dạng ảnh không hợp lệ"):
        validate_upload(
            _png_bytes(),
            claimed_mime_type="image/jpeg",
            max_upload_bytes=1024 * 1024,
            max_dimension_px=200,
            max_pixels=40_000,
        )


def test_upload_validation_rejects_corrupt_oversized_and_decompression_bomb(monkeypatch: pytest.MonkeyPatch) -> None:
    limits = {"claimed_mime_type": "image/png", "max_upload_bytes": 50, "max_dimension_px": 200, "max_pixels": 40_000}
    with pytest.raises(DrugImageChatError) as corrupt:
        validate_upload(b"not-an-image", **limits)
    assert corrupt.value.code == "IMAGE_UNREADABLE"
    with pytest.raises(DrugImageChatError) as oversized:
        validate_upload(_png_bytes(), **limits)
    assert oversized.value.code == "IMAGE_TOO_LARGE"
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)
    with pytest.raises(DrugImageChatError) as bomb:
        validate_upload(
            _png_bytes(),
            claimed_mime_type="image/png",
            max_upload_bytes=1024 * 1024,
            max_dimension_px=200,
            max_pixels=40_000,
        )
    assert bomb.value.code == "IMAGE_UNREADABLE"


def test_confirmation_is_allowlisted_idempotent_and_stale_attempts_are_rejected() -> None:
    session = _session()
    first = create_attempt(
        session,
        actor_id="actor-a",
        patient_id="patient-a",
        conversation_id="conversation-a",
        result=_result(),
        requested_attribute="side_effects",
        ttl_seconds=900,
    )
    session.commit()
    with pytest.raises(DrugImageChatError) as forged:
        confirm_attempt(
            session,
            attempt_id=first.attempt_id,
            action_id="forged-product-id",
            actor_id="actor-a",
            patient_id="patient-a",
            conversation_id="conversation-a",
        )
    assert forged.value.code == "CONFIRMATION_FORGED"

    confirmed = confirm_attempt(
        session,
        attempt_id=first.attempt_id,
        action_id=first.candidates[0].action_id,
        actor_id="actor-a",
        patient_id="patient-a",
        conversation_id="conversation-a",
    )
    session.commit()
    assert confirmed.drug_product_id == "product-a"
    assert session.get(DrugRecognitionAttempt, first.attempt_id).status == ATTEMPT_CONFIRMED
    replay = confirm_attempt(
        session,
        attempt_id=first.attempt_id,
        action_id=first.candidates[0].action_id,
        actor_id="actor-a",
        patient_id="patient-a",
        conversation_id="conversation-a",
    )
    assert replay.already_confirmed is True

    newer = create_attempt(
        session,
        actor_id="actor-a",
        patient_id="patient-a",
        conversation_id="conversation-a",
        result=_result(),
        requested_attribute=None,
        ttl_seconds=900,
    )
    newest = create_attempt(
        session,
        actor_id="actor-a",
        patient_id="patient-a",
        conversation_id="conversation-a",
        result=_result(),
        requested_attribute=None,
        ttl_seconds=900,
    )
    session.commit()
    assert session.get(DrugRecognitionAttempt, newer.attempt_id).status == ATTEMPT_SUPERSEDED
    with pytest.raises(DrugImageChatError) as stale:
        confirm_attempt(
            session,
            attempt_id=newer.attempt_id,
            action_id=newer.candidates[0].action_id,
            actor_id="actor-a",
            patient_id="patient-a",
            conversation_id="conversation-a",
        )
    assert stale.value.code == "CONFIRMATION_STALE"
    assert newest.candidates[0].action_id != newer.candidates[0].action_id


def test_confirmation_rejects_cross_patient_and_expired_actions() -> None:
    session = _session()
    now = datetime.now(UTC)
    presentation = create_attempt(
        session,
        actor_id="actor-a",
        patient_id="patient-a",
        conversation_id="conversation-a",
        result=_result(),
        requested_attribute=None,
        ttl_seconds=1,
        now=now,
    )
    with pytest.raises(DrugImageChatError) as cross_patient:
        confirm_attempt(
            session,
            attempt_id=presentation.attempt_id,
            action_id=presentation.candidates[0].action_id,
            actor_id="actor-a",
            patient_id="patient-b",
            conversation_id="conversation-a",
        )
    assert cross_patient.value.code == "CONFIRMATION_FORBIDDEN"
    with pytest.raises(DrugImageChatError) as expired:
        confirm_attempt(
            session,
            attempt_id=presentation.attempt_id,
            action_id=presentation.candidates[0].action_id,
            actor_id="actor-a",
            patient_id="patient-a",
            conversation_id="conversation-a",
            now=now + timedelta(seconds=2),
        )
    assert expired.value.code == "CONFIRMATION_EXPIRED"


def test_takeover_attachment_is_private_opaque_and_expired_files_are_cleaned(tmp_path: Path) -> None:
    session = _session()
    now = datetime.now(UTC)
    session.add(
        DoctorReviewRequest(
            id="handoff-a",
            patient_id="patient-a",
            created_by_actor_id="actor-a",
            reason_code="UNCERTAINTY",
            risk_disposition="HANDOFF",
            patient_question="image",
            agent_summary="image",
            status="ACTIVE",
            idempotency_key="handoff-a-key",
            assigned_doctor_id="doctor-a",
        )
    )
    session.commit()
    upload = validate_upload(
        _png_bytes(),
        claimed_mime_type="image/png",
        max_upload_bytes=1024 * 1024,
        max_dimension_px=200,
        max_pixels=40_000,
    )
    attachment = persist_takeover_upload(
        session,
        handoff_id="handoff-a",
        patient_id="patient-a",
        actor_id="actor-a",
        message="please review",
        upload=upload,
        storage_dir=tmp_path,
        ttl_seconds=1,
        now=now,
    )
    session.commit()
    path = private_takeover_upload_path(storage_dir=tmp_path, storage_key=attachment.storage_key)
    assert path.is_file()
    assert not list(tmp_path.glob("*.tmp"))
    assert str(path) not in attachment.storage_key
    replacement = persist_takeover_upload(
        session,
        handoff_id="handoff-a",
        patient_id="patient-a",
        actor_id="actor-a",
        message="new image",
        upload=upload,
        storage_dir=tmp_path,
        ttl_seconds=1,
        now=now + timedelta(seconds=2),
    )
    session.flush()
    assert session.get(DoctorReviewImageAttachment, attachment.id) is None
    assert not path.exists()
    assert private_takeover_upload_path(storage_dir=tmp_path, storage_key=replacement.storage_key).is_file()


def test_attempt_snapshot_never_persists_raw_ocr_or_image_payload() -> None:
    session = _session()
    presentation = create_attempt(
        session,
        actor_id="actor-a",
        patient_id="patient-a",
        conversation_id="conversation-a",
        result=_result(),
        requested_attribute="drug_uses",
        ttl_seconds=900,
    )
    row = session.get(DrugRecognitionAttempt, presentation.attempt_id)
    assert row is not None
    assert row.candidates_json == [
        {
            "action_id": presentation.candidates[0].action_id,
            "drug_product_id": "product-a",
            "legacy_drug_id": "legacy-a",
            "display_name": "Thuốc A 500 mg",
            "strength_text": "500 mg",
            "rank": 1,
        }
    ]
