"""Vong 3, muc 6 - build_greeting_node() tra loi co dinh (khong LLM/DB) khi
intent=="greeting". Duong SKIP da co o tests/test_intent_self_guards.py, file
nay chi test duong CHAY THAT."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from backend.agents.nodes.conversation_nodes import GREETING_RESPONSE, build_greeting_node  # noqa: E402


def _state(intent):
    return {"patient_id": "p1", "dose_event_id": None, "utterance": "xin chao", "trace": [], "intent": intent}


@pytest.mark.asyncio
async def test_greeting_node_returns_fixed_response_when_intent_is_greeting():
    node = build_greeting_node()
    result = await node(_state("greeting"))

    assert result["response"] == GREETING_RESPONSE
    assert result["trace"][-1]["step"] == "greeting"
    assert "skipped" not in result["trace"][-1]
