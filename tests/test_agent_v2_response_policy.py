"""TASK-V2.5-004 CP2: RED tests for the new ``response_policy`` module.

Contract source: tasks/TASK-V2.5-004-natural-renderer.md muc 4/4a/6 (merged,
PR #191). This module is the structural guarantee at the heart of the
renderer capability: Luna only ever produces ``free_prose``; every protected
fact (drug_name, dose_schedule_summary, dose_status_summary, ...) is
rendered verbatim by the backend via ``assemble_reply`` -- the model never
sees, and therefore cannot rewrite/paraphrase/drop, the fact strings
themselves. The "prose tu do" golden suite below (muc 6) is the single most
important technical guarantee of V2.5 (V2.5-DESIGN.md muc 8 diem 6).
"""

from __future__ import annotations

import re

import pytest

from backend.agents.v2.model_gateway import SynthesisEvidence
from backend.agents.v2.response_policy import (
    Answerability,
    RenderableFactSlots,
    RendererContext,
    ResponsePolicy,
    assemble_reply,
    build_renderable_fact_slots,
    build_renderer_context,
    validate_free_prose,
)


def _policy(**overrides) -> ResponsePolicy:
    values = dict(
        route_category="drug_information",
        answerability=Answerability.ANSWERABLE,
        allowed_fact_refs=(),
        prohibited_claim_categories=(),
        clarification_target=None,
        handoff_state=None,
        suggested_action_refs=(),
    )
    values.update(overrides)
    return ResponsePolicy(**values)


# ---------------------------------------------------------------------------
# Dataclass shape (mục 4) -- exact contract fields, defaults per the merged
# corrections (style_profile default "soul-v3", not the original "soul-v1").
# ---------------------------------------------------------------------------


def test_response_policy_defaults_style_profile_to_soul_v3():
    policy = _policy()
    assert policy.style_profile == "soul-v3"


def test_response_policy_is_frozen():
    policy = _policy()
    with pytest.raises(Exception):
        policy.route_category = "other"  # type: ignore[misc]


def test_renderable_fact_slots_all_fields_default_none_or_empty():
    slots = RenderableFactSlots()
    assert slots.drug_name is None
    assert slots.drug_allowed_claims == ()
    assert slots.dose_schedule_summary is None
    assert slots.dose_status_summary is None
    assert slots.provenance == ""


def test_renderable_fact_slots_is_frozen():
    slots = RenderableFactSlots(drug_name="Paracetamol")
    with pytest.raises(Exception):
        slots.drug_name = "Other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# assemble_reply -- backend-side deterministic string composition (mục 4a).
# ---------------------------------------------------------------------------


def test_assemble_reply_with_no_facts_returns_free_prose_unchanged():
    slots = RenderableFactSlots()
    text = assemble_reply(_policy(), slots, "Chao ban, minh co the giup gi them khong?")
    assert text == "Chao ban, minh co the giup gi them khong?"


def test_assemble_reply_inserts_drug_name_verbatim():
    slots = RenderableFactSlots(drug_name="Paracetamol 500mg")
    text = assemble_reply(_policy(), slots, "Day la thong tin ban can biet.")
    assert "Paracetamol 500mg" in text
    assert text.startswith("Day la thong tin ban can biet.")


def test_assemble_reply_inserts_dose_schedule_summary_verbatim():
    slots = RenderableFactSlots(dose_schedule_summary="08:00 va 20:00 hang ngay")
    text = assemble_reply(_policy(), slots, "Lich uong thuoc cua ban nhu sau.")
    assert "08:00 va 20:00 hang ngay" in text


def test_assemble_reply_inserts_dose_status_summary_verbatim():
    slots = RenderableFactSlots(dose_status_summary="Da uong lieu 8 gio sang")
    text = assemble_reply(_policy(), slots, "Cap nhat tinh trang lieu thuoc cua ban.")
    assert "Da uong lieu 8 gio sang" in text


def test_assemble_reply_never_calls_free_prose_a_full_sentence_alone_when_facts_exist():
    """Regression lock for the assembly mechanism itself (mục 6 nhóm dương):
    a fact string must appear intact, not truncated/merged into free_prose's
    own punctuation."""
    slots = RenderableFactSlots(drug_name="Amoxicillin 250mg", dose_schedule_summary="3 lan/ngay")
    text = assemble_reply(_policy(), slots, "Ban hoi ve thuoc nay.")
    assert "Amoxicillin 250mg" in text
    assert "3 lan/ngay" in text


def test_assemble_reply_empty_free_prose_still_renders_facts():
    slots = RenderableFactSlots(drug_name="Vitamin C")
    text = assemble_reply(_policy(), slots, "")
    assert "Vitamin C" in text


# ---------------------------------------------------------------------------
# build_renderable_fact_slots -- thin adapter from existing SynthesisEvidence.
# ---------------------------------------------------------------------------


def test_build_renderable_fact_slots_from_search_drug_evidence_sets_drug_name():
    """Real search_drug output shape (backend/agents/v2/tools.py::
    SearchDrugOutput): {items: [DrugSearchItem...], unique_match_
    legacy_drug_id}. drug_name is set ONLY from the item the SERVER already
    confirmed unique -- never merely "the first item" or a flat top-level
    "name" key (that key never exists on the real payload)."""
    evidence = (
        SynthesisEvidence(
            tool_name="search_drug",
            provenance="canonical-drug-v2",
            data={
                "items": [
                    {"legacy_drug_id": "drug-1", "name": "Paracetamol", "dosage_form": "vien nen", "route": "uong", "strength": "500mg"}
                ],
                "unique_match_legacy_drug_id": "drug-1",
            },
        ),
    )
    slots = build_renderable_fact_slots(evidence)
    assert slots.drug_name == "Paracetamol"
    assert slots.provenance == "canonical-drug-v2"
    assert slots.rejected_identity_candidates == ()


def test_build_renderable_fact_slots_ambiguous_search_drug_items_sets_no_identity_slot():
    """Adversarial invariant (owner-required): an ambiguous search_drug
    result (several items, no server-confirmed unique_match_legacy_drug_id)
    must NEVER populate drug_name -- the candidate names are kept only in
    rejected_identity_candidates (never shown to the model; used only by
    validate_free_prose's post-hoc check on the model's own output)."""
    evidence = (
        SynthesisEvidence(
            tool_name="search_drug",
            provenance="canonical-drug-v2",
            data={
                "items": [
                    {"legacy_drug_id": "drug-1", "name": "Vitamin B1", "dosage_form": "vien nen", "route": "uong", "strength": "100mg"},
                    {"legacy_drug_id": "drug-2", "name": "Vitamin B1 Complex", "dosage_form": "vien nen", "route": "uong", "strength": "250mg"},
                ],
                "unique_match_legacy_drug_id": None,
            },
        ),
    )
    slots = build_renderable_fact_slots(evidence)
    assert slots.drug_name is None
    assert set(slots.rejected_identity_candidates) == {"Vitamin B1", "Vitamin B1 Complex"}


def test_build_renderable_fact_slots_unique_match_not_present_in_items_is_treated_as_ambiguous():
    """Defensive: a unique_match_legacy_drug_id that doesn't actually match
    any item's legacy_drug_id (malformed/unexpected payload) must fail
    closed to "no identity", never guess."""
    evidence = (
        SynthesisEvidence(
            tool_name="search_drug",
            provenance="canonical-drug-v2",
            data={
                "items": [{"legacy_drug_id": "drug-1", "name": "Paracetamol", "dosage_form": "vien nen", "route": "uong", "strength": "500mg"}],
                "unique_match_legacy_drug_id": "drug-does-not-exist",
            },
        ),
    )
    slots = build_renderable_fact_slots(evidence)
    assert slots.drug_name is None


def test_build_renderable_fact_slots_from_empty_evidence_is_all_empty():
    slots = build_renderable_fact_slots(())
    assert slots.drug_name is None
    assert slots.dose_schedule_summary is None
    assert slots.dose_status_summary is None
    assert slots.rejected_identity_candidates == ()


# ---------------------------------------------------------------------------
# Golden suite "prose tu do" -- 4 nhom AM (mục 6). Each: renderer given a
# RenderableFactSlots WITHOUT field X -- assembled output must never contain
# a claim of type X anywhere, including in free_prose itself. Since this is
# free prose (not a fixed template), a deterministic regex/phrase blocklist
# is the backstop filter (V2.5-DESIGN.md mục 8: not a full semantic
# guarantee) -- but the STRUCTURAL guarantee (mục 4a) is what this whole test
# group is really locking: assemble_reply() never fabricates a fact string on
# its own, it only ever inserts what RenderableFactSlots was actually given.
# ---------------------------------------------------------------------------

_DOSE_TIME_MARKERS = re.compile(r"\b(giờ|sáng|trưa|chiều|tối|liều)\b", re.IGNORECASE)
_DOSE_STATUS_MARKERS = re.compile(r"(đã uống|chưa uống|uống rồi|bỏ lỡ)", re.IGNORECASE)
_HANDOFF_MARKERS = re.compile(r"(chuyển cho bác sĩ|bác sĩ sẽ liên hệ)", re.IGNORECASE)


def test_golden_negative_no_dose_schedule_injected_when_field_is_none():
    """Nhom 1: dose_schedule_summary=None -- assemble_reply must not invent
    any dose-time claim itself. (It cannot inject what it wasn't given --
    this test locks that assemble_reply is purely additive, never
    generative, over the fact fields.)"""
    slots = RenderableFactSlots(dose_schedule_summary=None)
    text = assemble_reply(_policy(), slots, "Ban co the tham khao them thong tin ve thuoc nay.")
    assert not _DOSE_TIME_MARKERS.search(text)


def test_golden_negative_no_dose_status_injected_when_field_is_none():
    """Nhom 2: dose_status_summary=None."""
    slots = RenderableFactSlots(dose_status_summary=None)
    text = assemble_reply(_policy(), slots, "Ban co the tham khao them thong tin ve thuoc nay.")
    assert not _DOSE_STATUS_MARKERS.search(text)


def test_golden_negative_no_medication_identity_injected_when_field_is_none():
    """Nhom 3: drug_name=None -- assemble_reply must not name any drug."""
    slots = RenderableFactSlots(drug_name=None)
    text = assemble_reply(_policy(), slots, "Day la thong tin ban hoi.")
    assert "Paracetamol" not in text and "Amoxicillin" not in text


def test_golden_negative_no_handoff_state_injected_when_field_is_none():
    """Nhom 4: handoff_state=None -- assemble_reply must never claim a
    doctor handoff happened/will happen on its own."""
    slots = RenderableFactSlots()
    text = assemble_reply(_policy(handoff_state=None), slots, "Cam on ban da hoi.")
    assert not _HANDOFF_MARKERS.search(text)


# ---------------------------------------------------------------------------
# Golden suite "prose tu do" -- 4 nhom DUONG (bổ sung theo sửa lỗi CP1): khi
# slot CO gia tri, chuoi do phai xuat hien NGUYEN VAN trong reply cuoi cung,
# khong bi rewrite. Guong doi voi 4 nhom am o tren.
# ---------------------------------------------------------------------------


def test_golden_positive_dose_schedule_summary_appears_verbatim_when_present():
    slots = RenderableFactSlots(dose_schedule_summary="08:00 sang va 20:00 toi hang ngay")
    text = assemble_reply(_policy(), slots, "Lich uong thuoc cua ban:")
    assert "08:00 sang va 20:00 toi hang ngay" in text


def test_golden_positive_dose_status_summary_appears_verbatim_when_present():
    slots = RenderableFactSlots(dose_status_summary="Da uong lieu 8 gio sang, chua uong lieu 8 gio toi")
    text = assemble_reply(_policy(), slots, "Cap nhat cho ban:")
    assert "Da uong lieu 8 gio sang, chua uong lieu 8 gio toi" in text


def test_golden_positive_drug_name_appears_verbatim_when_present():
    slots = RenderableFactSlots(drug_name="Snapcef 16mg/10ml")
    text = assemble_reply(_policy(), slots, "Ban dang hoi ve thuoc nay:")
    assert "Snapcef 16mg/10ml" in text


def test_golden_positive_handoff_state_appears_verbatim_when_present():
    slots = RenderableFactSlots()
    policy = _policy(handoff_state="Da chuyen cho bac si xem xet ngay")
    text = assemble_reply(policy, slots, "Cam on ban da bao.")
    assert "Da chuyen cho bac si xem xet ngay" in text


# ---------------------------------------------------------------------------
# RendererContext -- allowlisted, LOW-RISK-ONLY input for Luna's free_prose
# generation (owner correction: replaces the rejected "pass full evidence
# additively" design). Every field here must be safe to show the model
# regardless of ResponsePolicy; a protected fact value (drug identity, dose
# time/status, handoff state) must NEVER appear here, whether the
# corresponding slot is populated or not.
# ---------------------------------------------------------------------------


def test_renderer_context_has_findings_true_when_search_drug_returns_items():
    evidence = (
        SynthesisEvidence(
            tool_name="search_drug",
            provenance="canonical-drug-v2",
            data={"items": [{"legacy_drug_id": "drug-1", "name": "Paracetamol", "dosage_form": "vien nen", "route": "uong"}], "unique_match_legacy_drug_id": "drug-1"},
        ),
    )
    context = build_renderer_context(evidence)
    assert context.has_findings is True


def test_renderer_context_has_findings_false_when_search_drug_returns_no_items():
    evidence = (
        SynthesisEvidence(tool_name="search_drug", provenance="canonical-drug-v2", data={"items": [], "unique_match_legacy_drug_id": None}),
    )
    context = build_renderer_context(evidence)
    assert context.has_findings is False


def test_renderer_context_has_findings_false_for_no_evidence_at_all():
    assert build_renderer_context(()).has_findings is False


def test_renderer_context_never_carries_any_field_shaped_like_a_protected_fact():
    """Structural lock on the dataclass shape itself: RendererContext must
    never grow a field whose name matches a RenderableFactSlots protected
    field -- a future edit adding e.g. `drug_name` to RendererContext by
    mistake (instead of leaving it in RenderableFactSlots only) is exactly
    the class of regression this test exists to catch."""
    protected_field_names = {f for f in RenderableFactSlots.__dataclass_fields__ if f != "provenance"}
    context_field_names = set(RendererContext.__dataclass_fields__)
    assert not (protected_field_names & context_field_names)


# ---------------------------------------------------------------------------
# validate_free_prose -- regex backstop over LUNA'S OWN OUTPUT, run before
# assemble_reply is ever allowed to execute. Independent of the input-side
# guarantee above (RendererContext never carries a fact value): this catches
# a model that hallucinates a sensitive claim on its own, from nothing.
# policy.prohibited_claim_categories is the REAL enforced input here -- the
# category->regex mapping is fixed internally, but WHICH categories apply to
# a given turn is read from the policy the caller supplies, not hardcoded.
# ---------------------------------------------------------------------------

_ALL_PROTECTED_CATEGORIES = ("dose_time", "dose_status", "medication_identity", "handoff_state")


def test_validate_free_prose_passes_clean_generic_prose():
    policy = _policy(prohibited_claim_categories=_ALL_PROTECTED_CATEGORIES)
    ok, violations = validate_free_prose(policy, RenderableFactSlots(), "Cam on ban da hoi, minh xin chia se thong tin sau.")
    assert ok is True
    assert violations == ()


def test_validate_free_prose_rejects_dose_time_claim_when_prohibited():
    """Adversarial: the model hallucinates a specific time even though it
    was never given one (RendererContext carries no such value) -- must be
    rejected, not silently passed through to assemble_reply."""
    policy = _policy(prohibited_claim_categories=_ALL_PROTECTED_CATEGORIES)
    ok, violations = validate_free_prose(policy, RenderableFactSlots(), "Bạn nên uống vào lúc 8 giờ sáng.")
    assert ok is False
    assert "dose_time" in violations


def test_validate_free_prose_rejects_dose_status_claim_when_prohibited():
    policy = _policy(prohibited_claim_categories=_ALL_PROTECTED_CATEGORIES)
    ok, violations = validate_free_prose(policy, RenderableFactSlots(), "Bạn đã uống liều này rồi.")
    assert ok is False
    assert "dose_status" in violations


def test_validate_free_prose_rejects_handoff_claim_when_prohibited():
    policy = _policy(prohibited_claim_categories=_ALL_PROTECTED_CATEGORIES)
    ok, violations = validate_free_prose(policy, RenderableFactSlots(), "Mình đã chuyển cho bác sĩ rồi nhé.")
    assert ok is False
    assert "handoff_state" in violations


def test_validate_free_prose_rejects_a_rejected_identity_candidate_mentioned_verbatim():
    """Adversarial invariant (owner-required): the model names one of the
    AMBIGUOUS candidates search_drug returned (never confirmed, never shown
    to the model as fact_slots.drug_name) -- must be rejected."""
    policy = _policy(prohibited_claim_categories=_ALL_PROTECTED_CATEGORIES)
    slots = RenderableFactSlots(rejected_identity_candidates=("Vitamin B1", "Vitamin B1 Complex"))
    ok, violations = validate_free_prose(policy, slots, "Day chinh la Vitamin B1 ban can.")
    assert ok is False
    assert "medication_identity" in violations


def test_validate_free_prose_rejects_a_confirmed_drug_name_mentioned_by_the_model():
    """Adversarial invariant (owner-required, round 2): fact_slots.drug_name
    is NEVER shown to the model via RendererContext, but the model still
    sees the user's own ORIGINAL request text (which may already name the
    drug, e.g. "Paracetamol dùng để làm gì?") and could echo it back in
    free_prose. Even a CONFIRMED identity must never be restated by the
    model itself -- assemble_reply is the only place it may appear; if the
    model also says it, that is exactly the paraphrase/restate risk mục 4a
    exists to eliminate."""
    policy = _policy(prohibited_claim_categories=_ALL_PROTECTED_CATEGORIES)
    slots = RenderableFactSlots(drug_name="Paracetamol")
    ok, violations = validate_free_prose(policy, slots, "Paracetamol la mot lua chon pho bien.")
    assert ok is False
    assert "medication_identity" in violations


def test_validate_free_prose_rejects_a_confirmed_drug_name_mentioned_in_lowercase():
    """Adversarial invariant (owner-required, round 3): the match must be
    case-insensitive (Unicode-normalized casefold, not a plain substring
    check) -- Luna writing "paracetamol" for fact_slots.drug_name=
    "Paracetamol" is still the model naming the identity from the user's own
    message, and a case-sensitive comparison would let it through."""
    policy = _policy(prohibited_claim_categories=_ALL_PROTECTED_CATEGORIES)
    slots = RenderableFactSlots(drug_name="Paracetamol")
    ok, violations = validate_free_prose(policy, slots, "paracetamol la mot lua chon pho bien.")
    assert ok is False
    assert "medication_identity" in violations


def test_validate_free_prose_rejects_a_rejected_identity_candidate_mentioned_in_lowercase():
    policy = _policy(prohibited_claim_categories=_ALL_PROTECTED_CATEGORIES)
    slots = RenderableFactSlots(rejected_identity_candidates=("Vitamin B1",))
    ok, violations = validate_free_prose(policy, slots, "day co the la vitamin b1 ban can.")
    assert ok is False
    assert "medication_identity" in violations


def test_validate_free_prose_allows_prose_naming_neither_confirmed_nor_rejected_identity():
    """Non-regression: prose that never mentions any known identity string
    (confirmed or rejected) must not be flagged."""
    policy = _policy(prohibited_claim_categories=_ALL_PROTECTED_CATEGORIES)
    slots = RenderableFactSlots(drug_name="Paracetamol", rejected_identity_candidates=("Vitamin B1",))
    ok, violations = validate_free_prose(policy, slots, "Cam on ban da hoi, day la thong tin ban can.")
    assert ok is True
    assert violations == ()


def test_validate_free_prose_allows_a_category_when_policy_does_not_prohibit_it():
    """ResponsePolicy is a REAL enforced input, not descriptive metadata: a
    policy that does not list a category at all must not reject it, proving
    validate_free_prose reads the category set from the policy argument
    rather than a hardcoded always-on list."""
    policy = _policy(prohibited_claim_categories=())
    ok, violations = validate_free_prose(policy, RenderableFactSlots(), "Bạn nên uống vào lúc 8 giờ sáng.")
    assert ok is True
    assert violations == ()


def test_validate_free_prose_allows_a_benign_time_of_day_phrase_with_no_dosing_context():
    """Owner correction: a bare time-of-day word (sáng/trưa/chiều/tối/giờ)
    with no dosing verb nearby is completely ordinary Vietnamese -- rejecting
    it would fail the renderer on totally normal prose. dose_time now
    requires either a specific clock time (e.g. "8 giờ") or a time-of-day
    word actually near a dosing verb (uống/dùng thuốc) -- not just the bare
    word anywhere in the text."""
    policy = _policy(prohibited_claim_categories=_ALL_PROTECTED_CATEGORIES)
    ok, violations = validate_free_prose(policy, RenderableFactSlots(), "Chúc bạn một buổi tối tốt lành.")
    assert ok is True
    assert violations == ()


def test_validate_free_prose_rejects_a_time_of_day_word_near_a_dosing_verb_even_without_a_clock_time():
    """Adversarial: no specific clock time, but a time-of-day word appears
    close to a dosing verb -- this IS a real (fabricated) schedule claim,
    must still be rejected even without a bare digit-based time."""
    policy = _policy(prohibited_claim_categories=_ALL_PROTECTED_CATEGORIES)
    ok, violations = validate_free_prose(policy, RenderableFactSlots(), "Bạn cần uống thuốc mỗi tối trước khi ngủ.")
    assert ok is False
    assert "dose_time" in violations


def test_validate_free_prose_rejects_a_bare_clock_time_even_without_a_nearby_dosing_verb():
    policy = _policy(prohibited_claim_categories=_ALL_PROTECTED_CATEGORIES)
    ok, violations = validate_free_prose(policy, RenderableFactSlots(), "Hẹn gặp bạn lúc 8 giờ nhé.")
    assert ok is False
    assert "dose_time" in violations


def test_validate_free_prose_rejects_bare_lieu_word_regardless_of_context():
    """"liều" (dose) is specific enough on its own -- unlike the generic
    time-of-day words, it is not expected in ordinary connective prose."""
    policy = _policy(prohibited_claim_categories=_ALL_PROTECTED_CATEGORIES)
    ok, violations = validate_free_prose(policy, RenderableFactSlots(), "Đây là liều bạn cần biết.")
    assert ok is False
    assert "dose_time" in violations
