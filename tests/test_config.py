"""Unit tests for backend/config.py Settings validators.

Focused scope: this file currently only covers CAPYMEDI_RUNTIME_PROFILE
(chat-bot-build/chat-bot-v3/docs/runtime_config_v3.md SS13.1/SS20) -- the
single V3 rollout-profile switch that doubles as the rollback-to-V2 kill
switch once a V3 runtime exists. It must default to "v2_only" and fail
startup on anything else until a real V3 stage is implemented in code (see
chat-bot-build/chat-bot-v3/reports/phase_0_task_01_contract_and_rollback_readiness.md).
Other Settings fields already have their own fail-closed validators
(internal_auth_secret, jwt_secret) exercised indirectly via the `client`
fixture elsewhere in the suite; this file does not attempt to cover the
whole Settings surface.
"""

import pytest
from pydantic import ValidationError

from backend.config import Settings


def _minimal_env(**overrides):
    """``Settings()`` reads process env + ``.env``; supply the fields with
    no safe default (fail-closed secrets) explicitly so a validation
    failure under test is about the field actually being tested, not an
    unrelated missing secret picked up from whatever ``.env`` happens to be
    on disk."""
    base = {
        "internal_auth_secret": "test-internal-secret",
        "jwt_secret": "test-jwt-secret",
    }
    base.update(overrides)
    return base


def test_capymedi_runtime_profile_defaults_to_v2_only():
    settings = Settings(**_minimal_env())
    assert settings.capymedi_runtime_profile == "v2_only"


@pytest.mark.parametrize("value", ["v3_shadow", "v3_canary_read_only", "v3_production"])
def test_capymedi_runtime_profile_rejects_documented_v3_values_until_implemented(value):
    # These three values ARE part of the documented contract
    # (runtime_config_v3.md SS13.1) and are declared in the Literal type for
    # that reason, but no V3 stage (Planner/Workflow Router/Generator/
    # Reviewer) exists in code yet -- accepting them here would let an
    # operator silently misconfigure Railway with a profile that does
    # nothing, which is exactly the failure mode the rollback switch exists
    # to prevent.
    with pytest.raises(ValidationError, match="CAPYMEDI_RUNTIME_PROFILE"):
        Settings(**_minimal_env(capymedi_runtime_profile=value))


def test_capymedi_runtime_profile_rejects_unknown_value():
    with pytest.raises(ValidationError):
        Settings(**_minimal_env(capymedi_runtime_profile="bogus"))
