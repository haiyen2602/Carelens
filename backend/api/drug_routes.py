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

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.api.security import require_internal_secret
from backend.db.base import get_db
from backend.models.schemas import DrugSearchResponse, DrugSummary
from backend.services.drug_knowledge import GIOI_HAN_TOI_DA, tim_thuoc

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
