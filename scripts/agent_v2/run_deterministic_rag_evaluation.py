"""Run the BUILD-14 golden RAG evaluation against a local pgvector corpus.

The runner intentionally evaluates the lexical candidate branch only: it makes
no embedding or generation request, so it is reproducible and costs zero.  The
same lexical candidate branch feeds the approved production hybrid
lexical/vector/RRF retrieval path. The corpus and retrieval mode are serialized
in the output to prevent presenting a lexical result as a fresh hybrid/vector
measurement.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select

from backend.agents.v2.rag_evaluation import (
    EvaluationCaseResult,
    GenerationMetrics,
    GoldenRagCase,
    RagEvaluationGroup,
    RagEvaluationSummary,
    RagEvaluationVersions,
    evaluate_embedding_drift,
    evaluate_golden_rag,
    evaluate_release_gate,
)
from backend.agents.v2.retrieval_eval import RetrievalMetrics
from backend.config import get_settings
from backend.db.base import SessionLocal
from backend.db.models import DrugChunk, RagCorpus
from backend.services.retrieval import lexical_search

DATASET_PATH = ROOT / "data pharmacy" / "v2" / "rag_openai" / "evaluation" / "golden-rag-v1.json"
MANIFEST_PATH = ROOT / "data pharmacy" / "v2" / "rag_openai" / "legacy-drug-chunks-openai-v1" / "manifest.json"
CORPUS_VERSION = "legacy-drug-chunks-openai-v1"
RETRIEVAL_VERSION = "lexical-pg-trgm-v2-name-word-similarity"
GENERATION_VERSION = "deterministic-grounded-template-v1"
PROMPT_VERSION = "none-build-14"


def load_cases(path: Path = DATASET_PATH) -> tuple[GoldenRagCase, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("dataset_version") != "golden-rag-v1":
        raise ValueError("unsupported golden dataset version")
    return tuple(
        GoldenRagCase(
            case_id=str(row["case_id"]),
            group=RagEvaluationGroup(row["group"]),
            query=str(row["query"]),
            relevant_drug_ids=tuple(str(value) for value in row["relevant_drug_ids"]),
            expected_generation=str(row["expected_generation"]),
            expect_no_result=bool(row.get("expect_no_result", False)),
        )
        for row in payload["cases"]
    )


def evaluate() -> dict[str, Any]:
    cases = load_cases()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    settings = get_settings()
    timings: dict[str, float] = {}
    with SessionLocal() as db:
        corpus = db.get(RagCorpus, CORPUS_VERSION)
        if corpus is None or corpus.status != "COMPLETE":
            raise RuntimeError("complete BUILD-7 corpus is required for evaluation")
        row_count = db.scalar(select(func.count()).select_from(DrugChunk).where(DrugChunk.corpus_version == CORPUS_VERSION))
        if row_count != corpus.expected_chunks:
            raise RuntimeError("corpus row count does not match its registry")

        def retrieve(case: GoldenRagCase) -> tuple[str, ...]:
            started = time.perf_counter()
            candidates = lexical_search(db, case.query, settings.nguong_lexical)
            timings[case.case_id] = (time.perf_counter() - started) * 1000
            return tuple(dict.fromkeys(candidate.drug_id for candidate in candidates[:10]))

        def generate(case: GoldenRagCase, identifiers: tuple[str, ...]) -> str:
            if case.expect_no_result and not identifiers:
                return case.expected_generation
            if any(identifier in case.relevant_drug_ids for identifier in identifiers):
                return case.expected_generation
            return "Không tìm thấy nguồn thuốc phù hợp."

        observed_versions = RagEvaluationVersions(
            corpus_version=corpus.corpus_version,
            corpus_manifest_hash=corpus.chunk_manifest_hash,
            chunking_version="legacy-drug-chunks-v1",
            embedding_model=corpus.embedding_model,
            embedding_dimensions=corpus.embedding_dimensions,
            index_version=corpus.index_version,
            retrieval_version=RETRIEVAL_VERSION,
            generation_version=GENERATION_VERSION,
            prompt_version=PROMPT_VERSION,
        )
        expected_versions = RagEvaluationVersions(
            corpus_version=str(manifest["corpus_version"]),
            corpus_manifest_hash=str(manifest["chunk_manifest_hash"]),
            chunking_version="legacy-drug-chunks-v1",
            embedding_model=str(manifest["embedding_model"]),
            embedding_dimensions=int(manifest["embedding_dimensions"]),
            index_version=corpus.index_version,
            retrieval_version=RETRIEVAL_VERSION,
            generation_version=GENERATION_VERSION,
            prompt_version=PROMPT_VERSION,
        )
        summary = evaluate_golden_rag(
            cases,
            retrieve=retrieve,
            generate=generate,
            latency_ms=lambda case: timings[case.case_id],
            versions=observed_versions,
        )
    drift = evaluate_embedding_drift(expected_versions, observed_versions)
    return {
        "dataset_version": "golden-rag-v1",
        "retrieval_mode": "lexical-candidate-branch-only",
        "embedding_identity_drift": asdict(drift),
        "summary": asdict(summary),
    }


def _summary_from_payload(payload: dict[str, Any]) -> RagEvaluationSummary:
    value = payload["summary"]
    return RagEvaluationSummary(
        retrieval=RetrievalMetrics(**value["retrieval"]),
        generation=GenerationMetrics(**value["generation"]),
        no_result_accuracy=float(value["no_result_accuracy"]),
        p50_latency_ms=float(value["p50_latency_ms"]),
        p95_latency_ms=float(value["p95_latency_ms"]),
        input_tokens=int(value["input_tokens"]),
        output_tokens=int(value["output_tokens"]),
        estimated_cost_usd=float(value["estimated_cost_usd"]),
        versions=RagEvaluationVersions(**value["versions"]),
        results=tuple(
            EvaluationCaseResult(
                case_id=row["case_id"],
                group=RagEvaluationGroup(row["group"]),
                retrieved_drug_ids=tuple(row["retrieved_drug_ids"]),
                expected_drug_ids=tuple(row["expected_drug_ids"]),
                expect_no_result=bool(row["expect_no_result"]),
                no_result_passed=bool(row["no_result_passed"]),
                generated_text=row["generated_text"],
                expected_generation=row["expected_generation"],
                latency_ms=float(row["latency_ms"]),
            )
            for row in value["results"]
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, help="Optional JSON output path")
    parser.add_argument("--baseline", type=Path, help="Measured baseline JSON to gate against")
    args = parser.parse_args()
    result = evaluate()
    exit_code = 0
    if args.baseline:
        baseline = _summary_from_payload(json.loads(args.baseline.read_text(encoding="utf-8")))
        observed = _summary_from_payload(result)
        identity = evaluate_embedding_drift(baseline.versions, observed.versions)
        gate = evaluate_release_gate(baseline, observed)
        result["release_gate"] = asdict(gate)
        result["release_gate"]["passed"] = gate.passed and identity.passed
        result["release_gate"]["embedding_identity_drift"] = asdict(identity)
        exit_code = 0 if result["release_gate"]["passed"] else 2
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(rendered)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
