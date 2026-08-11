"""Test co ban cho lop keyword cua safety layer (ADR-0009, business-rules.md
§6) - tat dinh, khong can DB/API."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services.safety import check_keyword_redflag, check_safety  # noqa: E402


def test_clinical_redflag_detected():
    flag = check_keyword_redflag("tôi uống rồi, mà từ chiều thấy khó thở với tức ngực")
    assert flag.is_redflag is True
    assert flag.matched_group == "clinical"


def test_overdose_risk_redflag_detected():
    """BR-6.7 - vi du chinh trong thiet ke: hoi ve so luong thuoc bat thuong."""
    flag = check_keyword_redflag("tôi có 10 viên thuốc ngủ, uống hết có sao không")
    assert flag.is_redflag is True
    assert flag.matched_group == "overdose_risk"


def test_normal_utterance_no_redflag():
    flag = check_keyword_redflag("tôi uống thuốc rồi, cảm ơn bác sĩ")
    assert flag.is_redflag is False


def test_llm_error_does_not_crash_keyword_layer_br_6_3():
    """BR-6.3: LLM loi/timeout khong duoc lam mat hieu luc cua keyword layer."""

    def broken_llm(utterance: str) -> bool:
        raise RuntimeError("LLM API timeout")

    flag = check_safety("tôi uống thuốc rồi", llm_classifier=broken_llm)
    assert flag.is_redflag is False  # keyword sach, LLM loi -> khong crash, tra ve sach


def test_llm_flags_when_keyword_misses():
    """OR logic (BR-6.1): keyword sach nhung LLM flag -> van la redflag."""

    def llm_that_flags(utterance: str) -> bool:
        return True

    flag = check_safety("con thấy hơi lạ trong người", llm_classifier=llm_that_flags)
    assert flag.is_redflag is True
    assert flag.source == "llm"
