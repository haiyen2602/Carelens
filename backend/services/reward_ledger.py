"""Nghiep vu diem thuong: cong diem, xet Rank, doi qua.

MOI thay doi diem deu di qua `_award()` o day - khong route/service nao
duoc tu UPDATE thang PatientRewardAccount. Ly do: so du va ledger phai luon
khop nhau, va viec "1 lan/ngay" chi dung neu ca hai duoc ghi trong cung mot
transaction.

Cach chan cong trung, KHAC NHAU theo loai (tu migration 0050):
  - DAILY_SURVEY / WEEKLY_STREAK / MONTHLY_STREAK: index duy nhat mot phan
    (patient_id, event_type, occurred_on) o tang DB + savepoint, cung mau
    voi backend/services/agent_feedback.py va agent_idempotency.py - goi
    award_* lan hai trong ngay thi bi DB tu choi va ham tra ve False trong
    im lang (khong phai loi: cac ham nay duoc goi sau MOI lan xac nhan
    lieu, phan lon cac lan la trung).
  - DOSE_ON_TIME: 1 ngay CO nhieu dong (cong theo tung lieu) nen khong the
    dua vao khoa duy nhat. Thay bang phep tru 'dang le duoc bao nhieu' -
    'da cong bao nhieu hom nay' trong award_dose_on_time(): goi lai khi so
    lieu da uong khong doi thi phan chenh = 0 nen khong ghi gi.

GIOI HAN DA BIET - chi ho tro dose runtime "legacy": phep "hom nay uong du
thuoc chua" doc bang `dose_event`. Runtime V2 (settings.dose_runtime_mode =
"shadow"/"v2", mac dinh dang la "legacy") ghi vao bang KHAC han la
`dose_occurrence`, voi bo trang thai rieng - khi nhom bat V2 that su thi
diem "uong thuoc dung gio" se AM THAM ngung cong. Chua viet san nhanh V2 o
day vi khong the kiem thu dung/sai luc nay; nguoi thuc hien viec chuyen mode
(APP-4) can sua `da_uong_du_thuoc_trong_ngay()` va `_du_chuoi_hoan_hao()` cho
doc dung bang theo mode, va noi them loi goi trong
backend/services/scheduling/dose_state.py::_transition_locked.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import DoseEvent, PatientRewardAccount, PatientRewardEvent
from backend.services import reward_catalog as catalog

# Lech gio Viet Nam so voi UTC. Dung so co dinh thay vi ZoneInfo("Asia/
# Ho_Chi_Minh") - cung ly do da giai thich ky o backend/api/reporting_routes.py
# (_GIO_VN): Viet Nam khong co gio mua he, va tranh phu thuoc goi `tzdata`
# tren Windows. CAN mui gio o day chu khong duoc dung ngay UTC: mot lieu
# 06:00 gio VN la 23:00 UTC HOM TRUOC, gom nhom theo ngay UTC se tinh nham
# lieu buoi sang sang ngay hom truoc va lam hong ca phep "hom nay uong du
# thuoc chua".
_GIO_VN = timedelta(hours=7)

# Trang thai coi la "da uong" khi xet cong diem. DELAYED (uong tre nhung van
# trong ngay) CO tinh la da uong o moi bao cao khac cua he thong (xem
# reporting_routes._TRANG_THAI_CO_KET_QUA), nhung o day CHI TAKEN moi duoc
# thuong - phan thuong nay ten la "uong thuoc dung gio", tra cho DELAYED thi
# mat han y nghia khuyen khich.
_TRANG_THAI_DUOC_THUONG = ("TAKEN",)

# Cac trang thai da chot ket qua trong ngay. Con PENDING/AWAITING_CAREGIVER
# nghia la ngay do chua xong, chua xet thuong duoc.
_TRANG_THAI_DA_CHOT = ("TAKEN", "DELAYED", "MISSED")


def ngay_vn(moc: datetime | None = None) -> date:
    """Hom nay theo gio Viet Nam (khong phai gio UTC cua may chu)."""
    goc = moc or datetime.now(UTC)
    return (goc + _GIO_VN).date()


def _khoang_utc_cua_ngay_vn(ngay: date) -> tuple[datetime, datetime]:
    """[dau, cuoi) theo UTC cua tron mot ngay gio Viet Nam."""
    dau = datetime(ngay.year, ngay.month, ngay.day, tzinfo=UTC) - _GIO_VN
    return dau, dau + timedelta(days=1)


def _lay_hoac_tao_so(db: Session, patient_id: str) -> PatientRewardAccount:
    row = db.get(PatientRewardAccount, patient_id)
    if row is not None:
        return row
    row = PatientRewardAccount(patient_id=patient_id, lifetime_points=0, spendable_points=0)
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        # Hai request cua cung benh nhan tao so cung luc - dong kia da thang,
        # doc lai cua no thay vi bao loi.
        db.expire_all()
        existing = db.get(PatientRewardAccount, patient_id)
        if existing is None:  # pragma: no cover - chi xay ra neu DB that su hong
            raise
        return existing
    return row


def _award(
    db: Session,
    *,
    patient_id: str,
    event_type: str,
    points: int,
    occurred_on: date | None,
    label: str,
    item_id: str | None = None,
) -> bool:
    """Ghi 1 dong ledger + cap nhat so du. True neu ghi duoc, False neu da
    ton tai dong cho (benh nhan, loai, ngay) nay roi.

    KHONG commit - de nguoi goi quyet dinh, vi ham nay thuong duoc goi giua
    mot transaction dang do (vd sau khi cap nhat trang thai lieu thuoc)."""
    su_kien = PatientRewardEvent(
        patient_id=patient_id,
        event_type=event_type,
        points_delta=points,
        occurred_on=occurred_on,
        item_id=item_id,
        label=label,
    )
    try:
        with db.begin_nested():
            db.add(su_kien)
            db.flush()
    except IntegrityError:
        return False

    so = _lay_hoac_tao_so(db, patient_id)
    if points > 0:
        # LP chi tang, va chi tang khi DUOC THUONG - doi qua (points < 0)
        # khong dung toi no, nen Rank khong bao gio tut.
        so.lifetime_points += points
    so.spendable_points += points
    so.updated_at = datetime.now(UTC)
    return True


def da_uong_du_thuoc_trong_ngay(db: Session, patient_id: str, ngay: date) -> bool:
    """Ngay do co it nhat 1 lieu, va TAT CA lieu deu TAKEN."""
    dau, cuoi = _khoang_utc_cua_ngay_vn(ngay)
    trang_thai = db.scalars(
        select(DoseEvent.status).where(
            DoseEvent.patient_id == patient_id,
            DoseEvent.scheduled_at >= dau,
            DoseEvent.scheduled_at < cuoi,
            # CANCELLED (phac do da dung) khong noi len benh nhan co uong hay
            # khong - bo ra khoi phep tinh thay vi tinh la truot.
            DoseEvent.status != "CANCELLED",
        )
    ).all()
    if not trang_thai:
        return False
    return all(tt in _TRANG_THAI_DUOC_THUONG for tt in trang_thai)


def _dem_lieu_trong_ngay(db: Session, patient_id: str, ngay: date) -> tuple[int, int]:
    """(so lieu DA UONG dung gio, tong so lieu) cua ngay do."""
    dau, cuoi = _khoang_utc_cua_ngay_vn(ngay)
    trang_thai = db.scalars(
        select(DoseEvent.status).where(
            DoseEvent.patient_id == patient_id,
            DoseEvent.scheduled_at >= dau,
            DoseEvent.scheduled_at < cuoi,
            # CANCELLED (phac do da dung) khong noi len benh nhan co uong
            # hay khong - bo ra khoi phep tinh thay vi tinh la truot.
            DoseEvent.status != "CANCELLED",
        )
    ).all()
    da_uong = sum(1 for tt in trang_thai if tt in _TRANG_THAI_DUOC_THUONG)
    return da_uong, len(trang_thai)


def _diem_dose_da_cong(db: Session, patient_id: str, ngay: date) -> int:
    """Tong diem DOSE_ON_TIME da cong cho ngay do (co the gom nhieu dong)."""
    tong = db.scalar(
        select(func.coalesce(func.sum(PatientRewardEvent.points_delta), 0)).where(
            PatientRewardEvent.patient_id == patient_id,
            PatientRewardEvent.event_type == catalog.EVENT_DOSE_ON_TIME,
            PatientRewardEvent.occurred_on == ngay,
        )
    )
    return int(tong or 0)


def award_dose_on_time(db: Session, patient_id: str, ngay: date | None = None) -> int:
    """Cong diem NGAY sau moi lieu uong dung gio, toi da 20 diem/ngay.

    Tra ve SO DIEM vua cong o LAN GOI NAY (0 neu khong cong duoc gi) -
    KHONG phai tong luy ke cua ngay. Gia tri nay duoc dung de bao cho benh
    nhan biet ngay "+N diem" thay vi ho phai tu mo trang Diem thuong ra xem
    (yeu cau UX 2026-08-26) - xem noi goi o dose_routes.py va verifier.py.

    SUA 2026-08-26 (yeu cau nhom truong): truoc day cong 1 lan +20 khi CA
    NGAY da uong du - benh nhan uong lieu sang khong thay gi, va thieu 1
    lieu la mat sach 20 diem. Gio moi lieu cong ngay mot phan.

    Cach chia: sau khi uong k tren tong n lieu, TONG diem cua ngay phai la
    round(20*k/n); moi lan goi chi ghi PHAN CHENH so voi nhung gi da cong.
    Vd 3 lieu: 7 -> 6 -> 7 (cong don 7/13/20). Cach nay giu 3 tinh chat:
      - Tong ngay uong du LUON dung 20, khong le do lam tron.
      - Tu chong cong trung: goi lai khi k khong doi thi chenh = 0, nen
        khong con can UniqueConstraint theo ngay cho DOSE_ON_TIME (da doi
        thanh index mot phan o migration 0050).
      - n doi giua ngay (bac si them/dung 1 don) van tu can lai dung ty le.

    KHONG thu hoi diem khi k giam (vd nguoi than sua TAKEN -> MISSED): chi
    ghi khi chenh duong. Tru diem da cong se lam so diem tut xuong truoc
    mat benh nhan - phan tac dung voi mot he thong dong vien, va so tien
    "boi thuong" toi da chi 20 diem/ngay.

    Tra ve True neu lan goi nay co cong them diem."""
    hom_nay = ngay or ngay_vn()
    da_uong, tong_lieu = _dem_lieu_trong_ngay(db, patient_id, hom_nay)
    if tong_lieu == 0 or da_uong == 0:
        return 0

    muc_tieu = round(catalog.POINTS_DOSE_ON_TIME * da_uong / tong_lieu)
    chenh = muc_tieu - _diem_dose_da_cong(db, patient_id, hom_nay)
    if chenh <= 0:
        return 0

    duoc = _award(
        db,
        patient_id=patient_id,
        event_type=catalog.EVENT_DOSE_ON_TIME,
        points=chenh,
        occurred_on=hom_nay,
        label=f"{catalog.EVENT_LABELS[catalog.EVENT_DOSE_ON_TIME]} ({da_uong}/{tong_lieu} liều)",
    )
    if not duoc:
        # _award() chi tra False neu UniqueConstraint chan (khong ap dung
        # cho DOSE_ON_TIME nua - xem migration 0050) hoac loi khac; giu
        # nhanh nay de an toan neu logic tren doi trong tuong lai.
        return 0
    # Thuong chuoi chi xet khi ca ngay da uong du - chuoi la phan thuong
    # cho ngay HOAN HAO, khong phai cho tung lieu le.
    if da_uong == tong_lieu:
        _xet_thuong_chuoi(db, patient_id, hom_nay)
    return chenh


def award_daily_survey(db: Session, patient_id: str, ngay: date | None = None) -> bool:
    """Thuong +10 khi benh nhan tra loi khao sat suc khoe cua ngay."""
    return _award(
        db,
        patient_id=patient_id,
        event_type=catalog.EVENT_DAILY_SURVEY,
        points=catalog.POINTS_DAILY_SURVEY,
        occurred_on=ngay or ngay_vn(),
        label=catalog.EVENT_LABELS[catalog.EVENT_DAILY_SURVEY],
    )


def _du_chuoi_hoan_hao(db: Session, patient_id: str, den_ngay: date, so_ngay: int) -> bool:
    """`so_ngay` ngay lien tiep tinh nguoc tu `den_ngay`, ngay nao cung co
    lieu va MOI lieu deu TAKEN.

    BAT BUOC dem so ngay thuc te co lieu, khong chi xet "khong co lieu nao
    truot": benh nhan moi dung app duoc 1 ngay thi 6 ngay truoc do khong co
    du lieu gi - neu chi kiem tra ty le truot se ra 100% va ho duoc thuong
    ngay ca chuoi tuan lan chuoi thang trong ngay dau tien (bug that, bo
    test bat duoc)."""
    dau, _ = _khoang_utc_cua_ngay_vn(den_ngay - timedelta(days=so_ngay - 1))
    _, cuoi = _khoang_utc_cua_ngay_vn(den_ngay)
    lieu = db.execute(
        select(DoseEvent.scheduled_at, DoseEvent.status).where(
            DoseEvent.patient_id == patient_id,
            DoseEvent.scheduled_at >= dau,
            DoseEvent.scheduled_at < cuoi,
            DoseEvent.status.in_(_TRANG_THAI_DA_CHOT),
        )
    ).all()
    if not lieu:
        return False

    ngay_co_lieu: set[date] = set()
    for scheduled_at, status in lieu:
        if status not in _TRANG_THAI_DUOC_THUONG:
            return False
        ngay_co_lieu.add(ngay_vn(scheduled_at))
    return len(ngay_co_lieu) >= so_ngay


def _xet_thuong_chuoi(db: Session, patient_id: str, hom_nay: date) -> None:
    """Thuong chuoi tuan (+50) / thang (+100) neu 7 / 30 ngay gan nhat deu
    uong du thuoc.

    `occurred_on` = hom_nay nen moi ngay chi xet duoc toi da 1 lan cho moi
    loai - benh nhan giu chuoi 10 ngay lien se nhan thuong tuan vao ca 10
    ngay do (chuoi cang dai cang duoc thuong lien tuc), dung tinh than
    "thuong chuoi" chu khong phai moc 1 lan."""
    for so_ngay, loai, diem in (
        (7, catalog.EVENT_WEEKLY_STREAK, catalog.POINTS_WEEKLY_STREAK),
        (30, catalog.EVENT_MONTHLY_STREAK, catalog.POINTS_MONTHLY_STREAK),
    ):
        if not _du_chuoi_hoan_hao(db, patient_id, hom_nay, so_ngay):
            continue
        _award(
            db,
            patient_id=patient_id,
            event_type=loai,
            points=diem,
            occurred_on=hom_nay,
            label=catalog.EVENT_LABELS[loai],
        )


# --- Doc du lieu ------------------------------------------------------------


def get_summary(db: Session, patient_id: str) -> dict:
    """So diem + Rank hien tai. Benh nhan chua co so thi tra ve so 0/Rank
    Dong thay vi 404 - chua tich diem la trang thai hop le."""
    so = db.get(PatientRewardAccount, patient_id)
    lifetime = so.lifetime_points if so else 0
    spendable = so.spendable_points if so else 0

    rank = catalog.compute_rank(lifetime)
    ke_tiep = catalog.next_rank(rank)
    return {
        "lifetime_points": lifetime,
        "spendable_points": spendable,
        "rank": rank,
        "rank_label": catalog.RANK_LABELS[rank],
        "next_rank": ke_tiep[0] if ke_tiep else None,
        "next_rank_label": catalog.RANK_LABELS[ke_tiep[0]] if ke_tiep else None,
        "next_rank_at": ke_tiep[1] if ke_tiep else None,
        "points_to_next_rank": max(0, ke_tiep[1] - lifetime) if ke_tiep else None,
    }


def _da_doi(db: Session, patient_id: str) -> set[str]:
    return set(
        db.scalars(
            select(PatientRewardEvent.item_id).where(
                PatientRewardEvent.patient_id == patient_id,
                PatientRewardEvent.event_type == catalog.EVENT_REDEEM,
            )
        ).all()
    )


def list_catalog_for_patient(db: Session, patient_id: str) -> list[dict]:
    """Danh muc qua kem 3 co trang thai da tinh san - frontend chi viec ve,
    khong tu suy lai dieu kien (tranh 2 noi hieu luat khac nhau)."""
    tom_tat = get_summary(db, patient_id)
    rank = tom_tat["rank"]
    sp = tom_tat["spendable_points"]
    da_doi = _da_doi(db, patient_id)

    ket_qua = []
    for item in catalog.CATALOG:
        ket_qua.append(
            {
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "category": item.category,
                "sp_cost": item.sp_cost,
                "rank_required": item.rank_required,
                "rank_required_label": catalog.RANK_LABELS[item.rank_required],
                "unlocked": catalog.rank_meets(rank, item.rank_required),
                "affordable": sp >= item.sp_cost,
                "already_redeemed": item.one_time and item.id in da_doi,
            }
        )
    return ket_qua


def list_history(db: Session, patient_id: str, limit: int = 50) -> list[dict]:
    rows = db.scalars(
        select(PatientRewardEvent)
        .where(PatientRewardEvent.patient_id == patient_id)
        .order_by(PatientRewardEvent.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": r.id,
            "event_type": r.event_type,
            "points_delta": r.points_delta,
            "label": r.label,
            "occurred_on": r.occurred_on.isoformat() if r.occurred_on else None,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


# --- Doi qua ----------------------------------------------------------------


def _so_viet(n: int) -> str:
    """9990 -> "9.990". Tieng Viet dung dau CHAM phan cach hang nghin, con
    f"{n:,}" cua Python ra dau phay kieu Anh."""
    return f"{n:,}".replace(",", ".")


class RewardError(Exception):
    """Loi nghiep vu khi doi qua - route dich sang HTTP status tuong ung."""

    def __init__(self, message: str, *, http_status: int) -> None:
        super().__init__(message)
        self.message = message
        self.http_status = http_status


def redeem_item(db: Session, patient_id: str, item_id: str) -> dict:
    """Doi qua: tru SP, GIU NGUYEN lifetime_points nen Rank khong doi.

    Thu tu kiem tra co chu dich - bao "chua du Rank" truoc "chua du diem",
    vi mon chua mo khoa thi so diem khong con y nghia gi voi benh nhan."""
    item = catalog.get_item(item_id)
    if item is None:
        raise RewardError("Phần quà không tồn tại", http_status=404)

    tom_tat = get_summary(db, patient_id)

    if not catalog.rank_meets(tom_tat["rank"], item.rank_required):
        raise RewardError(
            f"Cần đạt Rank {catalog.RANK_LABELS[item.rank_required]} để đổi phần quà này",
            http_status=403,
        )

    if item.one_time and item_id in _da_doi(db, patient_id):
        raise RewardError("Bạn đã đổi phần quà này rồi", http_status=409)

    if tom_tat["spendable_points"] < item.sp_cost:
        thieu = item.sp_cost - tom_tat["spendable_points"]
        raise RewardError(
            f"Bạn còn thiếu {_so_viet(thieu)} điểm để đổi phần quà này", http_status=400
        )

    ghi_duoc = _award(
        db,
        patient_id=patient_id,
        event_type=catalog.EVENT_REDEEM,
        points=-item.sp_cost,
        # NULL: doi nhieu mon trong cung ngay la hop le, xem docstring cua
        # PatientRewardEvent. Chan doi trung dua vao item_id o tren.
        occurred_on=None,
        label=f"Đổi {item.name}",
        item_id=item.id,
    )
    if not ghi_duoc:  # pragma: no cover - REDEEM khong dinh unique constraint
        raise RewardError("Không ghi nhận được lượt đổi quà", http_status=409)

    return {
        "item_id": item.id,
        "item_name": item.name,
        "sp_spent": item.sp_cost,
        "spendable_points_left": tom_tat["spendable_points"] - item.sp_cost,
    }
