"""1 CHO NOI DUY NHAT de bien 1 chuoi email thanh "danh tinh" dung de tra cuu
tai khoan (`account.email`).

VI SAO CAN (bug that, phat hien 2026-08-17): `account.email` co UNIQUE nhung
Postgres so sanh chuoi CO PHAN BIET chu hoa/thuong, con moi cach nguoi ta go
email lai khong. Hau qua: cung 1 nguoi thanh 2 tai khoan rieng biet trong he
thong -

  - dang ky thu cong bang "MCK@gmail.com" -> account A (BN00002);
  - sau do bam "Login with Google", Google tra ve email da chuan hoa
    "mck@gmail.com" -> oauth_google() tra cuu bang `Account.email == body.email`
    KHONG thay A -> tao account B moi, patient_id moi, ho so benh nhan moi.

Tu do 2 ban ghi cung 1 nguoi ton tai song song: don thuoc/lich uong thuoc/
canh bao nam o A, con dang nhap Google lai vao B (trong tron). Tren production
2026-08-17 co 3 tai khoan dang cho san bug nay: MCK@gmail.com (BN00002),
TLINH@gmail.com (BN00003), testerNoPro@gmail.com (BN00034).

PHAM VI chuan hoa CO Y HAN CHE - chi `strip()` + `lower()`:
  - RFC 5321 noi domain KHONG phan biet chu hoa/thuong; local-part thi ve ly
    thuyet co, nhung khong nha cung cap email thuc te nao (Google, Microsoft,
    Yahoo) phan biet - nen ha ca chuoi la an toan va dung voi thuc te.
  - KHONG bo dau "." va KHONG cat duoi "+tag" kieu Gmail. Do la quy uoc RIENG
    cua Gmail, ap dung chung se lam 2 email KHAC NHAU o nha cung cap khac va
    trong du lieu san co (vd "a.b@congty.vn") bi gop thanh 1 tai khoan - hop
    nhat SAI tai khoan la loi khong the sua nguoc, nang hon bug dang chua.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import ColumnElement, func
from sqlalchemy.orm import Session

if TYPE_CHECKING:  # pragma: no cover
    from backend.db.models import Account


def normalize_email(raw: Any) -> Any:
    """Dang chuan de LUU va de SO SANH. Goi o BIEN (pydantic schema) de moi
    duong vao - register / login / oauth google / admin tao tai khoan - deu
    thong nhat, khong phai nho goi o tung route.

    Gia tri KHONG phai chuoi thi tra ve nguyen ven: ham nay duoc dung lam
    pydantic BeforeValidator, va `{"email": 123}` phai roi vao thong bao loi
    422 binh thuong cua EmailStr chu khong phai AttributeError -> 500."""
    if not isinstance(raw, str):
        return raw
    return raw.strip().lower()


# `Account` duoc import BEN TRONG 2 ham duoi (khong o dau file) co y:
# backend/models/schemas.py can `normalize_email` cho pydantic validator, va
# `backend.db.models` keo theo backend/db/base.py -> create_engine() ngay luc
# import (can DATABASE_URL that). Import muon giu cho file schemas van import
# duoc trong moi truong khong co DB (vd sinh openapi, unit test thuan).
def account_email_key() -> ColumnElement[str]:
    """Bieu thuc SQL ung voi `normalize_email` phia Python.

    PHAI trung khop TUNG CHU voi bieu thuc cua unique index
    `ux_account_email_normalized` (migration 0026) - neu lech, Postgres se
    khong dung duoc index va moi lan tra cuu email thanh 1 lan quet ca bang."""
    from backend.db.models import Account

    return func.lower(func.btrim(Account.email))


def find_account_by_email(db: Session, email: str) -> Account | None:
    """Tra cuu tai khoan theo email KHONG phan biet chu hoa/thuong + bo khoang
    trang 2 dau. Moi cho can "tim tai khoan tu email" PHAI goi ham nay, khong
    viet `Account.email == email` truc tiep.

    Van tra cuu qua bieu thuc (thay vi tin rang moi dong trong DB da chuan) de
    con dung ngay ca trong lat rolling-deploy, khi container CU (chua co ban sua
    nay) van con dang ghi email chua chuan hoa vao bang."""
    from backend.db.models import Account

    return db.query(Account).filter(account_email_key() == normalize_email(email)).first()
