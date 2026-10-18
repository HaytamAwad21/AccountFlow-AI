"""One-time upgrade of WhatsApp history to Hebrew.

WhatsApp contact is Hebrew-only. Databases created by older releases may still hold outbound
messages that were sent in English or Arabic. `hebrewize_message_history` rewrites every such
message with the Hebrew text the engine would send today (same template / reply, same ticket
data) and translates stored quick-reply button titles and inbound button taps. It is
idempotent: Hebrew messages are never touched, and messages it cannot map are left as they are.
"""
from __future__ import annotations

import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from models import ChasingTicket, MessageDirection, MessageTemplate, MessageType, TemplateCategory, WhatsAppMessageLog
from services.i18n import t
from services.templating import body_for, render_text

log = logging.getLogger("accountflow.history")

HEBREW_RE = re.compile(r"[֐-׿]")
FOREIGN_RE = re.compile(r"[A-Za-z؀-ۿ]{3}")
REMINDER_COUNT_RE = re.compile(r"\((\d+)/(\d+)\)")
DEADLINE_RE = re.compile(r"(\d+)\D+?(\d+)\D*$", re.S)


def needs_hebrew(text: str | None) -> bool:
    return bool(text) and not HEBREW_RE.search(text) and bool(FOREIGN_RE.search(text))


def _button_index(db: Session) -> tuple[dict[str, str], dict[str, str]]:
    """button id -> Hebrew title, and any legacy (en/ar) title -> Hebrew title."""
    by_id: dict[str, str] = {}
    by_title: dict[str, str] = {}
    for tpl in db.scalars(select(MessageTemplate)):
        for b in tpl.buttons_json or []:
            he = b.get("he") or b["id"]
            by_id.setdefault(b["id"], he)
            for key in ("en", "ar"):
                if b.get(key):
                    by_title.setdefault(b[key], he)
    return by_id, by_title


# English / Arabic reply prefixes from older releases -> current Hebrew string key
ACK_PREFIXES: list[tuple[tuple[str, ...], str]] = [
    (("⏰ No problem", "⏰ لا مشكلة"), "ack_SNOOZE_TONIGHT"),
    (("📷 Great", "📷 ممتاز"), "ack_REQUEST_MEDIA"),
    (("✍️ Sure", "✍️ بكل سرور"), "ack_TYPE_DETAIL"),
    (("👍 Thanks for letting", "👍 شكرًا لإبلاغنا"), "ack_NO_DOCUMENT"),
    (("🏢",), "ack_BUSINESS_NO_RECEIPT"),
    (("🏠",), "ack_PERSONAL_EXPENSE"),
    (("✅ Thank you! Your", "✅ شكرًا لك! تم تسجيل"), "ack_PAID_CONFIRMED"),
    (("💳",), "ack_PAY_LINK"),
    (("📞",), "ack_REQUEST_CALL"),
    (("👨‍💼",), "ack_SEND_CLERK_ANYWAY"),
    (("🙏 Thank you! We added", "🙏 شكرًا لك! أضفنا"), "ack_text_detail"),
    (("🙏 Thank you! Your message", "🙏 شكرًا لك! تم تحويل"), "ack_text_generic"),
    (("📥 Thanks", "📥 شكرًا"), "no_open_ticket"),
    (("📥 Received", "📥 تم الاستلام"), "media_forwarded"),
    (("✅ Received and verified", "✅ تم الاستلام والتحقق"), "ocr_verified"),
]


def _hebrew_for(db: Session, msg: WhatsAppMessageLog, ticket: ChasingTicket | None) -> str | None:
    text = msg.content_text or ""
    ctx = dict((ticket.context_variables_json if ticket else None) or {})
    ctx.setdefault("client_name", msg.client.full_name)
    ocr = (ticket.ocr_validation_json if ticket else None) or {}

    if msg.message_type == MessageType.TEMPLATE and ticket is not None:
        return render_text(body_for(ticket.template), ctx)

    if text.startswith("🔔") and ticket is not None:
        m = REMINDER_COUNT_RE.search(text)
        n, total = (m.group(1), m.group(2)) if m else (ticket.reminder_count, ticket.max_reminders)
        kwargs = {**ctx, "n": n, "max": total, "ticket_ref": ticket.ticket_ref}
        if "clearer" in text or "أوضح" in text:
            return t("reminder_correction", **kwargs)
        category = ticket.template.category
        if ticket.template.slug == "monthly_folder_deadline_warning":
            category = TemplateCategory.MONTHLY_FOLDER
        return t(f"reminder_{category.value}", **kwargs)

    if text.startswith("⚠️"):
        tpl = db.scalar(select(MessageTemplate).where(MessageTemplate.slug == "monthly_folder_deadline_warning"))
        numbers = re.findall(r"\d+", text)
        if tpl and len(numbers) >= 2:
            return render_text(body_for(tpl), {"client_name": msg.client.full_name, "days_left": numbers[0], "open_items_count": numbers[1]})

    if text.startswith("🌙") and ticket is not None:
        return f"{t('snooze_ping', client_name=msg.client.full_name)}\n\n{render_text(body_for(ticket.template), ctx)}"

    if msg.message_type == MessageType.OCR_FEEDBACK and (text.startswith("Thanks") or text.startswith("شكرًا")) and ticket is not None:
        tpl = db.scalar(select(MessageTemplate).where(MessageTemplate.slug == "blurry_or_wrong_receipt_reprompt"))
        if tpl:
            return render_text(body_for(tpl), {
                "client_name": msg.client.full_name,
                "rejection_reason": ocr.get("rejection_reason_he") or ocr.get("rejection_reason") or "הצילום לא עבר את הבדיקה",
                "supplier_name": ctx.get("supplier_name") or ocr.get("supplier_name") or t("supplier_fallback"),
            })

    for prefixes, key in ACK_PREFIXES:
        if text.startswith(prefixes):
            values = {
                **ctx,
                "hour": settings.snooze_hour,
                "text": ctx.get("client_reply_text") or "",
                "payment_link": ctx.get("payment_link") or settings.default_payment_link,
                "invoice_number": ocr.get("invoice_number") or ctx.get("invoice_number"),
                "supplier_name": ocr.get("supplier_name") or ctx.get("supplier_name"),
            }
            return t(key, **values)
    return None


def hebrewize_message_history(db: Session) -> int:
    """Rewrite legacy non-Hebrew WhatsApp messages in Hebrew. Returns the number of rows changed."""
    by_id, by_title = _button_index(db)
    changed = 0
    for msg in db.scalars(select(WhatsAppMessageLog).order_by(WhatsAppMessageLog.id)):
        touched = False
        ticket = db.get(ChasingTicket, msg.ticket_id) if msg.ticket_id else None

        if msg.direction == MessageDirection.OUTBOUND and needs_hebrew(msg.content_text):
            hebrew = _hebrew_for(db, msg, ticket)
            if hebrew:
                msg.content_text = hebrew
                touched = True
        elif msg.direction == MessageDirection.INBOUND and msg.message_type == MessageType.BUTTON_REPLY and needs_hebrew(msg.content_text):
            hebrew = by_title.get(msg.content_text or "")
            if hebrew:
                msg.content_text = hebrew
                touched = True

        if msg.buttons_json and any(needs_hebrew(b.get("title")) for b in msg.buttons_json):
            msg.buttons_json = [{**b, "title": by_id.get(b.get("id"), b.get("title"))} for b in msg.buttons_json]
            touched = True

        changed += int(touched)
    if changed:
        db.commit()
        log.warning("Rewrote %d legacy WhatsApp messages in Hebrew", changed)
    return changed
