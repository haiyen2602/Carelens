"""Cleanup: xoa push_subscription tao TRUOC khi doi domain FE production.

Revision ID: 0046
Revises: 0045
Create Date: 2026-08-25

BOI CANH: domain FE production doi tu vmec-04fe-production.up.railway.app
sang c3-app-067.up.railway.app (xac nhan qua `railway domain`, cap nhat luc
2026-08-24T15:10:46+00:00 - domain cu gio tra 404, khong con song). Web Push
subscription + Service Worker bi khoa cung vao DUNG origin luc dang ky (gioi
han cua trinh duyet, khong co co che migrate cross-origin) - moi dong
push_subscription tao TRUOC moc doi domain chac chan gan voi Service Worker
cua domain CU, nen:
  1. Notification van gui thanh cong (endpoint FCM/WNS khong quan tam domain
     app), nhung bam vao se mo domain cu -> 404 chet.
  2. Benh nhan bam "Bat thong bao" lai o domain moi se co THEM 1 dong moi
     (UPSERT theo endpoint - endpoint moi khac endpoint cu, khong ghi de),
     nen tu lan nhac tiep theo se nhan 2 thong bao trung: 1 dung, 1 dan toi
     404. Xem backend/services/push.py::send_push_to_patient (lay TOAN BO
     dong theo patient_id, khong loc domain vi bang khong luu domain).

Khong co cach nao "sua" nhung dong nay tro lai domain moi (endpoint la danh
tinh thiet bi do trinh duyet cap, khong sua duoc) - xoa la lua chon duy nhat
hop ly. Cat moc THEO GIO CHINH XAC domain doi (khong phai dau ngay) de khong
xoa nham dong nao tao dung trong ngay 2026-08-24 nhung da o domain moi.

CHI xoa 1 LAN duy nhat (Alembic danh dau qua alembic_version, khong chay lai
o cac lan deploy sau) - nhung dong push_subscription tao SAU moc nay (benh
nhan bam dang ky lai o domain moi) hoan toan an toan, khong bi dung toi.

KHONG THE hoan tac that su (downgrade() khong phuc hoi lai duoc du lieu da
xoa) - xem downgrade() ben duoi.
"""

from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None

# Moc doi domain FE production (UTC) - xem docstring o tren.
_CUTOFF = "2026-08-24T15:10:46+00:00"


def upgrade() -> None:
    op.execute(
        f"DELETE FROM push_subscription WHERE created_at < '{_CUTOFF}'"
    )


def downgrade() -> None:
    # Data cleanup KHONG THE hoan tac - da xoa la mat that (khong luu ban
    # sao). Co y de trong thay vi gia vo "downgrade" ma khong lam gi that.
    pass
