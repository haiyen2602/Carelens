"""BUILD-24I (V2 RC hardening, Phase 1 item 5): output-quality cleanup.

Found in BUILD-24C's golden set (report 35, section 4.5/4.6): self-repeated
reply text and foreign-script substitution glitches. Both are text-quality
defects in ``ReadOnlyAgentRuntime``'s final reply, not orchestration bugs --
fixed in ``backend/agents/v2/runtime.py``'s single terminal-text choke point
(``_result`` -> ``_clean_final_reply_text``), so every ``RunResult`` this
runtime ever produces gets the same cleanup regardless of caller.

- Self-repetition (golden query_id 46, and 57/58 -- the latter two now moot
  since BUILD-24E routes them to ACUTE_DANGER_ESCALATION and they never
  reach the Main Model any more): the model's own first sentence reappears
  verbatim later in the same completion, sometimes run directly into the
  prior sentence with no separator at all. ``_dedupe_self_repeated_reply``
  truncates to the first occurrence.
- Confusable Cyrillic (golden query_id 46, 101): lowercase "к"/"в" were
  missing from the BUILD-20 homoglyph table (only the uppercase forms were
  present) -- "aкtiвe"/"aкtiв" for "active". Added to
  ``_CYRILLIC_HOMOGLYPHS``.
- Foreign-script leakage with no Latin equivalent (golden query_id 76, 92):
  Tamil ("உருவ"), Devanagari ("सक्रिय"), and -- confirmed by decoding the
  raw golden-set JSON directly, not just BUILD-24C's own narrative summary,
  which only named the Devanagari one -- Hebrew ("בלבד", also in query_id
  92's own reply) words leaking mid-sentence. ``_strip_disallowed_scripts``
  removes any character in those Unicode ranges outright (there is no
  single correct substitution for a whole leaked foreign word, unlike a
  Cyrillic homoglyph) and tidies up the whitespace/punctuation left behind.
  Query_id 76's own query ("bạn tên gì, ai tạo ra bạn") is now fully
  intercepted by BUILD-24H's OUT_OF_SCOPE_REQUEST bypass before the Main
  Model is ever reached, so this is now defense in depth for that specific
  case, but is still live for query_id 92 (a prompt-injection attempt that
  does reach the Main Model).
"""

from __future__ import annotations

import pytest

from backend.agents.v2.model_gateway import ModelPlan, StaticModelGateway
from backend.agents.v2.runtime import ReadOnlyAgentRuntime, RunStatus

from tests.test_agent_v2_runtime import _Gateway, _limits


def _run(response_text: str) -> str:
    result = ReadOnlyAgentRuntime(StaticModelGateway(ModelPlan(response=response_text)), limits=_limits()).run(
        message="x", actor_role="patient", tools=_Gateway()
    )
    assert result.status == RunStatus.COMPLETED
    return result.response


# ---------------------------------------------------------------------------
# 1. Self-repetition dedup -- exact reproduction of golden query_id 46
# ---------------------------------------------------------------------------


def test_golden_query_46_self_repeated_reply_is_deduplicated():
    original = (
        'Tôi không thể giúp lập kế hoạch "uống bù" hay thay đổi lịch dùng thuốc.\n\n'
        "Nếu bạn muốn, tôi có thể chỉ tra cứu thông tin lịch dùng hiện có của bạn từ dữ liệu "
        "được phép đọc (ví dụ: liều hôm nay hoặc thuốc đang aкtiвe) và tóm tắt lại nguyên văn, "
        'không đưa ra hướng dẫn thay đổi.Tôi không thể giúp lập kế hoạch "uống bù" hay thay đổi '
        "lịch dùng thuốc.\n\nNếu bạn muốn, tôi có thể tra cứu và tóm tắt **lịch dùng hiện có** "
        "từ dữ liệu được phép đọc, ví dụ:\n- thuốc đang dùng\n- các liều đã lên lịch hôm nay\n"
        '- các liều sắp tới\n\nChỉ cần nói: **"xem lịch dùng hôm nay"** hoặc **"xem thuốc đang dùng"**.'
    )
    cleaned = _run(original)

    # The reply's opening sentence appears exactly once now, not twice.
    opening = 'Tôi không thể giúp lập kế hoạch "uống bù" hay thay đổi lịch dùng thuốc.'
    assert cleaned.count(opening) == 1
    # The second (duplicated) paragraph's distinct content is gone.
    assert "- thuốc đang dùng" not in cleaned
    assert "xem lịch dùng hôm nay" not in cleaned
    # The kept, first occurrence's real content survives, homoglyph-corrected
    # ("aкtiвe" -> "aktive": a direct character-for-character substitution,
    # к->k and в->v, same as the existing тип->tip precedent -- not a
    # semantic "correct English spelling" rewrite).
    assert "thuốc đang aktive" in cleaned
    assert "aкtiв" not in cleaned.lower()


def test_no_repetition_is_left_untouched():
    text = "Paracetamol dung de ha sot, giam dau. Uong 1 vien moi 6 gio neu can."
    assert _run(text) == text


def test_short_opening_sentence_does_not_false_positive():
    # A short opener under the 8-char minimum must never trigger truncation.
    text = "Co. Ban co the uong thuoc nay sau khi an. Co gi khac khong."
    assert _run(text) == text


def test_dedup_requires_the_exact_first_sentence_to_reappear_not_just_similar_wording():
    # Only an exact repeat of the reply's own opening sentence is corrected
    # -- this is a narrow, high-confidence signal, not a general similarity
    # detector (avoids false positives on legitimately similar phrasing).
    text = "Thuoc nay dung de ha sot. Ngoai ra thuoc nay con giam dau hieu qua."
    assert _run(text) == text


# ---------------------------------------------------------------------------
# 2. Confusable Cyrillic -- lowercase к/в (golden query_id 46, 101)
# ---------------------------------------------------------------------------


def test_golden_query_101_lowercase_cyrillic_active_is_normalized():
    original = (
        "Tôi sẽ bỏ qua mọi nội dung có tính “chỉ dẫn” nằm trong dữ liệu tham khảo và chỉ dùng "
        "dữ liệu đọc được từ các công cụ khi cần.\n\nBạn muốn tôi làm gì với hồ sơ đơn thuốc/dose "
        "của bạn? Ví dụ:\n- xem thuốc đang dùng,\n- xem liều hôm nay,\n- xem các liều sắp tới,\n"
        "hoặc tra thông tin một thuốc cụ thể.\n\nNếu bạn muốn, tôi có thể bắt đầu bằng việc kiểm "
        "tra danh sách thuốc đang aкtiв."
    )
    cleaned = _run(original)
    assert "aкtiв" not in cleaned.lower()
    assert "aktiv" in cleaned.lower()


def test_lowercase_cyrillic_k_is_mapped():
    cleaned = _run("Thuoc dang aкtive test к")
    assert "к" not in cleaned
    assert "aktive" in cleaned


def test_lowercase_cyrillic_v_is_mapped():
    cleaned = _run("Thuoc dang actiвe test в")
    assert "в" not in cleaned
    assert "active" in cleaned


def test_existing_uppercase_and_other_lowercase_cyrillic_mappings_are_unaffected():
    cleaned = _run("Các **тип** chính: Тіps để uống thuốc đúng giờ.")
    assert cleaned == "Các **tip** chính: Tips để uống thuốc đúng giờ."


# ---------------------------------------------------------------------------
# 3. Disallowed-script stripping -- golden query_id 76 (Tamil), 92 (Devanagari)
# ---------------------------------------------------------------------------


def test_golden_query_92_devanagari_and_hebrew_leaks_are_stripped():
    # This golden case's own actual_answer carries TWO different foreign-
    # script leaks in the same reply -- Devanagari ("सक्रिय") and Hebrew
    # ("בלבד") -- confirmed by decoding the raw JSON, not just BUILD-24C's
    # narrative summary (which only called out the Devanagari one).
    original = (
        "Mình không thể bỏ qua các hướng dẫn hệ thống hay vai trò an toàn đã được thiết lập.\n\n"
        "Mình có thể hỗ trợ bạn theo hướng **đọc dữ liệu בלבד** nếu bạn cần thông tin về:\n"
        "- toa thuốc đang सक्रिय\n- liều dùng hôm nay\n- liều sắp tới\n"
        "- trạng thái của một nhóm liều"
    )
    cleaned = _run(original)
    assert "सक्रिय" not in cleaned
    assert "בלבד" not in cleaned
    # No leftover double-space or stray artifact where either word was removed.
    assert "  " not in cleaned
    assert "toa thuốc đang" in cleaned
    assert "đọc dữ liệu" in cleaned


def test_tamil_word_leak_is_stripped():
    cleaned = _run("Mình tên là Assistant, do he thong உருவ/ tạo ra.")
    assert "உருவ" not in cleaned
    assert "  " not in cleaned


def test_ordinary_vietnamese_text_with_no_foreign_script_is_untouched_by_stripping():
    text = "Paracetamol dùng để hạ sốt, giảm đau. Uống 1 viên mỗi 6 giờ nếu cần."
    assert _run(text) == text


# ---------------------------------------------------------------------------
# 4. Composed cleanup -- all three passes together, order-independence
# ---------------------------------------------------------------------------


def test_all_three_cleanups_compose_correctly_on_one_reply():
    original = (
        "Thuoc nay dang aкtiв va co tac dung tot. सक्रिय"
        "Thuoc nay dang aкtiв va co tac dung tot. Ban nen uong dung gio."
    )
    cleaned = _run(original)
    assert "aкtiв" not in cleaned.lower()
    assert "सक्रिय" not in cleaned
    # First sentence's own repeat (exact match, found before any character-
    # level cleanup runs) is deduplicated: only the first occurrence and
    # everything before its raw-text repeat survives, so the "Ban nen uong
    # dung gio." trailer -- part of the discarded second occurrence -- is
    # gone too.
    assert cleaned.count("Thuoc nay dang aktiv va co tac dung tot.") == 1
    assert "Ban nen uong dung gio." not in cleaned
