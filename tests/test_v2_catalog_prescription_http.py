"""HTTP regression coverage for the V2 catalog adapter.

The public contract deliberately keeps the legacy slug as ``drug_id``.  This
test proves both the catalog route and prescription normalization resolve that
slug through Canonical V2, without requiring a seeded V1 ``drug`` table.
"""

from __future__ import annotations

import uuid

import pytest

from backend.config import get_settings
from backend.db.base import SessionLocal
from backend.db.models import DoseEvent, Patient, Prescription
from backend.services.drug_knowledge.v2_agent import get_v2_agent_knowledge_service


@pytest.mark.asyncio
async def test_v2_catalog_and_prescription_routes_keep_legacy_public_id(client, monkeypatch):
    monkeypatch.setenv("DRUG_KNOWLEDGE_BACKEND", "v2")
    get_settings.cache_clear()
    item = get_v2_agent_knowledge_service().catalog_items[0]
    patient_id = f"v2-http-{uuid.uuid4().hex[:12]}"
    db = SessionLocal()
    prescription_id: str | None = None
    try:
        db.add(Patient(id=patient_id, full_name="V2 HTTP Regression"))
        db.commit()

        catalog = await client.get("/api/v1/drugs", params={"q": item.ten_thuoc, "limit": 5})
        assert catalog.status_code == 200
        catalog_item = next(row for row in catalog.json()["items"] if row["drug_id"] == item.drug_id)
        assert catalog_item["drug_id"] == item.drug_id
        assert catalog_item["ham_luong"] == item.ham_luong

        payload = {
            "patient_id": patient_id,
            "doctor_id": "v2-http-doctor",
            "items": [
                {
                    "drug_id": item.drug_id,
                    "ten_thuoc": item.ten_thuoc,
                    "dang_thuoc": "untrusted-client-value",
                    "duong_dung": "untrusted-client-value",
                    "lieu_dung": "1 vien",
                    "gio_nhac": ["08:00"],
                }
            ],
        }
        created = await client.post("/api/v1/prescriptions", json=payload)
        assert created.status_code == 201
        created_body = created.json()
        prescription_id = created_body["id"]
        stored_item = created_body["items"][0]
        assert stored_item["drug_id"] == item.drug_id
        assert stored_item["dang_thuoc"] == item.dang_thuoc
        assert stored_item["duong_dung"] == item.duong_dung

        updated = await client.put(
            f"/api/v1/prescriptions/{prescription_id}",
            json={"doctor_id": "v2-http-doctor", "items": payload["items"], "note": "v2 adapter check"},
        )
        assert updated.status_code == 200
        assert updated.json()["items"][0]["drug_id"] == item.drug_id
    finally:
        if prescription_id:
            db.query(DoseEvent).filter(DoseEvent.prescription_id == prescription_id).delete(synchronize_session=False)
            db.query(Prescription).filter(Prescription.id == prescription_id).delete(synchronize_session=False)
        db.query(Patient).filter(Patient.id == patient_id).delete(synchronize_session=False)
        db.commit()
        db.close()
        get_settings.cache_clear()
