"""Typed, allowlisted Agent V2 gateway for audited read-only domain adapters."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from math import ceil
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.agents.v2.context import ContextAuthority, ContextItem, ContextLayer


class ToolName(StrEnum):
    SEARCH_DRUG = "search_drug"
    GET_DRUG_INFO = "get_drug_info"
    GET_ACTIVE_PRESCRIPTIONS = "get_active_prescriptions"
    GET_TODAY_DOSES = "get_today_doses"
    GET_UPCOMING_DOSES = "get_upcoming_doses"
    GET_DOSE_STATUS = "get_dose_status"


READ_ONLY_TOOLS = frozenset(tool.value for tool in ToolName)


class ToolExecutionError(ValueError):
    """Safe code only; never pass ORM, provider, or SQL errors to the model."""


@dataclass(frozen=True)
class AuthorizedToolContext:
    """Server-created patient scope after ``require_agent_patient_access``."""

    actor_id: str
    actor_role: str
    patient_id: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("actor_id", self.actor_id),
            ("actor_role", self.actor_role),
            ("patient_id", self.patient_id),
        ):
            if not value or not value.strip():
                raise ValueError(f"{field_name} is required for authorized tool scope")


@dataclass(frozen=True)
class ToolResult:
    name: str
    data: dict[str, Any]
    provenance: str = "tool:unknown"
    authority: ContextAuthority = ContextAuthority.TOOL
    freshness: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_context_item(self, *, context_id: str, priority: int = 70, relevance: float = 1.0) -> ContextItem:
        """Expose a typed result to BUILD-4 as authoritative Tool Context."""
        rendered = json.dumps(self.data, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)
        return ContextItem(
            id=context_id,
            layer=ContextLayer.TOOL,
            content=rendered,
            token_count=max(1, ceil(len(rendered) / 4)),
            authority=self.authority,
            priority=priority,
            provenance=self.provenance,
            freshness=self.freshness,
            relevance=relevance,
        )


class _StrictArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SearchDrugArguments(_StrictArguments):
    query: str = Field(min_length=1, max_length=100)
    limit: int = Field(ge=1, le=20)


class GetDrugInfoArguments(_StrictArguments):
    legacy_drug_id: str = Field(min_length=1, max_length=200)
    query: str = Field(max_length=500)


class EmptyArguments(_StrictArguments):
    pass


class GetDoseStatusArguments(_StrictArguments):
    dose_id: str = Field(min_length=1, max_length=200)


class DrugSearchItem(BaseModel):
    legacy_drug_id: str
    name: str
    dosage_form: str
    route: str
    strength: str | None = None


class SearchDrugOutput(BaseModel):
    items: list[DrugSearchItem]


class DrugInfoField(BaseModel):
    field: str
    content: str
    source: str


class GetDrugInfoOutput(BaseModel):
    legacy_drug_id: str
    results: list[DrugInfoField]
    trace: dict[str, Any]


class PrescriptionToolItem(BaseModel):
    id: str
    status: str
    note: str | None = None
    start_date: str | None = None
    duration_days: int | None = None


class ActivePrescriptionsOutput(BaseModel):
    items: list[PrescriptionToolItem]


class DoseToolItem(BaseModel):
    id: str
    prescription_id: str
    scheduled_at: str
    window_start: str
    window_end: str
    status: str
    expected_items: list[dict[str, Any]]
    # BUILD-18B defect 2: ``id`` above is a synthetic, display-only group id
    # (one card per prescription/local time slot) -- it is never a real
    # ``dose_occurrence`` row and Safety Domain cannot assess it directly.
    # ``occurrence_ids`` are the real, per-drug-item occurrence ids Safety
    # Domain needs; a group covering several drugs at the same time slot can
    # legitimately carry more than one.
    occurrence_ids: list[str] = Field(default_factory=list)


class DoseListOutput(BaseModel):
    items: list[DoseToolItem]


class DoseStatusOutput(DoseToolItem):
    pass


class ReadOnlyDomainTools(Protocol):
    def search_drug(self, *, query: str, limit: int) -> dict[str, Any]: ...

    def get_drug_info(self, *, legacy_drug_id: str, query: str) -> dict[str, Any]: ...

    def get_active_prescriptions(self, *, patient_id: str) -> dict[str, Any]: ...

    def get_today_doses(self, *, patient_id: str) -> dict[str, Any]: ...

    def get_upcoming_doses(self, *, patient_id: str) -> dict[str, Any]: ...

    def get_dose_status(self, *, patient_id: str, dose_id: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class _ToolDefinition:
    input_model: type[_StrictArguments]
    output_model: type[BaseModel]
    authority: ContextAuthority
    provenance: str
    invoke: Callable[[ReadOnlyDomainTools, AuthorizedToolContext, _StrictArguments], dict[str, Any]]


_TOOL_DEFINITIONS: dict[str, _ToolDefinition] = {
    ToolName.SEARCH_DRUG.value: _ToolDefinition(
        SearchDrugArguments,
        SearchDrugOutput,
        ContextAuthority.DRUG_KNOWLEDGE_V2,
        "canonical-drug-v2:catalog",
        lambda domain, _context, arguments: domain.search_drug(**arguments.model_dump()),
    ),
    ToolName.GET_DRUG_INFO.value: _ToolDefinition(
        GetDrugInfoArguments,
        GetDrugInfoOutput,
        ContextAuthority.DRUG_KNOWLEDGE_V2,
        "canonical-drug-v2:knowledge",
        lambda domain, _context, arguments: domain.get_drug_info(**arguments.model_dump()),
    ),
    ToolName.GET_ACTIVE_PRESCRIPTIONS.value: _ToolDefinition(
        EmptyArguments,
        ActivePrescriptionsOutput,
        ContextAuthority.OPERATIONAL_DB,
        "operational-db:prescription:active",
        lambda domain, context, _arguments: domain.get_active_prescriptions(patient_id=context.patient_id),
    ),
    ToolName.GET_TODAY_DOSES.value: _ToolDefinition(
        EmptyArguments,
        DoseListOutput,
        ContextAuthority.OPERATIONAL_DB,
        "operational-db:dose-occurrence:today",
        lambda domain, context, _arguments: domain.get_today_doses(patient_id=context.patient_id),
    ),
    ToolName.GET_UPCOMING_DOSES.value: _ToolDefinition(
        EmptyArguments,
        DoseListOutput,
        ContextAuthority.OPERATIONAL_DB,
        "operational-db:dose-occurrence:upcoming",
        lambda domain, context, _arguments: domain.get_upcoming_doses(patient_id=context.patient_id),
    ),
    ToolName.GET_DOSE_STATUS.value: _ToolDefinition(
        GetDoseStatusArguments,
        DoseStatusOutput,
        ContextAuthority.OPERATIONAL_DB,
        "operational-db:dose-occurrence:status",
        lambda domain, context, arguments: domain.get_dose_status(patient_id=context.patient_id, **arguments.model_dump()),
    ),
}


class ToolGateway:
    """Allow only six typed reads through a server-authorized patient scope."""

    def __init__(
        self,
        domain_tools: ReadOnlyDomainTools,
        *,
        context: AuthorizedToolContext,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._domain_tools = domain_tools
        self._context = context
        self._now = now or (lambda: datetime.now(UTC))

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        definition = _TOOL_DEFINITIONS.get(name)
        if definition is None:
            raise ToolExecutionError("TOOL_NOT_ALLOWED")
        if not isinstance(arguments, dict):
            raise ToolExecutionError("INVALID_TOOL_ARGUMENTS")
        try:
            validated = definition.input_model.model_validate(arguments)
        except ValidationError as exc:
            raise ToolExecutionError("INVALID_TOOL_ARGUMENTS") from exc
        try:
            raw_output = definition.invoke(self._domain_tools, self._context, validated)
            output = definition.output_model.model_validate(raw_output)
        except ToolExecutionError:
            raise
        except Exception as exc:
            # Lookup failures and infrastructure failures intentionally share
            # one non-sensitive contract while the Agent V2 path is disabled.
            raise ToolExecutionError("TOOL_UNAVAILABLE") from exc
        return ToolResult(
            name=name,
            data=output.model_dump(mode="json"),
            provenance=definition.provenance,
            authority=definition.authority,
            freshness=self._as_utc(self._now()),
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
