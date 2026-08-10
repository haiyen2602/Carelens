#!/usr/bin/env python3
"""Phase 3 (specs/build-kickoff-prompt.md): batch embed toan bo chunk
(scripts/chunk_drugs.py) bang text-embedding-3-small, insert vao pgvector.

Cot noi_dung_unaccent/ten_thuoc_unaccent duoc build BANG unaccent() cua
PostgreSQL NGAY TRONG cau INSERT (SQLAlchemy func.unaccent(...)), KHONG
build o Python truoc khi insert - dam bao logic bo dau dung 1 nguon voi
luc query (Phase 4 se unaccent cau hoi bang cung ham unaccent() nay).

Usage:
    python embed_and_insert.py --dry-run          # chi dem token/uoc tinh chi phi, khong goi API
    python embed_and_insert.py --limit 5           # embed + insert thu 5 chunk dau, kiem tra pipeline
    python embed_and_insert.py                     # chay that toan bo
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # cho `from chunk_drugs import ...`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # cho `from src... import ...`
from chunk_drugs import iter_all_chunks  # noqa: E402

# Gia tham khao cong khai cua OpenAI cho text-embedding-3-small tai thoi diem
# viet script nay - CAN TU KIEM TRA LAI tren trang gia OpenAI truoc khi coi
# day la con so chinh xac, gia co the doi.
USD_PER_1M_TOKENS = 0.02

BATCH_SIZE = 100  # so chunk/1 lan goi API embeddings (an toan duoi gioi han input cua OpenAI)


def estimate_tokens(text: str) -> int:
    """Uoc tinh tho: ~4 ky tu/token cho text co dau tieng Viet (thuc te co the
    nhieu token hon vi dau tieng Viet thuong tach thanh nhieu token con) - chi
    dung de dry-run uoc tinh chi phi TRUOC khi goi API, khong dung de tinh tien
    that (tien that lay tu response.usage.total_tokens cua chinh OpenAI)."""
    return max(1, len(text) // 4)


def run_dry_run() -> int:
    chunks = list(iter_all_chunks())
    total_tokens_est = sum(estimate_tokens(c["noi_dung"]) for c in chunks)
    cost_est = total_tokens_est / 1_000_000 * USD_PER_1M_TOKENS
    print(f"So chunk se embed: {len(chunks)}")
    print(f"Uoc tinh token (tho, ~4 ky tu/token): {total_tokens_est:,}")
    print(f"Uoc tinh chi phi (theo gia ${USD_PER_1M_TOKENS}/1M token, CAN TU KIEM TRA LAI): ${cost_est:.4f}")
    print("(Day chi la uoc tinh - so token/chi phi that se duoc bao cao sau khi chay that qua response.usage)")
    return 0


def run_real(limit: int | None) -> int:
    import openai
    from sqlalchemy import func, insert

    from src.config import get_settings
    from src.db.base import SessionLocal
    from src.db.models import DrugChunk

    settings = get_settings()
    if not settings.openai_api_key or settings.openai_api_key == "sk-your-key-here":
        print("[LOI] OPENAI_API_KEY chua duoc set that trong .env", file=sys.stderr)
        return 1

    client = openai.OpenAI(api_key=settings.openai_api_key)

    chunks = list(iter_all_chunks())
    if limit:
        chunks = chunks[:limit]
    print(f"Se embed + insert {len(chunks)} chunk (model: {settings.embedding_model})")

    total_tokens_real = 0
    inserted = 0
    t0 = time.time()

    session = SessionLocal()
    try:
        for i in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[i : i + BATCH_SIZE]
            texts = [c["noi_dung"] for c in batch]

            resp = client.embeddings.create(model=settings.embedding_model, input=texts)
            total_tokens_real += resp.usage.total_tokens

            now = datetime.now(UTC)
            for chunk, item in zip(batch, resp.data, strict=True):
                stmt = insert(DrugChunk).values(
                    drug_id=chunk["drug_id"],
                    ten_thuoc=chunk["ten_thuoc"],
                    danh_muc=chunk["danh_muc"],
                    muc_nghiem_trong=chunk["muc_nghiem_trong"],
                    field_group=chunk["field_group"],
                    noi_dung=chunk["noi_dung"],
                    noi_dung_unaccent=func.unaccent(chunk["noi_dung"]),
                    ten_thuoc_unaccent=func.unaccent(chunk["ten_thuoc"]),
                    embedding=item.embedding,
                    created_at=now,
                )
                session.execute(stmt)
            session.commit()
            inserted += len(batch)
            print(f"  [{inserted}/{len(chunks)}] da insert, token luy ke: {total_tokens_real:,}")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    elapsed = time.time() - t0
    cost_real = total_tokens_real / 1_000_000 * USD_PER_1M_TOKENS
    print()
    print(f"[OK] Da embed + insert {inserted} chunk trong {elapsed:.1f}s")
    print(f"Tong token that (tu response.usage): {total_tokens_real:,}")
    print(f"Chi phi thuc te (gia ${USD_PER_1M_TOKENS}/1M token, CAN TU KIEM TRA LAI): ${cost_real:.4f}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Chi uoc tinh token/chi phi, khong goi API")
    parser.add_argument("--limit", type=int, default=None, help="Chi embed N chunk dau (test pipeline)")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if args.dry_run:
        return run_dry_run()
    return run_real(args.limit)


if __name__ == "__main__":
    sys.exit(main())
