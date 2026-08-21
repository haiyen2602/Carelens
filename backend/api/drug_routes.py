"""
Tra cứu thuốc trong danh mục — cho ô chọn thuốc trên form kê đơn của bác sĩ.

Thay thế `DRUG_DATABASE` (19 thuốc viết cứng trong `frontend/src/lib/drugs.ts`)
bằng 3562 thuốc thật. Điểm quan trọng không phải là số lượng mà là `dang_thuoc`:
danh sách mock không có trường đó, nên đơn thuốc kê ra không biết là viên nén
hay lọ siro, và luồng xác nhận bằng ảnh không có gì để đối chiếu.

CHƯA CÓ TRONG api-contracts.md. ADR-0003 yêu cầu chốt contract trước khi code,
nên endpoint này phải được thêm vào specs/api-contracts.md §2 và review trước
khi coi là ổn định. Hình dạng ở đây cố ý bám sát các DTO sẵn có để lúc bổ sung
vào tài liệu không phải đổi gì.

Chỉ ĐỌC, không ghi. Nhưng vẫn qua `require_internal_secret` như mọi endpoint
khác — danh mục thuốc là dữ liệu của dự án, không phải API công khai.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.orm import Session

from backend.api.security import require_internal_secret
from backend.db.base import get_db
from backend.models.schemas import (
    DrugCatalogResponse,
    DrugDetail,
    DrugFiltersResponse,
    DrugSearchResponse,
    DrugSummary,
)
from backend.services.drug_knowledge import (
    GIOI_HAN_TOI_DA,
    lay_bo_loc,
    lay_chi_tiet_thuoc,
    liet_ke_thuoc,
    tim_thuoc,
)

drug_router = APIRouter()


@drug_router.get(
    "/drugs",
    response_model=DrugSearchResponse,
    dependencies=[Depends(require_internal_secret)],
)
def search_drugs(
    q: str = Query("", description="Tên thuốc, có dấu hoặc không dấu đều được"),
    limit: int = Query(20, ge=1, le=GIOI_HAN_TOI_DA),
    db: Session = Depends(get_db),
) -> DrugSearchResponse:
    """Tìm thuốc theo tên.

    Từ khoá rỗng trả về danh sách rỗng chứ không trả cả danh mục: ô tìm kiếm
    gọi endpoint này mỗi lần gõ phím, và lần đầu tiên thường là lúc ô còn trống.
    """
    ket_qua = tim_thuoc(db, q, limit)
    return DrugSearchResponse(
        query=q,
        count=len(ket_qua),
        items=[DrugSummary(**thuoc.to_dict()) for thuoc in ket_qua],
    )


@drug_router.get(
    "/drugs/catalog",
    response_model=DrugCatalogResponse,
    dependencies=[Depends(require_internal_secret)],
)
def browse_drugs(
    q: str = Query("", description="Loc theo ten, co dau hoac khong dau"),
    dang_thuoc: str | None = Query(default=None),
    duong_dung: str | None = Query(default=None),
    limit: int = Query(20, ge=1, le=GIOI_HAN_TOI_DA),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> DrugCatalogResponse:
    """Duyet danh muc cho trang tra cuu cua bac si.

    KHAC search_drugs() o tren: tu khoa RONG o day tra ve trang dau cua ca
    danh muc (bac si mo trang la thay danh sach ngay), con search_drugs() tra
    rong vi no phuc vu o goi y go-tung-phim.

    PHAI khai bao TRUOC "/drugs/{drug_id}": neu doi cho, "/drugs/catalog" se
    roi vao get_drug() voi drug_id="catalog" va tra 404.
    """
    items, total = liet_ke_thuoc(
        db,
        tu_khoa=q,
        dang_thuoc=dang_thuoc,
        duong_dung=duong_dung,
        gioi_han=limit,
        bo_qua=offset,
    )
    return DrugCatalogResponse(
        total=total,
        items=[DrugSummary(**thuoc.to_dict()) for thuoc in items],
    )


@drug_router.get(
    "/drugs/filters",
    response_model=DrugFiltersResponse,
    dependencies=[Depends(require_internal_secret)],
)
def drug_filters(db: Session = Depends(get_db)) -> DrugFiltersResponse:
    """Gia tri co that cua dang_thuoc/duong_dung, do vao dropdown loc.

    Cung ly do thu tu nhu browse_drugs(): phai dung TRUOC "/drugs/{drug_id}".
    """
    dang, duong = lay_bo_loc(db)
    return DrugFiltersResponse(dang_thuoc=dang, duong_dung=duong)


@drug_router.get(
    "/drugs/{drug_id}",
    response_model=DrugDetail,
    dependencies=[Depends(require_internal_secret)],
)
def get_drug(drug_id: str, db: Session = Depends(get_db)) -> DrugDetail:
    """Chi tiet mot thuoc — trang tra cuu cua bac si.

    CHI DOC, giong search_drugs() o tren: khong co endpoint tao/sua/xoa thuoc
    trong file nay. Danh muc thuoc duoc nap bang script (scripts/
    seed_drug_catalog.py), khong sua qua API.
    """
    chi_tiet = lay_chi_tiet_thuoc(db, drug_id)
    if chi_tiet is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="Thuốc không có trong danh mục"
        )

    return DrugDetail(
        **chi_tiet.thuoc.to_dict(),
        danh_muc=chi_tiet.danh_muc,
        cong_dung=chi_tiet.cong_dung,
        tac_dung_phu=chi_tiet.tac_dung_phu,
        cach_dung=chi_tiet.cach_dung,
        bao_quan=chi_tiet.bao_quan,
    )
