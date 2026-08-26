"""Cong diem thuong theo TUNG LIEU thay vi 1 lan/ngay (SUA 2026-08-26).

Truoc: +20 diem ghi 1 lan duy nhat khi CA NGAY da uong du -> benh nhan uong
lieu sang khong thay gi, phai doi het ngay; uong thieu 1 lieu thi mat sach
20 diem. Nhom truong yeu cau cong ngay sau moi lieu.

Sau: van toi da 20 diem/ngay (giu nguyen kinh te trong reward/reward.md -
~21.600 diem/nam), nhung chia theo ty le so lieu da uong. Vd 3 lieu/ngay thi
uong lieu 1 duoc 7, lieu 2 them 6, lieu 3 them 7 - tong dung 20. Xem
reward_ledger.award_dose_on_time().

De ghi duoc NHIEU dong DOSE_ON_TIME trong cung 1 ngay, khoa duy nhat
(patient_id, event_type, occurred_on) phai thoi ap dung cho DOSE_ON_TIME.
KHONG bo han khoa do: DAILY_SURVEY / WEEKLY_STREAK / MONTHLY_STREAK VAN
phai la 1-lan-moi-ngay, va do van la thu chan cong trung o tang DB. Nen thay
bang INDEX DUY NHAT MOT PHAN (partial unique index) loai tru DOSE_ON_TIME.

DOSE_ON_TIME khong con duoc DB chan cong trung nua - viec do chuyen sang
tang service: award_dose_on_time() tinh "dang le duoc bao nhieu" tru "da
cong bao nhieu hom nay" roi chi ghi phan chenh, goi lai nhieu lan thi phan
chenh = 0 nen khong ghi gi. Xem docstring cua ham do.

Revision ID: 0050
Revises: 0049
Create Date: 2026-08-26

"""

import sqlalchemy as sa
from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None

_TEN_CU = "uq_patient_reward_event_daily"
_TEN_MOI = "uq_patient_reward_event_daily_non_dose"


def upgrade() -> None:
    op.drop_constraint(_TEN_CU, "patient_reward_event", type_="unique")
    # Postgres coi moi NULL la khac nhau, nen dong REDEEM (occurred_on NULL)
    # van khong bao gio dung nhau o day - giong het hanh vi cua khoa cu.
    op.create_index(
        _TEN_MOI,
        "patient_reward_event",
        ["patient_id", "event_type", "occurred_on"],
        unique=True,
        postgresql_where=sa.text("event_type <> 'DOSE_ON_TIME'"),
    )


def downgrade() -> None:
    # Quay lai khoa cu CHI an toan khi moi ngay chi con 1 dong DOSE_ON_TIME.
    # Gop cac dong cung (patient_id, ngay) lai lam 1 truoc, neu khong
    # create_constraint se that bai tren du lieu da cong theo tung lieu.
    op.execute(
        """
        WITH gop AS (
            SELECT patient_id, occurred_on,
                   MIN(id) AS giu_lai,
                   SUM(points_delta) AS tong
            FROM patient_reward_event
            WHERE event_type = 'DOSE_ON_TIME'
            GROUP BY patient_id, occurred_on
        )
        UPDATE patient_reward_event e
        SET points_delta = gop.tong
        FROM gop
        WHERE e.id = gop.giu_lai
        """
    )
    op.execute(
        """
        DELETE FROM patient_reward_event e
        WHERE e.event_type = 'DOSE_ON_TIME'
          AND e.id <> (
              SELECT MIN(id) FROM patient_reward_event x
              WHERE x.event_type = 'DOSE_ON_TIME'
                AND x.patient_id = e.patient_id
                AND x.occurred_on IS NOT DISTINCT FROM e.occurred_on
          )
        """
    )
    op.drop_index(_TEN_MOI, table_name="patient_reward_event")
    op.create_unique_constraint(
        _TEN_CU, "patient_reward_event", ["patient_id", "event_type", "occurred_on"]
    )
