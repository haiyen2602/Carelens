"""BUILD-18B defect 2 regression: real domain objects, not fake opaque ids.

Exercises the full chain with the actual scheduling/runtime adapter and the
actual Safety Domain service (DB-4H) against a real SQLite-backed schema --
not the fully-faked doubles ``tests/test_agent_v2_orchestrator.py`` uses for
everything else -- so the group-id/occurrence-id split this build fixed is
proven against the real classes it was broken in, not against a fake that
could hide the same bug again.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.agents.v2.model_gateway import ModelPlan
from backend.agents.v2.orchestrator import AgentOrchestrator, OrchestrationRequest
from backend.agents.v2.runtime import AgentRunLimits, ReadOnlyAgentRuntime, RunStatus
from backend.agents.v2.safety import SafetyGateway, SafetyOutcome
from backend.agents.v2.tools import AuthorizedToolContext, ToolExecutionError, ToolGateway
from backend.db.models import (
    DoseEventLog,
    DoseOccurrence,
    DrugProduct,
    DrugProductIngredient,
    Ingredient,
    MedicationSafetyPolicy,
    MissedDoseAssessment,
    Prescription,
    PrescriptionItem,
    SafetyEvent,
)
from backend.services.agent_read_only_tools import AgentReadOnlyDomainTools
from backend.services.agent_safety import SafetyDomainAdapter
from backend.services.safety_policy_domain.service import CATEGORY, DRUG_PRODUCT, REVIEWED, assess_dose_safety
from backend.services.scheduling.runtime_adapter import get_v2_dose_group, list_v2_dose_groups
from tests.test_agent_v2_orchestrator import (
    _IdempotentHandoffDomain,
    _SpyModelGateway,
    _context_manager,
    _limits,
    _request,
)

TABLES = (
    Prescription.__table__,
    PrescriptionItem.__table__,
    DoseOccurrence.__table__,
    DrugProduct.__table__,
    Ingredient.__table__,
    DrugProductIngredient.__table__,
    MedicationSafetyPolicy.__table__,
    MissedDoseAssessment.__table__,
    SafetyEvent.__table__,
    DoseEventLog.__table__,
)
NOW = datetime(2026, 8, 19, 8, tzinfo=UTC)


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for table in TABLES:
        table.create(engine)
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _prescription(db: Session, *, patient_id: str = "patient-1", items: int = 1) -> Prescription:
    presc = Prescription(
        id=f"prescription-{patient_id}",
        patient_id=patient_id,
        doctor_id="doctor-1",
        status="active",
        start_date="2026-08-19",
        duration_days=1,
        items=[{"drug_id": f"legacy-{i}", "ten_thuoc": f"Drug {i}", "so_vien_moi_lan": 1} for i in range(items)],
    )
    db.add(presc)
    rows = [
        PrescriptionItem(
            id=f"item-{patient_id}-{i}",
            prescription_id=presc.id,
            patient_id=patient_id,
            legacy_drug_id=f"legacy-{i}",
            drug_display_name=f"Drug {i}",
            migration_item_index=i,
        )
        for i in range(items)
    ]
    db.add_all(rows)
    return presc


def _occurrence(
    db: Session,
    *,
    occurrence_id: str,
    prescription_item_id: str,
    patient_id: str,
    status: str = "MISSED",
    scheduled_local_time: time = time(8),
    drug_product_id: str | None = None,
) -> DoseOccurrence:
    occurrence = DoseOccurrence(
        id=occurrence_id,
        prescription_item_id=prescription_item_id,
        patient_id=patient_id,
        drug_product_id=drug_product_id,
        scheduled_at=NOW - timedelta(hours=1),
        scheduled_local_date=date(2026, 8, 19),
        scheduled_local_time=scheduled_local_time,
        timezone="Asia/Ho_Chi_Minh",
        status=status,
        generation_key=f"generation-{occurrence_id}",
    )
    db.add(occurrence)
    db.commit()
    return occurrence


def _reviewed_low_risk_policy(db: Session, *, product_id: str = "product-1") -> None:
    db.add(DrugProduct(id=product_id, display_name=product_id, category_id="category-1", status="ACTIVE"))
    db.add(
        MedicationSafetyPolicy(
            id=f"policy-{product_id}",
            scope_type=DRUG_PRODUCT,
            scope_id=product_id,
            risk_type="MISSED_DOSE",
            risk_level="LOW",
            action_policy="LOG_ONLY",
            source_type="CLINICAL_REVIEW",
            review_status=REVIEWED,
            policy_version=1,
            valid_from=NOW - timedelta(days=1),
        )
    )
    db.commit()


def _require_medical_review_policy(db: Session, *, product_id: str = "product-1") -> None:
    db.add(DrugProduct(id=product_id, display_name=product_id, category_id="category-1", status="ACTIVE"))
    db.add(
        MedicationSafetyPolicy(
            id=f"policy-{product_id}",
            scope_type=DRUG_PRODUCT,
            scope_id=product_id,
            risk_type="MISSED_DOSE",
            risk_level="HIGH",
            action_policy="REQUIRE_MEDICAL_REVIEW",
            source_type="CLINICAL_REVIEW",
            review_status=REVIEWED,
            policy_version=1,
            valid_from=NOW - timedelta(days=1),
        )
    )
    db.commit()


def _tools(db: Session, *, patient_id: str = "patient-1") -> ToolGateway:
    return ToolGateway(
        AgentReadOnlyDomainTools(db, now=lambda: NOW),
        context=AuthorizedToolContext(actor_id="actor-1", actor_role="patient", patient_id=patient_id),
    )


def _orchestrator(db: Session, *, model_gateway=None, handoff_domain=None) -> tuple[AgentOrchestrator, object]:
    from backend.agents.v2.handoff import DoctorHandoffGateway

    gateway = model_gateway or _SpyModelGateway(ModelPlan(response="ignored"))
    return (
        AgentOrchestrator(
            runtime=ReadOnlyAgentRuntime(gateway, limits=_limits()),
            context_manager=_context_manager(),
            safety_gateway=SafetyGateway(SafetyDomainAdapter(db), timeout_seconds=5.0),
            handoff_gateway=DoctorHandoffGateway(handoff_domain or _IdempotentHandoffDomain()),
        ),
        gateway,
    )


# ---------------------------------------------------------------------------
# 1. group id != occurrence id (structural)
# ---------------------------------------------------------------------------


def test_group_id_is_never_equal_to_its_real_occurrence_id(db):
    _prescription(db, items=1)
    _occurrence(db, occurrence_id="real-occurrence-1", prescription_item_id="item-patient-1-0", patient_id="patient-1")

    group = list_v2_dose_groups(db, patient_id="patient-1")[0]

    assert group.id != "real-occurrence-1"
    assert group.occurrence_ids == ("real-occurrence-1",)
    # The Agent V2 tool boundary must expose both, kept distinct.
    tool_result = _tools(db).execute("get_dose_status", {"dose_id": group.id})
    assert tool_result.data["id"] == group.id
    assert tool_result.data["occurrence_ids"] == ["real-occurrence-1"]
    assert tool_result.data["id"] not in tool_result.data["occurrence_ids"]


# ---------------------------------------------------------------------------
# 2/6. one real occurrence -> SAFE path end-to-end
# ---------------------------------------------------------------------------


def test_one_real_occurrence_resolves_and_reaches_safe(db):
    _prescription(db, items=1)
    _occurrence(
        db, occurrence_id="real-occurrence-1", prescription_item_id="item-patient-1-0",
        patient_id="patient-1", drug_product_id="product-1",
    )
    _reviewed_low_risk_policy(db)
    group = list_v2_dose_groups(db, patient_id="patient-1")[0]

    orchestrator, gateway = _orchestrator(db, model_gateway=_SpyModelGateway(ModelPlan(response="An toan.")))
    result = orchestrator.run(
        _request("Toi quen uong thuoc sang nay", dose_id=group.id), tools=_tools(db)
    )

    assert result.safety_decision is not None
    assert result.safety_decision.outcome is SafetyOutcome.SAFE
    assert result.safety_decision.reason_code == "POLICY_DRUG_PRODUCT_MATCH"
    assert result.status is RunStatus.COMPLETED
    assert len(gateway.calls) == 1  # SAFE reaches the Main Model


# ---------------------------------------------------------------------------
# 3. multiple occurrence_ids -> ambiguous, fail-closed to Doctor Handoff
# ---------------------------------------------------------------------------


def test_multiple_occurrence_ids_in_one_group_fail_closed_to_handoff_not_guessed(db):
    _prescription(db, items=2)
    # Two drugs at the identical scheduled local time -> one group, two occurrences.
    _occurrence(db, occurrence_id="occurrence-a", prescription_item_id="item-patient-1-0", patient_id="patient-1")
    _occurrence(db, occurrence_id="occurrence-b", prescription_item_id="item-patient-1-1", patient_id="patient-1")
    group = list_v2_dose_groups(db, patient_id="patient-1")[0]
    assert len(group.occurrence_ids) == 2  # sanity: this really is the ambiguous case

    handoff_domain = _IdempotentHandoffDomain()
    orchestrator, gateway = _orchestrator(
        db, model_gateway=_SpyModelGateway(ModelPlan(response="should never be produced")), handoff_domain=handoff_domain
    )
    result = orchestrator.run(_request("Toi quen uong thuoc sang nay", dose_id=group.id), tools=_tools(db))

    assert result.safety_decision.outcome is SafetyOutcome.HANDOFF_REQUIRED
    assert result.safety_decision.reason_code == "DOSE_OCCURRENCE_AMBIGUOUS"
    assert result.status is RunStatus.HANDOFF_CREATED
    assert len(handoff_domain.commands) == 1
    assert gateway.calls == []  # never guessed which drug's dose was "missed"


# ---------------------------------------------------------------------------
# 4. invalid occurrence / dose id -> fail-closed
# ---------------------------------------------------------------------------


def test_invalid_dose_id_fails_closed_to_handoff(db):
    _prescription(db, items=1)
    _occurrence(db, occurrence_id="real-occurrence-1", prescription_item_id="item-patient-1-0", patient_id="patient-1")

    orchestrator, gateway = _orchestrator(db)
    result = orchestrator.run(
        _request("Toi quen uong thuoc sang nay", dose_id="dose-group-that-does-not-exist"), tools=_tools(db)
    )

    assert result.safety_decision.outcome is SafetyOutcome.HANDOFF_REQUIRED
    assert result.safety_decision.reason_code == "DOSE_UNRESOLVED"
    assert result.status is RunStatus.HANDOFF_CREATED
    assert gateway.calls == []


# ---------------------------------------------------------------------------
# 5. cross-patient occurrence -> fail-closed, never leaked
# ---------------------------------------------------------------------------


def test_cross_patient_dose_group_is_rejected_before_safety_ever_sees_it(db):
    _prescription(db, patient_id="patient-other", items=1)
    _occurrence(
        db, occurrence_id="other-patient-occurrence", prescription_item_id="item-patient-other-0",
        patient_id="patient-other",
    )
    other_group = list_v2_dose_groups(db, patient_id="patient-other")[0]

    with pytest.raises(ToolExecutionError):
        # The authorized context is patient-1; the group belongs to patient-other.
        _tools(db, patient_id="patient-1").execute("get_dose_status", {"dose_id": other_group.id})

    orchestrator, gateway = _orchestrator(db)
    result = orchestrator.run(
        _request("Toi quen uong thuoc sang nay", dose_id=other_group.id, patient_id="patient-1"),
        tools=_tools(db, patient_id="patient-1"),
    )

    assert result.safety_decision.outcome is SafetyOutcome.HANDOFF_REQUIRED
    assert result.safety_decision.reason_code == "DOSE_UNRESOLVED"
    assert gateway.calls == []


# ---------------------------------------------------------------------------
# 7. Safety exception -> SAFETY_BLOCKED, fail-closed, Main Model never called
# ---------------------------------------------------------------------------


def test_real_safety_domain_exception_blocks_before_the_main_model(db):
    _prescription(db, items=1)
    # No matching DrugProduct/policy row and an occurrence status that is
    # neither MISSED nor DELAYED both make ``assess_dose_safety`` raise for
    # real (DoseSafetyStateError) -- exercised here via a PENDING occurrence.
    _occurrence(
        db, occurrence_id="real-occurrence-1", prescription_item_id="item-patient-1-0",
        patient_id="patient-1", status="PENDING",
    )
    group = list_v2_dose_groups(db, patient_id="patient-1")[0]

    orchestrator, gateway = _orchestrator(db, model_gateway=_SpyModelGateway(ModelPlan(response="should never be produced")))
    result = orchestrator.run(_request("Toi quen uong thuoc sang nay", dose_id=group.id), tools=_tools(db))

    assert result.status is RunStatus.SAFETY_BLOCKED
    assert result.safety_decision.outcome is SafetyOutcome.SAFETY_BLOCKED
    assert gateway.calls == []


# ---------------------------------------------------------------------------
# 8. HANDOFF_REQUIRED regression (real REQUIRE_MEDICAL_REVIEW policy)
# ---------------------------------------------------------------------------


def test_real_require_medical_review_policy_creates_a_handoff(db):
    _prescription(db, items=1)
    _occurrence(
        db, occurrence_id="real-occurrence-1", prescription_item_id="item-patient-1-0",
        patient_id="patient-1", drug_product_id="product-1",
    )
    _require_medical_review_policy(db)
    group = list_v2_dose_groups(db, patient_id="patient-1")[0]

    handoff_domain = _IdempotentHandoffDomain()
    orchestrator, gateway = _orchestrator(
        db, model_gateway=_SpyModelGateway(ModelPlan(response="should never be produced")), handoff_domain=handoff_domain
    )
    result = orchestrator.run(_request("Toi quen uong thuoc sang nay", dose_id=group.id), tools=_tools(db))

    assert result.safety_decision.outcome is SafetyOutcome.HANDOFF_REQUIRED
    assert result.safety_decision.reason_code == "POLICY_DRUG_PRODUCT_MATCH"
    assert result.status is RunStatus.HANDOFF_CREATED
    assert len(handoff_domain.commands) == 1
    assert gateway.calls == []


# ---------------------------------------------------------------------------
# get_v2_dose_group (singular, used by get_dose_status) exposes the same data
# ---------------------------------------------------------------------------


def test_get_v2_dose_group_singular_lookup_also_carries_real_occurrence_ids(db):
    _prescription(db, items=1)
    _occurrence(db, occurrence_id="real-occurrence-1", prescription_item_id="item-patient-1-0", patient_id="patient-1")
    group_id = list_v2_dose_groups(db, patient_id="patient-1")[0].id

    group = get_v2_dose_group(db, dose_group_id=group_id)

    assert group.occurrence_ids == ("real-occurrence-1",)
