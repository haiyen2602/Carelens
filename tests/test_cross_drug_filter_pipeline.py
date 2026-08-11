"""Muc 10 #17 (Phase 7, phat hien 2026-08-09, review): _filter_cross_drug_
mismatch() phai chay o retrieval_node (KHONG chi o answer_generation_node)
vi prescription_lookup_node chay GIUA 2 node do (muc 8: retrieval ->
prescription_lookup -> answer_generation) va dung thang rag_results[0].
drug_id de tra don thuoc ca nhan - neu chi loc o answer_generation_node,
prescription_lookup_node van doc duoc rag_results CHUA loc, co the tra nham
don thuoc (gio uong THAT cua benh nhan) cua 1 thuoc hoan toan khac.

Dung DB that (demo-patient-01, seed boi scripts/seed_demo_patient.py Phase 6)
thay vi mock tra_cuu_don_thuoc_ca_nhan - de kiem chung dung pipeline that,
khong chi logic don le."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from backend.agents.nodes.conversation_nodes import (  # noqa: E402
    build_prescription_lookup_node,
    build_retrieval_node,
)
from backend.db.base import SessionLocal, engine  # noqa: E402
from backend.services.retrieval import DrugInfoResult, RetrievalResult  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


def _demo_patient_seeded(db) -> bool:
    from backend.db.models import Prescription

    return (
        db.query(Prescription)
        .filter(Prescription.patient_id == "demo-patient-01", Prescription.status.in_(("approved", "active")))
        .first()
        is not None
    )


pytestmark = pytest.mark.skipif(not _db_available(), reason="Can Postgres that (docker compose up -d db)")


def _fake_result(drug_id: str, ten_thuoc: str, field_group: str = "cach_dung") -> DrugInfoResult:
    return DrugInfoResult(
        drug_id=drug_id,
        ten_thuoc=ten_thuoc,
        field_group=field_group,
        noi_dung=f"noi dung {field_group} cua {ten_thuoc}",
        danh_muc="Thuốc test",
        muc_nghiem_trong="Nhẹ",
        source=f"{field_group} — {ten_thuoc}",
        vector_score=0.8,
        lexical_score=None,
        rrf_score=0.02,
        rank=1,
    )


@pytest.mark.asyncio
async def test_prescription_lookup_receives_filtered_rag_results_not_raw():
    """Mo phong dung bug da phat hien: rag_results[0] la 1 thuoc KHONG lien
    quan (gia lap recall-miss/cross-drug misattribution #17), rag_results[1]
    moi la dung thuoc benh nhan da hoi (co ten trong cau hoi). Neu retrieval_
    node KHONG loc, prescription_lookup se tra nham don thuoc cua drug_id[0].
    Neu loc dung, prescription_lookup phai tra dung don cua thuoc benh nhan
    hoi (vitamin-c-500mg-khapharco-200v, seed that demo-patient-01)."""
    db = SessionLocal()
    try:
        if not _demo_patient_seeded(db):
            pytest.skip("demo-patient-01 chua duoc seed - chay scripts/seed_demo_patient.py truoc")

        utterance = "Vitamin C 500mg Khapharco 200v dùng lúc nào?"
        wrong_drug = _fake_result("mot-thuoc-khong-lien-quan-999", "Thuốc Hoàn Toàn Khác 999mg")
        target_drug = _fake_result("vitamin-c-500mg-khapharco-200v", "Vitamin C 500mg Khapharco 200v")

        def fake_search(db_, query, embed_query):
            # rag_results[0] la thuoc SAI - dung mo phong dung bug da phat hien
            return RetrievalResult(results=[wrong_drug, target_drug], no_source_found=False)

        retrieval_node = build_retrieval_node(db, embed_query=lambda t: [0.0], search_fn=fake_search)
        prescription_node = build_prescription_lookup_node(db)

        state = {
            "patient_id": "demo-patient-01",
            "dose_event_id": None,
            "intent": "drug_info",
            "utterance": utterance,
            "trace": [],
        }
        retrieval_update = await retrieval_node(state)
        state = {**state, **retrieval_update}

        # retrieval_node PHAI da loc bo wrong_drug truoc khi luu vao state
        assert all(r.drug_id != "mot-thuoc-khong-lien-quan-999" for r in state["rag_results"]), (
            "retrieval_node phai loc cross-drug mismatch TRUOC khi luu rag_results vao state, "
            "khong duoc de lai cho answer_generation_node loc mot minh"
        )

        prescription_update = await prescription_node(state)
        presc_entry = prescription_update["trace"][-1]

        assert presc_entry["drug_id"] == "vitamin-c-500mg-khapharco-200v", (
            "prescription_lookup_node phai tra cuu DUNG drug_id cua thuoc benh nhan hoi, "
            "khong phai drug_id[0] chua loc (rui ro tra nham gio uong thuoc that cua benh nhan)"
        )
        assert presc_entry["found"] is True
        assert presc_entry["thoi_diem_dung"] == "Sau khi ăn sáng và ăn tối"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_no_name_match_keeps_raw_order_prescription_lookup_uses_rank1():
    """Doi chung: neu KHONG chunk nao khop ten trong cau hoi (khong du tin
    cay de loc), retrieval_node giu nguyen thu tu goc - prescription_lookup
    van dung rag_results[0] nhu truoc gio (hanh vi khong doi khi filter
    khong kich hoat)."""
    db = SessionLocal()
    try:
        if not _demo_patient_seeded(db):
            pytest.skip("demo-patient-01 chua duoc seed - chay scripts/seed_demo_patient.py truoc")

        r1 = _fake_result("drug-a-khong-ro", "Thuốc A Không Rõ Tên")
        r2 = _fake_result("vitamin-c-500mg-khapharco-200v", "Vitamin C 500mg Khapharco 200v")

        def fake_search(db_, query, embed_query):
            return RetrievalResult(results=[r1, r2], no_source_found=False)

        retrieval_node = build_retrieval_node(db, embed_query=lambda t: [0.0], search_fn=fake_search)
        prescription_node = build_prescription_lookup_node(db)

        state = {
            "patient_id": "demo-patient-01",
            "dose_event_id": None,
            "intent": "drug_info",
            "utterance": "thuốc này dùng lúc nào",  # khong nhac ten thuoc cu the nao
            "trace": [],
        }
        retrieval_update = await retrieval_node(state)
        state = {**state, **retrieval_update}

        assert state["rag_results"] == [r1, r2], "khong khop ten -> khong loc, giu nguyen thu tu"

        prescription_update = await prescription_node(state)
        presc_entry = prescription_update["trace"][-1]
        assert presc_entry["drug_id"] == "drug-a-khong-ro", "dung rank1 nhu hanh vi cu khi khong loc"
        assert presc_entry["found"] is False
    finally:
        db.close()