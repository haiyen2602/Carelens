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
        "openai_renderer_api_key": "",
        "agent_router_model": "gpt-5.4-nano",
        "agent_main_model": "gpt-5.4-mini",
        "agent_fallback_model": "gpt-5.4",
        "agent_embedding_model": "text-embedding-3-small",
        "rag_judge_model": "gpt-4o",
        "agent_renderer_model": "gpt-5.6-luna",
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
        # TASK-V2.5-004: separate workload so the renderer's model can never
        # accidentally change the planner's (ModelRole.MAIN) model -- the
        # exact coupling bug this new role exists to avoid (CP0 mục 1.4a).
        ModelRole.RENDERER: "gpt-5.6-luna",
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
        "OPENAI_RENDERER_API_KEY",
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
    assert len(results) == 6
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

    assert synthesis.free_prose == "Day la cau tra loi cuoi cung."
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


# ---------------------------------------------------------------------------
# TASK-V2.5-004: opting into the renderer contract (policy/fact_slots passed)
# switches the workload to ModelRole.RENDERER without changing MAIN. Omitting
# both (every test above) must stay byte-identical to pre-existing behavior
# -- that is the whole point of making them optional/additive.
# ---------------------------------------------------------------------------


def test_synthesize_read_only_omitting_policy_uses_main_workload_unchanged():
    """Non-regression lock: the default (no policy/fact_slots) path must
    still call MAIN's model, never RENDERER's -- confirms the additive
    param design carries zero behavior change for every existing caller."""
    client = _SynthesisClient({"output_text": "ok", "usage": {"input_tokens": 1, "output_tokens": 1}})
    gateway = OpenAIModelGateway(build_model_workloads(_settings()), client_factory=lambda **_kwargs: client)

    gateway.synthesize_read_only(message="x", actor_role="patient", evidence=())

    assert client.responses.calls[0]["model"] == "gpt-5.4-mini"


def test_synthesize_read_only_with_policy_and_fact_slots_uses_renderer_workload():
    from backend.agents.v2.response_policy import Answerability, RenderableFactSlots, ResponsePolicy

    client = _SynthesisClient(
        {"output_text": "Day la loi dan tu nhien.", "usage": {"input_tokens": 3, "output_tokens": 2}}
    )
    gateway = OpenAIModelGateway(build_model_workloads(_settings()), client_factory=lambda **_kwargs: client)
    policy = ResponsePolicy(
        route_category="drug_information",
        answerability=Answerability.ANSWERABLE,
        allowed_fact_refs=("drug_name",),
        prohibited_claim_categories=(),
        clarification_target=None,
        handoff_state=None,
        suggested_action_refs=(),
    )
    fact_slots = RenderableFactSlots(drug_name="Paracetamol 500mg")

    synthesis = gateway.synthesize_read_only(
        message="thuoc nay la gi", actor_role="patient", evidence=(), policy=policy, fact_slots=fact_slots
    )

    assert synthesis.free_prose == "Day la loi dan tu nhien."
    call = client.responses.calls[0]
    assert call["model"] == "gpt-5.6-luna"
    assert "tools" not in call
    assert "tool_choice" not in call


def _renderer_policy(**overrides):
    from backend.agents.v2.response_policy import Answerability, ResponsePolicy

    values = dict(
        route_category="drug_information",
        answerability=Answerability.ANSWERABLE,
        allowed_fact_refs=(),
        prohibited_claim_categories=(),
        clarification_target=None,
        handoff_state=None,
        suggested_action_refs=(),
    )
    values.update(overrides)
    return ResponsePolicy(**values)


# ---------------------------------------------------------------------------
# Owner correction (post first-draft CP2): the renderer must NEVER receive
# raw evidence or any protected fact value, populated or not -- only the
# allowlisted RendererContext. These sentinel-absence tests prove it at the
# actual prompt-string boundary, not just at the assemble_reply boundary
# (tests/test_agent_v2_response_policy.py already covers that layer).
# ---------------------------------------------------------------------------


def test_synthesize_read_only_renderer_path_never_sends_raw_evidence_to_the_model():
    """The old (rejected) design showed the model full evidence "for
    context". A sentinel value that would only ever appear if raw evidence
    reached the prompt must be verifiably absent."""
    from backend.agents.v2.response_policy import RenderableFactSlots

    client = _SynthesisClient({"output_text": "ok", "usage": {"input_tokens": 1, "output_tokens": 1}})
    gateway = OpenAIModelGateway(build_model_workloads(_settings()), client_factory=lambda **_kwargs: client)
    evidence = (
        SynthesisEvidence(
            tool_name="get_drug_info",
            provenance="canonical-drug-v2",
            data={"side_effects": ["SENTINEL-RAW-EVIDENCE-LEAK"]},
        ),
    )

    gateway.synthesize_read_only(
        message="x", actor_role="patient", evidence=evidence, policy=_renderer_policy(), fact_slots=RenderableFactSlots()
    )

    assert "SENTINEL-RAW-EVIDENCE-LEAK" not in client.responses.calls[0]["input"]


def test_synthesize_read_only_renderer_path_never_sends_a_populated_drug_name_to_the_model():
    """Even when drug_name IS confirmed (fact_slots populated), the model
    must never see the value itself -- assemble_reply inserts it verbatim
    afterward; the model was never shown it, so it structurally cannot
    restate/paraphrase it."""
    from backend.agents.v2.response_policy import RenderableFactSlots

    client = _SynthesisClient({"output_text": "ok", "usage": {"input_tokens": 1, "output_tokens": 1}})
    gateway = OpenAIModelGateway(build_model_workloads(_settings()), client_factory=lambda **_kwargs: client)
    fact_slots = RenderableFactSlots(drug_name="SENTINEL-DRUG-NAME-XYZ")

    gateway.synthesize_read_only(message="x", actor_role="patient", evidence=(), policy=_renderer_policy(), fact_slots=fact_slots)

    assert "SENTINEL-DRUG-NAME-XYZ" not in client.responses.calls[0]["input"]


def test_synthesize_read_only_renderer_path_never_sends_populated_dose_schedule_or_status_to_the_model():
    from backend.agents.v2.response_policy import RenderableFactSlots

    client = _SynthesisClient({"output_text": "ok", "usage": {"input_tokens": 1, "output_tokens": 1}})
    gateway = OpenAIModelGateway(build_model_workloads(_settings()), client_factory=lambda **_kwargs: client)
    fact_slots = RenderableFactSlots(
        dose_schedule_summary="SENTINEL-SCHEDULE-08H00-20H00", dose_status_summary="SENTINEL-STATUS-TAKEN"
    )

    gateway.synthesize_read_only(message="x", actor_role="patient", evidence=(), policy=_renderer_policy(), fact_slots=fact_slots)

    call_input = client.responses.calls[0]["input"]
    assert "SENTINEL-SCHEDULE-08H00-20H00" not in call_input
    assert "SENTINEL-STATUS-TAKEN" not in call_input


def test_synthesize_read_only_renderer_path_never_sends_populated_handoff_state_to_the_model():
    from backend.agents.v2.response_policy import RenderableFactSlots

    client = _SynthesisClient({"output_text": "ok", "usage": {"input_tokens": 1, "output_tokens": 1}})
    gateway = OpenAIModelGateway(build_model_workloads(_settings()), client_factory=lambda **_kwargs: client)
    policy = _renderer_policy(handoff_state="SENTINEL-HANDOFF-STATE")

    gateway.synthesize_read_only(message="x", actor_role="patient", evidence=(), policy=policy, fact_slots=RenderableFactSlots())

    assert "SENTINEL-HANDOFF-STATE" not in client.responses.calls[0]["input"]


def test_synthesize_read_only_renderer_path_fails_closed_on_empty_free_prose():
    from backend.agents.v2.response_policy import RenderableFactSlots

    client = _SynthesisClient({"output_text": "  ", "usage": {"input_tokens": 1, "output_tokens": 0}})
    gateway = OpenAIModelGateway(build_model_workloads(_settings()), client_factory=lambda **_kwargs: client)

    with pytest.raises(ValueError):
        gateway.synthesize_read_only(
            message="x", actor_role="patient", evidence=(), policy=_renderer_policy(), fact_slots=RenderableFactSlots()
        )


# ---------------------------------------------------------------------------
# Owner-required adversarial invariant: the model hallucinates a prohibited
# claim on its own (from nothing -- it was never shown a fact value) --
# validate_free_prose must reject it and the gateway must fail closed
# BEFORE any caller could call assemble_reply with this output.
# ---------------------------------------------------------------------------


def test_synthesize_read_only_renderer_path_fails_closed_when_model_hallucinates_a_prohibited_claim():
    from backend.agents.v2.model_gateway import ProhibitedClaimLeakError
    from backend.agents.v2.response_policy import RenderableFactSlots

    client = _SynthesisClient(
        {"output_text": "Bạn nên uống vào lúc 8 giờ sáng.", "usage": {"input_tokens": 1, "output_tokens": 1}}
    )
    gateway = OpenAIModelGateway(build_model_workloads(_settings()), client_factory=lambda **_kwargs: client)
    policy = _renderer_policy(prohibited_claim_categories=("dose_time", "dose_status", "medication_identity", "handoff_state"))

    with pytest.raises(ProhibitedClaimLeakError):
        gateway.synthesize_read_only(
            message="x", actor_role="patient", evidence=(), policy=policy, fact_slots=RenderableFactSlots()
        )
