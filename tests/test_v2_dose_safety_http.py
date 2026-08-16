"""HTTP coverage for V2-backed dose and side-effect safety paths."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime

import pytest

from backend.agents.orchestrator import default_safety_check
from backend.api.chat_deps import ChatServices, get_chat_services
from backend.config import get_settings
from backend.db.base import SessionLocal
from backend.db.models import AuditLog, DoseEvent, Prescription
from backend.main import app
from backend.services.drug_knowledge.v2_agent import get_v2_agent_knowledge_service


@pytest.mark.asyncio
async def test_v2_http_dose_safety_paths_use_canonical_knowledge(client, monkeypatch):
    monkeypatch.setenv("DRUG_KNOWLEDGE_BACKEND", "v2")
    get_settings.cache_clear()
    drug = get_v2_agent_knowledge_service().catalog_items[0]
    patient_id = f"v2-dose-http-{uuid.uuid4().hex[:12]}"
    db = SessionLocal()
    prescription_id: str | None = None
    dose_ids: dict[str, str] = {}
    try:
        prescription = Prescription(
            patient_id=patient_id,
            doctor_id="v2-http-doctor",
            status="approved",
            items=[{"drug_id": drug.drug_id, "ten_thuoc": drug.ten_thuoc}],
            start_date="2026-08-01",
            duration_days=7,
        )
        db.add(prescription)
        db.commit()
        prescription_id = prescription.id
        for classification in ("SIDE_EFFECT", "MISSED", "DELAYED"):
            now = datetime.now(UTC)
            dose = DoseEvent(
                prescription_id=prescription.id,
                patient_id=patient_id,
                scheduled_at=now,
                window_start=now,
                window_end=now,
                status="PENDING",
                expected_items=[{"drug_id": drug.drug_id, "ten_thuoc": drug.ten_thuoc, "so_vien": 1}],
            )
            db.add(dose)
            db.commit()
            dose_ids[classification] = dose.id

        def services_for(classification: str) -> ChatServices:
            return ChatServices(
                classify_intent=lambda _text: ("dose_confirmation", 0.95),
                classify_dose=lambda _text: (classification, 0.95),
                generate_answer=lambda _text, _results: "test response",
                classify_severity=lambda _text: None,
                embed_query=lambda _text: [random.Random(42).gauss(0, 1) for _ in range(1536)],
                safety_check=default_safety_check,
                classify_drug_reply_plausibility=lambda _reply: True,
                select_fuzzy_candidate=lambda _utterance, candidates: candidates[0]["drug_id"] if candidates else None,
                classify_side_effect_match=lambda _utterance, _chunk: False,
            )

        for classification, dose_id in dose_ids.items():
            app.dependency_overrides[get_chat_services] = lambda c=classification: services_for(c)
            response = await client.post(
                "/api/v1/chat",
                json={"patient_id": patient_id, "dose_id": dose_id, "message": "dose safety regression"},
            )
            assert response.status_code == 200
            audit = db.query(AuditLog).filter(AuditLog.patient_id == patient_id).order_by(AuditLog.created_at.desc()).first()
            assert audit is not None
            trace = audit.trace
            if classification == "SIDE_EFFECT":
                entry = next(item for item in trace if item.get("step") == "side_effect_audit")
                assert entry["knowledge_backend"] == "v2"
            else:
                entry = next(item for item in trace if item.get("step") == "severity_assessment")
                assert entry["source_status"] == "REVIEW_REQUIRED"
                assert entry["source_field_groups"] == ["INDICATION", "ADVERSE_EFFECT"]
    finally:
        app.dependency_overrides.clear()
        db.query(AuditLog).filter(AuditLog.patient_id == patient_id).delete(synchronize_session=False)
        if prescription_id:
            db.query(DoseEvent).filter(DoseEvent.prescription_id == prescription_id).delete(synchronize_session=False)
            db.query(Prescription).filter(Prescription.id == prescription_id).delete(synchronize_session=False)
        db.commit()
        db.close()
        get_settings.cache_clear()
