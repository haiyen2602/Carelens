"""Domain `drug-knowledge` — dữ liệu thuốc có nguồn (specs/domains.md).

Đây là cửa công khai của domain. Các domain khác import từ đây, không đào vào
module con — theo ADR-0002: "Mỗi domain có một chủ sở hữu dữ liệu duy nhất;
domain khác không truy vấn thẳng bảng của domain khác."

Cụ thể: `prescription` cần `dang_thuoc` để ghi vào đơn thuốc thì gọi
`lay_thuoc()`, không tự viết SQL vào bảng `drug`.
"""

import logging

from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.services.drug_knowledge.resolver import (
    GIOI_HAN_TOI_DA,
    NGUONG_GAN_GIONG,
    ChiTietThuoc,
    ThuocTimDuoc,
    # Trang tra cuu thuoc cua bac si (doctor/drugs) - di THANG qua resolver V1,
    # khong qua lop V2 ben duoi: lop do chi bao `tim_thuoc`/`lay_thuoc` (danh
    # muc cho form ke don), chua co doi ung V2 cho duyet/loc/chi tiet.
    #
    # `liet_ke_thuoc`/`lay_chi_tiet_thuoc` duoc BOC LAI o cuoi file (2026-08-21)
    # de noi them thuoc duyet qua `drug_request` - xem ghi chu o do. `lay_bo_loc`
    # KHONG boc: no chi sinh danh sach gia tri cho o loc, va mot dang bao che chi
    # ton tai o thuoc ngoai le se khong hien thanh lua chon (chap nhan duoc, ghi
    # lai o day de sau nay khong tuong la bo sot).
    lay_bo_loc,
)
from backend.services.drug_knowledge.resolver import (
    lay_chi_tiet_thuoc as _legacy_lay_chi_tiet_thuoc,
)
from backend.services.drug_knowledge.resolver import (
    lay_thuoc as _legacy_lay_thuoc,
)
from backend.services.drug_knowledge.resolver import (
    liet_ke_thuoc as _legacy_liet_ke_thuoc,
)
from backend.services.drug_knowledge.resolver import (
    tim_thuoc as _legacy_tim_thuoc,
)
from backend.services.drug_knowledge.v2_agent import DrugCatalogItem, get_v2_agent_knowledge_service

logger = logging.getLogger(__name__)


def _to_catalog_item(yeu_cau) -> DrugCatalogItem:  # noqa: ANN001 - DrugRequest, import tre
    """DrugRequest -> DrugCatalogItem.

    Tra ve DrugCatalogItem chu khong phai ThuocTimDuoc vi no co them alias
    `.id` cho cac cho goi cu doc `Drug.id`; hai kieu con lai giong het truong.
    `muc_nghiem_trong` de None: bac si tu khai thi khong co gia tri nao dang
    tin de dien, va de None an toan hon doan bua.
    """
    return DrugCatalogItem(
        drug_id=yeu_cau.approved_drug_id,
        ten_thuoc=yeu_cau.ten_thuoc,
        dang_thuoc=yeu_cau.dang_thuoc,
        duong_dung=yeu_cau.duong_dung,
        ham_luong=yeu_cau.ham_luong,
        tong_so_luong=yeu_cau.tong_so_luong,
        muc_nghiem_trong=None,
    )


def _chan_tren(gioi_han: int) -> int:
    """Cung cong thuc voi resolver.py - chan tren la GIOI_HAN_TOI_DA.

    Phai chan LAI sau khi ghep hai nguon: resolver da chan phan cua no roi,
    nhung noi them thuoc ngoai le vao thi tong lai vuot tran. Ben goi tin vao
    tran nay (o goi y go-tung-phim), khong duoc pha.
    """
    return min(max(gioi_han, 1), GIOI_HAN_TOI_DA)


def tim_thuoc(db: Session, tu_khoa: str, gioi_han: int = 20) -> list[DrugCatalogItem | ThuocTimDuoc]:
    """Search the V2 catalog by default while retaining V1/shadow rollback behavior.

    THEM 2026-08-21 (FB-14): ket qua duoc noi them cac thuoc da duyet qua
    `drug_request`. Xem ghi chu o `lay_thuoc()` ben duoi.

    Thuoc ngoai le dat SAU danh muc goc co y: thuoc chinh thuc luon hien truoc.
    He qua la voi tu khoa qua rong (danh muc goc da lap day tran), thuoc ngoai
    le bi day ra ngoai - chap nhan duoc, vi bac si go dung ten thuoc minh can
    thi so ket qua it va no van hien.
    """

    mode = get_settings().drug_knowledge_backend
    if mode == "v1":
        ket_qua = [*_legacy_tim_thuoc(db, tu_khoa, gioi_han), *_tim_thuoc_ngoai_le(db, tu_khoa)]
        return ket_qua[: _chan_tren(gioi_han)]

    v2_results = get_v2_agent_knowledge_service().search_catalog(tu_khoa, gioi_han)
    if mode == "shadow":
        v1_results = _legacy_tim_thuoc(db, tu_khoa, gioi_han)
        logger.info("drug_catalog_shadow v1_count=%s v2_count=%s", len(v1_results), len(v2_results))
        return [*v1_results, *_tim_thuoc_ngoai_le(db, tu_khoa)][: _chan_tren(gioi_han)]
    return [*v2_results, *_tim_thuoc_ngoai_le(db, tu_khoa)][: _chan_tren(gioi_han)]


def lay_thuoc(db: Session, drug_id: str) -> DrugCatalogItem | ThuocTimDuoc | None:
    """Resolve the public legacy slug through Canonical V2 by default.

    THEM 2026-08-21 (FB-14): danh muc goc miss thi tra tiep bang
    `drug_request` (cac dong da duyet). Vi sao phai co nhanh nay: catalog V2
    doc tu file JSONL trong image va duoc @lru_cache, nen THEM DONG VAO BANG
    `drug` KHONG co tac dung gi - thuoc admin vua duyet se van khong ke duoc.

    Thu tu tra cuu la co y: danh muc goc THANG. Thuoc ngoai le chi duoc nhin
    toi khi danh muc goc khong co - khong bao gio de duong ngoai le ghi de
    len du lieu co nguon (ADR-0012).
    """

    mode = get_settings().drug_knowledge_backend
    if mode == "v1":
        return _legacy_lay_thuoc(db, drug_id) or _lay_thuoc_ngoai_le(db, drug_id)

    v2_result = get_v2_agent_knowledge_service().get_catalog_item(drug_id)
    if mode == "shadow":
        v1_result = _legacy_lay_thuoc(db, drug_id)
        logger.info("drug_catalog_shadow id=%s v1_found=%s v2_found=%s", drug_id, bool(v1_result), bool(v2_result))
        return v1_result or _lay_thuoc_ngoai_le(db, drug_id)
    return v2_result or _lay_thuoc_ngoai_le(db, drug_id)


# Import TRE trong hai ham duoi: `drug_requests.service` import nguoc lai
# `lay_thuoc` tu chinh module nay (de chan trung id luc duyet), import o dau
# file se thanh vong.
def _lay_thuoc_ngoai_le(db: Session, drug_id: str) -> DrugCatalogItem | None:
    from backend.services.drug_requests.service import lay_thuoc_da_duyet

    yeu_cau = lay_thuoc_da_duyet(db, drug_id)
    return _to_catalog_item(yeu_cau) if yeu_cau is not None else None


def _tim_thuoc_ngoai_le(db: Session, tu_khoa: str) -> list[DrugCatalogItem]:
    from backend.services.drug_requests.service import tim_thuoc_da_duyet

    return [_to_catalog_item(yc) for yc in tim_thuoc_da_duyet(db, tu_khoa)]


def _to_thuoc_tim_duoc(yeu_cau) -> ThuocTimDuoc:  # noqa: ANN001 - DrugRequest, import tre
    """Nhu `_to_catalog_item` nhung ra kieu cua resolver V1.

    Can ban rieng vi `ChiTietThuoc.thuoc` khai bao kieu `ThuocTimDuoc`; hai
    dataclass co truong giong het nhau nhung khong thay the nhau ve kieu.
    """
    return ThuocTimDuoc(
        drug_id=yeu_cau.approved_drug_id,
        ten_thuoc=yeu_cau.ten_thuoc,
        dang_thuoc=yeu_cau.dang_thuoc,
        duong_dung=yeu_cau.duong_dung,
        ham_luong=yeu_cau.ham_luong,
        tong_so_luong=yeu_cau.tong_so_luong,
        muc_nghiem_trong=None,
    )


def liet_ke_thuoc(
    db: Session,
    *,
    tu_khoa: str = "",
    dang_thuoc: str | None = None,
    duong_dung: str | None = None,
    gioi_han: int = 20,
    bo_qua: int = 0,
) -> tuple[list[ThuocTimDuoc], int]:
    """Duyet danh muc cho trang tra cuu, CO ke ca thuoc duyet qua drug_request.

    THEM 2026-08-21: truoc do trang tra cuu di thang bang `drug` nen mot thuoc
    admin vua duyet thi ke don duoc nhung tra cuu lai khong thay - vua ton tai
    vua khong tuy cho hoi.

    Thuoc ngoai le xep o CUOI toan bo danh sach (khong phai cuoi moi trang):
    chi duoc chen vao khi trang hien tai con cho trong sau khi da lay het phan
    danh muc goc. Nho vay phan trang van dung - khong dong nao bi lap lai o
    nhieu trang, va tong so khop voi so dong thuc su duyet qua duoc.
    """
    from backend.services.drug_requests.service import liet_ke_thuoc_da_duyet

    items, tong_goc = _legacy_liet_ke_thuoc(
        db,
        tu_khoa=tu_khoa,
        dang_thuoc=dang_thuoc,
        duong_dung=duong_dung,
        gioi_han=gioi_han,
        bo_qua=bo_qua,
    )
    ngoai_le = liet_ke_thuoc_da_duyet(
        db, tu_khoa=tu_khoa, dang_thuoc=dang_thuoc, duong_dung=duong_dung
    )
    if not ngoai_le:
        return items, tong_goc

    # Dung `_chan_tren` chu khong phai `gioi_han` tho: resolver da chan phan cua
    # no o GIOI_HAN_TOI_DA, lay hieu voi so tho se cho phep chen thua rat nhieu
    # dong khi ben goi xin mot gioi_han lon.
    con_trong = _chan_tren(gioi_han) - len(items)
    if con_trong > 0:
        # Trang hien tai da het phan danh muc goc -> lap day bang thuoc ngoai le.
        # `bat_dau` la vi tri trong danh sach ngoai le tuong ung voi `bo_qua`.
        bat_dau = max(0, bo_qua - tong_goc)
        items = [*items, *[_to_thuoc_tim_duoc(yc) for yc in ngoai_le[bat_dau : bat_dau + con_trong]]]
    return items, tong_goc + len(ngoai_le)


def lay_chi_tiet_thuoc(db: Session, drug_id: str) -> ChiTietThuoc | None:
    """Chi tiet mot thuoc, ke ca thuoc duyet qua drug_request.

    THEM 2026-08-21: truoc do bac si ke duoc mot thuoc ngoai le roi bam xem
    chi tiet chinh no thi nhan 404.

    4 truong van ban de None - thuoc ngoai le khong co dong nao trong
    `drug_chunks`. Day KHONG phai truong hop dac biet: resolver da tra None
    cho ca thuoc trong danh muc goc ma chua embed, giao dien da xu ly duoc.
    """
    from backend.services.drug_requests.service import lay_thuoc_da_duyet

    chi_tiet = _legacy_lay_chi_tiet_thuoc(db, drug_id)
    if chi_tiet is not None:
        return chi_tiet

    yeu_cau = lay_thuoc_da_duyet(db, drug_id)
    if yeu_cau is None:
        return None
    return ChiTietThuoc(
        thuoc=_to_thuoc_tim_duoc(yeu_cau),
        danh_muc=None,
        cong_dung=None,
        tac_dung_phu=None,
        cach_dung=None,
        bao_quan=None,
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
