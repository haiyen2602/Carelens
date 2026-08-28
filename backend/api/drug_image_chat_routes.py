"""Secure B-07 package-image recognition and confirmation endpoints."""

from __future__ import annotations

import logging
import os
import tempfile
import time
from dataclasses import replace
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from threading import BoundedSemaphore

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from PIL import Image
from sqlalchemy.orm import Session

from backend.agents.v2.conversation_state import ActiveEntity
from backend.agents.v2.orchestrator import OrchestrationIntent, classify_intent
from backend.api.agent_v2_routes import run_agent_orchestration
from backend.api.security import CurrentUser, get_current_user
from backend.config import get_settings
from backend.db.base import get_db
from backend.db.models import AgentRun
from backend.models.schemas import (
    AgentV2OrchestrateRequest,
    DrugImageCandidateOut,
    DrugImageConfirmOut,
    DrugImageConfirmRequest,
    DrugImageRecognitionOut,
)
from backend.services.agent_authorization import require_agent_patient_access
from backend.services.agent_conversation_state import AgentConversationStateStore
from backend.services.agent_doctor_takeover import get_active_takeover
from backend.services.agent_read_only_tools import AgentReadOnlyDomainTools
from backend.services.drug_image_chat import (
    DrugImageChatError,
    RecognitionRunner,
    confirm_attempt,
    create_attempt,
    persist_takeover_upload,
    reject_attempt,
    remove_takeover_upload,
    requested_attribute_for,
    validate_upload,
)
from backend.services.drug_image_recognition import (
    AMBIGUOUS_MATCH,
    DrugImageRecognizer,
    OptionalTesseractOcrExtractor,
    recognition_observability,
)
from backend.services.drug_image_retrieval import OpenClipImageEmbedder

drug_image_chat_router = APIRouter(prefix="/agent/v2/drug-images", tags=["agent-v2-drug-image"])
logger = logging.getLogger(__name__)
# B-05 is CPU/GPU-heavy. Acquire this before reading bytes so a worker never
# admits an unbounded number of max-size payloads into process memory.
_recognition_slot = BoundedSemaphore(value=1)


@lru_cache(maxsize=1)
def get_drug_image_recognizer() -> RecognitionRunner:
    """Lazy B-05 runtime construction; tests replace this dependency."""

    settings = get_settings()
    return DrugImageRecognizer(
        OpenClipImageEmbedder(),
        ocr=OptionalTesseractOcrExtractor(timeout_seconds=settings.drug_image_chat_ocr_timeout_seconds),
    )


def _safe_error(exc: DrugImageChatError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": exc.code, "message": str(exc)})


@drug_image_chat_router.post("/recognize", response_model=DrugImageRecognitionOut)
async def recognize_drug_image(
    patient_id: str = Form(...),
    conversation_id: str = Form(..., min_length=1, max_length=200),
    message: str = Form(default="", max_length=5000),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    actor: CurrentUser = Depends(get_current_user),
) -> DrugImageRecognitionOut:
    """Validate then run B-05 only when safety/takeover and policy permit it."""

    patient_id = require_agent_patient_access(db, actor, patient_id)
    protected_intents = {
        OrchestrationIntent.ACUTE_DANGER_ESCALATION,
        OrchestrationIntent.POSSIBLE_OVERDOSE,
        OrchestrationIntent.MEDICATION_DOSE_SAFETY,
        OrchestrationIntent.MISSED_DOSE,
        OrchestrationIntent.DELAYED_DOSE,
    }
    if message and classify_intent(message).intent in protected_intents:
        logger.info("DRUG_IMAGE_UPLOAD_REJECTED conversation_id=%s error_code=SAFETY_DEFERRED", conversation_id)
        safety_response = run_agent_orchestration(
            AgentV2OrchestrateRequest(patient_id=patient_id, message=message, conversation_id=conversation_id), db, actor
        )
        return DrugImageRecognitionOut(
            status="SAFETY_DEFERRED",
            reply=safety_response.reply,
        )
    settings = get_settings()
    if not _recognition_slot.acquire(blocking=False):
        logger.info("DRUG_IMAGE_UPLOAD_REJECTED conversation_id=%s error_code=RECOGNITION_BUSY", conversation_id)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="He thong dang xu ly mot anh khac. Hay thu lai sau it phut.",
        )
    try:
        raw = await file.read(settings.drug_image_chat_max_upload_bytes + 1)
        upload = validate_upload(
            raw,
            claimed_mime_type=file.content_type,
            max_upload_bytes=settings.drug_image_chat_max_upload_bytes,
            max_dimension_px=settings.drug_image_chat_max_dimension_px,
            max_pixels=settings.drug_image_chat_max_pixels,
        )
        del raw
    except DrugImageChatError as exc:
        _recognition_slot.release()
        logger.info("DRUG_IMAGE_UPLOAD_REJECTED conversation_id=%s error_code=%s", conversation_id, exc.code)
        raise _safe_error(exc) from exc
    except OSError as exc:
        _recognition_slot.release()
        logger.warning("DRUG_IMAGE_UPLOAD_REJECTED conversation_id=%s error_code=UPLOAD_READ_FAILED", conversation_id)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Khong the doc anh luc nay. Hay thu lai sau.") from exc

    # Recheck after validation to close the policy boundary immediately before
    # B-05. This branch never invokes recognition, OCR, tools or Agent V2.
    try:
        active_takeover = get_active_takeover(db, patient_id=patient_id)
    except Exception:
        _recognition_slot.release()
        raise
    if active_takeover is not None:
        attachment = None
        doctor_storage_dir = Path(settings.drug_image_chat_doctor_storage_dir)
        try:
            attachment = persist_takeover_upload(
                db,
                handoff_id=active_takeover.id,
                patient_id=patient_id,
                actor_id=actor.id,
                message=message,
                upload=upload,
                storage_dir=doctor_storage_dir,
                ttl_seconds=settings.drug_image_chat_doctor_attachment_ttl_seconds,
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            if attachment is not None:
                remove_takeover_upload(storage_dir=doctor_storage_dir, storage_key=attachment.storage_key)
            _recognition_slot.release()
            logger.warning("DRUG_IMAGE_UPLOAD_REJECTED conversation_id=%s error_code=DOCTOR_DELIVERY_FAILED", conversation_id)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Khong the chuyen anh den bac si luc nay. Hay thu lai sau.",
            ) from exc
        _recognition_slot.release()
        logger.info("DRUG_IMAGE_UPLOAD_ACCEPTED conversation_id=%s outcome=DOCTOR_ACTIVE", conversation_id)
        return DrugImageRecognitionOut(
            status="DOCTOR_ACTIVE",
            reply="Bac si dang phu trach cuoc trao doi nay. Anh va tin nhan cua ban da duoc chuyen rieng den bac si.",
        )

    # Do not construct the optional OpenCLIP runtime through FastAPI
    # dependencies: unavailable production vision dependencies must be a
    # policy response, not an unhandled 500 before this handler.
    if not settings.drug_image_chat_recognition_enabled:
        _recognition_slot.release()
        logger.info("DRUG_IMAGE_UPLOAD_ACCEPTED conversation_id=%s outcome=RECOGNITION_UNAVAILABLE", conversation_id)
        return DrugImageRecognitionOut(
            status="RECOGNITION_UNAVAILABLE",
            reply="Tinh nang nhan dien thuoc tu anh hien chua kha dung. Ban co the nhap ten thuoc hoac hoi bac si.",
        )

    temp_dir = Path(settings.drug_image_chat_temp_dir)
    path: Path | None = None
    started = time.monotonic()
    logger.info("DRUG_IMAGE_UPLOAD_ACCEPTED conversation_id=%s", conversation_id)
    logger.info("DRUG_RECOGNITION_STARTED conversation_id=%s", conversation_id)
    try:
        recognizer = get_drug_image_recognizer()
        temp_dir.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(prefix="drug-image-chat-", suffix=".upload", dir=temp_dir)
        path = Path(temp_name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(upload.payload)
        del upload
        with Image.open(path) as image:
            result = recognizer.recognize(db, image)
        if time.monotonic() - started > settings.drug_image_chat_recognition_timeout_seconds:
            raise DrugImageChatError("RECOGNITION_TIMEOUT", "Nhan dien anh qua lau. Hay thu lai voi anh ro hon.")
        presentation = create_attempt(
            db,
            actor_id=actor.id,
            patient_id=patient_id,
            conversation_id=conversation_id,
            result=result,
            requested_attribute=requested_attribute_for(message),
            ttl_seconds=settings.drug_image_chat_confirmation_ttl_seconds,
        )
        db.commit()
    except DrugImageChatError as exc:
        db.rollback()
        logger.info("DRUG_IMAGE_UPLOAD_REJECTED conversation_id=%s error_code=%s", conversation_id, exc.code)
        raise _safe_error(exc) from exc
    except Exception as exc:
        db.rollback()
        logger.warning("DRUG_RECOGNITION_RESULT conversation_id=%s error_code=RECOGNITION_FAILED", conversation_id)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Không thể nhận diện ảnh lúc này. Hãy thử lại sau.") from exc
    finally:
        _recognition_slot.release()
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning("DRUG_IMAGE_UPLOAD_REJECTED conversation_id=%s error_code=CLEANUP_FAILED", conversation_id)

    latency_ms = round((time.monotonic() - started) * 1000, 2)
    api_status = (
        "AMBIGUOUS_MATCH"
        if presentation.outcome == AMBIGUOUS_MATCH
        else "CANDIDATES"
        if presentation.candidates
        else "INSUFFICIENT_EVIDENCE"
    )
    evidence = recognition_observability(result)
    logger.info(
        "DRUG_RECOGNITION_EVIDENCE conversation_id=%s recognition_attempt_id=%s "
        "quality_status=%s quality_reasons=%s ocr_status=%s ocr_signal_count=%s "
        "internal_top1_drug_product_id=%s internal_top1_visual_score=%s "
        "internal_top2_visual_score=%s top1_top2_margin=%s ocr_name_match=%s "
        "ocr_strength_match=%s ocr_conflict=%s decision_reason_codes=%s "
        "recognizer_outcome=%s persisted_outcome=%s api_outcome=%s",
        conversation_id,
        presentation.attempt_id,
        evidence.quality_status,
        ",".join(evidence.quality_reasons) or "NONE",
        evidence.ocr_status,
        evidence.ocr_signal_count,
        evidence.internal_top1_drug_product_id,
        evidence.internal_top1_visual_score,
        evidence.internal_top2_visual_score,
        evidence.top1_top2_margin,
        evidence.ocr_name_match,
        evidence.ocr_strength_match,
        evidence.ocr_conflict,
        ",".join(evidence.decision_reason_codes) or "NONE",
        evidence.recognizer_outcome,
        presentation.outcome,
        api_status,
    )
    logger.info(
        "DRUG_RECOGNITION_RESULT conversation_id=%s recognition_attempt_id=%s outcome=%s candidate_count=%s recognition_version=%s latency_ms=%s",
        conversation_id,
        presentation.attempt_id,
        presentation.outcome,
        len(presentation.candidates),
        presentation.recognition_version,
        latency_ms,
    )
    return DrugImageRecognitionOut(
        status=api_status,
        reply=presentation.reply,
        recognition_attempt_id=presentation.attempt_id,
        outcome=presentation.outcome,
        recognition_version=presentation.recognition_version,
        candidates=[
            DrugImageCandidateOut(
                action_id=item.action_id,
                product_display_name=item.product_display_name,
                strength_text=item.strength_text,
                rank=item.rank,
            )
            for item in presentation.candidates
        ],
        requested_attribute=presentation.requested_attribute,
    )


@drug_image_chat_router.post("/confirm", response_model=DrugImageConfirmOut)
def confirm_drug_image_candidate(
    request: DrugImageConfirmRequest,
    db: Session = Depends(get_db),
    actor: CurrentUser = Depends(get_current_user),
) -> DrugImageConfirmOut:
    """Promote only an exact current candidate and query verified drug data."""

    patient_id = require_agent_patient_access(db, actor, request.patient_id)
    try:
        if request.decision == "REJECTED":
            rejected = reject_attempt(
                db,
                attempt_id=request.recognition_attempt_id,
                action_id=request.action_id,
                actor_id=actor.id,
                patient_id=patient_id,
                conversation_id=request.conversation_id,
            )
            db.commit()
            logger.info(
                "DRUG_CANDIDATE_REJECTED conversation_id=%s recognition_attempt_id=%s outcome=REJECTED",
                request.conversation_id,
                rejected.attempt_id,
            )
            return DrugImageConfirmOut(
                status="REJECTED",
                reply="Được, hãy chụp lại ảnh rõ hơn hoặc nhập tên thuốc để tôi tra cứu.",
                recognition_attempt_id=rejected.attempt_id,
            )
        confirmed = confirm_attempt(
            db,
            attempt_id=request.recognition_attempt_id,
            action_id=request.action_id,
            actor_id=actor.id,
            patient_id=patient_id,
            conversation_id=request.conversation_id,
        )
        state_store = AgentConversationStateStore()
        prior_state = state_store.load(
            db, actor_id=actor.id, patient_id=patient_id, conversation_id=request.conversation_id
        )
        run = AgentRun(
            conversation_id=request.conversation_id,
            patient_id=patient_id,
            actor_id=actor.id,
            intent="DRUG_IMAGE_CONFIRMATION",
            status="COMPLETED",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            model_calls=0,
            metadata_json={"execution_path": "DRUG_LOOKUP", "recognition_attempt_id": confirmed.attempt_id},
        )
        db.add(run)
        db.flush()
        canonical_entity = ActiveEntity(
            "drug",
            confirmed.drug_product_id,
            confirmed.display_name,
            legacy_drug_id=confirmed.legacy_drug_id,
        )
        state_store.save(
            db,
            agent_run_id=run.id,
            actor_id=actor.id,
            patient_id=patient_id,
            state=replace(
                prior_state,
                active_topic=None,
                active_entity=canonical_entity,
                requested_attribute=confirmed.requested_attribute,
                offered_actions=(),
                pending_selection=None,
                updated_at=datetime.now(UTC),
            ),
        )
        reply = f"Bạn đã xác nhận {confirmed.display_name}."
        tools: list[str] = []
        if confirmed.legacy_drug_id:
            query = (
                confirmed.requested_attribute
                if confirmed.requested_attribute
                else f"Thông tin chi tiết đã xác minh về {confirmed.display_name}"
            )
            tool_data = AgentReadOnlyDomainTools(db).get_drug_info(
                legacy_drug_id=confirmed.legacy_drug_id,
                query=query,
            )
            contents = [item["content"] for item in tool_data["results"] if item.get("content")]
            if contents:
                reply = f"{reply} {' '.join(contents[:3])}"
                tools.append("get_drug_info")
            else:
                reply = f"{reply} Tôi chưa có thông tin đã xác minh hiện có cho thuốc này."
        else:
            reply = f"{reply} Tôi chưa có thông tin đã xác minh hiện có cho thuốc này."
        db.commit()
    except DrugImageChatError as exc:
        db.rollback()
        logger.info("DRUG_CANDIDATE_REJECTED conversation_id=%s error_code=%s", request.conversation_id, exc.code)
        raise _safe_error(exc) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Không thể xác nhận lựa chọn lúc này.") from exc
    logger.info(
        "DRUG_CANDIDATE_CONFIRMED conversation_id=%s recognition_attempt_id=%s outcome=CONFIRMED",
        request.conversation_id,
        confirmed.attempt_id,
    )
    return DrugImageConfirmOut(
        status="CONFIRMED",
        reply=reply,
        recognition_attempt_id=confirmed.attempt_id,
        canonical_drug_product_id=confirmed.drug_product_id,
        requested_attribute=confirmed.requested_attribute,
        tools=tools,
    )


__all__ = ["drug_image_chat_router", "get_drug_image_recognizer"]
