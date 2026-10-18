"""Template variable extraction and interpolation. Templates are Hebrew-only."""
from __future__ import annotations

import re

from models import MessageTemplate

VAR_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

# Variables the engine always fills from the client record / live counters.
AUTO_VARIABLES = {"client_name", "company_name", "open_items_count", "days_left"}

RTL_LANGUAGES = {"ar", "he"}


def extract_variables(text: str) -> list[str]:
    seen: list[str] = []
    for name in VAR_RE.findall(text or ""):
        if name not in seen:
            seen.append(name)
    return seen


def template_variables(template: MessageTemplate) -> list[str]:
    names: list[str] = []
    for body in (template.body_he,):
        for name in extract_variables(body):
            if name not in names:
                names.append(name)
    return names


def required_variables(template: MessageTemplate) -> list[str]:
    return [v for v in template_variables(template) if v not in AUTO_VARIABLES]


def render_text(text: str, variables: dict) -> str:
    def _sub(match: re.Match) -> str:
        value = variables.get(match.group(1))
        if value is None or str(value).strip() == "":
            return "—"
        return str(value)

    return VAR_RE.sub(_sub, text or "")


def body_for(template: MessageTemplate, lang: str = "he") -> str:
    return template.body_he


def name_for(template: MessageTemplate, lang: str = "he") -> str:
    return template.name_he


def localized_buttons(template: MessageTemplate, lang: str) -> list[dict]:
    out = []
    for b in template.buttons_json or []:
        out.append({"id": b["id"], "title": b.get("he") or b["id"], "action": b.get("action", "")})
    return out


def text_direction(lang: str = "he") -> str:
    return "rtl"
