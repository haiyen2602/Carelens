"""BUILD-43: unit tests for the new deterministic follow-up taxonomy
(``backend/agents/v2/follow_up.py``), against the spec's own required
repro categories (SS3 A-F) before any orchestrator wiring."""

from __future__ import annotations

from backend.agents.v2.follow_up import FollowUpCategory, classify_follow_up

# ---------------------------------------------------------------------------
# A. Short standalone question -- must NOT inherit unrelated prior topic/entity.
# ---------------------------------------------------------------------------


def test_a1_short_standalone_disease_question_no_prior_context():
    d = classify_follow_up("Viêm gan B là gì?", prior_topic=None, prior_entity_name=None)
    assert d.category is FollowUpCategory.STANDALONE_QUESTION
    assert d.inherited_topic is False and d.inherited_entity is False


def test_a2_short_standalone_cause_question_no_prior_context():
    d = classify_follow_up("Đau đầu do đâu?", prior_topic=None, prior_entity_name=None)
    assert d.category is FollowUpCategory.STANDALONE_QUESTION


def test_a3_short_standalone_drug_question_no_prior_context():
    d = classify_follow_up("Paracetamol là gì?", prior_topic=None, prior_entity_name=None)
    assert d.category is FollowUpCategory.STANDALONE_QUESTION


def test_a4_short_standalone_does_not_inherit_unrelated_prior_drug():
    """Same short question, but with an UNRELATED prior drug active -- must
    still not silently inherit it (SHORT != FOLLOW_UP even with context
    present, when the message explicitly names its own subject)."""
    d = classify_follow_up("Viêm gan B là gì?", prior_topic=None, prior_entity_name="Amoxicillin")
    assert d.category is FollowUpCategory.TOPIC_SWITCH
    assert d.inherited_entity is False
    assert d.inherited_topic is False


# ---------------------------------------------------------------------------
# B. True follow-up -- inherits the relevant drug entity/topic.
# ---------------------------------------------------------------------------


def test_b_true_followup_attribute_only_inherits_entity():
    d = classify_follow_up("Tác dụng phụ thì sao?", prior_topic=None, prior_entity_name="Paracetamol")
    assert d.category is FollowUpCategory.TRUE_FOLLOWUP
    assert d.inherited_entity is True
    assert d.inherited_topic is False


# ---------------------------------------------------------------------------
# C. Pronoun/deictic follow-up.
# ---------------------------------------------------------------------------


def test_c_deictic_this_drug_inherits_entity():
    d = classify_follow_up("Thuốc này có tác dụng phụ gì?", prior_topic=None, prior_entity_name="Amoxicillin")
    assert d.category is FollowUpCategory.TRUE_FOLLOWUP
    assert d.inherited_entity is True


def test_c2_deictic_this_disease_cause_question_inherits_topic_not_a_topic_switch():
    """BUILD-45 Candidate B regression lock. Widening _DISPLAY_TOPIC_
    PATTERNS (orchestrator.py, now the single canonical source
    _explicit_topic reads from) to cover the "X do dau" cause shape
    exposed a real, pre-existing gap in _explicit_topic's own rejection
    logic: it only ever rejected a topic that IS WHOLLY a bare pronoun
    ("no"), never one that merely CONTAINS a deictic word ("Bệnh này" ->
    "benh nay", already its own _DEICTIC_MARKERS entry). Without the fix,
    "Bệnh này do đâu?" would misclassify as TOPIC_SWITCH (an explicit new
    topic "Bệnh này") instead of TRUE_FOLLOWUP correctly inheriting the
    prior topic -- caught by the pre-existing BUILD-43 orchestrator suite
    itself, not assumed safe."""
    d = classify_follow_up("Bệnh này do đâu?", prior_topic="sỏi thận", prior_entity_name=None)
    assert d.category is FollowUpCategory.TRUE_FOLLOWUP
    assert d.inherited_topic is True


# ---------------------------------------------------------------------------
# D. Topic switch -- must clear old drug context.
# ---------------------------------------------------------------------------


def test_d_topic_switch_drug_to_disease():
    d = classify_follow_up("Viêm phổi là bệnh gì?", prior_topic=None, prior_entity_name="Paracetamol")
    assert d.category is FollowUpCategory.TOPIC_SWITCH
    assert d.inherited_entity is False
    assert d.inherited_topic is False


def test_d2_topic_switch_disease_to_drug():
    d = classify_follow_up("Amoxicillin dùng thế nào?", prior_topic="viêm phổi", prior_entity_name=None)
    assert d.category is FollowUpCategory.TOPIC_SWITCH


# ---------------------------------------------------------------------------
# E. Ambiguous fragment -- unless enough prior context exists.
# ---------------------------------------------------------------------------


def test_e1_ambiguous_fragment_no_context():
    d = classify_follow_up("còn loại 500mg?", prior_topic=None, prior_entity_name=None)
    assert d.category is FollowUpCategory.AMBIGUOUS_FRAGMENT


def test_e2_ambiguous_fragment_this_thing_no_context():
    d = classify_follow_up("thế còn cái này?", prior_topic=None, prior_entity_name=None)
    assert d.category is FollowUpCategory.AMBIGUOUS_FRAGMENT


def test_e3_ambiguous_fragment_resolves_to_true_followup_with_context():
    d = classify_follow_up("còn loại 500mg?", prior_topic=None, prior_entity_name="Paracetamol")
    assert d.category is FollowUpCategory.TRUE_FOLLOWUP
    assert d.inherited_entity is True


# ---------------------------------------------------------------------------
# F. Short but complete disease question -- must NOT be follow-up solely
#    due to length, regardless of whether prior (unrelated) context exists.
# ---------------------------------------------------------------------------


def test_f_short_complete_question_not_followup_by_length_alone():
    for message in ("Viêm gan B là gì?", "Đau đầu do đâu?", "Paracetamol là gì?"):
        d = classify_follow_up(message, prior_topic=None, prior_entity_name=None)
        assert d.category is not FollowUpCategory.TRUE_FOLLOWUP, message
        assert len(message) <= 35


# ---------------------------------------------------------------------------
# Additional required test matrix items (SS20)
# ---------------------------------------------------------------------------


def test_g_long_standalone_is_not_followup():
    """B. long standalone != follow-up."""
    message = "Bệnh tiểu đường type 2 có những triệu chứng nào cần chú ý theo dõi lâu dài?"
    d = classify_follow_up(message, prior_topic=None, prior_entity_name="Paracetamol")
    assert d.category is not FollowUpCategory.TRUE_FOLLOWUP


def test_stale_entity_not_inherited_on_explicit_new_topic():
    d = classify_follow_up("Cảm cúm có nguy hiểm không?", prior_topic=None, prior_entity_name="Ibuprofen")
    assert d.category is FollowUpCategory.TOPIC_SWITCH
    assert d.inherited_entity is False


def test_no_prior_context_at_all_defaults_standalone_for_named_subject():
    d = classify_follow_up("Vitamin C có tác dụng gì?", prior_topic=None, prior_entity_name=None)
    assert d.category is FollowUpCategory.STANDALONE_QUESTION


def test_h_unrelated_short_standalone_question_does_not_inherit_prior_topic():
    """BUILD-45 §13 false-positive-safety lock: a short, unrelated,
    self-naming question must not silently inherit a stale prior TOPIC.
    The entity-side equivalent of this exact case was already covered
    (test_a4_short_standalone_does_not_inherit_unrelated_prior_drug /
    test_stale_entity_not_inherited_on_explicit_new_topic) but no test
    named the TOPIC-side case explicitly, so this closes that gap."""
    d = classify_follow_up("Cảm cúm là gì?", prior_topic="Tiểu đường", prior_entity_name=None)
    assert d.category is FollowUpCategory.TOPIC_SWITCH
    assert d.inherited_topic is False
    assert d.inherited_entity is False


def test_explicit_topic_repeats_same_prior_topic_stays_standalone_inherits_topic():
    d = classify_follow_up("Viêm phổi là gì?", prior_topic="Viêm phổi", prior_entity_name=None)
    assert d.category is FollowUpCategory.STANDALONE_QUESTION
    assert d.inherited_topic is True
