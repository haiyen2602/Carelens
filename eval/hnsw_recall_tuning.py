#!/usr/bin/env python3
"""Vong 2, muc 6 - phat hien 2026-08-09 (phan hoi review, sau khi 2 case tu
phat Bluepine/Fluopas lo ra HNSW approximate index co the bo sot true nearest
neighbor): do CO HE THONG tren toan bo eval/ground_truth.json (32 cau) +
eval/out_of_domain.json (15 cau), KHONG dung lai o 2 case da tim thay tay.

QUAN TRONG - day la 2 CHI SO KHAC HAN "retrieval recall vs ground truth" da
do o eval/tune_candidate_retrieval.py (muc 6, sweep nguong/rrf_k/n) - dung
bai hoc du an da tu sua nhieu lan (#8 vs #14, item-level vs recall@5 that):
KHONG duoc gop 2 nguon loi khac nhau vao 1 con so. O day chi do "HNSW co tim
duoc dung chunk GAN NHAT THAT (exact scan) hay khong", hoan toan doc lap voi
nguong_vector/nguong_lexical/rrf_k/n - 1 chunk co the la "gan nhat that" ma
van khong qua nguong (2 chuyen khac nhau).

Phuong phap, cho TUNG cau hoi (47 cau):
  1. Tinh embedding that 1 lan (cache, tai su dung cho ca buoc 2 va 3).
  2. EXACT SCAN (enable_indexscan=off, enable_bitmapscan=off - ep Postgres
     quet tuan tu, khong dung HNSW) -> chunk THAT gan nhat (top-1) theo cosine
     that. Chi tinh 1 LAN/cau (khong phu thuoc ef_search).
  3. Voi TUNG gia tri hnsw.ef_search trong luoi {40 (mac dinh), 60, 80, 100,
     150, 200}: chay lai truy van HNSW y het production (ORDER BY ... LIMIT
     CANDIDATE_POOL_SIZE=50), do:
       - "chunk that gan nhat" (buoc 2) co nam trong top-50 HNSW hay khong
         (chi so "HNSW recall vs exact scan")
       - thoi gian THAT cua truy van (wall-clock, khong suy doan)

Ghi ket qua eval/hnsw_recall_tuning.json. Chi phi: 47 embedding that (~$0.001,
nho) + 47 exact-scan query (khong goi API them) + 47*6=282 HNSW query (khong
goi API them) - toan bo phan sau la truy van DB thuan.

Usage:
    python eval/hnsw_recall_tuning.py
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from backend.db.base import SessionLocal  # noqa: E402
from backend.services.embeddings import embed_query  # noqa: E402
from backend.services.retrieval import CANDIDATE_POOL_SIZE  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
GROUND_TRUTH_PATH = EVAL_DIR / "ground_truth.json"
OUT_OF_DOMAIN_PATH = EVAL_DIR / "out_of_domain.json"

EF_SEARCH_GRID = [40, 60, 80, 100, 150, 200]  # 40 = mac dinh pgvector, chua tung doi


def _exact_top1_chunk(db, emb_str: str) -> tuple[str, str, float]:
    """Ep KHONG dung index (sequential scan, dung ca bang) - chunk id/drug_id/
    cosine GAN NHAT THAT, dung lam "ground truth" cho phep do HNSW recall."""
    db.execute(text("SET enable_indexscan = off"))
    db.execute(text("SET enable_bitmapscan = off"))
    row = db.execute(
        text(
            """
            SELECT id, drug_id, 1 - (embedding <=> CAST(:emb AS vector)) AS cos
            FROM drug_chunks ORDER BY embedding <=> CAST(:emb AS vector) LIMIT 1
            """
        ),
        {"emb": emb_str},
    ).fetchone()
    db.execute(text("RESET enable_indexscan"))
    db.execute(text("RESET enable_bitmapscan"))
    return str(row.id), row.drug_id, row.cos


def _hnsw_top_pool_chunk_ids(db, emb_str: str, ef_search: int) -> tuple[set[str], float]:
    """Dung DUNG truy van HNSW nhu production (vector_search(), CANDIDATE_
    POOL_SIZE lam LIMIT) - do thoi gian THAT cua rieng truy van nay (khong
    tinh thoi gian SET/RESET)."""
    db.execute(text("SET hnsw.ef_search = :ef"), {"ef": ef_search})
    t0 = time.monotonic()
    rows = db.execute(
        text(
            """
            SELECT id FROM drug_chunks
            ORDER BY embedding <=> CAST(:emb AS vector) LIMIT :pool_size
            """
        ),
        {"emb": emb_str, "pool_size": CANDIDATE_POOL_SIZE},
    ).fetchall()
    duration_ms = (time.monotonic() - t0) * 1000
    db.execute(text("RESET hnsw.ef_search"))
    return {str(r.id) for r in rows}, duration_ms


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ground_truth = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    out_of_domain = json.loads(OUT_OF_DOMAIN_PATH.read_text(encoding="utf-8"))
    all_items = [{"utterance": g["utterance"], "group": "GT"} for g in ground_truth] + [
        {"utterance": o["utterance"], "group": "OOD"} for o in out_of_domain
    ]
    print(f"Tong {len(all_items)} cau (32 GT + 15 OOD). Dang tinh embedding that (1 lan/cau)...")

    db = SessionLocal()
    try:
        # Buoc 1+2: embedding + exact-scan ground truth (khong phu thuoc ef_search).
        exact_by_utterance: dict[str, tuple[str, str, float]] = {}
        for item in all_items:
            emb_str = str(embed_query(item["utterance"]))
            item["_emb_str"] = emb_str
            exact_by_utterance[item["utterance"]] = _exact_top1_chunk(db, emb_str)

        print("Da xong exact-scan ground truth cho tat ca cau. Bat dau sweep ef_search...")

        results = []
        for ef in EF_SEARCH_GRID:
            n_recalled = 0
            n_gt_recalled = 0
            durations_ms = []
            for item in all_items:
                exact_chunk_id, exact_drug_id, exact_cos = exact_by_utterance[item["utterance"]]
                pool_ids, duration_ms = _hnsw_top_pool_chunk_ids(db, item["_emb_str"], ef)
                durations_ms.append(duration_ms)
                recalled = exact_chunk_id in pool_ids
                if recalled:
                    n_recalled += 1
                    if item["group"] == "GT":
                        n_gt_recalled += 1

            n_gt = sum(1 for i in all_items if i["group"] == "GT")
            row = {
                "ef_search": ef,
                "hnsw_recall_vs_exact_all": n_recalled / len(all_items),
                "hnsw_recall_vs_exact_gt_only": n_gt_recalled / n_gt,
                "latency_ms_mean": statistics.fmean(durations_ms),
                "latency_ms_p50": statistics.median(durations_ms),
                "latency_ms_p95": sorted(durations_ms)[int(len(durations_ms) * 0.95)],
                "latency_ms_max": max(durations_ms),
            }
            results.append(row)
            print(
                f"  ef_search={ef:>4} | HNSW recall vs exact (all 47)={row['hnsw_recall_vs_exact_all']:.1%}  "
                f"(GT only)={row['hnsw_recall_vs_exact_gt_only']:.1%}  "
                f"latency mean={row['latency_ms_mean']:.1f}ms p95={row['latency_ms_p95']:.1f}ms max={row['latency_ms_max']:.1f}ms"
            )

        out_path = EVAL_DIR / "hnsw_recall_tuning.json"
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nDa ghi bao cao vao {out_path}")
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())