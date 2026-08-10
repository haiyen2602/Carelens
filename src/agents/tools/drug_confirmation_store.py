"""CRUD cho bang pending_drug_confirmation (chatbot-rag-design.md muc 11.3) -
1 dong = 1 benh nhan DANG cho xac nhan danh tinh thuoc GIUA 2 lan goi HTTP.
Tach rieng module nay (khong nhet thang vao node) de node logic khong phai
biet chi tiet SQL, giong pattern cac tool khac trong src/agents/tools/.

TTL - THEM 2026-08-09 (phat hien qua review): benh nhan bo do 1 cau hoi giua
chung (khong tra loi xac nhan) se de lai pending state TREO VINH VIEN neu
khong co gioi han thoi gian - tin nhan KHONG lien quan gui sau do (ke ca vai
ngay sau) se bi hieu NHAM la dang tra loi cau hoi xac nhan cu. Xu ly bang
CHECK-ON-READ (get_pending_confirmation() tu kiem tra tuoi cua dong, xoa va
tra ve None neu qua han) - KHONG can APScheduler/job nen rieng cho dung y
nay: check-on-read da du de tin nhan tiep theo cua CHINH benh nhan do khong
bi hieu nham (dung y patient-safety chinh, giai quyet duoc NGAY, khong phai
cho toi muc 4 co APScheduler moi lam duoc). 1 sweep dinh ky qua APScheduler
(khi muc 4 xay xong) co the THEM SAU nhu don dep VAT LY cac dong da qua han
ma khong ai gui tin nhan tiep (khong ai doc lai row do de trigger check-on-
read) - la bo sung "don rac", khong phai yeu cau dung dan (correctness), nen
KHONG chan viec dong muc 5 lai day."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config import get_settings
from src.db.models import PendingDrugConfirmation


def get_pending_confirmation(db: Session, patient_id: str) -> dict | None:
    row = db.execute(
        select(PendingDrugConfirmation).where(PendingDrugConfirmation.patient_id == patient_id)
    ).scalar_one_or_none()
    if row is None:
        return None

    settings = get_settings()
    age = datetime.now(UTC) - row.created_at
    if age > timedelta(minutes=settings.drug_confirmation_ttl_minutes):
        # Het han - coi nhu KHONG co pending (tin nhan nay se duoc hieu la
        # CAU HOI MOI, khong phai reply cho cau hoi cu da qua han) - xoa
        # luon, khong de lai rac.
        clear_pending_confirmation(db, patient_id)
        return None

    return {
        "candidates": row.candidates,
        "stage": row.stage,
        "original_query": row.original_query,
        "retry_count": row.retry_count,
    }


def set_pending_confirmation(
    db: Session, patient_id: str, candidates: list[dict], stage: str, original_query: str, retry_count: int = 0
) -> None:
    """Upsert - 1 benh nhan chi co toi da 1 dong (patient_id la PK). Xoa dong
    cu (neu co) roi tao dong moi thay vi UPDATE tung cot - don gian hoa, so
    dong nho (toi da vai the ky tu), khong can toi uu. Tao dong MOI cung lam
    moi `created_at` - dung y TTL la "thoi gian tu lan hoat dong GAN NHAT",
    khong phai tong thoi luong ca hoi thoai (benh nhan tra loi cham nhung
    van dang tich cuc se KHONG bi tinh nham la het han).

    `retry_count` mac dinh 0 (CO TIEN TRIEN - stage/candidates moi) - node
    goi ham nay VOI gia tri retry_count HIEN TAI + 1 khi phai hoi lai DUNG
    stage cu (reply khong parse duoc), de dem so lan LIEN TIEP that bai
    (khac round-budget, xem PendingDrugConfirmation.retry_count docstring)."""
    clear_pending_confirmation(db, patient_id)
    row = PendingDrugConfirmation(
        patient_id=patient_id,
        candidates=candidates,
        stage=stage,
        original_query=original_query,
        retry_count=retry_count,
        created_at=datetime.now(UTC),
    )
    db.add(row)
    db.commit()


def clear_pending_confirmation(db: Session, patient_id: str) -> None:
    db.query(PendingDrugConfirmation).filter(PendingDrugConfirmation.patient_id == patient_id).delete(
        synchronize_session=False
    )
    db.commit()