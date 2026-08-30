"""Quet lieu thuoc toi gio roi day Web Push - phia SERVER (THEM 2026-08-20).

Vi sao can module nay: nhac gio uong thuoc von tinh hoan toan o client
(frontend/src/components/capy/capy-shell.tsx tu poll rui tu so gio). Cach do
chi chay khi tab con MO - dong tab la mat han, va tren dien thoai thi trinh
duyet tam dung tab nen sau vai phut. De thong bao toi duoc benh nhan ke ca
khi app da dong, noi quyet dinh "toi gio chua" PHAI nam o server.

CO Y GIU CA HAI, khong bo ban client: khi app dang mo, banner + cuoc goi gia
lap la trai nghiem chinh (giau hon han 1 dong thong bao he thong). Push chi
CONG THEM kenh cho luc tab dong. Doi lai, client phai thoi tu ban Notification
he thong khi da dang ky push - neu khong benh nhan nhan 2 thong bao cho 1
lieu (xem ghi chu o capy-shell.tsx).

DUNG `DoseEvent` (legacy), KHONG dung outbox V2 (`NotificationJob` +
advance_dose_occurrences trong backend/services/scheduling/dose_state.py) du
outbox do nhin qua la dung cho hon: da kiem tra 2026-08-20,
advance_dose_occurrences CHUA duoc goi o bat ky dau - do la ha tang thiet ke
san con "ngu", va no gan voi DoseOccurrence chi ton tai khi dose_runtime_mode
la shadow/v2 (production dang shadow nhung local mac dinh legacy). Toan bo
app dang phuc vu tu DoseEvent nen push bam theo dung nguon do. Di tru sang
outbox V2 khi V2 that su len.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import DoseEvent, PushReminderSent
from backend.services.caregiver_escalation import tao_canh_bao_cho_nguoi_than
from backend.services.notification_pref import lay_tuy_chon
from backend.services.push import send_push_to_patient
from backend.services.telegram import gio_dia_phuong, send_telegram_to_patient

logger = logging.getLogger("dose_push_reminder")

# 3 moc leo thang, tinh bang phut ke tu gio hen. PHAI KHOP Y HET ban client
# (MOC_NHAC_LAN_2 / MOC_GOI / HET_HAN_NHAC_PHUT trong frontend/src/components/
# capy/capy-shell.tsx) - 2 ben lech nhau thi benh nhan nhan nhac 2 lan o 2
# thoi diem khac nhau cho cung 1 lieu.
MOC_NHAC_LAN_2 = 15
MOC_GOI = 30

# Qua moc nay thi thoi han nhac: khung xac nhan cua backend chi +-30 phut
# (NUA_CUA_SO, backend/services/scheduling/generator.py) nen qua 60 phut la
# lieu do coi nhu da lo, nhac nua khong con y nghia. Cung ngan luon truong
# hop lieu ton dong tu hom truoc (khong ai doi status thanh MISSED) lam benh
# nhan bi day 1 loat thong bao cu.
HET_HAN_NHAC_PHUT = 60


def tinh_moc(phut_qua: float) -> int | None:
    """Ham THUAN - moc cao nhat ung voi do tre hien tai, None neu ngoai khung.

    Tach rieng khoi phan quet DB de test duoc truc tiep voi so phut gia lap
    (khong can DB/scheduler that) - cung tinh than voi is_reminder_due() cua
    escalation_reminder.py.
    """
    if phut_qua < 0 or phut_qua > HET_HAN_NHAC_PHUT:
        return None
    if phut_qua >= MOC_GOI:
        return MOC_GOI
    if phut_qua >= MOC_NHAC_LAN_2:
        return MOC_NHAC_LAN_2
    return 0


def _ten_thuoc_cua_nhom(nhom: list[DoseEvent]) -> str:
    tens: list[str] = []
    for d in nhom:
        items = d.expected_items or []
        ten = (items[0] or {}).get("ten_thuoc") if items else None
        if ten and ten not in tens:
            tens.append(ten)
    return " và ".join(tens) if tens else "thuốc"


def quet_va_day_nhac(db: Session, *, now: datetime | None = None) -> int:
    """Quet moi lieu PENDING toi gio, day push cho benh nhan. Tra ve so luot
    nhac da xu ly (moi luot = 1 khung gio cua 1 benh nhan).

    Gop theo (patient_id, scheduled_at) chu KHONG theo tung dong DoseEvent:
    2 thuoc cung hen 21:00 la 2 dong rieng nhung chi la 1 lan uong - nhac
    tung dong se thanh 2 thong bao lien tiep (bug that da sua o ban client).
    """
    now = now or datetime.now(UTC)
    som_nhat = now - timedelta(minutes=HET_HAN_NHAC_PHUT)

    rows = db.execute(
        select(DoseEvent).where(
            DoseEvent.status == "PENDING",
            DoseEvent.scheduled_at <= now,
            DoseEvent.scheduled_at >= som_nhat,
        )
    ).scalars().all()
    if not rows:
        return 0

    theo_khung: dict[tuple[str, datetime], list[DoseEvent]] = defaultdict(list)
    for d in rows:
        theo_khung[(d.patient_id, d.scheduled_at)].append(d)

    da_xu_ly = 0
    for (patient_id, slot_at), nhom in theo_khung.items():
        phut_qua = (now - slot_at).total_seconds() / 60
        moc = tinh_moc(phut_qua)
        if moc is None:
            continue

        # Da day moc nay roi thi thoi - ban ghi dung chung cho MOI thiet bi
        # cua benh nhan, khac localStorage o client (rieng tung may).
        da_co = db.execute(
            select(PushReminderSent).where(
                PushReminderSent.patient_id == patient_id,
                PushReminderSent.slot_at == slot_at,
                PushReminderSent.moc == moc,
            )
        ).scalars().first()
        if da_co is not None:
            continue

        ten_thuoc = _ten_thuoc_cua_nhom(nhom)
        if moc == MOC_GOI:
            title = "📞 CapyMedi đang gọi bạn"
            body = f"Vẫn chưa thấy bạn xác nhận uống {ten_thuoc}. Bạn ổn chứ?"
        elif moc == MOC_NHAC_LAN_2:
            title = "CapyMedi"
            body = f"Vẫn chưa thấy bạn xác nhận uống {ten_thuoc}"
        else:
            title = "CapyMedi"
            body = f"Đến giờ uống {ten_thuoc} rồi nhé"

        # TANG 1 - benh nhan co muon duoc nhac khong. Kiem SAU khi da tinh
        # moc chu khong loc tu cau query o tren: van phai ghi
        # PushReminderSent ben duoi de moc nay coi nhu da xu ly, neu khong
        # vong quet moi 60 giay se lam lai het tu dau cho ho.
        tuy_chon = lay_tuy_chon(db, patient_id)

        # TANG 2 - nhac qua duong nao. Tat tang 1 thi khong kenh nao chay,
        # du tung kenh van dang bat: dung thu tu nguoi dung mong doi khi nhin
        # man hinh Cai dat (kenh nam LONG trong muc nhac uong thuoc).
        #
        # MOT ban ghi chong trung dung chung cho ca hai kenh - moc nay coi
        # nhu da xu ly khi ca hai da chay xong.
        if tuy_chon.dose_reminder_enabled:
            if tuy_chon.web_push_enabled:
                send_push_to_patient(db, patient_id, title, body)
            send_telegram_to_patient(db, patient_id, title, body)

        if moc == MOC_GOI:
            # Bao nguoi than ngay o moc nay, khong doi het khung 60 phut -
            # cung hanh vi voi ban client (capy-shell.tsx).
            #
            # NAM NGOAI `if tuy_chon.dose_reminder_enabled` mot cach CO Y:
            # day la luoi an toan cho nguoi than, khong phai tien nghi cua
            # benh nhan. Nguoi muon tat no nhat - benh nhan khong muon con
            # chau biet minh quen thuoc - lai dung la nguoi no sinh ra de bao
            # ve. Muon tat thi phai la quyet dinh cua bac si/nguoi than.
            # Gio DIA PHUONG, khong phai UTC: canh bao nay di toi nguoi
            # than duoi dang text tho (Telegram/man hinh caregiver), doc
            # "hen 14:00 UTC" cho lieu 21:00 la vo nghia voi ho.
            gio_hen = gio_dia_phuong(slot_at)
            tao_canh_bao_cho_nguoi_than(
                db,
                patient_id=patient_id,
                severity="MEDIUM",
                trigger="dose_unconfirmed",
                reason=f"Chưa xác nhận uống {ten_thuoc} (hẹn {gio_hen}) sau 3 lần nhắc",
                dose_event_id=nhom[0].id,
            )

        # Ghi nhan KE CA khi benh nhan chua co thiet bi nao dang ky push -
        # van tinh la da xu ly moc nay, khoi quet lai vo ich moi 60 giay.
        db.add(PushReminderSent(patient_id=patient_id, slot_at=slot_at, moc=moc))
        da_xu_ly += 1

    if da_xu_ly:
        db.commit()
    return da_xu_ly
