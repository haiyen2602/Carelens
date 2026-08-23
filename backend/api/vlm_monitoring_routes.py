"""Admin Monitoring cho pipeline VLM (dem thuoc trong anh + doi chieu don
thuoc, backend/services/photo_verification/). THEM 2026-08-22.

Tach RIENG khoi backend/api/rag_monitoring_routes.py (RAG chatbot, viec cua
thanh vien khac - KHONG dung chung endpoint/nguon du lieu). Khac RAG (phai
fallback qua AuditLog vi khong co bang rieng), VLM da co san bang
`photo_verification` (1 dong = 1 lan chup, xem backend/db/models.py) nen dung
truc tiep lam nguon chinh cho lich su/trend - chi buffer in-memory
(vlm_telemetry.py) moi can cho latency (chua persist vao DB, xem ghi chu
trong plan/PR ve pham vi MVP)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from backend.api.security import CurrentUser, require_role
from backend.config import get_settings
from backend.db.base import get_db
from backend.db.models import DoseEvent, Escalation, PhotoVerification
from backend.services.escalation import TRIGGER_PHOTO_MISMATCH
from backend.services.photo_verification.matcher import KetQua
from backend.services.photo_verification.verifier import TRANG_THAI_LOI_HE_THONG
from backend.services.vlm_telemetry import get_vlm_local_traces, get_vlm_telemetry_service

vlm_monitoring_router = APIRouter(prefix="/admin/vlm", tags=["admin-vlm-monitoring"])

_CONFIDENCE_SCORE = {"cao": 1.0, "trung_binh": 0.5, "thap": 0.0}

# Du lieu o day gan voi tung benh nhan cu the (patient_id, ket qua doi chieu
# thuoc) - khong phai so lieu tong hop vo danh nhu RAG. Ban dau copy dung
# pattern "chi can dang nhap" cua rag_monitoring_routes.py TRUOC KHI no duoc
# BUILD-29 vá lai thanh require_role("admin") that su (xem comment cua ho,
# report 54-build-25-agent-v2-monitoring-audit.md muc 8: "_require_admin
# khong co role check that - bat ky JWT nao, role nao, doc duoc /admin/rag/*")
# - o day vá luon tu dau, khong lap lai lo hong da biet.
_require_admin = require_role("admin")


@vlm_monitoring_router.get("/health")
async def get_vlm_health(
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(_require_admin),
) -> dict[str, Any]:
    """KPI + trend 7 ngay, tinh THANG tu bang photo_verification (da persist
    moi lan chup that, khong can fallback nhu RAG).

    THEM 2026-08-23 (code review): endpoint nay duoc dashboard admin poll moi
    10s (xem frontend/src/app/admin/rag/vlm/page.tsx). Ban dau fetch toi 2000
    dong ORM day du (ke ca 2 cot JSON expected_by_form/detected_by_form) roi
    cong bang Python, cong them 1 truy van Escalation KHONG gioi han - cang
    ve sau bang cang lon thi endpoint nay cang cham. Doi sang SQL aggregate
    (COUNT/SUM CASE WHEN) cho KPI va Escalation, chi con fetch hang that cho
    trend 7 ngay (da gioi han theo thoi gian + chi lay 3 cot can dung, khong
    con cap cung 2000 dong nhu truoc).
    """
    settings = get_settings()
    telemetry = get_vlm_telemetry_service()

    agg = db.execute(
        select(
            func.count().label("total"),
            func.sum(case((PhotoVerification.ket_qua == KetQua.KHOP.value, 1), else_=0)).label("matched"),
            func.sum(case((PhotoVerification.ket_qua == KetQua.LECH.value, 1), else_=0)).label("mismatched"),
            func.sum(case((PhotoVerification.ket_qua == TRANG_THAI_LOI_HE_THONG, 1), else_=0)).label("errors"),
            func.sum(case((PhotoVerification.attempt > 1, 1), else_=0)).label("retaken"),
            func.sum(case((PhotoVerification.confidence == "cao", 1), else_=0)).label("conf_cao"),
            func.sum(case((PhotoVerification.confidence == "trung_binh", 1), else_=0)).label("conf_trung_binh"),
            func.sum(case((PhotoVerification.confidence == "thap", 1), else_=0)).label("conf_thap"),
        )
    ).one()
    total = agg.total or 0
    matched = agg.matched or 0
    mismatched = agg.mismatched or 0
    errors = agg.errors or 0
    retaken = agg.retaken or 0
    n_conf = (agg.conf_cao or 0) + (agg.conf_trung_binh or 0) + (agg.conf_thap or 0)
    avg_confidence = ((agg.conf_cao or 0) * 1.0 + (agg.conf_trung_binh or 0) * 0.5) / n_conf if n_conf else 0.0

    caregiver_review_count = db.execute(
        select(func.count()).select_from(Escalation).where(Escalation.trigger == TRIGGER_PHOTO_MISMATCH)
    ).scalar_one()

    # Ground truth THAT lay MIEN PHI tu chinh luong nghiep vu da co (THEM
    # 2026-08-22, khong can gan nhan/model thu 2): khi model bao "lech" 3 lan,
    # dose_event chuyen AWAITING_CAREGIVER va nguoi than tu xem anh roi dat
    # lai status that (PATCH /doses/{id}, backend/api/dose_routes.py:141).
    # Nguoi than dat lai thanh TAKEN/DELAYED = ho bac bo model (that su da
    # uong, model bao "lech" SAI). Dat thanh MISSED = xac nhan model dung.
    # Con AWAITING_CAREGIVER = chua ai xem, khong tinh vao ty le (chua co
    # ket luan). Day la accuracy DO TREN TRAFFIC THAT, cap nhat lien tuc -
    # khac han 1 golden dataset tinh chi do duoc tai 1 thoi diem.
    #
    # GROUP BY status qua JOIN thay vi fetch het Escalation roi fetch het
    # DoseEvent tuong ung (ban dau, THEM 2026-08-23) - dose_event.id la PK
    # nen JOIN + GROUP BY tu dedupe dung dose duoc nhieu escalation tro toi,
    # giu nguyen ngu nghia cua ban Python cu.
    status_counts = dict(
        db.execute(
            select(DoseEvent.status, func.count(func.distinct(DoseEvent.id)))
            .select_from(DoseEvent)
            .join(Escalation, Escalation.dose_event_id == DoseEvent.id)
            .where(Escalation.trigger == TRIGGER_PHOTO_MISMATCH)
            .group_by(DoseEvent.status)
        ).all()
    )
    overridden = status_counts.get("TAKEN", 0) + status_counts.get("DELAYED", 0)
    confirmed = status_counts.get("MISSED", 0)
    resolved = overridden + confirmed
    caregiver_override_rate = round((overridden / resolved) * 100, 1) if resolved else None

    # Buffer in-memory (khong persist DB, xem docstring vlm_telemetry.py) -
    # rong sau moi lan restart backend. None = "chua co lan xac minh nao
    # chay qua tien trinh hien tai" - PHAI phan biet voi 0.0 (se hien nham
    # thanh "toc do tuc thi", cung ly do voi caregiver_override_rate o tren).
    traces = get_vlm_local_traces()
    latencies = [t.duration_ms for t in traces if t.duration_ms > 0]
    avg_latency_ms = round(sum(latencies) / len(latencies), 1) if latencies else None

    # Trend 7 ngay: chi fetch 3 cot can dung (khong ORM day du/JSON columns)
    # va chi trong 7 ngay gan nhat - khong con doc chung voi KPI o tren nua
    # (truoc gio doc lai `rows` da fetch san, nay KPI khong con fetch full
    # rows) nen phai tu truy van rieng.
    now = datetime.now(UTC)
    week_start = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    trend_source = db.execute(
        select(
            PhotoVerification.created_at,
            PhotoVerification.ket_qua,
            PhotoVerification.confidence,
        ).where(PhotoVerification.created_at >= week_start)
    ).all()

    trend = []
    for i in range(6, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        day_str = day_start.strftime("%d/%m")

        day_rows = [r for r in trend_source if r.created_at and day_start <= r.created_at < day_end]
        day_matched = sum(1 for r in day_rows if r.ket_qua == KetQua.KHOP.value)
        day_conf = [_CONFIDENCE_SCORE[r.confidence] for r in day_rows if r.confidence in _CONFIDENCE_SCORE]

        trend.append({
            "date": day_str,
            "match_rate": round((day_matched / len(day_rows)) * 100, 1) if day_rows else 0.0,
            "avg_confidence": round(sum(day_conf) / len(day_conf), 2) if day_conf else 0.0,
            "attempts": len(day_rows),
        })

    status_str = "Healthy"
    if total == 0:
        status_str = "No Data"
    elif (matched / total if total else 0) < 0.80 or (errors / total if total else 0) > 0.05:
        status_str = "Warning"

    return {
        "status": status_str,
        "sample_size": total,
        "kpis": {
            "match_rate": round((matched / total) * 100, 1) if total else 0.0,
            "mismatch_rate": round((mismatched / total) * 100, 1) if total else 0.0,
            "error_rate": round((errors / total) * 100, 1) if total else 0.0,
            "retake_rate": round((retaken / total) * 100, 1) if total else 0.0,
            "caregiver_review_count": caregiver_review_count,
            # None = chua co ca nao duoc nguoi than xem xong (resolved=0) -
            # PHAI phan biet voi 0% (nguoi than luon dung y model), khong
            # duoc mac dinh ve 0 roi hien nham "model chua bi bac bo lan nao".
            "caregiver_override_rate": caregiver_override_rate,
            "caregiver_override_count": overridden,
            "caregiver_override_resolved_count": resolved,
            "avg_confidence": round(avg_confidence, 2),
            "avg_latency_ms": avg_latency_ms,
        },
        "trend": trend,
        # Trang thai ket noi GHI (backend -> Langfuse Cloud) THAT cho pipeline
        # VLM - project/key hoan toan rieng voi RAG chatbot (settings.langfuse_*).
        "langfuse": {
            "connected": telemetry.is_langfuse_connected(),
            "host": settings.vlm_langfuse_host,
        },
    }


@vlm_monitoring_router.get("/attempts")
async def get_vlm_attempts(
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(_require_admin),
    ket_qua: str | None = Query(default=None, description="khop | lech | khong_xac_minh_duoc | loi_he_thong"),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[dict[str, Any]]:
    """Danh sach cac lan xac minh gan nhat, doc THANG tu photo_verification -
    khong can buffer/fallback vi moi lan chup da la 1 dong that trong DB."""
    stmt = select(PhotoVerification).order_by(PhotoVerification.created_at.desc()).limit(limit)
    if ket_qua:
        stmt = stmt.where(PhotoVerification.ket_qua == ket_qua)

    rows = db.execute(stmt).scalars().all()
    return [
        {
            "id": r.id,
            "dose_event_id": r.dose_event_id,
            "patient_id": r.patient_id,
            "attempt": r.attempt,
            "ket_qua": r.ket_qua,
            "confidence": r.confidence,
            "ghi_chu": r.ghi_chu,
            "thong_bao": r.thong_bao,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
