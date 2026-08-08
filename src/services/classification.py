"""Cac ham LLM THAT (gpt-4o-mini, Structured Outputs - chatbot-rag-design.md
muc 2) dung de wire cac node Phase 5/5b vao production that (Phase 6). Test
KHONG goi qua day - moi test tu Phase 5 tro di deu dung fake function tu
injected truc tiep (xem tests/), file nay chi duoc goi tu main.py that.

Prompt o day la BAN DAU (first draft) - CHUA qua eval that (Phase 7,
build-kickoff-prompt.md), khong coi la da toi uu."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.services.llm import get_llm
from src.services.retrieval import DrugInfoResult


class _IntentResult(BaseModel):
    intent: Literal["drug_info", "today_schedule", "dose_confirmation"]
    confidence: float = Field(ge=0.0, le=1.0)


_INTENT_PROMPT = """Phân loại ý định của bệnh nhân vào 1 trong 3 nhóm:
- drug_info: hỏi thông tin chung về 1 loại thuốc (tác dụng, tác dụng phụ, cách dùng, liều dùng)
- today_schedule: hỏi lịch uống thuốc hôm nay / còn liều nào chưa uống
- dose_confirmation: xác nhận đã uống / chưa uống / uống trễ / có tác dụng phụ cho 1 liều cụ thể

Câu nói của bệnh nhân: {utterance}"""


def classify_intent(utterance: str) -> tuple[str, float]:
    """IntentClassifyFn (src/agents/nodes/conversation_nodes.py)."""
    llm = get_llm().with_structured_output(_IntentResult)
    result: _IntentResult = llm.invoke(_INTENT_PROMPT.format(utterance=utterance))
    return result.intent, result.confidence


class _DoseClassificationResult(BaseModel):
    label: Literal["TAKEN", "MISSED", "DELAYED", "SIDE_EFFECT"]
    confidence: float = Field(ge=0.0, le=1.0)


_DOSE_CLASSIFY_PROMPT = """Phân loại phát ngôn của bệnh nhân về 1 liều thuốc cụ thể vào 1 trong 4 nhãn:
- TAKEN: đã uống rồi
- MISSED: bỏ liều, chưa uống và sẽ không uống buổi này nữa
- DELAYED: chưa uống nhưng sẽ uống trễ
- SIDE_EFFECT: có đề cập tác dụng phụ/triệu chứng bất thường (dù có thể đã uống hay chưa)

Câu nói của bệnh nhân: {utterance}"""


def classify_dose(utterance: str) -> tuple[str, float]:
    """DoseClassifyFn (src/agents/nodes/dose_confirmation_nodes.py)."""
    llm = get_llm().with_structured_output(_DoseClassificationResult)
    result: _DoseClassificationResult = llm.invoke(_DOSE_CLASSIFY_PROMPT.format(utterance=utterance))
    return result.label, result.confidence


class _SeverityResult(BaseModel):
    severity: Literal["Nhẹ", "Trung bình", "Nguy hiểm"] | None = Field(
        description="null neu noi dung khong du ro rang de ket luan muc do nguy hiem"
    )


_SEVERITY_PROMPT = """Dựa vào mô tả công dụng và tác dụng phụ của 1 loại thuốc dưới đây, đánh giá
mức độ nguy hiểm NẾU BỆNH NHÂN BỎ/TRỄ LIỀU thuốc này ở mức: Nhẹ, Trung bình, hoặc Nguy hiểm.
Nếu nội dung không đủ rõ ràng để kết luận, trả về null - KHÔNG đoán.

{combined_text}"""


def classify_severity(combined_text: str) -> str | None:
    """SeverityClassifyFn (src/agents/nodes/dose_confirmation_nodes.py)."""
    llm = get_llm().with_structured_output(_SeverityResult)
    result: _SeverityResult = llm.invoke(_SEVERITY_PROMPT.format(combined_text=combined_text))
    return result.severity


_ANSWER_PROMPT = """Bạn là trợ lý nhắc thuốc. Trả lời câu hỏi của bệnh nhân CHỈ dựa vào thông tin
dưới đây (không bịa thêm, không dùng kiến thức ngoài). Trả lời ngắn gọn, thân thiện, tiếng Việt.

Câu hỏi: {utterance}

Thông tin thuốc:
{context}"""


def generate_answer(utterance: str, rag_results: list[DrugInfoResult]) -> str:
    """AnswerGenerateFn (src/agents/nodes/conversation_nodes.py)."""
    context = "\n\n".join(f"[{r.source}]\n{r.noi_dung}" for r in rag_results)
    llm = get_llm()
    response = llm.invoke(_ANSWER_PROMPT.format(utterance=utterance, context=context))
    return response.content
