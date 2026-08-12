#!/usr/bin/env python3
"""Vong 2, muc 6 (chatbot-rag-design.md, dong #1/#2) - tune NGUONG_VECTOR/
NGUONG_LEXICAL/rrf_k/n cho DUNG duong song HIEN TAI:
`_search_distinct_drug_candidates()` (backend/agents/nodes/drug_confirmation_
nodes.py) - KHONG phai `hybrid_search()`/`build_retrieval_node` (Phase 7 dung
de tune #8/#14) - duong do DA CHET trong production tu khi muc 5 (xac nhan
danh tinh thuoc) thay the (`build_retrieval_node` chi con duoc goi tu unit
test, `chat_routes.py` khong con import). Phat hien khi bat dau muc 6 - GHI
RO o day de khong ai doc bao cao nay ma tuong nham dang tune duong song that.

DO RECALL O CAP DO THUOC (khac Phase 7 - do o cap FIELD_GROUP qua hybrid_
search()): voi moi cau trong eval/ground_truth.json (32 cau, biet truoc
drug_id dung), drug_id dung co lot vao danh sach candidate (sau dedup theo
drug_id, cat con `n`) hay khong - dung DUNG logic cua _search_distinct_drug_
candidates(), chi tham so hoa nguong_vector/nguong_lexical/rrf_k/n de sweep
(ham that trong production hardcode pool=50 truoc dedup, KHONG doc tu
settings - giu co dinh khi sweep, chi 1 tham so `n` la analog dung cua "#2
top_k sau hop nhat" kickoff nhac toi, vi settings.retrieval_top_k gio la dead
code).

Cung do OOD (eval/out_of_domain.json) de tham khao - nhung KHONG con la chi
so quyet dinh chinh nhu Phase 7 nua: sau muc 5, ke ca OOD tinh co "co
candidate" (drug sai), benh nhan van phai XAC NHAN truoc khi duoc tra loi
(hoi lai toi da 2 vong theo muc 11.2) - human-in-the-loop da giam bot rui ro
false-positive ma nguong cao (0.60/0.55, chot o #8) ban dau dung de phong
ngua. Vi vay sweep nay CO THE de xuat ha nguong de tang GT recall, doi lay
1 chut OOD false-candidate cao hon co chu dinh - khac nguyen tac luc #8 (khi
chua co lop xac nhan).

Chi phi: tinh embedding that 1 lan cho 32 cau GT + 15 cau OOD (~47 call
that, nho) - toan bo sweep threshold/k/n sau do la truy van DB thuan (vector_
search/lexical_search/fuse_rrf), KHONG goi LLM/embedding them.

Usage:
    python eval/tune_candidate_retrieval.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db.base import SessionLocal  # noqa: E402
from backend.services.embeddings import embed_query  # noqa: E402
from backend.services.retrieval import fuse_rrf, lexical_search, vector_search  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
GROUND_TRUTH_PATH = EVAL_DIR / "ground_truth.json"
OUT_OF_DOMAIN_PATH = EVAL_DIR / "out_of_domain.json"

# Gia tri hardcode hien tai trong _search_distinct_drug_candidates() - giu CO
# DINH khi sweep threshold/k/n (khong phai muc tieu cua sweep nay, ban than
# no da du rong: pool 50 chunk truoc khi dedup theo drug_id).
POOL_SIZE = 50


def _distinct_drug_candidates(vec, lex, k: int, pool_size: int, n: int) -> tuple[list[str], bool]:
    """Sao chep DUNG logic dedup cua _search_distinct_drug_candidates() (drug_
    confirmation_nodes.py) - tham so hoa k/pool_size/n de sweep, ham production
    that hardcode pool_size=50."""
    outcome = fuse_rrf(vec, lex, k=k, top_k=pool_size)
    seen: set[str] = set()
    distinct: list[str] = []
    for r in outcome.results:
        if r.drug_id not in seen:
            seen.add(r.drug_id)
            distinct.append(r.drug_id)
        if len(distinct) >= n:
            break
    return distinct, outcome.no_source_found


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ground_truth = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    out_of_domain = json.loads(OUT_OF_DOMAIN_PATH.read_text(encoding="utf-8"))
    print(f"Ground truth: {len(ground_truth)} cau, out-of-domain: {len(out_of_domain)} cau")
    print("Dang tinh embedding that (1 lan, tai su dung cho toan bo sweep phia duoi)...")

    gt_embeddings = {item["utterance"]: embed_query(item["utterance"]) for item in ground_truth}
    ood_embeddings = {item["utterance"]: embed_query(item["utterance"]) for item in out_of_domain}

    db = SessionLocal()
    try:
        # Nguong hien tai (0.60/0.55, chot o #8) la 1 DIEM trong luoi nay,
        # KHONG phai gia dinh dung san - do lai tu dau cho dung cong viec
        # thuc te (drug-level candidate recall qua lop xac nhan moi).
        threshold_grid = [
            (0.50, 0.45),
            (0.55, 0.50),
            (0.60, 0.55),  # gia tri hien tai trong config.py
            (0.65, 0.60),
            (0.70, 0.65),
        ]
        k_grid = [30, 60, 100]
        n_grid = [3, 4, 5]

        results = []
        for nguong_vector, nguong_lexical in threshold_grid:
            # Cache candidate pool TRUOC RRF cho tung nguong (khong doi theo
            # k/n) - tranh query DB lap lai khong can thiet trong vong sweep
            # k/n ben duoi.
            gt_vec_lex = {}
            for item in ground_truth:
                emb = gt_embeddings[item["utterance"]]
                vec = vector_search(db, emb, nguong_vector)
                lex = lexical_search(db, item["utterance"], nguong_lexical)
                gt_vec_lex[item["utterance"]] = (vec, lex)

            ood_vec_lex = {}
            for item in out_of_domain:
                emb = ood_embeddings[item["utterance"]]
                vec = vector_search(db, emb, nguong_vector)
                lex = lexical_search(db, item["utterance"], nguong_lexical)
                ood_vec_lex[item["utterance"]] = (vec, lex)

            for k in k_grid:
                for n in n_grid:
                    n_gt_hit = 0
                    n_gt_zero_candidates = 0
                    for item in ground_truth:
                        vec, lex = gt_vec_lex[item["utterance"]]
                        distinct, no_source = _distinct_drug_candidates(vec, lex, k, POOL_SIZE, n)
                        if no_source or not distinct:
                            n_gt_zero_candidates += 1
                        if item["drug_id"] in distinct:
                            n_gt_hit += 1

                    n_ood_has_candidate = 0
                    for item in out_of_domain:
                        vec, lex = ood_vec_lex[item["utterance"]]
                        distinct, no_source = _distinct_drug_candidates(vec, lex, k, POOL_SIZE, n)
                        if not (no_source or not distinct):
                            n_ood_has_candidate += 1

                    row = {
                        "nguong_vector": nguong_vector,
                        "nguong_lexical": nguong_lexical,
                        "rrf_k": k,
                        "n_candidates": n,
                        "gt_recall_at_n": n_gt_hit / len(ground_truth),
                        "gt_zero_candidates_rate": n_gt_zero_candidates / len(ground_truth),
                        "ood_has_candidate_rate": n_ood_has_candidate / len(out_of_domain),
                    }
                    results.append(row)
                    print(
                        f"  nv={nguong_vector} nl={nguong_lexical} k={k:>3} n={n} | "
                        f"GT recall@n={row['gt_recall_at_n']:.1%}  GT zero-cand={row['gt_zero_candidates_rate']:.1%}  "
                        f"OOD co candidate={row['ood_has_candidate_rate']:.1%}"
                    )

        out_path = EVAL_DIR / "candidate_retrieval_tuning.json"
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nDa ghi bao cao vao {out_path}")
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())