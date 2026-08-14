"""Vong 2, muc 13 (chatbot-rag-design.md) - APScheduler wiring cho co che
nhac lai escalation. Tach RIENG khoi escalation_reminder.py (logic thuan +
quet DB) - module nay CHI lo phan "chay dinh ky that", de escalation_
reminder.py test duoc hoan toan khong can APScheduler.

**SQLAlchemyJobStore, KHONG dung in-memory jobstore mac dinh** - quyet dinh
2026-08-09 (chatbot-rag-design.md muc 13): chatbot sap tich hop vao app that,
nhieu kha nang chay nhieu worker process (`uvicorn --workers N` hoac nhieu
replica). In-memory jobstore khien MOI worker tu chay 1 scheduler rieng,
cung 1 escalation se bi nhac lai NHIEU LAN trung nhau (moi worker gui 1
lan). SQLAlchemyJobStore luu job vao CHINH Postgres dang co (dung chung
`engine` voi app, khong tao pool rieng) - APScheduler tu dam bao chi 1
worker thuc su chay job tai 1 thoi diem qua co che lock cua jobstore."""

from __future__ import annotations

import logging

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.config import get_settings
from backend.db.base import SessionLocal, engine
from backend.services.classification import summarize_hourly_conversation
from backend.services.escalation_reminder import check_and_send_reminders
from backend.services.hourly_conversation_summary import create_completed_hour_summaries

logger = logging.getLogger("escalation_scheduler")

_scheduler: AsyncIOScheduler | None = None


async def _run_reminder_check() -> None:
    """1 session/lan chay (khong dung chung 1 session dai han giua cac lan
    chay dinh ky) - cung idiom voi get_db() FastAPI dependency."""
    db = SessionLocal()
    try:
        reminded = await check_and_send_reminders(db)
        if reminded:
            logger.info("Da nhac lai %d escalation", reminded)
    except Exception:  # noqa: BLE001 - 1 lan chay job loi khong duoc lam scheduler dung han
        logger.exception("Loi khi chay escalation reminder check job")
    finally:
        db.close()


async def _run_hourly_summary() -> None:
    db = SessionLocal()
    try:
        created = await create_completed_hour_summaries(db, summarize_hourly_conversation)
        if created:
            logger.info("Da tao %d hourly conversation summaries", created)
    except Exception:  # noqa: BLE001 - a failed summary run must not stop other jobs
        logger.exception("Loi khi chay hourly conversation summary job")
    finally:
        db.close()


def start_escalation_scheduler() -> AsyncIOScheduler:
    """Goi trong FastAPI lifespan (src/main.py) luc app khoi dong. Idempotent
    - goi nhieu lan chi tao scheduler 1 lan (vd test import lai module)."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    settings = get_settings()
    jobstores = {"default": SQLAlchemyJobStore(engine=engine)}
    _scheduler = AsyncIOScheduler(jobstores=jobstores)
    _scheduler.add_job(
        _run_reminder_check,
        "interval",
        seconds=settings.escalation_reminder_check_interval_seconds,
        id="escalation_reminder_check",
        replace_existing=True,
        max_instances=1,  # tranh 2 lan chay chong nhau neu 1 lan chay lau hon interval
    )
    _scheduler.add_job(
        _run_hourly_summary,
        "cron",
        minute=0,
        id="hourly_conversation_summary",
        replace_existing=True,
        max_instances=1,
    )
    _scheduler.start()
    logger.info(
        "Escalation reminder scheduler da khoi dong (interval=%ss)",
        settings.escalation_reminder_check_interval_seconds,
    )
    return _scheduler


def stop_escalation_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
