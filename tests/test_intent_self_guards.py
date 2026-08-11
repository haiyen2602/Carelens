"""Phase 6 - moi node cua nhanh drug_info/dose_confirmation/today_schedule
PHAI tu bao ve theo `state["intent"]` va bo qua (khong chay logic that, khong
goi DB/LLM) khi intent khac nhanh cua no - dung idiom da co tu SEVERITY/LEVEL
(tu bao ve theo `classification`, Phase 5b). Test nay CHI kiem tra duong
SKIP (khong can DB/API that vi node tra ve som truoc khi cham toi db/LLM)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from backend.agents.nodes.conversation_nodes import (  # noqa: E402
    build_answer_generation_node,
    build_prescription_lookup_node,
    build_retrieval_node,
    build_today_schedule_node,
)
from backend.agents.nodes.dose_confirmation_nodes import build_classify_node  # noqa: E402


def _state(intent, **overrides):
    state = {"patient_id": "p1", "dose_event_id": None, "utterance": "test", "trace": [], "intent": intent}
    state.update(overrides)
    return state


@pytest.mark.asyncio
async def test_retrieval_node_skips_when_intent_is_not_drug_info():
    called = False

    def fake_embed(q):
        nonlocal called
        called = True
        return [0.0]

    node = build_retrieval_node(db=None, embed_query=fake_embed)
    result = await node(_state("today_schedule"))

    assert called is False, "khong duoc goi embed_query/DB khi intent khac drug_info"
    assert result["trace"][-1]["skipped"] is True


@pytest.mark.asyncio
async def test_prescription_lookup_node_skips_when_intent_is_not_drug_info():
    node = build_prescription_lookup_node(db=None)
    result = await node(_state("dose_confirmation"))
    assert result["trace"][-1]["skipped"] is True


@pytest.mark.asyncio
async def test_answer_generation_node_skips_when_intent_is_not_drug_info():
    called = False

    def fake_generate(u, r):
        nonlocal called
        called = True
        return "x"

    node = build_answer_generation_node(generate_fn=fake_generate)
    result = await node(_state("today_schedule"))

    assert called is False, "khong duoc goi LLM khi intent khac drug_info"
    assert result["trace"][-1]["skipped"] is True


@pytest.mark.asyncio
async def test_today_schedule_node_skips_when_intent_is_not_today_schedule():
    node = build_today_schedule_node(db=None)
    result = await node(_state("drug_info"))
    assert result["trace"][-1]["skipped"] is True
    assert "response" not in result


@pytest.mark.asyncio
async def test_classify_node_skips_when_intent_is_not_dose_confirmation():
    called = False

    def fake_classify(u):
        nonlocal called
        called = True
        return ("TAKEN", 0.9)

    node = build_classify_node(classify_fn=fake_classify)
    result = await node(_state("drug_info"))

    assert called is False, "khong duoc goi LLM classify khi intent khac dose_confirmation"
    assert result["trace"][-1]["skipped"] is True


@pytest.mark.asyncio
async def test_drug_info_nodes_still_run_when_intent_field_absent_backward_compat():
    """Test goi thang 1 node rieng le (khong qua orchestrator/intent_
    classification truoc) khong duoc set "intent" - phai VAN chay binh
    thuong (None duoc chap nhan), khong bi bao che nham thanh skip. Day la
    ly do cac test rieng le tu Phase 5 (vd test_answer_generation_node.py)
    khong can sua lai them field "intent" moi hoat dong duoc."""
    node = build_answer_generation_node(generate_fn=lambda u, r: "ok")
    state = {"patient_id": "p1", "dose_event_id": None, "utterance": "x", "trace": [], "rag_results": []}
    result = await node(state)  # khong co key "intent" o day
    assert result["trace"][-1]["step"] == "refuse"  # chay that (khong skip), chi la rag_results rong
