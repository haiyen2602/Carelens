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

from typing import Protocol

from fastapi import Header, HTTPException, status

from backend.config import get_settings

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


async def require_internal_secret(
    x_internal_secret: str | None = Header(default=None, alias=INTERNAL_SECRET_HEADER),
) -> None:
    """FastAPI dependency - chan request thieu hoac sai header
    `X-Internal-Secret` (gia tri dung dat qua env var `INTERNAL_AUTH_SECRET`,
    KHONG hardcode gia tri that trong code - xem src/config.py). FAIL-CLOSED
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


def get_current_patient_id(request: _HasPatientId) -> str:
    """Vòng 2 (chatbot-rag-design.md mục 14, mục 10 #10) - 1 CHỖ NỐI DUY NHẤT
    để đọc patient_id của người đang gọi. Mọi endpoint/node PHẢI gọi qua hàm
    này - KHÔNG đọc `request.patient_id` thẳng ở bất kỳ đâu khác (kể cả
    trong chính chat_routes.py).

    Implementation HIỆN TẠI: đọc từ body như cũ (giữ nguyên hành vi, không
    đổi behavior ngay - auth-api thật chưa xây trong repo này). Khi app có
    endpoint đăng nhập thật (JWT/session), CHỈ sửa BÊN TRONG hàm này (đọc
    patient_id từ token đã xác thực thay vì tin body), KHÔNG sửa lại từng
    chỗ gọi - đúng pattern đã dùng cho `escalate_fn` (tham số/hàm optional,
    đổi implementation không đổi logic nơi gọi).

    KHÔNG thay thế `require_internal_secret` (rào cản khác: chặn request lạ
    hoàn toàn, không biết ai đang gọi) - hàm này giải quyết vấn đề KHÁC: xác
    định ĐÚNG patient_id của người đang gọi, kể cả khi họ là 1 người dùng
    hợp lệ của app nhưng tự gõ patient_id của người khác vào request (lỗ
    hổng thật khi có nhiều người dùng thật, không còn là rủi ro lý thuyết -
    xem chatbot-rag-design.md mục 10 #10)."""
    return request.patient_id
