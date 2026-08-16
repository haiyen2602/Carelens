"""Regression Vong 4, muc 4: audit trieu chung/tac_dung_phu la noi bo."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.agents.nodes.side_effect_audit_nodes import (
    build_redflag_side_effect_audit,
    build_side_effect_audit_node,
)
from backend.agents.orchestrator import run_conversation
from backend.services.escalation import SYMPTOM_OVERLAY_MESSAGE
from backend.services.drug_knowledge.v2_agent import SideEffectMatchResult
from backend.services.retrieval import search_active_side_effect_chunks
from backend.services.safety import SafetyFlag


def _state(**overrides) -> dict:
    state = {
        "patient_id": "patient-1",
        "utterance": "Tôi bị buồn nôn sau khi uống thuốc.",
        "classification": "SIDE_EFFECT",
        "trace": [],
    }
    state.update(overrides)
    return state


def _candidates() -> list[SideEffectMatchResult]:
    return [
        SideEffectMatchResult("drug-a", "Thuốc A", "Có thể gây buồn nôn.", 0.41),
        SideEffectMatchResult("drug-b", "Thuốc B", "Có thể gây buồn nôn.", 0.35),
    ]


@pytest.mark.asyncio
async def test_side_effect_audit_logs_all_llm_confirmed_active_drugs_without_response():
    matcher_calls: list[str] = []

    def matcher(utterance: str, content: str) -> bool:
        assert utterance == "Tôi bị buồn nôn sau khi uống thuốc."
        matcher_calls.append(content)
        return True

    node = build_side_effect_audit_node(
        object(),
        embed_query=lambda _: [0.0],
        match_fn=matcher,
        list_active_items_fn=lambda _db, _patient_id: [
            {"drug_id": "drug-a", "ten_thuoc": "Thuốc A"},
            {"drug_id": "drug-b", "ten_thuoc": "Thuốc B"},
        ],
        search_fn=lambda _db, _utterance, drug_ids, _embed: _candidates() if drug_ids == ["drug-a", "drug-b"] else [],
    )

    result = await node(_state())

    assert "response" not in result, "audit khong duoc tao hay ghi de response cho benh nhan"
    entry = result["trace"][-1]
    assert entry["trigger"] == "dose_classification"
    assert entry["active_drug_ids"] == ["drug-a", "drug-b"]
    assert [match["drug_id"] for match in entry["matches"]] == ["drug-a", "drug-b"]
    assert all("Có thể liên quan tới tác dụng phụ" in match["message"] for match in entry["matches"])
    assert len(matcher_calls) == 2


@pytest.mark.asyncio
async def test_side_effect_audit_logs_no_clear_relation_when_llm_rejects_all_candidates():
    node = build_side_effect_audit_node(
        object(),
        embed_query=lambda _: [0.0],
        match_fn=lambda _utterance, _content: False,
        list_active_items_fn=lambda _db, _patient_id: [{"drug_id": "drug-a", "ten_thuoc": "Thuốc A"}],
        search_fn=lambda _db, _utterance, _drug_ids, _embed: _candidates()[:1],
    )

    result = await node(_state())

    entry = result["trace"][-1]
    assert entry["matches"] == []
    assert entry["result"] == "không tìm thấy liên hệ rõ ràng"


@pytest.mark.asyncio
async def test_side_effect_audit_does_not_call_llm_for_candidates_below_cosine_filter():
    matcher_calls: list[str] = []
    node = build_side_effect_audit_node(
        object(),
        embed_query=lambda _: [0.0],
        match_fn=lambda _utterance, content: matcher_calls.append(content) or True,
        list_active_items_fn=lambda _db, _patient_id: [{"drug_id": "drug-a", "ten_thuoc": "Thuốc A"}],
        search_fn=lambda _db, _utterance, _drug_ids, _embed: [
            SideEffectMatchResult("drug-a", "Thuốc A", "Không liên quan.", 0.19)
        ],
    )

    result = await node(_state())

    entry = result["trace"][-1]
    assert matcher_calls == []
    assert entry["raw_candidate_count"] == 1
    assert entry["candidate_count"] == 0
    assert entry["result"] == "không tìm thấy liên hệ rõ ràng"


@pytest.mark.asyncio
async def test_side_effect_audit_skips_non_side_effect_classification():
    node = build_side_effect_audit_node(object(), embed_query=lambda _: pytest.fail("khong duoc embed"))

    result = await node(_state(classification="TAKEN"))

    assert result["trace"][-1]["skipped"] is True


@pytest.mark.asyncio
async def test_clinical_redflag_keeps_audit_trace_but_only_returns_safety_overlay():
    audit = build_redflag_side_effect_audit(
        object(),
        embed_query=lambda _: [0.0],
        match_fn=lambda _utterance, _content: True,
        list_active_items_fn=lambda _db, _patient_id: [{"drug_id": "drug-a", "ten_thuoc": "Thuốc A"}],
        search_fn=lambda _db, _utterance, _drug_ids, _embed: _candidates()[:1],
    )

    async def clinical_redflag(_utterance: str) -> SafetyFlag:
        return SafetyFlag(is_redflag=True, matched_group="clinical", matched_keyword="khó thở", source="keyword")

    result = await run_conversation(
        _state(classification=None), nodes=[], safety_check=clinical_redflag, redflag_audit_fn=audit
    )

    assert [entry["step"] for entry in result["trace"]] == ["side_effect_audit", "safety_layer"]
    assert result["trace"][0]["trigger"] == "safety_redflag"
    assert result["trace"][0]["matches"][0]["drug_id"] == "drug-a"
    assert result["response"] == SYMPTOM_OVERLAY_MESSAGE
    assert "Thuốc A" not in result["response"]


def test_side_effect_search_queries_only_active_drugs_and_tac_dung_phu():
    captured: dict = {}

    class FakeDb:
        def execute(self, statement, params):
            captured["sql"] = statement.text
            captured["params"] = params
            return SimpleNamespace(
                fetchall=lambda: [
                    SimpleNamespace(
                        drug_id="drug-a",
                        ten_thuoc="Thuốc A",
                        noi_dung="Có thể gây buồn nôn.",
                        cosine_similarity=0.42,
                    )
                ]
            )

    results = search_active_side_effect_chunks(FakeDb(), [0.0], ["drug-a", "drug-a", "drug-b"])

    assert captured["params"]["drug_ids"] == ["drug-a", "drug-b"]
    assert "field_group = 'tac_dung_phu'" in captured["sql"]
    assert "drug_id = ANY" in captured["sql"]
    assert results[0].score == 0.42


def test_side_effect_search_does_not_query_when_no_active_drug():
    class UnexpectedDb:
        def execute(self, *_args, **_kwargs):
            pytest.fail("khong duoc query drug_chunks khi benh nhan khong co thuoc active")

    assert search_active_side_effect_chunks(UnexpectedDb(), [0.0], []) == []
