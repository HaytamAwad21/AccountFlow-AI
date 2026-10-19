"""Strict no-emoji policy.

Customer-facing WhatsApp text, quick-reply buttons and dashboard data contain clean Hebrew text
only. `strip_emoji` removes pictographs (and the joiners / variation selectors that build them)
and tidies the whitespace they leave behind. `purge_emojis_from_db` cleans rows written by older
releases (templates, quick-reply buttons, chat history, firm name, activity log). It is
idempotent: rows without emojis are never touched.
"""
from __future__ import annotations

import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import ActivityLog, MessageTemplate, SystemSettings, WhatsAppMessageLog

log = logging.getLogger("accountflow.no_emoji")

# Pictographs, dingbats, misc symbols/technical (clocks, play buttons), keycap + ZWJ + variation selectors.
EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"
    "\u2300-\u23FF"
    "\u2600-\u27BF"
    "\u2B00-\u2BFF"
    "\u25B6\u25C0"
    "\u20E3\u200D\uFE0E\uFE0F"
    "]"
)
BUTTON_TEXT_KEYS = ("he", "en", "ar", "title")


def has_emoji(text: str | None) -> bool:
    return bool(text) and bool(EMOJI_RE.search(text))


def strip_emoji(text: str | None) -> str | None:
    """Remove emojis and the spacing around them. Text without emojis is returned unchanged."""
    if not has_emoji(text):
        return text
    out = EMOJI_RE.sub("", text)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"(?m)^[ \t]+", "", out)
    out = re.sub(r"(?m)[ \t]+$", "", out)
    out = re.sub(r"[ \t]+([!?.,:;])", r"\1", out)
    return out.strip()


def strip_buttons(buttons: list[dict] | None) -> list[dict] | None:
    if not buttons:
        return buttons
    return [{**b, **{k: strip_emoji(b[k]) for k in BUTTON_TEXT_KEYS if isinstance(b.get(k), str)}} for b in buttons]


def _buttons_have_emoji(buttons: list[dict] | None) -> bool:
    return any(has_emoji(b.get(k)) for b in (buttons or []) for k in BUTTON_TEXT_KEYS if isinstance(b.get(k), str))


def purge_emojis_from_db(db: Session) -> int:
    """Strip emojis from stored templates, buttons, chat history, firm name and activity rows."""
    changed = 0
    for tpl in db.scalars(select(MessageTemplate)):
        touched = False
        for field in ("name_he", "body_he"):
            if has_emoji(getattr(tpl, field)):
                setattr(tpl, field, strip_emoji(getattr(tpl, field)))
                touched = True
        if _buttons_have_emoji(tpl.buttons_json):
            tpl.buttons_json = strip_buttons(tpl.buttons_json)
            touched = True
        changed += int(touched)

    for msg in db.scalars(select(WhatsAppMessageLog)):
        touched = False
        if has_emoji(msg.content_text):
            msg.content_text = strip_emoji(msg.content_text) or ""
            touched = True
        if _buttons_have_emoji(msg.buttons_json):
            msg.buttons_json = strip_buttons(msg.buttons_json)
            touched = True
        changed += int(touched)

    for row in db.scalars(select(SystemSettings)):
        if has_emoji(row.firm_name):
            row.firm_name = strip_emoji(row.firm_name)
            changed += 1

    for entry in db.scalars(select(ActivityLog)):
        if has_emoji(entry.description):
            entry.description = strip_emoji(entry.description) or ""
            changed += 1

    if changed:
        db.commit()
        log.warning("Removed emojis from %d stored rows (templates, buttons, chat history, settings, activity)", changed)
    return changed
