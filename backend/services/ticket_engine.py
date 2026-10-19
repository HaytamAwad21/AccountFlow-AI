"""Chasing-ticket state machine.

Engine A  – `create_and_send_ticket` (the 3-second clerk trigger)
Engine C  – `handle_button` / `handle_text` / `handle_media` (inbound WhatsApp + Vision AI,
            including the Israel Tax Authority 9-digit rules for typed allocation numbers / ח.פ)
Clerk ops – `approve_ticket`, `resolve_ticket`, `reopen_ticket`

Reminder cadence, max reminders, VAT rate, allocation threshold and the firm name come from
the live `system_settings` row (see services/system_settings.py).
"""
from __future__ import annotations

import logging
import mimetypes
import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config import settings
from models import (
    BulkTaxCampaign,
    BulkTaxRecipient,
    ChasingTicket,
    Client,
    MessageDirection,
    MessageTemplate,
    MessageType,
    PaymentStatus,
    TemplateCategory,
    TicketPriority,
    TicketStatus,
    User,
    WhatsAppMessageLog,
)
from services.clock import days_until_deadline, next_local_hour, utcnow
from services.events import queue_event
from services.i18n import classify_missing_detail, t
from services.no_emoji import strip_buttons, strip_emoji
from services.system_settings import auto_approve_enabled, firm_name, get_system_settings
from services.templating import (
    AUTO_VARIABLES,
    body_for,
    localized_buttons,
    render_text,
    required_variables,
)
from services.vision_ocr import is_nine_digits, normalize_id, verify_invoice_image
from services.whatsapp import dispatch

log = logging.getLogger("accountflow.engine")

ACTIVE_STATUSES = (
    TicketStatus.OPEN,
    TicketStatus.WAITING_FOR_CLIENT,
    TicketStatus.SNOOZED_TONIGHT,
    TicketStatus.NEEDS_CORRECTION,
    TicketStatus.NEEDS_CLERK_REVIEW,
    TicketStatus.ESCALATED,
)
CLIENT_PENDING_STATUSES = (
    TicketStatus.OPEN,
    TicketStatus.WAITING_FOR_CLIENT,
    TicketStatus.SNOOZED_TONIGHT,
    TicketStatus.NEEDS_CORRECTION,
    TicketStatus.ESCALATED,
)
OCR_CATEGORIES = {
    TemplateCategory.MISSING_INVOICE,
    TemplateCategory.MISSING_DETAIL,
    TemplateCategory.UNIDENTIFIED_CHARGE,
    TemplateCategory.MONTHLY_FOLDER,
}
# Statuses in which a ticket is waiting for the client's own reply (text or document). A snoozed
# ticket ("remind me at 20:00") and an escalated one are still waiting for the client.
# OPEN, NEEDS_CLERK_REVIEW and RESOLVED tickets never take free-form client input.
AWAITING_CLIENT_STATUSES = (
    TicketStatus.WAITING_FOR_CLIENT,
    TicketStatus.NEEDS_CORRECTION,
    TicketStatus.SNOOZED_TONIGHT,
    TicketStatus.ESCALATED,
)
# Request types whose answer is a photo / PDF even without requires_media_reply.
MEDIA_REQUEST_CATEGORIES = {TemplateCategory.MISSING_INVOICE, TemplateCategory.MISSING_DETAIL}
REPROMPT_SLUG = "blurry_or_wrong_receipt_reprompt"
DEADLINE_SLUG = "monthly_folder_deadline_warning"
TAX_SLUG = "tax_ready_to_pay"
ALLOWED_UPLOAD_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "application/pdf"}
MAX_UPLOAD_BYTES = 15 * 1024 * 1024


class EngineError(Exception):
    status_code = 400


class NotFoundError(EngineError):
    status_code = 404


class MissingVariablesError(EngineError):
    status_code = 422

    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__("חסרים שדות חובה: " + ", ".join(missing))


# ── lookups ──────────────────────────────────────────────────────────────────

def reminder_interval(db: Session) -> timedelta:
    return timedelta(hours=get_system_settings(db).reminder_interval_hours)


def lang_of(client: Client) -> str:
    """WhatsApp contact with clients is Hebrew-only."""
    return "he"


def open_items_count(db: Session, client_id: int) -> int:
    return db.scalar(
        select(func.count(ChasingTicket.id))
        .join(MessageTemplate)
        .where(
            ChasingTicket.client_id == client_id,
            ChasingTicket.status.in_(CLIENT_PENDING_STATUSES),
            MessageTemplate.category != TemplateCategory.TAX_READY,
            MessageTemplate.slug != DEADLINE_SLUG,
        )
    ) or 0


def auto_variables(db: Session, client: Client) -> dict:
    return {
        "client_name": client.full_name,
        "company_name": client.company_name,
        "open_items_count": str(open_items_count(db, client.id)),
        "days_left": str(days_until_deadline(client.reporting_frequency)),
    }


def template_by_slug(db: Session, slug: str) -> MessageTemplate:
    tpl = db.scalar(select(MessageTemplate).where(MessageTemplate.slug == slug))
    if not tpl:
        raise NotFoundError(f"התבנית {slug} לא נמצאה")
    return tpl


def button_index(db: Session) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for tpl in db.scalars(select(MessageTemplate)):
        for b in tpl.buttons_json or []:
            index.setdefault(b["id"], b)
    return index


def missing_variables(template: MessageTemplate, variables: dict) -> list[str]:
    return [v for v in required_variables(template) if not str(variables.get(v) or "").strip()]


# ── messaging primitives ─────────────────────────────────────────────────────

def log_message(
    db: Session,
    *,
    client: Client,
    ticket: ChasingTicket | None,
    direction: MessageDirection,
    message_type: MessageType,
    text: str,
    sender_name: str,
    buttons: list[dict] | None = None,
    media_url: str | None = None,
    is_automated: bool = True,
    sender_user: User | None = None,
) -> WhatsAppMessageLog:
    if direction == MessageDirection.OUTBOUND:
        # Strict no-emoji policy: everything the firm sends is clean Hebrew text.
        text = strip_emoji(text) or ""
        buttons = strip_buttons(buttons)
    msg = WhatsAppMessageLog(
        ticket_id=ticket.id if ticket else None,
        client_id=client.id,
        direction=direction,
        sender_name=sender_name,
        is_automated=is_automated,
        sender_user_id=sender_user.id if sender_user else None,
        message_type=message_type,
        content_text=text,
        buttons_json=buttons or None,
        media_url=media_url,
        created_at=utcnow(),
    )
    db.add(msg)
    db.flush()
    return msg


def send_outbound(
    db: Session,
    client: Client,
    ticket: ChasingTicket | None,
    text: str,
    buttons: list[dict] | None,
    message_type: MessageType,
    external: bool = True,
) -> WhatsAppMessageLog:
    msg = log_message(
        db, client=client, ticket=ticket, direction=MessageDirection.OUTBOUND, message_type=message_type,
        text=text, sender_name=firm_name(db), buttons=buttons,
    )
    if ticket is not None:
        ticket.last_contacted_at = msg.created_at
    dispatch(db, msg, client, msg.buttons_json, external=external)
    return msg


def send_manual_message(
    db: Session,
    *,
    client: Client,
    worker: User,
    text: str,
    media_url: str | None = None,
    media_mime: str | None = None,
    external: bool = True,
) -> WhatsAppMessageLog:
    """A worker's free-text message and/or picture, sent as-is (no template, no ticket, no reminders)."""
    if not client.is_active:
        raise EngineError(f"הלקוח '{client.full_name}' אינו פעיל")
    clean = (strip_emoji(text) or "").strip()
    if not clean and not media_url:
        raise EngineError("יש לכתוב הודעה או לצרף תמונה")
    msg = log_message(
        db, client=client, ticket=None, direction=MessageDirection.OUTBOUND,
        message_type=MessageType.IMAGE_UPLOAD if media_url else MessageType.TEXT,
        text=clean, sender_name=worker.full_name, media_url=media_url,
        is_automated=False, sender_user=worker,
    )
    dispatch(db, msg, client, None, external=external, media_mime=media_mime)
    return msg


def log_inbound(db: Session, client: Client, ticket: ChasingTicket | None, message_type: MessageType,
                text: str, media_url: str | None = None) -> WhatsAppMessageLog:
    msg = log_message(db, client=client, ticket=ticket, direction=MessageDirection.INBOUND,
                      message_type=message_type, text=text, sender_name=client.full_name, media_url=media_url,
                      is_automated=False)
    queue_event(db, {"type": "message", "client_id": client.id, "ticket_id": msg.ticket_id})
    return msg


def touch(db: Session, ticket: ChasingTicket) -> None:
    queue_event(db, {"type": "ticket", "ticket_id": ticket.id, "client_id": ticket.client_id, "status": ticket.status.value})


def _set_ctx(ticket: ChasingTicket, **updates) -> dict:
    ctx = dict(ticket.context_variables_json or {})
    ctx.update(updates)
    ticket.context_variables_json = ctx  # reassign so SQLAlchemy detects the JSON change
    return ctx


# ── Engine A: 3-second trigger ───────────────────────────────────────────────

def create_and_send_ticket(
    db: Session,
    *,
    client: Client,
    template: MessageTemplate,
    variables: dict | None = None,
    worker_id: int | None = None,
    priority: TicketPriority = TicketPriority.NORMAL,
    max_reminders: int | None = None,
    external: bool = True,
) -> tuple[ChasingTicket, WhatsAppMessageLog]:
    if not client.is_active:
        raise EngineError(f"הלקוח '{client.full_name}' אינו פעיל")
    lang = lang_of(client)
    provided = {k: str(v).strip() for k, v in (variables or {}).items() if v is not None and str(v).strip() != ""}
    merged = {**auto_variables(db, client), **provided}
    missing = missing_variables(template, merged)
    if missing:
        raise MissingVariablesError(missing)
    detail_kind = classify_missing_detail(merged.get("missing_detail"))
    if detail_kind:
        merged["detail_kind"] = detail_kind
    office = get_system_settings(db)

    text = render_text(body_for(template, lang), merged)
    buttons = localized_buttons(template, lang)
    now = utcnow()
    ticket = ChasingTicket(
        ticket_ref=f"TMP-{uuid.uuid4().hex[:12]}",
        client_id=client.id,
        worker_id=worker_id or client.assigned_worker_id,
        template_id=template.id,
        status=TicketStatus.WAITING_FOR_CLIENT,
        priority=priority,
        context_variables_json=merged,
        reminder_count=0,
        max_reminders=max_reminders or office.max_reminders,
        last_contacted_at=now,
        next_reminder_at=now + timedelta(hours=office.reminder_interval_hours),
        created_at=now,
    )
    db.add(ticket)
    db.flush()
    ticket.ticket_ref = f"TCK-{1000 + ticket.id}"
    msg = send_outbound(db, client, ticket, text, buttons, MessageType.TEMPLATE, external=external)
    touch(db, ticket)
    return ticket, msg


# ── Engine C: inbound handling ───────────────────────────────────────────────

def find_active_ticket(db: Session, client: Client, ticket_id: int | None = None,
                       for_media: bool = False) -> ChasingTicket | None:
    if ticket_id:
        tk = db.get(ChasingTicket, ticket_id)
        if tk and tk.client_id == client.id and tk.status != TicketStatus.RESOLVED:
            return tk
    candidates = list(
        db.scalars(
            select(ChasingTicket).where(
                ChasingTicket.client_id == client.id, ChasingTicket.status.in_(ACTIVE_STATUSES)
            )
        )
    )
    if not candidates:
        return None

    def rank(tk: ChasingTicket):
        ctx = tk.context_variables_json or {}
        media_fit = tk.template.category in OCR_CATEGORIES and tk.template.slug != DEADLINE_SLUG
        return (
            tk.status == TicketStatus.NEEDS_CORRECTION if for_media else False,
            bool(ctx.get("awaiting_media")) if for_media else bool(ctx.get("awaiting_text")),
            media_fit if for_media else True,
            tk.status != TicketStatus.NEEDS_CLERK_REVIEW,
            tk.last_contacted_at or tk.created_at,
        )

    return max(candidates, key=rank)


def expects_media(ticket: ChasingTicket) -> bool:
    """True when the request is answered with a photo / PDF (an invoice, receipt or corrected copy)."""
    ctx = ticket.context_variables_json or {}
    return (
        bool(ticket.template.requires_media_reply)
        or ticket.template.category in MEDIA_REQUEST_CATEGORIES
        or bool(ctx.get("awaiting_media"))
    )


def find_awaiting_ticket(db: Session, client: Client, ticket_id: int | None = None,
                         for_media: bool = False) -> ChasingTicket | None:
    """The open request that is waiting for this client's free-form reply, or None.

    Only tickets in AWAITING_CLIENT_STATUSES qualify; for a photo / PDF the ticket must also
    expect a document. A ticket that is resolved, waiting for the clerk, or asks for something
    else never receives the client's input, so the bot does not answer it.
    """
    def fits(tk: ChasingTicket) -> bool:
        return (tk.client_id == client.id and tk.status in AWAITING_CLIENT_STATUSES
                and (not for_media or expects_media(tk)))

    if ticket_id:
        tk = db.get(ChasingTicket, ticket_id)
        if tk and fits(tk):
            return tk
    candidates = [tk for tk in db.scalars(
        select(ChasingTicket).where(ChasingTicket.client_id == client.id,
                                    ChasingTicket.status.in_(AWAITING_CLIENT_STATUSES))
    ) if fits(tk)]
    if not candidates:
        return None

    def rank(tk: ChasingTicket):
        ctx = tk.context_variables_json or {}
        return (
            tk.status == TicketStatus.NEEDS_CORRECTION,
            bool(ctx.get("awaiting_media")) if for_media else bool(ctx.get("awaiting_text")),
            tk.template.category in OCR_CATEGORIES and tk.template.slug != DEADLINE_SLUG if for_media else True,
            tk.last_contacted_at or tk.created_at,
        )

    return max(candidates, key=rank)


def log_unsolicited(db: Session, client: Client, message_type: MessageType, text: str,
                    media_url: str | None = None) -> dict:
    """Silent logging: the message / photo is saved to the chat history for the office, and
    nothing else happens: no Vision AI check, no ticket change, no automated reply."""
    log_inbound(db, client, None, message_type, text, media_url=media_url)
    kind = "תמונה / מסמך" if media_url else "הודעת טקסט"
    log.info("%s מהלקוח %s ללא בקשה פתוחה מתאימה: נשמרה ביומן השיחה ללא מענה אוטומטי", kind, client.full_name)
    return {"ticket": None, "reply": None, "ocr": None, "unsolicited": True}


def sync_recipient(db: Session, ticket: ChasingTicket, status: PaymentStatus) -> None:
    recipient = db.scalar(select(BulkTaxRecipient).where(BulkTaxRecipient.ticket_id == ticket.id))
    if not recipient:
        return
    order = [PaymentStatus.SENT, PaymentStatus.VIEWED, PaymentStatus.QUESTION_ASKED, PaymentStatus.CONFIRMED_PAID]
    if status == PaymentStatus.VIEWED and order.index(recipient.payment_status) >= order.index(PaymentStatus.VIEWED):
        return
    recipient.payment_status = status
    db.flush()
    recount_campaign(db, recipient.campaign)
    queue_event(db, {"type": "campaign", "campaign_id": recipient.campaign_id})


def recount_campaign(db: Session, campaign: BulkTaxCampaign) -> None:
    recipients = campaign.recipients
    campaign.total_clients = len(recipients)
    campaign.confirmed_count = sum(1 for r in recipients if r.payment_status == PaymentStatus.CONFIRMED_PAID)
    campaign.pending_count = campaign.total_clients - campaign.confirmed_count


def handle_button(db: Session, client: Client, button_id: str, ticket_id: int | None = None) -> dict:
    lang = lang_of(client)
    button = button_index(db).get(button_id)
    ticket = find_active_ticket(db, client, ticket_id)
    title = (button or {}).get("he") or button_id
    action = (button or {}).get("action", "UNKNOWN")
    log_inbound(db, client, ticket, MessageType.BUTTON_REPLY, title)

    if ticket is None:
        reply = t("no_open_ticket", lang)
        send_outbound(db, client, None, reply, None, MessageType.TEXT)
        return {"ticket": None, "action": action, "reply": reply}

    now = utcnow()
    ctx = dict(ticket.context_variables_json or {})
    reply_key = f"ack_{action}"
    reply_kwargs = dict(ctx)
    reply_buttons: list[dict] | None = None

    if action == "REQUEST_MEDIA":
        ctx["awaiting_media"] = True
        if ticket.status in (TicketStatus.SNOOZED_TONIGHT, TicketStatus.OPEN, TicketStatus.ESCALATED):
            ticket.status = TicketStatus.WAITING_FOR_CLIENT
            ticket.next_reminder_at = now + reminder_interval(db)
    elif action == "SNOOZE_TONIGHT":
        ticket.status = TicketStatus.SNOOZED_TONIGHT
        ticket.next_reminder_at = next_local_hour(settings.snooze_hour, now)
        reply_kwargs["hour"] = settings.snooze_hour
    elif action == "TYPE_DETAIL":
        ctx["awaiting_text"] = True
        if ticket.status == TicketStatus.SNOOZED_TONIGHT:
            ticket.status = TicketStatus.WAITING_FOR_CLIENT
            ticket.next_reminder_at = now + reminder_interval(db)
    elif action == "NO_DOCUMENT":
        ctx["client_response"] = "no_document"
        ticket.status = TicketStatus.NEEDS_CLERK_REVIEW
        ticket.next_reminder_at = None
    elif action in ("BUSINESS_NO_RECEIPT", "PERSONAL_EXPENSE"):
        ctx["classification"] = "business_no_receipt" if action == "BUSINESS_NO_RECEIPT" else "personal"
        ticket.status = TicketStatus.RESOLVED
        ticket.resolved_at = now
        ticket.next_reminder_at = None
        ticket.resolution_note = ("הלקוח סיווג את החיוב כהוצאה עסקית ללא קבלה." if action == "BUSINESS_NO_RECEIPT"
                                  else "הלקוח סיווג את החיוב כהוצאה פרטית.")
    elif action == "PAID_CONFIRMED":
        ctx["payment_confirmed_at"] = now.isoformat()
        ticket.status = TicketStatus.RESOLVED
        ticket.resolved_at = now
        ticket.next_reminder_at = None
        ticket.resolution_note = "הלקוח אישר תשלום בוואטסאפ."
        sync_recipient(db, ticket, PaymentStatus.CONFIRMED_PAID)
    elif action == "PAY_LINK":
        reply_kwargs["payment_link"] = ctx.get("payment_link") or settings.default_payment_link
        paid = next((b for b in ticket.template.buttons_json or [] if b.get("action") == "PAID_CONFIRMED"), None)
        if paid:
            reply_buttons = [{"id": paid["id"], "title": paid.get("he") or paid["id"], "action": paid["action"]}]
        sync_recipient(db, ticket, PaymentStatus.VIEWED)
    elif action == "REQUEST_CALL":
        ctx["call_requested_at"] = now.isoformat()
        ticket.status = TicketStatus.ESCALATED
        if ticket.priority == TicketPriority.NORMAL:
            ticket.priority = TicketPriority.HIGH
        ticket.next_reminder_at = None
        sync_recipient(db, ticket, PaymentStatus.QUESTION_ASKED)
    elif action == "SEND_CLERK_ANYWAY":
        ctx["forwarded_despite_ocr"] = True
        ticket.status = TicketStatus.NEEDS_CLERK_REVIEW
        ticket.next_reminder_at = None
    else:
        reply_key = "ack_text_generic"

    ticket.context_variables_json = ctx
    reply = t(reply_key, lang, **reply_kwargs)
    send_outbound(db, client, ticket, reply, reply_buttons, MessageType.TEXT)
    touch(db, ticket)
    return {"ticket": ticket, "action": action, "reply": reply}


def _validate_typed_identifier(db: Session, client: Client, ticket: ChasingTicket, text: str, kind: str) -> dict:
    """Israel Tax Authority rule: an allocation number and a ח.פ / ע.מ are exactly 9 digits (^\\d{9}$)."""
    lang = lang_of(client)
    value = normalize_id(text)
    if not is_nine_digits(value):
        _set_ctx(ticket, awaiting_text=True, last_invalid_value=text,
                 invalid_attempts=int((ticket.context_variables_json or {}).get("invalid_attempts", 0)) + 1)
        ticket.status = TicketStatus.NEEDS_CORRECTION
        ticket.next_reminder_at = utcnow() + reminder_interval(db)
        reply_key = "invalid_allocation_reply" if kind == "allocation_number" else "invalid_tax_id_reply"
        reply = t(reply_key, lang)
        send_outbound(db, client, ticket, reply, None, MessageType.OCR_FEEDBACK)
        touch(db, ticket)
        return {"ticket": ticket, "reply": reply, "validation": {"field": kind, "valid": False, "value": text}}

    _set_ctx(ticket, awaiting_text=False, client_reply_text=value, **{kind: value})
    ticket.status = TicketStatus.NEEDS_CLERK_REVIEW
    ticket.next_reminder_at = None
    reply = t("ack_valid_allocation" if kind == "allocation_number" else "ack_valid_tax_id", lang, value=value)
    send_outbound(db, client, ticket, reply, None, MessageType.TEXT)
    touch(db, ticket)
    return {"ticket": ticket, "reply": reply, "validation": {"field": kind, "valid": True, "value": value}}


def handle_text(db: Session, client: Client, text: str, ticket_id: int | None = None) -> dict:
    lang = lang_of(client)
    ticket = find_awaiting_ticket(db, client, ticket_id)
    if ticket is None:
        return log_unsolicited(db, client, MessageType.TEXT, text)
    log_inbound(db, client, ticket, MessageType.TEXT, text)

    ctx = ticket.context_variables_json or {}
    kind = ctx.get("detail_kind")
    has_digits = any(ch.isdigit() for ch in text)
    if kind in ("allocation_number", "tax_id") and (ctx.get("awaiting_text") or has_digits):
        return _validate_typed_identifier(db, client, ticket, text, kind)
    if ctx.get("awaiting_text"):
        _set_ctx(ticket, awaiting_text=False, client_reply_text=text)
        ticket.status = TicketStatus.NEEDS_CLERK_REVIEW
        ticket.next_reminder_at = None
        reply = t("ack_text_detail", lang, text=text)
    else:
        _set_ctx(ticket, last_client_text=text)
        reply = t("ack_text_generic", lang)
    send_outbound(db, client, ticket, reply, None, MessageType.TEXT)
    touch(db, ticket)
    return {"ticket": ticket, "reply": reply}


def save_upload(content: bytes, filename: str | None, mime: str | None) -> tuple[Path, str, str]:
    if len(content) > MAX_UPLOAD_BYTES:
        raise EngineError("הקובץ גדול מדי (מקסימום 15MB)")
    mime = (mime or mimetypes.guess_type(filename or "")[0] or "application/octet-stream").lower()
    if mime not in ALLOWED_UPLOAD_TYPES:
        raise EngineError(f"סוג קובץ לא נתמך ({mime}). יש לשלוח JPG, PNG, WEBP או PDF.")
    ext = mimetypes.guess_extension(mime) or Path(filename or "").suffix or ".bin"
    if ext == ".jpe":
        ext = ".jpg"
    name = f"in_{uuid.uuid4().hex[:16]}{ext}"
    path = settings.upload_dir / name
    path.write_bytes(content)
    return path, f"/uploads/{name}", mime


def media_path(media_url: str | None) -> Path | None:
    if not media_url:
        return None
    return settings.upload_dir / Path(media_url).name


def handle_media(db: Session, client: Client, path: Path, media_url: str, mime: str,
                 ticket_id: int | None = None, caption: str = "") -> dict:
    lang = lang_of(client)
    ticket = find_awaiting_ticket(db, client, ticket_id, for_media=True)
    if ticket is None:
        return log_unsolicited(db, client, MessageType.IMAGE_UPLOAD, caption or "", media_url=media_url)
    log_inbound(db, client, ticket, MessageType.IMAGE_UPLOAD, caption or "", media_url=media_url)

    now = utcnow()
    ctx = _set_ctx(ticket, awaiting_media=False,
                   upload_attempts=int((ticket.context_variables_json or {}).get("upload_attempts", 0)) + 1)
    ticket.media_file_path = media_url

    if ticket.template.category not in OCR_CATEGORIES:
        ticket.status = TicketStatus.NEEDS_CLERK_REVIEW
        ticket.next_reminder_at = None
        reply = t("media_forwarded", lang)
        send_outbound(db, client, ticket, reply, None, MessageType.OCR_FEEDBACK)
        touch(db, ticket)
        return {"ticket": ticket, "ocr": None, "reply": reply}

    office = get_system_settings(db)
    result = verify_invoice_image(path, ctx.get("supplier_name"), ctx.get("invoice_number"), lang, mime,
                                  vat_rate=office.vat_rate / 100.0,
                                  allocation_threshold=office.allocation_number_threshold_nis)
    ticket.ocr_validation_json = result

    if result["is_valid"] is True:
        if auto_approve_enabled(db):
            ticket.status = TicketStatus.RESOLVED
            ticket.resolved_at = now
            ticket.resolution_note = "אושר אוטומטית: אימות Vision AI עבר בהצלחה."
        else:
            ticket.status = TicketStatus.NEEDS_CLERK_REVIEW
        ticket.next_reminder_at = None
        reply = t("ocr_verified", lang, invoice_number=result["invoice_number"], supplier_name=result["supplier_name"])
        send_outbound(db, client, ticket, reply, None, MessageType.OCR_FEEDBACK)
    elif result["is_valid"] is None:
        ticket.status = TicketStatus.NEEDS_CLERK_REVIEW
        ticket.next_reminder_at = None
        reply = t("media_forwarded", lang)
        send_outbound(db, client, ticket, reply, None, MessageType.OCR_FEEDBACK)
    else:
        ticket.status = TicketStatus.NEEDS_CORRECTION
        ticket.next_reminder_at = now + reminder_interval(db)
        reprompt = template_by_slug(db, REPROMPT_SLUG)
        variables = {
            "client_name": client.full_name,
            "rejection_reason": result["rejection_reason"],
            "supplier_name": ctx.get("supplier_name") or result.get("supplier_name") or t("supplier_fallback", lang),
        }
        reply = render_text(body_for(reprompt, lang), variables)
        send_outbound(db, client, ticket, reply, localized_buttons(reprompt, lang), MessageType.OCR_FEEDBACK)

    touch(db, ticket)
    return {"ticket": ticket, "ocr": result, "reply": reply}


# ── clerk operations ─────────────────────────────────────────────────────────

def approve_ticket(db: Session, ticket: ChasingTicket, user: User | None = None, note: str = "") -> ChasingTicket:
    now = utcnow()
    ticket.status = TicketStatus.RESOLVED
    ticket.resolved_at = now
    ticket.next_reminder_at = None
    ticket.resolution_note = note or f"אושר על ידי {user.full_name if user else 'צוות המשרד'}."
    if ticket.ocr_validation_json:
        ocr = dict(ticket.ocr_validation_json)
        ocr.update(approved=True, approved_at=now.isoformat(), approved_by=user.full_name if user else None)
        ticket.ocr_validation_json = ocr
    touch(db, ticket)
    return ticket


def reject_invoice(db: Session, ticket: ChasingTicket, user: User | None, reason: str) -> ChasingTicket:
    """A clerk rejects the received invoice: the client gets the Hebrew re-prompt with the clerk's
    reason, the ticket goes back to NEEDS_CORRECTION and the automatic chase restarts."""
    reason = reason.strip()
    client = ticket.client
    now = utcnow()
    ocr = dict(ticket.ocr_validation_json or {})
    if ocr:
        ocr.update(approved=False, rejected_at=now.isoformat(), rejected_by=user.full_name if user else None,
                   clerk_rejection_reason=reason)
        ticket.ocr_validation_json = ocr
    ctx = _set_ctx(ticket, awaiting_media=True, clerk_rejection_reason=reason)
    ticket.status = TicketStatus.NEEDS_CORRECTION
    ticket.resolved_at = None
    ticket.next_reminder_at = now + reminder_interval(db)
    reprompt = template_by_slug(db, REPROMPT_SLUG)
    text = render_text(body_for(reprompt), {
        "client_name": client.full_name,
        "rejection_reason": reason,
        "supplier_name": ctx.get("supplier_name") or ocr.get("supplier_name") or t("supplier_fallback"),
    })
    send_outbound(db, client, ticket, text, localized_buttons(reprompt, "he"), MessageType.OCR_FEEDBACK)
    touch(db, ticket)
    return ticket


def resolve_ticket(db: Session, ticket: ChasingTicket, note: str = "") -> ChasingTicket:
    ticket.status = TicketStatus.RESOLVED
    ticket.resolved_at = utcnow()
    ticket.next_reminder_at = None
    ticket.resolution_note = note or "נסגר ידנית על ידי צוות המשרד."
    touch(db, ticket)
    return ticket


def reopen_ticket(db: Session, ticket: ChasingTicket) -> ChasingTicket:
    now = utcnow()
    ticket.status = TicketStatus.WAITING_FOR_CLIENT
    ticket.reminder_count = 0
    ticket.resolved_at = None
    ticket.next_reminder_at = now + reminder_interval(db)
    touch(db, ticket)
    return ticket


__all__ = [
    "AUTO_VARIABLES",
    "ACTIVE_STATUSES",
    "CLIENT_PENDING_STATUSES",
    "EngineError",
    "MissingVariablesError",
    "NotFoundError",
    "approve_ticket",
    "auto_variables",
    "create_and_send_ticket",
    "find_active_ticket",
    "find_awaiting_ticket",
    "handle_button",
    "handle_media",
    "handle_text",
    "open_items_count",
    "reject_invoice",
    "reminder_interval",
    "reopen_ticket",
    "resolve_ticket",
    "save_upload",
    "template_by_slug",
]
