"""Engine B: 48-hour auto-nagging, snooze pings and monthly-deadline escalation.

`run_reminder_cycle` is the single source of truth. It runs every
SCHEDULER_INTERVAL_SECONDS on an APScheduler background thread and can be triggered
on demand (`/api/scheduler/trigger-48h-check`) or after a simulated 48h time jump
(`/api/scheduler/simulate-time-jump`) for live demos.
"""
from __future__ import annotations

import logging
import threading
from datetime import timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal
from models import ChasingTicket, MessageTemplate, MessageType, TemplateCategory, TicketPriority, TicketStatus
from services.activity import log_activity
from services.clock import days_until_deadline, utcnow
from services.events import queue_event
from services.i18n import t
from services.templating import body_for, localized_buttons, render_text
from services.ticket_engine import (
    DEADLINE_SLUG,
    lang_of,
    open_items_count,
    reminder_interval,
    send_outbound,
    template_by_slug,
    touch,
)

log = logging.getLogger("accountflow.scheduler")

CHASE_STATUSES = (TicketStatus.WAITING_FOR_CLIENT, TicketStatus.NEEDS_CORRECTION)
_cycle_lock = threading.Lock()
_scheduler: BackgroundScheduler | None = None


def _reminder_text(ticket: ChasingTicket, lang: str) -> str:
    ctx = ticket.context_variables_json or {}
    kwargs = {**ctx, "n": ticket.reminder_count, "max": ticket.max_reminders, "ticket_ref": ticket.ticket_ref}
    if ticket.status == TicketStatus.NEEDS_CORRECTION:
        return t("reminder_correction", lang, **kwargs)
    category = ticket.template.category
    if ticket.template.slug == DEADLINE_SLUG:
        category = TemplateCategory.MONTHLY_FOLDER
    return t(f"reminder_{category.value}", lang, **kwargs)


def _action(kind: str, ticket: ChasingTicket, text: str = "") -> dict:
    return {
        "kind": kind,
        "ticket_id": ticket.id,
        "ticket_ref": ticket.ticket_ref,
        "client_id": ticket.client_id,
        "client_name": ticket.client.full_name,
        "status": ticket.status.value,
        "priority": ticket.priority.value,
        "reminder_count": ticket.reminder_count,
        "message": text,
    }


def run_reminder_cycle(db: Session, now=None) -> list[dict]:
    now = now or utcnow()
    actions: list[dict] = []

    # 1) Snoozed "remind me tonight" tickets whose 20:00 slot has arrived
    snoozed = db.scalars(
        select(ChasingTicket).where(
            ChasingTicket.status == TicketStatus.SNOOZED_TONIGHT,
            ChasingTicket.next_reminder_at.is_not(None),
            ChasingTicket.next_reminder_at <= now,
        )
    ).all()
    for ticket in snoozed:
        client, lang = ticket.client, lang_of(ticket.client)
        original = render_text(body_for(ticket.template, lang), ticket.context_variables_json or {})
        text = f"{t('snooze_ping', lang, client_name=client.full_name)}\n\n{original}"
        send_outbound(db, client, ticket, text, localized_buttons(ticket.template, lang), MessageType.AUTO_REMINDER)
        ticket.status = TicketStatus.WAITING_FOR_CLIENT
        ticket.next_reminder_at = now + reminder_interval(db)
        touch(db, ticket)
        actions.append(_action("SNOOZE_PING", ticket, text))

    # 2) Regular 48h chase loop
    due = db.scalars(
        select(ChasingTicket)
        .join(MessageTemplate)
        .where(
            ChasingTicket.status.in_(CHASE_STATUSES),
            ChasingTicket.next_reminder_at.is_not(None),
            ChasingTicket.next_reminder_at <= now,
        )
        .order_by(ChasingTicket.client_id, ChasingTicket.next_reminder_at)
    ).all()

    deadline_tpl = template_by_slug(db, DEADLINE_SLUG)
    warned_clients: set[int] = set()

    for ticket in due:
        client, lang = ticket.client, lang_of(ticket.client)

        if ticket.reminder_count >= ticket.max_reminders:
            ticket.status = TicketStatus.ESCALATED
            ticket.next_reminder_at = None
            touch(db, ticket)
            actions.append(_action("ESCALATED", ticket, f"אין תגובה לאחר {ticket.reminder_count} תזכורות — יש להתקשר ללקוח."))
            continue

        ticket.reminder_count += 1
        days_left = days_until_deadline(client.reporting_frequency, now)
        is_tax = ticket.template.category == TemplateCategory.TAX_READY

        if not is_tax and days_left <= settings.urgent_deadline_days:
            ticket.priority = TicketPriority.URGENT_DEADLINE
            ticket.next_reminder_at = now + timedelta(hours=settings.urgent_reminder_interval_hours)
            if client.id in warned_clients:
                ticket.last_contacted_at = now
                touch(db, ticket)
                actions.append(_action("URGENT_GROUPED", ticket, "נכלל בהתראת המועד האחרון שנשלחה ללקוח במחזור זה."))
                continue
            warned_clients.add(client.id)
            variables = {
                "client_name": client.full_name,
                "open_items_count": str(max(1, open_items_count(db, client.id))),
                "days_left": str(days_left),
            }
            text = render_text(body_for(deadline_tpl, lang), variables)
            send_outbound(db, client, ticket, text, localized_buttons(deadline_tpl, lang), MessageType.AUTO_REMINDER)
            touch(db, ticket)
            actions.append(_action("URGENT_DEADLINE_WARNING", ticket, text))
        else:
            text = _reminder_text(ticket, lang)
            send_outbound(db, client, ticket, text, localized_buttons(ticket.template, lang), MessageType.AUTO_REMINDER)
            ticket.next_reminder_at = now + reminder_interval(db)
            touch(db, ticket)
            actions.append(_action("FRIENDLY_REMINDER", ticket, text))

    if actions:
        queue_event(db, {"type": "scheduler", "count": len(actions)})
    return actions


REMINDER_KINDS = {
    "FRIENDLY_REMINDER": "תזכורות ידידותיות",
    "URGENT_DEADLINE_WARNING": "התראות מועד דיווח",
    "SNOOZE_PING": "תזכורות ערב (20:00)",
    "ESCALATED": "פניות שהוסלמו לשיחה",
}


def describe_reminder_actions(actions: list[dict]) -> str:
    """Hebrew summary for the activity log, e.g. "3 תזכורות ידידותיות, 1 התראות מועד דיווח"."""
    parts = []
    for kind, label in REMINDER_KINDS.items():
        n = sum(1 for a in actions if a["kind"] == kind)
        if n:
            parts.append(f"{n} {label}")
    return ", ".join(parts) or "לא היו תזכורות שהגיע מועדן"


def shift_active_tickets(db: Session, hours: int) -> int:
    """Move every pending reminder `hours` into the past (the demo 'time machine')."""
    delta = timedelta(hours=hours)
    tickets = db.scalars(
        select(ChasingTicket).where(
            ChasingTicket.status.in_(CHASE_STATUSES + (TicketStatus.SNOOZED_TONIGHT,)),
            ChasingTicket.next_reminder_at.is_not(None),
        )
    ).all()
    for ticket in tickets:
        ticket.next_reminder_at = ticket.next_reminder_at - delta
        if ticket.last_contacted_at:
            ticket.last_contacted_at = ticket.last_contacted_at - delta
    db.flush()
    return len(tickets)


def simulate_time_jump(db: Session, hours: int = 48) -> tuple[int, list[dict]]:
    with _cycle_lock:
        shifted = shift_active_tickets(db, hours)
        actions = run_reminder_cycle(db)
        db.commit()
    return shifted, actions


def trigger_cycle(db: Session) -> list[dict]:
    with _cycle_lock:
        actions = run_reminder_cycle(db)
        db.commit()
    return actions


def _background_job() -> None:
    if not _cycle_lock.acquire(blocking=False):
        return
    try:
        with SessionLocal() as db:
            actions = run_reminder_cycle(db)
            if actions:
                # automatic 48h cycle: recorded as a system entry (no worker)
                log_activity(db, None, "REMINDERS_SENT", f"המערכת שלחה תזכורות אוטומטיות: {describe_reminder_actions(actions)}",
                             details={"source": "automatic"})
            db.commit()
            if actions:
                log.info("Reminder cycle sent %d automated actions", len(actions))
    except Exception:
        log.exception("Reminder cycle failed")
    finally:
        _cycle_lock.release()


def start_scheduler() -> BackgroundScheduler | None:
    global _scheduler
    if not settings.scheduler_enabled or _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone=settings.timezone)
    _scheduler.add_job(
        _background_job,
        "interval",
        seconds=settings.scheduler_interval_seconds,
        id="reminder_cycle",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    log.info("Nagging engine started (every %ss)", settings.scheduler_interval_seconds)
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def scheduler_status() -> dict:
    job = _scheduler.get_job("reminder_cycle") if _scheduler else None
    return {
        "enabled": settings.scheduler_enabled,
        "running": bool(_scheduler and _scheduler.running),
        "interval_seconds": settings.scheduler_interval_seconds,
        "next_run_at": job.next_run_time.isoformat() if job and job.next_run_time else None,
    }
