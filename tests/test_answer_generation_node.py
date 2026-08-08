"""Phase 5 - test bat buoc: 2 caveat (lieu_dung chung, thieu chi dinh ca
nhan) phai la 2 truong boolean RIENG BIET trong trace, khong gop chung 1
field (chot lai o Phase 4 review, nhac lai truoc khi code Phase 5). PURE
node test - generate_fn injectable, khong goi OpenAI that.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from src.agents.nodes.conversation_nodes import (  # noqa: E402
    CAVEAT_LIEU_DUNG,
    CAVEAT_THOI_DIEM_MISSING,
    NO_SOURCE_MESSAGE,
    build_answer_generation_node,
)
from src.services.retrieval import DrugInfoResult  # noqa: E402


def _fake_result(field_group: str, drug_id: str = "drug-1") -> DrugInfoResult:
    return DrugInfoResult(
        drug_id=drug_id,
        ten_thuoc="Thuốc test",
        field_group=field_group,
        noi_dung="nội dung test",
        danh_muc="Thuốc kháng virus",
        muc_nghiem_trong="Nguy hiểm",
        source=f"{field_group} — Thuốc test",
        vector_score=0.8,
        lexical_score=None,
        rrf_score=0.02,
        rank=1,
    )


def _base_state(**overrides) -> dict:
    state = {
        "patient_id": "p1",
        "dose_event_id": None,
        "utterance": "thuốc này dùng sao",
        "trace": [],
        "rag_results": [],
        "prescription_instruction": None,
    }
    state.update(overrides)
    return state


@pytest.mark.asyncio
async def test_both_caveats_are_separate_boolean_fields_not_merged():
    """2 truong PHAI cung co mat trong entry trace, ten khac nhau, gia tri
    doc lap nhau - khong duoc gop thanh 1 field chung (vd 'caveat_inserted')."""
    node = build_answer_generation_node(generate_fn=lambda u, r: "Câu trả lời cơ bản.")
    state = _base_state(rag_results=[_fake_result("cach_dung")], prescription_instruction=None)

    result = await node(state)
    entry = result["trace"][-1]

    assert "caveat_lieu_dung_inserted" in entry
    assert "caveat_thoi_diem_missing_inserted" in entry
    assert "caveat_inserted" not in entry, "khong duoc gop 2 caveat thanh 1 field chung ten khac"
    assert isinstance(entry["caveat_lieu_dung_inserted"], bool)
    assert isinstance(entry["caveat_thoi_diem_missing_inserted"], bool)


@pytest.mark.asyncio
async def test_caveat_lieu_dung_inserted_when_cach_dung_used_and_has_prescription():
    """cach_dung duoc dung + CO chi dinh ca nhan -> chi caveat lieu_dung chen,
    khong caveat thieu chi dinh (vi thuc su co chi dinh roi)."""
    node = build_answer_generation_node(generate_fn=lambda u, r: "Uống 1 viên/lần.")
    state = _base_state(
        rag_results=[_fake_result("cach_dung")],
        prescription_instruction="sau ăn sáng",
    )

    result = await node(state)
    entry = result["trace"][-1]

    assert entry["caveat_lieu_dung_inserted"] is True
    assert entry["caveat_thoi_diem_missing_inserted"] is False
    assert CAVEAT_LIEU_DUNG in result["response"]
    assert CAVEAT_THOI_DIEM_MISSING not in result["response"]
    assert "sau ăn sáng" in result["response"]


@pytest.mark.asyncio
async def test_caveat_thoi_diem_missing_when_no_active_prescription_for_drug():
    """Co ket qua RAG nhung KHONG co chi dinh ca nhan (benh nhan hoi thuoc
    ngoai don cua ho) -> chi caveat thieu chi dinh chen, khong phai caveat
    lieu_dung (vi field_group o day khong phai cach_dung)."""
    node = build_answer_generation_node(generate_fn=lambda u, r: "Thuốc này dùng để hạ sốt.")
    state = _base_state(
        rag_results=[_fake_result("cong_dung")],
        prescription_instruction=None,
    )

    result = await node(state)
    entry = result["trace"][-1]

    assert entry["caveat_lieu_dung_inserted"] is False
    assert entry["caveat_thoi_diem_missing_inserted"] is True
    assert CAVEAT_THOI_DIEM_MISSING in result["response"]
    assert CAVEAT_LIEU_DUNG not in result["response"]


@pytest.mark.asyncio
async def test_both_caveats_inserted_simultaneously_when_both_conditions_true():
    """cach_dung duoc dung VA khong co chi dinh ca nhan -> CA HAI caveat deu
    chen, doc lap nhau (chung minh 2 field khong loai tru lan nhau)."""
    node = build_answer_generation_node(generate_fn=lambda u, r: "Uống 1 viên/lần.")
    state = _base_state(
        rag_results=[_fake_result("cach_dung")],
        prescription_instruction=None,
    )

    result = await node(state)
    entry = result["trace"][-1]

    assert entry["caveat_lieu_dung_inserted"] is True
    assert entry["caveat_thoi_diem_missing_inserted"] is True
    assert CAVEAT_LIEU_DUNG in result["response"]
    assert CAVEAT_THOI_DIEM_MISSING in result["response"]


@pytest.mark.asyncio
async def test_empty_rag_results_refuses_instead_of_calling_llm_with_no_grounding():
    """BR-7.3 (muc 4.4): rag_results rong -> tu choi NGAY, KHONG goi
    generate_fn - phat hien 2026-08-08 (review Phase 6): ban truoc goi
    thang generate_fn ngay ca khi khong co nguon nao, rui ro bia thong tin
    ma khong bi bat vi khong co test nao lo ra qua danh sach node day du."""
    generate_fn_called = False

    def spy_generate(u, r):
        nonlocal generate_fn_called
        generate_fn_called = True
        return "Không có thông tin."

    node = build_answer_generation_node(generate_fn=spy_generate)
    state = _base_state(rag_results=[], prescription_instruction=None)

    result = await node(state)
    entry = result["trace"][-1]

    assert generate_fn_called is False, "khong duoc goi LLM khi khong co nguon nao de dua vao prompt"
    assert entry["step"] == "refuse"
    assert result["response"] == NO_SOURCE_MESSAGE
