"""API diem thuong & Rank cho benh nhan (THEM 2026-08-25).

Toan bo endpoint o day chi phuc vu CHINH benh nhan dang dang nhap - lay
patient_id tu JWT, khong nhan tu body/query. Nguoi than/bac si khong xem
duoc so diem cua benh nhan qua nhung route nay (chua co yeu cau nghiep vu
do, va diem thuong la thong tin ca nhan).

Danh muc qua nam o backend/services/reward_catalog.py (hang so, khong phai
bang DB) - xem ghi chu trong file do."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, get_current_user
from backend.db.base import get_db
from backend.models.reward_schemas import (
    DailyCheckinRequest,
    DailyCheckinResponse,
    RedeemRequest,
    RedeemResponse,
    RewardCatalogItemOut,
    RewardHistoryEntry,
    RewardSummary,
)
from backend.services import reward_ledger
from backend.services.reward_catalog import POINTS_DAILY_SURVEY

reward_router = APIRouter()

# Text co dinh theo yeu cau nghiep vu (reward/reward.md) - qua duoc trao tay
# tai co so y te, he thong khong giao hang.
#
# KHONG mo dau bang "Doi qua thanh cong!" nua: sheet ket qua o frontend
# (patient/rewards/page.tsx) DA co dong tieu de do roi, lap lai thanh 2 lan
# trong cung 1 khung. HTTP 200 + cac truong item_name/sp_spent trong response
# da du bao hieu thanh cong cho ben goi API.
THONG_BAO_DOI_QUA = (
    "Hãy đến cơ sở y tế Capymec gần nhất để nhận phần quà của bạn. "
    "Nhớ mang theo điện thoại và mã số bệnh nhân để nhân viên tra cứu nhanh nhé!"
)


def _patient_id(current_user: CurrentUser) -> str:
    if current_user.role != "patient" or not current_user.patient_id:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Chỉ bệnh nhân mới xem được điểm thưởng của chính mình",
        )
    return current_user.patient_id


@reward_router.get("/rewards/me", response_model=RewardSummary)
def get_my_rewards(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> RewardSummary:
    return RewardSummary(**reward_ledger.get_summary(db, _patient_id(current_user)))


@reward_router.get("/rewards/catalog", response_model=list[RewardCatalogItemOut])
def get_reward_catalog(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[RewardCatalogItemOut]:
    items = reward_ledger.list_catalog_for_patient(db, _patient_id(current_user))
    return [RewardCatalogItemOut(**item) for item in items]


@reward_router.get("/rewards/history", response_model=list[RewardHistoryEntry])
def get_reward_history(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[RewardHistoryEntry]:
    rows = reward_ledger.list_history(db, _patient_id(current_user))
    return [RewardHistoryEntry(**row) for row in rows]


@reward_router.post("/rewards/redeem", response_model=RedeemResponse)
def redeem_reward(
    body: RedeemRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> RedeemResponse:
    patient_id = _patient_id(current_user)
    try:
        ket_qua = reward_ledger.redeem_item(db, patient_id, body.item_id)
    except reward_ledger.RewardError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.http_status, detail=exc.message) from exc
    db.commit()
    return RedeemResponse(**ket_qua, message=THONG_BAO_DOI_QUA)


@reward_router.post("/rewards/daily-checkin", response_model=DailyCheckinResponse)
def daily_checkin(
    body: DailyCheckinRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> DailyCheckinResponse:
    """Benh nhan tra loi khao sat "hom nay ban cam thay the nao".

    `felt_ok` hien chi duoc dung de quyet dinh CO thuong hay khong (luon co)
    - luong dieu huong sang Capy AI khi benh nhan thay khong on van do
    frontend lo, khong di qua endpoint nay."""
    patient_id = _patient_id(current_user)
    awarded = reward_ledger.award_daily_survey(db, patient_id)
    db.commit()

    tom_tat = reward_ledger.get_summary(db, patient_id)
    return DailyCheckinResponse(
        awarded=awarded,
        points_awarded=POINTS_DAILY_SURVEY if awarded else 0,
        spendable_points=tom_tat["spendable_points"],
    )
