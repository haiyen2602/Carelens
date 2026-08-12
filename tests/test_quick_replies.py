"""Vong 3, muc 6.1 (#22) - _infer_quick_replies() suy quick_replies TAP
TRUNG theo stage, xem ghi chu chi tiet trong drug_confirmation_nodes.py
(ly do khong sua truc tiep 24 diem tao _StepResult)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.agents.nodes.drug_confirmation_nodes import (  # noqa: E402
    NOT_FOUND_QUICK_REPLY,
    STAGE_IN_RX_AWAITING_NEW_NAME,
    STAGE_IN_RX_CONFIRM_R1,
    STAGE_IN_RX_CONFIRM_R2,
    STAGE_OUT_RX_AWAITING_REDESCRIBE,
    STAGE_OUT_RX_CHOOSE_TOP3_R1,
    STAGE_OUT_RX_CONFIRM_PICK_R1,
    STAGE_OUT_RX_CONFIRM_TOP1_R1,
    STAGE_OUT_RX_CONFIRM_TOP1_R2,
    _infer_quick_replies,
)


def test_confirm_stages_return_co_khong():
    for stage in (
        STAGE_IN_RX_CONFIRM_R1,
        STAGE_IN_RX_CONFIRM_R2,
        STAGE_OUT_RX_CONFIRM_TOP1_R1,
        STAGE_OUT_RX_CONFIRM_TOP1_R2,
        STAGE_OUT_RX_CONFIRM_PICK_R1,
    ):
        assert _infer_quick_replies(stage, []) == ["Có", "Không"]


def test_top3_stage_returns_candidate_names_plus_not_found_option():
    candidates = [{"drug_id": "d1", "ten_thuoc": "Panadol"}, {"drug_id": "d2", "ten_thuoc": "Paracetamol"}]
    result = _infer_quick_replies(STAGE_OUT_RX_CHOOSE_TOP3_R1, candidates)
    assert result == ["Panadol", "Paracetamol", NOT_FOUND_QUICK_REPLY]


def test_free_text_stages_return_none():
    assert _infer_quick_replies(STAGE_IN_RX_AWAITING_NEW_NAME, []) is None
    assert _infer_quick_replies(STAGE_OUT_RX_AWAITING_REDESCRIBE, []) is None


def test_unknown_stage_returns_none():
    assert _infer_quick_replies("stage_khong_ton_tai", []) is None
