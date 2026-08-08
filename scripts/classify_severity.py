#!/usr/bin/env python3
"""Gan muc_nghiem_trong (Nhe/Trung binh/Nguy hiem) cho tung thuoc trong
data pharmacy/*/thuoc.json - rule-based tra bang theo `danh_muc` (tieu muc
goc cua trang nguon, xem schema.json), KHONG goi API/LLM nao.

Vi sao tra theo danh_muc thay vi ten thu muc chua file: danh_muc chi tiet
hon nhieu (52 gia tri, vd "Thuoc chong dong mau", "Thuoc tri tang nhan ap")
so voi 11 thu muc gop tho - phan loai sat tung nhom thuoc that hon la gop
chung ca thu muc lon "Thuoc tim mach va mau" lam 1 muc duy nhat.

Bang tra cuu duoc con nguoi (Architect + xac nhan 2026-08-04) tu doc tung
tieu muc va gan muc dua tren dac diem lam sang chung, dua tren so lieu
thuc te (vd ty le chi dinh HIV/viem gan B/C trong "Thuoc khang virus").
Nguyen tac an toan (BR-3.2): khong chac -> nang len, khong ha xuong.

Day chi la PRIOR/FALLBACK theo danh muc (BR-3.6) - khong thay the danh gia
per-thuoc bang RAG luc runtime (FEAT-007), va co 1 vai ngoai le (vd
glaucom trong nhom "Thuoc nho mat" da duoc tach thanh tieu muc rieng
"Thuoc tri tang nhan ap" ngay tu buoc gan danh_muc luc crawl).

Usage:
    python classify_severity.py                  # ap dung cho toan bo data pharmacy/*/thuoc.json
    python classify_severity.py --report-only     # chi in bao cao, khong ghi file
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data pharmacy"

NGUY_HIEM = "Nguy hiểm"
TRUNG_BINH = "Trung bình"
NHE = "Nhẹ"

# Danh_muc (tieu muc goc tu site) -> muc_nghiem_trong. Xem ly do tung nhom
# trong lich su thao luan thiet ke (2026-08-04) va business-rules.md §3.
SEVERITY_BY_DANH_MUC: dict[str, str] = {
    # --- Nguy hiem: benh man tinh de tro nang / thuoc cua so dieu tri hep /
    # duong dung nghiem trong / nguy co qua lieu ---
    "Thuốc tim mạch huyết áp": NGUY_HIEM,
    "Thuốc tim mạch và máu": NGUY_HIEM,
    "Thuốc tim mạch & máu": NGUY_HIEM,
    "Thuốc thần kinh": NGUY_HIEM,  # nhom gop chung, co the lan dong kinh/Parkinson - an toan truoc (BR-3.2)
    "Thuốc trị tiểu đường": NGUY_HIEM,
    "Thuốc tiêm chích": NGUY_HIEM,
    "Thuốc tiêm chích và dịch truyền": NGUY_HIEM,
    "Thuốc điều trị ung thư": NGUY_HIEM,
    "Thuốc kháng virus": NGUY_HIEM,  # 72% chi dinh HIV/viem gan B/C man tinh (so lieu thuc te)
    "Thuốc chống đông máu": NGUY_HIEM,  # vi du mau BR-3.1
    "Dịch truyền": NGUY_HIEM,
    "Thuốc chống trầm cảm": NGUY_HIEM,  # bo lieu -> tai phat/hoi chung cai
    "Thuốc xịt hen suyễn": NGUY_HIEM,  # bo lieu -> con hen cap
    "Thuốc an thần": NGUY_HIEM,  # = "thuoc ngu", trung kich ban redflag BR-6.7 (nguy co qua lieu)
    "Thuốc trị tăng nhãn áp": TRUNG_BINH,  # glaucom: hai thi luc lau dai, khong cap tinh ngay
    "Dung dịch tiêm": NGUY_HIEM,  # duong tiem, so luong nho nhung khong ro noi dung -> an toan truoc
    # --- Trung binh: can theo doi, khong cap cuu ngay tu 1 lieu ---
    "Thuốc kháng sinh": TRUNG_BINH,
    "Thuốc dạ dày": TRUNG_BINH,
    "Thuốc tiêu hoá": TRUNG_BINH,
    "Thuốc tiêu hoá & gan mật": TRUNG_BINH,
    "Thuốc trị mỡ máu": TRUNG_BINH,  # statin - quan trong dai han, khong cap tinh
    "Thuốc trị bệnh gan": TRUNG_BINH,  # lan ca thuoc dieu tri viem gan that, khong chi thuc pham chuc nang
    "Thuốc tăng cường tuần hoàn não": TRUNG_BINH,  # lan thuoc ke don that, khong chi TPCN
    "Thuốc trị tiêu chảy": TRUNG_BINH,
    "Thuốc trị thiếu máu": TRUNG_BINH,
    "Thuốc lợi tiểu": TRUNG_BINH,  # thuong di kem dieu tri suy tim/tang huyet ap
    "Thuốc trị trĩ, suy giãn tĩnh mạch": TRUNG_BINH,
    "Thuốc gan mật": TRUNG_BINH,
    "Thuốc bù điện giải": TRUNG_BINH,  # roi loan dien giai co the nghiem trong
    "Dinh dưỡng": TRUNG_BINH,  # dinh duong duong tinh mach, boi canh benh vien
    # --- Nhe: bo lieu khong gay hau qua cap tinh ---
    "Thuốc bôi ngoài da": NHE,
    "Thuốc bổ": NHE,
    "Thuốc nhỏ mắt": NHE,
    "Siro bổ": NHE,
    "Thuốc tai mũi họng": NHE,
    "Thuốc Mắt, Tai, Mũi, Họng": NHE,
    "Thuốc trị mụn": NHE,
    "Thuốc trị táo bón": NHE,
    "Thuốc tăng cường sức đề kháng": NHE,
    "Thuốc sát khuẩn": NHE,
    "Thuốc xịt mũi": NHE,
    "Thuốc cầm máu": NHE,
    "Bổ xương khớp": NHE,
    "Thuốc nhỏ tai": NHE,
    "Dung dịch súc miệng": NHE,
    "Thuốc tra mắt": NHE,
    "Thuốc trị viêm xoang": NHE,
    "Thuốc bôi răng miệng": NHE,
    "Dầu gội trị gàu": NHE,
    "Siro tiêu hoá": NHE,
    "Thuốc bôi sẹo liền sẹo": NHE,
    "Ống hít mũi": NHE,
    "Thuốc điều trị béo phì": NHE,
}

# Khong phai thuoc - loai khoi RAG thay vi gan muc nghiem trong (xem báo cáo).
NON_DRUG_DANH_MUC = {"Dụng cụ y tế"}


def classify(danh_muc: str) -> str | None:
    if danh_muc in NON_DRUG_DANH_MUC:
        return None
    return SEVERITY_BY_DANH_MUC.get(danh_muc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-only", action="store_true", help="Chi in bao cao, khong ghi file")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    total = 0
    counts = {NGUY_HIEM: 0, TRUNG_BINH: 0, NHE: 0}
    unmapped: dict[str, int] = {}
    non_drug: list[str] = []

    for path in sorted(DATA_DIR.glob("*/thuoc.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        kept = []
        for d in data:
            danh_muc = d.get("danh_muc", "")
            if danh_muc in NON_DRUG_DANH_MUC:
                non_drug.append(f"{path.parent.name}/{d.get('ten_thuoc')}")
                continue  # loai khoi data, khong phai thuoc
            tier = classify(danh_muc)
            if tier is None:
                unmapped[danh_muc] = unmapped.get(danh_muc, 0) + 1
                kept.append(d)
                continue
            if d.get("muc_nghiem_trong") != tier:
                d["muc_nghiem_trong"] = tier
                changed = True
            counts[tier] += 1
            total += 1
            kept.append(d)

        if not args.report_only and (changed or len(kept) != len(data)):
            with path.open("w", encoding="utf-8") as f:
                json.dump(kept, f, ensure_ascii=False, indent=2)
                f.write("\n")
        print(f"[{path.parent.name}] {len(data)} -> {len(kept)} (loai {len(data) - len(kept)} khong phai thuoc)")

    print()
    print("TONG:", total, "thuoc da gan muc_nghiem_trong")
    for tier, n in counts.items():
        print(f"  {tier}: {n}")
    if unmapped:
        print()
        print("CANH BAO - danh_muc chua co trong bang tra cuu (giu nguyen, chua gan muc):")
        for dm, n in sorted(unmapped.items(), key=lambda x: -x[1]):
            print(f"  {n:4d}  {dm!r}")
    if non_drug:
        print()
        print(f"Da loai {len(non_drug)} ban ghi khong phai thuoc:")
        for n in non_drug:
            print("  -", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
