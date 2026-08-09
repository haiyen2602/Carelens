"""2 tool ca nhan hoa (chatbot-rag-design.md muc 6):
  - tra_cuu_lich_uong_ca_nhan: "hom nay toi uong thuoc gi" -> query dose_event
  - tra_cuu_don_thuoc_ca_nhan: "thuoc X uong luc nao" -> query prescription.items[]

CA HAI BAT BUOC loc theo dung `patient_id` truyen vao (lay tu ConversationState
cua phien hien tai, KHONG bao gio tu nguon khac) - day la ranh gioi bao mat
that, khong phai ly thuyet: 1 cho sai (vd quen dieu kien WHERE patient_id,
hoac copy-paste nham tu tool kia) se lo du lieu benh nhan khac. Moi truy van
o day dung tham so hoa (:patient_id qua SQLAlchemy), khong noi chuoi.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import DoseEvent, Prescription

ACTIVE_PRESCRIPTION_STATUSES = ("approved", "active")


def tra_cuu_lich_uong_ca_nhan(db: Session, patient_id: str, on_date: datetime | None = None) -> list[dict]:
    """Danh sach dose_event cua DUNG patient_id trong ngay `on_date` (mac
    dinh: khong loc ngay, tra toan bo - Phase 6 co the truyen ngay cu the).
    KHONG nhan tham so nao khac co the doi ket qua sang benh nhan khac."""
    stmt = select(DoseEvent).where(DoseEvent.patient_id == patient_id)
    if on_date is not None:
        day_start = on_date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = on_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        stmt = stmt.where(DoseEvent.scheduled_at >= day_start, DoseEvent.scheduled_at <= day_end)

    rows = db.execute(stmt.order_by(DoseEvent.scheduled_at)).scalars().all()
    return [
        {
            "id": r.id,
            "prescription_id": r.prescription_id,
            "scheduled_at": r.scheduled_at.isoformat(),
            "status": r.status,
            "expected_items": r.expected_items,
        }
        for r in rows
    ]


def tra_cuu_dose_event_ca_nhan(db: Session, patient_id: str, dose_event_id: str) -> dict | None:
    """1 dose_event cu the CUA DUNG patient_id (dung boi node SEVERITY -
    Phase 5b - de biet dang xac nhan lieu nao/thuoc gi). Loc CA HAI dieu kien
    id VA patient_id trong CUNG 1 cau query - tra ve None neu dose_event
    khong ton tai HOAC ton tai nhung thuoc ve benh nhan khac, KHONG phan biet
    2 truong hop nay qua response (tranh lo kenh phu "dose_event nay co ton
    tai nhung khong phai cua ban")."""
    stmt = select(DoseEvent).where(DoseEvent.id == dose_event_id, DoseEvent.patient_id == patient_id)
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        return None
    return {
        "id": row.id,
        "prescription_id": row.prescription_id,
        "status": row.status,
        "expected_items": row.expected_items,
    }


def list_active_prescription_drug_items(db: Session, patient_id: str) -> list[dict]:
    """Vong 2 (chatbot-rag-design.md muc 11.1) - TOAN BO {drug_id, ten_thuoc}
    tu MOI don thuoc ACTIVE cua DUNG patient_id, dung de fuzzy-match ten
    thuoc benh nhan go (co the viet tat/gan dung) truoc khi roi sang hybrid
    search tu do (muc 11.2). Bo qua item khong co drug_id (khong the resolve
    ve 1 chunk RAG cu the)."""
    stmt = select(Prescription).where(
        Prescription.patient_id == patient_id,
        Prescription.status.in_(ACTIVE_PRESCRIPTION_STATUSES),
    )
    prescriptions = db.execute(stmt).scalars().all()

    items: list[dict] = []
    for presc in prescriptions:
        for item in presc.items or []:
            if item.get("drug_id"):
                items.append({"drug_id": item["drug_id"], "ten_thuoc": item.get("ten_thuoc", "")})
    return items


def tra_cuu_don_thuoc_ca_nhan(db: Session, patient_id: str, drug_id: str) -> dict | None:
    """Tim `thoi_diem_dung` (va cac field khac cua item) trong don thuoc DANG
    ACTIVE cua DUNG patient_id co chua drug_id nay. Tra ve None neu benh nhan
    khong co don nao chua thuoc do (chatbot-rag-design.md muc 3.1: khi do
    KHONG suy dien, phai noi ro can hoi bac si)."""
    stmt = select(Prescription).where(
        Prescription.patient_id == patient_id,
        Prescription.status.in_(ACTIVE_PRESCRIPTION_STATUSES),
    )
    prescriptions = db.execute(stmt).scalars().all()

    for presc in prescriptions:
        for item in presc.items or []:
            if item.get("drug_id") == drug_id:
                return {
                    "prescription_id": presc.id,
                    "ten_thuoc": item.get("ten_thuoc"),
                    "lieu_dung": item.get("lieu_dung"),
                    "duong_dung": item.get("duong_dung"),
                    "thoi_diem_dung": item.get("thoi_diem_dung"),
                    "gio_nhac": item.get("gio_nhac"),
                }
    return None
