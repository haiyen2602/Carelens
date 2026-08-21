"""Opt-in PostgreSQL row-lock validation for BUILD-12 checkpoints.

Set ``BUILD12_TEST_DATABASE_URL`` only to a migrated local/disposable database.
The test writes unique synthetic IDs and deletes them in ``finally``.
"""

from __future__ import annotations

import os
import threading
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.db.models import AgentRun, AgentRunCheckpoint
from backend.services.agent_checkpoint import (
    CheckpointBusyError,
    CheckpointCreateCommand,
    claim_resume,
    create_or_load_checkpoint,
)

DATABASE_URL = os.getenv("BUILD12_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="Set BUILD12_TEST_DATABASE_URL to a disposable migrated PostgreSQL database.",
)


def test_postgres_concurrent_resume_serializes_on_checkpoint_row_lock() -> None:
    assert DATABASE_URL is not None
    engine = create_engine(DATABASE_URL, pool_size=3, max_overflow=0)
    run_id = f"build12-run-{uuid4().hex}"
    now = datetime(2026, 8, 18, tzinfo=UTC)
    command = CheckpointCreateCommand(run_id, f"patient-{run_id}", f"conversation-{run_id}", None, "TEST")
    try:
        with Session(engine) as setup, setup.begin():
            create_or_load_checkpoint(setup, command=command, now=now)

        first = Session(engine, expire_on_commit=False)
        first_transaction = first.begin()
        claim_resume(first, agent_run_id=run_id, max_age=timedelta(minutes=1), now=now)
        finished = threading.Event()
        worker_result: dict[str, object] = {}

        def resume_in_second_session() -> None:
            try:
                with Session(engine, expire_on_commit=False) as second, second.begin():
                    claim_resume(
                        second,
                        agent_run_id=run_id,
                        max_age=timedelta(minutes=1),
                        now=now,
                    )
            except CheckpointBusyError:
                worker_result["busy"] = True
            finally:
                finished.set()

        worker = threading.Thread(target=resume_in_second_session)
        worker.start()
        assert not finished.wait(timeout=0.25), "second resume did not wait for row lock"
        first_transaction.commit()
        first.close()
        worker.join(timeout=5)
        assert finished.is_set()
        assert worker_result == {"busy": True}

        with Session(engine) as verify:
            checkpoint = verify.execute(
                select(AgentRunCheckpoint).where(AgentRunCheckpoint.agent_run_id == run_id)
            ).scalar_one()
            assert checkpoint.revision == 1
            assert checkpoint.lease_token is not None
    finally:
        with Session(engine) as cleanup, cleanup.begin():
            cleanup.query(AgentRunCheckpoint).filter(AgentRunCheckpoint.agent_run_id == run_id).delete(
                synchronize_session=False
            )
            cleanup.query(AgentRun).filter(AgentRun.id == run_id).delete(synchronize_session=False)
        engine.dispose()
