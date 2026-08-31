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
from pathlib import Path

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.config import get_settings
from backend.db.base import SessionLocal, engine
from backend.services.agent_judge_worker import process_pending_judge_batch
from backend.services.classification import summarize_hourly_conversation
from backend.services.doctor_takeover_timeout import close_inactive_takeovers
from backend.services.dose_push_reminder import quet_va_day_nhac
from backend.services.drug_image_chat import cleanup_expired_takeover_uploads
from backend.services.escalation_reminder import check_and_send_reminders
from backend.services.hourly_conversation_summary import create_completed_hour_summaries
from backend.services.photo_cleanup import xoa_anh_het_han
from backend.services.telegram import quet_update_moi

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


async def _run_photo_cleanup() -> None:
    db = SessionLocal()
    try:
        da_xoa = xoa_anh_het_han(db)
        if da_xoa:
            logger.info("Da xoa %d file anh xac nhan lieu qua han", da_xoa)
    except Exception:  # noqa: BLE001 - 1 lan chay job loi khong duoc lam scheduler dung han
        logger.exception("Loi khi chay photo cleanup job")
    finally:
        db.close()


async def _run_drug_image_chat_cleanup() -> None:
    """Remove expired B-07 doctor-only package images even without new uploads."""

    db = SessionLocal()
    try:
        settings = get_settings()
        removed = cleanup_expired_takeover_uploads(
            db,
            storage_dir=Path(settings.drug_image_chat_doctor_storage_dir),
        )
        if removed:
            db.commit()
            logger.info("Removed %d expired private doctor image attachments", removed)
    except Exception:  # noqa: BLE001 - a failed cleanup must not stop the scheduler
        db.rollback()
        logger.exception("Failed B-07 private doctor image cleanup")
    finally:
        db.close()


async def _run_dose_push_reminder() -> None:
    """Quet lieu toi gio roi day Web Push (backend/services/dose_push_reminder.py).

    Dat chung _scheduler co san thay vi tao scheduler thu 2 - de thua huong
    luon SQLAlchemyJobStore: nhieu worker/replica thi APScheduler tu khoa,
    chi 1 noi thuc su chay job, khong day trung nhieu lan (dung ly do da ghi
    trong docstring module nay)."""
    db = SessionLocal()
    try:
        da_nhac = quet_va_day_nhac(db)
        if da_nhac:
            logger.info("Da day push nhac gio uong thuoc cho %d khung gio", da_nhac)
    except Exception:  # noqa: BLE001 - 1 lan chay job loi khong duoc lam scheduler dung han
        logger.exception("Loi khi chay dose push reminder job")
    finally:
        db.close()


async def _run_doctor_takeover_timeout() -> None:
    db = SessionLocal()
    try:
        stopped = close_inactive_takeovers(db)
        if stopped:
            logger.info("Da tu dong dung %d doctor takeover khong hoat dong", stopped)
    except Exception:  # noqa: BLE001 - one failed tick must not stop other jobs
        db.rollback()
        logger.exception("Loi khi quet timeout doctor takeover")
    finally:
        db.close()


async def _run_telegram_updates() -> None:
    """Keo tin benh nhan gui toi bot (chi /start <token> de ghep tai khoan).

    Dat chung _scheduler co san vi dung ly do da ghi o _run_dose_push_reminder:
    SQLAlchemyJobStore dam bao chi 1 worker thuc su chay. Dieu do QUAN TRONG
    hon o job nay - getUpdates la hang doi TIEU THU MOT LAN, hai worker cung
    keo se moi ben nhan mot nua so tin, benh nhan bam /start co the roi vao
    worker khong xu ly."""
    db = SessionLocal()
    try:
        da_ghep = quet_update_moi(db)
        if da_ghep:
            logger.info("Da ghep %d tai khoan Telegram moi", da_ghep)
    except Exception:  # noqa: BLE001 - 1 lan chay job loi khong duoc lam scheduler dung han
        logger.exception("Loi khi chay Telegram update poller")
    finally:
        db.close()


async def _run_judge_worker() -> None:
    """BUILD-33 §4/§14: the only place ``process_pending_judge_batch`` (a
    real Judge LLM call) ever runs -- never inline in the chat request path.
    A no-op tick when ``agent_judge_enabled`` is off, same shape as every
    other flag-gated background job already in this file, so the job is
    always registered (simpler than conditional ``add_job`` calls) but does
    nothing until an operator opts in."""
    settings = get_settings()
    if not settings.agent_judge_enabled:
        return
    db = SessionLocal()
    try:
        processed = process_pending_judge_batch(db, settings=settings)
        if processed:
            logger.info("Da xu ly %d Judge evaluation dang cho", processed)
    except Exception:  # noqa: BLE001 - 1 lan chay job loi khong duoc lam scheduler dung han
        logger.exception("Loi khi chay Judge worker job")
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
    _scheduler.add_job(
        _run_dose_push_reminder,
        "interval",
        seconds=60,
        id="dose_push_reminder",
        replace_existing=True,
        max_instances=1,
    )
    _scheduler.add_job(
        _run_doctor_takeover_timeout,
        "interval",
        seconds=60,
        id="doctor_takeover_timeout",
        replace_existing=True,
        max_instances=1,
    )
    _scheduler.add_job(
        _run_photo_cleanup,
        "cron",
        hour=3,
        minute=0,
        id="photo_cleanup",
        replace_existing=True,
        max_instances=1,
    )
    _scheduler.add_job(
        _run_drug_image_chat_cleanup,
        "cron",
        hour=3,
        minute=10,
        id="drug_image_chat_cleanup",
        replace_existing=True,
        max_instances=1,
    )
    _scheduler.add_job(
        _run_telegram_updates,
        "interval",
        seconds=60,
        id="telegram_updates",
        replace_existing=True,
        max_instances=1,
    )
    _scheduler.add_job(
        _run_judge_worker,
        "interval",
        seconds=settings.agent_judge_poll_interval_seconds,
        id="agent_judge_worker",
        replace_existing=True,
        max_instances=1,  # tranh 2 tick chong nhau neu 1 lan Judge call cham hon interval
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
