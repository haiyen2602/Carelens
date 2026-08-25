"""BUILD-33: sanitized Judge input assembly + PII/PHI/secret rejection.

Builds the exact, minimal payload the Judge model is allowed to see (BUILD-33
§6). Deliberately does NOT import
``backend.agents.v2.deepeval_judge.assert_public_evaluation_text`` even
though the pattern is conceptually similar: that module's own docstring
states "Nothing in this module is imported by Agent runtime/Safety code" and
scopes itself to public, non-patient golden-RAG text only -- importing it
here (this module IS called from the real Agent V2 runtime path, for real
patient conversation turns) would silently break that stated invariant. The
guard below is written independently instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.agents.v2.evaluation_v2 import EvaluationPath


class JudgeInputRejectedError(ValueError):
    """Raised when a candidate Judge input contains PII/PHI/secret-shaped
    text. Callers must treat this as "do not enqueue this run for Judge",
    never as a reason to fail the underlying chat request."""


_EMAIL_RE = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
_PHONE_RE = re.compile(r"(?<!\d)\+?\d[\d .-]{7,}\d(?!\d)")
_OPERATIONAL_ID_RE = re.compile(
    r"\b(patient_id|actor_id|conversation_id|trace_id|agent_run_id|jwt|bearer|password|secret|api[_-]?key)\b",
    re.IGNORECASE,
)
# A bare JWT is 3 dot-separated base64url segments; the header/payload
# segments alone are long enough that this is very unlikely to false-positive
# on ordinary Vietnamese sentence text.
_JWT_SHAPE_RE = re.compile(r"\b[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")


def _assert_clean(value: str, *, field_name: str) -> None:
    if _EMAIL_RE.search(value) or _PHONE_RE.search(value) or _OPERATIONAL_ID_RE.search(value) or _JWT_SHAPE_RE.search(value):
        raise JudgeInputRejectedError(f"JUDGE_INPUT_REJECTED_{field_name.upper()}")


@dataclass(frozen=True)
class JudgeInputPayload:
    query: str
    response: str
    execution_path: str
    tool_names: tuple[str, ...] = ()
    citations: tuple[str, ...] = ()
    # Only ever populated for EvaluationPath.RAG -- public drug-corpus
    # snippets already surfaced as citations, never patient-specific tool
    # output (dose schedules, prescriptions, etc. stay names-only above).
    retrieved_evidence: tuple[str, ...] = ()
    expected_ground_truth: str | None = None

    def as_context_dict(self) -> dict:
        """Sanitized-context snapshot persisted on ``AgentRunJudge.
        sanitized_context_json`` -- everything except query/response text
        (which get their own dedicated columns)."""

        return {
            "execution_path": self.execution_path,
            "tool_names": list(self.tool_names),
            "citations": list(self.citations),
            "retrieved_evidence": list(self.retrieved_evidence),
            "expected_ground_truth": self.expected_ground_truth,
        }


# A tool's own structured `.data` is only ever folded into `retrieved_evidence`
# for these RAG-shaped tool names (drug-knowledge lookups over the public
# corpus) -- never for a dose/schedule/prescription tool, which returns real
# patient data.
_RAG_EVIDENCE_TOOL_NAMES = frozenset({"search_drug", "get_drug_info"})


def build_judge_input(
    *,
    query: str,
    response: str,
    path: EvaluationPath,
    tool_results: tuple = (),
    citations: tuple = (),
    expected_ground_truth: str | None = None,
) -> JudgeInputPayload:
    """Assemble and validate a sanitized Judge input. Raises
    ``JudgeInputRejectedError`` (never returns a partially-sanitized payload) if
    the query, response, or any evidence snippet looks like PII/PHI/a secret.
    """

    tool_names = tuple(str(getattr(item, "name", "")) for item in tool_results if getattr(item, "name", None))
    citation_labels = tuple(str(getattr(item, "title", "")) for item in citations if getattr(item, "title", None))

    retrieved_evidence: tuple[str, ...] = ()
    if path is EvaluationPath.RAG:
        snippets: list[str] = []
        for item in tool_results:
            name = str(getattr(item, "name", ""))
            if name not in _RAG_EVIDENCE_TOOL_NAMES:
                continue
            data = getattr(item, "data", None)
            if isinstance(data, dict):
                # A short, flat rendering (drug name/dosage_form/route/
                # strength/cong_dung -- the same catalog fields the router's
                # own grounding logic already treats as real evidence, per
                # BUILD-24F/24L) -- never nested raw tool JSON dumped whole.
                rendered = "; ".join(f"{k}={v}" for k, v in data.items() if isinstance(v, (str, int, float, bool)))
                if rendered:
                    snippets.append(rendered[:500])
        retrieved_evidence = tuple(snippets)

    payload = JudgeInputPayload(
        query=query.strip(),
        response=response.strip(),
        execution_path=path.value,
        tool_names=tool_names,
        citations=citation_labels,
        retrieved_evidence=retrieved_evidence,
        expected_ground_truth=expected_ground_truth,
    )

    _assert_clean(payload.query, field_name="query")
    _assert_clean(payload.response, field_name="response")
    for snippet in payload.retrieved_evidence:
        _assert_clean(snippet, field_name="evidence")

    return payload


__all__ = ["JudgeInputPayload", "JudgeInputRejectedError", "build_judge_input"]
