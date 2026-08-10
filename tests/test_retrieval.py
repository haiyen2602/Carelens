"""Phase 4 (specs/build-kickoff-prompt.md) - test fuse_rrf(), PURE function
khong dung DB/API, tap trung vao 2 nhanh an toan bat buoc (chatbot-rag-design.md
muc 4.3): (1) loc nguong tho o TUNG nguon roi UNION (OR), khong phai AND, va
(2) union rong -> tin hieu "khong co nguon" TUONG MINH, khong phai list rong
thuong (BR-7.3, muc 4.4).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.nodes.drug_confirmation_nodes import _dedupe_distinct_drugs  # noqa: E402
from src.services.retrieval import CandidateChunk, RetrievalResult, fuse_rrf  # noqa: E402


def _chunk(id_: str, score: float, drug_id: str = "drug-1", field_group: str = "cach_dung") -> CandidateChunk:
    return CandidateChunk(
        id=id_,
        drug_id=drug_id,
        ten_thuoc=f"Thuốc {drug_id}",
        danh_muc="Thuốc kháng virus",
        muc_nghiem_trong="Nguy hiểm",
        field_group=field_group,
        noi_dung=f"Nội dung chunk {id_}",
        score=score,
    )


def test_chunk_pass_only_vector_threshold_still_appears_in_final_result():
    """Test BAT BUOC (rui ro logic cao nhat, xem build-kickoff-prompt.md muc 3
    Phase 4): chunk 'only-vector' CHI xuat hien trong vector_results (da qua
    NGUONG_VECTOR), hoan toan KHONG co trong lexical_results (khong qua
    NGUONG_LEXICAL, hoac khong khop tu khoa nao ca) - van phai co mat trong
    ket qua cuoi cung sau fuse_rrf(). Neu test nay FAIL, logic dang la AND
    (giao 2 tap) thay vi dung OR (hop 2 tap) nhu thiet ke bat buoc."""
    only_vector = _chunk("only-vector", score=0.85)
    only_lexical = _chunk("only-lexical", score=0.9)

    vector_results = [only_vector]  # da qua NGUONG_VECTOR, khong co trong lexical
    lexical_results = [only_lexical]  # da qua NGUONG_LEXICAL, khong co trong vector

    outcome = fuse_rrf(vector_results, lexical_results, k=60, top_k=5)

    assert outcome.no_source_found is False
    # DrugInfoResult (DTO huong ra ngoai) khong lo id noi bo cua chunk - nhan
    # dien tung ket qua qua noi_dung (moi chunk trong test co noi_dung khac nhau).
    noi_dungs = {r.noi_dung for r in outcome.results}
    assert "Nội dung chunk only-vector" in noi_dungs, (
        "Chunk chi qua nguong vector (khong qua lexical) BI THIEU khoi ket qua "
        "- logic dang sai thanh AND thay vi OR"
    )
    assert "Nội dung chunk only-lexical" in noi_dungs, (
        "Chunk chi qua nguong lexical (khong qua vector) BI THIEU khoi ket qua "
        "- logic dang sai thanh AND thay vi OR"
    )
    assert len(outcome.results) == 2


def test_empty_both_sources_signals_no_source_found_explicitly():
    """Muc 4.4 - NHANH AN TOAN THU HAI, quan trong ngang nhanh OR o tren:
    neu ca 2 nguon deu rong (khong chunk nao qua nguong o dau ca), ham phai
    tra ve tin hieu `no_source_found=True` TUONG MINH - KHONG chi don thuan
    la `results=[]`. Ly do tach rieng: [] rong co the do nhieu nguyen nhan
    khac (loi query, du lieu chua co...), con `no_source_found=True` la tin
    hieu duy nhat noi Phase 5 (node NOSRC) duoc phep dua vao de kich hoat
    REFUSE theo BR-7.3, khong phai tu suy luan tu 1 list rong."""
    outcome = fuse_rrf([], [], k=60, top_k=5)

    assert isinstance(outcome, RetrievalResult)
    assert outcome.no_source_found is True
    assert outcome.results == []


def test_no_source_found_is_false_whenever_results_non_empty():
    """Bat bien nguoc lai: bat ky luc nao co it nhat 1 ket qua, no_source_found
    phai la False - khong duoc vua co results vua bao no_source_found=True
    (2 tin hieu mau thuan nhau se lam Phase 5 kho xu ly)."""
    outcome = fuse_rrf([_chunk("v1", score=0.9)], [], k=60, top_k=5)
    assert outcome.no_source_found is False
    assert len(outcome.results) == 1


def test_chunk_in_both_sources_ranks_higher_than_single_source():
    """Chunk xuat hien o CA HAI nguon (rank tot o ca 2) phai co rrf_score cao
    hon chunk chi xuat hien o 1 nguon - dung tinh chat cong don cua RRF."""
    in_both = _chunk("in-both", score=0.8)
    only_vector = _chunk("only-vector-2", score=0.95)  # diem vector cao hon nhung chi 1 nguon

    vector_results = [in_both, only_vector]
    lexical_results = [in_both]

    outcome = fuse_rrf(vector_results, lexical_results, k=60, top_k=5)
    by_noi_dung = {r.noi_dung: r for r in outcome.results}

    assert by_noi_dung["Nội dung chunk in-both"].rrf_score > by_noi_dung["Nội dung chunk only-vector-2"].rrf_score


def test_top_k_limits_result_count():
    vector_results = [_chunk(f"v{i}", score=0.9 - i * 0.01) for i in range(10)]
    outcome = fuse_rrf(vector_results, [], k=60, top_k=3)
    assert len(outcome.results) == 3


def test_rank_field_is_1_indexed_and_sequential():
    vector_results = [_chunk(f"v{i}", score=0.9 - i * 0.01) for i in range(5)]
    outcome = fuse_rrf(vector_results, [], k=60, top_k=5)
    assert [r.rank for r in outcome.results] == [1, 2, 3, 4, 5]


def test_scores_reported_separately_not_collapsed_into_one_number():
    """Muc 5.1: DTO phai tra ve ca 3 diem (vector_score, lexical_score,
    rrf_score) rieng biet, khong rut gon con 1 so tong hop - chunk chi co o
    1 nguon thi diem nguon kia phai la None (khong phai 0, de phan biet
    'khong co trong nguon nay' voi 'diem 0')."""
    only_vector = _chunk("ov", score=0.77)
    outcome = fuse_rrf([only_vector], [], k=60, top_k=5)
    assert outcome.results[0].vector_score == 0.77
    assert outcome.results[0].lexical_score is None
    assert outcome.results[0].rrf_score > 0


# ---------------------------------------------------------------------------
# THEM 2026-08-09 (phan hoi review muc 6) - invariant OR o tren CHI xac nhan
# cho fuse_rrf() THUAN. _dedupe_distinct_drugs() (src/agents/nodes/drug_
# confirmation_nodes.py, viet cho muc 5/11 - dedup chunk -> danh sach THUOC
# phan biet, dung boi _search_distinct_drug_candidates()) la code MOI, CHUA
# tung duoc kiem chung invariant nay con SONG SOT sau buoc dedup hay khong -
# truoc khi tin bat ky ket qua sweep nao (eval/tune_candidate_retrieval.py,
# muc 6) dua tren _search_distinct_drug_candidates(), phai xac nhan dedup
# khong vo tinh bien OR (hop) thanh AND (giao)/lam mat candidate hop le.
# ---------------------------------------------------------------------------


def test_dedupe_distinct_drugs_preserves_or_invariant_after_fuse_rrf():
    """Ghep dung 2 buoc that _search_distinct_drug_candidates() lam (fuse_rrf
    roi _dedupe_distinct_drugs), KHONG phai reimplement rieng - drug-A chi co
    1 chunk qua duoc NGUONG_VECTOR (khong qua lexical), drug-B chi co 1 chunk
    qua duoc NGUONG_LEXICAL (khong qua vector) - ca 2 deu phai con SONG SOT
    trong danh sach THUOC phan biet cuoi cung sau dedup. Neu FAIL, dedup dang
    vo tinh lam mat 1 candidate hop le theo OR - toan bo so lieu sweep muc 6
    dua tren ham nay se vo nghia."""
    only_vector = _chunk("only-vector", score=0.85, drug_id="drug-A")
    only_lexical = _chunk("only-lexical", score=0.9, drug_id="drug-B")

    outcome = fuse_rrf([only_vector], [only_lexical], k=60, top_k=50)
    distinct = _dedupe_distinct_drugs(outcome.results, n=4)

    drug_ids = {c["drug_id"] for c in distinct}
    assert "drug-A" in drug_ids, (
        "Thuoc chi co chunk qua nguong VECTOR (khong qua lexical) BI THIEU sau dedup "
        "- OR o fuse_rrf() dung nhung dedup lam mat candidate"
    )
    assert "drug-B" in drug_ids, (
        "Thuoc chi co chunk qua nguong LEXICAL (khong qua vector) BI THIEU sau dedup "
        "- OR o fuse_rrf() dung nhung dedup lam mat candidate"
    )


def test_dedupe_distinct_drugs_not_crowded_out_by_multi_chunk_drug():
    """Regression dung #14 (docstring _search_distinct_drug_candidates): 1
    thuoc co NHIEU chunk (field_group khac nhau) hay dung gan nhau trong
    top-k - khong duoc de thuoc do chiem het "cho" trong danh sach n=4 thuoc
    phan biet, lam thuoc khac (chi co 1 chunk, dung sau trong pool) bi day
    ra ngoai. drug-CROWD co 10 chunk deu qua CA HAI nguon (rank cao) - van
    chi duoc tinh la 1 "cho" sau dedup, drug-A (1 chunk, chi qua vector,
    rank thap hon) van phai con trong ket qua vi pool=50 du rong chua toi."""
    crowd_chunks = [_chunk(f"crowd-{i}", score=0.9 - i * 0.01, drug_id="drug-CROWD") for i in range(10)]
    only_vector = _chunk("only-vector-late", score=0.5, drug_id="drug-A")

    vector_results = [*crowd_chunks, only_vector]
    lexical_results = crowd_chunks

    outcome = fuse_rrf(vector_results, lexical_results, k=60, top_k=50)
    distinct = _dedupe_distinct_drugs(outcome.results, n=4)

    drug_ids = [c["drug_id"] for c in distinct]
    assert drug_ids.count("drug-CROWD") == 1, "1 thuoc nhieu chunk phai chi chiem 1 'cho' sau dedup, khong nhieu hon"
    assert "drug-A" in drug_ids, (
        "Thuoc chi co 1 chunk (qua 1 nguong) bi day ra ngoai vi 1 thuoc khac chiem qua nhieu "
        "'cho' trong pool - dung chinh loai loi #14 da ghi nhan"
    )
