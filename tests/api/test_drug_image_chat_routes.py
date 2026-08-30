"""B-07 route policy-boundary regression tests."""

from __future__ import annotations

import asyncio
from io import BytesIO
from threading import BoundedSemaphore
from types import SimpleNamespace

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from backend.agents.v2.conversation_state import ConversationState
from backend.agents.v2.orchestrator import OrchestrationIntent
from backend.api import drug_image_chat_routes as routes
from backend.models.schemas import DrugImageConfirmRequest
from backend.services.drug_image_chat import ConfirmedCandidate


def _upload() -> UploadFile:
    return UploadFile(
        filename="package.png",
        file=BytesIO(b"image-bytes"),
        headers=Headers({"content-type": "image/png"}),
    )


def _settings(*, enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(
        drug_image_chat_max_upload_bytes=1024,
        drug_image_chat_max_dimension_px=200,
        drug_image_chat_max_pixels=40_000,
        drug_image_chat_recognition_enabled=enabled,
        drug_image_chat_temp_dir="./unused",
        drug_image_chat_doctor_storage_dir="./unused",
        drug_image_chat_doctor_attachment_ttl_seconds=60,
        drug_image_chat_recognition_timeout_seconds=30,
    )


def _route_defaults(monkeypatch: pytest.MonkeyPatch, *, enabled: bool) -> None:
    monkeypatch.setattr(routes, "_recognition_slot", BoundedSemaphore(value=1))
    monkeypatch.setattr(routes, "get_settings", lambda: _settings(enabled=enabled))
    monkeypatch.setattr(routes, "require_agent_patient_access", lambda _db, _actor, patient_id: patient_id)
    monkeypatch.setattr(routes, "validate_upload", lambda *_args, **_kwargs: SimpleNamespace(payload=b"validated"))


def test_disabled_recognition_returns_bounded_response_without_constructing_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _route_defaults(monkeypatch, enabled=False)
    monkeypatch.setattr(routes, "get_active_takeover", lambda _db, **_kwargs: None)

    def fail_if_constructed() -> None:
        pytest.fail("disabled recognition must not construct the vision runtime")

    monkeypatch.setattr(routes, "get_drug_image_recognizer", fail_if_constructed)

    response = asyncio.run(
        routes.recognize_drug_image(
            patient_id="patient-a",
            conversation_id="conversation-a",
            message="",
            file=_upload(),
            db=object(),
            actor=SimpleNamespace(id="actor-a"),
        )
    )

    assert response.status == "RECOGNITION_UNAVAILABLE"
    assert response.recognition_attempt_id is None
    assert response.candidates == []


def test_doctor_takeover_stays_ahead_of_disabled_recognition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _route_defaults(monkeypatch, enabled=False)
    monkeypatch.setattr(routes, "get_active_takeover", lambda _db, **_kwargs: SimpleNamespace(id="handoff-a"))
    monkeypatch.setattr(routes, "persist_takeover_upload", lambda *_args, **_kwargs: SimpleNamespace(storage_key="opaque"))
    monkeypatch.setattr(routes, "get_drug_image_recognizer", lambda: pytest.fail("runtime must stay unused"))

    database = SimpleNamespace(commit=lambda: None)
    response = asyncio.run(
        routes.recognize_drug_image(
            patient_id="patient-a",
            conversation_id="conversation-a",
            message="please review",
            file=_upload(),
            db=database,
            actor=SimpleNamespace(id="actor-a"),
        )
    )

    assert response.status == "DOCTOR_ACTIVE"


def test_safety_route_stays_ahead_of_upload_and_recognition(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        routes,
        "classify_intent",
        lambda _message: SimpleNamespace(intent=OrchestrationIntent.MEDICATION_DOSE_SAFETY),
    )
    monkeypatch.setattr(routes, "require_agent_patient_access", lambda _db, _actor, patient_id: patient_id)
    monkeypatch.setattr(routes, "run_agent_orchestration", lambda *_args, **_kwargs: SimpleNamespace(reply="safety reply"))
    monkeypatch.setattr(routes, "get_drug_image_recognizer", lambda: pytest.fail("runtime must stay unused"))

    response = asyncio.run(
        routes.recognize_drug_image(
            patient_id="patient-a",
            conversation_id="conversation-a",
            message="dose safety",
            file=_upload(),
            db=object(),
            actor=SimpleNamespace(id="actor-a"),
        )
    )

    assert response.status == "SAFETY_DEFERRED"


def test_enabled_model_load_failure_returns_safe_503_and_releases_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _route_defaults(monkeypatch, enabled=True)
    monkeypatch.setattr(routes, "get_active_takeover", lambda _db, **_kwargs: None)

    def unavailable_recognizer() -> None:
        raise RuntimeError("model missing")

    monkeypatch.setattr(routes, "get_drug_image_recognizer", unavailable_recognizer)
    database = SimpleNamespace(rollback=lambda: None)

    with pytest.raises(routes.HTTPException) as error:
        asyncio.run(
            routes.recognize_drug_image(
                patient_id="patient-a",
                conversation_id="conversation-a",
                message="",
                file=_upload(),
                db=database,
                actor=SimpleNamespace(id="actor-a"),
            )
        )

    assert error.value.status_code == 503
    assert routes._recognition_slot.acquire(blocking=False) is True
    routes._recognition_slot.release()


def test_confirmation_binds_canonical_entity_and_queries_verified_drug_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: dict[str, object] = {}
    tool_call: dict[str, str] = {}

    class FakeStore:
        def load(self, _db, *, actor_id: str, patient_id: str, conversation_id: str):
            return ConversationState.empty(conversation_id)

        def save(self, _db, *, agent_run_id: str, actor_id: str, patient_id: str, state) -> None:
            saved["state"] = state

    class FakeTools:
        def __init__(self, _db) -> None:
            pass

        def get_drug_info(self, *, legacy_drug_id: str, query: str):
            tool_call.update(legacy_drug_id=legacy_drug_id, query=query)
            return {"results": [{"content": "Nội dung đã xác minh."}]}

    database = SimpleNamespace(add=lambda _row: None, flush=lambda: None, commit=lambda: None, rollback=lambda: None)
    monkeypatch.setattr(routes, "require_agent_patient_access", lambda _db, _actor, patient_id: patient_id)
    monkeypatch.setattr(
        routes,
        "confirm_attempt",
        lambda *_args, **_kwargs: ConfirmedCandidate(
            attempt_id="attempt-a",
            drug_product_id="canonical-product-a",
            legacy_drug_id="legacy-a",
            display_name="Thuốc A 500 mg",
            requested_attribute=None,
            already_confirmed=False,
        ),
    )
    monkeypatch.setattr(routes, "AgentConversationStateStore", lambda: FakeStore())
    monkeypatch.setattr(routes, "AgentRun", lambda **_kwargs: SimpleNamespace(id="run-a"))
    monkeypatch.setattr(routes, "AgentReadOnlyDomainTools", FakeTools)

    response = routes.confirm_drug_image_candidate(
        DrugImageConfirmRequest(
            patient_id="patient-a",
            conversation_id="conversation-a",
            recognition_attempt_id="attempt-a",
            action_id="opaque-action-a",
        ),
        db=database,
        actor=SimpleNamespace(id="actor-a"),
    )

    state = saved["state"]
    assert state.active_entity.type == "drug"
    assert state.active_entity.id == "canonical-product-a"
    assert state.active_entity.legacy_drug_id == "legacy-a"
    assert tool_call["legacy_drug_id"] == "legacy-a"
    assert "Thông tin chi tiết đã xác minh" in tool_call["query"]
    assert response.tools == ["get_drug_info"]
