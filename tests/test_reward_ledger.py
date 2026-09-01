"""Unit test cho backend/services/reward_ledger.py - cong diem, xet Rank,
doi qua.

Dung SQLite in-memory that (cung mau tests/test_agent_feedback_service.py)
chu khong mock Session: phan de sai nhat cua tinh nang nay la rang buoc
"1 lan/ngay" o tang DB va viec doi qua KHONG duoc dung toi lifetime_points -
ca hai chi kiem chung duoc bang mot DB that.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.db.models import DoseEvent, PatientRewardAccount, PatientRewardEvent
from backend.services import reward_catalog as catalog
from backend.services import reward_ledger

NGAY = date(2026, 8, 25)
BENH_NHAN = "patient-reward-test"


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    PatientRewardAccount.__table__.create(engine)
    PatientRewardEvent.__table__.create(engine)
    DoseEvent.__table__.create(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _them_lieu(db: Session, *, status: str, gio_vn: int = 8, ngay: date = NGAY) -> DoseEvent:
    """Tao 1 lieu vao `gio_vn` gio (gio Viet Nam) cua `ngay`, luu duoi dang UTC."""
    scheduled = datetime(ngay.year, ngay.month, ngay.day, gio_vn, tzinfo=UTC) - timedelta(hours=7)
    dose = DoseEvent(
        prescription_id="pres-1",
        patient_id=BENH_NHAN,
        scheduled_at=scheduled,
        window_start=scheduled - timedelta(minutes=30),
        window_end=scheduled + timedelta(minutes=30),
        status=status,
        expected_items=[],
    )
    db.add(dose)
    db.commit()
    return dose


# --- Cong diem uong thuoc ---------------------------------------------------


def test_cong_mot_phan_khi_moi_uong_mot_nua_so_lieu(db: Session) -> None:
    """Tu 2026-08-26 diem cong theo TUNG lieu: uong 1/2 lieu duoc 1/2 tran."""
    _them_lieu(db, status="TAKEN", gio_vn=8)
    _them_lieu(db, status="PENDING", gio_vn=20)

    # gia tri tra ve la SO DIEM VUA CONG o lan goi nay, dung tuyet doi 10
    # (khong chi ">0") - benh nhan can thay dung so nay ngay tren toast.
    assert reward_ledger.award_dose_on_time(db, BENH_NHAN, NGAY) == catalog.POINTS_DOSE_ON_TIME // 2
    db.commit()

    assert (
        reward_ledger.get_summary(db, BENH_NHAN)["lifetime_points"]
        == catalog.POINTS_DOSE_ON_TIME // 2
    )


def test_khong_thuong_khi_chua_uong_lieu_nao(db: Session) -> None:
    _them_lieu(db, status="PENDING", gio_vn=8)
    _them_lieu(db, status="MISSED", gio_vn=20)

    assert reward_ledger.award_dose_on_time(db, BENH_NHAN, NGAY) == 0
    assert reward_ledger.get_summary(db, BENH_NHAN)["lifetime_points"] == 0


def test_khong_thuong_khi_ngay_do_khong_co_lieu_nao(db: Session) -> None:
    assert reward_ledger.award_dose_on_time(db, BENH_NHAN, NGAY) == 0


def test_thuong_khi_uong_du_ca_ngay(db: Session) -> None:
    _them_lieu(db, status="TAKEN", gio_vn=8)
    _them_lieu(db, status="TAKEN", gio_vn=20)

    assert reward_ledger.award_dose_on_time(db, BENH_NHAN, NGAY) > 0
    db.commit()

    tom_tat = reward_ledger.get_summary(db, BENH_NHAN)
    assert tom_tat["lifetime_points"] == catalog.POINTS_DOSE_ON_TIME
    assert tom_tat["spendable_points"] == catalog.POINTS_DOSE_ON_TIME


def test_lieu_cuoi_xac_nhan_bang_anh_van_duoc_thuong(db: Session) -> None:
    """Hoi quy: luong xac nhan bang ANH (photo_verification/verifier.py) gan
    TAKEN thang vao dose_event, KHONG di qua PATCH /doses/{id}. Truoc
    2026-08-26 hook cong diem chi nam o dose_routes.py, nen benh nhan chup
    anh xac nhan lieu CUOI trong ngay thi ca ngay "du thuoc" ma khong bao
    gio duoc cong 20 diem. verifier.py phai tu goi award_dose_on_time."""
    _them_lieu(db, status="TAKEN", gio_vn=8)
    lieu_cuoi = _them_lieu(db, status="PENDING", gio_vn=20)

    # moi uong 1/2 lieu -> cong mot phan, chua du tran
    assert reward_ledger.award_dose_on_time(db, BENH_NHAN, NGAY) > 0
    db.flush()

    # verifier.py: anh khop -> gan TAKEN roi tu cong diem
    lieu_cuoi.status = "TAKEN"
    db.flush()
    assert reward_ledger.award_dose_on_time(db, BENH_NHAN, NGAY) > 0
    db.commit()

    so = db.get(PatientRewardAccount, BENH_NHAN)
    assert so.spendable_points == catalog.POINTS_DOSE_ON_TIME

def test_ba_lieu_chia_dung_tong_20_khong_le_do_lam_tron(db: Session) -> None:
    """3 lieu: 20/3 khong chia het. Cong don phai la 7 -> 13 -> 20, khong
    duoc thanh 6+6+6=18 hay 7+7+7=21."""
    lieu = [_them_lieu(db, status="PENDING", gio_vn=g) for g in (8, 13, 20)]
    cong_don = []
    for d in lieu:
        d.status = "TAKEN"
        db.flush()
        reward_ledger.award_dose_on_time(db, BENH_NHAN, NGAY)
        cong_don.append(reward_ledger.get_summary(db, BENH_NHAN)["lifetime_points"])
    db.commit()

    assert cong_don == [7, 13, catalog.POINTS_DOSE_ON_TIME]


def test_goi_lai_nhieu_lan_khong_vuot_tran_moi_ngay(db: Session) -> None:
    """award_dose_on_time duoc goi sau MOI lan xac nhan lieu (ke ca cac lan
    trung, vd nguoi than bam duyet lai) - tong ngay van phai dung tran."""
    _them_lieu(db, status="TAKEN", gio_vn=8)
    _them_lieu(db, status="TAKEN", gio_vn=20)

    for _ in range(5):
        reward_ledger.award_dose_on_time(db, BENH_NHAN, NGAY)
    db.commit()

    assert (
        reward_ledger.get_summary(db, BENH_NHAN)["lifetime_points"]
        == catalog.POINTS_DOSE_ON_TIME
    )


def test_them_lieu_giua_ngay_van_can_lai_dung_ty_le(db: Session) -> None:
    """Bac si ke them don giua ngay -> tong so lieu tang. Diem da cong
    khong bi doi lai, va tong ngay van khong vuot tran."""
    _them_lieu(db, status="TAKEN", gio_vn=8)
    reward_ledger.award_dose_on_time(db, BENH_NHAN, NGAY)
    db.flush()
    assert reward_ledger.get_summary(db, BENH_NHAN)["lifetime_points"] == 20

    # them 1 lieu moi chua uong -> muc tieu tut xuong 10, KHONG thu hoi
    _them_lieu(db, status="PENDING", gio_vn=20)
    assert reward_ledger.award_dose_on_time(db, BENH_NHAN, NGAY) == 0
    db.commit()
    assert reward_ledger.get_summary(db, BENH_NHAN)["lifetime_points"] == 20

def test_uong_tre_duoc_mot_nua_diem(db: Session) -> None:
    """SUA 2026-08-31 (quyet dinh san pham): truoc day DELAYED duoc 0 diem vi
    phan thuong ten la "uong thuoc DUNG GIO". Nhung hanh vi do chua bao gio
    thuc su chay: dose_routes.py gan thang chuoi client gui len nen khong
    duong tu khai nao sinh ra DELAYED - benh nhan uong tre van an tron diem
    duoi nhan TAKEN. Khi backend bat dau chot nhan dung, "tre = 0 diem" se
    triet tieu dong luc xac nhan muon (bo luon con hon bi ghi la tre ma van
    khong duoc gi), nen chot lai: tre duoc MOT NUA.

    1 lieu duy nhat, uong tre -> round(20 * 0.5 / 1) = 10.
    """
    _them_lieu(db, status="DELAYED", gio_vn=8)

    assert reward_ledger.award_dose_on_time(db, BENH_NHAN, NGAY) == 10


def test_uong_tre_van_it_hon_uong_dung_gio(db: Session) -> None:
    """Bat bien quan trong nhat cua muc 50%: tre PHAI thap hon dung gio, neu
    khong phan thuong het phan biet duoc hai hanh vi."""
    _them_lieu(db, status="DELAYED", gio_vn=8)
    diem_tre = reward_ledger.award_dose_on_time(db, BENH_NHAN, NGAY)

    assert 0 < diem_tre < catalog.POINTS_DOSE_ON_TIME


def test_ngay_co_lieu_tre_khong_phai_ngay_hoan_hao(db: Session) -> None:
    """Thuong chuoi chi danh cho ngay HOAN HAO. Mot ngay ma moi lieu deu tre
    van co diem (mot nua), nhung khong duoc tinh vao chuoi."""
    _them_lieu(db, status="DELAYED", gio_vn=8)
    reward_ledger.award_dose_on_time(db, BENH_NHAN, NGAY)
    db.commit()

    chuoi = [
        e
        for e in db.query(PatientRewardEvent).filter(PatientRewardEvent.patient_id == BENH_NHAN)
        if e.event_type in (catalog.EVENT_WEEKLY_STREAK, catalog.EVENT_MONTHLY_STREAK)
    ]
    assert chuoi == []


def test_lieu_da_huy_khong_lam_mat_thuong(db: Session) -> None:
    _them_lieu(db, status="TAKEN", gio_vn=8)
    _them_lieu(db, status="CANCELLED", gio_vn=20)

    assert reward_ledger.award_dose_on_time(db, BENH_NHAN, NGAY) > 0


def test_khong_cong_trung_trong_cung_ngay(db: Session) -> None:
    """dose_routes goi award sau MOI lan xac nhan lieu - lan thu hai tro di
    phai bi rang buoc DB chan lai, khong duoc cong them."""
    _them_lieu(db, status="TAKEN", gio_vn=8)

    assert reward_ledger.award_dose_on_time(db, BENH_NHAN, NGAY) > 0
    db.commit()
    assert reward_ledger.award_dose_on_time(db, BENH_NHAN, NGAY) == 0
    db.commit()

    assert reward_ledger.get_summary(db, BENH_NHAN)["lifetime_points"] == (
        catalog.POINTS_DOSE_ON_TIME
    )


def test_ngay_tinh_theo_gio_viet_nam_khong_phai_utc(db: Session) -> None:
    """Lieu 06:00 gio VN la 23:00 UTC HOM TRUOC - neu gom nhom theo ngay UTC
    thi lieu nay bi day sang ngay hom truoc va ngay NGAY se trong rong."""
    _them_lieu(db, status="TAKEN", gio_vn=6)

    assert reward_ledger.award_dose_on_time(db, BENH_NHAN, NGAY) > 0


# --- Thuong chuoi -----------------------------------------------------------


def test_ngay_dau_tien_khong_duoc_thuong_chuoi(db: Session) -> None:
    """Benh nhan moi dung app 1 ngay KHONG duoc an luon thuong chuoi tuan +
    thang. Truoc khi sua, viec chi xet "khong co lieu nao truot" khien 6/29
    ngay khong co du lieu van tinh la dat chuoi."""
    _them_lieu(db, status="TAKEN", gio_vn=8)
    reward_ledger.award_dose_on_time(db, BENH_NHAN, NGAY)
    db.commit()

    assert reward_ledger.get_summary(db, BENH_NHAN)["lifetime_points"] == (
        catalog.POINTS_DOSE_ON_TIME
    )


def test_du_7_ngay_lien_tiep_duoc_thuong_chuoi_tuan(db: Session) -> None:
    for lui in range(7):
        _them_lieu(db, status="TAKEN", gio_vn=8, ngay=NGAY - timedelta(days=lui))

    reward_ledger.award_dose_on_time(db, BENH_NHAN, NGAY)
    db.commit()

    # +20 uong thuoc, +50 chuoi tuan. Chua du 30 ngay nen khong co chuoi thang.
    assert reward_ledger.get_summary(db, BENH_NHAN)["lifetime_points"] == (
        catalog.POINTS_DOSE_ON_TIME + catalog.POINTS_WEEKLY_STREAK
    )


def test_bo_lieu_giua_chuoi_lam_dut_chuoi(db: Session) -> None:
    for lui in range(7):
        trang_thai = "MISSED" if lui == 3 else "TAKEN"
        _them_lieu(db, status=trang_thai, gio_vn=8, ngay=NGAY - timedelta(days=lui))

    reward_ledger.award_dose_on_time(db, BENH_NHAN, NGAY)
    db.commit()

    assert reward_ledger.get_summary(db, BENH_NHAN)["lifetime_points"] == (
        catalog.POINTS_DOSE_ON_TIME
    )


# --- Khao sat ---------------------------------------------------------------


def test_khao_sat_cong_diem_mot_lan_moi_ngay(db: Session) -> None:
    assert reward_ledger.award_daily_survey(db, BENH_NHAN, NGAY) is True
    db.commit()
    assert reward_ledger.award_daily_survey(db, BENH_NHAN, NGAY) is False
    db.commit()

    assert reward_ledger.get_summary(db, BENH_NHAN)["spendable_points"] == (
        catalog.POINTS_DAILY_SURVEY
    )


def test_khao_sat_va_uong_thuoc_cong_doc_lap(db: Session) -> None:
    _them_lieu(db, status="TAKEN", gio_vn=8)
    reward_ledger.award_dose_on_time(db, BENH_NHAN, NGAY)
    reward_ledger.award_daily_survey(db, BENH_NHAN, NGAY)
    db.commit()

    assert reward_ledger.get_summary(db, BENH_NHAN)["lifetime_points"] == (
        catalog.POINTS_DOSE_ON_TIME + catalog.POINTS_DAILY_SURVEY
    )


# --- Rank -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("diem", "rank"),
    [
        (0, catalog.BRONZE),
        (9_999, catalog.BRONZE),
        (10_000, catalog.SILVER),
        (29_999, catalog.SILVER),
        (30_000, catalog.GOLD),
        (59_999, catalog.GOLD),
        (60_000, catalog.DIAMOND),
        (1_000_000, catalog.DIAMOND),
    ],
)
def test_xet_rank_theo_nguong(diem: int, rank: str) -> None:
    assert catalog.compute_rank(diem) == rank


def test_tom_tat_bao_con_thieu_bao_nhieu_diem_toi_rank_ke(db: Session) -> None:
    _dat_diem(db, lifetime=25_000, spendable=25_000)

    tom_tat = reward_ledger.get_summary(db, BENH_NHAN)
    assert tom_tat["rank"] == catalog.SILVER
    assert tom_tat["next_rank"] == catalog.GOLD
    assert tom_tat["points_to_next_rank"] == 5_000


def test_rank_cao_nhat_khong_con_moc_ke_tiep(db: Session) -> None:
    _dat_diem(db, lifetime=60_000, spendable=0)

    tom_tat = reward_ledger.get_summary(db, BENH_NHAN)
    assert tom_tat["rank"] == catalog.DIAMOND
    assert tom_tat["next_rank"] is None
    assert tom_tat["points_to_next_rank"] is None


def test_benh_nhan_chua_co_so_tra_ve_rank_dong(db: Session) -> None:
    tom_tat = reward_ledger.get_summary(db, "chua-tung-tich-diem")
    assert tom_tat["rank"] == catalog.BRONZE
    assert tom_tat["lifetime_points"] == 0


# --- Doi qua ----------------------------------------------------------------


def _dat_diem(db: Session, *, lifetime: int, spendable: int) -> None:
    db.add(
        PatientRewardAccount(
            patient_id=BENH_NHAN, lifetime_points=lifetime, spendable_points=spendable
        )
    )
    db.commit()


def test_doi_qua_tru_sp_nhung_giu_nguyen_rank(db: Session) -> None:
    """Yeu cau nghiep vu quan trong nhat: doi qua KHONG lam tut Rank."""
    _dat_diem(db, lifetime=60_000, spendable=60_000)

    ket_qua = reward_ledger.redeem_item(db, BENH_NHAN, "hop-chia-thuoc-thong-minh")
    db.commit()

    assert ket_qua["sp_spent"] == 10_000
    tom_tat = reward_ledger.get_summary(db, BENH_NHAN)
    assert tom_tat["spendable_points"] == 50_000
    assert tom_tat["lifetime_points"] == 60_000
    assert tom_tat["rank"] == catalog.DIAMOND


def test_doi_qua_chua_du_rank_bi_tu_choi(db: Session) -> None:
    """Du thua diem nhung chua dat Rank thi van khong doi duoc."""
    _dat_diem(db, lifetime=0, spendable=500_000)

    with pytest.raises(reward_ledger.RewardError) as exc:
        reward_ledger.redeem_item(db, BENH_NHAN, "goi-kham-tong-quat-co-ban")
    assert exc.value.http_status == 403


def test_doi_qua_thieu_diem_bi_tu_choi(db: Session) -> None:
    _dat_diem(db, lifetime=10_000, spendable=1_000)

    with pytest.raises(reward_ledger.RewardError) as exc:
        reward_ledger.redeem_item(db, BENH_NHAN, "hop-chia-thuoc-thong-minh")
    assert exc.value.http_status == 400


def test_khong_doi_trung_mot_mon(db: Session) -> None:
    _dat_diem(db, lifetime=60_000, spendable=60_000)

    reward_ledger.redeem_item(db, BENH_NHAN, "hop-chia-thuoc-thong-minh")
    db.commit()

    with pytest.raises(reward_ledger.RewardError) as exc:
        reward_ledger.redeem_item(db, BENH_NHAN, "hop-chia-thuoc-thong-minh")
    assert exc.value.http_status == 409


def test_doi_nhieu_mon_khac_nhau_trong_cung_ngay(db: Session) -> None:
    """REDEEM khong dinh rang buoc 1-lan/ngay - doi 2 mon khac nhau cung
    ngay phai duoc (day la ly do occurred_on cua REDEEM de NULL)."""
    _dat_diem(db, lifetime=60_000, spendable=60_000)

    reward_ledger.redeem_item(db, BENH_NHAN, "hop-chia-thuoc-thong-minh")
    db.commit()
    reward_ledger.redeem_item(db, BENH_NHAN, "binh-nuoc-giu-nhiet-wellness")
    db.commit()

    assert reward_ledger.get_summary(db, BENH_NHAN)["spendable_points"] == 40_000


def test_doi_mon_khong_ton_tai(db: Session) -> None:
    _dat_diem(db, lifetime=60_000, spendable=60_000)

    with pytest.raises(reward_ledger.RewardError) as exc:
        reward_ledger.redeem_item(db, BENH_NHAN, "mon-khong-co-that")
    assert exc.value.http_status == 404


# --- Catalog ----------------------------------------------------------------


def test_catalog_danh_dau_dung_trang_thai_tung_mon(db: Session) -> None:
    # Rank Bac (10.000 LP) + 26.000 SP: mo khoa duoc mon Dong/Bac, du tien
    # cho voucher nha khoa (25.000) nhung chua du cho tu van dinh duong
    # (30.000), va hoan toan chua mo khoa mon Vang/Kim Cuong.
    _dat_diem(db, lifetime=10_000, spendable=26_000)

    theo_id = {m["id"]: m for m in reward_ledger.list_catalog_for_patient(db, BENH_NHAN)}

    assert theo_id["hop-chia-thuoc-thong-minh"]["unlocked"] is True
    assert theo_id["voucher-nha-khoa-tham-my"]["unlocked"] is True
    assert theo_id["voucher-nha-khoa-tham-my"]["affordable"] is True
    assert theo_id["tu-van-dinh-duong-1-1"]["unlocked"] is True
    assert theo_id["tu-van-dinh-duong-1-1"]["affordable"] is False
    assert theo_id["may-do-huyet-ap-tu-dong"]["unlocked"] is False
    assert theo_id["goi-kham-tong-quat-co-ban"]["unlocked"] is False


def test_catalog_danh_dau_mon_da_doi(db: Session) -> None:
    _dat_diem(db, lifetime=10_000, spendable=30_000)
    reward_ledger.redeem_item(db, BENH_NHAN, "hop-chia-thuoc-thong-minh")
    db.commit()

    theo_id = {m["id"]: m for m in reward_ledger.list_catalog_for_patient(db, BENH_NHAN)}
    assert theo_id["hop-chia-thuoc-thong-minh"]["already_redeemed"] is True
    assert theo_id["binh-nuoc-giu-nhiet-wellness"]["already_redeemed"] is False


def test_catalog_du_10_mon_va_id_khong_trung(db: Session) -> None:
    ids = [m.id for m in catalog.CATALOG]
    assert len(ids) == 10
    assert len(set(ids)) == 10


# --- Lich su ----------------------------------------------------------------


def test_lich_su_ghi_ca_diem_cong_va_diem_tru(db: Session) -> None:
    _dat_diem(db, lifetime=10_000, spendable=10_000)
    reward_ledger.award_daily_survey(db, BENH_NHAN, NGAY)
    reward_ledger.redeem_item(db, BENH_NHAN, "hop-chia-thuoc-thong-minh")
    db.commit()

    lich_su = reward_ledger.list_history(db, BENH_NHAN)
    loai = {d["event_type"] for d in lich_su}
    assert catalog.EVENT_DAILY_SURVEY in loai
    assert catalog.EVENT_REDEEM in loai

    doi_qua = next(d for d in lich_su if d["event_type"] == catalog.EVENT_REDEEM)
    assert doi_qua["points_delta"] == -10_000
    assert "Hộp chia thuốc thông minh" in doi_qua["label"]


# --- Tru diem theo cach xac nhan (yeu cau nhom truong 2026-08-28) ------------


def _phat(db: Session, dose_event_id: str, pct: int, ngay: date = NGAY) -> int:
    return reward_ledger.apply_confirmation_method_penalty(
        db, patient_id=BENH_NHAN, dose_event_id=dose_event_id, occurred_on=ngay, pct=pct
    )


def test_tru_diem_dung_ty_le_va_tra_ve_so_da_tru(db: Session) -> None:
    _them_lieu(db, status="TAKEN")
    tru = _phat(db, "dose-1", catalog.PCT_SELF_REPORT_NO_PHOTO)
    db.commit()

    assert tru == 10  # -50% cua tran 20 diem, ngay chi co 1 lieu
    so = db.get(PatientRewardAccount, BENH_NHAN)
    assert so.spendable_points == -10
    # Rank KHONG duoc tut vi mot lan tu khai - lifetime_points chi tang khi
    # duoc thuong (xem _award), giong het co che doi qua.
    assert so.lifetime_points == 0


def test_khong_tru_khi_giu_nguyen_100_phan_tram(db: Session) -> None:
    _them_lieu(db, status="TAKEN")
    assert _phat(db, "dose-1", 100) == 0
    db.commit()
    assert db.query(PatientRewardEvent).count() == 0


def test_khong_tru_khi_ngay_do_khong_co_lieu_nao(db: Session) -> None:
    """Khong co lieu thi khong co diem de tru - va tuyet doi khong duoc chia
    cho 0 khi tinh phan diem moi lieu."""
    assert _phat(db, "dose-1", catalog.PCT_SELF_REPORT_NO_PHOTO) == 0
    db.commit()
    assert db.query(PatientRewardEvent).count() == 0


def test_moi_lieu_chi_bi_tru_dung_mot_lan(db: Session) -> None:
    """Job xac minh anh co the chay lai, nguoi than co the bam duyet hai lan."""
    _them_lieu(db, status="TAKEN")
    lan_dau = _phat(db, "dose-1", catalog.PCT_SELF_REPORT_NO_PHOTO)
    lan_hai = _phat(db, "dose-1", catalog.PCT_SELF_REPORT_NO_PHOTO)
    db.commit()

    assert (lan_dau, lan_hai) == (10, 0)
    assert db.query(PatientRewardEvent).count() == 1
    assert db.get(PatientRewardAccount, BENH_NHAN).spendable_points == -10


@pytest.mark.parametrize("so_lieu", [1, 2, 3, 4, 5, 6, 7, 8])
@pytest.mark.parametrize(
    "pct,ty_le_giu",
    [
        (catalog.PCT_CAREGIVER_APPROVED_AFTER_PHOTO_FAIL, 0.9),
        (catalog.PCT_NO_CAREGIVER_APPROVED_AFTER_PHOTO_FAIL, 0.7),
        (catalog.PCT_SELF_REPORT_NO_PHOTO, 0.5),
    ],
)
def test_ty_le_dung_chinh_xac_voi_moi_so_lieu_trong_ngay(
    db: Session, so_lieu: int, pct: int, ty_le_giu: float
) -> None:
    """Chong hoi quy cho bug lam tron (migration 0062).

    Truoc khi sua, khoan tru duoc lam tron RIENG tung lieu. Vi tran 20 diem
    chia cho n lieu nen tu n=4 moi lieu chi con <= 5 diem, va muc -10% ra
    round(0.5) = 0 - ca bac chinh sach do khong tru gi. Sai ca chieu nguoc
    lai: n=7 muc -50% thanh -65%. Test nay ep dung so cho MOI n tu 1 den 8.
    """
    for i in range(so_lieu):
        _them_lieu(db, status="TAKEN", gio_vn=6 + i)
    for i in range(so_lieu):
        reward_ledger.award_dose_on_time(db, BENH_NHAN, NGAY)
        _phat(db, f"dose-{i}", pct)
    db.commit()

    thuc_nhan = db.get(PatientRewardAccount, BENH_NHAN).spendable_points
    assert thuc_nhan == round(catalog.POINTS_DOSE_ON_TIME * ty_le_giu)


def test_tron_nhieu_cach_xac_nhan_trong_cung_mot_ngay(db: Session) -> None:
    """2 lieu chup anh dung (khong phat) + 2 lieu tu khai (-50%): chi mat mot
    nua phan cua 2 lieu sau, khong dung toi phan cua 2 lieu dau."""
    for i in range(4):
        _them_lieu(db, status="TAKEN", gio_vn=6 + i)
    for i in range(4):
        reward_ledger.award_dose_on_time(db, BENH_NHAN, NGAY)
        if i >= 2:
            _phat(db, f"dose-{i}", catalog.PCT_SELF_REPORT_NO_PHOTO)
    db.commit()

    # 4 lieu -> moi lieu 5 diem; 2 lieu bi tru 50% = mat 5 diem tren tong 20.
    assert db.get(PatientRewardAccount, BENH_NHAN).spendable_points == 15


def test_tru_diem_khong_dung_toi_dong_diem_uong_thuoc(db: Session) -> None:
    """Khoan tru phai la DONG RIENG. Neu gop vao dong DOSE_ON_TIME thi lieu
    tiep theo trong ngay se tu dong bu lai phan da tru (award_dose_on_time
    tinh muc tieu tich luy round(20*k/n)) - khoan phat bien mat."""
    _them_lieu(db, status="TAKEN")
    goc = reward_ledger.award_dose_on_time(db, BENH_NHAN, NGAY)
    _phat(db, "dose-1", catalog.PCT_SELF_REPORT_NO_PHOTO)
    db.commit()

    loai = [d.event_type for d in db.query(PatientRewardEvent).all()]
    assert loai.count(catalog.EVENT_DOSE_ON_TIME) == 1
    assert loai.count(catalog.EVENT_DOSE_METHOD_PENALTY) == 1
    dong_goc = db.query(PatientRewardEvent).filter_by(event_type=catalog.EVENT_DOSE_ON_TIME).one()
    assert dong_goc.points_delta == goc  # dong goc GIU NGUYEN, khong bi sua
