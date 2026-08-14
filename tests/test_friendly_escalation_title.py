"""Vong 4 - friendly_escalation_title() (backend/services/escalation.py) PHAI
KHONG BAO GIO tra ve chuoi ky thuat (vd chua "SEVERITY="/"classification="/
"BR-") - man hinh nguoi than can tieu de NGAN, DE HIEU, khac han `Escalation.
reason` (chuoi audit noi bo). PURE FUNCTION - khong DB/API."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from backend.services.escalation import (  # noqa: E402
    TRIGGER_MISSED_DOSE,
    TRIGGER_PHOTO_MISMATCH,
    TRIGGER_SAFETY_REDFLAG,
    TRIGGER_SIDE_EFFECT,
    friendly_escalation_title,
)

ALL_TRIGGERS = (TRIGGER_MISSED_DOSE, TRIGGER_SIDE_EFFECT, TRIGGER_SAFETY_REDFLAG, TRIGGER_PHOTO_MISMATCH)
ALL_SEVERITIES = ("LOW", "MEDIUM", "HIGH")

_TECHNICAL_MARKERS = ("SEVERITY=", "classification=", "BR-", "llm_reasoning=", "llm_category=", "nhom_keyword=")


@pytest.mark.parametrize("trigger", ALL_TRIGGERS)
@pytest.mark.parametrize("severity", ALL_SEVERITIES)
def test_never_leaks_technical_reason_format(trigger: str, severity: str) -> None:
    """Bug thuc te da xay ra (man hinh /patient/family/{id}): title tung la
    `e.reason` nguyen van, lo chuoi kieu "SEVERITY=Trung bình tu
    classification='SIDE_EFFECT' (BR-3.1-3.6)" ra nguoi than. Test nay khoa
    dung dau hieu da gay loi, khong chi kiem tra 1 case rieng le."""
    title = friendly_escalation_title(trigger, severity)
    for marker in _TECHNICAL_MARKERS:
        assert marker not in title, f"title vẫn lộ chuỗi kỹ thuật ({marker!r}): {title!r}"


@pytest.mark.parametrize("trigger", ALL_TRIGGERS)
@pytest.mark.parametrize("severity", ALL_SEVERITIES)
def test_known_combination_returns_non_empty_short_title(trigger: str, severity: str) -> None:
    """4 trigger x 3 severity hien co (api-contracts.md §6) deu phai co tieu
    de cu the, khong roi vao fallback chung chung "Có cảnh báo mới cần bạn
    xem" - fallback chi danh cho to hop CHUA BIET (test rieng ben duoi)."""
    title = friendly_escalation_title(trigger, severity)
    assert title
    assert title != "Có cảnh báo mới cần bạn xem"
    assert len(title) <= 60  # "ngan gon" - man hinh danh sach, khong phai doan van


def test_unknown_combination_falls_back_safely_instead_of_crashing() -> None:
    """Du lieu cu/trigger moi phat sinh sau nay khong duoc lam sap man hinh
    nguoi than - fail-safe ve 1 cau chung chung thay vi raise/KeyError."""
    assert friendly_escalation_title("trigger_chua_biet", "HIGH") == "Có cảnh báo mới cần bạn xem"


def test_missed_dose_high_matches_known_bug_screenshot_case() -> None:
    """Regression dung case da gap thuc te (SEVERITY=Trung bình -> MEDIUM
    trong bao cao goc, nhung ca HIGH cung phai sach tuong tu) - khoa 1 gia
    tri cu the, khong chi kiem tra 'khong chua ky tu la'."""
    assert friendly_escalation_title(TRIGGER_MISSED_DOSE, "HIGH") == "Bỏ lỡ liều thuốc – mức nguy hiểm"


def test_side_effect_medium_matches_known_bug_screenshot_case() -> None:
    """Dung case xuat hien trong anh chup man hinh bao loi ("SEVERITY=Trung
    bình tu classification=...", trigger=side_effect, severity=MEDIUM)."""
    assert friendly_escalation_title(TRIGGER_SIDE_EFFECT, "MEDIUM") == "Nghi ngờ tác dụng phụ – cần theo dõi"


def test_photo_mismatch_is_short_and_stable_regardless_of_severity() -> None:
    """_escalate_photo_mismatch() (photo_verification/verifier.py) luon dung
    severity='Trung bình' (-> 'MEDIUM') that su, nhung title khong duoc phu
    thuoc vao severity chua tung xay ra trong thuc te de tranh crash neu du
    lieu cu/khac phat sinh."""
    titles = {friendly_escalation_title(TRIGGER_PHOTO_MISMATCH, s) for s in ALL_SEVERITIES}
    assert titles == {"Ảnh xác nhận uống thuốc không khớp"}
