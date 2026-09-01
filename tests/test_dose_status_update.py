"""PATCH /api/v1/doses/{dose_id} (backend/api/dose_routes.py) - test qua
FastAPI TestClient that, DB that. Cung pattern voi tests/test_escalation_ack.py.

Cac nhanh phan quyen can kiem: patient tu sua duoc lieu cua chinh minh (khong
sua duoc cua nguoi khac), caregiver can co CaregiverLink toi dung benh nhan,
doctor sua duoc lieu cua BAT KY benh nhan nao (khong con rang buoc theo
Patient.doctor_id - bac si quan ly toan bo benh nhan qua tim kiem theo ID)."""

import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.db.models import (  # noqa: E402
    Account,
    CaregiverLink,
    DoseEvent,
    Patient,
    PatientRewardAccount,
    PatientRewardEvent,
)
from backend.services import reward_catalog as catalog  # noqa: E402
from backend.services.auth import create_access_token  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


def _seed_dose(patient_id: str, doctor_id: str | None = None) -> tuple[str, str]:
    """Tra ve (patient_id, dose_id) - tao ca Patient lan DoseEvent."""
    db = SessionLocal()
    try:
        accounts = (
            ("acct-1", "patient", patient_id),
            ("acct-2", "patient", "someone-else"),
            ("cg-account-1", "caregiver", None),
            ("cg-account-no-link", "caregiver", None),
            ("doctor-account-1", "doctor", None),
            ("doctor-account-2", "doctor", None),
        )
        for account_id, role, linked_patient_id in accounts:
            if db.get(Account, account_id) is None:
                db.add(
                    Account(
                        id=account_id,
                        full_name=f"Dose status test {account_id}",
                        email=f"{account_id}@example.local",
                        password_hash="not-a-real-hash",
                        role=role,
                        status="active",
                        patient_id=linked_patient_id,
                    )
                )
        db.add(Patient(id=patient_id, full_name="Bệnh nhân dose test", doctor_id=doctor_id))
        now = datetime.now(UTC)
        dose = DoseEvent(
            prescription_id="presc-x",
            patient_id=patient_id,
            scheduled_at=now,
            window_start=now - timedelta(minutes=30),
            window_end=now + timedelta(minutes=30),
            status="PENDING",
            expected_items=[],
        )
        db.add(dose)
        db.commit()
        dose_id = dose.id
    finally:
        db.close()
    return patient_id, dose_id


def _cleanup(patient_id: str) -> None:
    db = SessionLocal()
    try:
        db.query(PatientRewardEvent).filter(PatientRewardEvent.patient_id == patient_id).delete(
            synchronize_session=False
        )
        db.query(PatientRewardAccount).filter(PatientRewardAccount.patient_id == patient_id).delete(
            synchronize_session=False
        )
        db.query(CaregiverLink).filter(CaregiverLink.patient_id == patient_id).delete(synchronize_session=False)
        db.query(DoseEvent).filter(DoseEvent.patient_id == patient_id).delete(synchronize_session=False)
        db.query(Patient).filter(Patient.id == patient_id).delete(synchronize_session=False)
        db.query(Account).filter(
            Account.id.in_(
                (
                    "acct-1",
                    "acct-2",
                    "cg-account-1",
                    "cg-account-no-link",
                    "doctor-account-1",
                    "doctor-account-2",
                )
            )
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


@pytest.mark.asyncio
async def test_patient_updates_own_dose(client):
    patient_id = f"test-dose-{uuid.uuid4().hex[:8]}"
    _, dose_id = _seed_dose(patient_id)
    token = create_access_token(sub="acct-1", role="patient", patient_id=patient_id)

    try:
        response = await client.patch(
            f"/api/v1/doses/{dose_id}",
            json={"status": "TAKEN"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "TAKEN"
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_patient_cannot_update_others_dose(client):
    patient_id = f"test-dose-{uuid.uuid4().hex[:8]}"
    _, dose_id = _seed_dose(patient_id)
    token = create_access_token(sub="acct-2", role="patient", patient_id="someone-else")

    try:
        response = await client.patch(
            f"/api/v1/doses/{dose_id}",
            json={"status": "TAKEN"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_caregiver_with_link_can_update(client):
    patient_id = f"test-dose-{uuid.uuid4().hex[:8]}"
    _, dose_id = _seed_dose(patient_id)
    caregiver_account_id = "cg-account-1"
    db = SessionLocal()
    db.add(CaregiverLink(caregiver_account_id=caregiver_account_id, patient_id=patient_id, relationship="Con gái"))
    db.commit()
    db.close()
    token = create_access_token(sub=caregiver_account_id, role="caregiver")

    try:
        response = await client.patch(
            f"/api/v1/doses/{dose_id}",
            json={"status": "TAKEN"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_caregiver_without_link_forbidden(client):
    patient_id = f"test-dose-{uuid.uuid4().hex[:8]}"
    _, dose_id = _seed_dose(patient_id)
    token = create_access_token(sub="cg-account-no-link", role="caregiver")

    try:
        response = await client.patch(
            f"/api/v1/doses/{dose_id}",
            json={"status": "TAKEN"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_doctor_in_charge_can_update(client):
    patient_id = f"test-dose-{uuid.uuid4().hex[:8]}"
    doctor_id = "doctor-account-1"
    _, dose_id = _seed_dose(patient_id, doctor_id=doctor_id)
    token = create_access_token(sub=doctor_id, role="doctor")

    try:
        response = await client.patch(
            f"/api/v1/doses/{dose_id}",
            json={"status": "MISSED"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "MISSED"
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_other_doctor_can_update(client):
    """Bac si khong phai doctor_id cua benh nhan van thao tac duoc - khong
    con rang buoc theo Patient.doctor_id, bat ky bac si nao cung quan ly
    duoc moi benh nhan."""
    patient_id = f"test-dose-{uuid.uuid4().hex[:8]}"
    _, dose_id = _seed_dose(patient_id, doctor_id="doctor-account-1")
    token = create_access_token(sub="doctor-account-2", role="doctor")

    try:
        response = await client.patch(
            f"/api/v1/doses/{dose_id}",
            json={"status": "MISSED"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "MISSED"
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_unknown_dose_returns_404(client):
    db = SessionLocal()
    try:
        db.add(
            Account(
                id="doctor-account-1",
                full_name="Dose status test doctor",
                email="doctor-account-1@example.local",
                password_hash="not-a-real-hash",
                role="doctor",
                status="active",
            )
        )
        db.commit()
    finally:
        db.close()
    token = create_access_token(sub="doctor-account-1", role="doctor")
    try:
        response = await client.patch(
            f"/api/v1/doses/{uuid.uuid4().hex}",
            json={"status": "TAKEN"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404
    finally:
        db = SessionLocal()
        try:
            db.query(Account).filter(Account.id == "doctor-account-1").delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()


# --- Muc diem theo cach xac nhan (yeu cau nhom truong 2026-08-28) ------------
#
# Diem bi tru theo do tin cay cua CACH lieu duoc xac nhan. Trang thai CU cua
# lieu la tin hieu duy nhat con lai de suy ra dieu do (DoseEvent khong luu
# "da xac nhan bang cach nao"), nen 3 test duoi kiem dung 3 trang thai cu.


def _dat_trang_thai(dose_id: str, status: str) -> None:
    db = SessionLocal()
    try:
        db.get(DoseEvent, dose_id).status = status
        db.commit()
    finally:
        db.close()


def _diem_phat(patient_id: str) -> list[int]:
    db = SessionLocal()
    try:
        return [
            e.points_delta
            for e in db.query(PatientRewardEvent).filter(
                PatientRewardEvent.patient_id == patient_id,
                PatientRewardEvent.event_type == catalog.EVENT_DOSE_METHOD_PENALTY,
            )
        ]
    finally:
        db.close()


@pytest.mark.asyncio
async def test_tu_bao_da_uong_khong_anh_bi_tru_diem(client):
    """PENDING -> TAKEN do CHINH benh nhan bam = tu khai, khong co anh: -50%."""
    patient_id = f"test-dose-{uuid.uuid4().hex[:8]}"
    _, dose_id = _seed_dose(patient_id)
    token = create_access_token(sub="acct-1", role="patient", patient_id=patient_id)

    try:
        response = await client.patch(
            f"/api/v1/doses/{dose_id}",
            json={"status": "TAKEN"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert _diem_phat(patient_id) != []
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_nguoi_than_duyet_sau_khi_anh_lech_bi_tru_it_hon(client):
    """AWAITING_CAREGIVER -> TAKEN = co nguoi that xem anh roi duyet: chi -10%,
    tin cay hon han tu khai suong nen tru nhe hon."""
    patient_id = f"test-dose-{uuid.uuid4().hex[:8]}"
    _, dose_id = _seed_dose(patient_id)
    _dat_trang_thai(dose_id, "AWAITING_CAREGIVER")
    token = create_access_token(sub="acct-1", role="patient", patient_id=patient_id)

    try:
        response = await client.patch(
            f"/api/v1/doses/{dose_id}",
            json={"status": "TAKEN"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        phat = _diem_phat(patient_id)
        assert phat != []
        # Tru it hon truong hop tu khai o test tren (10% so voi 50% cua cung
        # mot so diem goc) - so sanh dinh tinh, khong bam vao con so tuyet doi
        # vi diem goc con phu thuoc tong so lieu trong ngay.
        assert sum(phat) > -abs(catalog.POINTS_DOSE_ON_TIME)
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_bac_si_sua_ho_ho_so_khong_bi_tru_diem(client):
    """PENDING -> TAKEN do NGUOI KHAC (bac si) bam khong phai loi tu khai cua
    benh nhan - giu nguyen 100%, khong tru."""
    patient_id = f"test-dose-{uuid.uuid4().hex[:8]}"
    _, dose_id = _seed_dose(patient_id)
    token = create_access_token(sub="doctor-account-1", role="doctor", doctor_id="doc-1")

    try:
        response = await client.patch(
            f"/api/v1/doses/{dose_id}",
            json={"status": "TAKEN"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert _diem_phat(patient_id) == []
    finally:
        _cleanup(patient_id)


# --- Xac nhan MUON: nhan DELAYED + tru them diem ---------------------------
#
# Truoc thay doi nay dose_routes.py gan thang `body.status`, ma frontend luon
# gui "TAKEN" - nen lieu xac nhan muon van duoc ghi TAKEN va van an tron diem
# "uong thuoc dung gio". Backend moi la noi duoc quyen chot nhan nay.


def _day_lieu_ve_qua_khu(dose_id: str, gio_truoc: int) -> None:
    """Doi lieu thanh da qua window nhung VAN trong ngay VN cua no."""
    db = SessionLocal()
    try:
        dose = db.get(DoseEvent, dose_id)
        moc = datetime.now(UTC) - timedelta(hours=gio_truoc)
        dose.scheduled_at = moc
        dose.window_start = moc - timedelta(minutes=30)
        dose.window_end = moc + timedelta(minutes=30)
        db.commit()
    finally:
        db.close()


@pytest.mark.asyncio
async def test_xac_nhan_muon_duoc_ghi_la_delayed(client):
    """Benh nhan bam "toi da uong" 3 tieng sau gio hen - client van gui
    "TAKEN" nhung backend phai tu chot lai thanh DELAYED."""
    patient_id = f"test-dose-{uuid.uuid4().hex[:8]}"
    _, dose_id = _seed_dose(patient_id)
    _day_lieu_ve_qua_khu(dose_id, gio_truoc=3)
    token = create_access_token(sub="acct-1", role="patient", patient_id=patient_id)

    try:
        response = await client.patch(
            f"/api/v1/doses/{dose_id}",
            json={"status": "TAKEN"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "DELAYED", "client gui TAKEN nhung da qua window"
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_xac_nhan_trong_window_van_la_taken(client):
    """Phong ve cho thay doi tren: dung gio thi KHONG duoc bi ha thanh DELAYED."""
    patient_id = f"test-dose-{uuid.uuid4().hex[:8]}"
    _, dose_id = _seed_dose(patient_id)
    token = create_access_token(sub="acct-1", role="patient", patient_id=patient_id)

    try:
        response = await client.patch(
            f"/api/v1/doses/{dose_id}",
            json={"status": "TAKEN"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "TAKEN"
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_benh_nhan_chu_dong_bo_qua_van_duoc_ton_trong(client):
    """Chi nhan xac nhan "da uong" moi bi backend chot lai. Benh nhan bam
    "bo qua lieu nay" (MISSED) la y dinh ro rang, khong duoc dien giai lai."""
    patient_id = f"test-dose-{uuid.uuid4().hex[:8]}"
    _, dose_id = _seed_dose(patient_id)
    _day_lieu_ve_qua_khu(dose_id, gio_truoc=3)
    token = create_access_token(sub="acct-1", role="patient", patient_id=patient_id)

    try:
        response = await client.patch(
            f"/api/v1/doses/{dose_id}",
            json={"status": "MISSED"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "MISSED"
    finally:
        _cleanup(patient_id)


@pytest.mark.asyncio
async def test_lieu_muon_bi_tru_nang_hon_lieu_dung_gio(client):
    """Quyet dinh san pham 2026-08-31: lieu muon con 50% diem. Cong voi muc
    tu khai khong anh (50%) thanh 25% - hai chieu doc lap nen NHAN voi nhau,
    va bang tru diem chi cho ghi MOT dong moi lieu (idempotent theo
    dose_event_id) nen buoc phai gop thanh mot ty le duy nhat."""
    dung_gio = f"test-dose-{uuid.uuid4().hex[:8]}"
    muon = f"test-dose-{uuid.uuid4().hex[:8]}"

    try:
        _, dose_dung_gio = _seed_dose(dung_gio)
        token_dung_gio = create_access_token(sub="acct-1", role="patient", patient_id=dung_gio)
        r1 = await client.patch(
            f"/api/v1/doses/{dose_dung_gio}",
            json={"status": "TAKEN"},
            headers={"Authorization": f"Bearer {token_dung_gio}"},
        )
        assert r1.status_code == 200
        phat_dung_gio = sum(_diem_phat(dung_gio))
    finally:
        _cleanup(dung_gio)

    try:
        _, dose_muon = _seed_dose(muon)
        _day_lieu_ve_qua_khu(dose_muon, gio_truoc=3)
        token_muon = create_access_token(sub="acct-1", role="patient", patient_id=muon)
        r2 = await client.patch(
            f"/api/v1/doses/{dose_muon}",
            json={"status": "TAKEN"},
            headers={"Authorization": f"Bearer {token_muon}"},
        )
        assert r2.status_code == 200
        assert r2.json()["status"] == "DELAYED"
        phat_muon = sum(_diem_phat(muon))
    finally:
        _cleanup(muon)

    # points_delta cua dong phat la so AM, nen "tru nang hon" = nho hon.
    assert phat_muon < phat_dung_gio, (
        f"lieu muon phai bi tru nang hon lieu dung gio (muon={phat_muon}, dung_gio={phat_dung_gio})"
    )
