#!/usr/bin/env python3
"""Seed 1 benh nhan demo + 1 don thuoc active + 2 dose_event hom nay, du de
thu ca 3 domain cua POST /api/v1/chat trong 1 lan chat (chatbot-rag-design.md
muc 6):
  - domain 1 (drug_info): hoi thong tin chung ve thuoc (vd "Vitamin C dung
    de lam gi", "vitamin C co tac dung phu gi khong") - tra loi tu RAG that
    (drug_chunks, thuoc that trong 3562 thuoc da embed).
  - domain 2 (today_schedule): "hom nay toi uong thuoc gi" - tra loi tu 2
    dose_event da seed (1 TAKEN, 1 PENDING).
  - domain 3 (thoi_diem_dung / dose_confirmation): "vitamin C uong luc nao"
    (ghep RAG + Prescription.items[].thoi_diem_dung that), hoac "toi chua
    uong lieu toi" (CLASSIFY nhanh dose_confirmation, dung lieu PENDING).

KHONG seed case redflag/SEVERITY=Nguy hiem (co y - HIGH_OVERLAY_MESSAGE con
la placeholder, xem backend/services/escalation.py va chatbot-rag-design.md muc
10 #5 - go thu cau kich hoat nhanh do bay gio se thay noi dung CHUA duyet,
de hieu nham la bug neu khong nho truoc).

Script TAI CHAY DUOC (idempotent) - xoa du lieu demo cu (loc dung theo
DEMO_PATIENT_ID) truoc khi tao lai, an toan chay nhieu lan (vd Phase 7 can
reset DB roi seed lai nhieu lan luc eval), khong bao gio dung tay/cham vao
du lieu benh nhan khac.

Usage:
    python scripts/seed_demo_patient.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sqlalchemy import text  # noqa: E402

from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import DoseEvent, Prescription  # noqa: E402

# BUG THAT, sua 2026-08-12 (vong 3, muc 5.1): ban truoc dung
# `datetime.now(UTC).replace(hour=8)` - giu tzinfo=UTC nen "morning"/"evening"
# thuc ra la 8h/20h GIO UTC (= 15h/3h SANG HOM SAU gio VN), khong phai
# 8h sang/8h toi GIO VIET NAM nhu ten bien va muc dich demo (mo phong lich
# uong thuoc that cua benh nhan VN). Dung fixed-offset +07:00 (VN khong co
# DST), cung pattern da dung o scripts/log_*.py, KHONG dung UTC lam moc roi
# doi gio.
VN_TZ = timezone(timedelta(hours=7))

DEMO_PATIENT_ID = "demo-patient-01"
DEMO_DOCTOR_ID = "demo-doctor-01"

# Thuoc THAT trong 3562 thuoc da embed (Phase 3) - xac nhan bang tay
# 2026-08-08: oral, Nhe, huong dan dung ro rang trong RAG ("1 vien x 1-2
# lan/ngay, duong uong"), phu hop lam demo (khong phai dang tiem truyen).
DEMO_DRUG_ID = "vitamin-c-500mg-khapharco-200v"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    db = SessionLocal()
    try:
        drug_row = db.execute(
            text("SELECT DISTINCT ten_thuoc FROM drug_chunks WHERE drug_id = :d"),
            {"d": DEMO_DRUG_ID},
        ).fetchone()
        if drug_row is None:
            print(f"LOI: khong tim thay drug_id={DEMO_DRUG_ID!r} trong drug_chunks.")
            print("Co the du lieu goc da doi - chon 1 drug_id khac that trong bang roi cap nhat DEMO_DRUG_ID.")
            return 1
        ten_thuoc = drug_row.ten_thuoc

        # Xoa du lieu demo cu - CHI loc theo DEMO_PATIENT_ID, khong dung tay
        # toi du lieu benh nhan khac. Tai chay duoc: chay lai script nay bao
        # nhieu lan cung ra ket qua giong nhau.
        db.query(DoseEvent).filter(DoseEvent.patient_id == DEMO_PATIENT_ID).delete(synchronize_session=False)
        db.query(Prescription).filter(Prescription.patient_id == DEMO_PATIENT_ID).delete(synchronize_session=False)
        db.commit()

        presc = Prescription(
            patient_id=DEMO_PATIENT_ID,
            doctor_id=DEMO_DOCTOR_ID,
            status="approved",
            items=[
                {
                    "ten_thuoc": ten_thuoc,
                    "ham_luong": "500mg",
                    "dang_thuoc": "Viên nang cứng",
                    "lieu_dung": "1 viên/lần",
                    "duong_dung": "Uống",
                    # thoi_diem_dung: chi dinh CUA BAC SI cho benh nhan nay
                    # (khong phai RAG - chatbot-rag-design.md muc 3.1), khac
                    # voi huong dan chung "1 vien x 1-2 lan/ngay" trong
                    # drug_chunks.cach_dung.
                    "thoi_diem_dung": "Sau khi ăn sáng và ăn tối",
                    "so_vien_moi_lan": 1,
                    "gio_nhac": ["08:00", "20:00"],
                    "drug_id": DEMO_DRUG_ID,
                }
            ],
            start_date=datetime.now(VN_TZ).date().isoformat(),
            duration_days=30,
        )
        db.add(presc)
        db.commit()

        today = datetime.now(VN_TZ).replace(second=0, microsecond=0)
        morning = today.replace(hour=8, minute=0)
        evening = today.replace(hour=20, minute=0)
        # dang_thuoc/duong_dung THEM 2026-08-12 (truoc do thieu, dong bo voi
        # scripts/seed_photo_patients.py) - khong co 2 truong nay thi
        # backend/services/photo_verification/dosage_form.py khong phan loai
        # duoc, moi lieu cua benh nhan demo se bao "khong xac minh duoc bang
        # anh" du la vien nang that (dang_thuoc="" bi coi la khong nhan dien duoc).
        expected_items = [{
            "drug_id": DEMO_DRUG_ID, "ten_thuoc": ten_thuoc, "so_vien": 1,
            "dang_thuoc": "Viên nang cứng", "duong_dung": "Uống",
        }]

        dose_taken = DoseEvent(
            prescription_id=presc.id,
            patient_id=DEMO_PATIENT_ID,
            scheduled_at=morning,
            window_start=morning - timedelta(minutes=30),
            window_end=morning + timedelta(minutes=30),
            status="TAKEN",
            expected_items=expected_items,
        )
        # PENDING - chua xac nhan, dung de thu nhanh dose_confirmation/
        # CLASSIFY (vd "toi chua uong lieu toi", "toi quen uong buoi toi").
        dose_pending = DoseEvent(
            prescription_id=presc.id,
            patient_id=DEMO_PATIENT_ID,
            scheduled_at=evening,
            window_start=evening - timedelta(minutes=30),
            window_end=evening + timedelta(minutes=30),
            status="PENDING",
            expected_items=expected_items,
        )
        db.add_all([dose_taken, dose_pending])
        db.commit()

        print("Da seed benh nhan demo thanh cong:")
        print(f"  patient_id       = {DEMO_PATIENT_ID}")
        print(f"  prescription_id  = {presc.id}")
        print(f"  thuoc            = {ten_thuoc} ({DEMO_DRUG_ID})")
        print(f"  thoi_diem_dung   = {presc.items[0]['thoi_diem_dung']}")
        print(f"  dose_event TAKEN   = {dose_taken.id} (08:00 hom nay)")
        print(f"  dose_event PENDING = {dose_pending.id} (20:00 hom nay)")
        print()
        print("Goi thu POST /api/v1/chat (nho header X-Internal-Secret - xem .env INTERNAL_AUTH_SECRET):")
        print(f'  {{"patient_id": "{DEMO_PATIENT_ID}", "message": "Vitamin C dùng để làm gì"}}')
        print(f'  {{"patient_id": "{DEMO_PATIENT_ID}", "message": "hôm nay tôi uống thuốc gì"}}')
        print(f'  {{"patient_id": "{DEMO_PATIENT_ID}", "message": "Vitamin C uống lúc nào"}}')
        print(f'  {{"patient_id": "{DEMO_PATIENT_ID}", "message": "tôi chưa uống liều buổi tối"}}')
        print()
        print("KHONG go cau kich hoat redflag (vd \"khó thở\", \"10 viên uống hết\") de thu ngay luc nay -")
        print("4 overlay message (OVERDOSE/MISSED_DOSE/SYMPTOM/SIDE_EFFECT) con la placeholder chua duyet (chatbot-rag-design.md muc 10 #5).")
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
