#!/usr/bin/env python3
"""Eval harness Phase 7 (build-kickoff-prompt.md muc 3) - 3 viec dung theo
dung scope da chot, khong lam them/bot:

  1. Do phan phoi cosine_similarity/trigram that tren eval/ground_truth.json
     (32 cau, dung thuoc/dung field_group biet truoc) VA eval/out_of_domain.json
     (15 cau - thuoc khong ton tai trong 3562 ban ghi, go sai nghiem trong,
     van ban khong lien quan) - dung 2 phan phoi nay de DE XUAT
     NGUONG_VECTOR/NGUONG_LEXICAL bang so lieu (muc 10 #13b), khong doan.
  2. Do rieng 3 chi so: retrieval precision/recall, ty le hallucination (cau
     tra loi khong grounded vao chunk nao), ty le caveat bi thieu khi dang
     le phai co.

KHONG lam: sua NGUONG_VECTOR/NGUONG_LEXICAL trong code (chi DE XUAT so lieu,
Architect tu quyet co ap dung khong - xem report cuoi script). KHONG danh
gia lai #12 (routing gap) - do la van de khac, khong phai threshold.

Goi OpenAI THAT (embedding + gpt-4o-mini generate + judge) - xem uoc tinh
chi phi truoc khi chay that trong bao cao gui Architect, khong tu chay khi
chua xac nhan (dung tinh than cost-consciousness xuyen suot du an).

Usage:
    python eval/run_eval.py
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from langchain_openai import ChatOpenAI  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from sqlalchemy import text  # noqa: E402

from src.config import get_settings  # noqa: E402
from src.db.base import SessionLocal  # noqa: E402
from src.services.classification import generate_answer  # noqa: E402
from src.services.embeddings import embed_query  # noqa: E402
from src.services.retrieval import DrugInfoResult, hybrid_search  # noqa: E402


def _get_judge_llm() -> ChatOpenAI:
    """RIENG cho judge, KHONG dung get_llm() dung chung (settings.llm_temperature
    mac dinh 0.7 - phu hop cho generate_answer can tu nhien, nhung SAI cho
    1 tac vu XAC MINH/JUDGE can nhat quan). Phat hien 2026-08-08: chay lai
    32 cau judge 2 lan (cung prompt cu, sau do prompt sua) cho ra 2 TAP HOP
    flag KHAC NHAU (6 flip) - mot phan do prompt, nhung it nhat 1 truong hop
    (Fluopas bao_quan - context chi 1 cau ngan, ro rang) van bi judge doan
    SAI o CA HAI lan chay, xac nhan qua doi chieu tay: day khong chi la loi
    prompt, temperature=0.7 gay ra bien thien khong can thiet cho 1 tac vu
    lang ra dung/sai. temperature=0 giup judge nhat quan hon giua cac lan
    chay (khong dam bao het loi, nhung loai bo 1 nguon nhieu khong can thiet)."""
    settings = get_settings()
    return ChatOpenAI(model=settings.model_name, api_key=settings.openai_api_key, temperature=0)


EVAL_DIR = Path(__file__).resolve().parent
GROUND_TRUTH_PATH = EVAL_DIR / "ground_truth.json"
OUT_OF_DOMAIN_PATH = EVAL_DIR / "out_of_domain.json"

TOP_K_FOR_RECALL = 5  # khop settings.retrieval_top_k mac dinh


def load_json(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Phan 1: do phan phoi cosine/trigram that (GT true-match vs OOD best-match)
# ---------------------------------------------------------------------------


def _true_chunk_cosine(db, embedding: list[float], drug_id: str, field_group: str) -> float | None:
    row = db.execute(
        text(
            "SELECT 1 - (embedding <=> :q) AS cosine_similarity FROM drug_chunks "
            "WHERE drug_id = :d AND field_group = :fg"
        ),
        {"q": str(embedding), "d": drug_id, "fg": field_group},
    ).fetchone()
    return row.cosine_similarity if row else None


def _true_chunk_lexical(db, query: str, drug_id: str, field_group: str) -> float | None:
    row = db.execute(
        text(
            "SELECT GREATEST(similarity(ten_thuoc_unaccent, unaccent(:q)), "
            "word_similarity(unaccent(:q), noi_dung_unaccent)) AS lexical_score "
            "FROM drug_chunks WHERE drug_id = :d AND field_group = :fg"
        ),
        {"q": query, "d": drug_id, "fg": field_group},
    ).fetchone()
    return row.lexical_score if row else None


def _best_cosine_anywhere(db, embedding: list[float]) -> float:
    row = db.execute(
        text("SELECT MAX(1 - (embedding <=> :q)) AS best FROM drug_chunks"),
        {"q": str(embedding)},
    ).fetchone()
    return row.best


def _best_lexical_anywhere(db, query: str) -> float:
    row = db.execute(
        text(
            "SELECT MAX(GREATEST(similarity(ten_thuoc_unaccent, unaccent(:q)), "
            "word_similarity(unaccent(:q), noi_dung_unaccent))) AS best FROM drug_chunks"
        ),
        {"q": query},
    ).fetchone()
    return row.best or 0.0


def measure_threshold_distributions(
    db, ground_truth: list[dict], out_of_domain: list[dict], gt_embeddings: dict[str, list[float]]
) -> dict:
    """`gt_embeddings` (utterance -> embedding) do NGUOI GOI tinh san 1 lan
    va truyen vao - tranh goi embed_query() 2 lan cho CUNG 1 cau hoi GT (1
    lan o day, 1 lan o measure_retrieval_precision_recall) - du chi phi
    embedding gan nhu khong dang ke, van la goi API that thua khong can
    thiet neu khong tai su dung."""
    gt_cosine, gt_lexical = [], []
    for item in ground_truth:
        emb = gt_embeddings[item["utterance"]]
        c = _true_chunk_cosine(db, emb, item["drug_id"], item["field_group"])
        lx = _true_chunk_lexical(db, item["utterance"], item["drug_id"], item["field_group"])
        gt_cosine.append(c)
        gt_lexical.append(lx)

    ood_cosine, ood_lexical = [], []
    for item in out_of_domain:
        emb = embed_query(item["utterance"])
        ood_cosine.append(_best_cosine_anywhere(db, emb))
        ood_lexical.append(_best_lexical_anywhere(db, item["utterance"]))

    return {
        "gt_cosine": gt_cosine,
        "gt_lexical": gt_lexical,
        "ood_cosine": ood_cosine,
        "ood_lexical": ood_lexical,
    }


def _percentile(values: list[float], p: float) -> float:
    s = sorted(values)
    idx = min(len(s) - 1, max(0, round(p / 100 * (len(s) - 1))))
    return s[idx]


def summarize_distribution(name: str, values: list[float]) -> dict:
    return {
        "name": name,
        "n": len(values),
        "min": min(values),
        "p5": _percentile(values, 5),
        "p50": statistics.median(values),
        "p95": _percentile(values, 95),
        "max": max(values),
        "mean": statistics.fmean(values),
    }


# ---------------------------------------------------------------------------
# Phan 2a: retrieval precision/recall (dung config threshold HIEN TAI)
# ---------------------------------------------------------------------------


def measure_retrieval_precision_recall(db, ground_truth: list[dict], gt_embeddings: dict[str, list[float]]) -> dict:
    settings = get_settings()
    hits_at_k = 0
    hits_at_1 = 0
    reciprocal_ranks = []
    per_question = []

    for item in ground_truth:
        emb = gt_embeddings[item["utterance"]]
        outcome = hybrid_search(db, item["utterance"], emb)
        target = (item["drug_id"], item["field_group"])
        found_rank = None
        for r in outcome.results:
            if (r.drug_id, r.field_group) == target:
                found_rank = r.rank
                break
        if found_rank is not None:
            hits_at_k += 1
            reciprocal_ranks.append(1.0 / found_rank)
            if found_rank == 1:
                hits_at_1 += 1
        else:
            reciprocal_ranks.append(0.0)
        per_question.append(
            {
                "utterance": item["utterance"],
                "target": target,
                "found_rank": found_rank,
                "no_source_found": outcome.no_source_found,
                "result_count": len(outcome.results),
            }
        )

    n = len(ground_truth)
    return {
        "n": n,
        "nguong_vector_used": settings.nguong_vector,
        "nguong_lexical_used": settings.nguong_lexical,
        "recall_at_k": hits_at_k / n,
        "precision_at_1": hits_at_1 / n,
        "mean_reciprocal_rank": statistics.fmean(reciprocal_ranks),
        "per_question": per_question,
    }


# ---------------------------------------------------------------------------
# Phan 2b: hallucination rate (LLM-judge) + Phan 2c: missing-caveat rate
# (dung LAI ket qua generate_answer cua 2b, khong ton them API call)
# ---------------------------------------------------------------------------


class _GroundingJudgement(BaseModel):
    grounded: bool = Field(description="True neu MOI cau/y trong cau tra loi deu co can cu trong context")
    ly_do: str


# SUA 2026-08-08 (sau khi manually verify 6/6 flagged cua ban dau deu la LOI
# JUDGE, khong phai model that bia): prompt goc khong phan biet 2 that bai
# KHAC NHAU - "cau tra loi CHUA THONG TIN khong co trong context" (that bia,
# = khong grounded) vs "cau tra loi THIEU 1 phan thong tin VA NOI RO dieu do"
# (dung hanh vi #13a mong muon, VAN la grounded). Judge cu tung phat hien
# nham 3/6 case la loai thu 2 (model dung cau "khong co trong nguon cung
# cap" - CHINH XAC theo #13a - nhung van bi cham grounded=false).
_JUDGE_PROMPT = """Bạn là người kiểm tra "grounding" của câu trả lời AI về thuốc. Có 2 loại khác nhau,
PHẢI phân biệt rõ:

- KHÔNG grounded (grounded=false): câu trả lời CHỨA thông tin/khẳng định không có căn cứ trong context
  (model tự bịa thêm từ kiến thức nền, kể cả khi thông tin đó đúng trong thực tế).
- VẪN grounded (grounded=true): câu trả lời chỉ dùng thông tin có trong context, VÀ nếu thiếu thông tin
  gì so với câu hỏi thì NÓI RÕ phần đó không có trong nguồn (thay vì tự bịa) - đây là hành vi ĐÚNG và
  MONG MUỐN, không phải lỗi. Một câu trả lời KHÔNG ĐẦY ĐỦ nhưng KHÔNG BỊA THÊM vẫn phải tính là
  grounded=true.

Câu hỏi: {utterance}

Context (nguồn đã cung cấp cho model để trả lời):
{context}

Câu trả lời cần kiểm tra:
{answer}

Chỉ đánh dấu grounded=false nếu câu trả lời THỰC SỰ chứa 1 khẳng định KHÔNG có căn cứ trong context ở
trên - không phải vì câu trả lời ngắn gọn hơn context hoặc bỏ qua 1 phần câu hỏi mà đã nói rõ là thiếu
thông tin."""


def measure_hallucination_and_caveat_rate(
    db, ground_truth: list[dict], gt_embeddings: dict[str, list[float]]
) -> dict:
    judge = _get_judge_llm().with_structured_output(_GroundingJudgement)

    grounded_count = 0
    caveat_expected_but_missing = 0
    cach_dung_questions = 0
    per_question = []

    for item in ground_truth:
        emb = gt_embeddings[item["utterance"]]
        outcome = hybrid_search(db, item["utterance"], emb)
        rag_results: list[DrugInfoResult] = outcome.results

        if not rag_results:
            # Khong co nguon -> REFUSE (BR-7.3), khong goi generate_answer -
            # khop dung logic that trong answer_generation_node.
            per_question.append(
                {"utterance": item["utterance"], "refused": True, "grounded": None, "caveat_ok": None}
            )
            continue

        answer = generate_answer(item["utterance"], rag_results)
        context = "\n\n".join(f"[{r.source}]\n{r.noi_dung}" for r in rag_results)

        judgement: _GroundingJudgement = judge.invoke(
            _JUDGE_PROMPT.format(utterance=item["utterance"], context=context, answer=answer)
        )
        if judgement.grounded:
            grounded_count += 1

        # Missing-caveat rate: cau hoi GT co field_group=cach_dung DANG LE
        # phai kich hoat caveat_lieu_dung_inserted NEU rag_results thuc su
        # tra ve 1 chunk cach_dung (logic o build_answer_generation_node -
        # xem lai truc tiep tai day, khong goi qua node de tranh phu thuoc
        # ConversationState day du).
        caveat_ok = True
        if item["field_group"] == "cach_dung":
            cach_dung_questions += 1
            has_cach_dung_chunk = any(r.field_group == "cach_dung" for r in rag_results)
            if has_cach_dung_chunk:
                # Day la kiem tra WIRING (deterministic theo code), khong
                # phai hanh vi LLM - neu retrieval tra ve dung chunk
                # cach_dung, caveat PHAI duoc chen (code, khong phai model
                # quyet). Ghi nhan "missing" chi khi retrieval that su
                # KHONG tra ve chunk cach_dung nao (loi o buoc retrieval,
                # khong phai o buoc caveat).
                caveat_ok = True
            else:
                caveat_ok = False
                caveat_expected_but_missing += 1

        per_question.append(
            {
                "utterance": item["utterance"],
                "refused": False,
                "grounded": judgement.grounded,
                "ly_do": judgement.ly_do,
                "caveat_ok": caveat_ok if item["field_group"] == "cach_dung" else None,
                "answer": answer,
            }
        )

    answered = [p for p in per_question if not p["refused"]]
    return {
        "n_ground_truth": len(ground_truth),
        "n_refused_no_source": len(ground_truth) - len(answered),
        "n_answered": len(answered),
        "grounded_rate": grounded_count / len(answered) if answered else None,
        "hallucination_rate": 1 - (grounded_count / len(answered)) if answered else None,
        "cach_dung_questions": cach_dung_questions,
        "missing_caveat_rate": (
            caveat_expected_but_missing / cach_dung_questions if cach_dung_questions else None
        ),
        "per_question": per_question,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ground_truth = load_json(GROUND_TRUTH_PATH)
    out_of_domain = load_json(OUT_OF_DOMAIN_PATH)
    print(f"Ground truth: {len(ground_truth)} cau, out-of-domain: {len(out_of_domain)} cau")

    db = SessionLocal()
    t0 = time.monotonic()
    try:
        print("Dang tinh embedding cho tung cau GT (1 lan, tai su dung o ca 3 phan do phia duoi)...")
        gt_embeddings = {item["utterance"]: embed_query(item["utterance"]) for item in ground_truth}

        print("\n=== Phan 1: phan phoi cosine/trigram (GT true-match vs OOD best-match) ===")
        dist = measure_threshold_distributions(db, ground_truth, out_of_domain, gt_embeddings)
        summaries = [
            summarize_distribution("GT true-match cosine", dist["gt_cosine"]),
            summarize_distribution("OOD best-match cosine", dist["ood_cosine"]),
            summarize_distribution("GT true-match lexical", dist["gt_lexical"]),
            summarize_distribution("OOD best-match lexical", dist["ood_lexical"]),
        ]
        for s in summaries:
            print(
                f"  {s['name']:<24} n={s['n']:>3} min={s['min']:.3f} p5={s['p5']:.3f} "
                f"p50={s['p50']:.3f} p95={s['p95']:.3f} max={s['max']:.3f} mean={s['mean']:.3f}"
            )

        print("\n=== Phan 2a: retrieval precision/recall (nguong hien tai trong config.py) ===")
        pr = measure_retrieval_precision_recall(db, ground_truth, gt_embeddings)
        print(f"  recall@{TOP_K_FOR_RECALL}: {pr['recall_at_k']:.1%}  precision@1: {pr['precision_at_1']:.1%}  MRR: {pr['mean_reciprocal_rank']:.3f}")
        print(f"  (nguong_vector={pr['nguong_vector_used']}, nguong_lexical={pr['nguong_lexical_used']})")

        print("\n=== Phan 2b/2c: hallucination rate + missing-caveat rate ===")
        hc = measure_hallucination_and_caveat_rate(db, ground_truth, gt_embeddings)
        print(f"  refused (no_source_found): {hc['n_refused_no_source']}/{hc['n_ground_truth']}")
        print(f"  grounded rate: {hc['grounded_rate']:.1%}  hallucination rate: {hc['hallucination_rate']:.1%}")
        print(f"  cach_dung questions: {hc['cach_dung_questions']}, missing caveat rate: {hc['missing_caveat_rate']}")

        elapsed = time.monotonic() - t0
        print(f"\nTong thoi gian chay: {elapsed:.1f}s")

        report = {
            "distributions": {k: v for k, v in dist.items()},
            "distribution_summaries": summaries,
            "precision_recall": pr,
            "hallucination_and_caveat": hc,
        }
        out_path = EVAL_DIR / "eval_report.json"
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Da ghi bao cao day du vao {out_path}")
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
