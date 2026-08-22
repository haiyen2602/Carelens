"""BUILD-17: fail-closed corpus identity comparison logic (no DB required).

``evaluate_identity`` is the pure decision function used by
``scripts/agent_v2/verify_rag_corpus_identity.py`` before any Railway staging
environment is allowed to serve Agent V2 traffic. These tests exercise the
comparison logic directly; the thin DB I/O wrapper (``fetch_snapshot``) is
exercised manually against a live database as part of the BUILD-17 report,
consistent with how this repo tests other pure-logic/I/O-boundary splits.
"""

from scripts.agent_v2.verify_rag_corpus_identity import (
    EXPECTED_IDENTITY,
    CorpusIdentitySnapshot,
    evaluate_identity,
)


def _matching_row(**overrides) -> dict:
    row = {
        "corpus_version": EXPECTED_IDENTITY["corpus_version"],
        "status": EXPECTED_IDENTITY["status"],
        "source_manifest_hash": EXPECTED_IDENTITY["source_manifest_hash"],
        "chunk_manifest_hash": EXPECTED_IDENTITY["chunk_manifest_hash"],
        "embedding_model": EXPECTED_IDENTITY["embedding_model"],
        "embedding_dimensions": EXPECTED_IDENTITY["embedding_dimensions"],
        "index_version": EXPECTED_IDENTITY["index_version"],
        "expected_chunks": EXPECTED_IDENTITY["expected_chunks"],
    }
    row.update(overrides)
    return row


def _snapshot(**overrides) -> CorpusIdentitySnapshot:
    values = dict(
        rag_corpus_row=_matching_row(),
        drug_chunks_total=14423,
        drug_chunks_distinct_keys=14423,
        invalid_dimension_rows=0,
        hnsw_cosine_index_present=True,
        pgvector_extension_version="0.8.6",
    )
    values.update(overrides)
    return CorpusIdentitySnapshot(**values)


def test_matching_identity_passes_with_no_mismatches():
    assert evaluate_identity(_snapshot()) == []


def test_missing_rag_corpus_row_is_a_single_terminal_reason():
    assert evaluate_identity(_snapshot(rag_corpus_row=None)) == ["RAG_CORPUS_ROW_MISSING"]


def test_wrong_chunk_manifest_hash_fails_closed():
    reasons = evaluate_identity(_snapshot(rag_corpus_row=_matching_row(chunk_manifest_hash="deadbeef")))
    assert any(r.startswith("CHUNK_MANIFEST_HASH_MISMATCH") for r in reasons)


def test_wrong_embedding_model_or_dimensions_fails_closed():
    reasons = evaluate_identity(_snapshot(rag_corpus_row=_matching_row(embedding_model="text-embedding-3-large")))
    assert any(r.startswith("EMBEDDING_MODEL_MISMATCH") for r in reasons)

    reasons = evaluate_identity(_snapshot(rag_corpus_row=_matching_row(embedding_dimensions=3072)))
    assert any(r.startswith("EMBEDDING_DIMENSIONS_MISMATCH") for r in reasons)


def test_wrong_index_version_fails_closed():
    reasons = evaluate_identity(_snapshot(rag_corpus_row=_matching_row(index_version="pgvector-ivfflat-cosine-v1")))
    assert any(r.startswith("INDEX_VERSION_MISMATCH") for r in reasons)


def test_row_count_mismatch_fails_closed():
    reasons = evaluate_identity(_snapshot(drug_chunks_total=14000))
    assert any(r.startswith("DRUG_CHUNKS_ROW_COUNT_MISMATCH") for r in reasons)


def test_duplicate_chunk_keys_fail_closed():
    reasons = evaluate_identity(_snapshot(drug_chunks_distinct_keys=14422))
    assert any(r.startswith("DUPLICATE_CHUNK_KEYS_DETECTED") for r in reasons)


def test_invalid_embedding_dimension_rows_fail_closed():
    reasons = evaluate_identity(_snapshot(invalid_dimension_rows=3))
    assert any(r.startswith("INVALID_EMBEDDING_DIMENSIONS") for r in reasons)


def test_missing_hnsw_index_or_extension_fail_closed():
    reasons = evaluate_identity(_snapshot(hnsw_cosine_index_present=False))
    assert "HNSW_COSINE_INDEX_MISSING" in reasons

    reasons = evaluate_identity(_snapshot(pgvector_extension_version=None))
    assert "PGVECTOR_EXTENSION_MISSING" in reasons


def test_multiple_mismatches_are_all_reported_not_just_the_first():
    reasons = evaluate_identity(
        _snapshot(rag_corpus_row=_matching_row(status="FAILED"), drug_chunks_total=1, hnsw_cosine_index_present=False)
    )
    assert len(reasons) >= 3
