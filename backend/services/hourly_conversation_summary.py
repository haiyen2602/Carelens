"""Vong 4, muc 5 - tao tom tat cho benh nhan co chat trong 1 gio da ket thuc."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import ChatMessage, HourlyConversationSummary

logger = logging.getLogger("hourly_conversation_summary")
SummarizeFn = Callable[[list[dict]], str]


def completed_hour_bucket(now: datetime) -> datetime:
    """Tra ve moc bat dau cua gio vua ket thuc, luon theo UTC."""
    now_utc = now.astimezone(UTC)
    current_hour = now_utc.replace(minute=0, second=0, microsecond=0)
    return current_hour - timedelta(hours=1)


def _messages_for_hour(db: Session, patient_id: str, hour_bucket: datetime) -> list[ChatMessage]:
    end = hour_bucket + timedelta(hours=1)
    return (
        db.execute(
            select(ChatMessage)
            .where(
                ChatMessage.patient_id == patient_id,
                ChatMessage.created_at >= hour_bucket,
                ChatMessage.created_at < end,
                ChatMessage.hidden.is_(False),
            )
            .order_by(ChatMessage.created_at)
        )
        .scalars()
        .all()
    )


async def create_completed_hour_summaries(
    db: Session, summarize_fn: SummarizeFn, now: datetime | None = None
) -> int:
    """Tao toi da mot summary/patient cho gio vua ket thuc.

    Chi lay patient co message trong bucket va chua co summary, nen khong tao
    ban ghi rong hay goi LLM vo dieu kien. LLM sync chay trong thread de job
    APScheduler khong chan event loop.
    """
    bucket = completed_hour_bucket(now or datetime.now(UTC))
    end = bucket + timedelta(hours=1)
    patient_ids = db.execute(
        select(ChatMessage.patient_id)
        .where(
            ChatMessage.created_at >= bucket,
            ChatMessage.created_at < end,
            ChatMessage.hidden.is_(False),
        )
        .distinct()
    ).scalars().all()

    created = 0
    for patient_id in patient_ids:
        exists = db.execute(
            select(HourlyConversationSummary.id).where(
                HourlyConversationSummary.patient_id == patient_id,
                HourlyConversationSummary.hour_bucket == bucket,
            )
        ).scalar_one_or_none()
        if exists is not None:
            continue

        messages = _messages_for_hour(db, patient_id, bucket)
        if not messages:
            continue
        payload = [{"role": message.role, "content": message.content} for message in messages]
        try:
            summary_text = (await asyncio.to_thread(summarize_fn, payload)).strip()
        except Exception:  # noqa: BLE001 - one patient must not stop the scheduler
            logger.exception("Khong the tao hourly summary cho patient_id=%s bucket=%s", patient_id, bucket.isoformat())
            continue
        if not summary_text:
            logger.warning("Bo qua hourly summary rong cho patient_id=%s bucket=%s", patient_id, bucket.isoformat())
            continue

        db.add(
            HourlyConversationSummary(
                patient_id=patient_id,
                hour_bucket=bucket,
                summary_text=summary_text,
                message_count=len(messages),
            )
        )
        db.commit()
        created += 1
    return created
