"""Cau hinh TINH cua he thong diem thuong: nguong Rank + danh muc qua tang.

CO Y khong dung bang DB: 10 mon qua nay gan voi thoa thuan that voi Capymec
(goi kham, voucher Capypearl...), khong phai du lieu nguoi dung tao ra. De o
day thi doi gia/them mon la 1 dong code di qua code review - dung muc do
kiem soat can thiet cho thu quy doi ra tien that - va khong ton them 1 bang
+ migration chi de chua 10 dong bat bien.

`patient_reward_event.item_id` tro toi RewardItem.id ben duoi, nen ID la
slug ON DINH: doi ID = lich su doi qua cu tro thanh mo coi. Doi ten hien thi
(`name`) thi thoai mai, vi lich su da chot nhan rieng luc ghi (cot `label`).

So lieu lay tu reward/reward.md phan 3-4.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- Rank tron doi (xet theo lifetime_points, chi tang) ----------------------

BRONZE = "BRONZE"
SILVER = "SILVER"
GOLD = "GOLD"
DIAMOND = "DIAMOND"

RANK_LABELS: dict[str, str] = {
    BRONZE: "Đồng",
    SILVER: "Bạc",
    GOLD: "Vàng",
    DIAMOND: "Kim Cương",
}

# Xep TANG DAN theo diem - compute_rank() duyet nguoc tu cuoi len nen thu tu
# nay la mot phan cua hop dong, khong duoc xao tron.
RANK_THRESHOLDS: list[tuple[str, int]] = [
    (BRONZE, 0),
    (SILVER, 10_000),
    (GOLD, 30_000),
    (DIAMOND, 60_000),
]

_RANK_ORDER: dict[str, int] = {name: i for i, (name, _) in enumerate(RANK_THRESHOLDS)}


# --- Diem thuong moi hanh dong ----------------------------------------------

# TRAN diem uong thuoc cua MOT ngay. Tu 2026-08-26 so nay duoc chia deu
# cho cac lieu trong ngay va cong ngay sau tung lieu (vd 3 lieu -> 7/6/7),
# chu khong con cong 1 cuc khi het ngay - xem reward_ledger
# ::award_dose_on_time(). Tong 1 ngay van khong bao gio vuot so nay.
POINTS_DOSE_ON_TIME = 20
# Tra loi khao sat "hom nay ban cam thay the nao" (1 lan/ngay).
POINTS_DAILY_SURVEY = 10
# Thuong chuoi - CHOT LAI 2026-08-25 theo yeu cau nhom truong: 50/tuan va
# 100/thang (reward/reward.md phan 2 ghi 100/500, da bo).
POINTS_WEEKLY_STREAK = 50
POINTS_MONTHLY_STREAK = 100

EVENT_DOSE_ON_TIME = "DOSE_ON_TIME"
EVENT_DAILY_SURVEY = "DAILY_SURVEY"
EVENT_WEEKLY_STREAK = "WEEKLY_STREAK"
EVENT_MONTHLY_STREAK = "MONTHLY_STREAK"
EVENT_REDEEM = "REDEEM"

EVENT_LABELS: dict[str, str] = {
    EVENT_DOSE_ON_TIME: "Uống thuốc đúng giờ",
    EVENT_DAILY_SURVEY: "Khảo sát sức khoẻ",
    EVENT_WEEKLY_STREAK: "Thưởng chuỗi tuần",
    EVENT_MONTHLY_STREAK: "Thưởng chuỗi tháng",
}


# --- Danh muc qua tang ------------------------------------------------------


@dataclass(frozen=True)
class RewardItem:
    id: str
    name: str
    description: str
    category: str  # "Vật phẩm" | "Voucher" | "Gói dịch vụ"
    rank_required: str
    sp_cost: int
    # Toan bo qua hien tai deu la vat pham/voucher/goi kham dung 1 lan tai
    # Capymec, nen mac dinh moi benh nhan chi doi duoc 1 lan. Doi thanh False
    # neu sau nay co mon cho doi lai nhieu lan.
    one_time: bool = True


CATALOG: list[RewardItem] = [
    RewardItem(
        id="hop-chia-thuoc-thong-minh",
        name="Hộp chia thuốc thông minh",
        description="Hộp chia thuốc 7 ngày, có ngăn sáng/trưa/tối giúp không quên liều.",
        category="Vật phẩm",
        rank_required=BRONZE,
        sp_cost=10_000,
    ),
    RewardItem(
        id="binh-nuoc-giu-nhiet-wellness",
        name="Bình nước giữ nhiệt Wellness",
        description="Bình giữ nhiệt in logo Capymec, nhắc bạn uống đủ nước mỗi ngày.",
        category="Vật phẩm",
        rank_required=BRONZE,
        sp_cost=10_000,
    ),
    RewardItem(
        id="voucher-nha-khoa-tham-my",
        name="Voucher 10% Nha khoa thẩm mỹ",
        description="Giảm 10% chi phí dịch vụ nha khoa thẩm mỹ tại Capymec.",
        category="Voucher",
        rank_required=SILVER,
        sp_cost=25_000,
    ),
    RewardItem(
        id="tu-van-dinh-duong-1-1",
        name="Voucher tư vấn dinh dưỡng 1-1",
        description="Một buổi tư vấn riêng với chuyên gia dinh dưỡng Capymec.",
        category="Voucher",
        rank_required=SILVER,
        sp_cost=30_000,
    ),
    RewardItem(
        id="may-do-huyet-ap-tu-dong",
        name="Máy đo huyết áp tự động",
        description="Máy đo huyết áp bắp tay tự động, dùng tại nhà.",
        category="Vật phẩm",
        rank_required=GOLD,
        sp_cost=50_000,
    ),
    RewardItem(
        id="massage-tri-lieu-2h",
        name="Voucher Massage trị liệu phục hồi 2h",
        description="Liệu trình massage trị liệu 2 giờ tại cơ sở Capymec.",
        category="Voucher",
        rank_required=GOLD,
        sp_cost=60_000,
    ),
    RewardItem(
        id="the-vip-bac-vinmec",
        name="Thẻ VIP Bạc Capymec",
        description="Ưu tiên đặt lịch nhanh, giảm thời gian chờ khám.",
        category="Voucher",
        rank_required=GOLD,
        sp_cost=75_000,
    ),
    RewardItem(
        id="goi-kham-tong-quat-co-ban",
        name="Gói khám sức khỏe tổng quát cơ bản",
        description="Gói khám tổng quát cơ bản trị giá 3.5 triệu đồng.",
        category="Gói dịch vụ",
        rank_required=DIAMOND,
        sp_cost=90_000,
    ),
    RewardItem(
        id="goi-kham-tong-quat-nang-cao",
        name="Gói khám sức khỏe tổng quát nâng cao",
        description="Gói khám tổng quát nâng cao trị giá 7.0 triệu đồng.",
        category="Gói dịch vụ",
        rank_required=DIAMOND,
        sp_cost=140_000,
    ),
    RewardItem(
        id="capypearl-capywonders",
        name="Voucher nghỉ dưỡng Capypearl / Vé VIP CapyWonders",
        description="Một đêm nghỉ dưỡng Capypearl cho gia đình hoặc vé VIP CapyWonders.",
        category="Gói dịch vụ",
        rank_required=DIAMOND,
        sp_cost=180_000,
    ),
]

_CATALOG_BY_ID: dict[str, RewardItem] = {item.id: item for item in CATALOG}


def get_item(item_id: str) -> RewardItem | None:
    return _CATALOG_BY_ID.get(item_id)


def compute_rank(lifetime_points: int) -> str:
    """Rank cao nhat ma `lifetime_points` da voi toi."""
    current = BRONZE
    for name, threshold in RANK_THRESHOLDS:
        if lifetime_points >= threshold:
            current = name
    return current


def next_rank(rank: str) -> tuple[str, int] | None:
    """(ten rank ke tiep, nguong diem cua no) - None neu da o rank cao nhat."""
    index = _RANK_ORDER[rank] + 1
    if index >= len(RANK_THRESHOLDS):
        return None
    return RANK_THRESHOLDS[index]


def rank_meets(current: str, required: str) -> bool:
    """Rank hien tai da du de mo khoa mon qua doi hoi `required` chua."""
    return _RANK_ORDER[current] >= _RANK_ORDER[required]
