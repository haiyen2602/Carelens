"""Opt-in PostgreSQL concurrency validation for BUILD-22 HTTP idempotency.

Set ``BUILD22_TEST_DATABASE_URL`` only to a migrated local/disposable
database (needs the ``agent_idempotency_key`` table from migration 0034).
The test writes a unique synthetic key and deletes it in ``finally``.
"""

from __future__ import annotations

import os
import threading
import time
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

from backend.db.models import AgentIdempotencyKey
from backend.services.agent_idempotency import claim_or_replay, record_completion

DATABASE_URL = os.getenv("BUILD22_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="Set BUILD22_TEST_DATABASE_URL to a disposable migrated PostgreSQL database.",
)


def test_postgres_concurrent_duplicates_serialize_to_exactly_one_owner_and_converge_on_its_result() -> None:
    assert DATABASE_URL is not None
    engine = create_engine(DATABASE_URL, pool_size=8, max_overflow=0)
    key = f"build22-key-{uuid4().hex}"
    actor_id, patient_id = f"build22-actor-{uuid4().hex}", f"build22-patient-{uuid4().hex}"
    now = datetime(2026, 8, 22, tzinfo=UTC)
    n_workers = 6
    barrier = threading.Barrier(n_workers)
    results: list[object] = [None] * n_workers
    errors: list[BaseException] = []

    def worker(idx: int) -> None:
        session = Session(engine, expire_on_commit=False)
        try:
            barrier.wait(timeout=5)  # line every worker up to race the same INSERT together
            with session.begin():
                claim = claim_or_replay(
                    session, actor_id=actor_id, patient_id=patient_id, idempotency_key=key, ttl_seconds=3600, now=now
                )
                if not claim.is_replay:
                    # Simulate real orchestration latency so the other
                    # workers' INSERTs are genuinely still blocked when this
                    # commits, not racing a near-instant no-op.
                    time.sleep(0.4)
                    record_completion(
                        session, actor_id=actor_id, patient_id=patient_id, idempotency_key=key,
                        response={"marker": "owner-result", "owner_idx": idx},
                    )
            results[idx] = claim
        except BaseException as exc:  # noqa: BLE001 -- surfaced to the assertion below
            errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=worker, args=(idx,)) for idx in range(n_workers)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"unexpected worker errors: {errors!r}"
        assert all(r is not None for r in results)

        owners = [r for r in results if not r.is_replay]
        replays = [r for r in results if r.is_replay]
        assert len(owners) == 1, "exactly one concurrent duplicate must become the owner"
        assert len(replays) == n_workers - 1

        owner_run_id = owners[0].agent_run_id
        owner_idx = results.index(owners[0])
        expected_response = {"marker": "owner-result", "owner_idx": owner_idx}
        assert all(r.agent_run_id == owner_run_id for r in results), "every caller must derive the identical run id"
        assert all(r.cached_response == expected_response for r in replays), "every duplicate must converge on the owner's exact result"
    finally:
        with Session(engine) as cleanup, cleanup.begin():
            cleanup.execute(delete(AgentIdempotencyKey).where(AgentIdempotencyKey.idempotency_key == key))
        engine.dispose()
