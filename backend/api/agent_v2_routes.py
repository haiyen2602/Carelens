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
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.agents.tools.chat_history_tool import save_chat_message
from backend.agents.v2.answerability import handoff_type_for
from backend.agents.v2.context import ContextBudget, ContextManager
from backend.agents.v2.conversation_state import (
    ActiveEntity,
    SuggestedAction,
    is_allowed_action,
    is_drug_candidate_action,
    resolve_state_input,
    transition_state,
)
from backend.agents.v2.evaluation_v2 import EvaluationResult, MetricStatus, dispatch_evaluation
from backend.agents.v2.follow_up import FollowUpCategory
from backend.agents.v2.handoff import DoctorHandoffGateway
from backend.agents.v2.model_gateway import OpenAIModelGateway
from backend.agents.v2.observability import (
    AgentTelemetry,
    BufferingSink,
    ModelPricingCatalog,
    StructuredLogSink,
    TraceComponent,
    TraceContext,
)
from backend.agents.v2.orchestrator import (
    AgentOrchestrator,
    OrchestrationIntent,
    OrchestrationRequest,
    classify_intent,
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
from backend.db.models import AgentActivitySnapshot, AgentRun, AgentRunEvaluation, AgentRunSpan
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
from backend.services.agent_doctor_takeover import get_active_takeover
from backend.services.agent_idempotency import (
    IdempotencyBusyError,
    IdempotencyClaim,
    claim_or_replay,
    record_completion,
)
from backend.services.agent_judge_worker import enqueue_run_judge
from backend.services.agent_read_only_tools import AgentReadOnlyDomainTools
from backend.services.agent_retrieval import AgentRetrievalDomainService
from backend.services.agent_safety import SafetyDomainAdapter
from backend.services.agent_safety_monitoring import persist_safety_event
from backend.services.doctor_handoff import MessageSenderRole, record_doctor_review_message
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


def _resolved_drug_entity(tool_results, *, known_entity: ActiveEntity | None = None) -> ActiveEntity | None:
    """Promote only a server-returned canonical drug result into state.

    ``known_entity`` (BUILD-43): the already-known canonical entity for
    this SAME id, if any -- the orchestrator's TRUE_FOLLOWUP bound-lookup
    shortcut (``effective_entity_id``, orchestrator.py) calls
    ``get_drug_info`` directly, bypassing ``search_drug`` entirely (the
    whole point of the shortcut is to avoid re-searching an already-known
    drug), so the ``search_drug``-sourced display name below is never
    present for that path. Without this, the id-as-name fallback would
    silently DEGRADE an already-real display name back to a raw catalog
    slug every time a follow-up re-confirms the same entity -- found via
    real local E2E, not assumed.
    """
    info_ids = [item.data.get("legacy_drug_id") for item in tool_results if item.name == "get_drug_info"]
    if len(info_ids) == 1 and info_ids[0]:
        drug_id = str(info_ids[0])
        for item in tool_results:
            if item.name != "search_drug":
                continue
            for candidate in item.data.get("items", []):
                if candidate.get("legacy_drug_id") == drug_id and candidate.get("name"):
                    return ActiveEntity("drug", drug_id, str(candidate["name"]))
        if known_entity is not None and (known_entity.id == drug_id or known_entity.legacy_drug_id == drug_id):
            return known_entity
        return ActiveEntity("drug", drug_id, drug_id)

    # BUILD-45 Candidate A (cold drug entity binding): no get_drug_info call
    # happened this turn -- the natural cold-turn shape ("Paracetamol dung
    # de lam gi?" -> the model often calls only search_drug), previously an
    # unconditional None here. Promote anyway when search_drug's OWN
    # server-computed uniqueness signal (search_catalog_unique_match,
    # v2_agent.py -- the query's full, untruncated ranked result has
    # exactly one match, never inferred from len(items) alone, which a
    # caller-chosen `limit` could truncate) says this was genuinely
    # unambiguous, not a top-1-of-many fuzzy guess. Requires exactly one
    # search_drug call this turn -- multiple distinct searches in one turn
    # is rare and itself a form of ambiguity, so it falls through to None
    # rather than guessing which search "counts". Zero extra model calls:
    # this reads evidence the run already produced.
    search_calls = [item for item in tool_results if item.name == "search_drug"]
    if len(search_calls) == 1:
        unique_id = search_calls[0].data.get("unique_match_legacy_drug_id")
        if unique_id:
            for candidate in search_calls[0].data.get("items", []):
                if candidate.get("legacy_drug_id") == unique_id and candidate.get("name"):
                    return ActiveEntity("drug", str(unique_id), str(candidate["name"]))
    return None


def _picked_candidate_entity(selected_action: SuggestedAction | None) -> ActiveEntity | None:
    """BUILD-48: the product the user explicitly picked from an offered list.

    Authoritative by construction, and the only promotion path that does not
    depend on the model happening to call a particular tool --
    ``_resolved_drug_entity`` above needs either a ``get_drug_info`` call or
    a unique ``search_drug`` match, and an ambiguous/mistyped search yields
    neither, which is exactly the situation that put a candidate list on
    screen in the first place. ``_validated_selected_action`` has already
    matched every field of this action against this conversation's own
    ``offered_actions``, so both the id and the display name are
    server-issued; neither can come from raw client input.
    """
    if not is_drug_candidate_action(selected_action):
        return None
    return ActiveEntity("drug", selected_action.entity_id, selected_action.label)


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


def _renderer_runtime_kwargs(settings: object) -> dict[str, object]:
    """TASK-V2.5-004: the renderer MECHANISM (``ReadOnlyAgentRuntime``'s
    ``renderer_enabled``/``renderer_model_name``) is fully built and tested,
    but this function deliberately keeps it OFF at every route regardless of
    ``AGENT_V2_5_RENDERER_ENABLED`` until a response-type eligibility gate
    exists (V2.5-DESIGN.md mục 7's allowlist -- explicit remaining scope, see
    tasks/TASK-V2.5-004-natural-renderer.md's own AC checklist).

    Today's tool-calling loop synthesis call site is a single, undifferentiated
    call site far broader than what was reviewed for the renderer (every
    drug-info/prescription/dose-status reply that makes a tool call, not just
    the specific "Ưu tiên natural renderer" response types) -- honoring the
    flag here before that gate exists would let a single env var change on a
    real deployment silently expand the renderer's blast radius past approved
    scope. ``renderer_model_name`` is still read from real settings
    regardless (harmless while ``renderer_enabled`` is ``False`` -- the
    runtime never reads it in that state), so the wiring is already correct
    for the moment the gate lands and only needs `renderer_enabled` flipped
    per-route, not re-plumbed.
    """

    return {
        "renderer_enabled": False,
        "renderer_model_name": str(getattr(settings, "agent_renderer_model", "") or "") or None,
    }


# BUILD-5/BUILD-13 short-term memory and telemetry are deliberately
# process-local (see backend/agents/v2/short_term_memory.py); one instance is
# shared across requests behind the still-disabled flag so a conversation's
# session recall and the process metrics snapshot both work as designed.
_singleton_lock = Lock()
_short_term_memory: ShortTermMemoryStore | None = None
_telemetry: AgentTelemetry | None = None
# BUILD-32: the same BufferingSink instance `_telemetry` was constructed
# with -- kept as its own module global (rather than reading it back off
# `_telemetry`) so `_persist_durable_trace` can `.pop()` one run's real,
# live-captured spans without adding a public sink accessor to
# `AgentTelemetry` itself.
_telemetry_sink: BufferingSink | None = None


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
    global _telemetry, _telemetry_sink
    with _singleton_lock:
        if _telemetry is None:
            # BUILD-32: BufferingSink still delegates every event to
            # StructuredLogSink first (existing log behavior unchanged) and
            # additionally buffers each trace's real, live-captured events so
            # `_persist_durable_trace` can turn them into durable
            # `AgentRunSpan` rows after the response commits.
            _telemetry_sink = BufferingSink(StructuredLogSink())
            _telemetry = AgentTelemetry(sink=_telemetry_sink, pricing=ModelPricingCatalog.from_settings(settings))
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


# BUILD-32: makes Agent V2's real per-run token usage/cost/duration/timeout/
# error-code/empty-reply/evaluation durable in Postgres. Same best-effort,
# post-response shape as `_record_agent_v2_telemetry`/
# `_persist_activity_snapshot` right above -- a bug here must never affect a
# real chat response, and never runs before the real response is already
# committed.
#
# Spans: `AgentTelemetry.span()`/`record_model()` already measure real
# wall-clock duration live, during the actual runtime/orchestrator call (see
# `backend.agents.v2.observability`) -- the durability gap this build closes
# is only that the production sink threw that real data away into an
# unqueryable log line. `_telemetry_sink.pop(result.trace_id)` retrieves the
# exact events `BufferingSink` already buffered live for this run; only
# events carrying a real measured `latency_ms` (span-close/model-call/run-
# terminal events -- never a bare instantaneous marker event) become
# `AgentRunSpan` rows, so no fabricated-duration row is ever written.
#
# AgentRun columns: stamped here (not synchronously inside
# `CheckpointedTerminalStateRecorder`) because two terminal paths
# (SAFETY_BLOCKED, HANDOFF_CREATED) never reach that recorder at all --
# doing it in the one place that sees every `OrchestrationResult` uniformly
# guarantees complete coverage instead of two divergent code paths.
_TIMEOUT_ERROR_CODES = frozenset({"MODEL_TIMEOUT", "REQUEST_TIMEOUT"})


def _span_name_for(event_name: str, attributes: dict) -> str:
    if event_name == "agent_model.completed":
        return "model_call"
    if event_name == "agent_run.finished":
        return "run"
    tool_name = attributes.get("tool_name")
    operation = attributes.get("operation")
    if tool_name:
        return f"{operation}:{tool_name}" if operation else str(tool_name)
    return str(operation or "span")


def _build_span_rows(events: list) -> list[AgentRunSpan]:
    """Turn one run's buffered, already-real-timed events into durable
    `AgentRunSpan` rows.

    `AgentTelemetry.span()` emits a SEPARATE ``agent_span.started`` event
    (carries the call's own attributes, e.g. ``tool_name``/``model``) and
    ``agent_span.finished`` event (carries ``latency_ms``/``outcome`` only) --
    paired here (FIFO per component+operation; spans in this codebase are
    never nested) so neither the real duration nor the call's own attributes
    is lost. ``agent_model.completed``/``agent_run.finished`` are single,
    self-contained events (record_model()/record_terminal() emit everything
    in one call) and need no pairing. Bare instantaneous marker events (e.g.
    ``agent_router.classified``, ``agent_tool.completed``,
    ``agent_guardrail.*``) carry no ``latency_ms`` and are intentionally not
    turned into a (fabricated-duration) span row.
    """
    pending: dict[tuple[str, str], list[dict]] = {}
    rows: list[AgentRunSpan] = []
    for event in events:
        attributes = event.attributes
        if event.name == "agent_span.started":
            key = (event.component.value, str(attributes.get("operation") or ""))
            pending.setdefault(key, []).append(attributes)
            continue
        if event.name == "agent_span.finished":
            key = (event.component.value, str(attributes.get("operation") or ""))
            queue = pending.get(key)
            started_attrs = queue.pop(0) if queue else {}
            merged = {**started_attrs, **attributes}
            latency_ms = merged.get("latency_ms")
            if not isinstance(latency_ms, (int, float)):
                continue
            duration_ms = max(0.0, float(latency_ms))
            completed_at = event.occurred_at
            rows.append(
                AgentRunSpan(
                    agent_run_id=event.trace.agent_run_id,
                    trace_id=event.trace.trace_id,
                    span_name=_span_name_for(event.name, merged),
                    span_type=event.component.value,
                    status="ERROR" if merged.get("outcome") == "ERROR" else "OK",
                    started_at=completed_at - timedelta(milliseconds=duration_ms),
                    completed_at=completed_at,
                    duration_ms=duration_ms,
                    metadata_json=merged,
                )
            )
            continue
        if event.name in ("agent_model.completed", "agent_run.finished"):
            latency_ms = attributes.get("latency_ms")
            if not isinstance(latency_ms, (int, float)):
                continue
            duration_ms = max(0.0, float(latency_ms))
            completed_at = event.occurred_at
            rows.append(
                AgentRunSpan(
                    agent_run_id=event.trace.agent_run_id,
                    trace_id=event.trace.trace_id,
                    span_name=_span_name_for(event.name, attributes),
                    span_type=event.component.value,
                    status="ERROR" if attributes.get("outcome") == "ERROR" else "OK",
                    started_at=completed_at - timedelta(milliseconds=duration_ms),
                    completed_at=completed_at,
                    duration_ms=duration_ms,
                    metadata_json=dict(attributes),
                )
            )
    return rows


def _model_and_cost_from_events(
    events: list, *, metrics, pricing: ModelPricingCatalog
) -> tuple[str | None, str, str, float | None, float | None, float | None]:
    """TASK-V2.5-004 CP1 contract mục 3: real per-call model/cost, not a
    single-model aggregate guess. Caller guarantees ``metrics.model_calls >
    0`` here (the zero-call case is handled separately in
    ``_persist_durable_trace`` -- it never reaches this function). Returns
    ``(model, cost_status, pricing_version, input_cost_usd, output_cost_usd,
    total_cost_usd)``. ``model`` is the one real model every call used, or
    the literal string ``"MULTI_MODEL"`` when more than one distinct model
    appears across this run's own calls (e.g. planner=MAIN + renderer=
    RENDERER) -- never re-priced from aggregate tokens against a single
    assumed model, which would silently mix two different price lists into
    one number. Degrades honestly to ``NOT_AVAILABLE``/``None`` -- never a
    fabricated model or cost -- when the telemetry buffer lost/evicted this
    trace's events despite real calls happening, or when any one real call
    used a model absent from the pricing catalog.
    """

    model_call_events = [event for event in events if event.name == "agent_model.completed"]
    if not model_call_events:
        return None, "NOT_AVAILABLE", pricing.version, None, None, None
    models_used = {str(event.attributes.get("model") or "") for event in model_call_events}
    model = next(iter(models_used)) if len(models_used) == 1 else "MULTI_MODEL"
    input_cost_usd = output_cost_usd = total_cost_usd = 0.0
    for event in model_call_events:
        cost = event.attributes.get("estimated_cost_usd")
        if cost is None:
            return model, "NOT_AVAILABLE", pricing.version, None, None, None
        total_cost_usd += float(cost)
        input_cost_usd += float(event.attributes.get("input_cost_usd") or 0.0)
        output_cost_usd += float(event.attributes.get("output_cost_usd") or 0.0)
    return model, "AVAILABLE", pricing.version, input_cost_usd, output_cost_usd, total_cost_usd


def _persist_durable_trace(
    db: Session,
    *,
    result,
    telemetry: AgentTelemetry,
    settings: object,
    actor: CurrentUser,
) -> None:
    try:
        trace = TraceContext(trace_id=result.trace_id, agent_run_id=result.agent_run_id)
        # BUILD-32: real timing around the (small, synchronous, deterministic)
        # evaluation dispatch -- a genuine new span, not a reconstruction.
        with telemetry.span(trace, TraceComponent.EVALUATION, operation="dispatch_evaluation"):
            evaluation: EvaluationResult = dispatch_evaluation(result=result)

        events = _telemetry_sink.pop(result.trace_id) if _telemetry_sink is not None else []
        db.add_all(_build_span_rows(events))

        evaluation_payload = evaluation.as_dict()
        evaluation_version = str(evaluation_payload.get("evaluator_version") or "evaluation-v2")
        execution_path = evaluation_payload.get("execution_path")
        db.add(
            AgentRunEvaluation(
                agent_run_id=result.agent_run_id,
                trace_id=result.trace_id,
                evaluation_version=evaluation_version,
                execution_path=execution_path,
                metrics_json=evaluation_payload,
            )
        )

        metrics = result.metrics
        settings_model_name = str(getattr(settings, "agent_main_model", "") or "") or None
        error_code = getattr(result, "error_code", None)
        # A schedule/out-of-scope/clarification reply makes zero model calls
        # -- that is a real, definite zero, never "unknown"/N/A (plan §6).
        # Unlike the real-call branch below, there is no per-call telemetry
        # to derive a model from here, so this keeps stamping the
        # deployment's MAIN model as a label of convenience (a zero-call run
        # never actually used ANY model, so this is informational only, not
        # a cost-bearing claim -- cost is a real, definite zero either way).
        if metrics.model_calls <= 0:
            model_name = settings_model_name
            input_cost_usd = output_cost_usd = total_cost_usd = 0.0
            cost_status = "AVAILABLE"
            pricing_version = telemetry.pricing.version
        else:
            # TASK-V2.5-004 (CP1 contract mục 3, MULTI_MODEL accounting audit):
            # derive model/cost from THIS run's own real per-call
            # agent_model.completed events (AgentTelemetry.record_model
            # already computes an accurate per-call CostEstimate for every
            # real call) -- never re-estimated from the run's aggregate token
            # counts priced against one assumed model, which silently
            # mispriced any run whose calls used more than one model/price
            # (e.g. planner=ModelRole.MAIN + renderer=ModelRole.RENDERER).
            model_name, cost_status, pricing_version, input_cost_usd, output_cost_usd, total_cost_usd = (
                _model_and_cost_from_events(events, metrics=metrics, pricing=telemetry.pricing)
            )
            # PR review finding: cost accounting now depends on this run's
            # own telemetry events surviving in BufferingSink until this
            # point -- distinguish that (rarer, backlog-indicating) failure
            # mode from the ordinary "model has no configured price" one, so
            # it is operationally visible/alertable and correlatable with
            # BufferingSink's own eviction warning, rather than silently
            # blending into every other NOT_AVAILABLE cause.
            if model_name is None and cost_status == "NOT_AVAILABLE":
                logging.getLogger(__name__).warning(
                    "Agent V2 cost accounting degraded to NOT_AVAILABLE: telemetry buffer had "
                    "no agent_model.completed events for agent_run_id=%s trace_id=%s despite "
                    "%d real model call(s) -- likely BufferingSink eviction under backlog, not "
                    "an ordinary unpriced-model case.",
                    result.agent_run_id,
                    result.trace_id,
                    metrics.model_calls,
                )

        run = db.get(AgentRun, result.agent_run_id)
        if run is not None:
            run.trace_id = result.trace_id
            run.actor_id = actor.id
            run.input_tokens = metrics.input_tokens
            run.cached_input_tokens = metrics.cached_input_tokens
            run.output_tokens = metrics.output_tokens
            run.total_tokens = metrics.token_total
            run.model_calls = metrics.model_calls
            run.model = model_name
            run.pricing_version = pricing_version
            run.input_cost_usd = input_cost_usd
            run.output_cost_usd = output_cost_usd
            run.total_cost_usd = total_cost_usd
            run.cost_status = cost_status
            run.duration_ms = metrics.elapsed_ms
            run.timeout = error_code in _TIMEOUT_ERROR_CODES
            run.error_code = error_code
            # Plan §8: None/empty/whitespace-only/no user-visible answer --
            # never a legitimate deterministic empty-dataset reply the
            # composer still produced real text for.
            run.empty_reply = not (result.response or "").strip()
            run.evaluation_version = evaluation_version
            # BUILD-36: stamped so the Admin Monitoring V2 Versions tab has
            # a real, durable column to filter/compare on -- deployment-wide
            # constants at any given moment (this app has no per-request
            # prompt/retrieval override), meaningful for before/after
            # comparison ACROSS deployments, not a per-run varying signal.
            run.prompt_version = str(getattr(settings, "rag_prompt_version", "") or "") or None
            run.retrieval_version = str(getattr(settings, "rag_retriever_version", "") or "") or None
            # BUILD-47: makes the BUILD-43 follow-up decision durable. Read via
            # getattr because not every object reaching this best-effort
            # function is a full OrchestrationResult -- an AttributeError here
            # would be swallowed by the outer except and silently cost the run
            # its spans/evaluation/cost row too, not just these four fields.
            follow_up = getattr(result, "follow_up_decision", None)
            run.follow_up_category = follow_up.category.value if follow_up is not None else None
            run.follow_up_reason_code = follow_up.reason_code.value if follow_up is not None else None
            run.follow_up_inherited_topic = follow_up.inherited_topic if follow_up is not None else None
            run.follow_up_inherited_entity = follow_up.inherited_entity if follow_up is not None else None

        db.commit()
    except Exception as durable_err:  # noqa: BLE001 -- observability must never break the real response
        db.rollback()
        logging.getLogger(__name__).warning("Agent V2 durable trace recording failed: %s", durable_err)


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


# BUILD-44 SS13: never promise an SLA the app does not actually have; SS10
# uses almost this exact wording as its own spec example.
_DOCTOR_TAKEOVER_ACK_REPLY = "Bác sĩ đang theo dõi cuộc trò chuyện này. Tin nhắn của bạn đã được gửi."


def _respond_with_doctor_takeover_active(
    db: Session,
    *,
    request: AgentV2OrchestrateRequest,
    patient_id: str,
    conversation_id: str,
    actor: CurrentUser,
    handoff,
    started: float,
) -> AgentV2OrchestrateResponse:
    """BUILD-44 SS8/SS10/SS25: 0 router/RAG/Main Model/tool calls -- the
    patient's message is persisted for the doctor to read, never sent to
    Agent V2 synthesis. A real, minimal, durable ``AgentRun`` row is still
    written (status ``DOCTOR_ACTIVE`` -- a new, explicit, honest value,
    never a fabricated ``COMPLETED``/``model_calls=0`` that would misread
    as "the bot actually answered") so this turn is not invisible to the
    patient's own trace history or Admin Monitoring -- the same
    ``except Exception`` fallback a few lines below already establishes
    this pattern (a minimal direct ``AgentRun`` insert) for a different
    reason (the run raised before any durable row existed at all)."""
    now = datetime.now(UTC)
    record_doctor_review_message(
        db,
        handoff_id=handoff.id,
        patient_id=patient_id,
        sender_role=MessageSenderRole.PATIENT,
        actor_id=actor.id,
        content=request.message,
        created_at=now,
    )
    trace_id = str(uuid.uuid4())
    run = AgentRun(
        conversation_id=conversation_id,
        patient_id=patient_id,
        actor_id=actor.id,
        request_id=request.idempotency_key,
        intent=None,
        status="DOCTOR_ACTIVE",
        started_at=now,
        completed_at=now,
        trace_id=trace_id,
        duration_ms=max(0.0, (time.monotonic() - started) * 1000),
        cost_status="NOT_APPLICABLE",
    )
    db.add(run)
    db.commit()
    handoff_type = handoff_type_for(reason_code=handoff.reason_code, risk_disposition=handoff.risk_disposition).value
    return AgentV2OrchestrateResponse(
        status="DOCTOR_ACTIVE",
        reply=_DOCTOR_TAKEOVER_ACK_REPLY,
        intent="DOCTOR_TAKEOVER",
        tools=[],
        citations=[],
        safety_disposition=None,
        handoff_id=handoff.id,
        handoff_required=True,
        handoff_type=handoff_type,
        trace_id=trace_id,
        agent_run_id=run.id,
        suggested_actions=[],
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
        # TASK-V2.5-004: kept inert (see _renderer_runtime_kwargs's own
        # docstring) until the response-type eligibility gate exists -- same
        # wiring as the orchestrate route below, kept in sync so this debug/
        # smoke endpoint doesn't silently diverge from the real production
        # entry point.
        **_renderer_runtime_kwargs(settings),
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
    # BUILD-44: Agent V2 must not speak for a patient while a doctor OWNS
    # their conversation. Checked as early as possible -- before router/
    # RAG/Main Model/ConversationState work -- 0 model calls, same fail-
    # closed-before-work shape _require_agent_v2_enabled/patient access
    # above already use. ACTIVE only: PENDING/ASSIGNED do NOT suppress the
    # bot (see backend/services/agent_doctor_takeover.py's own docstring
    # and the BUILD-44 report SS7 for why). Patient-scoped (matching
    # BUILD-42's own cross-run dedup scope, not conversation-scoped) so a
    # patient cannot bypass an active takeover by starting a fresh
    # conversation_id.
    active_takeover = get_active_takeover(db, patient_id=patient_id)
    if active_takeover is not None:
        return _respond_with_doctor_takeover_active(
            db,
            request=request,
            patient_id=patient_id,
            conversation_id=conversation_id,
            actor=actor,
            handoff=active_takeover,
            started=_started,
        )
    state_store = AgentConversationStateStore()
    conversation_state = state_store.load(db, actor_id=actor.id, patient_id=patient_id, conversation_id=conversation_id)
    selected_action = _validated_selected_action(conversation_state, request.selected_action)
    input_resolution = resolve_state_input(conversation_state, message=request.message, selected_action=selected_action)
    # A numeric/typed follow-up is resolved from the same latest,
    # server-issued state as a button click. Downstream transition, activity,
    # and telemetry must use that resolved action rather than only the raw
    # client payload.
    selected_action = input_resolution.selected_action
    raw_intent = classify_intent(request.message, has_dose_id=bool(request.dose_id)).intent
    # BUILD-29F: a free-text dose-safety follow-up may rely on the canonical
    # medication already stored for this authorized conversation. This is
    # server-owned state, never a client-provided entity id; Safety routing
    # still sees the untouched raw message first inside the orchestrator.
    active_entity_for_request = (
        conversation_state.active_entity
        if conversation_state.active_entity
        and (input_resolution.used or raw_intent is OrchestrationIntent.MEDICATION_DOSE_SAFETY)
        else None
    )

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
            # TASK-V2.5-004: kept inert regardless of
            # AGENT_V2_5_RENDERER_ENABLED until the response-type
            # eligibility gate exists -- see _renderer_runtime_kwargs's own
            # docstring for why. Independent of Task 02/03's own flags
            # either way.
            **_renderer_runtime_kwargs(settings),
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
                # BUILD-49: falls back to the CONVERSATION, not to a fresh
                # uuid. `ShortTermMemoryStore` is keyed by (actor,
                # conversation, session); no client sends `session_id`
                # (verified across all of frontend/src), so a random value
                # here minted a brand-new session on every single HTTP
                # request -- the store wrote the current message and read
                # back only that same message, which is why the memory layer
                # had never once carried a previous turn in production.
                # `conversation_id` is already defaulted to a unique
                # `one-shot:<uuid>` above when the client sends none, so a
                # genuinely one-shot request stays just as isolated as
                # before; isolation across actors and conversations is
                # untouched, since both remain part of the key.
                session_id=request.session_id or conversation_id,
                dose_id=request.dose_id,
                request_id=request.idempotency_key,
                agent_run_id=idempotency_claim.agent_run_id if idempotency_claim is not None else None,
                resolved_query=input_resolution.query if input_resolution.used else None,
                active_entity_id=(
                    active_entity_for_request.legacy_drug_id or active_entity_for_request.id
                    if active_entity_for_request
                    else None
                ),
                active_entity_name=active_entity_for_request.canonical_name if active_entity_for_request else None,
                # The semantic value stays in state; the bound tool receives
                # the server-authored human query/label, never a client id.
                requested_attribute=selected_action.label
                if selected_action and selected_action.type == "drug_followup"
                else None,
                # BUILD-42: resolved from the same durable ConversationState
                # loaded above, same provenance discipline as every other
                # server-authored field in this request envelope.
                answerability_attempt_count=conversation_state.answerability_attempt_count,
                # BUILD-43: the CANONICAL prior state, ALWAYS passed (unlike
                # active_entity_id/active_entity_name above, which are only
                # set for the already-authorized button/typed-action path)
                # -- see follow_up.py's own module docstring and
                # OrchestrationRequest's own field comments for why this
                # replaced memory-text-based follow-up resolution.
                prior_active_topic=conversation_state.active_topic.canonical_name
                if conversation_state.active_topic
                else None,
                prior_active_entity_id=(
                    conversation_state.active_entity.legacy_drug_id or conversation_state.active_entity.id
                )
                if conversation_state.active_entity
                else None,
                prior_active_entity_name=conversation_state.active_entity.canonical_name
                if conversation_state.active_entity
                else None,
                # TASK-V2.5-002: raw prior-state evidence, always passed
                # (same discipline as prior_active_topic/prior_active_entity_*
                # above) -- harmless while the capability flag is off, since
                # the orchestrator's consumption of it is gated separately.
                prior_active_schedule_range=conversation_state.active_schedule_range,
                followup_capability_enabled=settings.agent_v2_5_followup_enabled,
                clarification_capability_enabled=settings.agent_v2_5_clarification_enabled,
            ),
            tools=tools,
            checkpoint_db=db,
        )
    except Exception:
        db.rollback()
        # BUILD-32: previously this path recorded absolutely nothing durable
        # -- neither `_record_agent_v2_telemetry` nor `_persist_activity_
        # snapshot`/`_persist_durable_trace` runs when `orchestrator.run()`
        # itself raises, since none of them are reached. `db.rollback()`
        # above already undid any partial `AgentRun`/checkpoint row this
        # attempt staged, so a fresh minimal row is the only way an Admin can
        # see that this request happened and failed at all. Best-effort, own
        # try/except: a failure here must not shadow the real exception below.
        try:
            db.add(
                AgentRun(
                    conversation_id=conversation_id,
                    patient_id=patient_id,
                    actor_id=actor.id,
                    request_id=request.idempotency_key,
                    intent=None,
                    status="FAILED",
                    started_at=datetime.now(UTC),
                    completed_at=datetime.now(UTC),
                    error_code="INTERNAL_ERROR",
                    cost_status="NOT_AVAILABLE",
                )
            )
            db.commit()
        except Exception as internal_err:  # noqa: BLE001
            db.rollback()
            logging.getLogger(__name__).warning("Agent V2 INTERNAL_ERROR durable recording failed: %s", internal_err)
        raise

    semantic = normalize_semantic_medical_query(input_resolution.query)
    resolved_entity = _resolved_drug_entity(
        result.tool_results, known_entity=conversation_state.active_entity
    ) or _picked_candidate_entity(selected_action)
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
    # to be state-write-safe (`_display_topic_from_raw`, follow_up.py: only
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
    # BUILD-43: an explicit TOPIC_SWITCH decision (follow_up.py) means the
    # canonical prior topic/entity must NOT be silently carried forward just
    # because THIS turn also failed to independently re-resolve a new one
    # (e.g. a genuinely new disease question whose phrasing doesn't happen
    # to match `_authoritative_topic_for_turn`'s own narrow rewrite rules
    # below) -- invariant #7 ("a topic switch must clear incompatible
    # inherited state"). `conversation_state_for_carry_forward` is what the
    # rest of this turn falls back to instead of `conversation_state`
    # itself for that one purpose; `conversation_state` itself is untouched
    # (still the real prior state passed to `transition_state` for every
    # OTHER field, and still what gets persisted if this turn fails).
    is_topic_switch = (
        result.follow_up_decision is not None and result.follow_up_decision.category is FollowUpCategory.TOPIC_SWITCH
    )
    conversation_state_for_carry_forward = (
        replace(conversation_state, active_topic=None, active_entity=None) if is_topic_switch else conversation_state
    )
    topic = _authoritative_topic_for_turn(
        conversation_state_for_carry_forward,
        selected_action=selected_action,
        semantic_topic=semantic.display_topic,
        is_general_medical_turn=result.intent is OrchestrationIntent.GENERAL_MEDICAL_INFORMATION,
        resolved_entity=resolved_entity,
    )
    active_topic = topic or (
        conversation_state_for_carry_forward.active_topic.canonical_name
        if conversation_state_for_carry_forward.active_topic
        else None
    )
    active_entity = resolved_entity or conversation_state_for_carry_forward.active_entity
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
    # BUILD-42: nonzero only when THIS turn's Answerability Gate decision was
    # NEED_MORE_INFO -- every other turn (answered, topic switch, NEED_DOCTOR
    # handoff, or the gate never engaging at all) resets the bounded-
    # clarification counter, matching ``transition_state``'s own docstring.
    next_answerability_attempt_count = (
        result.answerability_decision.attempt_count
        if result.answerability_decision is not None
        and result.answerability_decision.outcome.value == "NEED_MORE_INFO"
        else 0
    )
    next_answerability_reason = (
        result.answerability_decision.reason_code.value
        if result.answerability_decision is not None and result.answerability_decision.reason_code is not None
        else None
    )
    next_state = transition_state(
        conversation_state_for_carry_forward,
        intent=result.intent.value,
        topic=topic,
        entity=resolved_entity,
        selected_action=selected_action,
        offered_actions=suggested.actions,
        safety_event=safety_event,
        answerability_attempt_count=next_answerability_attempt_count,
        last_answerability_reason=next_answerability_reason,
        # TASK-V2.5-002: only non-None when THIS turn newly resolved a
        # genuine multi-day schedule range (never on the follow-up turn
        # that consumes a prior one) -- see OrchestrationResult's own field
        # comment and transition_state's docstring for why this is passed
        # through as-is rather than falling back to the prior state's value.
        schedule_range=result.resolved_schedule_range,
    )
    state_store.save(
        db,
        agent_run_id=result.agent_run_id,
        actor_id=actor.id,
        patient_id=patient_id,
        state=next_state,
    )

    # BUILD-42: a handoff created via the Answerability Gate always carries
    # `answerability_decision` with a real reason_code (see
    # `_answerability_handoff_reply` in orchestrator.py) -- any OTHER
    # handoff (Safety-Domain-sourced: acute danger, overdose, dose-
    # unresolved, or the pre-existing DOCTOR_REVIEW intent) never sets that
    # field, so its absence is exactly the SAFETY signal.
    handoff_type = None
    if result.handoff_result is not None:
        handoff_type = (
            handoff_type_for(
                reason_code=result.answerability_decision.reason_code.value, risk_disposition="UNCERTAINTY_HANDOFF"
            ).value
            if result.answerability_decision is not None and result.answerability_decision.reason_code is not None
            else handoff_type_for(reason_code=None, risk_disposition="HANDOFF_REQUIRED").value
        )

    response = AgentV2OrchestrateResponse(
        status=result.status,
        reply=suggested.reply,
        intent=result.intent,
        tools=[item.name for item in result.tool_results],
        citations=[AgentV2CitationOut(title=c.title, source=c.source, url=c.url) for c in result.citations],
        safety_disposition=result.safety_decision.outcome.value if result.safety_decision else None,
        handoff_id=result.handoff_result.request_id if result.handoff_result else None,
        handoff_required=result.handoff_result is not None,
        handoff_type=handoff_type,
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
    # BUILD-32: same best-effort, post-commit shape as the two calls above --
    # makes this run's real token usage/cost/duration/timeout/error/empty-
    # reply/evaluation/spans durable (see _persist_durable_trace's own
    # docstring).
    _persist_durable_trace(db, result=result, telemetry=telemetry, settings=settings, actor=actor)
    # BUILD-33: same best-effort, post-commit shape as the three calls above
    # -- decides Judge eligibility from real completed-run evidence
    # (Evaluation V2 dispatch, recomputed cheaply/deterministically inside
    # enqueue_run_judge) and, when eligible, inserts one JUDGE_PENDING row.
    # Never calls the Judge model itself -- that happens later, out-of-band,
    # off backend.services.escalation_scheduler's shared APScheduler. Fully
    # self-contained (own try/except/rollback/log), so it is safe to call
    # directly here without extra wrapping, same as _persist_durable_trace.
    enqueue_run_judge(db, result=result, request_message=request.message, settings=settings)
    # BUILD-34: same best-effort, post-commit shape as the calls above --
    # writes exactly one AgentSafetyEvent row when (and only when) this
    # run's real SafetyDecision.outcome was SAFETY_BLOCKED/HANDOFF_REQUIRED
    # (None for a plain SAFE outcome, by design). Pure consumer of the
    # already-computed `result` -- never influences Safety/Handoff runtime
    # behavior (BUILD-34 §12). Fully self-contained, safe to call directly.
    persist_safety_event(db, result=result, conversation_id=conversation_id, patient_id=patient_id, actor_id=actor.id)

    # TASK-021: Agent V2 is the production chat path. Persist its display-safe
    # patient/assistant pair just like the legacy route so the treating doctor
    # can review the patient's chatbot context after a handoff. This stores no
    # prompt, reasoning, or raw tool payload.
    save_chat_message(db, patient_id, "patient", request.message)
    save_chat_message(db, patient_id, "assistant", response.reply)

    return response
