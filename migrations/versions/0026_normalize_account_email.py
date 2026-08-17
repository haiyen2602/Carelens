"""1 email = 1 tai khoan, khong phan biet chu hoa/thuong.

VI SAO (bug that, phat hien 2026-08-17): `account.email` co UNIQUE nhung
Postgres so sanh chuoi CO PHAN BIET chu hoa/thuong, con nguoi dung va Google
thi khong nhat quan ve cach viet. Ket qua: cung 1 nguoi thanh 2 tai khoan.

  - dang ky thu cong "MCK@gmail.com" -> account A (patient_id BN00002);
  - bam "Login with Google", Google tra ve "mck@gmail.com" -> oauth_google()
    tra cuu khong thay A -> tao account B, patient_id moi, ho so trong.

Don thuoc / lich uong thuoc / canh bao nam o A, con nguoi dung dang nhap
Google lai vao B. Xem backend/services/email_identity.py.

Migration nay lam 2 viec:

1. Chuan hoa cac dong DA CO: `email = lower(btrim(email))`. Tren production
   2026-08-17 co dung 3 dong bi anh huong (MCK@gmail.com / TLINH@gmail.com /
   testerNoPro@gmail.com), va da kiem tra: KHONG co nhom nao trung nhau sau
   khi lower() - nen buoc nay khong the va unique constraint san co va khong
   phai hop nhat (merge) tai khoan nao. Neu tuong lai chay tren 1 DB CO trung,
   buoc 2 se that bai va migration dung lai (transaction roll back) thay vi
   im lang lam mat du lieu - do la hanh vi mong muon: hop nhat tai khoan la
   quyet dinh cua con nguoi, khong phai cua migration.

2. Them unique index tren BIEU THUC `lower(btrim(email))`. Chuan hoa o tang
   pydantic (NormalizedEmail trong backend/models/schemas.py) chi chan duong
   vao qua API; index nay la rao CUOI o tang DB - chan ca race condition (2
   request dang ky cung luc) va ca cac duong ghi khac (script, sua tay).

   Bieu thuc PHAI trung TUNG CHU voi email_identity.account_email_key()
   (`func.lower(func.btrim(Account.email))`) - neu lech, Postgres se khong
   dung index cho cac truy van tra cuu email va moi lan dang nhap thanh 1 lan
   quet ca bang `account`.

   UNIQUE cu tren cot `email` (tu migration 0012) duoc GIU LAI: no van dung
   (email chuan hoa roi thi 2 rang buoc tuong duong), va giu lai thi
   downgrade() khong phai dung lai mot rang buoc da bi xoa.

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-17
"""

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

INDEX_NAME = "ux_account_email_normalized"


def upgrade() -> None:
    # Chi UPDATE dong that su can (WHERE email <> lower(btrim(email))) - tranh
    # ghi lai toan bo bang va tranh sinh WAL/trigger vo ich.
    op.execute(
        """
        UPDATE account
           SET email = lower(btrim(email))
         WHERE email <> lower(btrim(email))
        """
    )

    op.execute(f"CREATE UNIQUE INDEX {INDEX_NAME} ON account (lower(btrim(email)))")


def downgrade() -> None:
    # Chi bo index. KHONG the (va khong nen) hoan nguyen buoc chuan hoa email:
    # dang chu hoa goc khong duoc luu o dau, va viec lay lai no khong co gia
    # tri nao - "MCK@gmail.com" va "mck@gmail.com" la cung 1 hom thu.
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
