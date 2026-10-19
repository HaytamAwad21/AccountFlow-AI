"""Strict typing for request variables: money amounts (with currency), dates, months and counts.

The "שליחת בקשה" form sends raw values (an amount like "1240.5" plus its currency, an ISO date
from the HTML date picker). `normalize_variables` validates every typed variable and returns the
exact strings the WhatsApp template renders and the ticket stores:

    amount 500 + ILS  -> "500 ₪"        amount 1240.5 + USD -> "$1,240.50"
    2026-10-03        -> "03/10/2026"   2026-10 (tax_period) -> "10/2026"

Amounts that already carry a symbol ("₪1,180.00", "1,180 ₪", "$99") are accepted, and the
symbol decides the currency. Anything with letters or other characters is rejected.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

Currency = Literal["ILS", "USD"]
CURRENCIES: tuple[str, ...] = ("ILS", "USD")
DEFAULT_CURRENCY: Currency = "ILS"
CURRENCY_SYMBOLS: dict[str, str] = {"ILS": "₪", "USD": "$"}

AMOUNT_VARIABLES = frozenset({"amount", "charge_amount", "vat_amount", "tax_advance_amount", "expected_amount"})
DATE_VARIABLES = frozenset({"invoice_date", "charge_date", "due_date"})
MONTH_VARIABLES = frozenset({"tax_period"})
INTEGER_VARIABLES = frozenset({"days_left", "open_items_count"})

# Hebrew field names used in validation messages (same labels as the dashboard form).
VARIABLE_LABELS_HE: dict[str, str] = {
    "amount": "סכום ששולם",
    "charge_amount": "סכום החיוב",
    "vat_amount": "מע״מ לתשלום",
    "tax_advance_amount": "מקדמות מס",
    "expected_amount": "סכום צפוי",
    "invoice_date": "תאריך תשלום / חשבונית",
    "charge_date": "תאריך החיוב",
    "due_date": "מועד אחרון לתשלום",
    "tax_period": "תקופת דיווח",
    "days_left": "ימים שנותרו",
    "open_items_count": "פריטים פתוחים",
}

MAX_AMOUNT = Decimal("100000000")
MIN_YEAR, MAX_YEAR = 2000, 2100

# Plain number ("1240", "1240.5", "1,240.50") with at most 2 decimals.
_NUMBER_RE = re.compile(r"^(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?$")
_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_DMY_DATE_RE = re.compile(r"^(\d{1,2})[/.](\d{1,2})[/.](\d{4})$")
_ISO_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")
_MY_MONTH_RE = re.compile(r"^(\d{1,2})/(\d{4})$")


class VariableError(ValueError):
    """A typed variable failed validation; the message is Hebrew and names the field."""


def label(name: str) -> str:
    return VARIABLE_LABELS_HE.get(name, name)


def format_money(amount: Decimal | float | int, currency: str = DEFAULT_CURRENCY) -> str:
    """500 -> "500 ₪" / "$500"; 1240.5 -> "1,240.50 ₪" / "$1,240.50"."""
    value = Decimal(str(amount)).quantize(Decimal("0.01"))
    number = f"{value:,.0f}" if value == value.to_integral_value() else f"{value:,.2f}"
    if currency == "USD":
        return f"${number}"
    return f"{number} ₪"


def parse_money(raw: object, name: str = "amount") -> tuple[Decimal, Currency | None]:
    """Strictly parse an amount. Returns (value, currency from a ₪/$ symbol or None)."""
    text = str(raw if raw is not None else "").strip()
    symbol_currency: Currency | None = None
    if "₪" in text or "$" in text:
        if "₪" in text and "$" in text:
            raise VariableError(f"{label(name)}: יש לבחור מטבע אחד בלבד")
        symbol_currency = "ILS" if "₪" in text else "USD"
        text = text.replace("₪", "").replace("$", "").strip()
    if not _NUMBER_RE.fullmatch(text):
        raise VariableError(f"{label(name)}: נא להזין מספרים בלבד")
    try:
        value = Decimal(text.replace(",", ""))
    except InvalidOperation as exc:
        raise VariableError(f"{label(name)}: נא להזין מספרים בלבד") from exc
    if value <= 0:
        raise VariableError(f"{label(name)}: הסכום חייב להיות גדול מאפס")
    if value > MAX_AMOUNT:
        raise VariableError(f"{label(name)}: הסכום גדול מדי")
    return value, symbol_currency


def parse_date(raw: object, name: str = "date") -> date:
    """Accepts the HTML date picker's "YYYY-MM-DD" or "DD/MM/YYYY"; must be a real calendar date."""
    text = str(raw if raw is not None else "").strip()
    m = _ISO_DATE_RE.fullmatch(text)
    if m:
        y, mo, d = (int(g) for g in m.groups())
    else:
        m = _DMY_DATE_RE.fullmatch(text)
        if not m:
            raise VariableError(f"{label(name)}: תאריך לא תקין")
        d, mo, y = (int(g) for g in m.groups())
    try:
        parsed = date(y, mo, d)
    except ValueError as exc:
        raise VariableError(f"{label(name)}: תאריך לא תקין") from exc
    if not MIN_YEAR <= parsed.year <= MAX_YEAR:
        raise VariableError(f"{label(name)}: תאריך לא תקין")
    return parsed


def format_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def parse_month(raw: object, name: str = "tax_period") -> tuple[int, int]:
    """Accepts the HTML month picker's "YYYY-MM" or "MM/YYYY". Returns (month, year)."""
    text = str(raw if raw is not None else "").strip()
    m = _ISO_MONTH_RE.fullmatch(text)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
    else:
        m = _MY_MONTH_RE.fullmatch(text)
        if not m:
            raise VariableError(f"{label(name)}: חודש לא תקין")
        month, year = int(m.group(1)), int(m.group(2))
    if not (1 <= month <= 12 and MIN_YEAR <= year <= MAX_YEAR):
        raise VariableError(f"{label(name)}: חודש לא תקין")
    return month, year


def parse_count(raw: object, name: str) -> int:
    text = str(raw if raw is not None else "").strip()
    if not re.fullmatch(r"\d{1,5}", text):
        raise VariableError(f"{label(name)}: נא להזין מספר שלם בלבד")
    return int(text)


def normalize_variables(variables: dict, currencies: dict[str, str] | None = None) -> tuple[dict, list[str]]:
    """Validate and format every typed variable. Returns (normalized variables, Hebrew errors).

    Empty values are left as they are: required-field checks happen in the ticket engine.
    """
    currencies = currencies or {}
    out = dict(variables)
    errors: list[str] = []
    for name, raw in variables.items():
        if raw is None or str(raw).strip() == "":
            continue
        try:
            if name in AMOUNT_VARIABLES:
                value, symbol_currency = parse_money(raw, name)
                chosen = currencies.get(name)
                if symbol_currency and chosen and chosen != symbol_currency:
                    raise VariableError(f"{label(name)}: המטבע שנבחר אינו תואם לסימן המטבע")
                out[name] = format_money(value, chosen or symbol_currency or DEFAULT_CURRENCY)
            elif name in DATE_VARIABLES:
                out[name] = format_date(parse_date(raw, name))
            elif name in MONTH_VARIABLES:
                month, year = parse_month(raw, name)
                out[name] = f"{month:02d}/{year}"
            elif name in INTEGER_VARIABLES:
                out[name] = str(parse_count(raw, name))
        except VariableError as exc:
            errors.append(str(exc))
    for name in currencies:
        if name not in AMOUNT_VARIABLES:
            errors.append(f"{label(name)}: לשדה זה אין מטבע")
    return out, errors
