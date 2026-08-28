"""Luu % giu lai cua tung lieu bi tru diem, de bo LAM TRON THEO TUNG LIEU.

Bug duoc phat hien khi review 0061: khoan tru tinh bang
round(diem_cua_lieu * (100-pct)/100), ma diem MOI LIEU la so nho (tran 20
diem/ngay chia cho n lieu). Voi n>=4 thi moi lieu chi con 5 diem tro xuong,
nen muc -10% ra round(0.5)=0 - Python dung banker's rounding nen 0.5 lam
tron XUONG. Do duoc: tu 4 lieu/ngay tro len, muc -10% tru dung 0 diem, tuc
la ca mot bac chinh sach khong ton tai. Sai ca chieu nguoc lai: 7 lieu/ngay
o muc -50% thanh -65% vi sai so cong don theo huong kia.

Cach sua: KHONG lam tron tung lieu nua. Tinh tong phat CHINH XAC cua ca
ngay (chua lam tron), lam tron MOT LAN, roi chi ghi phan chenh so voi da
tru - dung cung khuon voi award_dose_on_time() da lam cho diem cong. Do
duoc sau khi sua: dung 90%/70%/50% cho moi so lieu tu 1 den 8.

De tinh lai duoc tong do o moi lan goi, phai biet TUNG lieu bi phat theo
muc nao - so diem da tru khong suy nguoc ra duoc vi phan le da mat khi lam
tron. Vi vay them cot nay.

NULLABLE va KHONG backfill: cac dong ghi truoc migration nay (chi co o may
dev, tinh nang chua len production) khong the suy ra pct that. Ham tinh moi
CHI dem cac dong co method_pct - dong cu duoc giu nguyen trong so nhu su
that lich su, khong sua, khong xoa, va khong tham gia phep tinh moi.

Revision ID: 0062
Revises: 0061
Create Date: 2026-08-28

"""

import sqlalchemy as sa
from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("patient_reward_event", sa.Column("method_pct", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("patient_reward_event", "method_pct")
