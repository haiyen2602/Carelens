"""TASK-V2.5-004: backend-owned response contracts for the natural renderer.

Contract source: tasks/TASK-V2.5-004-natural-renderer.md muc 4/4a/6 (CP1,
merged PR #189 + corrective PR #191). This module is the STRUCTURAL
guarantee behind the renderer capability -- not a prompt instruction the
model is merely asked to follow:

- ``ResponsePolicy`` says what the model is allowed/forbidden to talk about.
- ``RenderableFactSlots`` carries fact values ALREADY rendered to
  verbatim-safe strings by the backend/template layer -- never raw tool
  payload for the model to reinterpret.
- ``ModelRole.RENDERER`` (gpt-5.6-luna) never sees these fact strings as
  something to reproduce; it only ever produces ``free_prose`` (connective/
  empathy/structuring text). ``assemble_reply`` is the one place a protected
  fact string and free_prose are combined, and it is a deterministic backend
  string composition, not a model call -- Luna structurally cannot rewrite,
  paraphrase, or drop a fact it never saw.

Deliberately minimal for the CP2 scope agreed in CP1 (drug info + schedule +
handoff state only) -- do not add speculative fields for a capability that
doesn't exist yet (V2.5-DESIGN.md's own reuse-boundary decision, CP0 mục 1.3).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from backend.agents.v2.model_gateway import SynthesisEvidence


class Answerability(StrEnum):
    ANSWERABLE = "ANSWERABLE"
    NEED_MORE_INFO = "NEED_MORE_INFO"
    NEED_DOCTOR = "NEED_DOCTOR"


@dataclass(frozen=True)
class ResponsePolicy:
    """Backend-owned: quyen noi gi/cam gi. Khong tu mang fact value
    (V2.5-DESIGN.md muc 5) -- khong chua raw tool payload, patient ID, actor
    ID, raw conversation history, hay prompt instruction tu client."""

    route_category: str
    answerability: Answerability
    allowed_fact_refs: tuple[str, ...]
    prohibited_claim_categories: tuple[str, ...]
    clarification_target: str | None
    handoff_state: str | None
    suggested_action_refs: tuple[str, ...]
    style_profile: str = "soul-v3"  # soul_v3.md, reuse truc tiep (CP0 muc 1.3)


@dataclass(frozen=True)
class RenderableFactSlots:
    """Fact value DA RENDER SAN, dang chuoi verbatim-safe -- khong phai du
    lieu tho dua cho model tu dien giai. Cac field ung voi "protected fact"
    (muc 4a) PHAI duoc backend/template render nguyen van truoc khi toi day;
    model khong bao gio tao lai chinh cac chuoi nay. KHONG duoc copy nguyen
    trang vao log/trace/audit metadata (V2.5-DESIGN.md muc 5). Field toi
    gian cho pham vi CP2 dau (drug info + schedule) -- mo rong them field khi
    co capability moi can, khong suy doan truoc.

    Owner correction (post-CP1): the ENTIRE object -- not just the
    protected-fact fields -- must never reach the renderer model. It is
    consumed only by ``assemble_reply`` (insertion) and ``validate_free_
    prose`` (post-hoc check against the model's own output). The renderer
    call itself receives only ``RendererContext`` below.
    """

    drug_name: str | None = None
    drug_allowed_claims: tuple[str, ...] = ()
    dose_schedule_summary: str | None = None  # da format san, KHONG phai raw DB row
    dose_status_summary: str | None = None
    provenance: str = ""
    # Owner correction: candidate identity strings AN AMBIGUOUS search_drug
    # result considered but did NOT confirm (no server-side unique_match_
    # legacy_drug_id) -- never shown to the model (not part of
    # RendererContext), used only by validate_free_prose to catch the model
    # naming one of them on its own from the request text alone.
    rejected_identity_candidates: tuple[str, ...] = ()


@dataclass(frozen=True)
class RendererContext:
    """Owner correction (post-CP1, replaces the rejected "pass full evidence
    additively" design): the ONLY input the renderer model turn ever
    receives about tool evidence. Allowlisted, LOW-RISK-ONLY -- every field
    here must be safe to show the model regardless of ``ResponsePolicy``,
    because nothing here is itself a claim about a protected fact (drug
    identity, dose time/status, handoff state). Extend this allowlist
    deliberately, one confirmed-safe field at a time -- when unsure whether
    a field is low-risk, it does NOT belong here; it belongs in
    ``RenderableFactSlots`` (verbatim, backend-only) instead.
    """

    has_findings: bool = False


# Protected facts in the "no free-form generation, verbatim-or-nothing"
# class (mục 4a): rendered by assemble_reply in this fixed order, each
# exactly once, only when the corresponding value is present. Extend this
# tuple (never inline a new field elsewhere) when a future capability adds
# another protected fact -- keeps the assembly order single-sourced.
_FACT_SLOT_ORDER: tuple[str, ...] = ("drug_name", "dose_schedule_summary", "dose_status_summary")


def assemble_reply(policy: ResponsePolicy, fact_slots: RenderableFactSlots, free_prose: str) -> str:
    """Deterministic backend string composition (muc 4a) -- NOT a model call.

    ``free_prose`` (Luna's only output) leads; every populated protected
    fact -- ``RenderableFactSlots`` fields in ``_FACT_SLOT_ORDER``, plus
    ``policy.handoff_state`` (mục 6 nhóm 4, lives on ``ResponsePolicy`` since
    it is a policy/state fact, not a drug/schedule fact) -- is appended
    verbatim, one per line, after it. A slot that is ``None``/absent
    contributes nothing; this function never invents, reorders inside, or
    truncates a fact string it was given.
    """

    lines: list[str] = []
    cleaned_prose = (free_prose or "").strip()
    if cleaned_prose:
        lines.append(cleaned_prose)
    for field_name in _FACT_SLOT_ORDER:
        value = getattr(fact_slots, field_name)
        if value:
            lines.append(value)
    if policy.handoff_state:
        lines.append(policy.handoff_state)
    return "\n".join(lines)


def build_renderable_fact_slots(evidence: tuple[SynthesisEvidence, ...]) -> RenderableFactSlots:
    """Thin adapter: convert already-verified ``SynthesisEvidence`` (the
    existing tool-evidence shape ``synthesize_read_only`` has always used)
    into structured, verbatim-safe ``RenderableFactSlots``. CP2-scoped to the
    two tool shapes this capability currently renders (drug lookup, dose
    status) -- extend deliberately, not speculatively, alongside a real new
    fact slot.

    ``search_drug``'s real output shape (``backend.agents.v2.tools.
    SearchDrugOutput``) is ``{items: [...], unique_match_legacy_drug_id}`` --
    NOT a flat ``name`` key (an earlier draft of this adapter read that key
    directly and always found nothing on the real payload; fixed here).
    ``drug_name`` is set ONLY when the server has already confirmed exactly
    one item via ``unique_match_legacy_drug_id`` -- an ambiguous result
    (several items, no confirmed match, or a match id absent from ``items``)
    never sets ``drug_name``; its candidate names go to
    ``rejected_identity_candidates`` instead, purely for
    ``validate_free_prose``'s post-hoc check, never for display.
    ``get_drug_info``'s real output (``field``/``content``/``source`` pairs)
    carries no drug-name field at all, so it is not a ``drug_name`` source
    here.
    """

    drug_name: str | None = None
    dose_status_summary: str | None = None
    provenance = ""
    rejected_identity_candidates: list[str] = []
    for item in evidence:
        data = item.data or {}
        if item.tool_name == "search_drug":
            items = data.get("items")
            unique_id = data.get("unique_match_legacy_drug_id")
            matched_name: str | None = None
            if isinstance(items, list) and isinstance(unique_id, str) and unique_id:
                for candidate in items:
                    if isinstance(candidate, dict) and candidate.get("legacy_drug_id") == unique_id:
                        name = candidate.get("name")
                        if isinstance(name, str) and name.strip():
                            matched_name = name.strip()
                        break
            if matched_name is not None:
                if drug_name is None:
                    drug_name = matched_name
                    provenance = item.provenance
            elif isinstance(items, list):
                # Ambiguous (no confirmed unique match, or the id doesn't
                # resolve to any item) -- never guess an identity; keep
                # candidate names only for the post-hoc validator.
                for candidate in items:
                    if isinstance(candidate, dict):
                        name = candidate.get("name")
                        if isinstance(name, str) and name.strip():
                            rejected_identity_candidates.append(name.strip())
        if dose_status_summary is None and item.tool_name == "get_dose_status":
            status = data.get("status")
            if isinstance(status, str) and status.strip():
                dose_status_summary = status.strip()
                if not provenance:
                    provenance = item.provenance
    return RenderableFactSlots(
        drug_name=drug_name,
        dose_status_summary=dose_status_summary,
        provenance=provenance,
        # dict.fromkeys: dedupe while preserving first-seen order, no set()
        # (order doesn't matter functionally but keeps output deterministic).
        rejected_identity_candidates=tuple(dict.fromkeys(rejected_identity_candidates)),
    )


def build_renderer_context(evidence: tuple[SynthesisEvidence, ...]) -> RendererContext:
    """Adapter mirroring ``build_renderable_fact_slots`` but producing the
    ALLOWLISTED, low-risk-only ``RendererContext`` instead -- this is what
    actually reaches the renderer model's prompt. ``has_findings`` is a
    boolean signal (something vs nothing), never a specific value, so it
    carries no claim-fabrication risk on its own.
    """

    for item in evidence:
        data = item.data or {}
        items = data.get("items")
        if isinstance(items, list):
            if items:
                return RendererContext(has_findings=True)
            continue
        results = data.get("results")
        if isinstance(results, list):
            if results:
                return RendererContext(has_findings=True)
            continue
        # Single-record tool shapes (e.g. get_dose_status) -- any non-empty
        # payload counts as a finding.
        if data:
            return RendererContext(has_findings=True)
    return RendererContext(has_findings=False)


def _normalize_for_match(text: str) -> str:
    """NFC-normalize then casefold -- ONE consistent case/Unicode-handling
    mechanism for every check in ``validate_free_prose`` (PR review
    hardening: an earlier draft mixed this with plain ``re.IGNORECASE`` on
    some patterns -- empirically verified to already handle every Vietnamese
    diacritic letter correctly, so this is not a fix for a live bypass, but
    converging on one mechanism removes any doubt and is free to do).
    ``casefold()`` is also stricter than ``.lower()`` for scripts where they
    diverge (e.g. German ß) -- irrelevant for Vietnamese today but no reason
    to use the weaker one. NFC first so a combining-mark-decomposed string
    (rare, but possible from a different input source) still compares equal
    to its precomposed form.

    Every regex/string constant below is written in already-lowercase
    Vietnamese and is matched ONLY against text this function has already
    normalized -- none of them carry ``re.IGNORECASE``; the normalization
    step is what makes case irrelevant, once, up front.
    """

    return unicodedata.normalize("NFC", text).casefold()


# validate_free_prose: fixed category -> detector mapping. WHICH categories
# apply to a given turn is read from policy.prohibited_claim_categories (the
# real enforced input, not hardcoded here) -- this dict only supplies the
# detector once a category is actually in play for that policy. Every
# detector here receives ALREADY-``_normalize_for_match``-ed text.
# "medication_identity" is handled separately below (it needs fact_slots).
_DOSE_STATUS_MARKERS = re.compile(r"(đã uống|chưa uống|uống rồi|bỏ lỡ)")
_HANDOFF_MARKERS = re.compile(r"(chuyển cho bác sĩ|bác sĩ sẽ liên hệ)")

# dose_time: a bare time-of-day word (sáng/trưa/chiều/tối/giờ) OR a bare
# clock/duration time (PR review correction: "8 giờ", "2h" alone -- an
# appointment time, "cách đây 2h", "đợi 1 giờ" duration/elapsed-time framing)
# is ordinary Vietnamese on its own and must NOT be rejected just for
# containing it -- the original marker regexes were flagging completely
# benign prose. A real dose-time leak needs EITHER of those temporal signals
# actually near a dosing verb (uống/dùng thuốc) -- a real, if fabricated,
# schedule claim -- so both are checked with the same proximity rule.
# "liều" (dose/dosage) stays a bare, unconditional marker -- unlike a
# temporal word/clock time, it is not expected in ordinary connective/
# empathy prose at all, dosing-context or not.
_LIEU_MARKER = re.compile(r"\bliều\b")
_CLOCK_TIME_MARKER = re.compile(r"\b\d{1,2}\s*(giờ|h)\b")
_TIME_OF_DAY_WORD = re.compile(r"\b(giờ|sáng|trưa|chiều|tối)\b")
_DOSING_VERB = re.compile(r"\b(uống|dùng thuốc)\b")
_TIME_WORD_PROXIMITY_WINDOW = 30  # characters either side -- same sentence/clause, not the whole reply


def _dose_time_leak_detected(normalized_text: str) -> bool:
    if _LIEU_MARKER.search(normalized_text):
        return True
    for temporal_pattern in (_CLOCK_TIME_MARKER, _TIME_OF_DAY_WORD):
        for match in temporal_pattern.finditer(normalized_text):
            window = normalized_text[
                max(0, match.start() - _TIME_WORD_PROXIMITY_WINDOW) : match.end() + _TIME_WORD_PROXIMITY_WINDOW
            ]
            if _DOSING_VERB.search(window):
                return True
    return False


_CLAIM_CATEGORY_DETECTORS: dict[str, Callable[[str], bool]] = {
    "dose_time": _dose_time_leak_detected,
    "dose_status": lambda text: bool(_DOSE_STATUS_MARKERS.search(text)),
    "handoff_state": lambda text: bool(_HANDOFF_MARKERS.search(text)),
}


def validate_free_prose(
    policy: ResponsePolicy, fact_slots: RenderableFactSlots, free_prose: str
) -> tuple[bool, tuple[str, ...]]:
    """Regex backstop over LUNA'S OWN OUTPUT -- run BEFORE ``assemble_reply``
    is ever allowed to execute (owner-required second, independent layer:
    ``RendererContext`` already keeps a fact value out of the model's INPUT;
    this catches a model that hallucinates a sensitive claim on its own, or
    echoes one back from the user's own original request text, on the
    OUTPUT side).

    Returns ``(is_valid, violated_categories)``. Only categories present in
    ``policy.prohibited_claim_categories`` are ever checked -- a policy that
    does not list a category cannot fail on it, which is what makes
    ``ResponsePolicy`` a real enforced input here rather than descriptive
    metadata. ``"medication_identity"`` is checked as a verbatim substring
    (case-sensitive: a real proper-noun drug name) against BOTH
    ``fact_slots.drug_name`` (CONFIRMED -- the model was never shown this
    value via ``RendererContext``, but the original request text it does see
    may already name the drug, so it could echo it back) and
    ``fact_slots.rejected_identity_candidates`` (never confirmed) -- there is
    no fixed vocabulary of drug names to pattern-match against otherwise.

    Known, accepted trade-off (V2.5-DESIGN.md mục 8): a plain word-marker
    regex is a coarse backstop, not full semantic validation. This function
    is deliberately over-broad (reject a possibly-innocent turn) rather than
    under-broad (silently let a real leak through) wherever precision and
    recall trade off against each other.

    Every check here -- ``medication_identity``'s substring comparison and
    every regex-based category -- runs against the SAME
    ``_normalize_for_match``-ed text (Unicode NFC + casefold), applied once,
    up front: one consistent case-handling mechanism for the whole function,
    not a mix of ``re.IGNORECASE`` on some patterns and casefold on others.
    """

    normalized_prose = _normalize_for_match(free_prose)
    violations: list[str] = []
    for category in policy.prohibited_claim_categories:
        if category == "medication_identity":
            identity_strings = fact_slots.rejected_identity_candidates
            if fact_slots.drug_name:
                identity_strings = (*identity_strings, fact_slots.drug_name)
            # Owner correction (round 3): Unicode-normalized casefold, not a
            # plain case-sensitive substring check -- Luna writing
            # "paracetamol" for a confirmed "Paracetamol" is still the model
            # naming the identity from the user's own message, and a bare
            # `in` comparison would let that through.
            if any(candidate and _normalize_for_match(candidate) in normalized_prose for candidate in identity_strings):
                violations.append(category)
            continue
        detector = _CLAIM_CATEGORY_DETECTORS.get(category)
        if detector is not None and detector(normalized_prose):
            violations.append(category)
    return not violations, tuple(violations)
