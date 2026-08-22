"""BUILD-5 tests for isolated, bounded, non-authoritative session memory."""

from datetime import UTC, datetime, timedelta

import pytest

from backend.agents.v2.context import (
    ContextAuthority,
    ContextBudget,
    ContextDisposition,
    ContextManager,
    MemoryKind,
)
from backend.agents.v2.short_term_memory import (
    MemoryContextRequest,
    MessageRole,
    SessionMemoryKey,
    ShortTermMemoryStore,
)


def _store(*, input_tokens=1_000):
    budget = ContextBudget(
        input_token_budget=input_tokens,
        output_token_reserve=100,
        total_run_token_budget=input_tokens + 100,
        memory_fractions={
            MemoryKind.SHORT_TERM: 0.10,
            MemoryKind.LONG_TERM_FACT: 0.04,
            MemoryKind.EPISODIC: 0.03,
            MemoryKind.SEMANTIC: 0.03,
        },
    )
    return ShortTermMemoryStore(ContextManager(budget))


def _key(actor="actor-a", conversation="conversation-a", session="session-a"):
    return SessionMemoryKey(actor_id=actor, conversation_id=conversation, session_id=session)


def test_memory_is_isolated_by_authenticated_actor_conversation_and_session():
    store = _store()
    first = _key()
    same_conversation_other_actor = _key(actor="actor-b")
    same_actor_other_conversation = _key(conversation="conversation-b")
    store.append_message(first, entry_id="first", role=MessageRole.USER, content="only first", token_count=4)
    store.append_message(same_conversation_other_actor, entry_id="second", role=MessageRole.USER, content="only second", token_count=4)
    store.append_message(same_actor_other_conversation, entry_id="third", role=MessageRole.USER, content="only third", token_count=4)

    assert [item.content for item in store.context_items(first)] == ["only first"]
    assert [item.content for item in store.context_items(same_conversation_other_actor)] == ["only second"]
    assert [item.content for item in store.context_items(same_actor_other_conversation)] == ["only third"]
    store.clear(first)
    assert store.context_items(first) == ()
    assert store.context_items(same_conversation_other_actor)


def test_memory_context_contains_recent_messages_task_references_and_pending_clarification():
    store = _store()
    key = _key()
    now = datetime(2026, 8, 18, tzinfo=UTC)
    store.append_message(key, entry_id="user", role=MessageRole.USER, content="Thuoc luc nay?", token_count=5, created_at=now)
    store.append_message(key, entry_id="assistant", role=MessageRole.ASSISTANT, content="Can xac dinh thuoc.", token_count=5, created_at=now + timedelta(seconds=1))
    store.set_current_task(key, entry_id="task", task_or_intent="Resolve referenced drug", token_count=4, created_at=now)
    store.add_resolved_reference(
        key,
        entry_id="drug-ref",
        reference_id="drug-product-1",
        content="Reference points to product 1.",
        token_count=5,
        provenance="tool:get_drug_info:drug-product-1",
    )
    store.set_pending_clarification(key, entry_id="clarify", clarification="Ask which morning dose.", token_count=4)

    items = store.context_items(key, MemoryContextRequest(resolved_reference_ids=frozenset({"drug-product-1"})))
    assert {item.id for item in items} == {
        "short-term:user",
        "short-term:assistant",
        "short-term:task",
        "short-term:drug-ref",
        "short-term:clarify",
    }


def test_irrelevant_memory_is_not_loaded_to_fill_the_short_term_quota():
    store = _store()
    key = _key()
    store.append_message(key, entry_id="relevant", role=MessageRole.USER, content="current question", token_count=10, relevance=0.8)
    store.append_message(key, entry_id="irrelevant", role=MessageRole.USER, content="unrelated history", token_count=10, relevance=0.2)
    store.add_resolved_reference(
        key,
        entry_id="unrequested-reference",
        reference_id="drug-1",
        content="not selected reference",
        token_count=10,
        provenance="tool:get_drug_info:drug-1",
    )

    assert [item.id for item in store.context_items(key)] == ["short-term:relevant"]


def test_user_claims_remain_user_asserted_and_memory_cannot_be_authoritative_clinical_truth():
    store = _store()
    key = _key()
    store.append_message(key, entry_id="claim", role=MessageRole.USER, content="Toi da uong lieu sang.", token_count=8)
    store.add_resolved_reference(
        key,
        entry_id="reference",
        reference_id="dose-1",
        content="Prior tool reference.",
        token_count=5,
        provenance="tool:get_dose_status:dose-1",
    )
    items = {item.id: item for item in store.context_items(key, MemoryContextRequest(resolved_reference_ids=frozenset({"dose-1"})))}
    assert items["short-term:claim"].authority is ContextAuthority.USER_ASSERTED
    assert items["short-term:reference"].authority is ContextAuthority.MEMORY
    assert items["short-term:reference"].provenance == "tool:get_dose_status:dose-1"
    assert all(item.authority not in {ContextAuthority.OPERATIONAL_DB, ContextAuthority.SAFETY_DOMAIN, ContextAuthority.DOCTOR} for item in items.values())


def test_short_term_memory_is_capped_at_ten_percent_of_context_input_budget():
    store = _store(input_tokens=1_000)
    key = _key()
    now = datetime(2026, 8, 18, tzinfo=UTC)
    store.append_message(
        key,
        entry_id="first",
        role=MessageRole.USER,
        content="first",
        token_count=60,
        created_at=now + timedelta(seconds=1),
    )
    store.append_message(
        key,
        entry_id="second",
        role=MessageRole.USER,
        content="second",
        token_count=50,
        created_at=now,
    )

    result = store.build_context(key)
    assert result.consumed_input_tokens == 60
    by_id = {selection.item.id: selection for selection in result.selections}
    assert by_id["short-term:first"].disposition is ContextDisposition.KEPT
    assert by_id["short-term:second"].disposition is ContextDisposition.DROPPED
    assert by_id["short-term:second"].reason == "MEMORY_ALLOCATION_CAP"


def test_memory_overflow_uses_context_manager_compact_then_reference_behavior():
    store = _store(input_tokens=1_000)
    key = _key()
    store.append_message(
        key,
        entry_id="compact",
        role=MessageRole.USER,
        content="long content",
        token_count=120,
        compact_content="compact content",
        compact_token_count=45,
    )
    store.append_message(
        key,
        entry_id="reference",
        role=MessageRole.USER,
        content="other long content",
        token_count=120,
        reference="session-entry:reference",
        reference_token_count=12,
    )

    result = store.build_context(key)
    by_id = {selection.item.id: selection for selection in result.selections}
    assert by_id["short-term:compact"].disposition is ContextDisposition.COMPACTED
    assert by_id["short-term:reference"].disposition is ContextDisposition.OFFLOADED_REFERENCE
    assert result.consumed_input_tokens == 57


def test_session_keys_and_memory_inputs_fail_closed_when_isolation_or_provenance_is_missing():
    with pytest.raises(ValueError, match="actor_id"):
        _key(actor=" ")
    store = _store()
    with pytest.raises(ValueError, match="provenance"):
        store.add_resolved_reference(
            _key(),
            entry_id="ref",
            reference_id="drug-1",
            content="x",
            token_count=1,
            provenance="",
        )
