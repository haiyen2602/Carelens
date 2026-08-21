"""BUILD-2 configuration and endpoint-contract tests; no real API credential required."""

from types import SimpleNamespace

import pytest

from backend.agents.v2.model_gateway import (
    MissingModelCredentialError,
    ModelRole,
    OpenAIModelGateway,
    SynthesisEvidence,
    build_model_workloads,
    missing_model_credentials,
)


def _settings(**overrides):
    values = {
        "openai_api_key": "backend-only-test-key",
        "openai_router_api_key": "",
        "openai_main_api_key": "",
        "openai_fallback_api_key": "",
        "openai_embedding_api_key": "",
        "openai_judge_api_key": "",
        "agent_router_model": "gpt-5.4-nano",
        "agent_main_model": "gpt-5.4-mini",
        "agent_fallback_model": "gpt-5.4",
        "agent_embedding_model": "text-embedding-3-small",
        "rag_judge_model": "gpt-4o",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_model_mapping_is_config_driven_and_uses_backend_key_fallback():
    workloads = build_model_workloads(_settings())
    assert {role: workload.model for role, workload in workloads.items()} == {
        ModelRole.ROUTER: "gpt-5.4-nano",
        ModelRole.MAIN: "gpt-5.4-mini",
        ModelRole.FALLBACK: "gpt-5.4",
        ModelRole.EMBEDDING: "text-embedding-3-small",
        ModelRole.JUDGE: "gpt-4o",
    }
    assert {workload.credential_source for workload in workloads.values()} == {"OPENAI_API_KEY"}
    assert not missing_model_credentials(workloads)


def test_missing_credential_fails_closed_before_any_api_request():
    workloads = build_model_workloads(_settings(openai_api_key=""))
    assert missing_model_credentials(workloads) == (
        "OPENAI_ROUTER_API_KEY",
        "OPENAI_MAIN_API_KEY",
        "OPENAI_FALLBACK_API_KEY",
        "OPENAI_EMBEDDING_API_KEY",
        "OPENAI_JUDGE_API_KEY",
    )
    with pytest.raises(MissingModelCredentialError):
        OpenAIModelGateway(workloads).smoke_all()


class _Responses:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["model"] == "gpt-5.4-nano":
            return {"output_text": '{"intent":"SMOKE"}', "usage": {"input_tokens": 1, "output_tokens": 1}}
        if kwargs["model"] == "gpt-5.4-mini":
            return {
                "output": [{"type": "function_call", "name": "search_drug", "arguments": '{"query":"para","limit":1}'}],
                "output_text": "",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        return {"output_text": "OK", "usage": {"input_tokens": 1, "output_tokens": 1}}


class _Embeddings:
    def create(self, **kwargs):
        return {"data": [{"embedding": [0.1]}], "usage": {"input_tokens": 1}}


class _Client:
    def __init__(self):
        self.responses = _Responses()
        self.embeddings = _Embeddings()


def test_smoke_checks_structured_router_and_main_tool_call_without_exposing_key():
    clients = []

    def factory(**kwargs):
        assert kwargs == {"api_key": "backend-only-test-key", "max_retries": 0, "timeout": 15.0}
        client = _Client()
        clients.append(client)
        return client

    results = OpenAIModelGateway(build_model_workloads(_settings()), client_factory=factory).smoke_all()
    assert all(result.passed for result in results)
    assert len(results) == 5
    router_call = clients[0].responses.calls[0]
    main_call = clients[1].responses.calls[0]
    assert "text" in router_call
    assert main_call["tool_choice"] == {"type": "function", "name": "search_drug"}


def test_embedding_gateway_uses_the_configured_embedding_workload_and_returns_a_typed_vector():
    gateway = OpenAIModelGateway(build_model_workloads(_settings()), client_factory=lambda **_kwargs: _Client())

    result = gateway.embed_query(text="retrieval query")

    assert result.model == "text-embedding-3-small"
    assert result.vector == (0.1,)


# ---------------------------------------------------------------------------
# BUILD-19B: the tool-calling loop's synthesis turn
# ---------------------------------------------------------------------------


class _SynthesisResponses:
    def __init__(self, response: dict):
        self._response = response
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class _SynthesisClient:
    def __init__(self, response: dict):
        self.responses = _SynthesisResponses(response)


def test_synthesize_read_only_never_offers_the_model_a_tools_schema():
    """Structural guarantee: synthesis cannot call a tool or otherwise act.

    ``plan_read_only`` is offered the six-tool allowlist; ``synthesize_read_only``
    must never be, so the model cannot call more tools, and therefore cannot
    override Safety/Doctor/Operational DB, during the synthesis turn.
    """

    client = _SynthesisClient(
        {"output_text": "Day la cau tra loi cuoi cung.", "usage": {"input_tokens": 5, "output_tokens": 4}, "_request_id": "req_synth_1"}
    )
    gateway = OpenAIModelGateway(build_model_workloads(_settings()), client_factory=lambda **_kwargs: client)
    evidence = (SynthesisEvidence(tool_name="search_drug", provenance="tool:search_drug", data={"items": []}),)

    synthesis = gateway.synthesize_read_only(message="tim thuoc para", actor_role="patient", evidence=evidence)

    assert synthesis.response == "Day la cau tra loi cuoi cung."
    assert synthesis.request_id == "req_synth_1"
    assert synthesis.usage.input_tokens == 5
    assert synthesis.usage.output_tokens == 4
    call = client.responses.calls[0]
    assert "tools" not in call
    assert "tool_choice" not in call


def test_synthesize_read_only_fails_closed_on_empty_output_text():
    """Even a second empty ``output_text`` must not silently reproduce BUILD-19."""

    client = _SynthesisClient({"output_text": "", "usage": {"input_tokens": 5, "output_tokens": 0}})
    gateway = OpenAIModelGateway(build_model_workloads(_settings()), client_factory=lambda **_kwargs: client)

    with pytest.raises(ValueError):
        gateway.synthesize_read_only(message="x", actor_role="patient", evidence=())
