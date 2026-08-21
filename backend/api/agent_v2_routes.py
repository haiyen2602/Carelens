"""Feature-flagged Agent V2 endpoints (read-only runtime + BUILD-16 orchestration).

Both routes stay behind ``AGENT_RUNTIME_ENABLED`` (default False) and are not
wired into the legacy chat endpoint; enabling the flag or routing legacy chat
to Agent V2 is a separate, not-yet-approved rollout decision (see
``agent_architecture_v2_plan.md`` sections 29-30).
"""

import hashlib
import uuid
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.agents.v2.context import ContextBudget, ContextManager
from backend.agents.v2.handoff import DoctorHandoffGateway
from backend.agents.v2.model_gateway import OpenAIModelGateway
from backend.agents.v2.observability import AgentTelemetry, ModelPricingCatalog
from backend.agents.v2.orchestrator import AgentOrchestrator, OrchestrationRequest
from backend.agents.v2.retrieval import RetrievalConfig, RetrievalGateway
from backend.agents.v2.runtime import AgentRunLimits, ReadOnlyAgentRuntime
from backend.agents.v2.safety import SafetyGateway
from backend.agents.v2.short_term_memory import ShortTermMemoryStore
from backend.agents.v2.tools import AuthorizedToolContext, ToolGateway
from backend.agents.v2.vinmec_web import VinmecWebConfig, VinmecWebSearchGateway
from backend.api.security import CurrentUser, get_current_user
from backend.config import get_settings
from backend.db.base import get_db
from backend.models.schemas import (
    AgentV2CitationOut,
    AgentV2OrchestrateRequest,
    AgentV2OrchestrateResponse,
    AgentV2ReadOnlyRequest,
    AgentV2ReadOnlyResponse,
)
from backend.services.agent_authorization import require_agent_patient_access
from backend.services.agent_doctor_handoff import AuthorizedDoctorHandoffAdapter
from backend.services.agent_idempotency import IdempotencyBusyError, IdempotencyClaim, claim_or_replay, record_completion
from backend.services.agent_read_only_tools import AgentReadOnlyDomainTools
from backend.services.agent_retrieval import AgentRetrievalDomainService
from backend.services.agent_safety import SafetyDomainAdapter
from backend.services.vinmec_web_search import VinmecWebSearchService

agent_v2_router = APIRouter()

_AGENT_V2_DISABLED_DETAIL = "Agent V2 chua duoc kich hoat"


def _canary_allowlist(settings: object) -> frozenset[str] | None:
    """``None`` means no explicit allowlist is configured; a frozenset means
    those account ids are always admitted regardless of the rollout
    percentage below. Empty/unset stays ``None`` so staging/local UAT is
    unaffected -- see ``backend.config.Settings.agent_canary_allowlist``."""
    raw = str(getattr(settings, "agent_canary_allowlist", "") or "").strip()
    if not raw:
        return None
    return frozenset(item.strip() for item in raw.split(",") if item.strip())


def _in_rollout_percentage(settings: object, actor_id: str) -> bool:
    """BUILD-23: deterministic bucket assignment for gradual rollout.

    ``sha256(actor_id) mod 100 < percentage`` -- stable per actor (the same
    account always lands in the same bucket) and monotonic as the
    percentage grows: an account admitted at 5% is still admitted at every
    later, larger stage (20/50/100), never flip-flopping in or out as the
    threshold moves. This is deliberately NOT random-per-request; a fresh
    coin flip on every call would make canary monitoring meaningless (the
    same real user's experience would vary call to call) and would make
    "roll a bad cohort back" impossible.
    """
    percentage = int(getattr(settings, "agent_rollout_percentage", 0) or 0)
    if percentage <= 0:
        return False
    if percentage >= 100:
        return True
    bucket = int(hashlib.sha256(actor_id.encode("utf-8")).hexdigest(), 16) % 100
    return bucket < percentage


def _require_agent_v2_enabled(settings: object, actor: CurrentUser) -> None:
    """The flag, the canary allowlist, and (BUILD-23) the rollout percentage
    together gate every Agent V2 endpoint. Any failure raises the exact same
    404 an entirely-disabled flag would -- indistinguishable from the
    outside, so a non-admitted caller learns nothing about Agent V2 existing
    (not "403 you're not allowed", which would itself be a signal).

    Unchanged from every build through BUILD-22C when neither an allowlist
    nor a rollout percentage is configured (both default empty/0): the flag
    alone gates access, exactly as staging/local UAT has always relied on.
    Once either is configured (production, mid-cutover), access requires
    being on the allowlist OR inside the rollout percentage's bucket.
    """
    if not getattr(settings, "agent_runtime_enabled", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_AGENT_V2_DISABLED_DETAIL)
    allowlist = _canary_allowlist(settings)
    percentage = int(getattr(settings, "agent_rollout_percentage", 0) or 0)
    restriction_active = allowlist is not None or percentage > 0
    if not restriction_active:
        return
    on_allowlist = allowlist is not None and actor.id in allowlist
    if on_allowlist:
        return
    if _in_rollout_percentage(settings, actor.id):
        return
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_AGENT_V2_DISABLED_DETAIL)

# BUILD-5/BUILD-13 short-term memory and telemetry are deliberately
# process-local (see backend/agents/v2/short_term_memory.py); one instance is
# shared across requests behind the still-disabled flag so a conversation's
# session recall and the process metrics snapshot both work as designed.
_singleton_lock = Lock()
_short_term_memory: ShortTermMemoryStore | None = None
_telemetry: AgentTelemetry | None = None


def _shared_short_term_memory(context_manager: ContextManager) -> ShortTermMemoryStore:
    global _short_term_memory
    with _singleton_lock:
        if _short_term_memory is None:
            _short_term_memory = ShortTermMemoryStore(context_manager)
        return _short_term_memory


def _shared_telemetry(settings: object) -> AgentTelemetry:
    """BUILD-21: ``AgentTelemetry()`` with no arguments defaults to an EMPTY
    ``ModelPricingCatalog`` -- ``AGENT_MODEL_PRICING_JSON`` was never actually
    wired into the live route at all, so ``estimated_cost_usd`` was silently
    ``None`` regardless of whether real pricing was configured (invisible
    until BUILD-21 actually populated real pricing and verified the live
    output, rather than only unit-testing ``ModelPricingCatalog`` in
    isolation as BUILD-13 did). The pricing catalog is built once, at the
    same singleton-construction point as everything else this function
    shares across requests -- a later config change still needs a restart to
    take effect, matching every other Settings-derived value already cached
    behind ``get_settings()``'s own ``lru_cache``."""
    global _telemetry
    with _singleton_lock:
        if _telemetry is None:
            _telemetry = AgentTelemetry(pricing=ModelPricingCatalog.from_settings(settings))
        return _telemetry


@agent_v2_router.post("/agent/v2/read-only", response_model=AgentV2ReadOnlyResponse)
def run_read_only_agent(
    request: AgentV2ReadOnlyRequest,
    db: Session = Depends(get_db),
    actor: CurrentUser = Depends(get_current_user),
) -> AgentV2ReadOnlyResponse:
    settings = get_settings()
    _require_agent_v2_enabled(settings, actor)
    patient_id = require_agent_patient_access(db, actor, request.patient_id)
    runtime = ReadOnlyAgentRuntime(
        OpenAIModelGateway.from_settings(settings),
        limits=AgentRunLimits.from_settings(settings),
        model_name=settings.agent_main_model,
    )
    tools = ToolGateway(
        AgentReadOnlyDomainTools(db),
        context=AuthorizedToolContext(actor_id=actor.id, actor_role=actor.role, patient_id=patient_id),
    )
    result = runtime.run(message=request.message, actor_role=actor.role, tools=tools)
    return AgentV2ReadOnlyResponse(status=result.status, reply=result.response, tools=[item.name for item in result.tool_results])


@agent_v2_router.post("/agent/v2/orchestrate", response_model=AgentV2OrchestrateResponse)
def run_agent_orchestration(
    request: AgentV2OrchestrateRequest,
    db: Session = Depends(get_db),
    actor: CurrentUser = Depends(get_current_user),
) -> AgentV2OrchestrateResponse:
    """BUILD-16 end-to-end flow: Router -> Context/Memory -> Tools/RAG/Web ->
    Safety -> Doctor Handoff -> Main Model -> Response -> Checkpoint/Observability.

    Still gated OFF by ``AGENT_RUNTIME_ENABLED``; not called by legacy chat.
    """
    settings = get_settings()
    _require_agent_v2_enabled(settings, actor)
    patient_id = require_agent_patient_access(db, actor, request.patient_id)

    # BUILD-22: an optional client idempotency key opts into HTTP-level
    # replay -- see backend.services.agent_idempotency. A key bound to a
    # different actor/patient can never match this claim (defense in depth
    # on top of the authorization check just above, which always re-runs).
    idempotency_claim: IdempotencyClaim | None = None
    if request.idempotency_key:
        try:
            idempotency_claim = claim_or_replay(
                db,
                actor_id=actor.id,
                patient_id=patient_id,
                idempotency_key=request.idempotency_key,
                ttl_seconds=settings.agent_idempotency_ttl_seconds,
            )
        except IdempotencyBusyError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Yeu cau trung idempotency key dang duoc xu ly, vui long thu lai sau.",
            ) from exc
        if idempotency_claim.is_replay:
            db.rollback()  # this call staged nothing of its own -- read-only replay
            return AgentV2OrchestrateResponse.model_validate(idempotency_claim.cached_response)

    context_manager = ContextManager(ContextBudget.from_settings(settings))
    model_gateway = OpenAIModelGateway.from_settings(settings)
    telemetry = _shared_telemetry(settings)
    orchestrator = AgentOrchestrator(
        runtime=ReadOnlyAgentRuntime(
            model_gateway,
            limits=AgentRunLimits.from_settings(settings),
            telemetry=telemetry,
            model_name=settings.agent_main_model,
        ),
        context_manager=context_manager,
        safety_gateway=SafetyGateway.from_settings(SafetyDomainAdapter(db), settings),
        handoff_gateway=DoctorHandoffGateway(AuthorizedDoctorHandoffAdapter(db, actor)),
        retrieval_gateway=RetrievalGateway(
            model_gateway, AgentRetrievalDomainService(db), config=RetrievalConfig.from_settings(settings)
        ),
        vinmec_gateway=VinmecWebSearchGateway(VinmecWebSearchService(), config=VinmecWebConfig.from_settings(settings)),
        short_term_memory=_shared_short_term_memory(context_manager),
        telemetry=telemetry,
    )
    tools = ToolGateway(
        AgentReadOnlyDomainTools(db),
        context=AuthorizedToolContext(actor_id=actor.id, actor_role=actor.role, patient_id=patient_id),
    )
    # BUILD-18B defect 3: the checkpoint/safety/handoff adapters below only
    # ever ``flush()``/savepoint (see backend/services/agent_checkpoint.py
    # and backend/services/doctor_handoff.py docstrings: "the caller owns the
    # surrounding transaction") -- this request/application boundary is that
    # caller and owns the one outer commit. A run that raises rolls back
    # everything it staged; a run that returns normally (whatever its
    # terminal status) is committed exactly once, and only *then* is the
    # HTTP response built, so a commit failure can never be reported to the
    # caller as a fabricated success (e.g. a HANDOFF_CREATED that was never
    # actually durable).
    try:
        result = orchestrator.run(
            OrchestrationRequest(
                message=request.message,
                actor_id=actor.id,
                actor_role=actor.role,
                patient_id=patient_id,
                conversation_id=request.conversation_id or f"one-shot:{actor.id}",
                session_id=request.session_id or str(uuid.uuid4()),
                dose_id=request.dose_id,
                request_id=request.idempotency_key,
                agent_run_id=idempotency_claim.agent_run_id if idempotency_claim is not None else None,
            ),
            tools=tools,
            checkpoint_db=db,
        )
    except Exception:
        db.rollback()
        raise

    response = AgentV2OrchestrateResponse(
        status=result.status,
        reply=result.response,
        intent=result.intent,
        tools=[item.name for item in result.tool_results],
        citations=[AgentV2CitationOut(title=c.title, source=c.source, url=c.url) for c in result.citations],
        safety_disposition=result.safety_decision.outcome.value if result.safety_decision else None,
        handoff_id=result.handoff_result.request_id if result.handoff_result else None,
        trace_id=result.trace_id,
        agent_run_id=result.agent_run_id,
    )

    # BUILD-22: record the replayable result in the SAME transaction as the
    # run itself, before the one outer commit below -- a request that raises
    # never reaches here (rolled back above), and a request that commits
    # therefore never leaves a claim row stuck IN_PROGRESS (see
    # backend.services.agent_idempotency module docstring).
    if idempotency_claim is not None:
        try:
            record_completion(
                db,
                actor_id=actor.id,
                patient_id=patient_id,
                idempotency_key=request.idempotency_key,
                response=response.model_dump(mode="json"),
            )
        except Exception:
            db.rollback()
            raise

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Khong the luu ket qua Agent V2, vui long thu lai.",
        ) from exc

    return response
