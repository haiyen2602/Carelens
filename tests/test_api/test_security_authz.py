"""Tests cho RBAC, ReBAC và Security helpers trong backend/api/security.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from backend.api.security import CurrentUser, get_current_user, require_role, verify_patient_access  # noqa: E402
from backend.services.auth import create_access_token  # noqa: E402


@pytest.mark.asyncio
async def test_get_current_user_valid_jwt():
    token = create_access_token(sub="usr_doc01", role="doctor", doctor_id="doc_01")
    user = await get_current_user(authorization=f"Bearer {token}")
    assert user.id == "usr_doc01"
    assert user.role == "doctor"
    assert user.doctor_id == "doc_01"


@pytest.mark.asyncio
async def test_get_current_user_missing_header():
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(authorization=None)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_invalid_header_format():
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(authorization="Basic invalidtoken")
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_require_role_allowed_role():
    user = CurrentUser(id="usr_01", role="admin", patient_id=None, doctor_id=None)
    check_fn = require_role("admin", "doctor")
    result = await check_fn(current_user=user)
    assert result.role == "admin"


@pytest.mark.asyncio
async def test_require_role_denied_role():
    user = CurrentUser(id="usr_02", role="patient", patient_id="pat_01", doctor_id=None)
    check_fn = require_role("admin", "doctor")
    with pytest.raises(HTTPException) as exc_info:
        await check_fn(current_user=user)
    assert exc_info.value.status_code == 403


def test_verify_patient_access_admin():
    admin = CurrentUser(id="admin_1", role="admin", patient_id=None, doctor_id=None)
    assert verify_patient_access("pat_99", admin) is True


def test_verify_patient_access_patient_own():
    patient = CurrentUser(id="pat_user", role="patient", patient_id="pat_01", doctor_id=None)
    assert verify_patient_access("pat_01", patient) is True
    assert verify_patient_access("pat_02", patient) is False


def test_verify_patient_access_doctor_caregiver():
    doctor = CurrentUser(id="doc_user", role="doctor", patient_id=None, doctor_id="doc_01")
    caregiver = CurrentUser(id="cg_user", role="caregiver", patient_id=None, doctor_id=None)
    assert verify_patient_access("pat_01", doctor) is True
    assert verify_patient_access("pat_01", caregiver) is True
