"""Phase 4 (specs/build-kickoff-prompt.md): hybrid retrieval - vector + lexical,
hop nhat bang RRF. Thiet ke day du: specs/chatbot-rag-design.md muc 4.

KIEN TRUC BAT BUOC (khong duoc doi khi khong hoi truoc - xem
build-kickoff-prompt.md muc 5): loc nguong tho o TUNG nguon (vector, lexical)
TRUOC, roi moi RRF tren tap da loc. RRF chi xep hang trong so ung vien da hop
le, KHONG tu phat hien "khong co gi lien quan ca" - neu chay RRF truoc roi
loc sau, mat kha nang tu choi cau hoi ngoai pham vi du lieu.

Ham `fuse_rrf()` la PURE FUNCTION (khong dung DB/API) de test duoc logic OR
(chunk chi pass 1 trong 2 nguong van phai xuat hien) ma khong can Postgres/
OpenAI that - xem tests/test_retrieval.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.config import get_settings

CANDIDATE_POOL_SIZE = 50  # so ung vien lay tu MOI nguon (vector, lexical) truoc khi loc nguong


@dataclass
class CandidateChunk:
    """1 ket qua tho tu 1 nguon (vector HOAC lexical) - chua qua hop nhat."""

    id: str
    drug_id: str
    ten_thuoc: str
    danh_muc: str
    muc_nghiem_trong: str
    field_group: str
    noi_dung: str
    score: float  # cosine_similarity (nguon vector) hoac lexical_score (nguon lexical)


@dataclass
class DrugInfoResult:
    """Ket qua sau hop nhat RRF - khop DrugInfoDTO (api-contracts.md §8) +
    3 diem so minh bach (chatbot-rag-design.md muc 5.1), khong rut gon con 1 so."""

    drug_id: str
    ten_thuoc: str
    field_group: str
    noi_dung: str
    danh_muc: str
    muc_nghiem_trong: str
    source: str
    vector_score: float | None
    lexical_score: float | None
    rrf_score: float
    rank: int = field(default=0)


@dataclass
class SideEffectMatchResult:
    """Mot chunk `tac_dung_phu` cua thuoc trong don active, xep theo cosine.

    Khac `DrugInfoResult`: day khong phai ket qua RAG chung/RRF va chi dung
    de audit noi bo, nen giu diem semantic duy nhat minh bach cho viec tune.
    """

    drug_id: str
    ten_thuoc: str
    noi_dung: str
    score: float


@dataclass
class RetrievalResult:
    """Wrapper tra ve tu fuse_rrf()/hybrid_search() - TACH RIENG tin hieu
    "khong tim duoc nguon" (BR-7.3, muc 4.4) khoi list ket qua rong thong
    thuong, de node NOSRC o Phase 5 khong phai tu suy luan "rong tuc la
    khong co nguon" (de nham voi rong vi ly do khac, vd loi query). Kiem tra
    `no_source_found`, KHONG kiem tra `not results.results`."""

    results: list[DrugInfoResult]
    no_source_found: bool


def fuse_rrf(
    vector_results: list[CandidateChunk],
    lexical_results: list[CandidateChunk],
    k: int = 60,
    top_k: int = 5,
) -> RetrievalResult:
    """Hop nhat 2 danh sach ung vien bang Reciprocal Rank Fusion.

    QUY TAC BAT BUOC (chatbot-rag-design.md muc 4.3): tap ung vien hop le la
    UNION (OR) cua 2 nguon - 1 chunk chi can qua NGUONG o MOT trong hai nguon
    (tuc co mat trong vector_results HOAC lexical_results - ca 2 danh sach nay
    da duoc loc nguong tu truoc khi truyen vao ham nay) la du dieu kien vao
    ket qua cuoi. KHONG yeu cau co mat o CA HAI (AND) - 1 chunk khop semantic
    tot nhung khong khop tu khoa (hoac nguoc lai) van phai xuat hien.

    Neu ca 2 danh sach dau vao deu rong -> RetrievalResult(results=[],
    no_source_found=True) (BR-7.3, muc 4.4), KHONG tinh RRF vi khong co gi
    de xep hang.
    """
    if not vector_results and not lexical_results:
        return RetrievalResult(results=[], no_source_found=True)

    vector_rank = {c.id: i + 1 for i, c in enumerate(vector_results)}  # 1-indexed
    lexical_rank = {c.id: i + 1 for i, c in enumerate(lexical_results)}
    vector_score = {c.id: c.score for c in vector_results}
    lexical_score = {c.id: c.score for c in lexical_results}

    # Metadata chunk co the lay tu 1 trong 2 nguon (giong nhau cho cung 1 id) -
    # uu tien vector_results, fallback lexical_results.
    chunk_by_id = {c.id: c for c in lexical_results}
    chunk_by_id.update({c.id: c for c in vector_results})

    candidate_ids = set(vector_rank) | set(lexical_rank)  # UNION - dung logic OR

    scored: list[tuple[str, float]] = []
    for cid in candidate_ids:
        rrf = 0.0
        if cid in vector_rank:
            rrf += 1.0 / (k + vector_rank[cid])
        if cid in lexical_rank:
            rrf += 1.0 / (k + lexical_rank[cid])
        scored.append((cid, rrf))

    scored.sort(key=lambda x: x[1], reverse=True)

    results: list[DrugInfoResult] = []
    for rank, (cid, rrf_score) in enumerate(scored[:top_k], start=1):
        c = chunk_by_id[cid]
        results.append(
            DrugInfoResult(
                drug_id=c.drug_id,
                ten_thuoc=c.ten_thuoc,
                field_group=c.field_group,
                noi_dung=c.noi_dung,
                danh_muc=c.danh_muc,
                muc_nghiem_trong=c.muc_nghiem_trong,
                source=f"{c.field_group} — {c.ten_thuoc}",
                vector_score=vector_score.get(cid),
                lexical_score=lexical_score.get(cid),
                rrf_score=rrf_score,
                rank=rank,
            )
        )
    return RetrievalResult(results=results, no_source_found=False)


def _row_to_candidate(row, score: float) -> CandidateChunk:
    return CandidateChunk(
        id=row.id,
        drug_id=row.drug_id,
        ten_thuoc=row.ten_thuoc,
        danh_muc=row.danh_muc,
        muc_nghiem_trong=row.muc_nghiem_trong,
        field_group=row.field_group,
        noi_dung=row.noi_dung,
        score=score,
    )


def vector_search(db: Session, query_embedding: list[float], nguong_vector: float) -> list[CandidateChunk]:
    """pgvector cosine similarity (HNSW index, ix_drug_chunks_embedding_hnsw).
    1 - (embedding <=> :q) = cosine similarity (OpenAI embedding da chuan hoa)."""
    rows = db.execute(
        text(
            """
            SELECT id, drug_id, ten_thuoc, danh_muc, muc_nghiem_trong, field_group, noi_dung,
                   1 - (embedding <=> :q) AS cosine_similarity
            FROM drug_chunks
            ORDER BY embedding <=> :q
            LIMIT :pool_size
            """
        ),
        {"q": str(query_embedding), "pool_size": CANDIDATE_POOL_SIZE},
    ).fetchall()
    candidates = [_row_to_candidate(r, r.cosine_similarity) for r in rows]
    return [c for c in candidates if c.score >= nguong_vector]


def lexical_search(db: Session, query: str, nguong_lexical: float) -> list[CandidateChunk]:
    """pg_trgm - similarity() cho ten_thuoc (ngan-ngan, GIN index
    ix_drug_chunks_ten_thuoc_unaccent_trgm), word_similarity() cho noi_dung
    (ngan-dai, GIN index ix_drug_chunks_noi_dung_unaccent_trgm). Ca 2 dung
    toan tu %/<%  (khong goi ham truc tiep trong WHERE) de tan dung duoc GIN
    index - can SET nguong truoc (chi anh huong session hien tai, khong doi
    cau hinh DB toan cuc). unaccent() ap dung cho query NGAY TRONG SQL, cung
    1 ham voi luc build cot _unaccent o Phase 3 - dam bao logic bo dau dung
    1 nguon.

    QUAN TRONG (phat hien 2026-08-08 luc verify bang du lieu that): toan tu
    `%` (similarity, dung cho ten_thuoc) va toan tu `<%` (word_similarity,
    dung cho noi_dung) doc 2 GUC KHAC NHAU cua pg_trgm -
    `pg_trgm.similarity_threshold` va `pg_trgm.word_similarity_threshold`
    - KHONG chung 1 GUC. GUC thu 2 mac dinh la 0.6 (khong phai 0.3 nhu
    NGUONG_LEXICAL du dinh) - neu chi SET similarity_threshold ma quen
    word_similarity_threshold, toan tu <% se am tham dung nguong 0.6 mac
    dinh, loai bo moi match co word_similarity trong khoang [nguong, 0.6)
    ma khong bao loi gi ca (code chay binh thuong, chi ket qua thieu)."""
    db.execute(text("SET pg_trgm.similarity_threshold = :t"), {"t": nguong_lexical})
    db.execute(text("SET pg_trgm.word_similarity_threshold = :t"), {"t": nguong_lexical})
    rows = db.execute(
        text(
            """
            SELECT id, drug_id, ten_thuoc, danh_muc, muc_nghiem_trong, field_group, noi_dung,
                   GREATEST(
                       similarity(ten_thuoc_unaccent, unaccent(:q)),
                       word_similarity(unaccent(:q), noi_dung_unaccent)
                   ) AS lexical_score
            FROM drug_chunks
            WHERE ten_thuoc_unaccent % unaccent(:q)
               OR unaccent(:q) <% noi_dung_unaccent
            ORDER BY lexical_score DESC
            LIMIT :pool_size
            """
        ),
        {"q": query, "pool_size": CANDIDATE_POOL_SIZE},
    ).fetchall()
    return [_row_to_candidate(r, r.lexical_score) for r in rows]


def fuzzy_name_search(db: Session, query: str, top_k: int = 5) -> list[CandidateChunk]:
    """Vong 4, muc 3.1 - fuzzy tang 1 THUAN cho `_search_distinct_drug_
    candidates()` moi (drug_confirmation_nodes.py) - dung `similarity()`
    (pg_trgm) tren `ten_thuoc_unaccent`, KHONG goi OpenAI embedding (cai
    thien chi phi that, khong chi latency - xem chatbot-rag-design.md muc
    10 #34: p90/p99 cu 5.2s/7.9s hoan toan tu API embedding, ham nay khong
    goi API nao ca).

    KHONG loc nguong truoc khi xep hang (khac vector_search()/lexical_
    search()) - luon tra ve DUNG top_k phan biet theo drug_id, quyet dinh
    "co tin duoc khong" thuoc ve tang 2 (NGUONG_CAO/NGUONG_CACH_BIET,
    drug_confirmation_nodes.py), khong phai tang nay. Vi khong loc bang
    toan tu `%`, KHONG dung duoc GIN trgm index cho phep loc tho - la full
    scan tren drug_chunks, nhung do that (~50-60ms tren 3562 thuoc phan
    biet, xem eval/tune_fuzzy_tier1.py) van nhanh hon nhieu p50 cu (~13ms
    THUONG nhung co duoi p90/p99 toi 5-8s do goi API that).

    `DISTINCT ON (drug_id)` lay dung 1 dong/thuoc (thuoc co the co nhieu
    chunk field_group, cung 1 ten_thuoc - khong can xep hang trung lap)."""
    rows = db.execute(
        text(
            """
            SELECT DISTINCT ON (drug_id) id, drug_id, ten_thuoc, danh_muc, muc_nghiem_trong, field_group, noi_dung,
                   similarity(ten_thuoc_unaccent, unaccent(:q)) AS name_sim
            FROM drug_chunks
            ORDER BY drug_id, name_sim DESC
            """
        ),
        {"q": query},
    ).fetchall()
    candidates = [_row_to_candidate(r, r.name_sim) for r in rows]
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:top_k]


def search_active_side_effect_chunks(
    db: Session, query_embedding: list[float], active_drug_ids: list[str]
) -> list[SideEffectMatchResult]:
    """So khop semantic chi trong `tac_dung_phu` cua thuoc active.

    Ham co y khong ap dung nguong: eval va node goi sau nay dung cung mot
    diem cosine, trong do nguong duoc chot bang sweep thay vi bi an trong SQL.
    """
    unique_drug_ids = list(dict.fromkeys(active_drug_ids))
    if not unique_drug_ids:
        return []

    rows = db.execute(
        text(
            """
            SELECT drug_id, ten_thuoc, noi_dung,
                   1 - (embedding <=> :q) AS cosine_similarity
            FROM drug_chunks
            WHERE field_group = 'tac_dung_phu'
              AND drug_id = ANY(CAST(:drug_ids AS text[]))
            ORDER BY embedding <=> :q
            """
        ),
        {"q": str(query_embedding), "drug_ids": unique_drug_ids},
    ).fetchall()
    return [
        SideEffectMatchResult(
            drug_id=row.drug_id,
            ten_thuoc=row.ten_thuoc,
            noi_dung=row.noi_dung,
            score=row.cosine_similarity,
        )
        for row in rows
    ]


def hybrid_search(db: Session, query: str, query_embedding: list[float]) -> RetrievalResult:
    """Entry point day du: loc nguong tho o tung nguon (mucd 4.3 buoc 1-2),
    hop nhat RRF chi tren union (buoc 3-5). Goi bang query_embedding co san
    (da embed cau hoi bang OpenAI truoc do o node retrieval - xem
    chatbot-rag-design.md muc 8) de ham nay khong tu goi API, de test/mock."""
    settings = get_settings()
    vec_candidates = vector_search(db, query_embedding, settings.nguong_vector)
    lex_candidates = lexical_search(db, query, settings.nguong_lexical)
    return fuse_rrf(vec_candidates, lex_candidates, k=settings.rrf_k, top_k=settings.retrieval_top_k)


def get_chunks_by_drug_id(db: Session, drug_id: str) -> list[DrugInfoResult]:
    """Che do 'Filter theo drug_id' (chatbot-rag-design.md muc 4.1) - khi da
    biet chac dang noi ve thuoc nao (tu dose_event/prescription active cua
    benh nhan), lay thang chunk cua dung thuoc do, KHONG can retrieval
    (khong vector, khong lexical, khong RRF)."""
    rows = db.execute(
        text(
            """
            SELECT id, drug_id, ten_thuoc, danh_muc, muc_nghiem_trong, field_group, noi_dung
            FROM drug_chunks
            WHERE drug_id = :drug_id
            ORDER BY field_group
            """
        ),
        {"drug_id": drug_id},
    ).fetchall()
    return [
        DrugInfoResult(
            drug_id=r.drug_id,
            ten_thuoc=r.ten_thuoc,
            field_group=r.field_group,
            noi_dung=r.noi_dung,
            danh_muc=r.danh_muc,
            muc_nghiem_trong=r.muc_nghiem_trong,
            source=f"{r.field_group} — {r.ten_thuoc}",
            vector_score=None,
            lexical_score=None,
            rrf_score=0.0,
            rank=i + 1,
        )
        for i, r in enumerate(rows)
    ]
