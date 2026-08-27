"""Tuy chon thong bao cua benh nhan - doc/ghi (THEM 2026-08-27).

Tach rieng khoi dose_push_reminder.py de vong quet chi lo viec "toi gio chua"
con module nay lo "benh nhan co muon nghe khong" - hai cau hoi khac nhau, va
tach ra thi test duoc rieng tung ben.

MAC DINH LA BAT: benh nhan chua bao gio vao Cai dat thi khong co dong nao
trong bang, va phai duoc nhac binh thuong. Neu mac dinh la tat, moi benh nhan
moi se im lang khong duoc nhac gi - dung loai loi ma khong ai bao cao vi
khong co gi de thay.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import CaregiverLink, PatientNotificationPref


def dang_theo_doi_ai(db: Session, account_id: str) -> bool:
    """Tai khoan nay co dang theo doi benh nhan nao khong (= co phai nguoi
    than khong).

    SUY TU caregiver_link, KHONG doc Account.role: mot nguoi vua co the la
    benh nhan cua chinh minh, vua theo doi bo/me/vo/chong. `role` chi giu
    duoc MOT gia tri nen dung no de quyet dinh se cat mat mot nua vai tro -
    dung loi da lam cong tac o man hinh Cai dat bi khoa.

    Chi tinh lien ket `accepted`: dong "pending" la loi moi chua duoc dong y.
    """
    return db.execute(
        select(CaregiverLink.id).where(
            CaregiverLink.caregiver_account_id == account_id,
            CaregiverLink.status == "accepted",
        ).limit(1)
    ).scalars().first() is not None


class TuyChonThongBao:
    """Ban doc duoc cua tuy chon - dung ca khi benh nhan chua co dong nao.

    Dung class nho thay vi tra thang model: nguoi goi khong phan biet duoc
    "dong that trong DB" voi "mac dinh dung tam", nen khong lo vo tinh sua
    thuoc tinh roi tuong da luu."""

    __slots__ = ("dose_reminder_enabled", "web_push_enabled")

    def __init__(self, *, dose_reminder_enabled: bool = True, web_push_enabled: bool = True):
        self.dose_reminder_enabled = dose_reminder_enabled
        self.web_push_enabled = web_push_enabled


def lay_tuy_chon(db: Session, patient_id: str) -> TuyChonThongBao:
    """Chua co dong nao = bat het (xem docstring module)."""
    row = db.execute(
        select(PatientNotificationPref).where(PatientNotificationPref.patient_id == patient_id)
    ).scalars().first()
    if row is None:
        return TuyChonThongBao()
    return TuyChonThongBao(
        dose_reminder_enabled=bool(row.dose_reminder_enabled),
        web_push_enabled=bool(row.web_push_enabled),
    )


def dat_tuy_chon(
    db: Session,
    patient_id: str,
    *,
    dose_reminder_enabled: bool | None = None,
    web_push_enabled: bool | None = None,
) -> TuyChonThongBao:
    """UPSERT, chi doi truong duoc truyen (None = giu nguyen). KHONG commit.

    Nhan tung truong rieng le thay vi ca cum: man hinh Cai dat gat 1 cong tac
    tai 1 thoi diem, gui ca cum se ghi de nham gia tri cua cong tac kia neu
    2 tab dang mo cung luc."""
    row = db.execute(
        select(PatientNotificationPref).where(PatientNotificationPref.patient_id == patient_id)
    ).scalars().first()
    if row is None:
        row = PatientNotificationPref(patient_id=patient_id)
        db.add(row)

    if dose_reminder_enabled is not None:
        row.dose_reminder_enabled = dose_reminder_enabled
    if web_push_enabled is not None:
        row.web_push_enabled = web_push_enabled

    db.flush()
    return TuyChonThongBao(
        dose_reminder_enabled=bool(row.dose_reminder_enabled),
        web_push_enabled=bool(row.web_push_enabled),
    )
