"""Phase 5b - test bat buoc cho invariant quan trong nhat cua FEAT-007:
combine_severity() PHAI chi nang, khong bao gio ha muc nghiem trong (BR-3.2 +
BR-3.6). PURE FUNCTION - khong DB/API."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from src.services.severity import SEVERITY_RANK, combine_severity  # noqa: E402

ALL_LEVELS = ("Nhẹ", "Trung bình", "Nguy hiểm")


def test_rag_clear_and_fallback_lower_never_downgrades():
    """BR-3.6: RAG da suy ra 'Nguy hiểm', fallback (muc_nghiem_trong) chi la
    'Nhẹ' -> ket qua PHAI van la 'Nguy hiểm', khong duoc ha xuong theo
    fallback. Day la kich ban rui ro nhat: 1 bug sai chieu se lam benh nhan
    dung thuoc nguy hiem bi ha xuong muc an toan gia."""
    result = combine_severity(rag_severity="Nguy hiểm", fallback_severity="Nhẹ")
    assert result == "Nguy hiểm"


def test_rag_clear_and_fallback_higher_raises():
    """BR-3.6: fallback CAO hon RAG -> duoc phep nang len (chieu con lai cua
    invariant, phai dung ca 2 chieu)."""
    result = combine_severity(rag_severity="Nhẹ", fallback_severity="Nguy hiểm")
    assert result == "Nguy hiểm"


def test_rag_none_floors_at_trung_binh_br_3_2():
    """BR-3.2: RAG khong ro rang (None) -> san toi thieu la 'Trung bình', du
    fallback la 'Nhẹ' - khong duoc suy dien 'Nhẹ' tu viec thieu du lieu."""
    result = combine_severity(rag_severity=None, fallback_severity="Nhẹ")
    assert result == "Trung bình"


def test_rag_none_fallback_nguy_hiem_still_raises():
    result = combine_severity(rag_severity=None, fallback_severity="Nguy hiểm")
    assert result == "Nguy hiểm"


def test_equal_levels_are_stable():
    for level in ALL_LEVELS:
        assert combine_severity(rag_severity=level, fallback_severity=level) == level


@pytest.mark.parametrize("rag", ALL_LEVELS)
@pytest.mark.parametrize("fallback", ALL_LEVELS)
def test_result_never_ranks_below_either_input_full_matrix(rag, fallback):
    """Ma tran day du 3x3 - invariant chung: rank(ket qua) >= rank(rag) VA
    rank(ket qua) >= rank(fallback), voi moi to hop co the co. Day la cach
    phat bieu invariant 'chi nang khong ha' khong phu thuoc cach trien khai
    cu the (khong test lai chinh cong thuc max() ben trong)."""
    result = combine_severity(rag_severity=rag, fallback_severity=fallback)
    assert SEVERITY_RANK[result] >= SEVERITY_RANK[rag]
    assert SEVERITY_RANK[result] >= SEVERITY_RANK[fallback]


def test_invalid_fallback_severity_raises():
    with pytest.raises(ValueError):
        combine_severity(rag_severity="Nhẹ", fallback_severity="khong_hop_le")


def test_invalid_rag_severity_raises():
    with pytest.raises(ValueError):
        combine_severity(rag_severity="khong_hop_le", fallback_severity="Nhẹ")
