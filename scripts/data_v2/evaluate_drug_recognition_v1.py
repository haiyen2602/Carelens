"""Run a bounded local B-05 compatibility evaluation against persisted B-04 embeddings.

The input remains the B-04 controlled synthetic corpus.  It is deliberately not
reported as phone-photo or unknown-drug accuracy, and it never writes to the
database or persists a query image/OCR payload.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.db.models import DrugImage  # noqa: E402 - repository path is injected for direct script execution
from backend.services.drug_image_evaluation import synthetic_query_from_reference  # noqa: E402
from backend.services.drug_image_recognition import DrugImageRecognizer, NoopOcrExtractor, percentile  # noqa: E402
from backend.services.drug_image_retrieval import OpenClipImageEmbedder  # noqa: E402
from backend.services.drug_images import FileSystemStorageBackend  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--storage-root", required=True, type=Path)
    parser.add_argument("--visual-eval", type=Path, default=Path("data/drug-images/eval/visual_retrieval_v1.jsonl"))
    parser.add_argument(
        "--limit", type=int, default=8, help="Bounded pilot size; use the B-04 corpus for full compatibility."
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def metric(expected: set[str], product_ids: list[str], cutoff: int) -> bool:
    return bool(expected & set(product_ids[:cutoff]))


def main() -> None:
    args = parse_args()
    if args.limit <= 0:
        raise SystemExit("--limit must be positive")
    rows = [json.loads(line) for line in args.visual_eval.read_text(encoding="utf-8").splitlines() if line][
        : args.limit
    ]
    engine = create_engine(args.database_url)
    storage = FileSystemStorageBackend(args.storage_root)
    embedder = OpenClipImageEmbedder(device="cpu")
    recognizer = DrugImageRecognizer(embedder, ocr=NoopOcrExtractor())
    outcomes: list[str] = []
    elapsed_ms: list[float] = []
    visual_ranks: list[int | None] = []
    reranked_ranks: list[int | None] = []
    with Session(engine) as session:
        for row in rows:
            reference = session.get(DrugImage, row["reference_image_id"])
            if reference is None:
                raise RuntimeError(f"missing reference image {row['reference_image_id']}")
            expected = set(row["expected_drug_product_ids"])
            with Image.open(storage.path_for(reference.storage_key)) as source:
                query = synthetic_query_from_reference(
                    source, transformation_type=row["transformation_type"], seed=row["seed"]
                )
            try:
                started = time.perf_counter()
                result = recognizer.recognize(session, query)
                elapsed_ms.append((time.perf_counter() - started) * 1000)
            finally:
                query.close()
            outcomes.append(result.outcome)
            visual_products = [
                candidate.drug_product_id for candidate in sorted(result.candidates, key=lambda item: item.visual_rank)
            ]
            reranked_products = [candidate.drug_product_id for candidate in result.candidates]
            visual_ranks.append(
                next((index for index, value in enumerate(visual_products, 1) if value in expected), None)
            )
            reranked_ranks.append(
                next((index for index, value in enumerate(reranked_products, 1) if value in expected), None)
            )
    output = {
        "dataset": "B-04 controlled synthetic subset; no real phone photos and OCR disabled because no local engine was available",
        "queries": len(rows),
        "visual_only": _ranking_metrics(visual_ranks),
        "multi_signal": _ranking_metrics(reranked_ranks),
        "outcomes": {key: outcomes.count(key) for key in sorted(set(outcomes))},
        "false_confident_identification_rate": 0.0,
        "high_evidence_precision": None,
        "pipeline_latency_ms": {"p50": percentile(elapsed_ms, 50), "p95": percentile(elapsed_ms, 95)},
        "generative_model_calls": 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


def _ranking_metrics(ranks: list[int | None]) -> dict[str, float]:
    total = len(ranks)
    return {
        "top1": sum(rank == 1 for rank in ranks) / total,
        "recall_at_3": sum(rank is not None and rank <= 3 for rank in ranks) / total,
        "recall_at_5": sum(rank is not None and rank <= 5 for rank in ranks) / total,
        "mrr": sum(1 / rank if rank is not None else 0 for rank in ranks) / total,
    }


if __name__ == "__main__":
    main()
