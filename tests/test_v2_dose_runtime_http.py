"""HTTP regression for APP-4's V2 grouped-dose adapter."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time

import pytest

from backend.config import get_settings
from backend.db.base import SessionLocal
from backend.db.models import (
    Account,
    DoseEventLog,
    DoseOccurrence,
    NotificationJob,
    Patient,
    Prescription,
    PrescriptionItem,
)
from backend.services.auth import create_access_token


@pytest.mark.asyncio
async def test_v2_dose_adapter_keeps_grouped_dto_and_uses_state_domain(client, monkeypatch):
    monkeypatch.setenv("DOSE_RUNTIME_MODE", "v2")
    get_settings.cache_clear()
    patient_id = f"v2-dose-runtime-{uuid.uuid4().hex[:12]}"
    prescription_id = f"prescription-{uuid.uuid4().hex}"
    account_id = f"account-{uuid.uuid4().hex}"
    db = SessionLocal()
    try:
        db.add(Patient(id=patient_id, full_name="V2 runtime test patient"))
        db.add(
            Account(
                id=account_id,
                full_name="V2 runtime account",
                email=f"{account_id}@example.local",
                password_hash="not-a-real-hash",
                role="patient",
                status="active",
                patient_id=patient_id,
            )
        )
        db.add(
            Prescription(
                id=prescription_id,
                patient_id=patient_id,
                doctor_id="doctor-1",
                status="active",
                start_date="2026-08-17",
                duration_days=1,
                items=[
                    {"drug_id": "legacy-a", "ten_thuoc": "Drug A", "so_vien_moi_lan": 1},
                    {"drug_id": "legacy-b", "ten_thuoc": "Drug B", "so_vien_moi_lan": 2},
                ],
            )
        )
        for index, (drug_id, name, count) in enumerate((("legacy-a", "Drug A", 1), ("legacy-b", "Drug B", 2))):
            item_id = f"item-{patient_id}-{index}"
            db.add(
                PrescriptionItem(
                    id=item_id,
                    prescription_id=prescription_id,
                    patient_id=patient_id,
                    legacy_drug_id=drug_id,
                    drug_display_name=name,
                    migration_item_index=index,
                )
            )
            db.add(
                DoseOccurrence(
                    id=f"occurrence-{patient_id}-{index}",
                    prescription_item_id=item_id,
                    patient_id=patient_id,
                    scheduled_at=datetime.now(UTC),
                    scheduled_local_date=date.today(),
                    scheduled_local_time=time(8),
                    timezone="Asia/Ho_Chi_Minh",
                    status="SCHEDULED",
                    generation_key=f"runtime-group-{patient_id}-{index}",
                )
            )
        db.commit()
        token = create_access_token(sub=account_id, role="patient", patient_id=patient_id)
        headers = {"Authorization": f"Bearer {token}"}

        listed = await client.get("/api/v1/doses", params={"patient_id": patient_id})
        assert listed.status_code == 200
        groups = listed.json()
        assert len(groups) == 1
        assert groups[0]["status"] == "PENDING"
        assert [item["so_vien"] for item in groups[0]["expected_items"]] == [1, 2]

        updated = await client.patch(f"/api/v1/doses/{groups[0]['id']}", json={"status": "TAKEN"}, headers=headers)
        assert updated.status_code == 200
        assert updated.json()["status"] == "TAKEN"
        db.expire_all()
        assert {row.status for row in db.query(DoseOccurrence).filter(DoseOccurrence.patient_id == patient_id)} == {"TAKEN"}
        assert db.query(DoseEventLog).filter(DoseEventLog.patient_id == patient_id).count() == 4
    finally:
        db.query(NotificationJob).filter(NotificationJob.patient_id == patient_id).delete(synchronize_session=False)
        db.query(DoseEventLog).filter(DoseEventLog.patient_id == patient_id).delete(synchronize_session=False)
        db.query(DoseOccurrence).filter(DoseOccurrence.patient_id == patient_id).delete(synchronize_session=False)
        db.query(PrescriptionItem).filter(PrescriptionItem.patient_id == patient_id).delete(synchronize_session=False)
        db.query(Prescription).filter(Prescription.id == prescription_id).delete(synchronize_session=False)
        db.query(Account).filter(Account.id == account_id).delete(synchronize_session=False)
        db.query(Patient).filter(Patient.id == patient_id).delete(synchronize_session=False)
        db.commit()
        db.close()
        get_settings.cache_clear()
