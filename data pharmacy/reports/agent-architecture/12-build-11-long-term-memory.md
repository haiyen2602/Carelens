# BUILD-11 — Long-Term Memory, Compaction, and Artifact Offload

Date: 2026-08-18  
Scope: Agent V2 memory boundary only. `AGENT_RUNTIME_ENABLED=false` remains
unchanged. No Agent write action, legacy chat change, migration, or production
memory collection was added.

## Long-term memory policy and record model

`backend/agents/v2/long_term_memory.py` adds a policy-gated memory store for
the three approved context allocations:

| Memory kind | Maximum share of input context | Retention class |
| --- | ---: | --- |
| Short-term (existing BUILD-5) | 10% | session only |
| Long-term facts | 4% | `APPROVED_LONG_TERM` |
| Episodic | 3% | `EPISODIC` |
| Semantic knowledge | 3% | `SEMANTIC` |

The collection boundary requires a named/versioned `MemoryCollectionPolicy`.
It must be explicitly approved, name permitted categories and kinds, set a
maximum retention, and require consent when configured. Retention fails closed
without approval or consent, for a category/kind outside policy, or if the
expiry exceeds policy. The disabled runtime does not instantiate a collection
policy or retain any user memory.

Every record carries the required traceability metadata: memory ID, actor /
subject / conversation / optional patient scope, type/category, content,
source, provenance, created/updated/last-verified timestamps, confidence,
sensitivity, retention class, expiry, and status/invalidation reason. A record
with no current verification, expiry, or invalidation is not recalled. Explicit
invalidation is scoped and idempotent.

## Authority, isolation, and Context Manager integration

`AgentMemoryContextBuilder` combines the existing session-isolated
Short-term Memory store and policy-gated long-term records only when the
authenticated actor and conversation match exactly. Long-term storage and
recall are also constrained by actor, subject user, patient, and conversation;
there is no cross-scope lookup or mutation path.

Recalled records are always rendered as `ContextLayer.MEMORY` with
`ContextAuthority.MEMORY`, regardless of their remembered source. Context now
rejects any memory item that attempts to claim Drug Knowledge V2, Operational
DB, Safety, Doctor, or another authoritative domain authority. Consequently a
fresh domain-tool lookup remains authoritative over a remembered user claim or
previous reference. Provenance, freshness, sensitivity, and verification status
are carried to Context Manager alongside the existing memory-kind quotas.

## Compaction and artifact offload

`ContextCompactor` is deterministic and versioned (`build-11-v1`). It records
the source item ID and SHA-256, compaction version, provenance, reference, and
reduced summary/token count. It refuses both Policy Context and protected
authoritative clinical context, so those facts are neither compacted nor
dropped. The source remains available for rehydration by its retained record or
artifact reference.

`FileSystemArtifactOffload` is a replaceable local adapter for large,
non-authoritative payloads. The prompt-facing reference contains only an
`artifact://` ID, summary, provenance, sensitivity, byte count, and SHA-256;
reads verify the digest and length. Paths are constrained to a safe artifact ID
and writes are atomic. Personal, health, and restricted artifacts are denied by default, so
local disk cannot silently become a PHI store. It is explicitly not an
authoritative store for prescriptions, doses, or Safety decisions.

## Validation

- Long-term fact, episodic, and semantic allocations validate at 4% / 3% / 3%;
  short-term remains capped at 10%.
- Policy approval, consent, category/kind, retention, expiry, stale detection,
  and invalidation fail closed.
- Cross actor, subject, patient, and conversation recall/mutation attempts are
  denied; mismatched short-/long-term context assembly is denied.
- A forged memory item with authoritative Operational DB authority is rejected.
- Compaction preserves audit/provenance metadata and rejects Policy/Safety
  context; offload verifies integrity and rejects traversal and sensitive
  content by default.
- Focused context/memory tests: **22 passed**.
- Full Agent V2 regression: **92 passed, 1 skipped** (the existing
  environment-dependent test remains skipped).
- Ruff for changed files and `git diff --check`: **PASS**.

## P0/P1

- **P0: none.** The runtime remains disabled, memory collection is opt-in and
  fail-closed, and recalled data cannot claim clinical authority.
- **P1: production memory governance and durable storage.** Before enabling
  memory, the team must approve allowed/prohibited categories, consent,
  retention/deletion/correction, re-verification, and retrieval policy; then
  provide encrypted durable storage and key/backup/access controls. The local
  in-process store and optional non-sensitive filesystem adapter are deliberate
  test/runtime-boundary implementations, not a production PHI store.
- **P1: memory retrieval evaluation.** Memory Hit/Precision/Recall, stale
  error rate, cross-user leakage rate, and clinical-override rate need an
  approved evaluation corpus before release.

## Conclusion

BUILD-11: PASS

LONG-TERM FACTS: PASS

EPISODIC MEMORY: PASS

SEMANTIC MEMORY: PASS

COMPACTOR: PASS

FILE OFFLOAD: PASS

AUTHORITY/ISOLATION: PASS

REGRESSION: PASS

READY FOR BUILD-12: YES
