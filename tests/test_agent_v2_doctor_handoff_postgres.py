"""Opt-in PostgreSQL serialization test for BUILD-10 Doctor Handoff.

Set ``BUILD10_TEST_DATABASE_URL`` only to a disposable database already
migrated to 0032.  It never falls back to the developer database.
"""

from __future__ import annotations

import os
import threading
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.db.models import Account, DoctorReviewRequest, Patient
from backend.services.doctor_handoff import (
    HandoffCreateCommand,
    VerifiedContextRef,
    VerifiedContextSource,
    create_doctor_review_request,
)

DATABASE_URL = os.getenv("BUILD10_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="Set BUILD10_TEST_DATABASE_URL to a disposable migrated PostgreSQL database.",
)
NOW = datetime(2026, 8, 18, tzinfo=UTC)


def test_postgres_handoff_retry_serializes_on_unique_idempotency_key() -> None:
    assert DATABASE_URL is not None
    engine = create_engine(DATABASE_URL, pool_size=3, max_overflow=0)
    suffix = uuid4().hex
    patient_id = f"build10-patient-{suffix}"
    doctor_id = f"build10-doctor-{suffix}"
    account_id = f"build10-account-{suffix}"
    command = HandoffCreateCommand(
        patient_id=patient_id,
        actor_id=f"build10-actor-{suffix}",
        patient_question="Can bac si xem xet.",
        reason_code="NO_POLICY_SAFE_FALLBACK",
        risk_disposition="HANDOFF_REQUIRED",
        idempotency_key=f"build10-run:{suffix}",
        verified_context_refs=(
            VerifiedContextRef(VerifiedContextSource.SAFETY_DOMAIN, f"assessment-{suffix}", "safety-domain:test"),
        ),
    )
    try:
        with Session(engine) as setup, setup.begin():
            setup.add(Patient(id=patient_id, full_name="Build10 Patient", doctor_id=doctor_id))
            setup.add(
                Account(
                    id=account_id,
                    full_name="Build10 Doctor",
                    email=f"{account_id}@example.local",
                    password_hash="not-a-password",
                    role="doctor",
                    doctor_id=doctor_id,
                    status="active",
                )
            )

        first_session = Session(engine, expire_on_commit=False)
        first_transaction = first_session.begin()
        first = create_doctor_review_request(first_session, command=command, created_at=NOW)
        finished = threading.Event()
        worker_result: dict[str, object] = {}

        def retry_in_second_session() -> None:
            with Session(engine, expire_on_commit=False) as second, second.begin():
                worker_result["result"] = create_doctor_review_request(second, command=command, created_at=NOW)
            finished.set()

        worker = threading.Thread(target=retry_in_second_session)
        worker.start()
        assert not finished.wait(timeout=0.25), "retry did not wait for the first transaction"
        first_transaction.commit()
        first_session.close()
        worker.join(timeout=5)
        assert finished.is_set(), "retry did not complete after first commit"
        second = worker_result["result"]
        assert first.created is True
        assert second.created is False

        with Session(engine) as verify:
            assert verify.execute(
                select(func.count()).select_from(DoctorReviewRequest).where(DoctorReviewRequest.patient_id == patient_id)
            ).scalar_one() == 1
    finally:
        with Session(engine) as cleanup, cleanup.begin():
            cleanup.query(DoctorReviewRequest).filter(DoctorReviewRequest.patient_id == patient_id).delete(synchronize_session=False)
            cleanup.query(Account).filter(Account.id == account_id).delete(synchronize_session=False)
            cleanup.query(Patient).filter(Patient.id == patient_id).delete(synchronize_session=False)
        engine.dispose()
