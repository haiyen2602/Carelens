"""FastAPI dependency cho cac ham LLM/embedding that dung boi POST
/api/v1/chat (Phase 6). Goi qua `Depends(get_chat_services)` (khong import
thang tu route handler) de test co the `app.dependency_overrides[...]`
thay bang fake function - dung idiom voi `Depends(get_db)` da co
(src/db/base.py) - tranh goi OpenAI that trong test (cung nguyen tac cost-
consciousness da giu xuyen suot Phase 1-5b)."""

from __future__ import annotations

from dataclasses import dataclass

from src.agents.nodes.conversation_nodes import AnswerGenerateFn, IntentClassifyFn
from src.agents.nodes.dose_confirmation_nodes import DoseClassifyFn, SeverityClassifyFn
from src.agents.orchestrator import SafetyCheckFn, default_safety_check
from src.agents.tools.drug_info_tool import EmbedFn


@dataclass(frozen=True)
class ChatServices:
    classify_intent: IntentClassifyFn
    classify_dose: DoseClassifyFn
    generate_answer: AnswerGenerateFn
    classify_severity: SeverityClassifyFn
    embed_query: EmbedFn
    safety_check: SafetyCheckFn


def get_chat_services() -> ChatServices:
    """Implementation THAT (goi OpenAI that) - dung cho production. Test
    override qua `app.dependency_overrides[get_chat_services]`."""
    from src.services.classification import classify_dose, classify_intent, classify_severity, generate_answer
    from src.services.embeddings import embed_query

    return ChatServices(
        classify_intent=classify_intent,
        classify_dose=classify_dose,
        generate_answer=generate_answer,
        classify_severity=classify_severity,
        embed_query=embed_query,
        safety_check=default_safety_check,
    )
