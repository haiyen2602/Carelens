"""BUILD-46 Fix A: model-visible tool-schema constraints must equal the
Tool Gateway's own Pydantic runtime validation constraints.

Root cause (found live during BUILD-45's own production validation, not
assumed): ``search_drug``'s model-visible JSON schema
(``model_gateway.py::_READ_ONLY_TOOL_SCHEMAS``) declared only bare
``{"type": "integer"}``/``{"type": "string"}`` for ``limit``/``query``,
while ``ToolGateway.execute()`` validates the same call against
``SearchDrugArguments`` (``tools.py``), which requires
``limit in [1, 20]`` and ``1 <= len(query) <= 100``. A model that picked
an out-of-range ``limit`` passed the (unconstrained) schema and then hard
-failed at the Pydantic boundary with ``INVALID_TOOL_ARGUMENTS`` ->
``TOOL_ERROR``, reproduced live on production
(BUILD-45-PRODUCTION-VALIDATION-REPORT.md section 7).

Researched, not assumed: OpenAI's own structured-outputs/strict-mode
documentation states ``minLength``/``maxLength``/``minimum``/``maximum``
are NOT enforced by constrained decoding the way ``type``/``enum``/
``required`` are -- adding them is harm reduction (a real API call with
these keys present was verified accepted, not rejected -- see the
build's own ad hoc verification script, not committed), not an absolute
guarantee. The Pydantic validation remains the actual fail-closed safety
net; this file locks the *contract equality* the task requires, plus a
generic, reusable completeness check so this whole class of drift cannot
silently ship again for any tool.
"""

from __future__ import annotations

import annotated_types
import pytest
from pydantic import ValidationError

from backend.agents.v2.model_gateway import _READ_ONLY_TOOL_SCHEMAS
from backend.agents.v2.tools import _TOOL_DEFINITIONS, SearchDrugArguments, ToolName

_SCHEMA_BY_NAME = {schema["name"]: schema for schema in _READ_ONLY_TOOL_SCHEMAS}

# Maps a Pydantic annotated_types constraint class to the JSON Schema
# keyword it must be mirrored as, and how to read the bound value off it.
_CONSTRAINT_TO_SCHEMA_KEY = {
    annotated_types.MinLen: ("minLength", "min_length"),
    annotated_types.MaxLen: ("maxLength", "max_length"),
    annotated_types.Ge: ("minimum", "ge"),
    annotated_types.Le: ("maximum", "le"),
    annotated_types.Gt: ("exclusiveMinimum", "gt"),
    annotated_types.Lt: ("exclusiveMaximum", "lt"),
}


def _expected_schema_bounds(model: type) -> dict[str, dict[str, object]]:
    """The bounds ``model``'s own Pydantic Field constraints require, in
    the JSON-Schema-keyword shape the model-visible schema must mirror."""
    expected: dict[str, dict[str, object]] = {}
    for field_name, field_info in model.model_fields.items():
        bounds: dict[str, object] = {}
        for constraint in field_info.metadata:
            mapping = _CONSTRAINT_TO_SCHEMA_KEY.get(type(constraint))
            if mapping is None:
                continue
            schema_key, attr = mapping
            bounds[schema_key] = getattr(constraint, attr)
        if bounds:
            expected[field_name] = bounds
    return expected


# ---------------------------------------------------------------------------
# 1. search_drug -- the mandatory candidate, spec's own exact required bound.
# ---------------------------------------------------------------------------


def test_search_drug_schema_declares_the_exact_pydantic_bounds():
    props = _SCHEMA_BY_NAME["search_drug"]["parameters"]["properties"]
    assert props["query"]["minLength"] == 1
    assert props["query"]["maxLength"] == 100
    assert props["limit"]["minimum"] == 1
    assert props["limit"]["maximum"] == 20


def test_search_drug_limit_1_accepted():
    SearchDrugArguments.model_validate({"query": "Paracetamol", "limit": 1})


def test_search_drug_limit_20_accepted():
    SearchDrugArguments.model_validate({"query": "Paracetamol", "limit": 20})


def test_search_drug_limit_0_rejected():
    with pytest.raises(ValidationError):
        SearchDrugArguments.model_validate({"query": "Paracetamol", "limit": 0})


def test_search_drug_limit_21_rejected():
    with pytest.raises(ValidationError):
        SearchDrugArguments.model_validate({"query": "Paracetamol", "limit": 21})


# ---------------------------------------------------------------------------
# 2. Generic, reusable completeness check (spec section 9): for EVERY
#    allowlisted tool, every Pydantic Field bound on its input_model must be
#    mirrored in the model-visible schema. This is what actually prevents
#    this whole class of drift from silently shipping again for a future
#    tool -- not just a fixed assertion on search_drug alone.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool_name", sorted(t.value for t in ToolName))
def test_every_tool_schema_declares_the_same_bounds_its_pydantic_model_enforces(tool_name):
    definition = _TOOL_DEFINITIONS[tool_name]
    expected = _expected_schema_bounds(definition.input_model)
    if not expected:
        return  # No length/range-constrained fields on this tool -- nothing to mirror.
    schema = _SCHEMA_BY_NAME[tool_name]
    props = schema["parameters"]["properties"]
    for field_name, bounds in expected.items():
        assert field_name in props, f"{tool_name}.{field_name} has no schema property at all"
        for schema_key, expected_value in bounds.items():
            assert props[field_name].get(schema_key) == expected_value, (
                f"{tool_name}.{field_name}: schema {schema_key}="
                f"{props[field_name].get(schema_key)!r}, Pydantic requires {expected_value!r}"
            )
