"""BUILD-7 deterministic tests for the typed Agent V2 Retrieval Gateway."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.agents.v2.context import (
    ContextAuthority,
    ContextBudget,
    ContextDisposition,
    ContextItem,
    ContextLayer,
    ContextManager,
    MemoryKind,
)
from backend.agents.v2.model_gateway import EmbeddingResult
from backend.agents.v2.retrieval import (
    RetrievalConfig,
    RetrievalGateway,
    RetrievalStatus,
)
from backend.agents.v2.retrieval_eval import evaluate_retrieval
from backend.services.agent_retrieval import (
    AgentRetrievalDomainService,
    DomainRetrievalResult,
    RetrievedKnowledgeDocument,
)
from backend.services.retrieval import DrugInfoResult, RetrievalResult


class _EmbeddingGateway:
    def __init__(self, *, model="text-embedding-3-small", fails=False):
        self.model = model
        self.fails = fails
        self.queries = []

    def embed_query(self, *, text):
        self.queries.append(text)
        if self.fails:
            raise RuntimeError("provider key and request details must not leak")
        return EmbeddingResult(model=self.model, vector=(0.1, 0.2))


class _Domain:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def retrieve(self, *, query, embedding, top_k):
        self.calls.append((query, embedding, top_k))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _document(source_id="chunk-1", *, content="retrieved drug knowledge", rank=1, relevance=0.5):
    return RetrievedKnowledgeDocument(
        source_id=source_id,
        drug_id="drug-1",
        drug_name="Drug 1",
        field_group="cong_dung",
        content=content,
        source="cong_dung — Drug 1",
        vector_score=0.8,
        lexical_score=0.7,
        relevance=relevance,
        rank=rank,
    )


def _config(*, top_k=3, token_budget=500):
    return RetrievalConfig(embedding_model="text-embedding-3-small", top_k=top_k, token_budget=token_budget)


def _gateway(result, *, config=None, embedding=None):
    return RetrievalGateway(
        embedding or _EmbeddingGateway(),
        _Domain(result),
        config=config or _config(),
        now=lambda: datetime(2026, 8, 18, tzinfo=UTC),
    )


def test_query_embedding_ranking_and_top_k_are_passed_to_domain_adapter_with_context_metadata():
    domain_result = DomainRetrievalResult(
        documents=(_document("chunk-1", rank=1, relevance=0.8), _document("chunk-2", rank=2, relevance=0.6)),
        no_source_found=False,
    )
    embedding = _EmbeddingGateway()
    domain = _Domain(domain_result)
    gateway = RetrievalGateway(embedding, domain, config=_config(top_k=2), now=lambda: datetime(2026, 8, 18, tzinfo=UTC))

    result = gateway.retrieve({"query": "thuoc dung de lam gi"})

    assert result.status is RetrievalStatus.READY
    assert embedding.queries == ["thuoc dung de lam gi"]
    assert domain.calls == [("thuoc dung de lam gi", (0.1, 0.2), 2)]
    items = result.to_context_items()
    assert [item.layer for item in items] == [ContextLayer.RETRIEVAL, ContextLayer.RETRIEVAL]
    assert all(item.authority is ContextAuthority.RETRIEVAL for item in items)
    assert [item.provenance for item in items] == ["legacy-rag:drug_chunks:chunk-1", "legacy-rag:drug_chunks:chunk-2"]
    assert all(item.freshness == datetime(2026, 8, 18, tzinfo=UTC) for item in items)
    assert [item.relevance for item in items] == [0.8, 0.6]


def test_retrieval_context_is_bounded_by_top_k_and_token_budget_without_rewriting_content():
    domain_result = DomainRetrievalResult(
        documents=(
            _document("chunk-1", content="a" * 80, rank=1),
            _document("chunk-2", content="b" * 80, rank=2),
            _document("chunk-3", content="c" * 80, rank=3),
        ),
        no_source_found=False,
    )
    result = _gateway(domain_result, config=_config(top_k=2, token_budget=100)).retrieve({"query": "q"})

    assert result.status is RetrievalStatus.READY
    assert len(result.documents) == 1
    assert result.documents[0].source_id == "chunk-1"
    assert result.excluded_by_budget == 1
    assert sum(item.token_count for item in result.to_context_items()) <= 100


def test_no_result_invalid_query_embedding_mismatch_and_failure_are_safe_terminal_outcomes():
    no_results = _gateway(DomainRetrievalResult(documents=(), no_source_found=True)).retrieve({"query": "unknown"})
    assert (no_results.status, no_results.no_source_found, no_results.safe_reason) == (
        RetrievalStatus.NO_RESULTS,
        True,
        "NO_RETRIEVAL_EVIDENCE",
    )

    embedding = _EmbeddingGateway()
    invalid = _gateway(DomainRetrievalResult(documents=(), no_source_found=True), embedding=embedding).retrieve(
        {"query": "x", "patient_id": "other-patient"}
    )
    assert invalid.status is RetrievalStatus.INVALID_QUERY
    assert embedding.queries == []

    mismatch = _gateway(DomainRetrievalResult(documents=(), no_source_found=True), embedding=_EmbeddingGateway(model="other-model")).retrieve({"query": "x"})
    assert mismatch.status is RetrievalStatus.UNAVAILABLE
    assert mismatch.safe_reason == "EMBEDDING_MODEL_MISMATCH"

    unavailable = _gateway(DomainRetrievalResult(documents=(), no_source_found=True), embedding=_EmbeddingGateway(fails=True)).retrieve({"query": "x"})
    assert unavailable.status is RetrievalStatus.UNAVAILABLE
    assert unavailable.safe_reason == "RETRIEVAL_UNAVAILABLE"


def test_retrieval_cannot_override_authoritative_operational_context():
    retrieval = _gateway(DomainRetrievalResult(documents=(_document(content="x" * 100),), no_source_found=False)).retrieve({"query": "x"})
    operational = ContextItem(
        id="tool:dose-status",
        layer=ContextLayer.TOOL,
        content="authoritative dose state",
        token_count=10,
        authority=ContextAuthority.OPERATIONAL_DB,
        priority=1,
        provenance="operational-db:dose-occurrence:status",
    )
    budget = ContextBudget(
        input_token_budget=10,
        output_token_reserve=1,
        total_run_token_budget=11,
        memory_fractions={
            MemoryKind.SHORT_TERM: 0.10,
            MemoryKind.LONG_TERM_FACT: 0.04,
            MemoryKind.EPISODIC: 0.03,
            MemoryKind.SEMANTIC: 0.03,
        },
    )
    built = ContextManager(budget).build([*retrieval.to_context_items(), operational])
    by_id = {selection.item.id: selection for selection in built.selections}

    assert by_id["tool:dose-status"].disposition is ContextDisposition.KEPT
    assert all(selection.disposition is ContextDisposition.DROPPED for key, selection in by_id.items() if key.startswith("retrieval:"))


def test_retrieval_config_requires_the_approved_embedding_model_and_positive_bounds():
    settings = SimpleNamespace(agent_embedding_model="text-embedding-3-small", agent_retrieval_top_k=5, agent_retrieval_token_budget=700)
    assert RetrievalConfig.from_settings(settings) == _config(top_k=5, token_budget=700)
    settings.agent_embedding_model = "other-model"
    try:
        RetrievalConfig.from_settings(settings)
    except ValueError as exc:
        assert "text-embedding-3-small" in str(exc)
    else:
        raise AssertionError("unapproved embedding model must fail closed")


def test_domain_adapter_reuses_existing_hybrid_search_and_preserves_chunk_provenance(monkeypatch):
    seen = {}

    def fake_hybrid_search(db, query, embedding, *, top_k):
        seen.update(db=db, query=query, embedding=embedding, top_k=top_k)
        return RetrievalResult(
            results=[
                DrugInfoResult(
                    drug_id="drug-1",
                    ten_thuoc="Drug 1",
                    field_group="cong_dung",
                    noi_dung="content",
                    danh_muc="category",
                    muc_nghiem_trong="unknown",
                    source="cong_dung — Drug 1",
                    vector_score=0.8,
                    lexical_score=0.7,
                    rrf_score=0.03,
                    rank=1,
                    chunk_id="stable-chunk-id",
                )
            ],
            no_source_found=False,
        )

    monkeypatch.setattr("backend.services.agent_retrieval.hybrid_search", fake_hybrid_search)
    marker = object()
    result = AgentRetrievalDomainService(marker).retrieve(query="q", embedding=(0.1, 0.2), top_k=4)

    assert seen == {"db": marker, "query": "q", "embedding": [0.1, 0.2], "top_k": 4}
    assert result.documents[0].source_id == "stable-chunk-id"


def test_deterministic_evaluation_hooks_report_hit_mrr_ndcg_precision_and_map():
    metrics = evaluate_retrieval(
        [
            (("a", "b", "c"), {"b", "c"}),
            (("x", "y"), {"z"}),
        ],
        precision_k=2,
    )

    assert metrics.hit_at_10 == 0.5
    assert metrics.mrr_at_10 == 0.25
    assert 0 < metrics.ndcg_at_10 < 0.5
    assert metrics.precision_at_k == 0.25
    assert metrics.map_at_10 == pytest.approx(7 / 24)
