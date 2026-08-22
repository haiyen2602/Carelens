"""BUILD-4 deterministic tests for Context Manager priority and overflow behavior."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.agents.v2.context import (
    ContextAuthority,
    ContextBudget,
    ContextBuildStatus,
    ContextDisposition,
    ContextItem,
    ContextLayer,
    ContextManager,
    MemoryKind,
)


def _budget(*, input_tokens=100, reserve=20, total=120, fractions=None):
    return ContextBudget(
        input_token_budget=input_tokens,
        output_token_reserve=reserve,
        total_run_token_budget=total,
        memory_fractions=fractions
        or {
            MemoryKind.SHORT_TERM: 0.10,
            MemoryKind.LONG_TERM_FACT: 0.04,
            MemoryKind.EPISODIC: 0.03,
            MemoryKind.SEMANTIC: 0.03,
        },
    )


def _item(id, layer, tokens, *, authority=ContextAuthority.USER_ASSERTED, priority=0, **changes):
    return ContextItem(
        id=id,
        layer=layer,
        content=f"raw:{id}",
        token_count=tokens,
        authority=authority,
        priority=priority,
        provenance=f"test:{id}",
        **changes,
    )


def test_all_seven_layers_are_supported_and_policy_system_precede_other_context():
    layers = tuple(ContextLayer)
    result = ContextManager(_budget(input_tokens=200)).build(
        [_item(layer.value, layer, 10, authority=ContextAuthority.SYSTEM if layer is ContextLayer.SYSTEM else ContextAuthority.USER_ASSERTED) for layer in layers]
    )
    assert result.status == ContextBuildStatus.READY
    assert [selection.item.layer for selection in result.included] == list(layers)


def test_priority_then_authority_and_freshness_choose_relevant_context_within_budget():
    older = _item(
        "older",
        ContextLayer.USER,
        30,
        priority=5,
        freshness=datetime(2026, 1, 1, tzinfo=UTC),
        relevance=0.5,
    )
    newer = _item(
        "newer",
        ContextLayer.USER,
        30,
        priority=5,
        freshness=datetime(2026, 2, 1, tzinfo=UTC),
        relevance=0.5,
    )
    result = ContextManager(_budget(input_tokens=30)).build([older, newer])
    assert [selection.item.id for selection in result.included] == ["newer"]
    assert next(selection for selection in result.selections if selection.item.id == "older").disposition == ContextDisposition.DROPPED


def test_policy_is_never_dropped_and_protected_overflow_fails_gracefully():
    policy = _item("policy", ContextLayer.POLICY, 80, authority=ContextAuthority.POLICY)
    system = _item("system", ContextLayer.SYSTEM, 30, authority=ContextAuthority.SYSTEM)
    optional = _item("optional", ContextLayer.USER, 10)
    result = ContextManager(_budget(input_tokens=100)).build([optional, system, policy])
    assert result.status == ContextBuildStatus.OVERFLOW
    assert result.overflow_reason == "PROTECTED_CONTEXT_EXCEEDS_INPUT_BUDGET"
    assert [selection.item.id for selection in result.included] == ["policy", "system"]
    assert next(selection for selection in result.selections if selection.item.id == "optional").disposition == ContextDisposition.DROPPED


def test_authoritative_clinical_content_is_preserved_verbatim_not_compacted_or_dropped():
    fact = _item(
        "dose-fact",
        ContextLayer.TOOL,
        80,
        authority=ContextAuthority.OPERATIONAL_DB,
        compact_content="changed",
        compact_token_count=5,
    )
    result = ContextManager(_budget(input_tokens=50)).build([fact])
    selection = result.included[0]
    assert result.status == ContextBuildStatus.OVERFLOW
    assert selection.disposition == ContextDisposition.KEPT
    assert selection.rendered_content == fact.content


def test_memory_allocations_are_maxima_not_required_quotas():
    manager = ContextManager(_budget(input_tokens=1000))
    short = _item("short", ContextLayer.MEMORY, 101, memory_kind=MemoryKind.SHORT_TERM)
    long_fact = _item("long", ContextLayer.MEMORY, 40, memory_kind=MemoryKind.LONG_TERM_FACT)
    result = manager.build([short, long_fact])
    assert [selection.item.id for selection in result.included] == ["long"]
    assert next(selection for selection in result.selections if selection.item.id == "short").reason == "MEMORY_ALLOCATION_CAP"
    assert result.consumed_input_tokens == 40


def test_overflow_pipeline_compacts_then_offloads_then_drops_irrelevant_context():
    compactable = _item(
        "compact",
        ContextLayer.USER,
        80,
        priority=3,
        compact_content="compact:compact",
        compact_token_count=30,
    )
    offloadable = _item(
        "offload",
        ContextLayer.RETRIEVAL,
        80,
        priority=2,
        reference="retrieval:chunk-1",
        reference_token_count=10,
    )
    dropped = _item("drop", ContextLayer.USER, 80, priority=1)
    result = ContextManager(_budget(input_tokens=45)).build([dropped, offloadable, compactable])
    by_id = {selection.item.id: selection for selection in result.selections}
    assert by_id["compact"].disposition == ContextDisposition.COMPACTED
    assert by_id["offload"].disposition == ContextDisposition.OFFLOADED_REFERENCE
    assert by_id["drop"].disposition == ContextDisposition.DROPPED
    assert result.consumed_input_tokens == 40


def test_budget_is_derived_from_settings_and_reserves_model_output_tokens():
    settings = SimpleNamespace(
        agent_token_budget=120,
        agent_context_token_budget=90,
        agent_output_token_reserve=30,
        agent_context_short_term_fraction=0.10,
        agent_context_long_term_facts_fraction=0.04,
        agent_context_episodic_fraction=0.03,
        agent_context_semantic_fraction=0.03,
    )
    budget = ContextBudget.from_settings(settings)
    assert (budget.input_token_budget, budget.output_token_reserve, budget.memory_cap(MemoryKind.SHORT_TERM)) == (90, 30, 9)
    settings.agent_context_token_budget = 100
    with pytest.raises(ValueError, match="exceeds"):
        ContextBudget.from_settings(settings)
