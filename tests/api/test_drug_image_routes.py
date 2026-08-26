"""Authorization coverage for B-06 catalog image delivery."""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.api.drug_image_routes import _is_authorized_for_product
from backend.api.security import CurrentUser
from backend.db.models import (
    CaregiverLink,
    DoctorWatch,
    DoseEvent,
    DoseOccurrence,
    DrugIdMap,
    MedicationPlan,
    Patient,
    PrescriptionItem,
)


def _session() -> Session:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    for table in (
        Patient.__table__,
        CaregiverLink.__table__,
        DoctorWatch.__table__,
        DrugIdMap.__table__,
        PrescriptionItem.__table__,
        MedicationPlan.__table__,
        DoseOccurrence.__table__,
        DoseEvent.__table__,
    ):
        table.create(engine)
    return Session(engine)


def _patient_user(patient_id: str) -> CurrentUser:
    return CurrentUser(id=f"account-{patient_id}", role="patient", patient_id=patient_id, doctor_id=None)


def test_image_access_requires_exact_prescribed_canonical_product() -> None:
    session = _session()
    session.add_all(
        (
            Patient(id="patient-a", full_name="Patient A"),
            PrescriptionItem(
                id="item-a",
                prescription_id="prescription-a",
                patient_id="patient-a",
                drug_product_id="product-a",
            ),
        )
    )
    session.commit()

    assert _is_authorized_for_product(session, drug_product_id="product-a", current_user=_patient_user("patient-a"))
    assert not _is_authorized_for_product(session, drug_product_id="product-b", current_user=_patient_user("patient-a"))
    assert not _is_authorized_for_product(session, drug_product_id="product-a", current_user=_patient_user("patient-b"))


def test_image_access_accepts_only_active_legacy_mapping_in_legacy_dose() -> None:
    session = _session()
    now = datetime.now(UTC)
    session.add_all(
        (
            Patient(id="patient-a", full_name="Patient A"),
            DrugIdMap(
                id="map-active",
                legacy_drug_id="legacy-active",
                drug_product_id="product-a",
                mapping_status="ACTIVE",
                created_at=now,
                updated_at=now,
            ),
            DrugIdMap(
                id="map-retired",
                legacy_drug_id="legacy-retired",
                drug_product_id="product-b",
                mapping_status="RETIRED",
                created_at=now,
                updated_at=now,
            ),
            DoseEvent(
                id="dose-a",
                prescription_id="prescription-a",
                patient_id="patient-a",
                scheduled_at=now,
                window_start=now,
                window_end=now,
                status="PENDING",
                expected_items=[
                    {"drug_id": "legacy-active", "ten_thuoc": "Cùng tên"},
                    {"drug_id": "legacy-retired", "ten_thuoc": "Cùng tên"},
                ],
            ),
        )
    )
    session.commit()

    assert _is_authorized_for_product(session, drug_product_id="product-a", current_user=_patient_user("patient-a"))
    assert not _is_authorized_for_product(session, drug_product_id="product-b", current_user=_patient_user("patient-a"))


def test_caregiver_requires_accepted_link_for_catalog_image() -> None:
    session = _session()
    session.add_all(
        (
            Patient(id="patient-a", full_name="Patient A"),
            PrescriptionItem(
                id="item-a",
                prescription_id="prescription-a",
                patient_id="patient-a",
                drug_product_id="product-a",
            ),
            CaregiverLink(
                id="accepted",
                caregiver_account_id="caregiver-accepted",
                patient_id="patient-a",
                relationship="Con",
                status="accepted",
            ),
            CaregiverLink(
                id="pending",
                caregiver_account_id="caregiver-pending",
                patient_id="patient-a",
                relationship="Con",
                status="pending",
            ),
        )
    )
    session.commit()

    accepted = CurrentUser("caregiver-accepted", "caregiver", None, None)
    pending = CurrentUser("caregiver-pending", "caregiver", None, None)
    assert _is_authorized_for_product(session, drug_product_id="product-a", current_user=accepted)
    assert not _is_authorized_for_product(session, drug_product_id="product-a", current_user=pending)
