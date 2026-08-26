"""Opt-in PostgreSQL serialization test for BUILD-42's SS12 cross-run
Answerability-Gate handoff dedup (PR #127 review, round 2).

Set ``BUILD42_TEST_DATABASE_URL`` only to a disposable database already
migrated through the Doctor Handoff / Agent V2 tables. It never falls back
to the developer database.

Regression for a real race the review correctly flagged:
``AuthorizedDoctorHandoffAdapter.create``'s same-patient active-handoff
reuse check (agent_doctor_handoff.py) is a plain check-then-act SELECT --
with no lock, two DIFFERENT concurrent agent runs for the SAME patient
(different idempotency keys, so the pre-existing unique-idempotency-key
constraint does not help) could both see no active row and both insert,
producing two handoff rows for the same uncertainty episode. Fixed by
locking the (always-present) ``Patient`` row for the duration of the
check-then-act sequence, scoped to the ``UNCERTAINTY_HANDOFF`` branch only.
"""

from __future__ import annotations

import os
import threading
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.agents.v2.handoff import HandoffCreateCommand
from backend.api.security import CurrentUser
from backend.db.models import DoctorReviewRequest, Patient
from backend.services.agent_doctor_handoff import AuthorizedDoctorHandoffAdapter

DATABASE_URL = os.getenv("BUILD42_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="Set BUILD42_TEST_DATABASE_URL to a disposable migrated PostgreSQL database.",
)
NOW = datetime(2026, 8, 26, tzinfo=UTC)


def _command(patient_id: str, actor_id: str, idempotency_key: str) -> HandoffCreateCommand:
    return HandoffCreateCommand(
        patient_id=patient_id,
        actor_id=actor_id,
        patient_question="Tôi bị đau đầu.",
        reason_code="REPEATED_CLARIFICATION",
        risk_disposition="UNCERTAINTY_HANDOFF",
        idempotency_key=idempotency_key,
        verified_context_refs=(),
    )


def test_postgres_concurrent_uncertainty_handoffs_for_the_same_patient_serialize_on_patient_row_lock() -> None:
    assert DATABASE_URL is not None
    engine = create_engine(DATABASE_URL, pool_size=3, max_overflow=0)
    suffix = uuid4().hex
    patient_id = f"build42-dedup-patient-{suffix}"
    actor_id = f"build42-dedup-account-{suffix}"
    actor = CurrentUser(id=actor_id, role="patient", patient_id=patient_id, doctor_id=None)
    try:
        with Session(engine) as setup, setup.begin():
            setup.add(Patient(id=patient_id, full_name="Build42 Dedup Patient", doctor_id=None))

        # Two DIFFERENT agent runs (distinct idempotency keys) for the SAME
        # patient -- e.g. a rapid double-send -- must still converge on one
        # row, not the unique-idempotency-key path (which only protects a
        # retry of the SAME run).
        first_session = Session(engine, expire_on_commit=False)
        first_transaction = first_session.begin()
        first = AuthorizedDoctorHandoffAdapter(first_session, actor).create(
            _command(patient_id, actor_id, f"build42-dedup-run-a-{suffix}"), created_at=NOW
        )
        finished = threading.Event()
        worker_result: dict[str, object] = {}

        def concurrent_second_run() -> None:
            with Session(engine, expire_on_commit=False) as second, second.begin():
                worker_result["result"] = AuthorizedDoctorHandoffAdapter(second, actor).create(
                    _command(patient_id, actor_id, f"build42-dedup-run-b-{suffix}"), created_at=NOW
                )
            finished.set()

        worker = threading.Thread(target=concurrent_second_run)
        worker.start()
        assert not finished.wait(timeout=0.25), "second concurrent run did not wait for the patient row lock"
        first_transaction.commit()
        first_session.close()
        worker.join(timeout=5)
        assert finished.is_set(), "second concurrent run did not complete after the first commit"

        second = worker_result["result"]
        assert first.created is True
        # The fix: the second run reuses the first's row instead of racing
        # past the (empty) reuse check and creating its own.
        assert second.created is False
        assert second.request_id == first.request_id

        with Session(engine) as verify:
            assert (
                verify.execute(
                    select(func.count()).select_from(DoctorReviewRequest).where(DoctorReviewRequest.patient_id == patient_id)
                ).scalar_one()
                == 1
            )
    finally:
        with Session(engine) as cleanup, cleanup.begin():
            cleanup.query(DoctorReviewRequest).filter(DoctorReviewRequest.patient_id == patient_id).delete(synchronize_session=False)
            cleanup.query(Patient).filter(Patient.id == patient_id).delete(synchronize_session=False)
        engine.dispose()
