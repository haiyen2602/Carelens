"""Feature-flagged Agent V2 endpoints (read-only runtime + BUILD-16 orchestration).

Both routes stay behind ``AGENT_RUNTIME_ENABLED`` (default False) and are not
wired into the legacy chat endpoint; enabling the flag or routing legacy chat
to Agent V2 is a separate, not-yet-approved rollout decision (see
``agent_architecture_v2_plan.md`` sections 29-30).
"""

import hashlib
import json
import logging
import time
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
from backend.services.evaluators import LLMJudgeEvaluator
from backend.services.telemetry import get_telemetry_service
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


# BUILD-25 (production monitoring audit): Agent V2 never fed the existing
# Langfuse/admin-RAG-monitoring pipeline (backend/services/telemetry.py +
# backend/api/rag_monitoring_routes.py) at all -- only the legacy chat route
# (backend/api/chat_routes.py) ever called `get_telemetry_service()`, and only
# legacy chat ever wrote `AuditLog` (the admin dashboard's DB fallback source).
# Since Agent V2 is now 100% of production traffic and legacy chat is ~0%,
# every KPI on the admin dashboard (faithfulness, relevance, latency
# percentiles, error rate, model/prompt breakdowns, Trace Explorer) was
# reading an empty in-memory buffer (reset on every deploy, per-process) or a
# handful of stale historical rows -- not Agent V2's real traffic at all. This
# is the root cause behind the reported "P95 ~0.7ms" reading: with the trace
# buffer empty, `/admin/rag/system` fell back to whatever sparse legacy
# `AuditLog` rows happen to exist, not a measurement of a live LLM call.
#
# This function wires a real Agent V2 request into that SAME existing
# pipeline (no new dashboard, no new backend, per the audit's own
# instruction) -- purely additive around the HTTP boundary, after
# `orchestrator.run()` has already returned, so it can never change Agent
# V2's own routing/safety/model behavior. Every step is best-effort: a
# telemetry failure is logged and swallowed, never surfaced to the caller
# and never allowed to affect the actual response already computed.
#
# Faithfulness/relevance reuse the exact same generic, deterministic
# heuristic evaluators legacy chat already uses
# (`backend.services.evaluators.LLMJudgeEvaluator` -- word-overlap ratios,
# not an LLM-judge call, so this adds no extra model cost or latency)
# -- "retrieved_contexts" is built from each tool call's own structured
# result data (already real information the model was given, not fabricated
# text). `mask_sensitive_data`/`hash_identifier` (telemetry.py's own existing
# redaction) still apply to everything recorded, same as for legacy chat.
def _record_agent_v2_telemetry(
    *,
    request: AgentV2OrchestrateRequest,
    actor: CurrentUser,
    result,
    latency_ms: float,
    error: Exception | None = None,
) -> None:
    try:
        telemetry = get_telemetry_service()
        trace = telemetry.create_trace(
            trace_id=getattr(result, "trace_id", None) or f"agent_v2_{int(time.time() * 1000)}_{actor.id[:6]}",
            name="agent_v2.orchestrate",
            session_id=request.conversation_id,
            user_id=actor.id,
            input_data={"message": request.message},
            metadata={
                "agent_run_id": getattr(result, "agent_run_id", None),
                "intent": getattr(result, "intent", None).value if getattr(result, "intent", None) else None,
                "actor_role": actor.role,
            },
            tags=["agent_v2"],
        )

        tool_results = list(getattr(result, "tool_results", []) or [])
        retrieved_contexts: list[str] = []
        for tool_result in tool_results:
            obs = telemetry.start_observation(
                trace, name=f"tool.{tool_result.name}", obs_type="retriever", input_data={"tool": tool_result.name}
            )
            telemetry.end_observation(obs, output_data=tool_result.data)
            try:
                retrieved_contexts.append(json.dumps(tool_result.data, ensure_ascii=False, default=str))
            except Exception:  # noqa: BLE001 -- best-effort context text, never block telemetry
                pass

        safety_decision = getattr(result, "safety_decision", None)
        if safety_decision is not None:
            safety_obs = telemetry.start_observation(trace, name="safety.decision", obs_type="span")
            telemetry.end_observation(
                safety_obs,
                output_data={"outcome": safety_decision.outcome.value},
                level="WARNING" if safety_decision.outcome.value != "SAFE" else "DEFAULT",
            )

        handoff_result = getattr(result, "handoff_result", None)
        if handoff_result is not None:
            handoff_obs = telemetry.start_observation(trace, name="handoff.created", obs_type="span")
            telemetry.end_observation(handoff_obs, output_data={"request_id": handoff_result.request_id})

        response_text = getattr(result, "response", "") or ""
        gen_obs = telemetry.start_observation(trace, name="generation.answer", obs_type="generation")
        telemetry.end_observation(gen_obs, output_data={"response": response_text})

        if response_text:
            relevance = LLMJudgeEvaluator.evaluate_answer_relevance(request.message, response_text)
            telemetry.record_score(trace, relevance.score_name, relevance.value)
            faithfulness = LLMJudgeEvaluator.evaluate_faithfulness(retrieved_contexts, response_text)
            telemetry.record_score(trace, faithfulness.score_name, faithfulness.value)

        # `create_trace()` stamped `start_time` when this function was called
        # (i.e. after `orchestrator.run()` already returned) -- overwrite it
        # with the real wall-clock start so `duration_ms` reflects the actual
        # request latency, not the near-zero time spent inside this function.
        trace.start_time = time.time() - (latency_ms / 1000.0)
        status_value = "error" if error is not None else "success"
        telemetry.finalize_trace(trace, output_data={"response": response_text}, status=status_value)
    except Exception as telemetry_err:  # noqa: BLE001 -- observability must never break the real response
        logging.getLogger(__name__).warning("Agent V2 telemetry recording failed: %s", telemetry_err)


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
    _started = time.monotonic()
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

    # BUILD-25: best-effort, after the real commit above -- never allowed to
    # affect the response already built and durably saved.
    _record_agent_v2_telemetry(
        request=request,
        actor=actor,
        result=result,
        latency_ms=(time.monotonic() - _started) * 1000.0,
    )

    return response
