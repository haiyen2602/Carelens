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
from backend.agents.v2.conversation_state import (
    ActiveEntity,
    SuggestedAction,
    is_allowed_action,
    resolve_state_input,
    transition_state,
)
from backend.agents.v2.evaluation_v2 import MetricStatus, dispatch_evaluation
from backend.agents.v2.handoff import DoctorHandoffGateway
from backend.agents.v2.model_gateway import OpenAIModelGateway
from backend.agents.v2.observability import AgentTelemetry, ModelPricingCatalog
from backend.agents.v2.orchestrator import (
    AgentOrchestrator,
    OrchestrationIntent,
    OrchestrationRequest,
    normalize_semantic_medical_query,
)
from backend.agents.v2.retrieval import RetrievalConfig, RetrievalGateway
from backend.agents.v2.runtime import AgentRunLimits, ReadOnlyAgentRuntime
from backend.agents.v2.safety import SafetyGateway
from backend.agents.v2.short_term_memory import ShortTermMemoryStore
from backend.agents.v2.suggested_actions import build_suggested_actions
from backend.agents.v2.tools import AuthorizedToolContext, ToolGateway
from backend.agents.v2.vinmec_web import VinmecWebConfig, VinmecWebSearchGateway
from backend.api.security import CurrentUser, get_current_user
from backend.config import get_settings
from backend.db.base import get_db
from backend.db.models import AgentActivitySnapshot
from backend.models.schemas import (
    AgentActivityItemOut,
    AgentActivityOut,
    AgentV2CitationOut,
    AgentV2OrchestrateRequest,
    AgentV2OrchestrateResponse,
    AgentV2ReadOnlyRequest,
    AgentV2ReadOnlyResponse,
    SuggestedActionOut,
)
from backend.services.agent_activity import build_activity_timeline
from backend.services.agent_authorization import require_agent_patient_access
from backend.services.agent_conversation_state import AgentConversationStateStore
from backend.services.agent_doctor_handoff import AuthorizedDoctorHandoffAdapter
from backend.services.agent_idempotency import (
    IdempotencyBusyError,
    IdempotencyClaim,
    claim_or_replay,
    record_completion,
)
from backend.services.agent_read_only_tools import AgentReadOnlyDomainTools
from backend.services.agent_retrieval import AgentRetrievalDomainService
from backend.services.agent_safety import SafetyDomainAdapter
from backend.services.evaluators import LLMJudgeEvaluator
from backend.services.telemetry import get_telemetry_service
from backend.services.vinmec_web_search import VinmecWebSearchService

agent_v2_router = APIRouter()

_AGENT_V2_DISABLED_DETAIL = "Agent V2 chua duoc kich hoat"


def _validated_selected_action(state, candidate) -> SuggestedAction | None:
    """Match every client field against the latest state-issued action."""
    if candidate is None:
        return None
    for action in state.offered_actions:
        if (
            action.action_id == candidate.action_id
            and action.type == candidate.type
            and action.value == candidate.value
            and action.entity_id == candidate.entity_id
            and action.topic == candidate.topic
            and is_allowed_action(action)
        ):
            return action
    return None


def _resolved_drug_entity(tool_results) -> ActiveEntity | None:
    """Promote only a server-returned canonical drug result into state."""
    info_ids = [item.data.get("legacy_drug_id") for item in tool_results if item.name == "get_drug_info"]
    if len(info_ids) != 1 or not info_ids[0]:
        return None
    drug_id = str(info_ids[0])
    for item in tool_results:
        if item.name != "search_drug":
            continue
        for candidate in item.data.get("items", []):
            if candidate.get("legacy_drug_id") == drug_id and candidate.get("name"):
                return ActiveEntity("drug", drug_id, str(candidate["name"]))
    return ActiveEntity("drug", drug_id, drug_id)


def _authoritative_topic_for_turn(
    conversation_state,
    *,
    selected_action: SuggestedAction | None,
    semantic_topic: str | None,
    is_general_medical_turn: bool,
    resolved_entity: ActiveEntity | None,
) -> str | None:
    """Return only a topic that may replace durable conversation state.

    A selected follow-up has already been validated against the latest
    server-issued action. Its query is intentionally rewritten for retrieval,
    so semantic extraction of that ephemeral text must not replace the
    existing canonical topic. A legacy action with no active topic may seed
    it from the validated server-issued action only.
    """
    if selected_action is not None and selected_action.type == "topic_followup":
        return selected_action.topic if conversation_state.active_topic is None else None
    if is_general_medical_turn and resolved_entity is None:
        return semantic_topic
    return None


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
    conversation_state_before=None,
    conversation_state_after=None,
    followup_resolved: bool = False,
    topic_changed: bool = False,
) -> None:
    try:
        settings = get_settings()
        telemetry = get_telemetry_service()
        trace = telemetry.create_trace(
            trace_id=getattr(result, "trace_id", None) or f"agent_v2_{int(time.time() * 1000)}_{actor.id[:6]}",
            name="agent_v2.orchestrate",
            session_id=request.conversation_id,
            user_id=actor.id,
            input_data={"message": request.message},
            metadata={
                # BUILD-25B: `create_trace()`'s own base metadata defaults
                # "model"/"prompt_version" to the LEGACY chat pipeline's
                # settings (settings.model_name/rag_prompt_version) --
                # overridden here so the dashboard's Model/Prompt Version
                # filters reflect Agent V2's actual model, not legacy chat's.
                # "chatbot_version" is the new, explicit tag both this route
                # and legacy chat's own create_trace() call now set, so the
                # admin dashboard can separate the two systems' traces
                # instead of mixing them under one undifferentiated list.
                "chatbot_version": "agent-v2",
                "model": settings.agent_main_model,
                "router_model": settings.agent_router_model,
                "fallback_model": settings.agent_fallback_model,
                "embedding_model": settings.agent_embedding_model,
                "prompt_version": "agent-v2-orchestrator",
                "agent_run_id": getattr(result, "agent_run_id", None),
                "intent": getattr(result, "intent", None).value if getattr(result, "intent", None) else None,
                "actor_role": actor.role,
                # BUILD-29D.3: server-derived state transition metadata only;
                # no raw client action, query, credentials, or hidden reasoning.
                "conversation_state": {
                    "before_topic": (
                        conversation_state_before.active_topic.display_name
                        if getattr(conversation_state_before, "active_topic", None)
                        else None
                    ),
                    "after_topic": (
                        conversation_state_after.active_topic.display_name
                        if getattr(conversation_state_after, "active_topic", None)
                        else None
                    ),
                    "requested_aspect": getattr(conversation_state_after, "requested_aspect", None),
                    "followup_resolved": followup_resolved,
                    "topic_changed": topic_changed,
                },
            },
            tags=["agent_v2"],
        )
        evaluation = dispatch_evaluation(result=result)
        trace.metadata["evaluation_v2"] = evaluation.as_dict()

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

        if response_text and evaluation.metrics["answer_relevance"].status is MetricStatus.AVAILABLE:
            relevance = LLMJudgeEvaluator.evaluate_answer_relevance(request.message, response_text)
            telemetry.record_score(trace, relevance.score_name, relevance.value)
        if response_text and evaluation.metrics["faithfulness"].status is MetricStatus.AVAILABLE:
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


# BUILD-30: durable, sanitized activity timeline for GET /agent/v2/traces/
# {trace_id}/activity -- deliberately its own table/write path, NOT reusing
# the telemetry buffer above (see AgentActivitySnapshot's own docstring for
# why: that buffer is process-local, capped at 200 entries, and reset on
# every deploy, which BUILD-29's admin ticket explorer already had to accept
# as a known limitation -- this feature is user-facing and needs to survive
# both). Same "best-effort, after the real commit, never allowed to affect
# the actual response" shape as `_record_agent_v2_telemetry`: a bug in
# activity-building must never take down a real chat reply. Uses its own
# `db.commit()` (the main response commit already happened by the time this
# runs) rather than joining an already-closed transaction.
def _persist_activity_snapshot(
    db: Session,
    *,
    patient_id: str,
    actor: CurrentUser,
    result,
    suggested_actions: tuple[SuggestedAction, ...] = (),
    selected_action: SuggestedAction | None = None,
) -> None:
    try:
        activities = build_activity_timeline(
            result, suggested_actions=suggested_actions, selected_action=selected_action
        )
        db.add(
            AgentActivitySnapshot(
                agent_run_id=result.agent_run_id,
                trace_id=result.trace_id,
                patient_id=patient_id,
                actor_id=actor.id,
                intent=result.intent.value,
                status=result.status.value,
                model_calls=result.metrics.model_calls,
                activities_json=activities,
            )
        )
        db.commit()
    except Exception as activity_err:  # noqa: BLE001 -- must never break the real response
        db.rollback()
        logging.getLogger(__name__).warning("Agent V2 activity snapshot recording failed: %s", activity_err)


@agent_v2_router.get("/agent/v2/traces/{trace_id}/activity", response_model=AgentActivityOut)
def get_trace_activity(
    trace_id: str,
    db: Session = Depends(get_db),
    actor: CurrentUser = Depends(get_current_user),
) -> AgentActivityOut:
    """BUILD-30 §3: a patient-safe read of their OWN message's activity
    timeline -- deliberately NOT a reuse of the admin Trace Explorer's
    response shape (BUILD-29's ``AgentFeedbackTraceSummaryOut`` carries far
    more technical detail than a patient should ever see). Only role
    "patient" may call this, and only for a trace that resolves to their own
    ``patient_id`` -- a trace belonging to a different account is a 403, not
    a silently-empty result (the same "fail closed, not fail quiet"
    principle as BUILD-29's ``verify_trace_ownership``).

    A trace this app never persisted an activity snapshot for (not found)
    returns 200 with ``available: false`` rather than 404 -- the frontend
    treats a genuinely-unknown id and an aged-out/pre-BUILD-30 one
    identically ("Chi tiết hoạt động hiện không còn khả dụng."), and no
    caller can distinguish "wrong id" from "real id, snapshot not kept" by
    HTTP status alone, which is the more private default here.
    """
    if actor.role != "patient" or not actor.patient_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Chi benh nhan moi xem duoc hoat dong cua chinh minh"
        )

    snapshot = db.query(AgentActivitySnapshot).filter(AgentActivitySnapshot.trace_id == trace_id).first()
    if snapshot is None:
        return AgentActivityOut(trace_id=trace_id, available=False, activities=[])
    if snapshot.patient_id != actor.patient_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Trace nay khong thuoc ve tai khoan cua ban")

    return AgentActivityOut(
        trace_id=trace_id,
        available=True,
        activities=[AgentActivityItemOut.model_validate(item) for item in snapshot.activities_json],
    )


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
    return AgentV2ReadOnlyResponse(
        status=result.status, reply=result.response, tools=[item.name for item in result.tool_results]
    )


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
    # A missing id is explicitly one-shot.  It must not accidentally reuse
    # state from a prior request by the same account.
    conversation_id = request.conversation_id or f"one-shot:{uuid.uuid4()}"
    state_store = AgentConversationStateStore()
    conversation_state = state_store.load(db, actor_id=actor.id, patient_id=patient_id, conversation_id=conversation_id)
    selected_action = _validated_selected_action(conversation_state, request.selected_action)
    input_resolution = resolve_state_input(conversation_state, message=request.message, selected_action=selected_action)
    # A numeric/typed follow-up is resolved from the same latest,
    # server-issued state as a button click. Downstream transition, activity,
    # and telemetry must use that resolved action rather than only the raw
    # client payload.
    selected_action = input_resolution.selected_action

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
                conversation_id=conversation_id,
                session_id=request.session_id or str(uuid.uuid4()),
                dose_id=request.dose_id,
                request_id=request.idempotency_key,
                agent_run_id=idempotency_claim.agent_run_id if idempotency_claim is not None else None,
                resolved_query=input_resolution.query if input_resolution.used else None,
                active_entity_id=conversation_state.active_entity.id
                if input_resolution.used and conversation_state.active_entity
                else None,
                active_entity_name=conversation_state.active_entity.canonical_name
                if input_resolution.used and conversation_state.active_entity
                else None,
                # The semantic value stays in state; the bound tool receives
                # the server-authored human query/label, never a client id.
                requested_attribute=selected_action.label
                if selected_action and selected_action.type == "drug_followup"
                else None,
            ),
            tools=tools,
            checkpoint_db=db,
        )
    except Exception:
        db.rollback()
        raise

    semantic = normalize_semantic_medical_query(input_resolution.query)
    resolved_entity = _resolved_drug_entity(result.tool_results)
    safety_event = result.intent is OrchestrationIntent.ACUTE_DANGER_ESCALATION or result.safety_decision is not None
    # BUILD-29D.2 fix (found via real local E2E, 2026-08-23): the keyword
    # router (classify_intent) can label a message GENERAL_MEDICAL_INFORMATION
    # purely because it contains a generic phrase like "la gi" even when it
    # also names a specific drug (e.g. "Cong dung cua thuoc X la gi") -- the
    # orchestrator still correctly resolves and answers from that drug's real
    # evidence despite the label. Trusting the label alone here made `topic`
    # a raw, un-vetted echo of the user's message, which both corrupted the
    # persisted state (transition_state nulls out topic AND entity when both
    # are set - see conversation_state.py) and produced nonsense
    # topic_followup suggestions with no entity binding for an answer that
    # was actually about one specific drug. A server-resolved drug entity
    # (real tool evidence, never client input) is authoritative over the
    # router's own intent label -- only treat this as a general-topic turn
    # when no drug was actually resolved.
    #
    # BUILD-29D.3 fix (found via real local E2E, 2026-08-23): the fallback to
    # `semantic.topic` below used to reintroduce the exact corruption this
    # build removes. `semantic.topic` is an ascii-folded, retrieval-only
    # string built for embedding/lexical search (e.g. "cong dung cua thuoc
    # long huyet") -- it was never meant to be a display-safe state value.
    # `semantic.display_topic` is the one field this build added specifically
    # to be state-write-safe (`_display_topic_from_raw`, orchestrator.py: only
    # an explicit disease/topic shape, rejected outright for anything that
    # looks like a drug-attribute question). Falling back to `semantic.topic`
    # whenever `display_topic` is intentionally None (a drug-attribute
    # question with no entity resolved yet -- the common case, since
    # get_drug_info structurally cannot fire on most cold turns; see
    # BUILD-29D2-REPORT.md Sec 15) defeated that guard and corrupted state
    # again with the raw/normalized query text. `None` here (no topic write
    # at all -- the turn's `else` branch in transition_state then correctly
    # carries the existing state forward unchanged) is the only display-safe
    # fallback.
    topic = _authoritative_topic_for_turn(
        conversation_state,
        selected_action=selected_action,
        semantic_topic=semantic.display_topic,
        is_general_medical_turn=result.intent is OrchestrationIntent.GENERAL_MEDICAL_INFORMATION,
        resolved_entity=resolved_entity,
    )
    active_topic = topic or (
        conversation_state.active_topic.canonical_name if conversation_state.active_topic else None
    )
    active_entity = resolved_entity or conversation_state.active_entity
    suggested = build_suggested_actions(
        reply=result.response,
        status=result.status,
        intent=result.intent,
        semantic_query=semantic,
        topic=active_topic,
        entity=active_entity,
        selected_action=selected_action,
        tool_results=result.tool_results,
        safety_event=safety_event,
    )
    next_state = transition_state(
        conversation_state,
        intent=result.intent.value,
        topic=topic,
        entity=resolved_entity,
        selected_action=selected_action,
        offered_actions=suggested.actions,
        safety_event=safety_event,
    )
    state_store.save(
        db,
        agent_run_id=result.agent_run_id,
        actor_id=actor.id,
        patient_id=patient_id,
        state=next_state,
    )

    response = AgentV2OrchestrateResponse(
        status=result.status,
        reply=suggested.reply,
        intent=result.intent,
        tools=[item.name for item in result.tool_results],
        citations=[AgentV2CitationOut(title=c.title, source=c.source, url=c.url) for c in result.citations],
        safety_disposition=result.safety_decision.outcome.value if result.safety_decision else None,
        handoff_id=result.handoff_result.request_id if result.handoff_result else None,
        trace_id=result.trace_id,
        agent_run_id=result.agent_run_id,
        suggested_actions=[SuggestedActionOut(**action.as_dict()) for action in next_state.offered_actions],
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
        conversation_state_before=conversation_state,
        conversation_state_after=next_state,
        followup_resolved=input_resolution.used and selected_action is not None,
        topic_changed=bool(
            conversation_state.active_topic
            and next_state.active_topic
            and conversation_state.active_topic.normalized_key != next_state.active_topic.normalized_key
        )
        or (conversation_state.active_topic is None) != (next_state.active_topic is None),
    )
    # BUILD-30: same best-effort, post-commit shape as the telemetry call
    # above -- see _persist_activity_snapshot's own docstring for why this
    # is a separate, durable table rather than reading the telemetry buffer
    # back.
    _persist_activity_snapshot(
        db,
        patient_id=patient_id,
        actor=actor,
        result=result,
        suggested_actions=suggested.actions,
        selected_action=selected_action,
    )

    return response
