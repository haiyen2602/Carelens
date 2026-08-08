"""Phase 6 code review (2026-08-08): trigger_emergency_escalation() phai
BEST-EFFORT, khong ALL-OR-NOTHING - 1 kenh (family/doctor) loi KHONG duoc
lam mat ket qua cua kenh con lai, VA phai bao ro CHINH XAC kenh nao that
bai (khong gop chung thanh 1 trang thai "da escalate"). PURE test - khong
can DB that (escalate_fn gia lap)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from src.services.escalation import trigger_emergency_escalation  # noqa: E402


@pytest.mark.asyncio
async def test_one_channel_failing_does_not_lose_the_other_channels_success():
    async def flaky_escalate(target, patient_id, dose_event_id, severity, urgent, trigger, reason):
        if target == "doctor":
            raise RuntimeError("push API doctor timeout (mo phong)")
        return None

    outcome = await trigger_emergency_escalation(
        flaky_escalate, "p1", "dose-1", "Nguy hiểm", True, "safety_redflag", "test"
    )

    assert outcome.succeeded == ["family"], "kenh family thanh cong khong duoc mat di vi doctor loi"
    assert outcome.failed == {"doctor": "push API doctor timeout (mo phong)"}
    assert outcome.all_succeeded is False


@pytest.mark.asyncio
async def test_both_channels_succeed_reports_no_failures():
    async def ok_escalate(target, patient_id, dose_event_id, severity, urgent, trigger, reason):
        return None

    outcome = await trigger_emergency_escalation(ok_escalate, "p1", None, "Nguy hiểm", True, "safety_redflag", "x")

    assert set(outcome.succeeded) == {"family", "doctor"}
    assert outcome.failed == {}
    assert outcome.all_succeeded is True


@pytest.mark.asyncio
async def test_both_channels_fail_does_not_raise_and_reports_both():
    async def always_fails(target, patient_id, dose_event_id, severity, urgent, trigger, reason):
        raise ConnectionError(f"{target} unreachable")

    # KHONG duoc raise ra ngoai - request HTTP dang xu ly (co the dang tra
    # ve overlay cap cuu cho benh nhan) khong duoc crash chi vi CA HAI kenh
    # thong bao deu that bai.
    outcome = await trigger_emergency_escalation(always_fails, "p1", None, "Nguy hiểm", True, "safety_redflag", "x")

    assert outcome.succeeded == []
    assert set(outcome.failed.keys()) == {"family", "doctor"}
    assert outcome.all_succeeded is False
