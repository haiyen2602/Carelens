"""Rao can TAM cho endpoint cham vao du lieu benh nhan, cho toi khi auth-api
that co (chatbot-rag-design.md muc 10 #10 - RUI RO BAO MAT CHAN PRODUCTION).

KHONG PHAI auth that - khong co khai niem user/role, khong biet request tu
ai, chi biet co dung 1 chuoi bi mat (shared secret) hay khong. Muc dich DUY
NHAT: chan truy cap tu NGOAI pham vi thu nghiem noi bo (Architect, mentor,
BTC) trong luc auth-api chua co timeline - khong phai giai phap phan quyen
cuoi cung.

XOA dependency nay khoi route NGAY khi auth-api (JWT that, api-contracts.md
§1) duoc xay - day la rao can tam, gan vao 1 diem duy nhat (route) de de
xoa, khong rai rac nhieu noi."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status

from backend.config import get_settings
from backend.models.schemas import ConversationChatRequest
from backend.services.auth import TokenError, decode_token

INTERNAL_SECRET_HEADER = "X-Internal-Secret"


@dataclass(frozen=True)
class CurrentUser:
    """Danh tinh nguoi goi da xac thuc (TASK-010) - giai ma tu JWT
    (Authorization: Bearer <token>), KHONG bao gio doc thang tu body/query.
    `patient_id`/`doctor_id` la claim mo rong (xem backend/services/auth.py::
    create_access_token), co the None neu tai khoan khong co lien ket."""

    id: str
    role: str
    patient_id: str | None
    doctor_id: str | None


async def get_current_user(
    authorization: str | None = Header(default=None),
) -> CurrentUser:
    """FastAPI dependency - xac thuc JWT that (TASK-010, api-contracts.md
    §1: `Authorization: Bearer <JWT>`). 401 neu thieu header, sai dinh dang,
    sai chu ky, hoac het han - KHONG phan biet ly do cu the trong response
    (tranh lo thong tin cho ke tan cong do JWT), chi log noi bo neu can."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Thieu hoac sai dinh dang Authorization: Bearer <JWT>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Thieu/het han JWT",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    sub = payload.get("sub")
    role = payload.get("role")
    if not sub or not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT thieu sub/role",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return CurrentUser(
        id=sub, role=role, patient_id=payload.get("patient_id"), doctor_id=payload.get("doctor_id")
    )


def require_role(*roles: str):
    """Factory dependency - 403 neu role cua CurrentUser khong nam trong
    `roles`. Dung cho endpoint sau nay can khoa theo ma tran quyen
    (user-roles.md) - CHUA ap dung cho /api/v1/chat trong TASK-010 (pham vi
    task chi la xac thuc danh tinh, chua lam RBAC day du theo tung role -
    xem ghi chu trong tasks/TASK-010-auth-api.md)."""

    async def _check(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Khong co quyen")
        return current_user

    return _check


async def require_internal_secret(
    x_internal_secret: str | None = Header(default=None, alias=INTERNAL_SECRET_HEADER),
) -> None:
    """FastAPI dependency - chan request thieu hoac sai header
    `X-Internal-Secret` (gia tri dung dat qua env var `INTERNAL_AUTH_SECRET`,
    KHONG hardcode gia tri that trong code - xem backend/config.py). FAIL-CLOSED
    co y: neu secret chua duoc cau hinh (van con gia tri mac dinh ro rang la
    khong that), request van bi tu choi trong moi truong khong khop, khong
    am tham cho qua - phong ve ky thuat dang tin hon viec dua vao moi nguoi
    lien quan deu nho dung chinh sach da ghi trong tai lieu."""
    settings = get_settings()
    if x_internal_secret is None or x_internal_secret != settings.internal_auth_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-Internal-Secret header (temp auth gate - chatbot-rag-design.md mục 10 #10)",
        )


def get_current_patient_id(request: ConversationChatRequest, current_user: CurrentUser) -> str:
    """Vòng 2 (chatbot-rag-design.md mục 14, mục 10 #10) - 1 CHỖ NỐI DUY NHẤT
    để đọc patient_id của người đang gọi. Mọi endpoint/node PHẢI gọi qua hàm
    này - KHÔNG đọc `request.patient_id` thẳng ở bất kỳ đâu khác (kể cả
    trong chính chat_routes.py).

    TASK-010 (auth-api thật đã xây): đổi implementation BÊN TRONG hàm này
    như ghi chú cũ đã dự tính — nhưng KHÔNG thể giữ nguyên chữ ký 1 tham số
    như dự tính ban đầu, vì để đọc JWT cần danh tính đã xác thực
    (`CurrentUser`), thứ mà `ConversationChatRequest` (chỉ là body) không
    mang theo. Vì vậy chỗ gọi DUY NHẤT trong `chat_routes.py` phải thêm
    `Depends(get_current_user)` — đây là điểm lệch nhỏ so với ghi chú gốc,
    chấp nhận được vì vẫn chỉ có 1 chỗ gọi cần sửa.

    Role `patient`: BỎ QUA `request.patient_id`, luôn dùng `patient_id` của
    chính JWT — đúng lỗ hổng đã nêu trong ghi chú gốc (không cho phép 1
    bệnh nhân tự gõ patient_id của người khác vào request).

    Role `doctor`/`caregiver`/`admin`: vẫn TIN `request.patient_id` (gọi hộ
    bệnh nhân) như hành vi cũ — CHƯA kiểm tra quan hệ liên kết (bác sĩ có
    thật sự phụ trách bệnh nhân này không, `user-roles.md`) vì mô hình liên
    kết đầy đủ chưa có trong TASK-010 (xem ghi chú trong tasks/TASK-010-auth-api.md).
    TODO: thêm kiểm tra liên kết trước khi mở rộng role nào được gọi /chat.

    KHÔNG thay thế `require_internal_secret` (rào cản khác: chặn request lạ
    hoàn toàn, không biết ai đang gọi) - hàm này giải quyết vấn đề KHÁC: xác
    định ĐÚNG patient_id của người đang gọi, kể cả khi họ là 1 người dùng
    hợp lệ của app nhưng tự gõ patient_id của người khác vào request (lỗ
    hổng thật khi có nhiều người dùng thật, không còn là rủi ro lý thuyết -
    xem chatbot-rag-design.md mục 10 #10)."""
    if current_user.role == "patient" and current_user.patient_id:
        return current_user.patient_id
    return request.patient_id
