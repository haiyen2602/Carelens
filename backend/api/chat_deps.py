"""FastAPI dependency cho cac ham LLM/embedding that dung boi POST
/api/v1/chat (Phase 6). Goi qua `Depends(get_chat_services)` (khong import
thang tu route handler) de test co the `app.dependency_overrides[...]`
thay bang fake function - dung idiom voi `Depends(get_db)` da co
(src/db/base.py) - tranh goi OpenAI that trong test (cung nguyen tac cost-
consciousness da giu xuyen suot Phase 1-5b)."""

from __future__ import annotations

from dataclasses import dataclass

from backend.agents.nodes.conversation_nodes import AnswerGenerateFn, IntentClassifyFn
from backend.agents.nodes.dose_confirmation_nodes import DoseClassifyFn, SeverityClassifyFn
from backend.agents.nodes.drug_confirmation_nodes import (
    DrugReplyPlausibilityFn,
    FuzzyCandidateSelectFn,
    _default_drug_reply_plausibility,
    _default_fuzzy_candidate_select,
)
from backend.agents.nodes.side_effect_audit_nodes import SideEffectMatchFn, _default_side_effect_match
from backend.agents.orchestrator import SafetyCheckFn, default_safety_check
from backend.agents.tools.drug_info_tool import EmbedFn


@dataclass(frozen=True)
class ChatServices:
    classify_intent: IntentClassifyFn
    classify_dose: DoseClassifyFn
    generate_answer: AnswerGenerateFn
    classify_severity: SeverityClassifyFn
    embed_query: EmbedFn
    safety_check: SafetyCheckFn
    # Vong 4, muc 2.2 - mac dinh permissive (khong sua hanh vi cu cho test
    # nao chua biet ve gate nay); get_chat_services() THAT luon override
    # bang ham LLM that ben duoi, khong dua vao default nay.
    classify_drug_reply_plausibility: DrugReplyPlausibilityFn = _default_drug_reply_plausibility
    select_fuzzy_candidate: FuzzyCandidateSelectFn = _default_fuzzy_candidate_select
    classify_side_effect_match: SideEffectMatchFn = _default_side_effect_match


def get_chat_services() -> ChatServices:
    """Implementation THAT (goi OpenAI that) - dung cho production. Test
    override qua `app.dependency_overrides[get_chat_services]`."""
    from backend.services.classification import (
        classify_dose,
        classify_drug_reply_plausibility,
        classify_intent,
        classify_severity,
        classify_side_effect_match,
        generate_answer,
        select_fuzzy_drug_candidate,
    )
    from backend.services.embeddings import embed_query

    return ChatServices(
        classify_intent=classify_intent,
        classify_dose=classify_dose,
        generate_answer=generate_answer,
        classify_severity=classify_severity,
        embed_query=embed_query,
        safety_check=default_safety_check,
        classify_drug_reply_plausibility=classify_drug_reply_plausibility,
        select_fuzzy_candidate=select_fuzzy_drug_candidate,
        classify_side_effect_match=classify_side_effect_match,
    )
