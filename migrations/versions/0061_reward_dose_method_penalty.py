"""Tru diem theo CACH xac nhan uong thuoc (yeu cau nhom truong 2026-08-28).

Anh chup khop don thuoc giu tron 100% diem; cac duong tu khai bi tru bot:
-10% (nguoi than duyet sau 3 lan anh sai), -30% (khong co nguoi than de
duyet), -50% (tu bao da uong, khong co anh). Xem
reward_ledger::apply_confirmation_method_penalty().

Khoan tru duoc ghi thanh DONG RIENG voi event_type=DOSE_METHOD_PENALTY thay
vi giam so diem cua dong DOSE_ON_TIME. Bat buoc phai vay: award_dose_on_time()
tinh MUC TIEU tich luy ca ngay (round(20*k/n)) roi chi ghi phan chenh, nen
neu giam ngay tai do thi lieu tiep theo trong ngay se tu dong bu lai phan da
tru - khoan phat bien mat.

CHONG CONG TRUNG - khac ca 2 loai da co truoc do:
  - DAILY_SURVEY/WEEKLY_STREAK/MONTHLY_STREAK: 1 dong/ngay, chan bang index
    duy nhat mot phan (patient_id, event_type, occurred_on) tu migration 0050.
  - DOSE_ON_TIME: nhieu dong/ngay, khong chan o DB, chan o tang service bang
    phep tru "dang le duoc bao nhieu" - "da cong bao nhieu".
  - DOSE_METHOD_PENALTY (moi): cung nhieu dong/ngay (moi lieu bi phat 1 dong)
    nen KHONG dung duoc khoa theo ngay, nhung cung KHONG tu chan duoc o tang
    service nhu DOSE_ON_TIME vi day khong phai phep tinh tich luy. Thay bang
    index duy nhat theo (patient_id, event_type, item_id) voi
    item_id = dose_event.id - moi lieu chi bi phat dung 1 lan, du ham co bi
    goi lai (retry job xac minh anh, nguoi than bam duyet 2 lan...).

Vi index 0050 ap dung cho MOI event_type tru DOSE_ON_TIME, phai loai tru
them DOSE_METHOD_PENALTY khoi no - neu khong, benh nhan bi phat 2 lieu trong
cung 1 ngay se bi IntegrityError o lieu thu hai.

Revision ID: 0061
Revises: 0060
Create Date: 2026-08-28

"""

import sqlalchemy as sa
from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None

_INDEX_NGAY = "uq_patient_reward_event_daily_non_dose"
_INDEX_PHAT = "uq_patient_reward_event_method_penalty"
_LOC_CU = "event_type <> 'DOSE_ON_TIME'"
_LOC_MOI = "event_type NOT IN ('DOSE_ON_TIME', 'DOSE_METHOD_PENALTY')"


def upgrade() -> None:
    op.drop_index(_INDEX_NGAY, table_name="patient_reward_event")
    op.create_index(
        _INDEX_NGAY,
        "patient_reward_event",
        ["patient_id", "event_type", "occurred_on"],
        unique=True,
        postgresql_where=sa.text(_LOC_MOI),
    )
    op.create_index(
        _INDEX_PHAT,
        "patient_reward_event",
        ["patient_id", "event_type", "item_id"],
        unique=True,
        postgresql_where=sa.text("event_type = 'DOSE_METHOD_PENALTY'"),
    )


def downgrade() -> None:
    # Quay ve trang thai 0050. CHI an toan khi khong con dong
    # DOSE_METHOD_PENALTY nao trong bang, hoac moi (benh nhan, ngay) chi co
    # dung 1 dong - neu khong, viec tao lai index cu se that bai.
    op.drop_index(_INDEX_PHAT, table_name="patient_reward_event")
    op.drop_index(_INDEX_NGAY, table_name="patient_reward_event")
    op.create_index(
        _INDEX_NGAY,
        "patient_reward_event",
        ["patient_id", "event_type", "occurred_on"],
        unique=True,
        postgresql_where=sa.text(_LOC_CU),
    )
