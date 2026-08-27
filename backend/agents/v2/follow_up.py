"""BUILD-43: deterministic conversation follow-up taxonomy (CANDIDATE-02 fix).

Replaces the brittle ``len(message.strip()) <= 35`` heuristic
(``_follow_up_category``, orchestrator.py) and the memory-text-regex-based
``resolve_conversation_context`` it powered. That old mechanism re-derived
"the current topic" by regex-scanning raw short-term MEMORY TEXT
(``_recent_topic``/``_extract_topic`` over recent user turns) -- entirely
independent of the DURABLE, canonical ``ConversationState.active_topic``/
``active_entity`` fields BUILD-29D/BUILD-42 already established as
authoritative. This module fixes both problems at once: it classifies off
the canonical prior state (never raw memory text), and it never uses
message length as the deciding signal -- ``SHORT != FOLLOW_UP``.

No model call. Every decision comes from observable structure: an explicit
new topic/entity name, deictic/ellipsis markers, attribute-only phrasing
(a drug/topic aspect keyword with no named subject of its own), and the
canonical prior state passed in by the caller.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "FollowUpCategory",
    "FollowUpDecision",
    "FollowUpReasonCode",
    "classify_follow_up",
]


class FollowUpCategory(StrEnum):
    TRUE_FOLLOWUP = "TRUE_FOLLOWUP"
    STANDALONE_QUESTION = "STANDALONE_QUESTION"
    TOPIC_SWITCH = "TOPIC_SWITCH"
    AMBIGUOUS_FRAGMENT = "AMBIGUOUS_FRAGMENT"


class FollowUpReasonCode(StrEnum):
    """Observable evidence the decision was based on -- never a model's
    stated confidence/reasoning (SS4: "do NOT expose hidden reasoning")."""

    EXPLICIT_TOPIC_NO_PRIOR_CONTEXT = "EXPLICIT_TOPIC_NO_PRIOR_CONTEXT"
    EXPLICIT_TOPIC_MATCHES_PRIOR = "EXPLICIT_TOPIC_MATCHES_PRIOR"
    EXPLICIT_TOPIC_DIFFERS_FROM_PRIOR = "EXPLICIT_TOPIC_DIFFERS_FROM_PRIOR"
    NAMED_SUBJECT_NO_PRIOR_CONTEXT = "NAMED_SUBJECT_NO_PRIOR_CONTEXT"
    NAMED_SUBJECT_MATCHES_PRIOR_ENTITY = "NAMED_SUBJECT_MATCHES_PRIOR_ENTITY"
    NAMED_SUBJECT_DIFFERS_FROM_PRIOR = "NAMED_SUBJECT_DIFFERS_FROM_PRIOR"
    DEICTIC_OR_ATTRIBUTE_ONLY_WITH_PRIOR_CONTEXT = "DEICTIC_OR_ATTRIBUTE_ONLY_WITH_PRIOR_CONTEXT"
    DEICTIC_OR_ATTRIBUTE_ONLY_NO_PRIOR_CONTEXT = "DEICTIC_OR_ATTRIBUTE_ONLY_NO_PRIOR_CONTEXT"


@dataclass(frozen=True)
class FollowUpDecision:
    category: FollowUpCategory
    inherited_topic: bool
    inherited_entity: bool
    reason_code: FollowUpReasonCode
    evidence_source: str


# ---------------------------------------------------------------------------
# Evidence vocabulary -- deterministic markers only, never a phrase-by-phrase
# patch for specific failing strings (SS21). Extends the pre-existing
# _FOLLOW_UP_MARKERS/_AMBIGUOUS_FOLLOW_UP_MARKERS vocabulary from
# orchestrator.py with pronoun/deictic forms explicitly named in the spec
# ("thuốc này", "cái này") that the old marker list did not carry.
# ---------------------------------------------------------------------------

_DEICTIC_MARKERS = (
    "con", "thi sao", "the nao", "vay", "no", "cua no",
    "cai nay", "cai do", "cai kia", "benh nay", "thuoc nay",
    "loai nay", "loai kia", "loai do",
)

# Fragment-only words: unlike the compound "loại này/kia/đó" forms above
# (already unambiguous anaphora), a BARE "loại" ("type/kind of") next to
# nothing but a dosage/strength number ("loại 500mg?") is still a fragment
# referring to an unstated entity -- but "loại" on its own can also appear
# inside a genuinely self-sufficient question ("loại thuốc nào trị đau đầu
# an toàn?"), so it is stripped only from the REMAINDER measurement (never
# used to force has_deictic=True), alongside bare dosage/strength tokens.
_FRAGMENT_ONLY_WORDS = ("loai",)
_DOSAGE_TOKEN_RE = re.compile(r"\b\d+\s*(?:mg|ml|mcg|g|iu)\b")

# Reused, not reinvented: the union of the same drug-attribute-aspect
# vocabulary already defined for the typed-alias mechanism
# (conversation_state.py's DRUG_ACTION_VALUES aliases) and the topic-aspect
# vocabulary already defined for follow-up query building
# (orchestrator.py's own _FOLLOW_UP_CATEGORY_KEYWORDS -- urgent_care/cause/
# symptoms/danger/prevention), flattened into one ascii-folded set. An
# attribute keyword alone ("tác dụng phụ thì sao?", "khi nào cần đi khám
# ngay?") names WHAT ASPECT is being asked about, never WHO/WHAT it is
# about -- it can never by itself make a message self-sufficient.
_ATTRIBUTE_KEYWORDS = (
    "dinh nghia", "nguyen nhan", "trieu chung", "dau hieu", "dieu tri",
    "phong ngua", "phong tranh", "nguy hiem", "chan doan", "theo doi",
    "cong dung", "chi dinh", "lieu dung", "cach dung", "tac dung phu",
    "chong chi dinh", "luu y", "canh bao", "tuong tac", "di kham",
    "kham ngay", "cap cuu", "thanh phan", "di vien", "nang khong", "tranh",
    "do dau", "tai sao", "truoc an", "sau an", "uong truoc", "uong sau",
)

# Question particles / fillers / pure function words with no subject content
# of their own -- must be stripped before measuring whether meaningful
# subject text remains. Vietnamese-only, deterministic (grammatical
# particles, pronouns, question words, common helper verbs); never a
# specific topic/entity name, so stripping these can narrow a fragment down
# to nothing but can never erase a genuine subject's own content words.
_QUESTION_PARTICLES = (
    "co", "khong", "gi", "la", "a", "nhe", "vay", "ha", "sao", "nhu",
    "duoc", "hay", "thi", "the", "ma", "nhi", "ay", "cua", "cach", "khi",
    "nao", "toi", "can", "muon", "biet", "hoi", "nen", "bao", "gio", "di",
    "khac",
)

_PRONOUN_ONLY_WORDS = frozenset({"no", "do", "nay", "kia", "cai nay", "cai do", "cai kia"})


def _ascii_fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    folded = "".join(char for char in decomposed if not unicodedata.combining(char))
    return folded.replace("đ", "d").replace("Đ", "d")


def _explicit_topic(message: str) -> str | None:
    """A disease/topic name in an explicit, self-contained question shape.

    BUILD-45 Candidate B: ``_DISPLAY_TOPIC_PATTERNS`` used to be
    independently re-defined here too -- a second, separately-maintained
    copy of orchestrator.py's own tuple that had ALREADY drifted from it
    (confirmed by real audit, not assumed: orchestrator.py's copy once had
    a "con X thi sao" shape this one lacked). Now imported directly from
    the single canonical source (a function-local import -- orchestrator.py
    imports FROM this module at ITS OWN module level, so importing back
    from it here at module level would be a genuine circular import;
    deferring to call time breaks that safely). This function's own
    REJECTION logic below (``_ATTRIBUTE_KEYWORDS``/``_PRONOUN_ONLY_WORDS``)
    is deliberately NOT shared with orchestrator.py's own
    ``_display_topic_from_raw`` -- the two have intentionally different,
    independently-tuned rejection vocabularies for their own call sites,
    and unifying THAT (not just the pattern shapes) would risk changing
    this safety-adjacent classifier's own decisions without the extensive
    re-verification such a change would need.
    """
    from backend.agents.v2.orchestrator import _DISPLAY_TOPIC_PATTERNS

    candidate = message.strip(" ?!.,;:")
    for pattern in _DISPLAY_TOPIC_PATTERNS:
        match = pattern.match(candidate)
        if match is None:
            continue
        topic = match.group(1).strip(" ?!.,;:")
        if len(topic) < 2:
            continue
        folded = _ascii_fold(topic)
        if any(keyword in folded for keyword in _ATTRIBUTE_KEYWORDS):
            continue
        # A pronoun/demonstrative captured as the "topic" (e.g. "Triệu
        # chứng của NÓ?") is a deictic reference, never an explicit new
        # subject -- falls through to the deictic/attribute-only case
        # instead, same as "Thuốc này..." already does.
        if folded in _PRONOUN_ONLY_WORDS:
            continue
        # BUILD-45 Candidate B: a topic CONTAINING a deictic word (e.g.
        # "Bệnh này" -> "benh nay", already one of _DEICTIC_MARKERS' own
        # entries) is just as much a reference to the PRIOR topic as a
        # bare pronoun is -- the check above only ever caught a topic that
        # IS wholly a pronoun, never one that merely contains one. Exposed
        # by widening _DISPLAY_TOPIC_PATTERNS (a new cause-shaped pattern
        # now matches "Bệnh này do đâu?", which the narrower pre-BUILD-45
        # pattern set never did) -- confirmed as a real, pre-existing gap
        # in this function's own rejection logic, not a new one this
        # build introduces; found via the existing BUILD-43 regression
        # suite itself catching it, not assumed safe.
        if _has_deictic_marker(folded):
            continue
        return topic
    return None


def _has_deictic_marker(folded: str) -> bool:
    return any(_contains_word(folded, marker) for marker in _DEICTIC_MARKERS)


def _contains_word(folded: str, marker: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", folded) is not None


def _strip_evidence_markers(folded: str) -> str:
    """Remove deictic markers, attribute keywords, and question particles.

    What remains is the closest deterministic signal this module has for
    "does the message name its own subject" -- never a model guess.
    """
    remainder = _DOSAGE_TOKEN_RE.sub(" ", folded)
    for marker in sorted((*_DEICTIC_MARKERS, *_ATTRIBUTE_KEYWORDS, *_FRAGMENT_ONLY_WORDS), key=len, reverse=True):
        remainder = re.sub(rf"(?<!\w){re.escape(marker)}(?!\w)", " ", remainder)
    tokens = [
        stripped
        for tok in remainder.split()
        for stripped in (tok.strip("?!.,;:"),)
        if stripped and stripped not in _QUESTION_PARTICLES
    ]
    return " ".join(tokens)


def _mentions(folded_haystack: str, needle: str | None) -> bool:
    if not needle:
        return False
    folded_needle = _ascii_fold(needle).strip()
    if not folded_needle:
        return False
    return folded_needle in folded_haystack


def _same_topic(topic_a: str | None, topic_b: str | None) -> bool:
    if not topic_a or not topic_b:
        return False
    return _ascii_fold(topic_a).strip() == _ascii_fold(topic_b).strip()


def classify_follow_up(
    message: str,
    *,
    prior_topic: str | None,
    prior_entity_name: str | None,
) -> FollowUpDecision:
    """Classify one turn's dependency on prior conversation context.

    ``prior_topic``/``prior_entity_name`` MUST be the canonical
    ``ConversationState.active_topic``/``active_entity`` display names as of
    BEFORE this turn -- never raw memory text, never a retrieval query (see
    module docstring; this is invariant #5 in the BUILD-43 spec:
    "retrieval_query must NEVER overwrite canonical topic/entity", which
    this function's own input contract enforces by construction: it never
    receives a retrieval query at all).
    """
    folded = _ascii_fold(message)
    prior_context_exists = bool(prior_topic or prior_entity_name)

    explicit_topic = _explicit_topic(message)
    has_deictic = _has_deictic_marker(folded)
    remainder = _strip_evidence_markers(folded)
    has_named_subject = bool(explicit_topic) or len(remainder) >= 2

    # Case 1: the message names its own explicit disease/topic subject.
    if explicit_topic is not None:
        if not prior_context_exists:
            return FollowUpDecision(
                FollowUpCategory.STANDALONE_QUESTION, False, False,
                FollowUpReasonCode.EXPLICIT_TOPIC_NO_PRIOR_CONTEXT, "display_topic_pattern",
            )
        if _same_topic(explicit_topic, prior_topic):
            return FollowUpDecision(
                FollowUpCategory.STANDALONE_QUESTION, True, False,
                FollowUpReasonCode.EXPLICIT_TOPIC_MATCHES_PRIOR, "display_topic_pattern",
            )
        return FollowUpDecision(
            FollowUpCategory.TOPIC_SWITCH, False, False,
            FollowUpReasonCode.EXPLICIT_TOPIC_DIFFERS_FROM_PRIOR, "display_topic_pattern",
        )

    # Case 2: no explicit topic pattern, but the message still names a
    # subject beyond deictic/attribute/particle/dosage-number filler (e.g. a
    # drug name the router itself recognized, or a disease phrasing the
    # narrow pattern family above does not happen to cover). A pure
    # interrogative marker ("thế nào"/"vậy") attached to a real named
    # subject ("Amoxicillin dùng thế nào?") does not itself create a
    # dependency -- only the ANAPHORIC/demonstrative markers folded into
    # ``remainder`` above (which strip nothing of a real subject) do; a
    # true fragment always reduces ``remainder`` to nothing regardless of
    # whether it happens to also contain one of those interrogative words.
    if has_named_subject:
        if not prior_context_exists:
            return FollowUpDecision(
                FollowUpCategory.STANDALONE_QUESTION, False, False,
                FollowUpReasonCode.NAMED_SUBJECT_NO_PRIOR_CONTEXT, "named_subject",
            )
        if _mentions(folded, prior_entity_name) or _mentions(folded, prior_topic):
            return FollowUpDecision(
                FollowUpCategory.STANDALONE_QUESTION, False, bool(prior_entity_name),
                FollowUpReasonCode.NAMED_SUBJECT_MATCHES_PRIOR_ENTITY, "named_subject",
            )
        return FollowUpDecision(
            FollowUpCategory.TOPIC_SWITCH, False, False,
            FollowUpReasonCode.NAMED_SUBJECT_DIFFERS_FROM_PRIOR, "named_subject",
        )

    # Case 3: deictic reference and/or attribute-only phrasing -- names no
    # subject of its own. Only safely resolvable with prior context.
    if prior_context_exists:
        return FollowUpDecision(
            FollowUpCategory.TRUE_FOLLOWUP,
            inherited_topic=bool(prior_topic) and not bool(prior_entity_name),
            inherited_entity=bool(prior_entity_name),
            reason_code=FollowUpReasonCode.DEICTIC_OR_ATTRIBUTE_ONLY_WITH_PRIOR_CONTEXT,
            evidence_source="deictic_marker" if has_deictic else "attribute_only",
        )
    return FollowUpDecision(
        FollowUpCategory.AMBIGUOUS_FRAGMENT, False, False,
        FollowUpReasonCode.DEICTIC_OR_ATTRIBUTE_ONLY_NO_PRIOR_CONTEXT,
        "deictic_marker" if has_deictic else "attribute_only",
    )
