"""
Tra cứu thuốc trong danh mục theo tên bác sĩ gõ.

Đây là cửa duy nhất để các domain khác lấy `dang_thuoc` của một thuốc. Trường
đó quyết định một liều có xác minh được bằng ảnh hay không, nên lấy sai nó
nghiêm trọng hơn hẳn việc không tìm thấy: thà nói "không có thuốc này" còn hơn
trả về một thuốc gần giống rồi ghi vào đơn một dạng bào chế sai.

Bỏ dấu trước khi so khớp, cả hai phía. Bác sĩ gõ nhanh thường không bỏ dấu
("amlodipin"), mà tên trong danh mục thì có dấu ("Amlodipine Stada 10mg"). Hàm
`unaccent()` chạy TRONG SQL chứ không ở Python — cùng hàm đã dùng lúc nạp dữ
liệu, nếu hai bên bỏ dấu khác nhau thì tìm sẽ trượt mà không báo lỗi gì.

Xếp hạng theo ba bậc, chặt trước lỏng sau:
    1. khớp từ đầu tên   "amlodipin" -> "Amlodipine Stada 10mg"
    2. chứa trong tên    "stada"     -> "Amlodipine Stada 10mg"
    3. gần giống         "amlodipm"  -> "Amlodipine Stada 10mg"  (gõ sai)

Bậc 3 dùng `similarity()` của pg_trgm, có ngưỡng để không trả về rác — gõ
"xyz" phải ra rỗng chứ không ra một thuốc ngẫu nhiên.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

# Dưới ngưỡng này coi như không liên quan. 0.3 là mặc định của pg_trgm; giữ
# nguyên vì tên thuốc ngắn, hạ thấp hơn sẽ trả về thuốc không liên quan gì.
NGUONG_GAN_GIONG = 0.3

# Chặn trên số kết quả mỗi lần tra, kể cả khi bên gọi xin nhiều hơn: danh mục
# có 3562 thuốc, gõ một chữ cái mà trả hết là đơ trình duyệt.
GIOI_HAN_TOI_DA = 50


@dataclass(frozen=True)
class ThuocTimDuoc:
    """Đủ để điền một dòng thuốc vào đơn, không hơn.

    Không trả `tac_dung`/`tac_dung_phu` — những thứ đó thuộc luồng RAG
    (`drug_chunks`), và trả kèm ở đây sẽ khiến ô tìm kiếm tải về hàng chục KB
    văn bản cho mỗi lần gõ phím.
    """

    drug_id: str
    ten_thuoc: str
    dang_thuoc: str
    duong_dung: str
    ham_luong: str | None
    tong_so_luong: str | None
    muc_nghiem_trong: str | None

    def to_dict(self) -> dict:
        return {
            "drug_id": self.drug_id,
            "ten_thuoc": self.ten_thuoc,
            "dang_thuoc": self.dang_thuoc,
            "duong_dung": self.duong_dung,
            "ham_luong": self.ham_luong,
            "tong_so_luong": self.tong_so_luong,
            "muc_nghiem_trong": self.muc_nghiem_trong,
        }


@dataclass(frozen=True)
class ChiTietThuoc:
    """Một thuốc kèm phần văn bản mô tả — cho trang tra cứu của bác sĩ.

    KHÁC `ThuocTimDuoc`: bản đó cố ý không mang `cong_dung`/`tac_dung_phu` vì
    ô gợi ý gọi nó mỗi lần gõ phím. Ở đây chỉ MỘT thuốc, lấy khi bác sĩ bấm mở
    chi tiết, nên tải kèm văn bản là hợp lý.

    4 trường văn bản lấy từ `drug_chunks` (field_group), và chỉ 226/3562 thuốc
    đã được embed — thuốc chưa có chunk trả về `None`, KHÔNG phải lỗi.
    """

    thuoc: ThuocTimDuoc
    danh_muc: str | None
    cong_dung: str | None
    tac_dung_phu: str | None
    cach_dung: str | None
    bao_quan: str | None


_CHON = (
    "SELECT id, ten_thuoc, dang_thuoc, duong_dung, ham_luong, tong_so_luong, muc_nghiem_trong"
    " FROM drug"
)

# word_similarity(ngan, dai) chu KHONG phai similarity(): tu khoa bac si go
# ngan ("amlodipm") con ten trong danh muc dai ("Amlodipin 5 Domesco 3x10").
# similarity() so hai chuoi theo TOAN BO do dai nen phat rat nang cap ngan-dai
# - do sai chinh ta mot chu cung tut duoi nguong. word_similarity() tim doan
# khop tot nhat BEN TRONG chuoi dai, dung cho tinh huong nay. Cung ly do da
# ghi trong backend/services/retrieval.py.
_TIM = text(
    f"{_CHON}"
    " WHERE ten_thuoc_unaccent ILIKE '%' || unaccent(:q) || '%'"
    "    OR word_similarity(unaccent(:q), ten_thuoc_unaccent) > :nguong"
    " ORDER BY (ten_thuoc_unaccent ILIKE unaccent(:q) || '%') DESC,"
    "          word_similarity(unaccent(:q), ten_thuoc_unaccent) DESC,"
    "          ten_thuoc"
    " LIMIT :gioi_han"
)

_THEO_ID = text(f"{_CHON} WHERE id = :drug_id")

# Ban day du cho trang tra cuu - them `danh_muc` so voi _CHON.
_CHI_TIET_THEO_ID = text(
    "SELECT id, ten_thuoc, dang_thuoc, duong_dung, ham_luong, tong_so_luong,"
    "       muc_nghiem_trong, danh_muc"
    " FROM drug WHERE id = :drug_id"
)

# 4 chunk/thuoc (cong_dung|tac_dung_phu|cach_dung|bao_quan). Chi lay 2 cot can
# hien thi - KHONG lay `embedding` (1536 so thuc, khong dung de doc).
_CHUNK_THEO_ID = text(
    "SELECT field_group, noi_dung FROM drug_chunks WHERE drug_id = :drug_id"
)


def _to_thuoc(row) -> ThuocTimDuoc:
    return ThuocTimDuoc(
        drug_id=row.id,
        ten_thuoc=row.ten_thuoc,
        dang_thuoc=row.dang_thuoc,
        duong_dung=row.duong_dung,
        ham_luong=row.ham_luong,
        tong_so_luong=row.tong_so_luong,
        muc_nghiem_trong=row.muc_nghiem_trong,
    )


def tim_thuoc(db: Session, tu_khoa: str, gioi_han: int = 20) -> list[ThuocTimDuoc]:
    """Tìm thuốc theo tên. Từ khoá rỗng trả về danh sách rỗng.

    Trả rỗng thay vì trả toàn bộ danh mục: ô tìm kiếm gọi hàm này mỗi lần gõ
    phím, và lần gõ đầu tiên thường là lúc chuỗi vẫn còn rỗng.
    """
    tu_khoa = (tu_khoa or "").strip()
    if not tu_khoa:
        return []

    rows = db.execute(
        _TIM,
        {"q": tu_khoa, "nguong": NGUONG_GAN_GIONG, "gioi_han": min(max(gioi_han, 1), GIOI_HAN_TOI_DA)},
    ).all()
    return [_to_thuoc(r) for r in rows]


def lay_thuoc(db: Session, drug_id: str) -> ThuocTimDuoc | None:
    """Lấy đúng một thuốc theo id. `None` nếu không có trong danh mục.

    Dùng lúc lưu đơn thuốc: frontend gửi lên `drug_id` đã chọn, backend tra lại
    để lấy `dang_thuoc` từ danh mục thay vì tin vào những gì trình duyệt gửi.
    """
    row = db.execute(_THEO_ID, {"drug_id": drug_id}).first()
    return _to_thuoc(row) if row else None


def liet_ke_thuoc(
    db: Session,
    *,
    tu_khoa: str = "",
    dang_thuoc: str | None = None,
    duong_dung: str | None = None,
    gioi_han: int = 20,
    bo_qua: int = 0,
) -> tuple[list[ThuocTimDuoc], int]:
    """Duyệt danh mục cho trang tra cứu: lọc + phân trang, trả kèm tổng số.

    KHÁC `tim_thuoc()`: hàm đó phục vụ ô gợi ý gõ-từng-phím nên từ khoá rỗng
    trả rỗng. Ở đây từ khoá rỗng nghĩa là "xem cả danh mục" — bác sĩ mở trang
    tra cứu là muốn thấy danh sách ngay, chưa gõ gì.

    Xếp theo tên (không theo độ giống) khi không có từ khoá: phân trang chỉ ổn
    định khi thứ tự ổn định.
    """
    dieu_kien = []
    tham_so: dict = {}

    tu_khoa = (tu_khoa or "").strip()
    if tu_khoa:
        dieu_kien.append("ten_thuoc_unaccent ILIKE '%' || unaccent(:q) || '%'")
        tham_so["q"] = tu_khoa
    if dang_thuoc:
        dieu_kien.append("dang_thuoc = :dang_thuoc")
        tham_so["dang_thuoc"] = dang_thuoc
    if duong_dung:
        dieu_kien.append("duong_dung = :duong_dung")
        tham_so["duong_dung"] = duong_dung

    where = f" WHERE {' AND '.join(dieu_kien)}" if dieu_kien else ""

    tong = db.execute(text(f"SELECT count(*) FROM drug{where}"), tham_so).scalar_one()
    rows = db.execute(
        text(f"{_CHON}{where} ORDER BY ten_thuoc LIMIT :gioi_han OFFSET :bo_qua"),
        {
            **tham_so,
            "gioi_han": min(max(gioi_han, 1), GIOI_HAN_TOI_DA),
            "bo_qua": max(bo_qua, 0),
        },
    ).all()
    return [_to_thuoc(r) for r in rows], tong


def lay_bo_loc(db: Session) -> tuple[list[str], list[str]]:
    """Các giá trị `dang_thuoc` / `duong_dung` có thật trong danh mục.

    Đọc từ DB chứ không viết cứng: danh mục nạp từ file JSON ngoài, viết cứng
    thì thêm thuốc dạng mới là bộ lọc lặng lẽ bỏ sót.
    """
    dang = db.execute(
        text("SELECT DISTINCT dang_thuoc FROM drug WHERE dang_thuoc <> '' ORDER BY dang_thuoc")
    ).scalars().all()
    duong = db.execute(
        text("SELECT DISTINCT duong_dung FROM drug WHERE duong_dung <> '' ORDER BY duong_dung")
    ).scalars().all()
    return list(dang), list(duong)


def lay_chi_tiet_thuoc(db: Session, drug_id: str) -> ChiTietThuoc | None:
    """Một thuốc kèm phần mô tả, cho trang tra cứu. `None` nếu không có thuốc.

    Thuốc CÓ trong danh mục nhưng CHƯA embed vẫn trả về bình thường, 4 trường
    văn bản để `None` — đây là trường hợp thường gặp (226/3562 thuốc có chunk),
    không phải lỗi.
    """
    row = db.execute(_CHI_TIET_THEO_ID, {"drug_id": drug_id}).first()
    if row is None:
        return None

    doan = {
        r.field_group: r.noi_dung
        for r in db.execute(_CHUNK_THEO_ID, {"drug_id": drug_id}).all()
    }
    return ChiTietThuoc(
        thuoc=_to_thuoc(row),
        danh_muc=row.danh_muc,
        cong_dung=doan.get("cong_dung"),
        tac_dung_phu=doan.get("tac_dung_phu"),
        cach_dung=doan.get("cach_dung"),
        bao_quan=doan.get("bao_quan"),
    )


__all__ = [
    "GIOI_HAN_TOI_DA",
    "NGUONG_GAN_GIONG",
    "ChiTietThuoc",
    "ThuocTimDuoc",
    "lay_bo_loc",
    "lay_chi_tiet_thuoc",
    "lay_thuoc",
    "liet_ke_thuoc",
    "tim_thuoc",
]
