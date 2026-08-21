"""No-cost determinism checks for the BUILD-7C corpus recovery path."""

from __future__ import annotations

from backend.services.rag_corpus_recovery import (
    RESERVATION_COMMITTED,
    RESERVATION_RESERVED,
    RESERVATION_RESPONSE_RECORDED,
    RESERVATION_UNRESOLVED,
    CorpusChunk,
    batch_key_for,
    build_preflight,
    reservation_usage_liability,
    token_capped_batches,
)


def _chunk(key: str, tokens: int) -> CorpusChunk:
    return CorpusChunk(
        chunk_key=key,
        drug_chunk_id=key,
        source_path="source.json",
        drug_id="drug",
        ten_thuoc="Drug",
        danh_muc="category",
        muc_nghiem_trong="Nhe",
        field_group="cong_dung",
        split_ordinal=0,
        noi_dung="content",
        token_count=tokens,
    )


def test_active_canonical_preflight_is_deterministic_and_excludes_six_legacy_ids():
    """Frozen V1 data must produce the signed active-only corpus without an API call."""

    first = build_preflight()
    second = build_preflight()

    assert len(first.active_drug_ids) == 3_556
    assert len(first.excluded_drug_ids) == 6
    assert len(first.chunks) == 14_423
    assert first.field_group_counts == {
        "bao_quan": 3_508,
        "cach_dung": 3_560,
        "cong_dung": 3_556,
        "tac_dung_phu": 3_799,
    }
    assert not {chunk.drug_id for chunk in first.chunks}.intersection(first.excluded_drug_ids)
    assert first.source_manifest_hash == second.source_manifest_hash
    assert first.chunk_manifest_hash == second.chunk_manifest_hash
    assert [chunk.chunk_key for chunk in first.chunks] == [chunk.chunk_key for chunk in second.chunks]


def test_token_capped_batches_preserve_order_and_never_exceed_cap():
    """Resume batches are deterministic and cannot exceed the approved token cap."""

    chunks = (_chunk("one", 7), _chunk("two", 6), _chunk("three", 4))
    batches = token_capped_batches(chunks, 10)

    assert [[item.chunk_key for item in batch] for batch in batches] == [["one"], ["two", "three"]]
    assert all(sum(item.token_count for item in batch) <= 10 for batch in batches)


def test_reservation_key_and_cost_liability_are_deterministic_and_fail_closed():
    """Unknown requests reserve their ceiling; staged usage cannot be omitted."""

    batch = (_chunk("one", 7), _chunk("two", 6))
    assert batch_key_for(batch) == batch_key_for(batch)
    assert batch_key_for(batch) != batch_key_for(tuple(reversed(batch)))
    assert (
        reservation_usage_liability(
            status=RESERVATION_RESERVED, planned_tokens=13, actual_tokens=None, accounted_in_corpus=False
        )
        == 13
    )
    assert (
        reservation_usage_liability(
            status=RESERVATION_UNRESOLVED, planned_tokens=13, actual_tokens=None, accounted_in_corpus=False
        )
        == 13
    )
    assert (
        reservation_usage_liability(
            status=RESERVATION_RESPONSE_RECORDED, planned_tokens=13, actual_tokens=11, accounted_in_corpus=False
        )
        == 11
    )
    assert (
        reservation_usage_liability(
            status=RESERVATION_COMMITTED, planned_tokens=13, actual_tokens=11, accounted_in_corpus=True
        )
        == 0
    )
