"""Schema cho luong yeu cau bo sung thuoc (FB-14).

Tach file rieng thay vi nhet vao schemas.py: file do da hon 800 dong va gom
moi domain: auth, account, prescription, dose... Cung ly do admin_drug_schemas.py
duoc tach ra o TASK-019.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

DrugRequestStatus = Literal["PENDING", "APPROVED", "REJECTED"]


class DrugRequestCreate(BaseModel):
    """POST /api/v1/drug-requests - bac si xin bo sung mot thuoc.

    `dang_thuoc`/`duong_dung` BAT BUOC du bac si phai go tay: `dang_thuoc` la
    dau vao cua photo_verification/dosage_form.py, quyet dinh lieu thuoc do co
    xac minh duoc bang anh hay khong. Cho bo trong la de lot mot lop thuoc
    khong bao gio xac minh duoc - dung thu FB-14 muon dep.

    KHONG co `doctor_id` trong body: lay tu JWT o tang route.
    """

    ten_thuoc: str = Field(..., min_length=1, max_length=300)
    dang_thuoc: str = Field(..., min_length=1, max_length=200)
    duong_dung: str = Field(..., min_length=1, max_length=100)
    ham_luong: str | None = Field(default=None, max_length=100)
    tong_so_luong: str | None = Field(default=None, max_length=100)
    ly_do: str | None = Field(default=None, max_length=1000)


class DrugRequestReject(BaseModel):
    """POST /api/v1/admin/drug-requests/{id}/reject.

    `note` bat buoc va min_length=1 - bac si can biet vi sao bi tu choi de con
    sua lai, mot yeu cau bi tu choi khong ly do la mot nguoi bi ket.
    """

    note: str = Field(..., min_length=1, max_length=1000)


class DrugRequestApprove(BaseModel):
    """POST /api/v1/admin/drug-requests/{id}/approve - `note` tuy chon."""

    note: str | None = Field(default=None, max_length=1000)


class DrugRequestOut(BaseModel):
    id: str
    requested_by_doctor_id: str
    ten_thuoc: str
    dang_thuoc: str
    duong_dung: str
    ham_luong: str | None = None
    tong_so_luong: str | None = None
    ly_do: str | None = None
    status: DrugRequestStatus
    reviewed_by_account_id: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    # Chinh la gia tri bac si gui len trong PrescriptionItemIn.drug_id sau khi
    # duoc duyet. None khi chua duyet.
    approved_drug_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DrugRequestListResponse(BaseModel):
    items: list[DrugRequestOut]
