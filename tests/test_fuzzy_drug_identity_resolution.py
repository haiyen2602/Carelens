"""Vong 4, muc 3.4 - khoa invariant cua fuzzy 2 tang khong can Postgres/LLM.

`fuzzy_name_search()` da duoc sweep tren DB that trong eval/tune_fuzzy_tier1.py.
O day chi test logic orchestration: fast-path khong goi embedding/LLM selector,
case mo ho bat buoc qua selector, va ca hai van tao pending confirmation.
"""

from __future__ import annotations

import asyncio

import pytest

from backend.agents.nodes import drug_confirmation_nodes as nodes
from backend.agents.nodes.drug_confirmation_nodes import (
    STAGE_OUT_RX_CONFIRM_TOP1_R1,
    build_drug_identity_resolution_node,
)
from backend.services.retrieval import CandidateChunk


def _candidate(drug_id: str, name: str, score: float) -> CandidateChunk:
    return CandidateChunk(
        id=f"{drug_id}-chunk",
        drug_id=drug_id,
        ten_thuoc=name,
        danh_muc="test",
        muc_nghiem_trong="Nhẹ",
        field_group="tac_dung_phu",
        noi_dung="test",
        score=score,
    )


def _state() -> dict:
    return {"intent": "drug_info", "patient_id": "patient-1", "utterance": "bluepine 5mg", "trace": []}


def _patch_out_of_prescription_dependencies(monkeypatch, candidates: list[CandidateChunk], saved: dict) -> None:
    monkeypatch.setattr(nodes, "list_active_prescription_drug_items", lambda _db, _patient_id: [])
    monkeypatch.setattr(nodes, "fuzzy_name_search", lambda _db, _query, top_k: candidates[:top_k])
    monkeypatch.setattr(
        nodes,
        "set_pending_confirmation",
        lambda _db, patient_id, candidates, stage, original_query: saved.update(
            patient_id=patient_id, candidates=candidates, stage=stage, original_query=original_query
        ),
    )


def test_clear_fuzzy_match_skips_llm_and_still_creates_pending_confirmation(monkeypatch):
    saved: dict = {}
    _patch_out_of_prescription_dependencies(
        monkeypatch,
        [
            _candidate("bluepine", "Bluepine 5mg", 0.30),
            _candidate("other", "Other 5mg", 0.24),
        ],
        saved,
    )

    def _embed_must_not_run(_text: str) -> list[float]:
        raise AssertionError("fast-path must not create an embedding")

    def _selector_must_not_run(_utterance: str, _candidates: list[dict]) -> str | None:
        raise AssertionError("fast-path must not call the LLM candidate selector")

    result = asyncio.run(
        build_drug_identity_resolution_node(object(), _embed_must_not_run, _selector_must_not_run)(_state())
    )

    assert saved["stage"] == STAGE_OUT_RX_CONFIRM_TOP1_R1
    assert saved["candidates"] == [
        {"drug_id": "bluepine", "ten_thuoc": "Bluepine 5mg"},
        {"drug_id": "other", "ten_thuoc": "Other 5mg"},
    ]
    assert result["awaiting_drug_confirmation"] is True
    assert "Bluepine 5mg" in result["response"]
    assert result["trace"][-1]["candidate_selection"] == "fuzzy_fast_path"


def test_ambiguous_high_score_uses_llm_selector_and_keeps_patient_confirmation(monkeypatch):
    saved: dict = {}
    _patch_out_of_prescription_dependencies(
        monkeypatch,
        [
            _candidate("vitamin-c-a", "Vitamin C 500mg A", 0.586),
            _candidate("vitamin-c-b", "Vitamin C 500mg B", 0.548),
        ],
        saved,
    )
    selector_calls: list[list[dict]] = []

    def _selector(_utterance: str, candidates: list[dict]) -> str | None:
        selector_calls.append(candidates)
        return "vitamin-c-b"

    result = asyncio.run(build_drug_identity_resolution_node(object(), lambda _text: [], _selector)(_state()))

    assert len(selector_calls) == 1
    assert saved["stage"] == STAGE_OUT_RX_CONFIRM_TOP1_R1
    assert saved["candidates"][0] == {"drug_id": "vitamin-c-b", "ten_thuoc": "Vitamin C 500mg B"}
    assert result["awaiting_drug_confirmation"] is True
    assert "Vitamin C 500mg B" in result["response"]
    assert result["trace"][-1]["candidate_selection"] == "llm_candidate_review"
    assert result["trace"][-1]["score_gap"] == pytest.approx(0.038)


def test_low_confidence_default_selector_fails_closed(monkeypatch):
    saved: dict = {}
    _patch_out_of_prescription_dependencies(
        monkeypatch,
        [_candidate("unrelated", "Unrelated 5mg", 0.12), _candidate("other", "Other 5mg", 0.10)],
        saved,
    )

    result = asyncio.run(build_drug_identity_resolution_node(object(), lambda _text: [])(_state()))

    assert "candidates" not in saved
    assert result["awaiting_drug_confirmation"] is True
    assert result["trace"][-1]["result"] == "llm_no_safe_candidate"
