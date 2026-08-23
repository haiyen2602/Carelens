"""
State machine ADR-0011: nhận một ảnh, đối chiếu, quyết định bước tiếp theo, lưu.

Luồng chia hai nửa vì một lần gọi mô hình mất khá nhiều thời gian (xem
`vlm_bridge.py`) — quá lâu để giữ trong một request HTTP đồng bộ:

    1. `khoi_tao_xac_minh()` — chạy NGAY trong request, tạo dòng
       `photo_verification` ở trạng thái `dang_xu_ly`. Không gọi mô hình.
    2. `hoan_tat_xac_minh()` — chạy NỀN (`BackgroundTasks` của FastAPI, xem
       `backend/api/photo_routes.py`), tự mở `Session` riêng vì session của
       request đã đóng trước khi hàm này chạy xong.

Hai lỗi KHÔNG được tính vào hạn mức 2 lần chụp lại của ADR-0011:
  - liều không xác minh được bằng ảnh (toàn thuốc tiêm...) — chặn ở bước 1,
    không tốn một lượt chụp nào, không gọi mô hình.
  - mô hình lỗi (mất mạng, endpoint hỏng) — không phải lỗi của bệnh nhân, họ
    không được trừ lượt vì hạ tầng của mình chập chờn.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.base import SessionLocal
from backend.db.models import DoseEvent, PhotoVerification
from backend.services.escalation import (
    TRIGGER_PHOTO_MISMATCH,
    build_db_escalate_fn,
    trigger_emergency_escalation,
)
from backend.services.photo_verification.matcher import (
    KetQua,
    doi_chieu_don_thuoc,
    tinh_yeu_cau,
)
from backend.services.photo_verification.vlm_bridge import dem_thuoc_trong_anh
from backend.services.vlm_telemetry import get_vlm_telemetry_service

logger = logging.getLogger(__name__)

# ADR-0011: toi da 2 lan chup lai = tong 3 lan gui.
MAX_ATTEMPTS = 3

NEXT_ACTION_NONE = "NONE"
NEXT_ACTION_RETAKE = "RETAKE"
NEXT_ACTION_CAREGIVER_REVIEW = "CAREGIVER_REVIEW"

# Trạng thái của DÒNG (không phải kết quả đối chiếu) khi còn đang chờ mô hình
# trả lời, hoặc khi mô hình/mạng lỗi. Hai giá trị này KHÔNG nằm trong
# `matcher.KetQua` (chỉ có 3 giá trị: khớp/lệch/không xác minh được) vì chúng
# mô tả trạng thái XỬ LÝ, không phải kết quả NGHIỆP VỤ của việc đối chiếu.
TRANG_THAI_DANG_XU_LY = "dang_xu_ly"
TRANG_THAI_LOI_HE_THONG = "loi_he_thong"
# THEM 2026-08-23, sau khi chay golden set that (eval/eval_vlm/): do_tin_cay
# model tu bao cao TUONG QUAN THAT voi do dung (cao=73%, trung_binh=43%,
# thap=14%) - "thap" gan nhu vo dung, coi nhu loi model chua chac chan chu
# khong phai loi benh nhan, cung tinh than voi TRANG_THAI_LOI_HE_THONG o tren.
TRANG_THAI_DO_TIN_CAY_THAP = "do_tin_cay_thap"

# Gioi han RIENG cho so lan "thap" duoc mien phi (KHONG dung chung MAX_ATTEMPTS
# voi KHOP/LECH) - tranh vong lap vo han neu moi truong chup (anh sang, camera)
# cua benh nhan lien tuc cho ra anh mo, khong bao gio toi duoc caregiver
# review. Qua gioi han nay, lan tiep theo KHONG con duoc mien nua - chay tiep
# xuong so sanh binh thuong, chap nhan ket qua tot nhat hien co (co the
# KHOP/LECH nhu moi lan khac) thay vi hoi mai.
MAX_LAN_DO_TIN_CAY_THAP = 2

_DANG_TAO_LIEU = "Đang phân tích ảnh, việc này có thể mất vài phút — bạn cứ để yên máy, tôi sẽ báo ngay khi xong."


class HanMucVuotQuaError(RuntimeError):
    """Đã hết 2 lần chụp lại (business-rules.md §4) — không nhận thêm ảnh cho
    liều này, đang chờ người thân duyệt."""


class KhongXacMinhDuocError(RuntimeError):
    """Liều này không có thuốc nào xác minh được bằng ảnh (vd toàn thuốc
    tiêm) — không tốn lượt chụp nào, hướng bệnh nhân sang nút bấm xác nhận."""

    def __init__(self, thong_bao: str) -> None:
        super().__init__(thong_bao)
        self.thong_bao = thong_bao


def dem_luot_da_dung(db: Session, dose_event_id: str) -> int:
    """Số lượt ĐÃ THỰC SỰ so sánh được (khớp hoặc lệch) — không tính dòng đang
    xử lý hoặc dòng lỗi hệ thống, đúng tinh thần "không trừ lượt vì hạ tầng
    lỗi" đã nói ở docstring module."""
    dem_duoc = (
        db.execute(
            select(func.count())
            .select_from(PhotoVerification)
            .where(
                PhotoVerification.dose_event_id == dose_event_id,
                PhotoVerification.ket_qua.in_([KetQua.KHOP.value, KetQua.LECH.value]),
            )
        ).scalar_one()
    )
    return int(dem_duoc)


def dem_lan_do_tin_cay_thap(db: Session, dose_event_id: str) -> int:
    """Số lần đã trả về do_tin_cay=thấp cho liều này - đếm RIÊNG với
    dem_luot_da_dung() (chỉ khớp/lệch), cùng lý do đã giải thích ở
    MAX_LAN_DO_TIN_CAY_THAP."""
    dem_duoc = (
        db.execute(
            select(func.count())
            .select_from(PhotoVerification)
            .where(
                PhotoVerification.dose_event_id == dose_event_id,
                PhotoVerification.ket_qua == TRANG_THAI_DO_TIN_CAY_THAP,
            )
        ).scalar_one()
    )
    return int(dem_duoc)


@dataclass(frozen=True)
class XacMinhMoi:
    id: str
    attempt: int
    thong_bao: str


def khoi_tao_xac_minh(db: Session, dose_event: DoseEvent, image_path: str) -> XacMinhMoi:
    """Tạo dòng `photo_verification` ở trạng thái chờ. Không gọi mô hình.

    Ném `HanMucVuotQuaError` nếu đã hết lượt, `KhongXacMinhDuocError` nếu liều
    này không thuộc dạng xác minh được bằng ảnh — cả hai chặn TRƯỚC khi tốn
    thời gian gọi mô hình hay lưu ảnh vào đĩa.
    """
    yeu_cau = tinh_yeu_cau(dose_event.expected_items)
    if not yeu_cau.xac_minh_duoc_bang_anh:
        raise KhongXacMinhDuocError(
            "Liều này không có thuốc nào kiểm tra bằng ảnh được — bạn bấm nút xác nhận giúp tôi nhé."
        )

    so_da_dung = dem_luot_da_dung(db, dose_event.id)
    if so_da_dung >= MAX_ATTEMPTS:
        raise HanMucVuotQuaError(
            f"Liều này đã chụp đủ {MAX_ATTEMPTS} lần, đang chờ người thân xem lại giúp."
        )

    attempt = so_da_dung + 1
    row = PhotoVerification(
        dose_event_id=dose_event.id,
        patient_id=dose_event.patient_id,
        attempt=attempt,
        expected_by_form=dict(yeu_cau.so_luong),
        detected_by_form={},
        ket_qua=TRANG_THAI_DANG_XU_LY,
        confidence=None,
        ghi_chu=None,
        thong_bao=_DANG_TAO_LIEU,
        image_path=image_path,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return XacMinhMoi(id=row.id, attempt=attempt, thong_bao=row.thong_bao)


def xac_dinh_next_action(ket_qua: KetQua, attempt: int) -> str:
    """`next_action` theo api-contracts.md §5 — NONE | RETAKE | CAREGIVER_REVIEW."""
    if ket_qua is KetQua.KHOP:
        return NEXT_ACTION_NONE
    if ket_qua is KetQua.KHONG_XAC_MINH_DUOC:
        # Trên lý thuyết không tới đây (đã chặn ở khoi_tao_xac_minh), giữ lại
        # cho đủ nhánh — an toàn hơn để lọt xuống LECH nếu logic trên đổi sau này.
        return NEXT_ACTION_NONE
    return NEXT_ACTION_RETAKE if attempt < MAX_ATTEMPTS else NEXT_ACTION_CAREGIVER_REVIEW


def hoan_tat_xac_minh(verification_id: str) -> None:
    """Chạy NỀN: gọi mô hình, đối chiếu, cập nhật dòng, escalate nếu hết lượt.

    Tự mở `Session` riêng — session của request HTTP đã đóng trước khi hàm
    này chạy xong (response đã trả về từ lâu). Không bao giờ ném exception ra
    ngoài: đây là một background task của FastAPI, không có ai bắt lỗi.
    """
    db = SessionLocal()
    try:
        _hoan_tat_xac_minh(db, verification_id)
    except Exception:
        logger.exception("Xử lý ảnh %s thất bại ngoài dự kiến.", verification_id)
        _luu_loi_du_phong(db, verification_id)
    finally:
        db.close()


def _hoan_tat_xac_minh(db: Session, verification_id: str) -> None:
    row = db.get(PhotoVerification, verification_id)
    if row is None:
        logger.error("Không tìm thấy photo_verification %s để hoàn tất.", verification_id)
        return

    # Telemetry VLM (THEM 2026-08-22, xem backend/services/vlm_telemetry.py) -
    # HOAN TOAN doc lap voi RAG chatbot (project/key Langfuse rieng). Trace
    # gom ca lan xac minh nay; try/finally dam bao MOI nhanh thoat som (lieu
    # khong ton tai, doc anh loi, VLM loi ha tang, thanh cong) deu finalize
    # duoc 1 trace hoan chinh, khong bo sot nhanh loi nao.
    telemetry = get_vlm_telemetry_service()
    trace = telemetry.create_trace(
        trace_id=verification_id,
        user_id=row.patient_id,
        input_data={"attempt": row.attempt, "expected_by_form": row.expected_by_form},
        metadata={"dose_event_id": row.dose_event_id, "attempt": row.attempt},
    )
    trace_status = "success"

    try:
        dose_event = db.get(DoseEvent, row.dose_event_id)
        if dose_event is None:
            row.ket_qua = TRANG_THAI_LOI_HE_THONG
            row.thong_bao = "Không tìm thấy liều thuốc tương ứng — báo lại cho quản trị viên."
            db.commit()
            trace_status = "error"
            return

        try:
            with open(row.image_path, "rb") as tep:
                anh = tep.read()
        except OSError as exc:
            row.ket_qua = TRANG_THAI_LOI_HE_THONG
            row.thong_bao = "Không đọc lại được ảnh vừa lưu — bạn thử chụp lại giúp tôi nhé."
            logger.error("Không đọc được ảnh %s: %s", row.image_path, exc)
            db.commit()
            trace_status = "error"
            return

        obs_vlm = telemetry.start_observation(
            trace, "vlm.model_call", obs_type="generation", input_data={"attempt": row.attempt}
        )
        ket_qua_vlm = dem_thuoc_trong_anh(anh)
        telemetry.end_observation(
            obs_vlm,
            output_data={"counts": ket_qua_vlm.counts, "do_tin_cay": ket_qua_vlm.do_tin_cay}
            if ket_qua_vlm.ok
            else None,
            level="DEFAULT" if ket_qua_vlm.ok else "ERROR",
            status_message=None if ket_qua_vlm.ok else ket_qua_vlm.error,
        )
        if not ket_qua_vlm.ok:
            # Lỗi hạ tầng, KHÔNG tính vào hạn mức — xem docstring module.
            row.ket_qua = TRANG_THAI_LOI_HE_THONG
            row.thong_bao = "Hệ thống đang bận, chưa phân tích được ảnh. Bạn thử gửi lại giúp tôi nhé."
            row.ghi_chu = ket_qua_vlm.error
            db.commit()
            logger.warning("Gọi VLM thất bại cho %s: %s", verification_id, ket_qua_vlm.error)
            trace_status = "error"
            return

        if (
            ket_qua_vlm.do_tin_cay == "thap"
            and dem_lan_do_tin_cay_thap(db, row.dose_event_id) < MAX_LAN_DO_TIN_CAY_THAP
        ):
            # Model tu bao khong chac chan (14% dung that trong golden set,
            # xem MAX_LAN_DO_TIN_CAY_THAP) - xin chup lai, KHONG tinh vao han
            # muc that (dem_luot_da_dung chi dem KHOP/LECH). Gioi han rieng o
            # tren tranh vong lap vo han neu moi truong chup lien tuc mo.
            row.ket_qua = TRANG_THAI_DO_TIN_CAY_THAP
            row.detected_by_form = dict(ket_qua_vlm.counts)
            row.confidence = ket_qua_vlm.do_tin_cay
            row.ghi_chu = ket_qua_vlm.ghi_chu or None
            row.thong_bao = (
                "Ảnh chưa đủ rõ để xác nhận chắc chắn — bạn chụp lại giúp mình, "
                "cố gắng đủ sáng và không để các viên chồng lên nhau nhé."
            )
            db.commit()
            logger.info("Do tin cay thap cho %s, xin chup lai khong tru luot.", verification_id)
            trace_status = "retry_low_confidence"
            return

        detected = dict(ket_qua_vlm.counts)

        obs_compare = telemetry.start_observation(
            trace,
            "vlm.compare_prescription",
            obs_type="span",
            input_data={"expected": row.expected_by_form, "detected": detected},
        )
        ket_qua_doi_chieu = doi_chieu_don_thuoc(dose_event.expected_items, detected)
        telemetry.end_observation(obs_compare, output_data={"ket_qua": ket_qua_doi_chieu.ket_qua.value})

        telemetry.record_score(trace, "match_result", 1.0 if ket_qua_doi_chieu.khop else 0.0)
        confidence_score = {"cao": 1.0, "trung_binh": 0.5, "thap": 0.0}.get(ket_qua_vlm.do_tin_cay or "", 0.0)
        telemetry.record_score(trace, "vlm_confidence", confidence_score, comment=ket_qua_vlm.do_tin_cay)

        row.detected_by_form = detected
        row.ket_qua = ket_qua_doi_chieu.ket_qua.value
        row.confidence = ket_qua_vlm.do_tin_cay
        row.ghi_chu = ket_qua_vlm.ghi_chu or None
        row.thong_bao = ket_qua_doi_chieu.thong_bao

        next_action = xac_dinh_next_action(ket_qua_doi_chieu.ket_qua, row.attempt)
        trace.metadata["next_action"] = next_action

        if ket_qua_doi_chieu.khop:
            # BR-2.2: xác nhận TRONG cửa sổ -> TAKEN; SAU window_end -> DELAYED,
            # không phải TAKEN. Hệ thống chưa có job quét tự chuyển PENDING quá
            # hạn sang MISSED (ADR-0007, ngoài phạm vi domain này), nên ở đây chỉ
            # so window_end với giờ hiện tại — không phân biệt "trễ trong ngày" với
            # "trễ nhiều ngày", đơn giản hoá có chủ đích vì chưa có gì để so lệch.
            dose_event.status = "TAKEN" if datetime.now(UTC) <= dose_event.window_end else "DELAYED"
        elif next_action == NEXT_ACTION_CAREGIVER_REVIEW:
            dose_event.status = "AWAITING_CAREGIVER"
            _escalate_photo_mismatch(db, dose_event, row)

        db.commit()
        logger.info(
            "Hoàn tất xác minh %s: ket_qua=%s next_action=%s attempt=%d",
            verification_id, row.ket_qua, next_action, row.attempt,
        )
    finally:
        telemetry.finalize_trace(trace, output_data={"ket_qua": row.ket_qua}, status=trace_status)


def _escalate_photo_mismatch(db: Session, dose_event: DoseEvent, row: PhotoVerification) -> None:
    """BR §3 (MEDIUM): ảnh không khớp sau 2 lần -> escalate người thân + bác sĩ.

    Dùng lại `trigger_emergency_escalation`/`build_db_escalate_fn` — 1 điểm
    DUY NHẤT tạo `escalation` trong toàn hệ thống (xem docstring của chúng),
    không tự viết SQL insert riêng ở đây dù tên hàm nghe như chỉ dành cho HIGH:
    `severity` là tham số, không hardcode.
    """
    escalate_fn = build_db_escalate_fn(db)
    reason = f"Ảnh xác nhận liều không khớp đơn thuốc sau {row.attempt} lần chụp. {row.thong_bao}"
    ket_qua = asyncio.run(
        trigger_emergency_escalation(
            escalate_fn,
            patient_id=dose_event.patient_id,
            dose_event_id=dose_event.id,
            severity="Trung bình",
            urgent=False,
            trigger=TRIGGER_PHOTO_MISMATCH,
            reason=reason,
        )
    )
    if not ket_qua.all_succeeded:
        logger.error(
            "Escalate photo_mismatch cho dose_event %s thất bại một phần: %s",
            dose_event.id, ket_qua.failed,
        )


def _luu_loi_du_phong(db: Session, verification_id: str) -> None:
    """Cố gắng ghi lại lỗi vào đúng dòng khi `_hoan_tat_xac_minh` văng exception
    không lường trước — best-effort, không để lỗi ở đây làm chết background task."""
    try:
        row = db.get(PhotoVerification, verification_id)
        if row is not None:
            row.ket_qua = TRANG_THAI_LOI_HE_THONG
            row.thong_bao = "Có lỗi hệ thống khi xử lý ảnh. Bạn thử gửi lại giúp tôi nhé."
            db.commit()
    except Exception:
        logger.exception("Không ghi lại được lỗi dự phòng cho %s.", verification_id)
        db.rollback()


__all__ = [
    "MAX_ATTEMPTS",
    "NEXT_ACTION_CAREGIVER_REVIEW",
    "NEXT_ACTION_NONE",
    "NEXT_ACTION_RETAKE",
    "TRANG_THAI_DANG_XU_LY",
    "TRANG_THAI_LOI_HE_THONG",
    "HanMucVuotQuaError",
    "KhongXacMinhDuocError",
    "XacMinhMoi",
    "dem_luot_da_dung",
    "hoan_tat_xac_minh",
    "khoi_tao_xac_minh",
    "xac_dinh_next_action",
]
