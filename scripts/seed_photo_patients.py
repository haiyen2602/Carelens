#!/usr/bin/env python3
"""Seed 3 benh nhan mau de thu luong xac nhan lieu thuoc BANG ANH (ADR-0011).

Moi benh nhan phu dung mot nhanh cua backend/services/photo_verification:

  pat_001  1 vien nen + 2 vien nang, cung gio 08:00
           -> CONG DON nhieu thuoc trong MOT anh: can thay 3 vien
  pat_002  1 vien nen + 1 siro
           -> TRON hai che do: EXACT (dem dung so vien) va PRESENCE (chi can
              thay co lo thuoc, vi anh khong noi duoc benh nhan rot bao nhieu ml)
  pat_003  1 thuoc tiem
           -> KHONG XAC MINH DUOC bang anh, phai roi ve nut bam xac nhan

Vi sao la script RIENG, khong them vao seed_demo_patient.py: script do dung de
thu 3 domain cua POST /api/v1/chat (xem docstring cua no), gop them 3 benh nhan
anh vao se lam logic "xoa theo DEMO_PATIENT_ID roi tao lai" cua no phuc tap
hon, va nguoi khac dang dung no hang ngay.

Thuoc dung o day la thuoc THAT trong 'data pharmacy/' (kem dang bao che that),
nhung PHAN LON CHUA duoc embed vao drug_chunks (moi co 226/3688 thuoc). Khong
sao: luong xac nhan bang anh khong dung RAG - no chi can `dang_thuoc` va
`so_vien`, ca hai deu nam trong prescription.items do bac si ke.

TAI CHAY DUOC: xoa du lieu cu loc dung theo 3 patient_id nay roi tao lai, chay
bao nhieu lan cung ra ket qua giong nhau. Khong bao gio cham vao benh nhan khac.

Usage:
    python scripts/seed_photo_patients.py
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.db.base import SessionLocal  # noqa: E402
from backend.db.models import DoseEvent, Patient, Prescription  # noqa: E402
from backend.services.photo_verification import doi_chieu_don_thuoc  # noqa: E402

DOCTOR_ID = "demo-doctor-01"
GIO_UONG = "08:00"

# Thuoc that trong 'data pharmacy/' - giu nguyen id/ten/dang bao che that de
# du lieu mau khong lech voi du lieu san xuat.
VIEN_NEN = ("agi-calci-agimexpharm-20x10", "Agi-calci Agimexpharm 20x10", "Viên nén", "Uống")
VIEN_NANG = ("aginfolix-5-agimexpharm-10x10", "Aginfolix 5 Agimexpharm 10x10", "Viên nang cứng", "Uống")
SIRO = ("a-t-calci-plus-an-thien-30-ong-x-10ml-huong-cam", "A.t Calci PLUS An Thiên", "Siro", "Uống")
THUOC_TIEM = ("vitamin-c-100mg-2ml-vidipha-100-ong", "Vitamin C 100mg/2ml Vidipha", "Dung dịch tiêm", "Tiêm")


def _thuoc(nguon: tuple[str, str, str, str], so_vien: int) -> dict:
    """Mot phan tu items[] cua PrescriptionDTO (api-contracts.md §2)."""
    drug_id, ten_thuoc, dang_thuoc, duong_dung = nguon
    return {
        "drug_id": drug_id,
        "ten_thuoc": ten_thuoc,
        "dang_thuoc": dang_thuoc,
        "duong_dung": duong_dung,
        "lieu_dung": f"{so_vien} đơn vị/lần",
        "thoi_diem_dung": "Sau khi ăn sáng",
        "so_vien_moi_lan": so_vien,
        "gio_nhac": [GIO_UONG],
    }


def _expected_item(item: dict) -> dict:
    """Mot phan tu expected_items[] cua DoseEventDTO (api-contracts.md §3).

    Mang theo `dang_thuoc` va `duong_dung` - hai truong nay KHONG co trong ban
    goc cua dose_event, them vao de tang doi chieu anh khong phai join nguoc
    ve prescription/drug_chunks. Them truong la thay doi CONG THEM, code cu
    doc bang .get() nen khong hong.
    """
    return {
        "drug_id": item["drug_id"],
        "ten_thuoc": item["ten_thuoc"],
        "so_vien": item["so_vien_moi_lan"],
        "dang_thuoc": item["dang_thuoc"],
        "duong_dung": item["duong_dung"],
    }


BENH_NHAN = [
    {
        "id": "pat_001",
        "full_name": "Nguyễn Văn Ba",
        "year_of_birth": 1948,
        "note": "Tăng huyết áp, sau đột quỵ",
        "items": [_thuoc(VIEN_NEN, 1), _thuoc(VIEN_NANG, 2)],
        "kich_ban": "cộng dồn nhiều thuốc trong một ảnh",
    },
    {
        "id": "pat_002",
        "full_name": "Trần Thị Hoa",
        "year_of_birth": 1955,
        "note": "Loãng xương, ho kéo dài",
        "items": [_thuoc(VIEN_NEN, 1), _thuoc(SIRO, 1)],
        "kich_ban": "trộn đếm chính xác với chỉ xác minh có mặt",
    },
    {
        "id": "pat_003",
        "full_name": "Lê Văn Tám",
        "year_of_birth": 1940,
        "note": "Thiếu vitamin, dùng đường tiêm",
        "items": [_thuoc(THUOC_TIEM, 1)],
        "kich_ban": "không xác minh được bằng ảnh",
    },
]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ids = [b["id"] for b in BENH_NHAN]
    db = SessionLocal()
    try:
        # Xoa theo dung thu tu nguoc voi luc tao, va CHI loc theo 3 id nay.
        db.query(DoseEvent).filter(DoseEvent.patient_id.in_(ids)).delete(synchronize_session=False)
        db.query(Prescription).filter(Prescription.patient_id.in_(ids)).delete(synchronize_session=False)
        db.query(Patient).filter(Patient.id.in_(ids)).delete(synchronize_session=False)
        db.commit()

        hom_nay = datetime.now(UTC).replace(second=0, microsecond=0)
        gio, phut = (int(x) for x in GIO_UONG.split(":"))
        gio_uong = hom_nay.replace(hour=gio, minute=phut)

        for cau_hinh in BENH_NHAN:
            # Ho so benh nhan phai co TRUOC don thuoc: don thuoc tro toi
            # patient_id, tao nguoc thu tu se de lai don mo coi neu loi giua chung.
            db.add(
                Patient(
                    id=cau_hinh["id"],
                    full_name=cau_hinh["full_name"],
                    year_of_birth=cau_hinh["year_of_birth"],
                    doctor_id=DOCTOR_ID,
                    note=cau_hinh["note"],
                )
            )
            db.flush()

            presc = Prescription(
                patient_id=cau_hinh["id"],
                doctor_id=DOCTOR_ID,
                status="active",
                items=cau_hinh["items"],
                start_date=hom_nay.date().isoformat(),
                duration_days=7,
                note=cau_hinh["note"],
                approved_by=DOCTOR_ID,
                approved_at=hom_nay,
            )
            db.add(presc)
            db.flush()

            # MOT dose_event cho ca nhom thuoc uong cung gio - dieu kien de
            # benh nhan bay tat ca ra roi chup MOT anh.
            db.add(
                DoseEvent(
                    prescription_id=presc.id,
                    patient_id=cau_hinh["id"],
                    scheduled_at=gio_uong,
                    window_start=gio_uong - timedelta(minutes=30),
                    window_end=gio_uong + timedelta(minutes=30),
                    status="PENDING",
                    expected_items=[_expected_item(i) for i in cau_hinh["items"]],
                )
            )
            cau_hinh["_presc_id"] = presc.id

        db.commit()
        _in_ket_qua()
        return 0
    finally:
        db.close()


def _in_ket_qua() -> None:
    """In ra ky vong da tinh bang chinh logic doi chieu that.

    Doi chieu ngay tai day de seed khong the lech voi code: neu bang luat quy
    doi dang bao che doi, so ky vong in ra doi theo, khong phai comment chet.
    """
    print("Da seed 3 benh nhan mau cho luong xac nhan bang anh:\n")
    for cau_hinh in BENH_NHAN:
        expected = [_expected_item(i) for i in cau_hinh["items"]]
        yeu_cau = doi_chieu_don_thuoc(expected, {}).yeu_cau
        thuoc = ", ".join(f"{i['ten_thuoc'][:28]} ({i['dang_thuoc']}) x{i['so_vien_moi_lan']}" for i in cau_hinh["items"])

        print(f"  {cau_hinh['id']}  {cau_hinh['full_name']}  — {cau_hinh['kich_ban']}")
        print(f"      đơn thuốc     : {thuoc}")
        print(f"      ảnh cần thấy  : {dict(yeu_cau.so_luong) or 'không xác minh được bằng ảnh'}")
        if yeu_cau.bo_qua:
            print(f"      bỏ qua        : {', '.join(t.ten_thuoc for t in yeu_cau.bo_qua)}")
        print(f"      liều PENDING  : {GIO_UONG} hôm nay (cửa sổ ±30 phút)")
        print()


if __name__ == "__main__":
    raise SystemExit(main())
