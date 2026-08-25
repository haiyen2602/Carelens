"""BUILD-33 §9: Judge calibration harness.

Runs the real Judge provider (no mocking) against a small, fully synthetic
controlled set (scripts/agent_v2/judge_calibration_cases.json -- 9 cases:
good/hallucinated RAG, irrelevant answer, good/unsafe triage, correct/unsafe
dose safety, correct acute-danger escalation, inappropriate fallback) and
reports agreement against each case's hand-authored expected label.

This is intentionally NOT a pytest test (a real, billed LLM call every run is
not appropriate for the regular test suite) -- run it manually:

    python scripts/agent_v2/judge_calibration.py [--provider openai|google]
        [--model MODEL] [--api-key KEY] [--base-url URL]

With no flags it uses whatever backend.config.Settings resolves (the
project's configured default -- see BUILD-33 report §2/§13 for why this
build's own real run used --provider openai explicitly: no live
GOOGLE_API_KEY was available in this local environment).

Never claims Judge is "trustworthy" from this alone (BUILD-33 §9's own
explicit instruction) -- prints per-case PASS/DISAGREE plus the raw score,
for a human to read alongside the report.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.agents.v2.evaluation_v2 import EvaluationPath  # noqa: E402
from backend.agents.v2.judge_input import JudgeInputPayload  # noqa: E402
from backend.agents.v2.judge_provider import call_judge, resolve_base_url, resolve_credential  # noqa: E402
from backend.agents.v2.judge_rubrics import render_prompt, rubric_for_path  # noqa: E402
from backend.config import get_settings  # noqa: E402

_CASES_PATH = Path(__file__).resolve().parent / "judge_calibration_cases.json"


def _check_expectation(case: dict, call_result) -> tuple[bool, list[str]]:
    expect = case["expect"]
    notes: list[str] = []
    agree = True

    if "overall_score_at_least" in expect:
        threshold = expect["overall_score_at_least"]
        ok = call_result.overall_score is not None and call_result.overall_score >= threshold
        notes.append(f"overall_score={call_result.overall_score} >= {threshold}: {ok}")
        agree = agree and ok
    if "overall_score_at_most" in expect:
        threshold = expect["overall_score_at_most"]
        ok = call_result.overall_score is not None and call_result.overall_score <= threshold
        notes.append(f"overall_score={call_result.overall_score} <= {threshold}: {ok}")
        agree = agree and ok
    for dim, threshold in expect.get("dimension_at_least", {}).items():
        value = call_result.dimension_scores.get(dim)
        ok = value is not None and value >= threshold
        notes.append(f"dim[{dim}]={value} >= {threshold}: {ok}")
        agree = agree and ok
    for dim, threshold in expect.get("dimension_at_most", {}).items():
        value = call_result.dimension_scores.get(dim)
        ok = value is not None and value <= threshold
        notes.append(f"dim[{dim}]={value} <= {threshold}: {ok}")
        agree = agree and ok

    return agree, notes


def main() -> int:
    parser = argparse.ArgumentParser(description="BUILD-33 Judge calibration run (real model call)")
    parser.add_argument("--provider", choices=["openai", "google"], default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--out", default=None, help="Optional path to write a JSON results file")
    args = parser.parse_args()

    settings = get_settings()
    provider = args.provider or settings.agent_judge_provider
    model = args.model or settings.agent_judge_model
    api_key = args.api_key or resolve_credential(
        provider=provider,
        openai_judge_api_key=settings.openai_judge_api_key,
        openai_api_key=settings.openai_api_key,
        google_api_key=settings.agent_judge_google_api_key,
    )
    base_url = args.base_url or resolve_base_url(provider=provider, configured_base_url=settings.agent_judge_base_url)

    cases = json.loads(_CASES_PATH.read_text(encoding="utf-8"))
    results = []
    agree_count = 0

    print(f"BUILD-33 Judge calibration -- provider={provider} model={model} base_url={base_url or '(default)'}")
    print(f"{len(cases)} cases\n")

    for case in cases:
        path = EvaluationPath(case["execution_path"])
        payload = JudgeInputPayload(
            query=case["query"],
            response=case["response"],
            execution_path=path.value,
            retrieved_evidence=tuple(case.get("retrieved_evidence") or ()),
        )
        rubric = rubric_for_path(path)
        prompt = render_prompt(rubric=rubric, payload=payload)

        call_result = call_judge(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            reasoning_effort=settings.agent_judge_reasoning_effort,
            timeout_seconds=settings.agent_judge_timeout_seconds,
            prompt=prompt,
        )

        if call_result.status != "SCORED":
            print(f"[{case['case_id']}] JUDGE_FAILED ({call_result.failure_reason}) -- {case['category']}")
            results.append({"case_id": case["case_id"], "status": "JUDGE_FAILED", "failure_reason": call_result.failure_reason})
            continue

        agree, notes = _check_expectation(case, call_result)
        agree_count += int(agree)
        label = "AGREE" if agree else "DISAGREE"
        print(f"[{case['case_id']}] {label} -- {case['category']}")
        for note in notes:
            print(f"    {note}")
        if call_result.flags:
            print(f"    flags={call_result.flags}")
        results.append(
            {
                "case_id": case["case_id"],
                "category": case["category"],
                "status": "SCORED",
                "agree": agree,
                "overall_score": call_result.overall_score,
                "dimension_scores": call_result.dimension_scores,
                "flags": call_result.flags,
                "confidence": call_result.confidence,
                "notes": notes,
            }
        )

    scored = [r for r in results if r["status"] == "SCORED"]
    print(f"\n{agree_count}/{len(scored)} scored cases agreed with the expected label ({len(cases) - len(scored)} JUDGE_FAILED).")
    print("This is a small, hand-authored sanity check, not a statistical claim of Judge reliability (BUILD-33 section 9).")

    if args.out:
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Results written to {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
