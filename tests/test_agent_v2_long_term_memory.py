"""BUILD-11 tests for policy-gated memory, compaction, and artifact offload."""

from datetime import UTC, datetime, timedelta

import pytest

from backend.agents.v2.context import (
    ContextAuthority,
    ContextBudget,
    ContextItem,
    ContextLayer,
    ContextManager,
    ContextSensitivity,
    MemoryKind,
)
from backend.agents.v2.long_term_memory import (
    AgentMemoryContextBuilder,
    ContextCompactor,
    FileSystemArtifactOffload,
    LongTermMemoryStore,
    MemoryCollectionPolicy,
    MemoryRecord,
    MemoryScope,
    MemoryStatus,
    RetentionClass,
)
from backend.agents.v2.short_term_memory import (
    MessageRole,
    SessionMemoryKey,
    ShortTermMemoryStore,
)

NOW = datetime(2026, 8, 18, 9, tzinfo=UTC)


def _manager(*, input_tokens=1_000):
    return ContextManager(
        ContextBudget(
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
    )


def _policy(*, approved=True):
    return MemoryCollectionPolicy(
        policy_id="approved-user-memory",
        version="v1",
        approved=approved,
        require_consent=True,
        allowed_categories=frozenset({"preference", "conversation-summary", "knowledge-note"}),
        allowed_kinds=frozenset(
            {MemoryKind.LONG_TERM_FACT, MemoryKind.EPISODIC, MemoryKind.SEMANTIC}
        ),
        max_retention=timedelta(days=30),
    )


def _scope(*, actor="actor-a", subject="subject-a", conversation="conversation-a", patient="patient-a"):
    return MemoryScope(actor_id=actor, subject_user_id=subject, conversation_id=conversation, patient_id=patient)


def _record(
    memory_id="memory-1",
    *,
    scope=None,
    kind=MemoryKind.LONG_TERM_FACT,
    tokens=20,
    verified_at=NOW,
    expires_at=NOW + timedelta(days=7),
):
    return MemoryRecord(
        memory_id=memory_id,
        scope=scope or _scope(),
        memory_kind=kind,
        category={
            MemoryKind.LONG_TERM_FACT: "preference",
            MemoryKind.EPISODIC: "conversation-summary",
            MemoryKind.SEMANTIC: "knowledge-note",
        }[kind],
        content=f"content for {memory_id}",
        token_count=tokens,
        source="user-approved-memory",
        provenance=f"memory-source:{memory_id}",
        created_at=NOW,
        updated_at=NOW,
        last_verified_at=verified_at,
        confidence=0.9,
        sensitivity=ContextSensitivity.PERSONAL,
        retention_class={
            MemoryKind.LONG_TERM_FACT: RetentionClass.APPROVED_LONG_TERM,
            MemoryKind.EPISODIC: RetentionClass.EPISODIC,
            MemoryKind.SEMANTIC: RetentionClass.SEMANTIC,
        }[kind],
        expires_at=expires_at,
    )


def test_long_term_collection_is_fail_closed_without_approval_or_consent():
    record = _record()
    with pytest.raises(PermissionError, match="not approved"):
        LongTermMemoryStore(_policy(approved=False), _manager()).retain(record, consent_granted=True)
    with pytest.raises(PermissionError, match="consent"):
        LongTermMemoryStore(_policy(), _manager()).retain(record, consent_granted=False)


def test_long_term_episodic_semantic_allocation_and_context_manager_integration():
    store = LongTermMemoryStore(_policy(), _manager())
    assert store.retain(_record("fact", kind=MemoryKind.LONG_TERM_FACT, tokens=40), consent_granted=True)
    assert store.retain(_record("episode", kind=MemoryKind.EPISODIC, tokens=30), consent_granted=True)
    assert store.retain(_record("semantic", kind=MemoryKind.SEMANTIC, tokens=30), consent_granted=True)

    result = store.build_context(_scope())
    assert result.consumed_input_tokens == 100
    assert {selection.item.memory_kind for selection in result.included} == {
        MemoryKind.LONG_TERM_FACT,
        MemoryKind.EPISODIC,
        MemoryKind.SEMANTIC,
    }


def test_recalled_memory_carries_metadata_but_never_becomes_clinical_authority():
    store = LongTermMemoryStore(_policy(), _manager())
    store.retain(_record(), consent_granted=True)
    item = store.context_items(_scope())[0]
    assert item.authority is ContextAuthority.MEMORY
    assert item.sensitivity is ContextSensitivity.PERSONAL
    assert item.provenance == "memory-source:memory-1"
    assert item.freshness == NOW
    assert not item.protected

    operational = ContextItem(
        id="dose-status",
        layer=ContextLayer.TOOL,
        content="authoritative dose state",
        token_count=999,
        authority=ContextAuthority.OPERATIONAL_DB,
        priority=1,
        provenance="tool:get_dose_status",
    )
    result = _manager(input_tokens=100).build([item, operational])
    assert result.included[0].item.id == "dose-status"
    assert result.status.value == "OVERFLOW"
    with pytest.raises(ValueError, match="cannot claim authoritative"):
        ContextItem(
            id="forged-memory",
            layer=ContextLayer.MEMORY,
            content="forged dose state",
            token_count=1,
            authority=ContextAuthority.OPERATIONAL_DB,
            priority=1,
            provenance="forged",
            memory_kind=MemoryKind.LONG_TERM_FACT,
        )


def test_stale_expired_and_invalidated_records_are_not_recalled_and_are_traceable():
    store = LongTermMemoryStore(_policy(), _manager())
    stale = _record("stale", verified_at=None)
    expired = _record("expired", expires_at=NOW + timedelta(minutes=1))
    active = _record("active")
    for record in (stale, expired, active):
        store.retain(record, consent_granted=True)
    invalidated = store.invalidate(_scope(), "active", reason="user correction", now=NOW + timedelta(minutes=1))
    assert invalidated.status is MemoryStatus.INVALIDATED
    recalled = store.recall(_scope(), now=NOW + timedelta(days=1))
    assert recalled.records == ()
    assert set(recalled.stale_or_inactive_ids) == {"stale", "expired", "active"}


def test_memory_scope_prevents_cross_actor_subject_patient_and_conversation_leakage():
    store = LongTermMemoryStore(_policy(), _manager())
    source_scope = _scope()
    store.retain(_record(scope=source_scope), consent_granted=True)
    assert store.recall(_scope(actor="actor-b")).records == ()
    assert store.recall(_scope(subject="subject-b")).records == ()
    assert store.recall(_scope(patient="patient-b")).records == ()
    assert store.recall(_scope(conversation="conversation-b")).records == ()
    with pytest.raises(ValueError, match="not found in this scope"):
        store.invalidate(_scope(conversation="conversation-b"), "memory-1", reason="wrong scope")


def test_compactor_is_versioned_and_refuses_policy_or_authoritative_clinical_context():
    compactor = ContextCompactor()
    ordinary = ContextItem(
        id="old-conversation",
        layer=ContextLayer.MEMORY,
        content="very long non-authoritative content",
        token_count=20,
        authority=ContextAuthority.MEMORY,
        priority=1,
        provenance="memory:old",
        memory_kind=MemoryKind.EPISODIC,
    )
    record = compactor.compact(ordinary, summary="short summary", token_count=3)
    compacted = compactor.apply(ordinary, record)
    assert record.compaction_version == ContextCompactor.VERSION
    assert compacted.compact_content == "short summary"
    assert "context-compactor" in compacted.provenance

    policy = ContextItem(
        id="policy",
        layer=ContextLayer.POLICY,
        content="must keep",
        token_count=10,
        authority=ContextAuthority.POLICY,
        priority=1,
        provenance="policy",
    )
    clinical = ContextItem(
        id="clinical",
        layer=ContextLayer.TOOL,
        content="authoritative",
        token_count=10,
        authority=ContextAuthority.SAFETY_DOMAIN,
        priority=1,
        provenance="safety",
    )
    with pytest.raises(PermissionError):
        compactor.compact(policy, summary="bad", token_count=1)
    with pytest.raises(PermissionError):
        compactor.compact(clinical, summary="bad", token_count=1)


def test_file_system_offload_keeps_only_reference_summary_and_verifies_integrity(tmp_path):
    offload = FileSystemArtifactOffload(tmp_path)
    reference = offload.offload(
        artifact_id="large-report-1",
        payload=b"large non-sensitive report payload",
        summary="Summary retained in context.",
        provenance="tool:report",
    )
    assert reference.uri.startswith("artifact://large-report-1/")
    assert reference.summary == "Summary retained in context."
    assert offload.read(reference) == b"large non-sensitive report payload"
    assert offload.offload(
        artifact_id="large-report-1",
        payload=b"large non-sensitive report payload",
        summary="Summary retained in context.",
        provenance="tool:report",
    ).sha256 == reference.sha256
    with pytest.raises(PermissionError, match="sensitive"):
        offload.offload(
            artifact_id="health-report",
            payload=b"phi",
            summary="PHI summary",
            provenance="tool:report",
            sensitivity=ContextSensitivity.HEALTH,
        )
    with pytest.raises(PermissionError, match="sensitive"):
        offload.offload(
            artifact_id="personal-report",
            payload=b"pii",
            summary="Personal-data summary",
            provenance="tool:report",
            sensitivity=ContextSensitivity.PERSONAL,
        )
    with pytest.raises(ValueError, match="safe"):
        offload.offload(
            artifact_id="../traversal",
            payload=b"x",
            summary="x",
            provenance="test",
        )


def test_combined_memory_context_requires_the_same_authenticated_actor_and_conversation():
    manager = _manager()
    short = ShortTermMemoryStore(manager)
    long = LongTermMemoryStore(_policy(), manager)
    key = SessionMemoryKey(actor_id="actor-a", conversation_id="conversation-a", session_id="session-a")
    short.append_message(key, entry_id="message", role=MessageRole.USER, content="question", token_count=5)
    long.retain(_record(), consent_granted=True)
    builder = AgentMemoryContextBuilder(manager, short, long)
    result = builder.build(key, _scope())
    assert {selection.item.memory_kind for selection in result.included} == {
        MemoryKind.SHORT_TERM,
        MemoryKind.LONG_TERM_FACT,
    }
    with pytest.raises(PermissionError, match="scopes must match"):
        builder.build(key, _scope(conversation="other-conversation"))
