"""BUILD-6 contract tests for the strict Agent V2 read-only Tool Gateway."""

from datetime import UTC, datetime

import pytest

from backend.agents.v2.context import (
    ContextAuthority,
    ContextBudget,
    ContextDisposition,
    ContextItem,
    ContextLayer,
    ContextManager,
    MemoryKind,
)
from backend.agents.v2.tools import (
    AuthorizedToolContext,
    ToolExecutionError,
    ToolGateway,
    ToolName,
)
from backend.services.agent_read_only_tools import AgentReadOnlyDomainTools


class _DomainTools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def search_drug(self, *, query, limit):
        self.calls.append(("search_drug", {"query": query, "limit": limit}))
        return {"items": [{"legacy_drug_id": "drug-1", "name": "Drug 1", "dosage_form": "tablet", "route": "oral"}]}

    def get_drug_info(self, *, legacy_drug_id, query):
        self.calls.append(("get_drug_info", {"legacy_drug_id": legacy_drug_id, "query": query}))
        return {"legacy_drug_id": legacy_drug_id, "results": [{"field": "cong_dung", "content": "x", "source": "canonical"}], "trace": {"mode": "v2"}}

    def get_active_prescriptions(self, *, patient_id):
        self.calls.append(("get_active_prescriptions", {"patient_id": patient_id}))
        return {"items": [{"id": "rx-1", "status": "active", "note": None, "start_date": "2026-08-18", "duration_days": 7}]}

    def get_today_doses(self, *, patient_id):
        self.calls.append(("get_today_doses", {"patient_id": patient_id}))
        return {"items": [self._dose("today-1")]}

    def get_upcoming_doses(self, *, patient_id):
        self.calls.append(("get_upcoming_doses", {"patient_id": patient_id}))
        return {"items": [self._dose("upcoming-1")]}

    def get_dose_status(self, *, patient_id, dose_id):
        self.calls.append(("get_dose_status", {"patient_id": patient_id, "dose_id": dose_id}))
        return self._dose(dose_id)

    @staticmethod
    def _dose(dose_id):
        return {
            "id": dose_id,
            "prescription_id": "rx-1",
            "scheduled_at": "2026-08-18T08:00:00+00:00",
            "window_start": "2026-08-18T07:30:00+00:00",
            "window_end": "2026-08-18T08:30:00+00:00",
            "status": "PENDING",
            "expected_items": [{"drug_id": "drug-1", "ten_thuoc": "Drug 1"}],
        }


def _gateway(domain=None):
    return ToolGateway(
        domain or _DomainTools(),
        context=AuthorizedToolContext(actor_id="actor-1", actor_role="patient", patient_id="patient-1"),
        now=lambda: datetime(2026, 8, 18, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    ("name", "arguments", "expected_authority", "expected_provenance"),
    [
        (ToolName.SEARCH_DRUG.value, {"query": "para", "limit": 5}, ContextAuthority.DRUG_KNOWLEDGE_V2, "canonical-drug-v2:catalog"),
        (ToolName.GET_DRUG_INFO.value, {"legacy_drug_id": "drug-1", "query": "cong dung"}, ContextAuthority.DRUG_KNOWLEDGE_V2, "canonical-drug-v2:knowledge"),
        (ToolName.GET_ACTIVE_PRESCRIPTIONS.value, {}, ContextAuthority.OPERATIONAL_DB, "operational-db:prescription:active"),
        (ToolName.GET_TODAY_DOSES.value, {}, ContextAuthority.OPERATIONAL_DB, "operational-db:dose-occurrence:today"),
        (ToolName.GET_UPCOMING_DOSES.value, {}, ContextAuthority.OPERATIONAL_DB, "operational-db:dose-occurrence:upcoming"),
        (ToolName.GET_DOSE_STATUS.value, {"dose_id": "dose-1"}, ContextAuthority.OPERATIONAL_DB, "operational-db:dose-occurrence:status"),
    ],
)
def test_all_six_allowlisted_tools_validate_and_return_authoritative_metadata(
    name, arguments, expected_authority, expected_provenance
):
    gateway = _gateway()
    result = gateway.execute(name, arguments)

    assert result.name == name
    assert result.authority is expected_authority
    assert result.provenance == expected_provenance
    assert result.freshness == datetime(2026, 8, 18, tzinfo=UTC)
    assert result.data


def test_patient_scope_is_server_owned_and_cannot_be_overridden_by_tool_arguments():
    domain = _DomainTools()
    gateway = _gateway(domain)

    with pytest.raises(ToolExecutionError, match="INVALID_TOOL_ARGUMENTS"):
        gateway.execute("get_dose_status", {"dose_id": "dose-1", "patient_id": "patient-2"})
    assert domain.calls == []

    gateway.execute("get_dose_status", {"dose_id": "dose-1"})
    assert domain.calls == [("get_dose_status", {"patient_id": "patient-1", "dose_id": "dose-1"})]


def test_domain_adapter_denies_an_opaque_dose_group_owned_by_another_patient(monkeypatch):
    class _OtherPatientGroup:
        patient_id = "patient-2"

    monkeypatch.setattr("backend.services.agent_read_only_tools.get_v2_dose_group", lambda _db, *, dose_group_id: _OtherPatientGroup())
    gateway = _gateway(AgentReadOnlyDomainTools(object()))

    with pytest.raises(ToolExecutionError, match="TOOL_UNAVAILABLE"):
        gateway.execute("get_dose_status", {"dose_id": "other-patient-dose"})


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("mark_dose_taken", {}),
        ("search_drug", {"query": "", "limit": 5}),
        ("search_drug", {"query": "para", "limit": 21}),
        ("get_active_prescriptions", {"unexpected": True}),
        ("get_dose_status", {}),
    ],
)
def test_disallowed_or_invalid_tool_calls_fail_closed_before_any_domain_read(name, arguments):
    domain = _DomainTools()
    with pytest.raises(ToolExecutionError) as exc:
        _gateway(domain).execute(name, arguments)
    assert str(exc.value) in {"TOOL_NOT_ALLOWED", "INVALID_TOOL_ARGUMENTS"}
    assert domain.calls == []


def test_domain_failure_and_malformed_output_are_sanitized():
    class _FailingDomain(_DomainTools):
        def search_drug(self, *, query, limit):
            raise RuntimeError("SELECT patient data from internal table")

    with pytest.raises(ToolExecutionError, match="TOOL_UNAVAILABLE"):
        _gateway(_FailingDomain()).execute("search_drug", {"query": "para", "limit": 5})

    class _MalformedDomain(_DomainTools):
        def get_today_doses(self, *, patient_id):
            return {"items": [{"id": "missing-required-fields"}]}

    with pytest.raises(ToolExecutionError, match="TOOL_UNAVAILABLE"):
        _gateway(_MalformedDomain()).execute("get_today_doses", {})


def test_tool_result_becomes_protected_tool_context_and_memory_cannot_replace_it():
    tool_context = _gateway().execute("get_dose_status", {"dose_id": "dose-1"}).to_context_item(context_id="tool:dose-1")
    user_memory = ContextItem(
        id="memory:claim",
        layer=ContextLayer.MEMORY,
        content="I already took this dose.",
        token_count=10,
        authority=ContextAuthority.USER_ASSERTED,
        priority=100,
        provenance="short-term-memory:user-message",
        memory_kind=MemoryKind.SHORT_TERM,
    )
    budget = ContextBudget(
        input_token_budget=10,
        output_token_reserve=1,
        total_run_token_budget=11,
        memory_fractions={
            MemoryKind.SHORT_TERM: 0.10,
            MemoryKind.LONG_TERM_FACT: 0.04,
            MemoryKind.EPISODIC: 0.03,
            MemoryKind.SEMANTIC: 0.03,
        },
    )
    result = ContextManager(budget).build([user_memory, tool_context])
    by_id = {selection.item.id: selection for selection in result.selections}

    assert by_id["tool:dose-1"].disposition is ContextDisposition.KEPT
    assert by_id["tool:dose-1"].item.authority is ContextAuthority.OPERATIONAL_DB
    assert by_id["memory:claim"].disposition is ContextDisposition.DROPPED
