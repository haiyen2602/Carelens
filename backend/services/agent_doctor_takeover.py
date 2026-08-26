"""BUILD-44: doctor-identity verification + the Agent V2 bot-suppression
check for an ACTIVE doctor takeover.

Deliberately a THIN module: the actual lifecycle transitions live in
``backend.services.doctor_handoff`` (the domain service BUILD-42 already
built and this build extends); this module only answers "is Agent V2
allowed to speak for this patient right now" and "is this caller a real,
currently-active doctor account" -- the two checks the route layer and
``agent_v2_routes.py`` both need, kept in one place so they can never
drift out of sync with each other.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser
from backend.db.models import Account, DoctorReviewRequest
from backend.services.doctor_handoff import get_active_takeover

__all__ = ["get_active_takeover", "require_active_doctor"]


def require_active_doctor(db: Session, actor: CurrentUser) -> str:
    """Return the caller's own ``doctor_id`` only if they are a real,
    currently-active doctor account. Never trusts ``role``/``doctor_id``
    from a stale JWT alone -- a deactivated account must fail closed even
    if its token has not yet expired (the same discipline
    ``resolve_approved_doctor`` already applies when picking a treating
    doctor)."""
    if actor.role != "doctor" or not actor.doctor_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Khong co quyen bac si")
    account = db.get(Account, actor.id)
    if account is None or account.role != "doctor" or account.status != "active" or account.doctor_id != actor.doctor_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tai khoan bac si khong hop le")
    return actor.doctor_id


def active_takeover_for_patient(db: Session, *, patient_id: str) -> DoctorReviewRequest | None:
    """Thin re-export with the name ``agent_v2_routes.py`` reads at its own
    call site -- see ``get_active_takeover``'s own docstring for why this
    is the single source of truth for "is there an ACTIVE handoff right
    now" (patient-scoped, matching BUILD-42's own dedup scope)."""
    return get_active_takeover(db, patient_id=patient_id)
