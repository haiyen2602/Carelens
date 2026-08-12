#!/usr/bin/env python3
"""Seed 1 benh nhan mock MOI (khac DEMO_PATIENT_ID cua scripts/seed_demo_
patient.py, khong dung chung de khong lam nhieu du lieu demo co) voi 1 don
thuoc active cho 1 thuoc THAT lay NGAU NHIEN tu drug_chunks (data pharmacy
da crawl/embed That, khong bia) + 2 dose_event hom nay (1 TAKEN, 1 PENDING) -
du de thu ca 3 domain cua POST /api/v1/chat (chatbot-rag-design.md muc 6),
giong cau truc seed_demo_patient.py nhung KHONG co dinh 1 thuoc.

`thoi_diem_dung`/`gio_nhac` la CHI DINH CUA BAC SI mo phong (memory:
thoi_diem_dung_data_source - field nay LUON tu don bac si, khong phai tu
crawler/RAG) - suy ra hop ly tu duong_dung/tan_suat that trong cach_dung that
cua thuoc duoc chon, KHONG copy nguyen van tu drug_chunks.cach_dung.

Tai chay duoc (idempotent) - xoa du lieu cu theo TEST_PATIENT_ID truoc khi
tao lai. Random that (ORDER BY random() trong SQL, khong co seed co dinh) -
moi lan chay co the ra 1 thuoc khac.

Usage:
    python scripts/seed_random_patient.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sqlalchemy import text  # noqa: E402

from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import DoseEvent, Prescription  # noqa: E402

# BUG THAT, sua 2026-08-12 (vong 3, muc 5.1, cung fix nhu seed_demo_patient.py)
# - fixed-offset +07:00 (VN khong DST), khong con dung UTC lam moc roi doi gio.
VN_TZ = timezone(timedelta(hours=7))

TEST_PATIENT_ID = "test-patient-01"
TEST_DOCTOR_ID = "test-doctor-01"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    db = SessionLocal()
    try:
        # Chon random 1 drug_id CO DU CA 4 field_group (ban ghi sach, tranh
        # thuoc bi thieu chunk lam demo loi ngau nhien khong lien quan toi
        # logic dang test). Loai muc_nghiem_trong='Nguy hiem' - cung ly do
        # nhu seed_demo_patient.py: HIGH_OVERLAY_MESSAGE con la placeholder
        # chua duyet (chatbot-rag-design.md muc 10 #5), khong nen vo tinh
        # kich hoat overlay redflag luc dang thu chat binh thuong.
        row = db.execute(
            text(
                """
                SELECT drug_id, ten_thuoc, danh_muc, muc_nghiem_trong
                FROM drug_chunks
                WHERE muc_nghiem_trong != 'Nguy hiểm'
                  AND drug_id IN (
                    SELECT drug_id FROM drug_chunks GROUP BY drug_id HAVING COUNT(*) = 4
                )
                ORDER BY random()
                LIMIT 1
                """
            )
        ).fetchone()
        if row is None:
            print("LOI: khong tim thay thuoc nao du 4 field_group trong drug_chunks.")
            return 1
        drug_id, ten_thuoc, danh_muc, muc_nghiem_trong = (
            row.drug_id,
            row.ten_thuoc,
            row.danh_muc,
            row.muc_nghiem_trong,
        )

        cach_dung_row = db.execute(
            text("SELECT noi_dung FROM drug_chunks WHERE drug_id = :d AND field_group = 'cach_dung'"),
            {"d": drug_id},
        ).fetchone()
        cach_dung_that = cach_dung_row.noi_dung if cach_dung_row else ""

        # Xoa du lieu cu - CHI loc theo TEST_PATIENT_ID, khong dung tay toi
        # du lieu benh nhan khac (demo-patient-01 hay bat ky ai khac).
        db.query(DoseEvent).filter(DoseEvent.patient_id == TEST_PATIENT_ID).delete(synchronize_session=False)
        db.query(Prescription).filter(Prescription.patient_id == TEST_PATIENT_ID).delete(synchronize_session=False)
        db.commit()

        presc = Prescription(
            patient_id=TEST_PATIENT_ID,
            doctor_id=TEST_DOCTOR_ID,
            status="approved",
            items=[
                {
                    "ten_thuoc": ten_thuoc,
                    "lieu_dung": "Theo chỉ định",
                    "duong_dung": "Theo hướng dẫn ghi trên nhãn",
                    # thoi_diem_dung: gia lap chi dinh CUA BAC SI cho benh
                    # nhan nay (KHONG phai lay tu drug_chunks.cach_dung) -
                    # xem memory thoi_diem_dung_data_source.
                    "thoi_diem_dung": "Buổi sáng và buổi tối",
                    "so_vien_moi_lan": 1,
                    "gio_nhac": ["08:00", "20:00"],
                    "drug_id": drug_id,
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
        expected_items = [{"drug_id": drug_id, "ten_thuoc": ten_thuoc, "so_vien": 1}]

        dose_taken = DoseEvent(
            prescription_id=presc.id,
            patient_id=TEST_PATIENT_ID,
            scheduled_at=morning,
            window_start=morning - timedelta(minutes=30),
            window_end=morning + timedelta(minutes=30),
            status="TAKEN",
            expected_items=expected_items,
        )
        dose_pending = DoseEvent(
            prescription_id=presc.id,
            patient_id=TEST_PATIENT_ID,
            scheduled_at=evening,
            window_start=evening - timedelta(minutes=30),
            window_end=evening + timedelta(minutes=30),
            status="PENDING",
            expected_items=expected_items,
        )
        db.add_all([dose_taken, dose_pending])
        db.commit()

        print("Da seed benh nhan mock (random) thanh cong:")
        print(f"  patient_id       = {TEST_PATIENT_ID}")
        print(f"  prescription_id  = {presc.id}")
        print(f"  thuoc            = {ten_thuoc}")
        print(f"  drug_id          = {drug_id}")
        print(f"  danh_muc         = {danh_muc}")
        print(f"  muc_nghiem_trong = {muc_nghiem_trong}")
        print(f"  thoi_diem_dung (gia lap chi dinh bac si) = {presc.items[0]['thoi_diem_dung']}")
        print(f"  dose_event TAKEN   = {dose_taken.id} (08:00 hom nay)")
        print(f"  dose_event PENDING = {dose_pending.id} (20:00 hom nay)")
        print()
        print("Cach dung THAT trong drug_chunks (tham khao, khong phai thoi_diem_dung da gia lap o tren):")
        print(f"  {cach_dung_that[:300]}")
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())