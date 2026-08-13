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
from typing import Protocol

from fastapi import Depends, Header, HTTPException, status

from sqlalchemy.orm import Session
from backend.config import get_settings
from backend.db.base import get_db
from backend.db.models import Account
from backend.services.auth import TokenError, decode_token, token_revoked_by_password_change

INTERNAL_SECRET_HEADER = "X-Internal-Secret"


class _HasPatientId(Protocol):
    """Vong 3 (muc 7.1) - noi long type hint cua get_current_patient_id()
    tu ConversationChatRequest CU THE sang BAT KY schema nao co truong
    patient_id (structural typing) - de cac endpoint MOI (vd chat history
    muc 7.1) tai su dung DUNG 1 cho noi nay, khong tao 1 ham doc patient_id
    song song rieng (dung y "1 CHO NOI DUY NHAT" cua chinh ham nay). KHONG
    doi hanh vi (van chi doc .patient_id), chi noi rong kieu du lieu chap
    nhan duoc."""

    patient_id: str


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
    db: Session = Depends(get_db),
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

    account = db.query(Account).filter(Account.id == sub).first()
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tai khoan khong ton tai",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if account.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản đã bị khoá",
        )
    if token_revoked_by_password_change(payload, account.password_changed_at):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Thieu/het han JWT",
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
    lien quan deu nho dung chinh sach da ghi trong tai lieu.

    KHONG con duoc dung cho /api/v1/chat va /api/v1/chat/history* (TASK-010,
    auth-api that thay the) - giu lai ham nay cho cac route noi bo khac neu
    can (vd escalation ack cu, xem escalation_routes.py), xoa han khi khong
    con noi nao goi toi."""
    settings = get_settings()
    if x_internal_secret is None or x_internal_secret != settings.internal_auth_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-Internal-Secret header (temp auth gate - chatbot-rag-design.md mục 10 #10)",
        )


def get_current_patient_id(request: _HasPatientId, current_user: CurrentUser) -> str:
    """Vòng 2 (chatbot-rag-design.md mục 14, mục 10 #10) - 1 CHỖ NỐI DUY NHẤT
    để đọc patient_id của người đang gọi. Mọi endpoint/node PHẢI gọi qua hàm
    này - KHÔNG đọc `request.patient_id` thẳng ở bất kỳ đâu khác (kể cả
    trong chính chat_routes.py).

    TASK-010 (auth-api thật đã xây): đổi implementation BÊN TRONG hàm này
    như ghi chú cũ đã dự tính — nhưng KHÔNG thể giữ nguyên chữ ký 1 tham số
    như dự tính ban đầu, vì để đọc JWT cần danh tính đã xác thực
    (`CurrentUser`), thứ mà `ConversationChatRequest` (chỉ là body) không
    mang theo. Vì vậy MỌI chỗ gọi (kể cả 2 endpoint chat/history* thêm ở
    vòng 3) đều phải kèm `Depends(get_current_user)` — đây là điểm lệch nhỏ
    so với ghi chú gốc, chấp nhận được vì vẫn chỉ có 1 hàm duy nhất chứa
    logic, không có đường đọc patient_id song song nào khác.

    `request` nới type hint sang `_HasPatientId` (Protocol, vòng 3 mục 7.1)
    thay vì cụ thể `ConversationChatRequest` - để `ChatHistoryRequest` (khác
    schema, cùng có field `patient_id`) tái dùng được đúng hàm này, không
    tạo đường đọc patient_id song song cho chat history.

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


def verify_patient_access(
    patient_id: str,
    current_user: CurrentUser,
) -> bool:
    """Kiểm tra xem current_user có quyền truy cập dữ liệu của patient_id hay không (ReBAC).

    - admin: Được truy cập mọi bệnh nhân.
    - patient: Chỉ truy cập bệnh nhân của chính mình (current_user.patient_id).
    - doctor / caregiver: Được truy cập dữ liệu bệnh nhân trong danh sách phụ trách / liên kết.
    """
    if current_user.role == "admin":
        return True
    if current_user.role == "patient":
        return current_user.patient_id == patient_id
    if current_user.role in ("doctor", "caregiver"):
        # Trong tương lai có thể query DB check link, hiện tại cho phép nếu là doctor/caregiver
        return True
    return False

