"""Vong 4, muc 6.3 - regression cho soul patient-facing cua Capy Medi."""

from backend.agents.nodes.conversation_nodes import (
    CAVEAT_LIEU_DUNG,
    CAVEAT_THOI_DIEM_MISSING,
    GREETING_RESPONSE,
    NO_SCHEDULE_TODAY_MESSAGE,
    NO_SOURCE_MESSAGE,
    _greeting_response_for,
)
from backend.agents.nodes.dose_confirmation_nodes import (
    ASK_AGAIN_MESSAGE,
    LOW_ACTION_RESPONSE,
    MEDIUM_ACTION_RESPONSE,
    TAKEN_RESPONSE,
)
from backend.agents.nodes.drug_confirmation_nodes import (
    ASK_DESCRIBE_AGAIN_MESSAGE,
    ASK_DIFFERENT_NAME_MESSAGE,
    NOT_FOUND_FINAL_MESSAGE,
    TOO_MANY_UNPARSEABLE_REPLIES_MESSAGE,
    UNPARSEABLE_CHOICE_MESSAGE_TEMPLATE,
    UNPARSEABLE_YES_NO_MESSAGE,
    _confirm_question,
    _top3_menu,
)
from backend.services.classification import (
    _ANSWER_PROMPT,
    _HOURLY_SUMMARY_PROMPT,
    _INTENT_PROMPT,
    _PATIENT_LANGUAGE_AND_PERSONA,
    _SAFETY_LLM_PROMPT,
)


def test_patient_facing_fixed_responses_follow_capy_persona():
    responses = (
        CAVEAT_LIEU_DUNG,
        CAVEAT_THOI_DIEM_MISSING,
        NO_SOURCE_MESSAGE,
        NO_SCHEDULE_TODAY_MESSAGE,
        GREETING_RESPONSE,
        _greeting_response_for("Nguyen Van A"),
        ASK_AGAIN_MESSAGE,
        TAKEN_RESPONSE,
        LOW_ACTION_RESPONSE,
        MEDIUM_ACTION_RESPONSE,
        NOT_FOUND_FINAL_MESSAGE,
        ASK_DIFFERENT_NAME_MESSAGE,
        ASK_DESCRIBE_AGAIN_MESSAGE,
        UNPARSEABLE_YES_NO_MESSAGE,
        UNPARSEABLE_CHOICE_MESSAGE_TEMPLATE,
        TOO_MANY_UNPARSEABLE_REPLIES_MESSAGE,
        _confirm_question("Vitamin C 500mg"),
        _top3_menu([{"ten_thuoc": "Vitamin C 500mg"}]),
    )

    assert all(response.startswith("Dạ") for response in responses)
    assert "mình" in GREETING_RESPONSE.lower()
    assert "bạn" in GREETING_RESPONSE.lower()


def test_persona_is_limited_to_patient_facing_generation():
    rendered_answer = _ANSWER_PROMPT.format(
        persona=_PATIENT_LANGUAGE_AND_PERSONA,
        utterance="What are the side effects of Vitamin C 500mg?",
        context="Vitamin C 500mg: Có thể gây buồn nôn.",
    )

    assert _PATIENT_LANGUAGE_AND_PERSONA in rendered_answer
    assert "triệu chứng" in rendered_answer
    assert "nguyên nhân" in rendered_answer
    assert "Không chẩn đoán, kê đơn" in rendered_answer
    assert "Luôn trả lời bằng tiếng Việt" in rendered_answer
    assert "{persona}" in _HOURLY_SUMMARY_PROMPT
    assert _PATIENT_LANGUAGE_AND_PERSONA not in _INTENT_PROMPT
    assert _PATIENT_LANGUAGE_AND_PERSONA not in _SAFETY_LLM_PROMPT
