"""Phase 2 Definition of Done (specs/build-kickoff-prompt.md):
voi 1 thuoc mau that, ra dung 4 record, dung noi dung gop, va assertion
thoi_diem_dung khong xuat hien trong bat ky chunk nao.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from chunk_drugs import (  # noqa: E402
    FIELD_GROUPS,
    MAX_TOKENS_PER_CHUNK,
    _count_tokens,
    build_chunks_for_drug,
)

# Ban ghi that, lay tu data pharmacy/Thuốc kháng virus/thuoc.json (id: agiclovir-5-agimexpharm).
SAMPLE_THUOC = {
    "ten_thuoc": "Agiclovir 5% Agimexpharm",
    "ham_luong": "Aciclovir 0.25g",
    "dang_thuoc": "Thuốc mỡ",
    "tong_so_luong": "Tuýp X 5g",
    "tac_dung": (
        "Thuốc mỡ bôi da Agiclovir 5% được chỉ định dùng trong các trường hợp sau: Các trường "
        "hợp nhiễm Herpes simplex trên da và niêm mạc, nhiễm Herpes zoster , Herpes sinh dục , "
        "Herpes môi khởi phát và tái phát."
    ),
    "tac_dung_phu": (
        "Khi sử dụng thuốc mỡ bôi da Agiclovir 5%, bạn có thể gặp các tác dụng không mong muốn (ADR)."
    ),
    "huong_dan_su_dung": "Thuốc mỡ dùng bôi ngoài.",
    "lieu_dung": "Thoa thuốc lên vùng da bị nhiễm, 5 - 6 lần/mỗi ngày, cách nhau 4 giờ 1 lần.",
    "duong_dung": "Bôi ngoài da",
    "thoi_diem_dung": "",
    "huong_dan_bao_quan": "Để ở nhiệt độ dưới 30°C, tránh ẩm và ánh sáng.",
    "luu_y_dac_biet": [
        "Chống chỉ định: Mẫn cảm với các thành phần của thuốc.",
        "Thời kỳ mang thai: Thận trọng khi sử dụng cho phụ nữ có thai.",
    ],
    "id": "agiclovir-5-agimexpharm",
    "danh_muc": "Thuốc kháng virus",
    "muc_nghiem_trong": "Nguy hiểm",
}


def test_real_sample_produces_exactly_4_chunks():
    chunks = build_chunks_for_drug(SAMPLE_THUOC)
    assert len(chunks) == 4
    assert {c["field_group"] for c in chunks} == {g for g, _ in FIELD_GROUPS}


def test_chunk_fields_and_metadata_correct():
    chunks = build_chunks_for_drug(SAMPLE_THUOC)
    by_group = {c["field_group"]: c for c in chunks}

    for c in chunks:
        assert c["drug_id"] == "agiclovir-5-agimexpharm"
        assert c["ten_thuoc"] == "Agiclovir 5% Agimexpharm"
        assert c["danh_muc"] == "Thuốc kháng virus"
        assert c["muc_nghiem_trong"] == "Nguy hiểm"
        # Prefix co dinh (chatbot-rag-design.md muc 3.1)
        assert c["noi_dung"].startswith(
            "Thuốc: Agiclovir 5% Agimexpharm (Aciclovir 0.25g, Thuốc mỡ) — Thuốc kháng virus"
        )

    assert "Herpes simplex" in by_group["cong_dung"]["noi_dung"]

    assert "Tác dụng phụ:" in by_group["tac_dung_phu"]["noi_dung"]
    assert "Lưu ý đặc biệt:" in by_group["tac_dung_phu"]["noi_dung"]
    assert "Chống chỉ định" in by_group["tac_dung_phu"]["noi_dung"]

    cach_dung = by_group["cach_dung"]["noi_dung"]
    assert "Cách dùng: Thuốc mỡ dùng bôi ngoài." in cach_dung
    assert "Liều dùng: Thoa thuốc lên vùng da" in cach_dung
    assert "Đường dùng: Bôi ngoài da" in cach_dung

    assert by_group["bao_quan"]["noi_dung"].endswith("tránh ẩm và ánh sáng.")


def test_thoi_diem_dung_never_leaks_into_any_chunk():
    """An toan chinh cua Phase 2: du thoi_diem_dung CO gia tri (gia lap - thuc te
    data pharmacy luon de trong), no khong duoc phep lot vao bat ky chunk nao."""
    thuoc_with_timing = dict(SAMPLE_THUOC, thoi_diem_dung="Bôi vào buổi sáng và tối trước khi ngủ")
    chunks = build_chunks_for_drug(thuoc_with_timing)
    assert len(chunks) == 4
    for c in chunks:
        assert "Bôi vào buổi sáng và tối trước khi ngủ" not in c["noi_dung"]


def test_missing_bao_quan_skips_that_chunk_only():
    thuoc_no_bao_quan = dict(SAMPLE_THUOC, huong_dan_bao_quan="")
    chunks = build_chunks_for_drug(thuoc_no_bao_quan)
    assert len(chunks) == 3
    assert "bao_quan" not in {c["field_group"] for c in chunks}


def test_prefix_handles_empty_ham_luong_or_dang_thuoc():
    """Phat hien 2026-08-08: du ham_luong/dang_thuoc bat buoc trong schema, 5 ban ghi
    thuc te (danh muc crawl sau, chua qua buoc don du lieu) van bi rong 1 trong 2 -
    vd 'Cetimed 10mg Medochemie 1x10' (dang_thuoc rong)."""
    missing_dang_thuoc = dict(SAMPLE_THUOC, dang_thuoc="")
    chunks = build_chunks_for_drug(missing_dang_thuoc)
    noi_dung = chunks[0]["noi_dung"]
    assert "(, " not in noi_dung
    assert ", )" not in noi_dung
    assert noi_dung.startswith("Thuốc: Agiclovir 5% Agimexpharm (Aciclovir 0.25g) —")

    missing_both = dict(SAMPLE_THUOC, ham_luong="", dang_thuoc="")
    chunks2 = build_chunks_for_drug(missing_both)
    noi_dung2 = chunks2[0]["noi_dung"]
    assert "()" not in noi_dung2
    assert noi_dung2.startswith("Thuốc: Agiclovir 5% Agimexpharm — Thuốc kháng virus")


def test_oversized_field_group_splits_into_multiple_chunks_under_token_limit():
    """Phat hien 2026-08-08 luc chay Phase 3 that: thuoc phoi hop nhieu hoat
    chat (vd Triplixam) co luu_y_dac_biet ~40000 ky tu, vuot 8192 token cua
    OpenAI embedding API. Gia lap tinh huong nay bang 1 luu_y_dac_biet cuc dai,
    kiem tra tach thanh nhieu chunk, khong chunk nao vuot MAX_TOKENS_PER_CHUNK,
    va khong mat noi dung (moi cau trong ban goc phai xuat hien o dau do)."""
    huge_note = " ".join(f"Câu cảnh báo an toàn số {i} nói về tương tác thuốc." for i in range(400))
    thuoc_huge = dict(SAMPLE_THUOC, luu_y_dac_biet=[huge_note])

    chunks = build_chunks_for_drug(thuoc_huge)
    tac_dung_phu_chunks = [c for c in chunks if c["field_group"] == "tac_dung_phu"]

    assert len(tac_dung_phu_chunks) > 1, "phai tach thanh >1 chunk"
    for c in tac_dung_phu_chunks:
        assert _count_tokens(c["noi_dung"]) <= MAX_TOKENS_PER_CHUNK

    combined = " ".join(c["noi_dung"] for c in tac_dung_phu_chunks)
    assert "Câu cảnh báo an toàn số 0 " in combined
    assert "Câu cảnh báo an toàn số 399 " in combined
