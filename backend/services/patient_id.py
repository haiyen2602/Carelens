"""Sinh ID benh nhan dang BNxxxxx (BN + 5 chu so, zero-pad) - dung CHUNG cho
CA 2 duong tao benh nhan that (`auth_routes.py::register`, `account_routes.py
::create_account`) de khong bao gio lech nhau (dung tinh than "1 diem duy
nhat" da ap dung cho `trigger_emergency_escalation()`/`get_current_patient_
id()` trong du an nay - xem `backend/services/escalation.py`/`backend/api/
security.py`).

Phat hien 2026-08-14 (yeu cau PM, kem anh chup man hinh that): 2 duong nay
TUNG sinh ID hoan toan khac nhau - duong tu dang ky (`/auth/register`) dung
UUID ngau nhien lam `Patient.id` (khong doc duoc, khac han quy uoc du lieu
cu vd "BN00002" cua benh nhan MCK) - lo ra qua UI hien thi thang UUID o dau
trang benh nhan thay vi ID ngan gon. Duong admin tao tai khoan (`POST /api/
v1/accounts`) cho go `patient_id` TU DO thanh chuoi bat ky VA khong tung tao
dong `Patient` that dang sau - benh nhan "co ID nhung khong co ho so"."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Patient

_PATIENT_ID_RE = re.compile(r"^BN(\d+)$")
_PATIENT_ID_DIGITS = 5


def generate_next_patient_id(db: Session) -> str:
    """Quet TOAN BO `Patient.id` khop dang `BN<so>`, lay so LON NHAT, +1,
    format lai `BN` + it nhat 5 chu so (zero-pad) - khop dung quy uoc du
    lieu cu da co (vd "BN00002"). Vuot 99999 thi TU MO RONG so chu so (vd
    "BN100000"), khong cat/trung lap.

    Khong dung SEQUENCE rieng cua Postgres (`Patient.id` la String tu do,
    khong phai cot so nguyen) - quet + lay max don gian, du nhanh o quy mo
    hien tai (vai nghin ban ghi). Rui ro da biet, CHAP NHAN duoc: 2 request
    tao benh nhan gan nhu CUNG LUC co the doc duoc cung 1 "so lon nhat"
    truoc khi ben nao commit xong, sinh trung ID - tan suat tao tai khoan
    benh nhan (dang ky/admin tao) thap, uu tien don gian (BR-6.2 cung tinh
    than), khong xay co che khoa/sequence rieng khi chua co bang chung that
    can thiet."""
    ids = db.execute(select(Patient.id)).scalars().all()
    max_n = 0
    for pid in ids:
        match = _PATIENT_ID_RE.match(pid or "")
        if match:
            max_n = max(max_n, int(match.group(1)))
    next_n = max_n + 1
    return f"BN{next_n:0{_PATIENT_ID_DIGITS}d}"
