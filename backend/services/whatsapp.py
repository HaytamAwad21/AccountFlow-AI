"""WhatsApp adapter.

Every outbound message is (1) published to the in-app phone simulator over SSE and
(2) — when WHATSAPP_TOKEN + WHATSAPP_PHONE_NUMBER_ID are configured — sent through the
Meta WhatsApp Cloud API as an interactive quick-reply message. The Cloud API call runs
after the DB commit on a worker thread, so the clerk's request returns immediately.

Every outbound message starts with a header line that tells the customer who wrote it:
"הודעה אוטומטית" for bot / template / reminder / Vision AI messages, or "הודעה מאת <worker>"
for a worker's manual message. A manual picture / PDF is first uploaded to the Cloud API media
endpoint and then sent by its media ID, so Meta never has to reach the office computer (only the
webhook is exposed).

Meta accepts free-form and reply-button messages only within 24 hours of the client's last
message (the customer-service window). When the window is closed, outbound messages are held
(`awaiting_window`) and the approved WHATSAPP_REENGAGE_TEMPLATE is sent once instead; the held
messages go out, in order, as soon as the client taps it or writes anything. Outdated held
messages are dropped on release instead of piling up (see `_outdated_held`).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import mimetypes
import re
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal
from models import Client, DeliveryStatus, MessageDirection, MessageType, TicketStatus, WhatsAppMessageLog
from services.clock import utcnow
from services.events import queue_event, queue_in_order_after_commit
from services.system_settings import get_system_settings

log = logging.getLogger("accountflow.whatsapp")

GRAPH_URL = "https://graph.facebook.com"
BUTTON_TITLE_MAX = 20  # Meta limit for reply-button titles
BODY_MAX = 1024
SERVICE_WINDOW = timedelta(hours=24)  # Meta's customer-service window
WINDOW_CLOSED_ERROR = 131047  # Cloud API: "more than 24 hours have passed since the customer last replied"
REENGAGE_BUTTON_ID = "show_held"  # quick-reply payload of the re-engagement template's button
REENGAGE_BUTTON_TITLE = "הצגת ההודעה"


def verify_webhook_signature(raw_body: bytes, header: str | None) -> bool:
    """True when `X-Hub-Signature-256` is Meta's HMAC-SHA256 of the raw body, keyed with
    WHATSAPP_APP_SECRET. Always False while no app secret is configured."""
    secret = settings.whatsapp_app_secret
    if not secret or not header:
        return False
    scheme, _, digest = header.strip().partition("=")
    if scheme.lower() != "sha256" or not digest:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, digest.lower())


def normalize_phone(raw: str, default_cc: str | None = None) -> str:
    """Normalize to E.164 (+972501234567). Local Israeli numbers (05x...) get the default country code."""
    default_cc = default_cc or settings.default_country_code
    raw = (raw or "").strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    if raw.startswith("+"):
        return f"+{digits}"
    if digits.startswith("00"):
        return f"+{digits[2:]}"
    if digits.startswith("0"):
        return f"+{default_cc}{digits[1:]}"
    if digits.startswith(default_cc):
        return f"+{digits}"
    if len(digits) <= 9:
        return f"+{default_cc}{digits}"
    return f"+{digits}"


def button_payload(ticket_id: int | None, button_id: str) -> str:
    return f"t{ticket_id or 0}:{button_id}"


def parse_button_payload(payload: str) -> tuple[int | None, str]:
    m = re.match(r"^t(\d+):(.+)$", payload or "")
    if not m:
        return None, payload
    tid = int(m.group(1))
    return (tid or None), m.group(2)


AUTOMATED_HEADER = "הודעה אוטומטית"


def customer_header(msg: WhatsAppMessageLog) -> str:
    """The header line shown to the customer above every outbound message."""
    if msg.is_automated:
        return AUTOMATED_HEADER
    return f"הודעה מאת {msg.sender_name}"


def with_header(header: str, text: str) -> str:
    return f"*{header}*\n{text}" if text else f"*{header}*"


def dispatch(db: Session, msg: WhatsAppMessageLog, client: Client, buttons: list[dict] | None, external: bool = True,
             media_mime: str | None = None) -> None:
    queue_event(db, {"type": "message", "client_id": client.id, "ticket_id": msg.ticket_id})
    if not (external and settings.whatsapp_live):
        return
    if service_window_open(db, client.id):
        _queue_send(db, msg, client, buttons, media_mime)
    else:
        _hold(db, msg, client)


def service_window_open(db: Session, client_id: int) -> bool:
    """True while the client's last inbound message is less than 24 hours old."""
    last = db.scalar(select(func.max(WhatsAppMessageLog.created_at)).where(
        WhatsAppMessageLog.client_id == client_id, WhatsAppMessageLog.direction == MessageDirection.INBOUND))
    return last is not None and last > utcnow() - SERVICE_WINDOW


SKIP_OLDER_REMINDER = "לא נשלחה: נשלחה במקומה התזכורת העדכנית לאותה בקשה"
SKIP_REQUEST_PENDING = "לא נשלחה: הבקשה המקורית עוד לא נמסרה ללקוח ונשלחה במקום התזכורת"
SKIP_TICKET_CLOSED = "לא נשלחה: הפנייה נסגרה לפני שהלקוח חזר לשיחה"


def _outdated_held(held: list[WhatsAppMessageLog]) -> dict[int, str]:
    """Held messages that should not be sent when the window reopens, with the Hebrew reason.

    Per ticket (manual messages and other messages without a ticket always go out):
    - the ticket was closed meanwhile: none of its held automated messages are sent;
    - the original request itself is held: it goes out and its held reminders are dropped
      (a reminder about a request the client never saw is confusing);
    - otherwise only the newest held reminder goes out.
    """
    by_ticket: dict[int, list[WhatsAppMessageLog]] = defaultdict(list)
    for msg in held:
        if msg.ticket_id and msg.is_automated:
            by_ticket[msg.ticket_id].append(msg)
    skip: dict[int, str] = {}
    for msgs in by_ticket.values():
        ticket = msgs[0].ticket
        if ticket is None or ticket.status == TicketStatus.RESOLVED:
            skip.update({m.id: SKIP_TICKET_CLOSED for m in msgs})
            continue
        reminders = [m for m in msgs if m.message_type == MessageType.AUTO_REMINDER]
        if any(m.message_type == MessageType.TEMPLATE for m in msgs):
            skip.update({m.id: SKIP_REQUEST_PENDING for m in reminders})
        else:
            skip.update({m.id: SKIP_OLDER_REMINDER for m in reminders[:-1]})
    return skip


def release_held_messages(db: Session, client: Client) -> int:
    """The client wrote (or tapped the re-engagement template): send the held messages, oldest first,
    except outdated ones (see `_outdated_held`), which are marked SKIPPED and never sent.
    Call it after logging the inbound message, before any reply is dispatched. Returns how many were sent."""
    held = db.scalars(select(WhatsAppMessageLog).where(
        WhatsAppMessageLog.client_id == client.id, WhatsAppMessageLog.awaiting_window.is_(True),
    ).order_by(WhatsAppMessageLog.created_at, WhatsAppMessageLog.id)).all()
    skip = _outdated_held(list(held))
    released = 0
    for msg in held:
        msg.awaiting_window = False
        if msg.id in skip:
            msg.delivery_status = DeliveryStatus.SKIPPED
            msg.error_text = skip[msg.id]
            continue
        msg.error_text = None
        released += 1
        if settings.whatsapp_live:
            _queue_send(db, msg, client, msg.buttons_json, None)
    if skip:
        log.info("לקוח %s: %d הודעות ממתינות שאינן עדכניות לא נשלחו", client.id, len(skip))
    if held:
        queue_event(db, {"type": "message", "client_id": client.id, "ticket_id": None})
    return released


def _has_held(db: Session, client_id: int) -> bool:
    return db.scalar(select(WhatsAppMessageLog.id).where(
        WhatsAppMessageLog.client_id == client_id, WhatsAppMessageLog.awaiting_window.is_(True)).limit(1)) is not None


def _hold(db: Session, msg: WhatsAppMessageLog, client: Client) -> None:
    """Window closed: keep the message for later and invite the client back with the approved template,
    once per closed window (only the first held message sends it)."""
    first = not _has_held(db, client.id)
    msg.awaiting_window = True
    db.flush()  # the next message held in this transaction must see this one
    if not first:
        return
    if not settings.whatsapp_reengage_template:
        log.warning("Client %s: 24-hour window closed and WHATSAPP_REENGAGE_TEMPLATE is not set; "
                    "message %s waits until the client writes", client.id, msg.id)
        msg.error_text = "חלון 24 השעות של WhatsApp סגור ולא הוגדרה תבנית פתיחה (WHATSAPP_REENGAGE_TEMPLATE): ההודעה תישלח כשהלקוח יכתוב"
        return
    msg_id, phone, name, firm = msg.id, client.whatsapp_phone, client.full_name, get_system_settings(db).firm_name
    queue_in_order_after_commit(db, lambda: _send_reengage(msg_id, phone, name, firm))


def _queue_send(db: Session, msg: WhatsAppMessageLog, client: Client, buttons: list[dict] | None,
                media_mime: str | None) -> None:
    msg_id, phone = msg.id, client.whatsapp_phone
    text = with_header(customer_header(msg), msg.content_text or "")
    btns = [dict(b) for b in (buttons or [])]
    ticket_id, media_url = msg.ticket_id, msg.media_url
    queue_in_order_after_commit(db, lambda: _send_cloud_api(msg_id, phone, text, btns, ticket_id, media_url, media_mime))


def _media_kind(mime: str | None, filename: str) -> str:
    return "document" if (mime or "").endswith("pdf") or filename.lower().endswith(".pdf") else "image"


def _cloud_payload(phone: str, text: str, buttons: list[dict], ticket_id: int | None,
                   media_id: str | None = None, media_kind: str = "image", filename: str | None = None) -> dict:
    to = re.sub(r"\D", "", phone)
    if media_id:
        media: dict = {"id": media_id, "caption": text[:BODY_MAX]}
        if media_kind == "document" and filename:
            media["filename"] = filename
        return {"messaging_product": "whatsapp", "to": to, "type": media_kind, media_kind: media}
    if buttons:
        return {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": text[:BODY_MAX]},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": button_payload(ticket_id, b["id"]), "title": b["title"][:BUTTON_TITLE_MAX]}}
                        for b in buttons[:3]
                    ]
                },
            },
        }
    return {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text[:4096], "preview_url": True}}


def _reengage_payload(phone: str, client_name: str, firm_name: str) -> dict:
    return {
        "messaging_product": "whatsapp",
        "to": re.sub(r"\D", "", phone),
        "type": "template",
        "template": {
            "name": settings.whatsapp_reengage_template,
            "language": {"code": settings.whatsapp_template_language},
            "components": [
                {"type": "body", "parameters": [{"type": "text", "text": client_name}, {"type": "text", "text": firm_name}]},
                {"type": "button", "sub_type": "quick_reply", "index": "0",
                 "parameters": [{"type": "payload", "payload": button_payload(None, REENGAGE_BUTTON_ID)}]},
            ],
        },
    }


def _post_message(payload: dict) -> tuple[str | None, str | None, int | None]:
    """POST one Cloud API message. Returns (external_id, error, Meta error code)."""
    url = f"{GRAPH_URL}/{settings.whatsapp_api_version}/{settings.whatsapp_phone_number_id}/messages"
    try:
        resp = httpx.post(url, headers={"Authorization": f"Bearer {settings.whatsapp_token}"}, json=payload, timeout=15)
    except httpx.HTTPError as exc:
        return None, f"{type(exc).__name__}: {exc}", None
    if resp.status_code >= 400:
        try:
            code = resp.json().get("error", {}).get("code")
        except ValueError:
            code = None
        return None, f"HTTP {resp.status_code}: {resp.text[:500]}", code
    return (resp.json().get("messages") or [{}])[0].get("id"), None, None


def _send_reengage(msg_id: int, phone: str, client_name: str, firm_name: str) -> None:
    _external_id, error, _code = _post_message(_reengage_payload(phone, client_name, firm_name))
    if not error:
        return
    log.warning("WhatsApp re-engagement template failed for message %s: %s", msg_id, error)
    with SessionLocal() as db:
        msg = db.get(WhatsAppMessageLog, msg_id)
        if msg and msg.awaiting_window:
            msg.error_text = f"תבנית הפתיחה לא נשלחה, ההודעה תישלח כשהלקוח יכתוב: {error}"
            queue_event(db, {"type": "message", "client_id": msg.client_id, "ticket_id": msg.ticket_id})
            db.commit()


def upload_cloud_media(path: Path, mime: str) -> tuple[str | None, str | None]:
    """Upload a local file to the Cloud API media endpoint. Returns (media_id, error)."""
    url = f"{GRAPH_URL}/{settings.whatsapp_api_version}/{settings.whatsapp_phone_number_id}/media"
    try:
        content = path.read_bytes()
    except OSError as exc:
        return None, f"{type(exc).__name__}: {exc}"
    try:
        resp = httpx.post(url, headers={"Authorization": f"Bearer {settings.whatsapp_token}"},
                          data={"messaging_product": "whatsapp", "type": mime},
                          files={"file": (path.name, content, mime)}, timeout=60)
    except httpx.HTTPError as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if resp.status_code >= 400:
        return None, f"HTTP {resp.status_code}: {resp.text[:500]}"
    media_id = resp.json().get("id")
    return (media_id, None) if media_id else (None, "Cloud API media upload returned no id")


def _send_cloud_api(msg_id: int, phone: str, text: str, buttons: list[dict], ticket_id: int | None,
                    media_url: str | None = None, media_mime: str | None = None) -> None:
    media_id, kind, filename, error, code = None, "image", None, None, None
    if media_url:
        path = settings.upload_dir / Path(media_url).name
        mime = media_mime or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        kind, filename = _media_kind(mime, path.name), path.name
        media_id, upload_error = upload_cloud_media(path, mime)
        if upload_error:
            error = f"העלאת הקובץ ל-WhatsApp נכשלה: {upload_error}"
    if not error:
        external_id, error, code = _post_message(_cloud_payload(phone, text, buttons, ticket_id, media_id, kind, filename))

    with SessionLocal() as db:
        msg = db.get(WhatsAppMessageLog, msg_id)
        if not msg:
            return
        if code == WINDOW_CLOSED_ERROR:
            # Meta's clock says the window is closed (e.g. it closed while this message was queued): hold it.
            _hold(db, msg, msg.client)
        elif error:
            log.warning("WhatsApp Cloud API send failed for message %s: %s", msg_id, error)
            msg.delivery_status = DeliveryStatus.FAILED
            msg.error_text = error
        else:
            msg.external_id = external_id
        queue_event(db, {"type": "message", "client_id": msg.client_id, "ticket_id": msg.ticket_id})
        db.commit()


def download_cloud_media(media_id: str) -> tuple[bytes, str]:
    """Fetch an inbound image/document from the Cloud API. Returns (content, mime_type)."""
    headers = {"Authorization": f"Bearer {settings.whatsapp_token}"}
    meta = httpx.get(f"{GRAPH_URL}/{settings.whatsapp_api_version}/{media_id}", headers=headers, timeout=15)
    meta.raise_for_status()
    info = meta.json()
    content = httpx.get(info["url"], headers=headers, timeout=30)
    content.raise_for_status()
    return content.content, info.get("mime_type", "application/octet-stream")
