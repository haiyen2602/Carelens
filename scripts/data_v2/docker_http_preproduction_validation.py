"""Exercise catalog and prescription routes over real container HTTP.

This script is copied into the validation container and intentionally uses
loopback HTTP rather than ASGI transport. It seeds one disposable Patient only
because prescription validation requires an existing patient record.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.config import get_settings  # noqa: E402
from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import DoseEvent, Patient, Prescription  # noqa: E402
from backend.services.drug_knowledge.v2_agent import get_v2_agent_knowledge_service  # noqa: E402

BASE_URL = os.environ.get("VALIDATION_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def _request(method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    settings = get_settings()
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(
        f"{BASE_URL}{path}",
        data=payload,
        method=method,
        headers={
            "X-Internal-Secret": settings.internal_auth_secret,
            "Content-Type": "application/json",
        },
    )
    with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed local validation URL
        return response.status, json.loads(response.read().decode("utf-8"))


def main() -> None:
    catalog_item = get_v2_agent_knowledge_service().catalog_items[0]
    patient_id = f"docker-v2-validation-{uuid.uuid4().hex[:12]}"
    prescription_id: str | None = None
    db = SessionLocal()
    try:
        db.add(Patient(id=patient_id, full_name="Docker V2 Validation"))
        db.commit()

        catalog_status, catalog = _request("GET", f"/api/v1/drugs?{urlencode({'q': catalog_item.ten_thuoc, 'limit': 5})}")
        matched = next(item for item in catalog["items"] if item["drug_id"] == catalog_item.drug_id)
        assert catalog_status == 200
        assert matched["drug_id"] == catalog_item.drug_id
        assert matched["ham_luong"] == catalog_item.ham_luong

        item = {
            "drug_id": catalog_item.drug_id,
            "ten_thuoc": catalog_item.ten_thuoc,
            "dang_thuoc": "untrusted-client-value",
            "duong_dung": "untrusted-client-value",
            "lieu_dung": "1 vien",
            "gio_nhac": ["08:00"],
        }
        create_status, created = _request(
            "POST",
            "/api/v1/prescriptions",
            {"patient_id": patient_id, "doctor_id": "docker-v2-doctor", "items": [item]},
        )
        prescription_id = created["id"]
        assert create_status == 201
        assert created["items"][0]["drug_id"] == catalog_item.drug_id
        assert created["items"][0]["dang_thuoc"] == catalog_item.dang_thuoc
        assert created["items"][0]["duong_dung"] == catalog_item.duong_dung

        update_status, updated = _request(
            "PUT",
            f"/api/v1/prescriptions/{prescription_id}",
            {"doctor_id": "docker-v2-doctor", "items": [item], "note": "docker validation"},
        )
        assert update_status == 200
        assert updated["items"][0]["drug_id"] == catalog_item.drug_id
        print(
            json.dumps(
                {
                    "catalog_status": catalog_status,
                    "prescription_create_status": create_status,
                    "prescription_update_status": update_status,
                    "public_drug_id": catalog_item.drug_id,
                },
                sort_keys=True,
            )
        )
    finally:
        if prescription_id:
            db.query(DoseEvent).filter(DoseEvent.prescription_id == prescription_id).delete(synchronize_session=False)
            db.query(Prescription).filter(Prescription.id == prescription_id).delete(synchronize_session=False)
        db.query(Patient).filter(Patient.id == patient_id).delete(synchronize_session=False)
        db.commit()
        db.close()


if __name__ == "__main__":
    main()
