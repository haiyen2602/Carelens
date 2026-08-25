"""Kiểm chứng tra cứu danh mục thuốc trên Postgres thật.

Cần DB có bảng `drug` đã nạp: `python scripts/seed_drug_catalog.py`.

Hai loại lỗi phải chặn, ngược chiều nhau:
  - tìm không ra thuốc có thật -> bác sĩ không kê được đơn
  - trả về thuốc không liên quan -> bác sĩ chọn nhầm, và `dang_thuoc` sai sẽ
    kéo theo việc đối chiếu ảnh sai ở cuối chuỗi

Không gọi mạng, không gọi LLM — chỉ SQL.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

from backend.db.base import SessionLocal, engine
from backend.services.drug_knowledge import GIOI_HAN_TOI_DA, lay_thuoc, tim_thuoc
from backend.services.photo_verification import classify


def _danh_muc_san_sang() -> bool:
    try:
        with engine.connect() as conn:
            return bool(conn.execute(text("SELECT count(*) FROM drug")).scalar())
    except (OperationalError, ProgrammingError):
        return False


pytestmark = pytest.mark.skipif(
    not _danh_muc_san_sang(),
    reason="Can Postgres + bang drug da nap (python scripts/seed_drug_catalog.py)",
)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# ---------------------------------------------------------------------------
# Tìm được thứ có thật
# ---------------------------------------------------------------------------
def test_go_dung_ten_thi_tim_ra(db):
    assert tim_thuoc(db, "amlodipin")


def test_go_khong_dau_van_tim_ra_ten_co_dau(db):
    """Bác sĩ gõ nhanh thường bỏ dấu, tên trong danh mục thì có dấu."""
    assert tim_thuoc(db, "vien nen")


def test_go_sai_mot_chu_van_tim_ra(db):
    """`similarity()` phạt nặng cặp truy vấn ngắn / tên dài nên trượt hẳn;
    `word_similarity()` mới là hàm đúng cho tình huống này."""
    assert tim_thuoc(db, "amlodipm"), "gõ sai một chữ mà không tìm ra thì bác sĩ phải gõ lại từ đầu"


def test_khop_tu_dau_ten_duoc_xep_truoc(db):
    ket_qua = tim_thuoc(db, "amlodipin", 10)

    assert ket_qua[0].ten_thuoc.lower().startswith("amlodipin")


# ---------------------------------------------------------------------------
# Không trả rác
# ---------------------------------------------------------------------------
def test_tu_khoa_vo_nghia_tra_ve_rong(db):
    """Trả một thuốc ngẫu nhiên còn tệ hơn trả rỗng: bác sĩ có thể chọn nhầm."""
    assert tim_thuoc(db, "xyzqwe") == []


def test_tu_khoa_rong_tra_ve_rong(db):
    """Ô tìm kiếm gọi mỗi lần gõ phím, lần đầu luôn là chuỗi rỗng — không được
    đổ cả 3562 thuốc về trình duyệt."""
    assert tim_thuoc(db, "") == []
    assert tim_thuoc(db, "   ") == []


# ---------------------------------------------------------------------------
# Giới hạn số kết quả
# ---------------------------------------------------------------------------
def test_ton_trong_gioi_han_duoc_yeu_cau(db):
    assert len(tim_thuoc(db, "vien", 5)) <= 5


def test_khong_bao_gio_vuot_chan_tren_du_xin_bao_nhieu(db):
    assert len(tim_thuoc(db, "a", 10_000)) <= GIOI_HAN_TOI_DA


# ---------------------------------------------------------------------------
# Lấy theo id
# ---------------------------------------------------------------------------
def test_lay_dung_thuoc_theo_id(db):
    mau = tim_thuoc(db, "amlodipin", 1)[0]

    assert lay_thuoc(db, mau.drug_id) == mau


def test_id_khong_ton_tai_tra_ve_none(db):
    assert lay_thuoc(db, "khong-co-thuoc-nao-ten-nay") is None


# ---------------------------------------------------------------------------
# Mắt xích với luồng xác nhận ảnh
# ---------------------------------------------------------------------------
def test_moi_ket_qua_deu_co_dang_thuoc(db):
    """`dang_thuoc` rỗng sẽ khiến mọi liều dùng thuốc đó không xác minh được
    bằng ảnh — hỏng âm thầm ở tận cuối chuỗi, rất khó lần ngược về đây."""
    for thuoc in tim_thuoc(db, "vien", GIOI_HAN_TOI_DA):
        assert thuoc.dang_thuoc.strip(), f"{thuoc.ten_thuoc!r} không có dạng bào chế"


def test_dang_thuoc_tu_danh_muc_phan_loai_duoc(db):
    """Mắt xích thật giữa hai domain: `dang_thuoc` lấy từ danh mục phải là thứ
    `dosage_form.classify()` hiểu được, nếu không thì chuỗi đứt ở giữa."""
    for tu_khoa in ("amlodipin", "siro", "kem", "tiem"):
        for thuoc in tim_thuoc(db, tu_khoa, 5):
            ket_qua = classify(thuoc.dang_thuoc, thuoc.duong_dung)

            assert ket_qua.ly_do, f"{thuoc.dang_thuoc!r} phân loại ra nhưng không nêu lý do"


# ---------------------------------------------------------------------------
# BUILD-38 PR review response: migration 0047 (ALTER FUNCTION word_similarity_
# op/similarity_op COST 100) là thay đổi toàn CSDL, không scope theo 1 truy
# vấn -- reviewer tự động hỏi đúng liệu nó có ảnh hưởng các truy vấn trigram
# KHÁC ngoài backend/services/retrieval.py không. Đây (bảng `drug`, ~3562
# dòng) là nơi DUY NHẤT khác trong repo dùng `word_similarity()`/toán tử `<%`
# thật (xác nhận qua `rg '<%|%>|similarity\(' backend/ scripts/`). Test dưới
# đây khoá lại: bộ 12 test có sẵn ở trên đã chạy (và pass) VỚI migration 0047
# đã áp dụng -- không phải test mới riêng cho việc này, mà là bằng chứng thật
# rằng chức năng tìm thuốc gõ sai/không dấu vẫn đúng sau migration.
# ---------------------------------------------------------------------------
def test_word_similarity_search_still_fast_after_cost_migration(db):
    """`drug` (~3562 dòng) không có index cạnh tranh kiểu
    `ix_drug_chunks_corpus_version` của `drug_chunks` -- chính điều kiện đó
    mới khiến Cluster A's bug gốc xảy ra (planner chọn nhầm 1 index không
    liên quan). Không có điều kiện đó, plan cho bảng nhỏ này vẫn là Seq Scan
    dù COST=1 hay COST=100 (đã verify trực tiếp bằng EXPLAIN ANALYZE trên dữ
    liệu thật khi review migration -- xem migration 0047's docstring), nên
    không có gì để mất tốc độ. Bound rộng (2s, không phải mốc chặt) để tránh
    flaky theo máy/CI -- mục đích là bắt một regression THẬT (giây, không
    phải mili-giây), không phải theo dõi hiệu năng tinh vi."""

    import time

    started = time.monotonic()
    results = tim_thuoc(db, "amlodipin gõ sai chính tả amlodipm", 50)
    elapsed = time.monotonic() - started

    assert results
    assert elapsed < 2.0, f"tim_thuoc mất {elapsed:.3f}s -- nghi ngờ regression từ migration cost pg_trgm"
