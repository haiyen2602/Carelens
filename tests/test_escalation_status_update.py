"""PATCH /api/v1/escalations/{id}/status (THEM 2026-08-23) - dat trang thai
tuy y cho 1 canh bao, phuc vu 3 nut "Ghi nhận"/"Từ chối"/"Đánh dấu đã xử lý"
va nut "Hoàn tác" o Hop canh bao cua bac si.

KHAC test_escalation_ack.py: /ack chi di MOT chieu toi RESOLVED. O day quan
tam ba dieu /ack khong tra loi duoc - trang thai DISMISSED moi, chieu quay
NGUOC ve OPEN, va viec xoa resolved_at/resolved_by khi quay nguoc.

Test qua FastAPI TestClient that, DB that (cung khuon voi test_escalation_ack).
"""

import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import Escalation  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


def _seed_open_escalation(patient_id: str) -> str:
    db = SessionLocal()
    try:
        row = Escalation(
            patient_id=patient_id,
            dose_event_id=None,
            severity="MEDIUM",
            trigger="missed_dose",
            raw_utterance="test",
            reason="test escalation for status endpoint",
            status="OPEN",
            notified=["doctor"],
            reminder_count=1,
            last_reminder_at=datetime.now(UTC),
        )
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def _cleanup(patient_id: str) -> None:
    db = SessionLocal()
    try:
        db.query(Escalation).filter(Escalation.patient_id == patient_id).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _doc(esc_id: str) -> Escalation:
    db = SessionLocal()
    try:
        return db.get(Escalation, esc_id)
    finally:
        db.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["ACKED", "RESOLVED", "DISMISSED"])
async def test_set_each_closing_status(client, status):
    patient_id = f"test-status-{uuid.uuid4().hex[:8]}"
    esc_id = _seed_open_escalation(patient_id)

    try:
        response = await client.patch(f"/api/v1/escalations/{esc_id}/status", json={"status": status})
        assert response.status_code == 200
        assert response.json()["status"] == status

        row = _doc(esc_id)
        assert row.status == status
        if status == "ACKED":
            # ACKED chua phai "da chot" - khong ghi resolved_at/resolved_by.
            assert row.resolved_at is None
            assert row.resolved_by is None
        else:
            assert row.resolved_at is not None
            assert row.resolved_by == "Test caregiver caller"
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_revert_to_open_clears_resolved_fields(client):
    """Day chinh la nut "Hoàn tác": mot canh bao quay ve OPEN ma van mang
    resolved_by cua lan bam nham truoc do se hien sai o moi cho doc hai truong
    nay (vd cot "Người xử lý" trong bao cao)."""
    patient_id = f"test-status-undo-{uuid.uuid4().hex[:8]}"
    esc_id = _seed_open_escalation(patient_id)

    try:
        await client.patch(f"/api/v1/escalations/{esc_id}/status", json={"status": "RESOLVED"})
        assert _doc(esc_id).resolved_by == "Test caregiver caller"

        response = await client.patch(f"/api/v1/escalations/{esc_id}/status", json={"status": "OPEN"})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "OPEN"
        assert body["resolved_at"] is None
        assert body["resolved_by"] is None

        row = _doc(esc_id)
        assert row.status == "OPEN"
        assert row.resolved_at is None
        assert row.resolved_by is None
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_unknown_status_is_rejected(client):
    """Literal trong EscalationStatusUpdateRequest chan gia tri la - cot
    Escalation.status la String thuong (khong co CHECK ben DB) nen day la
    HANG RAO DUY NHAT giu cho cot khong lan gia tri rac."""
    patient_id = f"test-status-bad-{uuid.uuid4().hex[:8]}"
    esc_id = _seed_open_escalation(patient_id)

    try:
        response = await client.patch(f"/api/v1/escalations/{esc_id}/status", json={"status": "CANCELLED"})
        assert response.status_code == 422
        assert _doc(esc_id).status == "OPEN", "trang thai cu phai giu nguyen khi request bi tu choi"
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_nonexistent_escalation_returns_404(client):
    response = await client.patch(
        f"/api/v1/escalations/{uuid.uuid4().hex}/status", json={"status": "RESOLVED"}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_without_auth_header_is_rejected(client):
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    patient_id = f"test-status-noauth-{uuid.uuid4().hex[:8]}"
    esc_id = _seed_open_escalation(patient_id)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as unauthenticated_client:
            response = await unauthenticated_client.patch(
                f"/api/v1/escalations/{esc_id}/status", json={"status": "RESOLVED"}
            )
        assert response.status_code == 401
        assert _doc(esc_id).status == "OPEN"
    finally:
        _cleanup(patient_id)
