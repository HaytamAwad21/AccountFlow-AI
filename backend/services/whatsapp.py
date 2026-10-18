"""WhatsApp adapter.

Every outbound message is (1) published to the in-app phone simulator over SSE and
(2) — when WHATSAPP_TOKEN + WHATSAPP_PHONE_NUMBER_ID are configured — sent through the
Meta WhatsApp Cloud API as an interactive quick-reply message. The Cloud API call runs
after the DB commit on a worker thread, so the clerk's request returns immediately.
"""
from __future__ import annotations

import logging
import re

import httpx
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal
from models import Client, DeliveryStatus, WhatsAppMessageLog
from services.events import queue_after_commit, queue_event

log = logging.getLogger("accountflow.whatsapp")

GRAPH_URL = "https://graph.facebook.com"
BUTTON_TITLE_MAX = 20  # Meta limit for reply-button titles
BODY_MAX = 1024


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


def dispatch(db: Session, msg: WhatsAppMessageLog, client: Client, buttons: list[dict] | None, external: bool = True) -> None:
    queue_event(db, {"type": "message", "client_id": client.id, "ticket_id": msg.ticket_id})
    if external and settings.whatsapp_live:
        msg_id, phone, text = msg.id, client.whatsapp_phone, msg.content_text
        btns = [dict(b) for b in (buttons or [])]
        ticket_id = msg.ticket_id
        queue_after_commit(db, lambda: _send_cloud_api(msg_id, phone, text, btns, ticket_id))


def _cloud_payload(phone: str, text: str, buttons: list[dict], ticket_id: int | None) -> dict:
    to = re.sub(r"\D", "", phone)
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


def _send_cloud_api(msg_id: int, phone: str, text: str, buttons: list[dict], ticket_id: int | None) -> None:
    url = f"{GRAPH_URL}/{settings.whatsapp_api_version}/{settings.whatsapp_phone_number_id}/messages"
    external_id, error = None, None
    try:
        resp = httpx.post(url, headers={"Authorization": f"Bearer {settings.whatsapp_token}"},
                          json=_cloud_payload(phone, text, buttons, ticket_id), timeout=15)
        if resp.status_code >= 400:
            error = f"HTTP {resp.status_code}: {resp.text[:500]}"
        else:
            external_id = (resp.json().get("messages") or [{}])[0].get("id")
    except httpx.HTTPError as exc:
        error = f"{type(exc).__name__}: {exc}"

    with SessionLocal() as db:
        msg = db.get(WhatsAppMessageLog, msg_id)
        if not msg:
            return
        if error:
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
