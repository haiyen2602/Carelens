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


__all__ = ["GIOI_HAN_TOI_DA", "NGUONG_GAN_GIONG", "ThuocTimDuoc", "lay_thuoc", "tim_thuoc"]
