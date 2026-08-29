"""BUILD-49: the short-term memory session key must be stable across turns.

`ShortTermMemoryStore` has worked correctly since BUILD-5 -- it keeps the
recent turns of a conversation and feeds them to the Main Model as MEMORY
context. It has also been dead in production the entire time.

The store is keyed by ``SessionMemoryKey(actor_id, conversation_id,
session_id)``, and the route filled the last field with
``request.session_id or str(uuid.uuid4())``. No client sends ``session_id``
(verified across all of ``frontend/src``), so every HTTP request minted a
brand-new random session, wrote the current message into it, and read back
only that same message. Measured before the fix: turn 1 recalls 1 message,
turn 2 recalls 1 message -- never 2.

Falling back to ``conversation_id`` (which the frontend does send, and which
the route already defaults to a unique ``one-shot:<uuid>`` when absent) makes
the key stable for a real conversation while keeping a one-shot request
isolated exactly as before.

These tests assert the mechanism end to end through the real orchestrator:
what actually matters is that turn 2's prompt can see turn 1, not that a
particular string was passed around.
"""

from __future__ import annotations

from backend.agents.v2.context import ContextBudget, ContextManager, MemoryKind
from backend.agents.v2.model_gateway import ModelPlan
from backend.agents.v2.short_term_memory import ShortTermMemoryStore
from tests.test_agent_v2_orchestrator import _orchestrator, _request, _SpyModelGateway, _tools


def _store() -> ShortTermMemoryStore:
    return ShortTermMemoryStore(
        ContextManager(
            ContextBudget(
                input_token_budget=4000,
                output_token_reserve=500,
                total_run_token_budget=5000,
                memory_fractions={
                    MemoryKind.SHORT_TERM: 0.4,
                    MemoryKind.LONG_TERM_FACT: 0.1,
                    MemoryKind.EPISODIC: 0.1,
                    MemoryKind.SEMANTIC: 0.1,
                },
            )
        )
    )


def test_a_stable_session_lets_the_second_turn_see_the_first():
    orchestrator, gateway = _orchestrator(
        model_gateway=_SpyModelGateway(ModelPlan(response="ok")), short_term_memory=_store()
    )
    orchestrator.run(_request("Paracetamol la gi", session_id="s-1", conversation_id="c-1"), tools=_tools())
    orchestrator.run(_request("Ibuprofen la gi", session_id="s-1", conversation_id="c-1"), tools=_tools())

    assert len(gateway.calls) == 2, "both turns must actually reach the model"
    assert "Paracetamol la gi" in gateway.calls[-1]["message"], (
        "turn 2's prompt must carry turn 1 as memory context"
    )


def test_a_fresh_session_per_turn_remembers_nothing():
    """The production bug, reproduced: a new session id every turn.

    This is what `request.session_id or str(uuid.uuid4())` produced on every
    HTTP request, and it is why the memory layer never did anything.
    """
    orchestrator, gateway = _orchestrator(
        model_gateway=_SpyModelGateway(ModelPlan(response="ok")), short_term_memory=_store()
    )
    orchestrator.run(_request("Paracetamol la gi", session_id="s-1", conversation_id="c-1"), tools=_tools())
    orchestrator.run(_request("Ibuprofen la gi", session_id="s-2", conversation_id="c-1"), tools=_tools())

    assert "Paracetamol la gi" not in gateway.calls[-1]["message"]


def test_separate_conversations_never_share_memory():
    """Isolation is unchanged: the key still carries actor and conversation."""
    orchestrator, gateway = _orchestrator(
        model_gateway=_SpyModelGateway(ModelPlan(response="ok")), short_term_memory=_store()
    )
    orchestrator.run(_request("Paracetamol la gi", session_id="c-1", conversation_id="c-1"), tools=_tools())
    orchestrator.run(_request("Ibuprofen la gi", session_id="c-2", conversation_id="c-2"), tools=_tools())

    assert "Paracetamol la gi" not in gateway.calls[-1]["message"]


def test_route_falls_back_to_the_conversation_id_when_no_session_is_sent():
    """The fix itself, at the boundary that had the defect.

    Asserted against the real route source rather than a mock: the failure
    was one expression, and a test that re-implements it would pass whether
    or not the route was ever changed.
    """
    import inspect

    from backend.api import agent_v2_routes

    source = inspect.getsource(agent_v2_routes.run_agent_orchestration)
    assert "session_id=request.session_id or conversation_id" in source
    assert "session_id=request.session_id or str(uuid.uuid4())" not in source
