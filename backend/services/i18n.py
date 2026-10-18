"""Hebrew system strings used by the automated engines.

WhatsApp contact with clients is Hebrew-only. Customer-facing *templates* live in the DB
(editable by the firm); these are the short engine replies: reminders, acknowledgements,
Vision AI feedback and Israel Tax Authority validation replies.
"""
from __future__ import annotations

import re
from collections import defaultdict

STRINGS: dict[str, dict[str, str]] = {
    # ── 48h friendly reminders ────────────────────────────────────────────
    "reminder_MISSING_INVOICE": {
        "he": "🔔 תזכורת ידידותית ({n}/{max}): אנחנו עדיין ממתינים לחשבונית מהספק '{supplier_name}' ({amount}, {invoice_date}). מספיק צילום ברור אחד 🙏",
    },
    "reminder_MISSING_DETAIL": {
        "he": "🔔 תזכורת ידידותית ({n}/{max}) לגבי חשבונית מס' {invoice_number} מהספק '{supplier_name}': עדיין חסר בה '{missing_detail}'. נא לשלוח עותק מתוקן או לכתוב כאן את הפרט החסר.",
    },
    "reminder_UNIDENTIFIED_CHARGE": {
        "he": "🔔 תזכורת ידידותית ({n}/{max}): עדיין צריך לסווג את החיוב על סך {charge_amount} מתאריך {charge_date} (אסמכתא: {bank_reference}). מספיקה לחיצה אחת למטה.",
    },
    "reminder_TAX_READY": {
        "he": "🔔 תזכורת ידידותית ({n}/{max}): התשלום עבור {tax_period} (מע\"מ {vat_amount}, מקדמות {tax_advance_amount}) לתשלום עד {due_date}. נא לאשר לאחר התשלום.",
    },
    "reminder_MONTHLY_FOLDER": {
        "he": "🔔 תזכורת ידידותית ({n}/{max}): אנחנו עדיין ממתינים ל-{open_items_count} פריטים חסרים לדיווח החודשי.",
    },
    "reminder_correction": {
        "he": "🔔 תזכורת ידידותית ({n}/{max}): אנחנו עדיין צריכים צילום ברור אחד של החשבונית מ-'{supplier_name}' — עמוד מלא ומספר החשבונית גלוי 📷",
    },
    "snooze_ping": {
        "he": "🌙 ערב טוב {client_name}! כמו שביקשת, הנה תזכורת עדינה:",
    },
    # ── Button acknowledgements ───────────────────────────────────────────
    "ack_SNOOZE_TONIGHT": {
        "he": "⏰ אין בעיה! נזכיר לך הערב בשעה {hour}:00.",
    },
    "ack_REQUEST_MEDIA": {
        "he": "📷 מצוין — נא לשלוח עכשיו צילום ברור או PDF של המסמך (עמוד מלא, תאורה טובה).",
    },
    "ack_TYPE_DETAIL": {
        "he": "✍️ בשמחה — נא לכתוב בהודעה הבאה את הפרט החסר ({missing_detail}).",
    },
    "ack_NO_DOCUMENT": {
        "he": "👍 תודה שעדכנת. רואה החשבון יבדוק את הפריט וייצור קשר עם הספק במידת הצורך.",
    },
    "ack_BUSINESS_NO_RECEIPT": {
        "he": "🏢 קיבלנו — נרשם כהוצאה עסקית ללא קבלה. תודה!",
    },
    "ack_PERSONAL_EXPENSE": {
        "he": "🏠 קיבלנו — נרשם כהוצאה פרטית (לא עסקית). תודה!",
    },
    "ack_PAID_CONFIRMED": {
        "he": "✅ תודה! התשלום עבור {tax_period} סומן כמאושר.",
    },
    "ack_PAY_LINK": {
        "he": "💳 אפשר לשלם בצורה מאובטחת כאן: {payment_link}\nלאחר התשלום נא ללחוץ 'שולם / מאושר'.",
    },
    "ack_REQUEST_CALL": {
        "he": "📞 רואה החשבון יתקשר אליך בהקדם.",
    },
    "ack_SEND_CLERK_ANYWAY": {
        "he": "👨‍💼 אין בעיה — העברנו את הצילום לרואה החשבון לבדיקה ידנית.",
    },
    "ack_text_detail": {
        "he": "🙏 תודה! הוספנו את '{text}' לרשומת החשבונית והעברנו לרואה החשבון לבדיקה.",
    },
    "ack_text_generic": {
        "he": "🙏 תודה! ההודעה שלך הועברה לרואה החשבון.",
    },
    "no_open_ticket": {
        "he": "📥 תודה! קיבלנו את ההודעה והעברנו אותה לרואה החשבון.",
    },
    "media_forwarded": {
        "he": "📥 התקבל! רואה החשבון יבדוק את המסמך בקרוב. תודה!",
    },
    # ── Vision AI results ─────────────────────────────────────────────────
    "ocr_verified": {
        "he": "✅ התקבלה ואומתה! חשבונית מס' {invoice_number} מאת {supplier_name} נקלטה במערכת. תודה!",
    },
    "reason_blurry": {
        "he": "הצילום מטושטש ולא ניתן לקרוא את מספר החשבונית",
    },
    "reason_missing_number": {
        "he": "מספר החשבונית לא מופיע במסמך — נא לוודא שמספר החשבונית נראה בצילום",
    },
    "reason_not_tax_invoice": {
        "he": "זה לא נראה כמו חשבונית מס (צריך את המסמך שכתוב עליו 'חשבונית מס', לא קבלה או שובר תשלום)",
    },
    "reason_wrong_supplier": {
        "he": "החשבונית היא מ-'{detected}' ולא מ-'{expected}'",
    },
    "reason_math_mismatch": {
        "he": "הסכומים לא מסתדרים (לפני מע\"מ {net} + מע\"מ {vat} ≠ סה\"כ {total})",
    },
    "reason_amounts_missing": {
        "he": "הסכומים (לפני מע\"מ, מע\"מ וסה\"כ) לא קריאים",
    },
    "reason_unreadable_file": {
        "he": "לא הצלחנו לפתוח את הקובץ ששלחת",
    },
    "reason_vat_rate_mismatch": {
        "he": "סכום המע\"מ אינו תואם לשיעור המע\"מ הנוכחי ({rate}%)",
    },
    "reason_invalid_tax_id": {
        "he": "מספר העוסק / ח.פ של הספק אינו תקין — הוא חייב להכיל בדיוק 9 ספרות",
    },
    "reason_missing_allocation": {
        "he": "חסר מספר הקצאה — חשבונית בסך {threshold} ₪ ומעלה לפני מע\"מ חייבת לכלול מספר הקצאה מרשות המסים",
    },
    "reason_invalid_allocation": {
        "he": "מספר ההקצאה בחשבונית אינו תקין — הוא חייב להכיל בדיוק 9 ספרות",
    },
    # ── Israeli Tax Authority typed-detail validation ─────────────────────
    "invalid_allocation_reply": {
        "he": "מספר ההקצאה שהזנת אינו תקין. לפי הוראות רשות המסים, מספר הקצאה חייב להכיל בדיוק 9 ספרות. אנא הקלד את המספר המדויק מחדש.",
    },
    "invalid_tax_id_reply": {
        "he": "מספר העוסק / ח.פ שהזנת אינו תקין. לפי הוראות רשות המסים, מספר ח.פ או עוסק מורשה חייב להכיל בדיוק 9 ספרות. אנא הקלד מספר תקין בן 9 ספרות.",
    },
    "ack_valid_allocation": {
        "he": "✅ תודה! מספר ההקצאה {value} נקלט ונבדק. רואה החשבון יעדכן את החשבונית.",
    },
    "ack_valid_tax_id": {
        "he": "✅ תודה! מספר העוסק / ח.פ {value} נקלט ונבדק. רואה החשבון יעדכן את החשבונית.",
    },
    "supplier_fallback": {"he": "החשבונית"},
}

# Keywords that tell the engine which Israeli tax identifier a "missing detail" request is about.
ALLOCATION_KEYWORDS = ("הקצאה", "allocation")
TAX_ID_KEYWORDS = ("ח.פ", "ח\"פ", "ח״פ", "ע.מ", "ע\"מ", "עוסק", "tax id", "vat number", "business id", "company number")


def classify_missing_detail(text: str | None) -> str | None:
    """'allocation_number' | 'tax_id' | None — drives the 9-digit validation of the client's typed reply."""
    lowered = (text or "").lower()
    if any(k in lowered for k in ALLOCATION_KEYWORDS):
        return "allocation_number"
    if any(k.lower() in lowered for k in TAX_ID_KEYWORDS):
        return "tax_id"
    return None

CONJUNCTION = " וגם "


class _Blank(defaultdict):
    def __missing__(self, key):  # noqa: D401 - unknown placeholders render as an em dash
        return "—"


def t(key: str, lang: str = "he", **values) -> str:
    """Hebrew text for `key`. `lang` is kept for call-site compatibility; messages are always Hebrew."""
    entry = STRINGS.get(key)
    if not entry:
        return key
    text = entry["he"]
    clean = {k: ("—" if v is None or str(v).strip() == "" else v) for k, v in values.items()}
    return text.format_map(_Blank(None, clean))


def join_reasons(reasons: list[str], lang: str = "he") -> str:
    if not reasons:
        return ""
    if len(reasons) == 1:
        return reasons[0]
    return CONJUNCTION.join(reasons)


# Arabic script (incl. supplements and presentation forms). Business and contact names may be
# written in Hebrew or English only.
ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
NAME_LANGUAGE_ERROR = "שם הלקוח ושם העסק יכולים להיות בעברית או באנגלית בלבד"


def has_arabic(text: str | None) -> bool:
    return bool(ARABIC_RE.search(text or ""))
