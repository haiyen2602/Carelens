"""BUILD-46 Fix B: cross-run handoff dedup must never reuse across
incompatible handoff types.

Root cause (found live during BUILD-44's own production validation, not
fixed there -- see memory agent-v2-handoff-dedup-type-bug):
``AuthorizedDoctorHandoffAdapter.create``'s reuse-check ``if`` guard only
ever gates on the INCOMING command's own ``risk_disposition`` ("is this
an Answerability-Gate-sourced command allowed to reuse at all"), but
``"UNCERTAINTY_HANDOFF"`` is the same literal, hardcoded value BOTH a
genuine UNCERTAINTY handoff and a USER_REQUEST handoff are created with
(``handoff.py::create_for_uncertainty`` -- USER_REQUEST vs UNCERTAINTY is
a DERIVED display distinction computed from ``reason_code`` via
``answerability.handoff_type_for``, never its own stored disposition).
The candidate query itself matched by ``patient_id`` + open ``status``
alone, with NO filter on the EXISTING row's own type -- so it could
return a genuinely open SAFETY handoff as the "reused" result for a
brand new USER_REQUEST/UNCERTAINTY trigger. Confirmed live: a
USER_REQUEST message reused a real 2-day-old SAFETY
(ACUTE_DANGER_DETECTED) handoff.

Fix: derive the canonical ``HandoffType`` for both the incoming command
and every open candidate via the SAME existing ``handoff_type_for``
(never a second, parallel derivation) and only reuse a type-matching
candidate.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from backend.agents.v2.handoff import HandoffCreateCommand as AgentHandoffCreateCommand
from backend.api.security import CurrentUser
from backend.db.models import Account, CaregiverLink, DoctorReviewRequest, DoctorWatch, Patient
from backend.services.agent_doctor_handoff import AuthorizedDoctorHandoffAdapter
from backend.services.doctor_handoff import HandoffStatus

NOW = datetime(2026, 8, 27, tzinfo=UTC)
PATIENT_ID = "patient-1"
ACTOR_ID = "acct-1"

TABLES = (Patient.__table__, Account.__table__, CaregiverLink.__table__, DoctorWatch.__table__, DoctorReviewRequest.__table__)


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _sqlite_btrim(connection, _record) -> None:
        connection.create_function("btrim", 1, lambda value: value.strip() if value else value, deterministic=True)

    for table in TABLES:
        table.create(engine)
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _patient(db: Session, patient_id: str = PATIENT_ID, doctor_id: str = "doctor-1") -> None:
    db.add(Patient(id=patient_id, full_name="Patient", doctor_id=doctor_id))
    db.add(
        Account(
            id=f"{doctor_id}-account",
            full_name="Doctor",
            email=f"{doctor_id}@example.local",
            password_hash="not-a-password",
            role="doctor",
            doctor_id=doctor_id,
            status="active",
        )
    )
    db.commit()


def _existing_row(
    db: Session,
    *,
    row_id: str,
    reason_code: str,
    risk_disposition: str,
    status: str = HandoffStatus.PENDING,
    patient_id: str = PATIENT_ID,
) -> None:
    db.add(
        DoctorReviewRequest(
            id=row_id,
            patient_id=patient_id,
            created_by_actor_id=ACTOR_ID,
            reason_code=reason_code,
            risk_disposition=risk_disposition,
            patient_question="q",
            agent_summary="s",
            status=status,
            idempotency_key=f"key-{row_id}",
            assigned_doctor_id="doctor-1" if status != HandoffStatus.PENDING else None,
        )
    )
    db.commit()


def _incoming(*, reason_code: str, risk_disposition: str, idempotency_key: str, patient_id: str = PATIENT_ID):
    return AgentHandoffCreateCommand(
        patient_id=patient_id,
        actor_id=ACTOR_ID,
        patient_question="another turn",
        reason_code=reason_code,
        risk_disposition=risk_disposition,
        idempotency_key=idempotency_key,
        verified_context_refs=(),
    )


def _create(db: Session, command, patient_id: str = PATIENT_ID):
    actor = CurrentUser(id=ACTOR_ID, role="patient", patient_id=patient_id, doctor_id=None)
    return AuthorizedDoctorHandoffAdapter(db, actor).create(command, created_at=NOW)


# ---------------------------------------------------------------------------
# The exact production scenario: an open SAFETY handoff must never be
# reused/mislabeled by a USER_REQUEST or UNCERTAINTY trigger.
# ---------------------------------------------------------------------------


def test_safety_handoff_open_then_user_request_does_not_reuse_or_mislabel_it(db):
    _patient(db)
    _existing_row(
        db, row_id="safety-1", reason_code="ACUTE_DANGER_DETECTED", risk_disposition="HANDOFF_REQUIRED"
    )
    result = _create(
        db,
        _incoming(reason_code="EXPLICIT_DOCTOR_REQUEST", risk_disposition="UNCERTAINTY_HANDOFF", idempotency_key="k2"),
    )
    assert result.request_id != "safety-1"
    assert result.created is True
    assert db.execute(select(func.count()).select_from(DoctorReviewRequest)).scalar_one() == 2


def test_safety_handoff_open_then_uncertainty_does_not_reuse_or_mislabel_it(db):
    _patient(db)
    _existing_row(
        db, row_id="safety-1", reason_code="POSSIBLE_OVERDOSE_REPORTED", risk_disposition="HANDOFF_REQUIRED"
    )
    result = _create(
        db,
        _incoming(reason_code="REPEATED_CLARIFICATION", risk_disposition="UNCERTAINTY_HANDOFF", idempotency_key="k2"),
    )
    assert result.request_id != "safety-1"
    assert result.created is True
    assert db.execute(select(func.count()).select_from(DoctorReviewRequest)).scalar_one() == 2


# ---------------------------------------------------------------------------
# USER_REQUEST and UNCERTAINTY share the SAME literal risk_disposition
# ("UNCERTAINTY_HANDOFF") -- they are only told apart by reason_code. Must
# not cross-reuse each other either.
# ---------------------------------------------------------------------------


def test_uncertainty_open_then_user_request_does_not_cross_reuse(db):
    _patient(db)
    _existing_row(db, row_id="unc-1", reason_code="REPEATED_CLARIFICATION", risk_disposition="UNCERTAINTY_HANDOFF")
    result = _create(
        db,
        _incoming(reason_code="EXPLICIT_DOCTOR_REQUEST", risk_disposition="UNCERTAINTY_HANDOFF", idempotency_key="k2"),
    )
    assert result.request_id != "unc-1"
    assert result.created is True


def test_user_request_open_then_uncertainty_does_not_cross_reuse(db):
    _patient(db)
    _existing_row(db, row_id="ur-1", reason_code="EXPLICIT_DOCTOR_REQUEST", risk_disposition="UNCERTAINTY_HANDOFF")
    result = _create(
        db,
        _incoming(reason_code="REPEATED_CLARIFICATION", risk_disposition="UNCERTAINTY_HANDOFF", idempotency_key="k2"),
    )
    assert result.request_id != "ur-1"
    assert result.created is True


# ---------------------------------------------------------------------------
# Same-type reuse must still work (the pre-BUILD-46 feature this fix must
# not regress).
# ---------------------------------------------------------------------------


def test_same_type_user_request_repeated_reuses_existing_row(db):
    _patient(db)
    _existing_row(db, row_id="ur-1", reason_code="EXPLICIT_DOCTOR_REQUEST", risk_disposition="UNCERTAINTY_HANDOFF")
    result = _create(
        db,
        _incoming(reason_code="EXPLICIT_DOCTOR_REQUEST", risk_disposition="UNCERTAINTY_HANDOFF", idempotency_key="k2"),
    )
    assert result.request_id == "ur-1"
    assert result.created is False
    assert db.execute(select(func.count()).select_from(DoctorReviewRequest)).scalar_one() == 1


def test_same_type_uncertainty_repeated_reuses_existing_row(db):
    _patient(db)
    _existing_row(db, row_id="unc-1", reason_code="REPEATED_CLARIFICATION", risk_disposition="UNCERTAINTY_HANDOFF")
    result = _create(
        db,
        _incoming(reason_code="REPEATED_CLARIFICATION", risk_disposition="UNCERTAINTY_HANDOFF", idempotency_key="k2"),
    )
    assert result.request_id == "unc-1"
    assert result.created is False


def test_active_status_same_type_still_reuses_per_existing_lifecycle_policy(db):
    """BUILD-44's own ACTIVE-status reuse behavior must survive this fix
    unchanged -- same scenario as the pre-existing
    test_adapter_reuses_an_active_uncertainty_handoff_instead_of_duplicating,
    re-asserted here under the new type-aware code path, plus a
    USER_REQUEST-type variant that test did not cover."""
    _patient(db)
    _existing_row(
        db,
        row_id="ur-active-1",
        reason_code="EXPLICIT_DOCTOR_REQUEST",
        risk_disposition="UNCERTAINTY_HANDOFF",
        status=HandoffStatus.ACTIVE,
    )
    result = _create(
        db,
        _incoming(reason_code="EXPLICIT_DOCTOR_REQUEST", risk_disposition="UNCERTAINTY_HANDOFF", idempotency_key="k2"),
    )
    assert result.request_id == "ur-active-1"
    assert result.created is False


# ---------------------------------------------------------------------------
# RESOLVED/CANCELLED (a closed episode) must never be reused, same-type or
# not -- an explicit spec test.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("closed_status", [HandoffStatus.RESOLVED, HandoffStatus.CANCELLED])
def test_resolved_or_cancelled_same_type_is_not_reused(db, closed_status):
    _patient(db)
    _existing_row(
        db,
        row_id="closed-1",
        reason_code="EXPLICIT_DOCTOR_REQUEST",
        risk_disposition="UNCERTAINTY_HANDOFF",
        status=closed_status,
    )
    result = _create(
        db,
        _incoming(reason_code="EXPLICIT_DOCTOR_REQUEST", risk_disposition="UNCERTAINTY_HANDOFF", idempotency_key="k2"),
    )
    assert result.request_id != "closed-1"
    assert result.created is True


# ---------------------------------------------------------------------------
# Patient isolation: an open, type-matching row for a DIFFERENT patient must
# never be reused.
# ---------------------------------------------------------------------------


def test_open_same_type_row_for_a_different_patient_is_never_reused(db):
    _patient(db, patient_id="patient-1", doctor_id="doctor-1")
    _patient(db, patient_id="patient-2", doctor_id="doctor-2")
    _existing_row(
        db,
        row_id="other-patient-1",
        reason_code="EXPLICIT_DOCTOR_REQUEST",
        risk_disposition="UNCERTAINTY_HANDOFF",
        patient_id="patient-2",
    )
    result = _create(
        db,
        _incoming(reason_code="EXPLICIT_DOCTOR_REQUEST", risk_disposition="UNCERTAINTY_HANDOFF", idempotency_key="k2", patient_id="patient-1"),
        patient_id="patient-1",
    )
    assert result.request_id != "other-patient-1"
    assert result.created is True
    assert db.execute(
        select(func.count()).select_from(DoctorReviewRequest).where(DoctorReviewRequest.patient_id == "patient-1")
    ).scalar_one() == 1


# ---------------------------------------------------------------------------
# A more recent, type-INCOMPATIBLE row must be skipped in favor of an
# older, type-COMPATIBLE one -- proves the fix filters by type, not just
# takes the single most recent active row (the pre-fix behavior).
# ---------------------------------------------------------------------------


def test_skips_a_more_recent_incompatible_row_to_reuse_an_older_compatible_one(db):
    _patient(db)
    _existing_row(db, row_id="unc-older", reason_code="REPEATED_CLARIFICATION", risk_disposition="UNCERTAINTY_HANDOFF")
    _existing_row(
        db, row_id="safety-newer", reason_code="ACUTE_DANGER_DETECTED", risk_disposition="HANDOFF_REQUIRED"
    )
    result = _create(
        db,
        _incoming(reason_code="REPEATED_CLARIFICATION", risk_disposition="UNCERTAINTY_HANDOFF", idempotency_key="k3"),
    )
    assert result.request_id == "unc-older"
    assert result.created is False
