"""Test lop KEYWORD (tat dinh, khong can DB/API) VA logic hop nhat check_safety()
(vong 3, muc 3 - LLM la lop chinh, regex la lop phu chay song song). Dung
fake llm_classifier (khong goi OpenAI that) de test logic hop nhat DOC LAP
voi chat luong phan loai that cua prompt - test prompt that (goi OpenAI that,
20 lan cho case bien theo kickoff-prompt-vong-3.md muc 3.4) o
tests/test_safety_llm.py rieng."""

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services.safety import check_keyword_redflag, check_safety  # noqa: E402


@dataclass
class _FakeLLMResult:
    level: str
    category: str = "none"
    reasoning: str = "test"


def test_clinical_redflag_detected():
    flag = check_keyword_redflag("tôi uống rồi, mà từ chiều thấy khó thở với tức ngực")
    assert flag.is_redflag is True
    assert flag.matched_group == "clinical"
    assert flag.level == "Nguy hiểm"


def test_overdose_risk_redflag_detected():
    """BR-6.7 - vi du chinh trong thiet ke: hoi ve so luong thuoc bat thuong."""
    flag = check_keyword_redflag("tôi có 10 viên thuốc ngủ, uống hết có sao không")
    assert flag.is_redflag is True
    assert flag.matched_group == "overdose_risk"


def test_normal_utterance_no_redflag():
    flag = check_keyword_redflag("tôi uống thuốc rồi, cảm ơn bác sĩ")
    assert flag.is_redflag is False
    assert flag.level == "Không đáng ngại"


def test_no_llm_classifier_returns_keyword_flag_unchanged():
    """llm_classifier=None (mac dinh) - hanh vi CU nguyen ven, chi lop keyword."""
    flag = check_safety("tôi uống thuốc rồi")
    assert flag.is_redflag is False
    assert flag.source == "keyword"


def test_llm_error_does_not_crash_keyword_layer_br_6_3():
    """BR-6.3: LLM loi/timeout khong duoc lam mat hieu luc cua keyword layer."""

    def broken_llm(utterance: str):
        raise RuntimeError("LLM API timeout")

    flag = check_safety("tôi uống thuốc rồi", llm_classifier=broken_llm)
    assert flag.is_redflag is False  # keyword sach, LLM loi -> khong crash, tra ve sach
    assert flag.source == "keyword"


def test_llm_malformed_result_does_not_crash_br_6_3():
    """Vong 3 - BR-6.3 ap dung ca khi LLM goi THANH CONG nhung tra ve sai
    dang (vd thieu attribute) - khong chi loi mang/timeout."""

    def malformed_llm(utterance: str) -> bool:
        return True  # SAI dang - khong co .level, tung la interface CU truoc vong 3

    flag = check_safety("tôi uống thuốc rồi", llm_classifier=malformed_llm)
    assert flag.is_redflag is False
    assert flag.source == "keyword"


def test_llm_flags_dangerous_when_keyword_misses():
    """OR logic (BR-6.1), vong 3 - keyword sach nhung LLM tra ve "Nguy hiểm"
    -> van la redflag (dung case bug goc: "muon uong 10 vien thuoc ngu")."""

    def llm_that_flags(utterance: str) -> _FakeLLMResult:
        return _FakeLLMResult(level="Nguy hiểm", category="dosage_risk", reasoning="y dinh uong qua lieu")

    flag = check_safety("tôi muốn uống 10 viên thuốc ngủ", llm_classifier=llm_that_flags)
    assert flag.is_redflag is True
    assert flag.source == "llm"
    assert flag.level == "Nguy hiểm"
    assert flag.llm_category == "dosage_risk"


def test_keyword_redflag_is_floor_llm_cannot_downgrade():
    """Vong 3 - "nếu regex trigger, tối thiểu Nguy hiểm" (kickoff muc 3.2) -
    LLM noi "Không đáng ngại" KHONG duoc ha muc khi keyword da trigger."""

    def llm_that_says_fine(utterance: str) -> _FakeLLMResult:
        return _FakeLLMResult(level="Không đáng ngại", category="none")

    flag = check_safety("tôi có 10 viên thuốc ngủ, uống hết có sao không", llm_classifier=llm_that_says_fine)
    assert flag.is_redflag is True
    assert flag.level == "Nguy hiểm"
    # source="keyword": LLM CO CHAY (khong crash) nhung khong "flag" gi ca -
    # source phan anh lop nao THUC SU dong gop vao ket qua cuoi, khong phai
    # "lop nao co duoc goi".
    assert flag.source == "keyword"


def test_llm_medium_level_does_not_interrupt_but_is_captured():
    """Vong 3 - "Trung bình" KHONG cat luong chinh (is_redflag=False, tranh
    bao dong gia) nhung VAN duoc ghi lai day du (level/category) de audit."""

    def llm_medium(utterance: str) -> _FakeLLMResult:
        return _FakeLLMResult(level="Trung bình", category="clinical_symptom", reasoning="trieu chung nhe")

    flag = check_safety("dạo này hơi mệt mỏi", llm_classifier=llm_medium)
    assert flag.is_redflag is False
    assert flag.level == "Trung bình"
    assert flag.llm_category == "clinical_symptom"


def test_llm_low_level_does_not_interrupt():
    def llm_low(utterance: str) -> _FakeLLMResult:
        return _FakeLLMResult(level="Nhẹ", category="none")

    flag = check_safety("hơi buồn ngủ sau khi uống thuốc", llm_classifier=llm_low)
    assert flag.is_redflag is False
    assert flag.level == "Nhẹ"


def test_self_harm_category_never_goes_below_trung_binh_even_if_llm_says_nhe():
    """Phan hoi review 2026-08-12 - eval/safety_llm_report.json do duoc
    self_harm_borderline dao dong Nhẹ/Trung bình 12/20 (60% on dinh) qua
    20 lan goi that - "may rui roi vao lan chay nao" khong chap nhan duoc
    cho category nay. San rieng dam bao KHONG BAO GIO tut duoi Trung bình
    du 1 lan goi thuc te ra "Nhẹ"."""

    def llm_says_nhe_self_harm(utterance: str) -> _FakeLLMResult:
        return _FakeLLMResult(level="Nhẹ", category="self_harm", reasoning="test")

    flag = check_safety("câu biên nào đó", llm_classifier=llm_says_nhe_self_harm)
    assert flag.level == "Trung bình"
    assert flag.llm_category == "self_harm"


def test_wrong_drug_category_never_goes_below_trung_binh():
    def llm_says_khong_dang_ngai_wrong_drug(utterance: str) -> _FakeLLMResult:
        return _FakeLLMResult(level="Không đáng ngại", category="wrong_drug", reasoning="test")

    flag = check_safety("câu biên nào đó", llm_classifier=llm_says_khong_dang_ngai_wrong_drug)
    assert flag.level == "Trung bình"


def test_category_floor_does_not_apply_to_other_categories():
    """Regression - san CHI ap dung cho self_harm/wrong_drug, khong lan sang
    dosage_risk/clinical_symptom/severe_reaction (chua co bang chung dao dong
    tuong tu, khong doan bua)."""

    def llm_says_nhe_dosage(utterance: str) -> _FakeLLMResult:
        return _FakeLLMResult(level="Nhẹ", category="dosage_risk", reasoning="test")

    flag = check_safety("câu biên nào đó", llm_classifier=llm_says_nhe_dosage)
    assert flag.level == "Nhẹ"  # khong bi nang len


def test_both_clean_no_redflag():
    def llm_clean(utterance: str) -> _FakeLLMResult:
        return _FakeLLMResult(level="Không đáng ngại", category="none")

    flag = check_safety("thuốc này uống trước hay sau ăn", llm_classifier=llm_clean)
    assert flag.is_redflag is False
    assert flag.level == "Không đáng ngại"
    assert flag.source == "keyword"  # LLM khong dong gop gi (ca 2 cung sach)
