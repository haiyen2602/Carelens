"""BUILD-45 Candidate A: cold drug entity binding.

Root cause (confirmed by real code read, not assumed): ``_resolved_drug_
entity`` (agent_v2_routes.py) only ever promoted a canonical
``ActiveEntity`` from a ``get_drug_info`` tool result -- a natural
first-turn drug question where the Main Model calls only ``search_drug``
(even when that search returns a single, genuinely unique match) never
established ``active_entity`` at all, so a later TRUE_FOLLOWUP had
nothing to inherit. Documented as a known limitation since BUILD-29D2,
re-confirmed by BUILD-43's own production validation (report SS15).

Fix (tool-contract level, zero new model calls): ``search_catalog``
(v2_agent.py) now also exposes ``search_catalog_unique_match`` -- the
query's FULL, untruncated ranked result, reduced to a single item only
when there is genuinely exactly one match. This is threaded through
``search_drug``'s own tool result (``unique_match_legacy_drug_id``), so
``_resolved_drug_entity`` can promote an entity from an unambiguous
search alone, without ever inferring "uniqueness" from ``len(items) ==
1`` (which a caller-chosen ``limit`` could truncate down to 1 even for a
genuinely ambiguous query -- the exact trap the spec explicitly warned
against).
"""

from __future__ import annotations

from backend.agents.v2.conversation_state import ActiveEntity
from backend.agents.v2.tools import ToolResult
from backend.api.agent_v2_routes import _resolved_drug_entity
from backend.services.drug_knowledge.v2_agent import DrugCatalogItem, V2AgentKnowledgeService


def _search_result(items: list[dict], *, unique_match_legacy_drug_id: str | None) -> ToolResult:
    return ToolResult(name="search_drug", data={"items": items, "unique_match_legacy_drug_id": unique_match_legacy_drug_id})


def _info_result(legacy_drug_id: str) -> ToolResult:
    return ToolResult(name="get_drug_info", data={"legacy_drug_id": legacy_drug_id, "results": []})


# ---------------------------------------------------------------------------
# _resolved_drug_entity: route-level promotion logic
# ---------------------------------------------------------------------------


def test_unique_search_drug_result_alone_now_promotes_entity():
    """The fix: a genuinely unique search_drug result -- server-confirmed via
    unique_match_legacy_drug_id, not just len(items) -- promotes an entity
    with zero extra model calls, no get_drug_info needed."""
    tool_results = [
        _search_result(
            [{"legacy_drug_id": "para-500", "name": "Paracetamol 500mg", "dosage_form": "vien nen"}],
            unique_match_legacy_drug_id="para-500",
        ),
    ]
    entity = _resolved_drug_entity(tool_results, known_entity=None)
    assert entity == ActiveEntity("drug", "para-500", "Paracetamol 500mg")


def test_ambiguous_search_drug_result_still_does_not_promote_entity():
    """Locked: real ambiguity (unique_match_legacy_drug_id is None, even
    though multiple items were returned) must never auto-bind."""
    tool_results = [
        _search_result(
            [
                {"legacy_drug_id": "para-500", "name": "Paracetamol 500mg"},
                {"legacy_drug_id": "para-650", "name": "Paracetamol 650mg"},
            ],
            unique_match_legacy_drug_id=None,
        ),
    ]
    assert _resolved_drug_entity(tool_results, known_entity=None) is None


def test_truncated_but_not_actually_unique_result_does_not_promote_entity():
    """The exact trap this fix must not fall into: a caller-chosen limit
    that happens to truncate ``items`` down to 1 must NOT be mistaken for
    genuine uniqueness -- only trust the server-computed
    unique_match_legacy_drug_id, never len(items) alone."""
    tool_results = [
        _search_result(
            [{"legacy_drug_id": "para-500", "name": "Paracetamol 500mg"}],  # truncated to 1 by the model's own limit
            unique_match_legacy_drug_id=None,  # but the server says this was NOT actually unique
        ),
    ]
    assert _resolved_drug_entity(tool_results, known_entity=None) is None


def test_no_tool_results_at_all_stays_none():
    assert _resolved_drug_entity([], known_entity=None) is None


def test_multiple_search_drug_calls_in_one_turn_does_not_auto_bind():
    """Two distinct searches in one turn is itself a form of ambiguity this
    fix deliberately does not try to resolve -- falls through to None."""
    tool_results = [
        _search_result([{"legacy_drug_id": "a", "name": "A"}], unique_match_legacy_drug_id="a"),
        _search_result([{"legacy_drug_id": "b", "name": "B"}], unique_match_legacy_drug_id="b"),
    ]
    assert _resolved_drug_entity(tool_results, known_entity=None) is None


def test_get_drug_info_path_is_completely_unchanged():
    """Pre-existing behavior, locked: when get_drug_info ran, that remains
    the authoritative path exactly as before -- this fix only ADDS a
    fallback for its absence, never changes this branch."""
    tool_results = [
        _search_result([{"legacy_drug_id": "para-500", "name": "Paracetamol 500mg"}], unique_match_legacy_drug_id="para-500"),
        _info_result("para-500"),
    ]
    entity = _resolved_drug_entity(tool_results, known_entity=None)
    assert entity == ActiveEntity("drug", "para-500", "Paracetamol 500mg")


def test_known_entity_reconfirmation_still_preserves_real_display_name():
    """BUILD-43's own regression lock, re-verified unaffected by this fix:
    a TRUE_FOLLOWUP bound-lookup (get_drug_info only, no search_drug) still
    reuses the already-known real display name, never degrading to the
    raw id."""
    tool_results = [_info_result("para-500")]
    known = ActiveEntity("drug", "para-500", "Paracetamol 500mg")
    entity = _resolved_drug_entity(tool_results, known_entity=known)
    assert entity == known


# ---------------------------------------------------------------------------
# search_catalog_unique_match: tool-contract level (real catalog service)
# ---------------------------------------------------------------------------


def _service_with_items(*names: str) -> V2AgentKnowledgeService:
    service = V2AgentKnowledgeService.__new__(V2AgentKnowledgeService)
    service.catalog_items = [
        DrugCatalogItem(
            drug_id=f"id-{i}", ten_thuoc=name, dang_thuoc="vien nen", duong_dung="uong",
            ham_luong="500mg", tong_so_luong=None, muc_nghiem_trong=None,
        )
        for i, name in enumerate(names)
    ]
    return service


def test_search_catalog_unique_match_real_unique_query():
    # "Insulin Actrapid" deliberately shares no meaningful characters with
    # the query (score 0.089, real value confirmed) -- unlike two products
    # that happen to share a digit/"mg" tail (e.g. "500mg"/"250mg"), which
    # can cross the 0.20 fuzzy-match floor and correctly count as a second
    # real candidate; found via this test's own first run, not assumed.
    service = _service_with_items("Paracetamol 500mg", "Insulin Actrapid")
    match = service.search_catalog_unique_match("Paracetamol 500mg")
    assert match is not None
    assert match.ten_thuoc == "Paracetamol 500mg"


def test_search_catalog_unique_match_none_for_genuinely_ambiguous_query():
    service = _service_with_items("Paracetamol 500mg", "Paracetamol 650mg")
    assert service.search_catalog_unique_match("Paracetamol") is None


def test_search_catalog_unique_match_none_for_no_match():
    service = _service_with_items("Paracetamol 500mg")
    assert service.search_catalog_unique_match("hoan toan khong lien quan xyz") is None


def test_search_catalog_unique_match_ignores_shared_manufacturer_packaging_noise():
    """Regression lock for a real finding made while verifying this fix
    against the real production catalog: two DIFFERENT products that merely
    share a manufacturer/dosage/packaging token (e.g. both "40mg" from
    "Astrazeneca") can score well above search_catalog's own 0.20 browsing
    floor via the fuzzy token/char scorer -- confirmed empirically (one
    real exact-full-name query matched 161 unrelated catalog rows at 0.20).
    The stricter _UNIQUE_MATCH_SCORE_FLOOR must not be fooled by this."""
    service = _service_with_items("Nexium 40mg INJ Astrazeneca", "Tagrisso 40mg Astrazeneca 3x10")
    # Confirm the two items really do share enough surface tokens to clear
    # search_catalog's own general 0.20 floor (the noise this fix must see
    # past), before asserting the strict floor correctly stays unfooled.
    from backend.services.drug_knowledge.v2_agent import V2AgentKnowledgeService

    sibling_score = V2AgentKnowledgeService._name_score("Nexium 40mg INJ Astrazeneca", "Tagrisso 40mg Astrazeneca 3x10")
    assert sibling_score >= 0.20
    assert sibling_score < service._UNIQUE_MATCH_SCORE_FLOOR
    match = service.search_catalog_unique_match("Nexium 40mg INJ Astrazeneca")
    assert match is not None
    assert match.ten_thuoc == "Nexium 40mg INJ Astrazeneca"


def test_search_catalog_unique_match_short_prefix_never_promotes():
    """The doctor-combobox short-prefix branch uses a different, looser
    startswith scoring scheme -- never safe to treat as an identity
    signal, regardless of how many/few catalog rows it happens to match."""
    service = _service_with_items("ABC Drug")
    assert service.search_catalog_unique_match("abc") is None


def test_search_catalog_unique_match_is_independent_of_search_catalog_limit():
    """The whole point of this fix: search_catalog's own truncation must
    never leak into the uniqueness signal."""
    service = _service_with_items("Paracetamol 500mg", "Paracetamol 650mg")
    truncated = service.search_catalog("Paracetamol", limit=1)
    assert len(truncated) == 1  # truncated by limit, NOT genuinely unique
    assert service.search_catalog_unique_match("Paracetamol") is None
