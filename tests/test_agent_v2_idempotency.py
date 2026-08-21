"""BUILD-22: HTTP-level Agent V2 idempotency (backend.services.agent_idempotency).

See that module's docstring for why this is a genuinely different concern
from BUILD-12's crash-recovery checkpoint resume (tests/test_agent_v2_checkpoints.py).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.db.models import AgentIdempotencyKey
from backend.services.agent_idempotency import (
    IdempotencyBusyError,
    IdempotencyError,
    claim_or_replay,
    derive_agent_run_id,
    record_completion,
)

NOW = datetime(2026, 8, 22, 10, tzinfo=UTC)
TABLES = (AgentIdempotencyKey.__table__,)


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for table in TABLES:
        table.create(engine)
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _claim(db, actor="account-1", patient="patient-1", key="key-1", ttl=3600, now=NOW):
    return claim_or_replay(db, actor_id=actor, patient_id=patient, idempotency_key=key, ttl_seconds=ttl, now=now)


# ---------------------------------------------------------------------------
# derivation / binding
# ---------------------------------------------------------------------------


def test_derivation_is_deterministic():
    a = derive_agent_run_id(actor_id="account-1", patient_id="patient-1", idempotency_key="k")
    b = derive_agent_run_id(actor_id="account-1", patient_id="patient-1", idempotency_key="k")
    assert a == b


def test_derivation_differs_for_a_different_actor():
    a = derive_agent_run_id(actor_id="account-1", patient_id="patient-1", idempotency_key="k")
    b = derive_agent_run_id(actor_id="account-2", patient_id="patient-1", idempotency_key="k")
    assert a != b


def test_derivation_differs_for_a_different_patient():
    a = derive_agent_run_id(actor_id="account-1", patient_id="patient-1", idempotency_key="k")
    b = derive_agent_run_id(actor_id="account-1", patient_id="patient-2", idempotency_key="k")
    assert a != b


def test_a_different_actor_supplying_the_identical_key_string_never_replays_another_actors_run(db):
    owner = _claim(db, actor="account-1")
    record_completion(db, actor_id="account-1", patient_id="patient-1", idempotency_key="key-1", response={"marker": "owner"})

    other = _claim(db, actor="account-2")  # same patient, same key string, different actor
    assert other.is_replay is False
    assert other.agent_run_id != owner.agent_run_id


def test_a_different_patient_with_the_identical_key_string_never_replays_another_patients_run(db):
    owner = _claim(db, patient="patient-1")
    record_completion(db, actor_id="account-1", patient_id="patient-1", idempotency_key="key-1", response={"marker": "owner"})

    other = _claim(db, patient="patient-2")  # same actor, same key string, different patient
    assert other.is_replay is False
    assert other.agent_run_id != owner.agent_run_id


# ---------------------------------------------------------------------------
# claim -> complete -> replay
# ---------------------------------------------------------------------------


def test_first_claim_is_not_a_replay(db):
    claim = _claim(db)
    assert claim.is_replay is False
    assert claim.cached_response is None


def test_retry_before_completion_reports_busy_not_a_silent_rerun(db):
    _claim(db)  # owner claims, does not complete yet
    with pytest.raises(IdempotencyBusyError):
        _claim(db)


def test_retry_after_completion_replays_the_identical_cached_response(db):
    owner = _claim(db)
    response = {"status": "COMPLETED", "reply": "xin chao", "agent_run_id": owner.agent_run_id}
    record_completion(db, actor_id="account-1", patient_id="patient-1", idempotency_key="key-1", response=response)

    replay = _claim(db)
    assert replay.is_replay is True
    assert replay.agent_run_id == owner.agent_run_id
    assert replay.cached_response == response


def test_replay_never_invokes_the_orchestrator_again_by_construction(db):
    """The route only calls the orchestrator when ``is_replay`` is False --
    this asserts that guard's precondition holds across many retries."""
    owner = _claim(db)
    record_completion(db, actor_id="account-1", patient_id="patient-1", idempotency_key="key-1", response={"n": 1})
    for _ in range(5):
        replay = _claim(db)
        assert replay.is_replay is True
        assert replay.agent_run_id == owner.agent_run_id


def test_completion_without_a_prior_claim_fails_closed(db):
    with pytest.raises(IdempotencyError):
        record_completion(db, actor_id="account-1", patient_id="patient-1", idempotency_key="never-claimed", response={})


# ---------------------------------------------------------------------------
# TTL / replay policy
# ---------------------------------------------------------------------------


def test_within_ttl_replays(db):
    _claim(db, ttl=3600, now=NOW)
    record_completion(db, actor_id="account-1", patient_id="patient-1", idempotency_key="key-1", response={"n": 1})
    replay = _claim(db, ttl=3600, now=NOW + timedelta(minutes=59))
    assert replay.is_replay is True


def test_past_ttl_starts_a_genuinely_new_independent_run_not_a_replay(db):
    original = _claim(db, ttl=3600, now=NOW)
    record_completion(db, actor_id="account-1", patient_id="patient-1", idempotency_key="key-1", response={"n": 1})

    fresh = _claim(db, ttl=3600, now=NOW + timedelta(hours=2))
    assert fresh.is_replay is False
    # Same (actor, patient, key) still derives the same id -- a fresh run
    # under an expired key is allowed to reuse it; only the CLAIM record
    # (and hence replay eligibility) resets, not the deterministic identity.
    assert fresh.agent_run_id == original.agent_run_id


def test_expired_in_progress_claim_does_not_report_busy(db):
    """An IN_PROGRESS claim whose owner never completed it (e.g. crashed) and
    whose TTL has since elapsed must not wedge every future retry with
    IdempotencyBusyError forever."""
    _claim(db, ttl=1, now=NOW)  # never completed
    claim = _claim(db, ttl=1, now=NOW + timedelta(seconds=5))
    assert claim.is_replay is False


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["actor_id", "patient_id", "idempotency_key"])
def test_empty_required_fields_are_rejected(db, field):
    kwargs = {"actor_id": "account-1", "patient_id": "patient-1", "idempotency_key": "key-1"}
    kwargs[field] = ""
    with pytest.raises(ValueError):
        claim_or_replay(db, ttl_seconds=3600, now=NOW, **kwargs)


def test_non_positive_ttl_is_rejected(db):
    with pytest.raises(ValueError):
        _claim(db, ttl=0)
