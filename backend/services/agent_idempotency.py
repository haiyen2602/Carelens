"""BUILD-22: HTTP-level idempotency for /agent/v2/orchestrate.

This is a genuinely different concern from ``backend.services.agent_checkpoint``
(crash-recovery resume of an in-flight run, proven end to end by BUILD-12/
18B/19B): that layer lets a *new worker* safely continue a run interrupted
mid-flight. Calling ``AgentOrchestrator.run()`` again for an ``agent_run_id``
that is already terminal raises ``CheckpointTerminalError`` by design --
there is nothing left to resume. This module exists so a caller's *retried
HTTP request* for an already-finished run gets back the exact same response
without the orchestrator ever running a second time: it must intercept a
duplicate *before* the orchestrator is invoked at all.

Binding and isolation
----------------------
The deterministic ``agent_run_id`` returned by ``claim_or_replay`` is derived
from ``(actor_id, patient_id, idempotency_key)`` together (see
``derive_agent_run_id``). An identical key string supplied by a different
actor, or for a different patient, deterministically maps to a completely
different id -- it can never collide with, resume, or read another actor's
or patient's run. The unique constraint on
``agent_idempotency_key(actor_id, patient_id, idempotency_key)`` is the same
binding enforced at the database level.

Concurrency
-----------
``claim_or_replay`` inserts a claim row inside a savepoint (mirroring
``backend.services.doctor_handoff.create_doctor_review_request``). A
genuinely concurrent duplicate's ``INSERT`` blocks at the database level on
the still-uncommitted conflicting row until the owning request's *single*
outer transaction commits or rolls back (see
``backend/api/agent_v2_routes.py``: the route commits exactly once, after
``record_completion`` has already flipped the row to ``COMPLETED`` in the
same transaction) -- so by the time a blocked duplicate's ``INSERT`` unblocks
and raises ``IntegrityError``, the row it then reads is always in one of
exactly two states: fully committed and ``COMPLETED``, or (if the owner's
transaction rolled back instead) simply gone, letting the duplicate claim it
fresh. A plain, unlocked ``SELECT`` after catching ``IntegrityError`` is
therefore sufficient; no ``SELECT ... FOR UPDATE`` polling is needed. The
defensive ``IdempotencyBusyError`` branch below exists only to fail closed
(never to silently re-run) if that invariant is ever violated by a future
change.

TTL / replay policy
--------------------
A claim older than ``ttl_seconds`` (``Settings.agent_idempotency_ttl_seconds``,
default 24h) is treated as expired: the stale row is deleted and the same
key string starts a brand new, independent run rather than replaying a stale
result forever.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import AgentIdempotencyKey

_MAX_CLAIM_ATTEMPTS = 3


class IdempotencyError(RuntimeError):
    """Safe idempotency failure; callers must not expose internal state."""


class IdempotencyBusyError(IdempotencyError):
    """A claim row exists but is not yet COMPLETED and not expired.

    Under normal operation this should be unreachable (see module docstring);
    it exists so an unexpected state fails closed instead of silently
    re-running the request or returning a partial/garbage response.
    """


def derive_agent_run_id(*, actor_id: str, patient_id: str, idempotency_key: str) -> str:
    """Deterministic id bound to (actor, patient, key).

    Same tuple -> same id, always; a different actor or patient with the
    identical key string -> a completely different id. This is what makes
    cross-actor/cross-patient replay structurally impossible rather than
    merely policy-checked.
    """
    return str(uuid5(NAMESPACE_URL, f"vmec04:agent-v2:idempotency:{actor_id}:{patient_id}:{idempotency_key}"))


@dataclass(frozen=True)
class IdempotencyClaim:
    agent_run_id: str
    is_replay: bool
    cached_response: dict | None = None


def _utc(value: datetime) -> datetime:
    """Strict: validates a caller-supplied timestamp (``now=``)."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("idempotency timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _as_utc(value: datetime) -> datetime:
    """Lenient: coerces a value just read back from the database. SQLite (unit
    tests only; production is Postgres) does not preserve tzinfo on a
    ``DateTime(timezone=True)`` column, so a naive value here is always
    treated as already-UTC rather than rejected -- mirrors
    ``backend.services.agent_checkpoint._as_utc``."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _existing(db: Session, *, actor_id: str, patient_id: str, idempotency_key: str) -> AgentIdempotencyKey | None:
    for row in db.new:
        if (
            isinstance(row, AgentIdempotencyKey)
            and row.actor_id == actor_id
            and row.patient_id == patient_id
            and row.idempotency_key == idempotency_key
        ):
            return row
    return db.execute(
        select(AgentIdempotencyKey).where(
            AgentIdempotencyKey.actor_id == actor_id,
            AgentIdempotencyKey.patient_id == patient_id,
            AgentIdempotencyKey.idempotency_key == idempotency_key,
        )
    ).scalar_one_or_none()


def claim_or_replay(
    db: Session,
    *,
    actor_id: str,
    patient_id: str,
    idempotency_key: str,
    ttl_seconds: int,
    now: datetime | None = None,
) -> IdempotencyClaim:
    """Claim ownership of a new run, or return a prior completed retry's result.

    Never invokes or waits on the orchestrator itself -- this only manages
    the claim row. The caller (the route) is responsible for calling
    ``record_completion`` before its own single commit when ``is_replay`` is
    ``False``.
    """
    if ttl_seconds <= 0:
        raise ValueError("idempotency ttl_seconds must be positive")
    if not actor_id or not patient_id or not idempotency_key:
        raise ValueError("actor_id, patient_id, and idempotency_key are all required")
    at = _utc(now or datetime.now(UTC))
    agent_run_id = derive_agent_run_id(actor_id=actor_id, patient_id=patient_id, idempotency_key=idempotency_key)

    for _attempt in range(_MAX_CLAIM_ATTEMPTS):
        existing = _existing(db, actor_id=actor_id, patient_id=patient_id, idempotency_key=idempotency_key)
        if existing is not None:
            if _as_utc(existing.expires_at) <= at:
                db.execute(delete(AgentIdempotencyKey).where(AgentIdempotencyKey.id == existing.id))
                db.flush()
                continue
            if existing.status == "COMPLETED":
                return IdempotencyClaim(existing.agent_run_id, is_replay=True, cached_response=existing.response_json)
            raise IdempotencyBusyError("a duplicate request for this idempotency key is already in progress")

        row = AgentIdempotencyKey(
            actor_id=actor_id,
            patient_id=patient_id,
            idempotency_key=idempotency_key,
            agent_run_id=agent_run_id,
            status="IN_PROGRESS",
            response_json=None,
            created_at=at,
            expires_at=at + timedelta(seconds=ttl_seconds),
        )
        # The savepoint preserves the enclosing request transaction when a
        # concurrent duplicate wins the unique (actor, patient, key) index --
        # see module docstring for why a plain re-read after this is safe.
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
        except IntegrityError:
            continue
        return IdempotencyClaim(agent_run_id, is_replay=False, cached_response=None)

    raise IdempotencyError("could not claim idempotency key after retrying contention")


def record_completion(
    db: Session,
    *,
    actor_id: str,
    patient_id: str,
    idempotency_key: str,
    response: dict,
) -> None:
    """Flip an owned claim to COMPLETED with the response a replay must return.

    Must be called (and flushed) before the route's own single commit, in the
    same transaction as the claim insert -- see module docstring.
    """
    existing = _existing(db, actor_id=actor_id, patient_id=patient_id, idempotency_key=idempotency_key)
    if existing is None:
        raise IdempotencyError("idempotency claim was not found to complete")
    existing.status = "COMPLETED"
    existing.response_json = response
    db.flush()


__all__ = [
    "IdempotencyBusyError",
    "IdempotencyClaim",
    "IdempotencyError",
    "claim_or_replay",
    "derive_agent_run_id",
    "record_completion",
]
