"""Feature flag regression for the isolated BUILD-1 Agent V2 path."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import backend.api.agent_v2_routes as agent_v2_routes
from backend.agents.v2.model_gateway import ModelRole, ModelUsage
from backend.agents.v2.observability import TraceContext
from backend.api.agent_v2_routes import (
    _in_rollout_percentage,
    _renderer_runtime_kwargs,
    _require_agent_v2_enabled,
    _shared_telemetry,
    run_read_only_agent,
)
from backend.api.security import CurrentUser
from backend.models.schemas import AgentV2ReadOnlyRequest


def test_agent_v2_route_is_off_by_default_without_touching_db():
    # The handler checks the OFF flag before authorizing or querying a patient.
    with pytest.raises(HTTPException) as exc:
        run_read_only_agent(
            AgentV2ReadOnlyRequest(patient_id="p-1", message="xin chao"),
            db=object(),
            actor=CurrentUser(id="user", role="patient", patient_id="p-1", doctor_id=None),
        )
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# BUILD-21: canary allowlist -- an ADDITIVE restriction on top of the flag,
# empty/unset by default so staging/local UAT is unaffected.
# ---------------------------------------------------------------------------


def _settings(**changes) -> SimpleNamespace:
    values = {"agent_runtime_enabled": True, "agent_canary_allowlist": ""}
    values.update(changes)
    return SimpleNamespace(**values)


def _actor(account_id: str = "account-1") -> CurrentUser:
    return CurrentUser(id=account_id, role="patient", patient_id="p-1", doctor_id=None)


def test_empty_allowlist_does_not_restrict_beyond_the_flag():
    # Unchanged behavior for staging/local -- every prior build's UAT relied
    # on exactly this (flag alone gates access).
    _require_agent_v2_enabled(_settings(agent_canary_allowlist=""), _actor("anyone"))  # does not raise


def test_flag_off_is_404_even_when_the_actor_is_on_the_allowlist():
    # The flag is the outer kill switch: no allowlist membership overrides it.
    with pytest.raises(HTTPException) as exc:
        _require_agent_v2_enabled(
            _settings(agent_runtime_enabled=False, agent_canary_allowlist="account-1"), _actor("account-1")
        )
    assert exc.value.status_code == 404


def test_actor_on_the_allowlist_proceeds():
    _require_agent_v2_enabled(
        _settings(agent_canary_allowlist="account-1, account-2"), _actor("account-2")
    )  # does not raise (whitespace around commas is tolerated)


def test_actor_not_on_the_allowlist_gets_the_identical_404_as_a_disabled_flag():
    # Indistinguishable from the outside: a non-canary caller must not be
    # able to tell "you're excluded" apart from "this doesn't exist".
    disabled = pytest.raises(HTTPException)
    with disabled as exc_disabled:
        _require_agent_v2_enabled(_settings(agent_runtime_enabled=False), _actor("outsider"))
    excluded = pytest.raises(HTTPException)
    with excluded as exc_excluded:
        _require_agent_v2_enabled(_settings(agent_canary_allowlist="account-1"), _actor("outsider"))
    assert exc_disabled.value.status_code == exc_excluded.value.status_code == 404
    assert exc_disabled.value.detail == exc_excluded.value.detail


def test_a_real_patient_account_never_accidentally_lands_on_a_test_allowlist():
    # The allowlist is account ids, never a role or a patient_id -- a real
    # patient asking about themselves is not implicitly "internal/test".
    with pytest.raises(HTTPException):
        _require_agent_v2_enabled(
            _settings(agent_canary_allowlist="agent-v2-staging-doctor-account"),
            CurrentUser(id="real-patient-42", role="patient", patient_id="real-patient-42", doctor_id=None),
        )


# ---------------------------------------------------------------------------
# BUILD-23: rollout percentage -- additive on top of (never a replacement
# for) the allowlist, 0 by default so every prior build's tests/UAT (which
# never set this) are completely unaffected.
# ---------------------------------------------------------------------------


def test_zero_percent_is_the_default_and_changes_nothing_when_no_allowlist_either():
    _require_agent_v2_enabled(_settings(), _actor("anyone"))  # does not raise -- unchanged from BUILD-22C


def test_zero_percent_with_no_allowlist_member_is_excluded_once_an_allowlist_exists():
    with pytest.raises(HTTPException):
        _require_agent_v2_enabled(_settings(agent_canary_allowlist="account-1"), _actor("outsider"))


def test_hundred_percent_admits_everyone():
    for account_id in ("a", "b", "some-real-patient-id", "another-one"):
        _require_agent_v2_enabled(_settings(agent_rollout_percentage=100), _actor(account_id))  # none raise


def test_bucket_assignment_is_deterministic_and_stable_per_actor():
    settings = _settings(agent_rollout_percentage=50)
    first = _in_rollout_percentage(settings, "account-1")
    second = _in_rollout_percentage(settings, "account-1")
    assert first == second


def test_an_actor_admitted_at_a_lower_percentage_stays_admitted_at_every_higher_one():
    # Monotonic inclusion -- BUILD-23's whole 5% -> 20% -> 50% -> 100% cutover
    # plan depends on this: nobody flip-flops in and out as the stage advances.
    account_id = "monotonic-test-account"
    admitted_from = None
    for pct in (1, 5, 10, 20, 35, 50, 70, 90, 99, 100):
        admitted = _in_rollout_percentage(_settings(agent_rollout_percentage=pct), account_id)
        if admitted and admitted_from is None:
            admitted_from = pct
        if admitted_from is not None:
            assert admitted, f"{account_id} dropped back out at {pct}% after being admitted at {admitted_from}%"


def test_bucket_distribution_is_reasonably_uniform_across_many_accounts():
    # Not a statistical proof, just a sanity check the hash isn't degenerate
    # (e.g. everyone landing in bucket 0) -- roughly 5% of 2000 synthetic
    # accounts should land inside a 5% threshold, generously bounded.
    settings = _settings(agent_rollout_percentage=5)
    admitted = sum(1 for i in range(2000) if _in_rollout_percentage(settings, f"account-{i}"))
    assert 60 <= admitted <= 160  # ~100 expected (5% of 2000), wide margin


def test_percentage_rollout_never_overrides_the_flag_being_off():
    with pytest.raises(HTTPException) as exc:
        _require_agent_v2_enabled(
            _settings(agent_runtime_enabled=False, agent_rollout_percentage=100), _actor("anyone")
        )
    assert exc.value.status_code == 404


def test_allowlist_member_is_always_admitted_regardless_of_percentage_bucket():
    # An account explicitly on the allowlist must never depend on winning a
    # hash bucket -- even at 0%, allowlisted accounts still get in.
    _require_agent_v2_enabled(
        _settings(agent_canary_allowlist="account-1", agent_rollout_percentage=0), _actor("account-1")
    )  # does not raise


def test_non_allowlisted_account_outside_the_bucket_still_gets_the_identical_404():
    disabled = pytest.raises(HTTPException)
    with disabled as exc_disabled:
        _require_agent_v2_enabled(_settings(agent_runtime_enabled=False), _actor("outsider"))
    excluded = pytest.raises(HTTPException)
    with excluded as exc_excluded:
        _require_agent_v2_enabled(
            _settings(agent_canary_allowlist="account-1", agent_rollout_percentage=0), _actor("outsider")
        )
    assert exc_disabled.value.status_code == exc_excluded.value.status_code == 404
    assert exc_disabled.value.detail == exc_excluded.value.detail


# ---------------------------------------------------------------------------
# BUILD-21: cost telemetry must actually be wired to settings-derived pricing,
# not just correctly parseable in isolation (BUILD-13 unit-tested
# ModelPricingCatalog.from_settings itself; nothing ever called it from the
# live route -- AgentTelemetry() with no arguments silently defaults to an
# EMPTY catalog, so estimated_cost_usd stayed None even with real pricing
# configured. Invisible until BUILD-21 actually verified live output on a
# real deployment instead of only the parsing step).
# ---------------------------------------------------------------------------


def test_shared_telemetry_is_wired_to_the_configured_pricing_catalog():
    agent_v2_routes._telemetry = None  # force a fresh singleton for this test
    try:
        settings = SimpleNamespace(
            agent_model_pricing_json='{"gpt-5.4-mini": {"input_per_million": 0.75, "cached_input_per_million": 0.075, "output_per_million": 4.5}}'
        )
        telemetry = _shared_telemetry(settings)
        estimate = telemetry.record_model(
            TraceContext.create(),
            role=ModelRole.MAIN,
            model="gpt-5.4-mini",
            usage=ModelUsage(input_tokens=1000, cached_input_tokens=0, output_tokens=200),
            latency_ms=1.0,
        )
        # (1000*0.75 + 200*4.5) / 1_000_000 -- not the None BUILD-13's default
        # empty catalog would have produced for a perfectly valid, known model.
        assert estimate.estimated_cost_usd == pytest.approx(0.00165)
    finally:
        agent_v2_routes._telemetry = None  # do not leak this singleton into other tests


def test_shared_telemetry_still_returns_none_for_a_genuinely_unknown_model():
    # Fail-safe direction unchanged: an unpriced model is still None, never a
    # fabricated $0 -- the fix only makes a *configured* price actually apply.
    agent_v2_routes._telemetry = None
    try:
        settings = SimpleNamespace(agent_model_pricing_json="{}")
        telemetry = _shared_telemetry(settings)
        estimate = telemetry.record_model(
            TraceContext.create(),
            role=ModelRole.MAIN,
            model="some-unpriced-model",
            usage=ModelUsage(input_tokens=1000, output_tokens=200),
            latency_ms=1.0,
        )
        assert estimate.estimated_cost_usd is None
    finally:
        agent_v2_routes._telemetry = None


# ---------------------------------------------------------------------------
# TASK-V2.5-004: renderer must stay INERT at every route until a response-
# type eligibility gate exists (V2.5-DESIGN.md mục 7's allowlist). The
# mechanism (ReadOnlyAgentRuntime's renderer_enabled) already works, but the
# route layer must not honor AGENT_V2_5_RENDERER_ENABLED yet -- setting that
# env var alone on a real deployment must have zero effect today, since it
# would otherwise silently expand the renderer to the whole generic tool-
# loop, far broader than what has been reviewed.
# ---------------------------------------------------------------------------


def test_renderer_runtime_kwargs_stays_off_even_when_settings_flag_is_true():
    settings = SimpleNamespace(agent_v2_5_renderer_enabled=True, agent_renderer_model="gpt-5.6-luna")
    kwargs = _renderer_runtime_kwargs(settings)
    assert kwargs["renderer_enabled"] is False


def test_renderer_runtime_kwargs_stays_off_when_settings_flag_is_false_too():
    settings = SimpleNamespace(agent_v2_5_renderer_enabled=False, agent_renderer_model="gpt-5.6-luna")
    kwargs = _renderer_runtime_kwargs(settings)
    assert kwargs["renderer_enabled"] is False


def test_renderer_runtime_kwargs_still_carries_the_real_renderer_model_name():
    """Harmless while renderer_enabled=False (never read), but already wired
    correctly for when the eligibility gate lands -- no second change needed
    at that point just to plumb the model name through."""
    settings = SimpleNamespace(agent_v2_5_renderer_enabled=True, agent_renderer_model="gpt-5.6-luna")
    kwargs = _renderer_runtime_kwargs(settings)
    assert kwargs["renderer_model_name"] == "gpt-5.6-luna"
