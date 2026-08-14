#!/usr/bin/env python3
"""Vong 4, muc 3.2 (kickoff-prompt-vong-4.md) - tune NGUONG_CAO/NGUONG_CACH_BIET
cho quyet dinh "bo qua LLM hay khong" o tang 2 cua fuzzy 2 tang. Dung DUNG ham
production `fuzzy_name_search()` (backend/services/retrieval.py), khong viet
lai logic SQL rieng cho eval - cung nguyen tac da dung o eval/tune_candidate_
retrieval.py.

QUAN TRONG - phat hien truoc khi sweep (khong doan so tu vi du kickoff):
diem so that cua `similarity()` tren ten_thuoc_unaccent THAP HON NHIEU vi du
0.90 kickoff dua ra (test tay: "vitamin C" dung top-1 chi 0.43, "Paracetamol "
dung top-1 chi 0.26 - similarity() la ham DOI XUNG, bi phat vi chenh lech do
dai giua query ngan va ten thuoc day du). Neu NGUONG_CAO=0.90 nhu vi du, nhanh
"bo qua LLM" se GAN NHU KHONG BAO GIO kich hoat - sweep nay do that pham vi
diem so hop ly truoc khi chot so.

Do TREN CA 4 TAP (2 tap dau da co tu truoc, 2 tap sau MOI - phan hoi review
"GT hien tai toan cau day du co ten thuoc, chua dai dien dung use-case cau
ngan/viet tat cua muc 3"):
  - eval/ground_truth.json (32 cau day du, biet truoc drug_id dung).
  - eval/out_of_domain.json (15 cau - nonexistent_drug/severe_typo/
    unrelated_text) - do nhanh "bo qua LLM" co bao nhieu lan tu tin sai.
  - eval/short_name_ground_truth.json (MOI, 10 cau) - ten thuong hieu NGAN/
    viet tat (co/khong ham luong) DA XAC MINH TAY la unique trong corpus
    (khong trung SKU nao khac) truoc khi dua vao - dai dien dung use-case
    that cua muc 3 (bo tra loi luc reply-parsing/redescribe thuong ngan hon
    cau hoi day du nhieu).
  - eval/short_name_ambiguous.json (MOI, 10 cau) - ten NGAN nhung THAT SU
    khong co dap an unique (nhieu SKU khac hang/lieu cung ten trong corpus,
    vd "vitamin C"/"vitamin b1"/"noklot") HOAC khong ton tai (panadol extra,
    #muc 1.2) - KHONG do precision (khong co "dung"), chi do gap co du THAP
    de KHONG fast-path (an toan) hay khong.

  Tat ca 4 tap do CHUNG 1 metric "GT skip-precision" (rieng 2 tap dau) va
  "khong fast-path nham" (rieng short_name_ambiguous.json) - KHONG gop lan
  "dung/sai" cua tap co dap an voi "an toan/khong an toan" cua tap khong co
  dap an, tranh nham lan y nghia 2 loai chi so khac nhau.

Chi phi: 0 - fuzzy_name_search() khong goi API nao (khong embedding, khong
LLM), toan bo sweep la truy van DB thuan.

Usage:
    python eval/tune_fuzzy_tier1.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db.base import SessionLocal  # noqa: E402
from backend.services.retrieval import fuzzy_name_search  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
GROUND_TRUTH_PATH = EVAL_DIR / "ground_truth.json"
OUT_OF_DOMAIN_PATH = EVAL_DIR / "out_of_domain.json"
SHORT_NAME_GROUND_TRUTH_PATH = EVAL_DIR / "short_name_ground_truth.json"
SHORT_NAME_AMBIGUOUS_PATH = EVAL_DIR / "short_name_ambiguous.json"
# MOI 2026-08-14 (phan hoi review): 15 cau OOD cu deu la cau hoi DAY DU
# ("Adderall 20mg dung de lam gi?"), khong dai dien dung use-case NGAN cua
# muc 3 - can biet 0.238 (tran cu) co con la tran that voi brand NGAN khong
# ton tai hay khong.
SHORT_OOD_PATH = EVAL_DIR / "short_ood_nonexistent.json"

# Grid sweep - pham vi thap hon nhieu vi du kickoff (0.90), dua theo diem so
# THAT quan sat duoc (0.15-0.45 cho top-1 dung). Buoc nho o vung quan sat
# duoc diem thuc te tap trung.
NGUONG_CAO_GRID = [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60]
NGUONG_CACH_BIET_GRID = [0.03, 0.05, 0.08, 0.10, 0.15]
# MOI 2026-08-14 - sweep MIN trong dung khoang 0.25-0.30 (buoc 0.01), CO
# DINH biet=0.05 (da xac nhan la tuyen phong thu chinh o lan sweep truoc) -
# tim diem CHINH XAC GT-short bat dau tut duoi 100%, de chon nguong ngay
# TRUOC diem do thay vi dung o mac luoi tho dau tien vuot OOD.
FINE_NGUONG_CAO_GRID = [round(0.25 + i * 0.01, 2) for i in range(6)]  # 0.25..0.30
FINE_NGUONG_CACH_BIET = 0.05


def _load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_correctness_set(db, items: list[dict], measure_latency: bool = False) -> tuple[list[dict], float]:
    """Dung chung cho ca 2 tap CO dap an (ground_truth.json day du +
    short_name_ground_truth.json ngan/viet tat) - tra ve list run + tong
    thoi gian (ms, chi tinh khi measure_latency=True, tranh cong don 2 lan)."""
    runs = []
    t_total = 0.0
    for item in items:
        t0 = time.monotonic()
        top5 = fuzzy_name_search(db, item["utterance"], top_k=5)
        if measure_latency:
            t_total += (time.monotonic() - t0) * 1000
        top1_score = top5[0].score if top5 else 0.0
        top2_score = top5[1].score if len(top5) > 1 else 0.0
        runs.append(
            {
                "utterance": item["utterance"],
                "expect_drug_id": item["drug_id"],
                "top1_drug_id": top5[0].drug_id if top5 else None,
                "top1_score": top1_score,
                "gap": top1_score - top2_score,
                "top1_correct": bool(top5) and top5[0].drug_id == item["drug_id"],
            }
        )
    return runs, t_total


def _run_no_answer_set(db, items: list[dict]) -> list[dict]:
    """Dung chung cho ca 2 tap KHONG co dap an unique (out_of_domain.json +
    short_name_ambiguous.json) - chi ghi lai score/gap de kiem tra AN TOAN
    (khong fast-path nham), khong co khai niem "dung/sai"."""
    runs = []
    for item in items:
        top5 = fuzzy_name_search(db, item["utterance"], top_k=5)
        top1_score = top5[0].score if top5 else 0.0
        top2_score = top5[1].score if len(top5) > 1 else 0.0
        runs.append(
            {
                "utterance": item["utterance"],
                "label": item.get("category", "ambiguous"),
                "top1_ten_thuoc": top5[0].ten_thuoc if top5 else None,
                "top1_score": top1_score,
                "gap": top1_score - top2_score,
            }
        )
    return runs


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    gt_full = _load(GROUND_TRUTH_PATH)
    ood = _load(OUT_OF_DOMAIN_PATH)
    gt_short = _load(SHORT_NAME_GROUND_TRUTH_PATH)
    ambiguous = _load(SHORT_NAME_AMBIGUOUS_PATH)
    short_ood = _load(SHORT_OOD_PATH)

    db = SessionLocal()

    gt_full_runs, t_full = _run_correctness_set(db, gt_full, measure_latency=True)
    gt_short_runs, t_short = _run_correctness_set(db, gt_short, measure_latency=True)
    ood_runs = _run_no_answer_set(db, ood)
    ambiguous_runs = _run_no_answer_set(db, ambiguous)
    short_ood_runs = _run_no_answer_set(db, short_ood)

    db.close()

    all_latency_ms = t_full + t_short
    all_latency_n = len(gt_full) + len(gt_short)
    print(f"Latency fuzzy_name_search() that: {all_latency_ms / all_latency_n:.1f}ms/cau (trung binh {all_latency_n} cau)")

    # Gop 2 tap CO dap an lam 1 pool danh gia chung (danh dau nguon rieng de
    # con bao cao tach) - dung y "khong gop lan 2 loai chi so khac nhau"
    # (docstring dau file): day van la 1 loai chi so (dung/sai vs expect_
    # drug_id), chi khac NGUON cau hoi (day du vs ngan).
    for r in gt_full_runs:
        r["source"] = "full_sentence"
    for r in gt_short_runs:
        r["source"] = "short_name"
    gt_all = gt_full_runs + gt_short_runs

    print(f"\nPhan bo diem top-1 CAU DAY DU (32 cau, top1_correct=True): "
          f"{[round(r['top1_score'], 3) for r in gt_full_runs if r['top1_correct']]}")
    print(f"Phan bo diem top-1 CAU NGAN/VIET TAT ({len(gt_short)} cau, top1_correct=True): "
          f"{[round(r['top1_score'], 3) for r in gt_short_runs if r['top1_correct']]}")
    for r in gt_short_runs:
        if not r["top1_correct"]:
            print(f"  [CANH BAO] short-name case SAI: {r['utterance']!r} expect={r['expect_drug_id']} "
                  f"top1={r['top1_drug_id']} score={r['top1_score']:.3f}")

    no_answer_all = ood_runs + ambiguous_runs
    print(f"\nPhan bo diem top-1 OOD cau DAY DU (15 cau, khong lien quan/khong ton tai): "
          f"max={max(r['top1_score'] for r in ood_runs):.4f}")
    print(f"Phan bo diem top-1 OOD brand NGAN khong ton tai ({len(short_ood)} cau, MOI): "
          f"max={max(r['top1_score'] for r in short_ood_runs):.4f} "
          f"(so voi OOD day du: {'THAP HON' if max(r['top1_score'] for r in short_ood_runs) < max(r['top1_score'] for r in ood_runs) else 'CAO HON'})")
    for r in sorted(short_ood_runs, key=lambda x: -x["top1_score"])[:5]:
        print(f"    {r['utterance']!r:15s} -> top1={r['top1_ten_thuoc']!r:35s} score={r['top1_score']:.4f} gap={r['gap']:.4f}")
    print(f"Phan bo diem top-1 AMBIGUOUS ({len(ambiguous)} cau, ten that nhung nhieu SKU/khong ton tai): "
          f"max={max(r['top1_score'] for r in ambiguous_runs):.4f}, "
          f"gap max={max(r['gap'] for r in ambiguous_runs):.4f}")

    # Tran an toan CUOI CUNG = max ca 2 nguon OOD (day du + ngan) - khong lac
    # quan chi vi 10 mau moi thap hon, dung so CAO HON de tinh margin.
    ood_all_runs = ood_runs + short_ood_runs
    ood_ceiling = max(r["top1_score"] for r in ood_all_runs)
    print(f"\n>>> TRAN AN TOAN CUOI (max ca OOD day du + OOD ngan, {len(ood_all_runs)} cau) = {ood_ceiling:.4f}")

    # Sweep grid - do CA 2 pool CUNG LUC de thay ro trade-off precision (tren
    # tap co dap an) vs an toan (tren tap khong co dap an), gom ca nguon
    # full_sentence rieng vs short_name rieng dam bao khong "an" loi cua 1
    # nguon vao trung binh chung.
    print("\n=== Sweep NGUONG_CAO x NGUONG_CACH_BIET ===")
    header = (
        f"{'cao':>6} {'biệt':>6} {'GT-full skip%':>14} {'prec':>6} "
        f"{'GT-short skip%':>15} {'prec':>6} {'OOD skip':>9} {'Ambig skip':>11}"
    )
    print(header)
    sweep_results = []
    for cao in NGUONG_CAO_GRID:
        for biet in NGUONG_CACH_BIET_GRID:
            def _skip(runs):
                return [r for r in runs if r["top1_score"] >= cao and r["gap"] >= biet]

            full_skip = _skip(gt_full_runs)
            full_skip_correct = [r for r in full_skip if r["top1_correct"]]
            full_skip_pct = len(full_skip) / len(gt_full_runs) * 100
            full_prec = (len(full_skip_correct) / len(full_skip) * 100) if full_skip else None

            short_skip = _skip(gt_short_runs)
            short_skip_correct = [r for r in short_skip if r["top1_correct"]]
            short_skip_pct = len(short_skip) / len(gt_short_runs) * 100
            short_prec = (len(short_skip_correct) / len(short_skip) * 100) if short_skip else None

            ood_skip_n = len(_skip(ood_all_runs))  # gop ca OOD day du + OOD ngan moi
            ambiguous_skip_n = len(_skip(ambiguous_runs))

            row = {
                "nguong_cao": cao,
                "nguong_cach_biet": biet,
                "gt_full_skip_pct": full_skip_pct,
                "gt_full_skip_precision": full_prec,
                "gt_short_skip_pct": short_skip_pct,
                "gt_short_skip_precision": short_prec,
                "ood_skip_count": ood_skip_n,
                "ambiguous_skip_count": ambiguous_skip_n,
            }
            sweep_results.append(row)
            fp = f"{full_prec:.0f}%" if full_prec is not None else "n/a"
            sp = f"{short_prec:.0f}%" if short_prec is not None else "n/a"
            print(f"{cao:>6.2f} {biet:>6.2f} {full_skip_pct:>13.0f}% {fp:>6} "
                  f"{short_skip_pct:>14.0f}% {sp:>6} {ood_skip_n:>9} {ambiguous_skip_n:>11}")

    # Sweep MIN 0.25-0.30, buoc 0.01, biet CO DINH 0.05 - tim diem CHINH XAC
    # GT-short bat dau tut duoi 100%, de chon nguong ngay TRUOC diem do (margin
    # rong hon 0.012 hien tai) thay vi dung o mac luoi tho dau tien vuot OOD.
    print(f"\n=== Sweep MIN 0.25-0.30 (buoc 0.01, cách_biệt cố định {FINE_NGUONG_CACH_BIET}) ===")
    print(f"{'cao':>6} {'GT-full skip%':>14} {'GT-short skip%':>15} {'short case truot (neu co)':>30} "
          f"{'OOD skip':>9} {'Ambig skip':>11} {'margin tren OOD ceiling':>24}")
    fine_results = []
    for cao in FINE_NGUONG_CAO_GRID:
        biet = FINE_NGUONG_CACH_BIET

        def _skip(runs, cao=cao, biet=biet):
            return [r for r in runs if r["top1_score"] >= cao and r["gap"] >= biet]

        full_skip = _skip(gt_full_runs)
        full_skip_pct = len(full_skip) / len(gt_full_runs) * 100

        short_skip = _skip(gt_short_runs)
        short_skip_pct = len(short_skip) / len(gt_short_runs) * 100
        short_missed = [r["utterance"] for r in gt_short_runs if r not in short_skip]

        ood_skip_n = len(_skip(ood_all_runs))
        ambiguous_skip_n = len(_skip(ambiguous_runs))
        margin = cao - ood_ceiling

        fine_results.append(
            {
                "nguong_cao": cao,
                "nguong_cach_biet": biet,
                "gt_full_skip_pct": full_skip_pct,
                "gt_short_skip_pct": short_skip_pct,
                "gt_short_missed_cases": short_missed,
                "ood_skip_count": ood_skip_n,
                "ambiguous_skip_count": ambiguous_skip_n,
                "margin_over_ood_ceiling": margin,
            }
        )
        missed_str = ", ".join(short_missed) if short_missed else "-"
        print(f"{cao:>6.2f} {full_skip_pct:>13.0f}% {short_skip_pct:>14.0f}% {missed_str:>30} "
              f"{ood_skip_n:>9} {ambiguous_skip_n:>11} {margin:>+23.4f}")

    report = {
        "gt_full_runs": gt_full_runs,
        "gt_short_runs": gt_short_runs,
        "ood_runs": ood_runs,
        "short_ood_runs": short_ood_runs,
        "ambiguous_runs": ambiguous_runs,
        "ood_ceiling_combined": ood_ceiling,
        "sweep": sweep_results,
        "fine_sweep_0_25_to_0_30": fine_results,
        "avg_latency_ms": all_latency_ms / all_latency_n,
    }
    out_path = EVAL_DIR / "fuzzy_tier1_tuning.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDa ghi {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
