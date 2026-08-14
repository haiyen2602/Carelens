#!/usr/bin/env python3
"""Vong 4, muc 2.2/2.6 (kickoff-prompt-vong-4.md) - xac minh THAT
classify_drug_reply_plausibility() (backend/services/classification.py) qua
OpenAI THAT - KHONG chay trong `pytest tests/` mac dinh (giong eval/
safety_llm_check.py) vi ton chi phi API that, chay TAY khi can xac nhan chat
luong prompt, khong phai moi lan CI.

Bao phu dung 3 nhom kickoff muc 2.6 yeu cau:
  1. Case bug that da tai hien (PHAI tra False - khong lien quan thuoc):
     "tôi buồn đi vệ sinh" (dung case tung khop nham Coveram 10/5 30v qua
     _search_distinct_drug_candidates()), "tôi thích ăn phở".
  2. Case hop le NGAN (PHAI tra True) - day la test QUAN TRONG NHAT theo
     kickoff: neu gate qua nghiem, tai tao dung van de "recall kem" da thay
     o kenh vector cu (NGUONG_VECTOR=0.60 tu choi ca "vitamin C"/
     "paracetamol"). Gom ca ten day du, viet tat, khong dau.
  3. Case mo ta hop le (khong co ten thuoc, dung kieu redescribe that -
     PHAI tra True): "thuốc hạ huyết áp", "thuốc màu trắng uống buổi sáng"...

Case bien (borderline) chay lap REPEAT_COUNT lan (dung idiom eval/
safety_llm_check.py) - khong tin 1 lan chay duy nhat, cung ly do da ap dung
cho #30 (dao dong that o temperature=0).

Ghi ket qua ra eval/drug_reply_gate_report.json.

Usage:
    python eval/drug_reply_gate_check.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services.classification import classify_drug_reply_plausibility  # noqa: E402

REPEAT_COUNT = 20  # cung nguong voi eval/safety_llm_check.py


@dataclass
class GateCase:
    id: str
    reply: str
    expect: bool  # True = phai duoc gate cho qua (lien quan thuoc)
    repeat: int = 1
    note: str = ""


@dataclass
class CaseResult:
    id: str
    reply: str
    expect: bool
    runs: list[bool] = field(default_factory=list)
    all_runs_match_expected: bool = False
    note: str = ""


# ---------------------------------------------------------------------------
# 1. Bug that da tai hien - PHAI tra False
# ---------------------------------------------------------------------------
BUG_REPRO_CASES = [
    GateCase(
        "bug_repro_ve_sinh",
        "tôi buồn đi vệ sinh",
        expect=False,
        repeat=REPEAT_COUNT,
        note="Dung case that tung khop nham Coveram 10/5 30v qua _search_distinct_drug_candidates()",
    ),
    GateCase(
        "bug_repro_an_pho",
        "tôi thích ăn phở",
        expect=False,
        repeat=REPEAT_COUNT,
        note="Case thu 2 tai hien cung loai bug (khop nham Bisoloc 5mg)",
    ),
    GateCase("bug_repro_greeting", "xin chào bạn khoẻ không", expect=False, repeat=5),
    GateCase("bug_repro_weather", "hôm nay trời đẹp quá", expect=False, repeat=5),
]

# ---------------------------------------------------------------------------
# 2. Case hop le NGAN - PHAI tra True. QUAN TRONG NHAT (kickoff muc 2.6) -
# day la test do "recall" cua gate, tranh lap lai loi kenh vector cu.
# ---------------------------------------------------------------------------
SHORT_VALID_CASES = [
    GateCase("short_paracetamol", "paracetamol", expect=True, repeat=REPEAT_COUNT),
    GateCase("short_vitamin_c", "vitamin C", expect=True, repeat=REPEAT_COUNT),
    GateCase("short_panadol_extra", "panadol extra", expect=True, repeat=REPEAT_COUNT),
    GateCase("short_no_diacritics", "vitamin c khong dau", expect=True, repeat=5),
    GateCase("short_abbreviation", "cefixim", expect=True, repeat=5),
    GateCase("short_brand_generic", "efferalgan", expect=True, repeat=5),
]

# ---------------------------------------------------------------------------
# 3. Mo ta hop le (redescribe that, khong co ten thuoc) - PHAI tra True
# ---------------------------------------------------------------------------
DESCRIPTIVE_VALID_CASES = [
    GateCase("desc_ha_huyet_ap", "thuốc hạ huyết áp", expect=True, repeat=REPEAT_COUNT),
    GateCase("desc_mau_trang", "thuốc màu trắng uống buổi sáng", expect=True, repeat=5),
    GateCase("desc_dau_bung", "thuốc tôi hay uống khi bị đau bụng", expect=True, repeat=5),
    GateCase("desc_tieu_hoa", "viên uống hỗ trợ tiêu hoá", expect=True, repeat=5),
    GateCase("desc_dau_dau", "thuốc trị đau đầu", expect=True, repeat=5),
]


def _run_case(case: GateCase) -> CaseResult:
    result = CaseResult(id=case.id, reply=case.reply, expect=case.expect, note=case.note)
    for _ in range(case.repeat):
        result.runs.append(classify_drug_reply_plausibility(case.reply))
    result.all_runs_match_expected = all(r == case.expect for r in result.runs)
    return result


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    all_cases = BUG_REPRO_CASES + SHORT_VALID_CASES + DESCRIPTIVE_VALID_CASES
    results = []
    total_calls = 0

    for case in all_cases:
        print(f"[chay] {case.id} (expect={case.expect}, repeat={case.repeat}) ...")
        r = _run_case(case)
        results.append(r)
        total_calls += case.repeat
        stability = f"{sum(1 for v in r.runs if v == case.expect)}/{len(r.runs)} khop expect"
        status = "PASS" if r.all_runs_match_expected else "FAIL"
        print(f"  -> [{status}] runs={r.runs} {stability}")

    report = {"total_llm_calls": total_calls, "results": [asdict(r) for r in results]}
    out_path = Path(__file__).resolve().parent / "drug_reply_gate_report.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDa ghi {out_path} - tong {total_calls} lan goi LLM that.")

    failed = [r for r in results if not r.all_runs_match_expected]
    print(f"\nTong ket: {len(results) - len(failed)}/{len(results)} case PASS.")
    if failed:
        print("Case FAIL:")
        for r in failed:
            print(f"  - {r.id}: {r.reply!r} expect={r.expect} runs={r.runs}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
