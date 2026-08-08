"""1 diem DUY NHAT cho hanh dong "escalate khan cap" (HIGH/ESC, muc 8) - CA
2 nguon kich hoat HIGH deu PHAI goi qua day, khong duoc code rieng 2 lan:
  1. safety_layer redflag (muc 7, ADR-0009) - src/agents/orchestrator.py
  2. SEVERITY -> LEVEL = "Nguy hiểm" (FEAT-007, muc 8) -
     src/agents/nodes/dose_confirmation_nodes.py

Ly do gop: muc 8 flowchart ve CA HAI duong deu hoi tu ve chung 1 node
HIGH/ESC. Neu code 2 lan rieng, sau nay sua noi dung overlay cap cuu (muc 10
#5 con [CAN CHOT] - PM + Pham Thanh Dat chua quyet) o 1 cho ma quen cho kia,
2 duong se troi lech nhau ma khong co gi bao (phat hien 2026-08-08, code
review Phase 5b)."""

from __future__ import annotations

import asyncio
from typing import Protocol

# TODO [CẦN CHỐT — chatbot-rag-design.md muc 10 #5]: day la PLACEHOLDER, KHONG
# PHAI noi dung da duyet. Muc 10 #5 ghi ro noi dung overlay cho nhom redflag
# "nguy co lieu dung bat thuong" (BR-6.7/6.8) can PM + Pham Thanh Dat quyet -
# build-kickoff-prompt.md muc 5 noi ro dung vao [CAN CHOT] phai dung lai hoi,
# khong tu chon. Cau chu duoi day chi de PIPELINE CHAY DUOC HET-TO-END VA TEST
# DUOC (bao gom Phase 5 orchestrator/dose_confirmation_nodes) - dung DUNG cho
# san xuat/demo that voi benh nhan cho toi khi PM + mentor duyet noi dung that
# (day la man hinh benh nhan nhin thay LUC KHUNG HOANG THAT - cau chu sai cach
# co the gay hoang mang thay vi tran an). Phase 6 (wiring FastAPI that) PHAI
# dung lai o day va xac nhan lai truoc khi cho phep endpoint nhan traffic that.
HIGH_OVERLAY_MESSAGE = (
    "⚠️ Đây có thể là tình huống khẩn cấp. Vui lòng liên hệ cấp cứu 115 ngay. "
    "Người thân và bác sĩ của bạn đã được thông báo."
)


class EscalateFn(Protocol):
    async def __call__(
        self, target: str, patient_id: str, dose_event_id: str | None, severity: str, urgent: bool
    ) -> None: ...


async def trigger_emergency_escalation(
    escalate_fn: EscalateFn,
    patient_id: str,
    dose_event_id: str | None,
    severity: str = "Nguy hiểm",
    urgent: bool = True,
) -> None:
    """Goi `escalate_fn` cho CA family LAN doctor SONG SONG qua
    `asyncio.gather` (BR-3.5: "khong xep hang cho nguoi than xu ly truoc" -
    gui thang ca 2). Dung chung cho CA 2 nguon kich hoat HIGH o tren."""
    await asyncio.gather(
        escalate_fn("family", patient_id, dose_event_id, severity, urgent),
        escalate_fn("doctor", patient_id, dose_event_id, severity, urgent),
    )
