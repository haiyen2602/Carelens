"""Vong 3, muc 5.3 - _detect_requested_buoi(). Sua theo phan hoi review
2026-08-13 (PR #20): them buoc match "buoi <ten buoi khong dau>" cho benh
nhan go khong dau (pho bien tren mobile), KHONG duoc lam song lai bug goc
("tôi" bi hieu nham la "tối" khi bo dau ca cau)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.agents.nodes.conversation_nodes import _detect_requested_buoi  # noqa: E402


def test_matches_accented_buoi_label():
    assert _detect_requested_buoi("Buổi sáng tôi cần uống thuốc gì") == "sang"
    assert _detect_requested_buoi("cho tôi xem lịch buổi tối") == "toi"


def test_original_bug_does_not_regress():
    """Bug goc: "tôi" bi hieu nham la "tối" khi bo dau CA CAU. Cau nay
    KHONG co "buổi"/"buoi" nao ca - phai tra None (fallback ca ngay), khong
    duoc doan la buoi toi chi vi co chu "toi" (tu "tôi")."""
    assert _detect_requested_buoi("hôm nay tôi uống thuốc gì") is None
    assert _detect_requested_buoi("tôi cần uống thuốc lúc mấy giờ") is None


def test_matches_unaccented_buoi_phrase():
    """Sua moi (PR #20 review) - go khong dau nhung CO tu "buoi" ngay truoc
    ten buoi -> van phat hien duoc, khong con phai fallback ca ngay."""
    assert _detect_requested_buoi("buoi sang toi uong thuoc gi") == "sang"
    assert _detect_requested_buoi("cho toi xem lich buoi toi") == "toi"
    assert _detect_requested_buoi("BUOI CHIEU can uong gi") == "chieu"


def test_unaccented_toi_alone_without_buoi_prefix_is_not_detected():
    """"toi" don doc (khong co "buoi" ngay truoc) van KHONG duoc doan la
    buoi toi - dung y an toan goc, chi mo rong cho cum "buoi X" ro rang."""
    assert _detect_requested_buoi("toi can uong thuoc gi") is None


def test_no_buoi_mentioned_returns_none():
    assert _detect_requested_buoi("thuốc paracetamol dùng để làm gì") is None
