#!/usr/bin/env python3
"""Phase 2 (specs/build-kickoff-prompt.md): chunking data pharmacy/*/thuoc.json
thanh 4 chunk/thuoc theo field_group, dung cho RAG (pgvector).

Chunking strategy day du: specs/chatbot-rag-design.md muc 3.1.

    field_group     field goc gop lai
    -------------   --------------------------------------------
    cong_dung       tac_dung
    tac_dung_phu    tac_dung_phu + luu_y_dac_biet
    cach_dung       huong_dan_su_dung + lieu_dung + duong_dung
    bao_quan        huong_dan_bao_quan

thoi_diem_dung KHONG BAO GIO duoc dua vao bat ky chunk nao - day la du
lieu ca nhan hoa theo don bac si (PrescriptionDTO.items[].thoi_diem_dung),
khong phai kien thuc chung cua thuoc (xem chatbot-rag-design.md muc 3.1).

1 field_group bi bo qua (khong tao chunk) neu toan bo noi dung goc cua no
rong - tranh embed 1 chunk trong vo nghia (vd huong_dan_bao_quan khong
bat buoc trong schema, co the rong o vai thuoc).

TACH CHUNK QUA DAI (phat hien 2026-08-08 luc chay Phase 3 that): 1 so thuoc
phoi hop nhieu hoat chat (vd Triplixam 3 thanh phan) co luu_y_dac_biet rat
dai, chunk tac_dung_phu vuot 8192 token - gioi han input cua OpenAI embedding
API. KHONG cat cut mat thong tin (day la du lieu an toan - chong chi dinh,
tuong tac thuoc) - thay vao do TACH thanh nhieu chunk cung field_group, moi
chunk van co du prefix, tach o ranh gioi tung muc luu_y_dac_biet (khong cat
giua 1 cau). 1 field_group co the sinh ra >1 chunk neu qua dai.

Usage:
    python chunk_drugs.py                  # chunk toan bo, in bao cao, ghi ra output
    python chunk_drugs.py --report-only     # chi in bao cao, khong ghi file
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from pathlib import Path

import tiktoken

DATA_DIR = Path(__file__).resolve().parent.parent / "data pharmacy"
OUTPUT_PATH = DATA_DIR / "_chunks.jsonl"

# Gioi han that cua OpenAI la 8192 token/input - de margin an toan cho phan
# prefix cong them sau khi dong goi (xem _pack_pieces).
MAX_TOKENS_PER_CHUNK = 7500
_ENCODING = tiktoken.encoding_for_model("text-embedding-3-small")


def _count_tokens(text: str) -> int:
    return len(_ENCODING.encode(text))

FIELD_GROUPS: list[tuple[str, list[str]]] = [
    ("cong_dung", ["tac_dung"]),
    ("tac_dung_phu", ["tac_dung_phu", "luu_y_dac_biet"]),
    ("cach_dung", ["huong_dan_su_dung", "lieu_dung", "duong_dung"]),
    ("bao_quan", ["huong_dan_bao_quan"]),
]

# Nhan tung field con trong 1 chunk gop nhieu field, giup answer_generation
# (LLM) va nguoi doc phan biet duoc phan nao la phan nao trong 1 chunk gop.
FIELD_LABELS: dict[str, str] = {
    "tac_dung": None,  # chunk cong_dung chi co 1 field, khong can nhan
    "tac_dung_phu": "Tác dụng phụ",
    "luu_y_dac_biet": "Lưu ý đặc biệt",
    "huong_dan_su_dung": "Cách dùng",
    "lieu_dung": "Liều dùng",
    "duong_dung": "Đường dùng",
    "huong_dan_bao_quan": None,  # chunk bao_quan chi co 1 field
}


def _field_pieces(thuoc: dict, field: str) -> list[str]:
    """Tra ve list 'manh' da gan nhan cho 1 field - luu_y_dac_biet tach thanh
    1 manh/muc (Chong chi dinh, Than trong...) de co the phan phoi qua nhieu
    chunk ma khong cat giua 1 muc; cac field khac la 1 manh duy nhat."""
    label = FIELD_LABELS.get(field)
    if field == "luu_y_dac_biet":
        items = [v for v in (thuoc.get(field) or []) if v]
        return [f"{label}: {item}" if label else item for item in items]
    text = (thuoc.get(field) or "").strip()
    if not text:
        return []
    return [f"{label}: {text}" if label else text]


def _pack_pieces(pieces: list[str], prefix: str) -> list[str]:
    """Dong goi cac manh vao it nhat co the cac khoi text, moi khoi (ke ca
    prefix) khong vuot MAX_TOKENS_PER_CHUNK.

    QUAN TRONG: kiem tra bang cach do TOKEN THAT cua chuoi da ghep
    (_count_tokens goi lai moi buoc), KHONG cong don uoc luong token tung
    manh rieng le - tokenize khong cong tinh (ghep 2 chuoi lai co the ra so
    token khac tong 2 so token rieng), cong don se le dan qua nhieu manh va
    vuot gioi han that (da bat duoc bang test, xem
    test_oversized_field_group_splits_into_multiple_chunks_under_token_limit)."""

    def fits(body: str) -> bool:
        return _count_tokens(f"{prefix}\n\n{body}") <= MAX_TOKENS_PER_CHUNK

    # Buoc 1: neu 1 manh don le da vuot gioi han ngay ca khi dung rieng no
    # (hiem, vd 1 muc luu_y_dac_biet cuc dai), cat truoc thanh cac cau nho hon.
    units: list[str] = []
    for piece in pieces:
        if fits(piece):
            units.append(piece)
        else:
            sentences = [s.strip() for s in piece.split(". ") if s.strip()]
            units.extend(sentences or [piece])

    # Buoc 2: dong goi tham lam, luon xac nhan bang fits() tren chuoi da ghep that.
    groups: list[str] = []
    current: list[str] = []
    for unit in units:
        trial = current + [unit]
        if fits(" ".join(trial)):
            current = trial
        else:
            if current:
                groups.append(" ".join(current))
            current = [unit]
    if current:
        groups.append(" ".join(current))
    return groups


def _build_prefix(thuoc: dict) -> str:
    """"Thuốc: {ten_thuoc} ({ham_luong}, {dang_thuoc}) — {danh_muc}" - nhung bo qua
    phan ngoac neu ca ham_luong lan dang_thuoc deu rong, va bo dau phay thua neu
    chi 1 trong 2 rong (du ca 2 field nay bat buoc trong schema, van co vai ban ghi
    lot qua - xem ghi chu 2026-08-08). Khong de lai "(, )" hoac "(x, )" trong prefix."""
    ten_thuoc = thuoc.get("ten_thuoc", "")
    danh_muc = thuoc.get("danh_muc", "")
    meta = [v for v in (thuoc.get("ham_luong", ""), thuoc.get("dang_thuoc", "")) if v]
    meta_str = f" ({', '.join(meta)})" if meta else ""
    return f"Thuốc: {ten_thuoc}{meta_str} — {danh_muc}"


def build_chunks_for_drug(thuoc: dict) -> list[dict]:
    """Tra ve list chunk (0-N phan tu, thuong la 4, co the nhieu hon neu 1
    field_group qua dai phai tach - xem _pack_pieces) cho 1 ban ghi thuoc.

    Moi chunk: {drug_id, ten_thuoc, danh_muc, muc_nghiem_trong, field_group, noi_dung}
    - ten_thuoc: giu nguyen (chua unaccent) - Phase 3 build ten_thuoc_unaccent
      bang ham unaccent() cua Postgres luc insert, khong build o day.
    """
    chunks: list[dict] = []
    prefix = _build_prefix(thuoc)

    for field_group, fields in FIELD_GROUPS:
        pieces: list[str] = []
        for field in fields:
            pieces.extend(_field_pieces(thuoc, field))

        if not pieces:
            continue  # field_group nay rong o thuoc nay (vd huong_dan_bao_quan), bo qua

        for body in _pack_pieces(pieces, prefix):
            chunks.append(
                {
                    "drug_id": thuoc.get("id", ""),
                    "ten_thuoc": thuoc.get("ten_thuoc", ""),
                    "danh_muc": thuoc.get("danh_muc", ""),
                    "muc_nghiem_trong": thuoc.get("muc_nghiem_trong", ""),
                    "field_group": field_group,
                    "noi_dung": f"{prefix}\n\n{body}",
                }
            )

    return chunks


def iter_all_chunks() -> Iterator[dict]:
    """Generator - doc toan bo data pharmacy/*/thuoc.json, yield tung chunk.
    Phase 3 (embedding) import ham nay truc tiep thay vi doc lai _chunks.jsonl,
    de khong phu thuoc vao viec file staging co ton tai/moi hay khong."""
    for path in sorted(DATA_DIR.glob("*/thuoc.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for thuoc in data:
            yield from build_chunks_for_drug(thuoc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-only", action="store_true", help="Chi in bao cao, khong ghi file")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    total_drugs = 0
    total_chunks = 0
    per_field_group: dict[str, int] = dict.fromkeys([g for g, _ in FIELD_GROUPS], 0)
    missing_bao_quan = 0
    chunks_out: list[dict] = []

    for path in sorted(DATA_DIR.glob("*/thuoc.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for thuoc in data:
            total_drugs += 1
            chunks = build_chunks_for_drug(thuoc)

            # Assertion an toan (Phase 2 DoD): thoi_diem_dung KHONG duoc lot vao chunk nao.
            thoi_diem = (thuoc.get("thoi_diem_dung") or "").strip()
            for c in chunks:
                if thoi_diem and thoi_diem in c["noi_dung"]:
                    print(
                        f"[LOI NGHIEM TRONG] thoi_diem_dung lot vao chunk cua "
                        f"'{thuoc.get('ten_thuoc')}' ({c['field_group']})",
                        file=sys.stderr,
                    )

            groups_present = {c["field_group"] for c in chunks}
            if "bao_quan" not in groups_present:
                missing_bao_quan += 1
            for c in chunks:
                per_field_group[c["field_group"]] += 1
            total_chunks += len(chunks)
            chunks_out.extend(chunks)

    print(f"Tong so thuoc: {total_drugs}")
    print(f"Tong so chunk: {total_chunks}")
    for g, n in per_field_group.items():
        print(f"  {g}: {n}")
    print(f"Thuoc thieu chunk bao_quan (huong_dan_bao_quan rong): {missing_bao_quan}")

    if not args.report_only:
        with OUTPUT_PATH.open("w", encoding="utf-8") as f:
            for c in chunks_out:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        print(f"[OK] Da ghi {len(chunks_out)} chunk -> {OUTPUT_PATH.relative_to(DATA_DIR.parent)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
