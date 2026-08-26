"""Schema cho he thong diem thuong & Rank (reward).

Tach file rieng thay vi nhet vao schemas.py - cung ly do
drug_request_schemas.py/admin_drug_schemas.py da tach: file do da hon 800
dong va gom moi domain.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RankName = Literal["BRONZE", "SILVER", "GOLD", "DIAMOND"]


class RewardSummary(BaseModel):
    """GET /api/v1/rewards/me.

    Tra ve ca ten rank tieng Viet (`rank_label`) de frontend khong tu dich -
    de doi chu hien thi chi phai sua mot noi o backend/services/reward_catalog.py.

    Nhom `next_rank*` la None khi benh nhan da o Rank cao nhat (Kim Cuong)."""

    lifetime_points: int
    spendable_points: int
    rank: RankName
    rank_label: str
    next_rank: RankName | None
    next_rank_label: str | None
    next_rank_at: int | None
    points_to_next_rank: int | None


class RewardCatalogItemOut(BaseModel):
    """Mot mon qua kem trang thai DA TINH SAN cho dung benh nhan dang goi.

    3 co `unlocked`/`affordable`/`already_redeemed` do backend tinh (khong
    bat frontend tu suy tu rank + so diem) - de luat mo khoa chi ton tai o
    mot noi duy nhat."""

    id: str
    name: str
    description: str
    category: str
    sp_cost: int
    rank_required: RankName
    rank_required_label: str
    unlocked: bool
    affordable: bool
    already_redeemed: bool


class RewardHistoryEntry(BaseModel):
    """Mot dong lich su diem. `points_delta` am voi luot doi qua."""

    id: str
    event_type: str
    points_delta: int
    label: str
    occurred_on: str | None
    created_at: str


class RedeemRequest(BaseModel):
    item_id: str = Field(..., min_length=1, max_length=100)


class RedeemResponse(BaseModel):
    item_id: str
    item_name: str
    sp_spent: int
    spendable_points_left: int
    message: str


class DailyCheckinRequest(BaseModel):
    """POST /api/v1/rewards/daily-checkin - tra loi khao sat "hom nay ban cam
    thay the nao" o tab Hom nay.

    `felt_ok=False` KHONG lam mat diem: khao sat thuong cho viec tra loi, dap
    an nao cung duoc thuong nhu nhau - neu khong benh nhan se hoc cach luon
    bam "On" de giu diem, dung thu ma tinh nang nay can biet nhat."""

    felt_ok: bool


class DailyCheckinResponse(BaseModel):
    awarded: bool  # False khi hom nay da tra loi khao sat roi
    points_awarded: int
    spendable_points: int
