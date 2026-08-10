"""1 diem DUY NHAT cho hanh dong "escalate khan cap" (HIGH/ESC, muc 8) - CA
2 nguon kich hoat HIGH deu PHAI goi qua day, khong duoc code rieng 2 lan:
  1. safety_layer redflag (muc 7, ADR-0009) - src/agents/orchestrator.py
  2. SEVERITY -> LEVEL = "Nguy hiểm" (FEAT-007, muc 8) -
     src/agents/nodes/dose_confirmation_nodes.py

Ly do gop: muc 8 flowchart ve CA HAI duong deu hoi tu ve chung 1 node
HIGH/ESC. Neu code 2 lan rieng, sau nay sua noi dung overlay cap cuu o 1 cho
ma quen cho kia, 2 duong se troi lech nhau ma khong co gi bao (phat hien
2026-08-08, code review Phase 5b). Vong 2 (2026-08-09) tach 1 HIGH_OVERLAY_
MESSAGE chung thanh 5 hang so rieng (xem duoi) - ca cong thuc LAN noi
dung da qua PM + Pham Thanh Dat xac nhan (2026-08-09, xem chatbot-rag-
design.md muc 10 #5), khong con marker CAN CHOT."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.orm import Session

from src.db.models import Escalation
from src.services.severity import SEVERITY_VI_TO_EN

# ĐÃ CHỐT 2026-08-09 (chatbot-rag-design.md muc 10 #5): cong thuc CẢNH BÁO:
# [LOẠI] NGUY HIỂM VA noi dung cu the (kem cau 115/thong bao nguoi than-bac
# si) da qua PM + Pham Thanh Dat xac nhan - KHONG con la placeholder, khong
# con marker CAN CHOT tren ca 5 hang so duoi day.
#
# 5 nguon kich hoat rieng biet (chatbot-rag-design.md muc 7.1) - TRUOC vong 2
# ca 4 duong (chua tinh GENERIC) deu dung chung 1 HIGH_OVERLAY_MESSAGE (da
# retire, xem lich su git) - gio moi nguon co cau rieng, van dung CHUNG cong
# thuc da chot.
OVERDOSE_OVERLAY_MESSAGE = (
    "⚠️ CẢNH BÁO: QUÁ LIỀU NGUY HIỂM. Vui lòng liên hệ cấp cứu 115 ngay. "
    "Người thân và bác sĩ của bạn đã được thông báo."
)
MISSED_DOSE_OVERLAY_MESSAGE = (
    "⚠️ CẢNH BÁO: THIẾU LIỀU NGUY HIỂM. Vui lòng liên hệ cấp cứu 115 ngay. "
    "Người thân và bác sĩ của bạn đã được thông báo."
)
SYMPTOM_OVERLAY_MESSAGE = (
    "⚠️ CẢNH BÁO: TRIỆU CHỨNG NGUY HIỂM. Vui lòng liên hệ cấp cứu 115 ngay. "
    "Người thân và bác sĩ của bạn đã được thông báo."
)
SIDE_EFFECT_OVERLAY_MESSAGE = (
    "⚠️ CẢNH BÁO: TÁC DỤNG PHỤ NGUY HIỂM. Vui lòng liên hệ cấp cứu 115 ngay. "
    "Người thân và bác sĩ của bạn đã được thông báo."
)

# Hang so THU 5 - danh RIENG cho truong hop safety_layer.matched_group=None
# (LLM layer flag redflag nhung KHONG khop keyword group nao, tuc CHINH HE
# THONG cung chua biet day la loai nguy hiem gi - co the khong phai lieu
# dung/trieu chung ma la thu khac hoan toan, vd y dinh tu hai khong lien
# quan toi thuoc). KHONG duoc ep vao 1 trong 4 nhan cu the o tren - gan nham
# nhan (vd "TRIEU CHUNG NGUY HIEM" cho 1 case co the khong phai trieu chung)
# se dua thong tin SAI nhung nghe rat cu the cho nguoi than/bac si nhan canh
# bao, khien ho chuan bi phan ung SAI huong - cung ban chat rui ro voi #17
# (thong tin sai nhung tu tin) da danh nhieu cong dong. Quyet dinh 2026-08-09
# (review vong 2): dung 1 nhan TONG QUAT, khong tuyen bo loai nguy hiem cu
# the, thay vi doan bua vao 1 trong 4 nhan co san. DA CHOT 2026-08-09 cung
# 4 hang so tren (PM + Pham Thanh Dat xac nhan), khong con marker CAN CHOT.
GENERIC_OVERLAY_MESSAGE = (
    "⚠️ CẢNH BÁO: NGUY HIỂM KHẨN CẤP. Vui lòng liên hệ cấp cứu 115 ngay. "
    "Người thân và bác sĩ của bạn đã được thông báo."
)


# trigger ∈ missed_dose | side_effect | safety_redflag | photo_mismatch (api-contracts.md §6)
TRIGGER_SAFETY_REDFLAG = "safety_redflag"
TRIGGER_MISSED_DOSE = "missed_dose"
TRIGGER_SIDE_EFFECT = "side_effect"


class EscalateFn(Protocol):
    async def __call__(
        self,
        target: str,
        patient_id: str,
        dose_event_id: str | None,
        severity: str,
        urgent: bool,
        trigger: str,
        reason: str,
    ) -> None: ...


@dataclass
class EscalationOutcome:
    """Ket qua THAT cua trigger_emergency_escalation() - PHAN BIET ro target
    nao thanh cong/that bai, khong gop chung thanh 1 trang thai tong (phat
    hien 2026-08-08, code review Phase 6): voi escalate CAP CUU, biet CHINH
    XAC kenh nao that bai quan trong hon nhieu so voi RAG - neu bac si
    khong nhan duoc canh bao ma audit log chi ghi chung chung "da escalate",
    khong ai biet de goi lai thu cong."""

    succeeded: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)  # target -> loi (str(exception))

    @property
    def all_succeeded(self) -> bool:
        return not self.failed


async def trigger_emergency_escalation(
    escalate_fn: EscalateFn,
    patient_id: str,
    dose_event_id: str | None,
    severity: str = "Nguy hiểm",
    urgent: bool = True,
    trigger: str = TRIGGER_SAFETY_REDFLAG,
    reason: str = "",
) -> EscalationOutcome:
    """Goi `escalate_fn` cho CA family LAN doctor SONG SONG qua
    `asyncio.gather(..., return_exceptions=True)` (BR-3.5: "khong xep hang
    cho nguoi than xu ly truoc" - gui thang ca 2). Dung chung cho CA 2 nguon
    kich hoat HIGH o tren.

    `return_exceptions=True` la CO Y (phat hien 2026-08-08, code review
    Phase 6): escalate cap cuu can BEST-EFFORT, khong phai ALL-OR-NOTHING -
    1 kenh loi (vd ghi DB that bai cho doctor) KHONG duoc lam MAT luon ket
    qua cua kenh con lai (family) hay lam sap ca request HTTP dang xu ly.
    Nguoi goi (orchestrator.py/dose_confirmation_nodes.py) PHAI doc
    `EscalationOutcome.failed` va ghi vao trace - khong duoc coi
    `escalated_to` la ca 2 target mac dinh.

    `trigger`/`reason` do NGUOI GOI tinh - chi ho moi biet CHINH XAC vi sao
    escalate kich hoat (tu khoa redflag nao, hay classification/severity
    nao) - escalate_fn khong tu suy dien nguoc lai duoc tu severity/urgent
    don thuan (vd urgent=True co the la ca safety_redflag LAN severity=Nguy
    hiem tu SEVERITY node, khong phan biet duoc chi tu 2 co nay)."""
    targets = ["family", "doctor"]
    results = await asyncio.gather(
        *(escalate_fn(t, patient_id, dose_event_id, severity, urgent, trigger, reason) for t in targets),
        return_exceptions=True,
    )
    outcome = EscalationOutcome()
    for target, result in zip(targets, results, strict=True):
        if isinstance(result, BaseException):
            outcome.failed[target] = str(result)
        else:
            outcome.succeeded.append(target)
    return outcome


def build_db_escalate_fn(db: Session) -> EscalateFn:
    """`escalate_fn` ghi THAT vao bang `escalation` (api-contracts.md §6/§8)
    thay vi push/SMS that (chua co ha tang do trong repo nay - xem cau hoi
    da xac nhan voi Architect 2026-08-08: build toi thieu bang that thay vi
    stub log-only). `trigger_emergency_escalation()` goi ham nay 2 LAN qua
    `asyncio.gather` (1 lan/target) cho CUNG 1 su kien escalate - gop lai
    thanh DUNG 1 dong Escalation (notified=["caregiver","doctor"]) thay vi 2
    dong trung lap, bang 1 dict nho trong closure de nho row vua tao o lan
    goi dau.

    GIA DINH KY THUAT (ghi ro vi day la diem de sai sau nay): than ham ben
    duoi la I/O DONG BO (SQLAlchemy Session thuong, khong async driver) -
    KHONG co `await` thuc su nao ben trong. 1 coroutine khong co diem await
    noi bo thi `asyncio.gather()` van chay no CHAY HET TUAN TU (khong xen
    ke that giua 2 task) - nen lan goi 'family' luon INSERT xong TRUOC KHI
    lan goi 'doctor' doc lai `_pending`. Neu sau nay escalate_fn doi sang
    goi API push/SMS THAT (co await/network I/O ben trong), gia dinh nay
    KHONG con dung nua - can dong bo hoa ro rang (vd lock) truoc khi doi."""
    _pending: dict[str, str] = {}  # f"{patient_id}:{dose_event_id}" -> escalation.id

    async def escalate_fn(
        target: str,
        patient_id: str,
        dose_event_id: str | None,
        severity: str,
        urgent: bool,
        trigger: str,
        reason: str,
    ) -> None:
        key = f"{patient_id}:{dose_event_id}"
        notified_target = "caregiver" if target == "family" else target
        severity_en = SEVERITY_VI_TO_EN.get(severity, severity)

        existing_id = _pending.get(key)
        if existing_id is not None:
            row = db.get(Escalation, existing_id)
            if row is not None and notified_target not in row.notified:
                row.notified = [*row.notified, notified_target]
                db.commit()
            return

        now = datetime.now(UTC)
        row = Escalation(
            patient_id=patient_id,
            dose_event_id=dose_event_id,
            severity=severity_en,
            trigger=trigger,
            reason=reason,
            status="OPEN",
            notified=[notified_target],
            reminder_count=1,  # da gui t=0 (chinh lan nay), chua tinh nhac lai
            last_reminder_at=now,
        )
        db.add(row)
        db.commit()
        _pending[key] = row.id

    return escalate_fn
