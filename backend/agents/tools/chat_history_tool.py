"""Vong 3, muc 7 (chatbot-rag-design.md) - 3 nhom chuc nang TACH BIET, dung
2 co che khac nhau (muc 7 gioi thieu, doc lai truoc khi sua o day):

  1. save_chat_message() / get_chat_history_for_display() - luu/doc LICH SU
     DAY DU (muc 7.1), CHI dung de hien thi lai cho benh nhan xem, KHONG BAO
     GIO dua vao LLM.
  2. get_recent_context() - CUA SO NGAN HAN 15 phut (muc 7.2), dua vao
     classify_intent/generate_answer (xem conversation_nodes.py). THAY THE
     HOAN TOAN thiet ke last_discussed_drug_id cu (khong con dung).
  3. search_chat_history() - tra cuu DAI HAN THEO YEU CAU (muc 7.3(a)),
     CHI chay khi intent=="chat_history_query" - KHONG BAO GIO tu dong bom
     vao moi cau tra loi (khac han (2), muc dich khac nhau ro rang).

CA 3 deu BAT BUOC loc theo patient_id truyen vao (cung nguyen tac isolation
da ap dung xuyen suot personal_tools.py tu Phase 5b)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import ChatMessage, HourlyConversationSummary

# Muc 7.2 - "Da chot: 15 phut" (kickoff-prompt-vong-3.md), tieu chi thoi gian
# THUAN, khong gioi han them theo so luong tin nhan.
CONTEXT_WINDOW_MINUTES = 15


def save_chat_message(db: Session, patient_id: str, role: str, content: str) -> None:
    """role: "patient" | "assistant". Goi 2 lan/luot chat that (1 cho
    utterance benh nhan, 1 cho response) - xem chat_routes.py."""
    db.add(ChatMessage(patient_id=patient_id, role=role, content=content))
    db.commit()


def get_chat_history_for_display(db: Session, patient_id: str, include_hidden: bool = False) -> list[dict]:
    """Muc 7.1 - CHI dung de hien thi, khong dua vao LLM. Mac dinh loai tin
    nhan da bi an (hidden=True, #20) - `include_hidden` chi dung cho tang
    bac si/doi ky thuat neu sau nay can (hien tai khong co UI nao goi True)."""
    stmt = select(ChatMessage).where(ChatMessage.patient_id == patient_id)
    if not include_hidden:
        stmt = stmt.where(ChatMessage.hidden.is_(False))
    rows = db.execute(stmt.order_by(ChatMessage.created_at)).scalars().all()
    return [
        {"id": r.id, "role": r.role, "content": r.content, "created_at": r.created_at.isoformat(), "hidden": r.hidden}
        for r in rows
    ]


def hide_all_chat_messages(db: Session, patient_id: str) -> int:
    """#20 - "xoa doan chat" = an khoi man hinh (soft-delete), audit_log
    KHONG doi. Tra ve so dong bi anh huong (0 neu khong co gi de an)."""
    stmt = select(ChatMessage).where(ChatMessage.patient_id == patient_id, ChatMessage.hidden.is_(False))
    rows = db.execute(stmt).scalars().all()
    for r in rows:
        r.hidden = True
    summaries = db.execute(
        select(HourlyConversationSummary).where(
            HourlyConversationSummary.patient_id == patient_id,
            HourlyConversationSummary.hidden.is_(False),
        )
    ).scalars().all()
    for summary in summaries:
        summary.hidden = True
    db.commit()
    return len(rows)


def get_hourly_summaries_for_history(db: Session, patient_id: str, limit: int = 5) -> list[dict]:
    """Nguon history dai han uu tien theo Vong 4; khong dung cho context 15 phut."""
    rows = (
        db.execute(
            select(HourlyConversationSummary)
            .where(
                HourlyConversationSummary.patient_id == patient_id,
                HourlyConversationSummary.hidden.is_(False),
            )
            .order_by(HourlyConversationSummary.hour_bucket.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        {
            "hour_bucket": row.hour_bucket.isoformat(),
            "summary_text": row.summary_text,
            "message_count": row.message_count,
        }
        for row in rows
    ]


def get_recent_context(
    db: Session, patient_id: str, now: datetime | None = None, window_minutes: int = CONTEXT_WINDOW_MINUTES
) -> list[dict]:
    """Muc 7.2 - cua so ngu canh NGAN HAN, tinh TUYET DOI tu `now` lui lai
    `window_minutes` phut (khong phai dem so tin nhan). `now` injectable cho
    test (giong pattern da dung o escalation_reminder.py::check_and_send_
    reminders(), khong test theo dong ho he thong that).

    Loai tru tin nhan DA BI AN (hidden=True) - quyet dinh thiet ke: benh
    nhan "xoa" 1 doan chat hop ly ky vong ca 2 y (khong chi khong hien thi
    nua, ma cung khong con duoc dung ngam de tra loi cau hoi sau) - #20 chi
    noi ro chinh sach hien thi/audit, KHONG noi ro anh huong ngu canh, day
    la lua chon AN TOAN HON theo huong nguoi dung mong doi, ghi ro de khong
    ai tuong nham day la hanh vi ngau nhien."""
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(minutes=window_minutes)
    stmt = (
        select(ChatMessage)
        .where(
            ChatMessage.patient_id == patient_id,
            ChatMessage.created_at >= cutoff,
            ChatMessage.created_at <= now,
            ChatMessage.hidden.is_(False),
        )
        .order_by(ChatMessage.created_at)
    )
    rows = db.execute(stmt).scalars().all()
    return [{"role": r.role, "content": r.content} for r in rows]


def search_chat_history(db: Session, patient_id: str, query: str, limit: int = 5) -> list[dict]:
    """Muc 7.3(a) - tra cuu lich su THEO YEU CAU (intent=="chat_history_query"
    CHI), giong RAG nhung KHONG phai "luon nho". Pham vi NHO (1 benh nhan),
    KHONG can vector search phuc tap nhu RAG thuoc (dung y kickoff) - lexical
    don gian (ILIKE substring, khong phan biet hoa/thuong/dau) + uu tien tin
    nhan GAN DAY nhat, du dung cho pham vi "tim lai tin nhan cu cua chinh
    minh". Chi tim trong tin nhan CHUA bi an (hidden=False) - benh nhan da
    "xoa" 1 doan thi khong con tim lai duoc qua duong nay nua, dung tinh
    than #20 (an = coi nhu khong con, khong phai chi an 1 nua)."""
    like_pattern = f"%{query.strip()}%"
    stmt = (
        select(ChatMessage)
        .where(
            ChatMessage.patient_id == patient_id,
            ChatMessage.hidden.is_(False),
            ChatMessage.content.ilike(like_pattern),
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    rows = db.execute(stmt).scalars().all()
    return [{"role": r.role, "content": r.content, "created_at": r.created_at.isoformat()} for r in rows]
