"""Vong doi yeu cau bo sung thuoc: `PENDING -> APPROVED | REJECTED`.

Duong thoat cho FB-14. Xem ghi chu kien truc day du trong
backend/db/models.py::DrugRequest.

CHI ADMIN DUYET. Khong co tham so nao cho phep tao thang o trang thai da
duyet - cung nguyen tac voi `tao_phac_do()` (ADR-0010): muon sang trang thai
dung duoc thi phai goi `duyet_yeu_cau()`, va cho do ghi lai ai duyet luc nao.
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import DrugRequest
from backend.services.drug_knowledge import lay_thuoc
from backend.services.drug_requests.controlled_substances import tim_chat_bi_kiem_soat
from backend.services.drug_requests.errors import (
    ThuocBiKiemSoatError,
    TrangThaiYeuCauKhongHopLeError,
    TrungThuocTrongDanhMucError,
    YeuCauThuocKhongTonTaiError,
)

logger = logging.getLogger(__name__)

PENDING = "PENDING"
APPROVED = "APPROVED"
REJECTED = "REJECTED"

# Chi yeu cau dang cho moi xu ly duoc. Duyet lai cai da duyet la 409 chu khong
# phai loi im lang - admin can biet minh vua bam vao cai da xong roi.
CHO_XU_LY = frozenset({PENDING})


def _slug(chuoi: str) -> str:
    khong_dau = unicodedata.normalize("NFD", chuoi)
    khong_dau = "".join(ky_tu for ky_tu in khong_dau if unicodedata.category(ky_tu) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", khong_dau.lower()).strip("-")[:60] or "thuoc"


def _sinh_approved_drug_id(yeu_cau: DrugRequest) -> str:
    """`req-<slug>-<hash6>`.

    Tien to `req-` de nhin id la biet thuoc den tu duong ngoai le. Hash lay tu
    id cua chinh yeu cau (da la uuid) chu khong phai tu ten: hai yeu cau cung
    ten thuoc van ra hai id khac nhau, va id khong doi neu sau nay ai do sua
    lai ten hien thi.
    """
    hash6 = hashlib.sha256(yeu_cau.id.encode()).hexdigest()[:6]
    return f"req-{_slug(yeu_cau.ten_thuoc)}-{hash6}"


def tao_yeu_cau(
    db: Session,
    *,
    doctor_id: str,
    ten_thuoc: str,
    dang_thuoc: str,
    duong_dung: str,
    ham_luong: str | None = None,
    tong_so_luong: str | None = None,
    ly_do: str | None = None,
) -> DrugRequest:
    """Tao yeu cau moi. LUON o `PENDING`.

    Chan chat bi kiem soat NGAY TAI DAY thay vi doi toi buoc duyet: bac si
    nhan phan hoi ngay, va admin khong bao gio phai nhin thay loai yeu cau
    nay trong hang doi.
    """
    ten_thuoc = ten_thuoc.strip()

    chat_bi_chan = tim_chat_bi_kiem_soat(ten_thuoc)
    if chat_bi_chan is not None:
        # Ghi log de moi lan dinh deu truy vet duoc - ai gui, ten gi, chat nao.
        logger.warning(
            "drug_request_blocked doctor_id=%s chat=%s ten_thuoc=%r",
            doctor_id,
            chat_bi_chan,
            ten_thuoc,
        )
        raise ThuocBiKiemSoatError(
            f"{ten_thuoc!r} chứa hoạt chất bị kiểm soát ({chat_bi_chan}) nên không thể bổ sung "
            "qua đường này. Liên hệ quản trị viên nếu đây là nhầm lẫn.",
            ten_thuoc=ten_thuoc,
            chat=chat_bi_chan,
        )

    return _luu_yeu_cau_moi(
        db,
        requested_by_doctor_id=doctor_id,
        ten_thuoc=ten_thuoc,
        dang_thuoc=dang_thuoc.strip(),
        duong_dung=duong_dung.strip(),
        ham_luong=(ham_luong or "").strip() or None,
        tong_so_luong=(tong_so_luong or "").strip() or None,
        ly_do=(ly_do or "").strip() or None,
    )


def _luu_yeu_cau_moi(db: Session, **truong: object) -> DrugRequest:
    try:
        yeu_cau = DrugRequest(status=PENDING, **truong)
        db.add(yeu_cau)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Tao yeu cau bo sung thuoc that bai, da hoan tac.")
        raise
    db.refresh(yeu_cau)
    logger.info(
        "Bac si %s gui yeu cau bo sung thuoc %s (%r).",
        yeu_cau.requested_by_doctor_id,
        yeu_cau.id,
        yeu_cau.ten_thuoc,
    )
    return yeu_cau


def lay_yeu_cau(db: Session, request_id: str, *, for_update: bool = False) -> DrugRequest:
    stmt = select(DrugRequest).where(DrugRequest.id == request_id)
    if for_update:
        stmt = stmt.with_for_update()
    yeu_cau = db.execute(stmt).scalar_one_or_none()
    if yeu_cau is None:
        raise YeuCauThuocKhongTonTaiError(
            f"Không tìm thấy yêu cầu {request_id!r}.", request_id=request_id
        )
    return yeu_cau


def liet_ke_yeu_cau(
    db: Session,
    *,
    doctor_id: str | None = None,
    status: str | None = None,
) -> list[DrugRequest]:
    """`doctor_id` co gia tri => chi yeu cau cua chinh bac si do.

    Bac si khong duoc xem yeu cau cua nguoi khac - cung nguyen tac loc theo
    quan he da ghi trong user-roles.md, khong chi kiem tra role.
    """
    stmt = select(DrugRequest)
    if doctor_id is not None:
        stmt = stmt.where(DrugRequest.requested_by_doctor_id == doctor_id)
    if status is not None:
        stmt = stmt.where(DrugRequest.status == status)
    return list(db.execute(stmt.order_by(DrugRequest.created_at.desc())).scalars())


def duyet_yeu_cau(db: Session, request_id: str, *, admin_account_id: str, note: str | None = None) -> DrugRequest:
    """CUA DUY NHAT dua mot thuoc ngoai danh muc thanh ke duoc.

    Sinh `approved_drug_id` tai day - do la gia tri bac si se gui len trong
    `PrescriptionItemIn.drug_id`, va la thu `lay_thuoc()` tra cuu nguoc lai.
    """
    yeu_cau = lay_yeu_cau(db, request_id, for_update=True)
    _kiem_tra_dang_cho(yeu_cau)

    approved_drug_id = _sinh_approved_drug_id(yeu_cau)
    # Trung voi danh muc goc thi khong duyet: hai nguon cung tra ve mot id se
    # lam `lay_thuoc()` tra ve thuoc nao tuy thu tu tra cuu - khong xac dinh.
    if lay_thuoc(db, approved_drug_id) is not None:
        raise TrungThuocTrongDanhMucError(
            f"Đã có thuốc mang mã {approved_drug_id!r} trong danh mục.", drug_id=approved_drug_id
        )

    try:
        yeu_cau.status = APPROVED
        yeu_cau.approved_drug_id = approved_drug_id
        yeu_cau.reviewed_by_account_id = admin_account_id
        yeu_cau.reviewed_at = datetime.now(UTC)
        yeu_cau.review_note = (note or "").strip() or None
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Duyet yeu cau %s that bai, da hoan tac.", request_id)
        raise
    db.refresh(yeu_cau)

    logger.info(
        "Admin %s duyet yeu cau %s -> drug_id=%s.", admin_account_id, request_id, approved_drug_id
    )
    return yeu_cau


def tu_choi_yeu_cau(db: Session, request_id: str, *, admin_account_id: str, note: str) -> DrugRequest:
    """`note` BAT BUOC - bac si can biet vi sao bi tu choi de con sua."""
    note = note.strip()
    if not note:
        raise TrangThaiYeuCauKhongHopLeError("Phải ghi lý do khi từ chối yêu cầu.", request_id=request_id)

    yeu_cau = lay_yeu_cau(db, request_id, for_update=True)
    _kiem_tra_dang_cho(yeu_cau)

    try:
        yeu_cau.status = REJECTED
        yeu_cau.reviewed_by_account_id = admin_account_id
        yeu_cau.reviewed_at = datetime.now(UTC)
        yeu_cau.review_note = note
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Tu choi yeu cau %s that bai, da hoan tac.", request_id)
        raise
    db.refresh(yeu_cau)

    logger.info("Admin %s tu choi yeu cau %s.", admin_account_id, request_id)
    return yeu_cau


def _kiem_tra_dang_cho(yeu_cau: DrugRequest) -> None:
    if yeu_cau.status not in CHO_XU_LY:
        raise TrangThaiYeuCauKhongHopLeError(
            f"Yêu cầu đang ở trạng thái {yeu_cau.status!r}, không xử lý lại được.",
            request_id=yeu_cau.id,
            status=yeu_cau.status,
        )


def lay_thuoc_da_duyet(db: Session, drug_id: str) -> DrugRequest | None:
    """Tra ve yeu cau DA DUYET mang `approved_drug_id` nay, None neu khong.

    Diem noi giua bang nay va tang phan giai danh muc: xem
    services/drug_knowledge/__init__.py::lay_thuoc.
    """
    if not drug_id.startswith("req-"):
        # Loi ra som: id khong mang tien to `req-` chac chan khong phai thuoc
        # duyet qua duong nay, khoi phai vao DB.
        return None
    stmt = select(DrugRequest).where(
        DrugRequest.approved_drug_id == drug_id, DrugRequest.status == APPROVED
    )
    return db.execute(stmt).scalar_one_or_none()


def tim_thuoc_da_duyet(db: Session, tu_khoa: str, gioi_han: int = 20) -> list[DrugRequest]:
    """Tim trong cac thuoc da duyet, phuc vu o goi y cua bac si.

    Dung ILIKE chu khong dung word_similarity/unaccent nhu danh muc goc: tap
    nay nho (vai chuc dong), khong dang dung index trigram, va bang nay khong
    co cot `ten_thuoc_unaccent`.
    """
    tu_khoa = tu_khoa.strip()
    if not tu_khoa:
        return []
    stmt = (
        select(DrugRequest)
        .where(DrugRequest.status == APPROVED, DrugRequest.ten_thuoc.ilike(f"%{tu_khoa}%"))
        .order_by(DrugRequest.ten_thuoc)
        .limit(gioi_han)
    )
    return list(db.execute(stmt).scalars())


def liet_ke_thuoc_da_duyet(
    db: Session,
    *,
    tu_khoa: str = "",
    dang_thuoc: str | None = None,
    duong_dung: str | None = None,
) -> list[DrugRequest]:
    """Toan bo thuoc da duyet khop bo loc, KHONG phan trang.

    Khong phan trang o day co y: tap nay nho (vai chuc dong), va ben goi
    (drug_knowledge.liet_ke_thuoc) can biet TONG SO de tinh xem trang hien tai
    con cho trong bao nhieu. Phan trang hai nguon roi ghep lai o tang duoi se
    phai hoi tong so lan nua - vong ve khong loi gi.

    Loc `dang_thuoc`/`duong_dung` so khop CHINH XAC, cung quy uoc voi
    resolver.liet_ke_thuoc (`dang_thuoc = :dang_thuoc`), de hai nguon hieu
    cung mot bo loc tren giao dien.
    """
    stmt = select(DrugRequest).where(DrugRequest.status == APPROVED)
    if tu_khoa.strip():
        stmt = stmt.where(DrugRequest.ten_thuoc.ilike(f"%{tu_khoa.strip()}%"))
    if dang_thuoc:
        stmt = stmt.where(DrugRequest.dang_thuoc == dang_thuoc)
    if duong_dung:
        stmt = stmt.where(DrugRequest.duong_dung == duong_dung)
    return list(db.execute(stmt.order_by(DrugRequest.ten_thuoc)).scalars())


__all__ = [
    "APPROVED",
    "PENDING",
    "REJECTED",
    "duyet_yeu_cau",
    "lay_thuoc_da_duyet",
    "liet_ke_thuoc_da_duyet",
    "lay_yeu_cau",
    "liet_ke_yeu_cau",
    "tao_yeu_cau",
    "tim_thuoc_da_duyet",
    "tu_choi_yeu_cau",
]
