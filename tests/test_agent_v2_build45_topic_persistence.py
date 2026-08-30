"""BUILD-45 Candidate B: topic persistence coverage.

Root cause (confirmed by real code read, not assumed): ``_DISPLAY_TOPIC_
PATTERNS`` -- the pattern family ``_display_topic_from_raw``
(orchestrator.py) uses to decide whether a message's disease/topic name
is worth persisting into canonical ``ConversationState.active_topic`` --
was independently DEFINED TWICE (orchestrator.py AND follow_up.py's own
``_explicit_topic``), and the two copies had ALREADY DRIFTED APART
(orchestrator.py's own copy once had a "con X thi sao" shape follow_up.py's
copy lacked). Neither copy tested an ASCII-folded (no-diacritics) variant
of most patterns, unlike the WIDER retrieval-side semantic families
(``_CAUSE_PATTERNS``/``_SYMPTOM_PATTERNS``/etc., also orchestrator.py)
which explicitly test both accented and folded forms. Several real,
missing sentence shapes were also found this way (spec's own worked
examples): "X là bệnh gì" (only "X là gì" was handled), "X do đâu"
(missing entirely), and "nguyên nhân X là gì" with no connector word
(previously matched the GENERIC "X là gì" pattern first and wrongly
captured "nguyên nhân X" as the topic, including those two words).

Fix: ONE canonical, widened ``_DISPLAY_TOPIC_PATTERNS`` (orchestrator.py).
follow_up.py's ``_explicit_topic`` now imports it directly (a
function-local import -- orchestrator.py imports FROM follow_up.py at
module level, so importing back at module level would be circular) instead
of maintaining a second, divergent copy. Its own REJECTION logic
(``_ATTRIBUTE_KEYWORDS``/``_PRONOUN_ONLY_WORDS``/now also deictic
CONTAINMENT, not just whole-string equality) is deliberately NOT shared --
see ``test_agent_v2_follow_up.py::test_c2_...`` for the real regression
this widening exposed there and how it was fixed.
"""

from __future__ import annotations

from backend.agents.v2.follow_up import _explicit_topic
from backend.agents.v2.orchestrator import _display_topic_from_raw


def test_definition_question_with_benh_gi_tail_now_extracts_a_topic():
    """Spec's own example #1: "X là bệnh gì" (bệnh appearing in the
    TRAILING question tail) used to return None -- only a LEADING "bệnh "
    prefix before the topic was recognized, a different sentence shape."""
    assert _display_topic_from_raw("Viêm gan B là bệnh gì?") == "Viêm gan B"


def test_definition_question_la_gi_still_works_unchanged():
    assert _display_topic_from_raw("Viêm gan B là gì?") == "Viêm gan B"


def test_cause_question_do_dau_shape_now_extracts_a_topic():
    """Spec's own example #3: "X do đâu" was entirely missing from
    _DISPLAY_TOPIC_PATTERNS before this fix (present in the wider
    retrieval-side _CAUSE_PATTERNS family, but that is a deliberately
    separate, untouched pattern set -- see this module's own docstring)."""
    assert _display_topic_from_raw("Đau đầu do đâu?") == "Đau đầu"


def test_cause_question_no_connector_no_longer_corrupts_the_topic():
    """Spec's own example #4, a real WRONG-extraction bug, not just a
    missed match: "Nguyên nhân đau đầu là gì?" has no gây/của/dẫn đến
    connector, so it used to fall through to the generic "X là gì"
    pattern and capture "Nguyên nhân đau đầu" (the words "Nguyên nhân"
    leaking into the topic) instead of just "đau đầu"."""
    assert _display_topic_from_raw("Nguyên nhân đau đầu là gì?") == "đau đầu"


def test_symptom_question_still_works_unchanged():
    assert _display_topic_from_raw("Triệu chứng viêm phổi?") == "viêm phổi"


def test_ascii_folded_definition_question_extracts_a_topic():
    assert _display_topic_from_raw("viem gan b la gi") == "viem gan b"


def test_ascii_folded_cause_do_dau_question_extracts_a_topic():
    assert _display_topic_from_raw("dau dau do dau") == "dau dau"


def test_ascii_folded_no_connector_cause_question_extracts_the_right_topic():
    assert _display_topic_from_raw("nguyen nhan dau dau la gi") == "dau dau"


def test_ascii_folded_symptom_question_now_extracts_a_topic():
    """Was entirely accented-only before this fix."""
    assert _display_topic_from_raw("trieu chung viem phoi") == "viem phoi"


def test_continuation_shape_still_works_accented():
    assert _display_topic_from_raw("còn viêm gan B thì sao") == "viêm gan B"


def test_continuation_shape_folded_leading_con_no_longer_leaks_into_the_topic():
    """A real, smaller bug found while verifying this fix: the leading
    "còn"/"con" was an ACCENT-ONLY optional prefix, so a fully-folded
    message ("con X thi sao") fell through to the non-greedy capture
    instead of being stripped, leaking "con " into the extracted topic."""
    assert _display_topic_from_raw("con viem gan B thi sao") == "viem gan B"


def test_now_the_two_call_sites_agree_on_the_same_shape():
    """Regression lock for the confirmed drift: orchestrator.py's
    _display_topic_from_raw and follow_up.py's _explicit_topic now both
    read the SAME single pattern tuple -- verified by checking they agree
    on whether a topic shape is recognized at all (their own, separately-
    tuned REJECTION vocabularies can still legitimately differ -- see the
    module docstring -- so this checks pattern-shape agreement, not that
    every output is byte-identical)."""
    message = "còn viêm gan B thì sao"
    assert _display_topic_from_raw(message) is not None
    assert _explicit_topic(message) is not None


def test_bare_pronoun_still_never_becomes_a_topic():
    """False-positive-safety lock (spec's own explicit critical test):
    unchanged behavior, re-verified after the widening above."""
    assert _display_topic_from_raw("Nó có nguy hiểm không?") is None


def test_drug_attribute_question_is_still_rejected_not_a_topic():
    """BUILD-29D.3's own pre-existing regression, re-verified unaffected
    by this widening."""
    assert _display_topic_from_raw("Cong dung cua thuoc Long Huyet la gi") is None


def test_compound_symptom_plus_pronoun_la_gi_tail_is_rejected_not_a_topic():
    """Real bug found via this build's own local E2E script (real model,
    real Postgres, no synthetic test data): "Trieu chung cua no la gi?"
    is a compound sentence -- the SYMPTOM pattern's own capture
    (".+", unlike the cause/definition patterns, which already exclude a
    trailing "la gi" tail from their capture group) swallowed the whole
    remainder "nó là gì" (pronoun + filler), which does not equal any
    single entry in _PRONOUN_ONLY_WORDS, so the bare-pronoun rejection
    silently failed to catch it and "nó là gì" was persisted as
    active_topic -- a corrupted, nonsensical topic string, observed live
    in the E2E's own printed ConversationState. Fixed by stripping a
    trailing "la gi" tail from EVERY pattern's capture before the
    pronoun check runs, not just the patterns whose own regex already
    excludes it."""
    assert _display_topic_from_raw("Triệu chứng của nó là gì?") is None
    assert _display_topic_from_raw("trieu chung cua no la gi") is None


def test_compound_symptom_plus_named_topic_la_gi_tail_extracts_correctly():
    """The same fix also corrects a related, previously-unexposed latent
    bug for a NAMED (non-pronoun) subject: "Triệu chứng của tiểu đường là
    gì?" used to extract "tiểu đường là gì" (the filler words leaking
    into the topic) instead of just "tiểu đường"."""
    assert _display_topic_from_raw("Triệu chứng của tiểu đường là gì?") == "tiểu đường"
