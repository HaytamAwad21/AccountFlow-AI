"""Engine D: bulk "Tax is ready" broadcast from a CSV / Excel sheet."""
from __future__ import annotations

import io
import re
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import BulkTaxCampaign, BulkTaxRecipient, Client, PaymentStatus, ReportingFrequency
from services.clock import fmt_date, next_deadline
from services.demo_invoices import parse_amount
from services.money import format_money
from services.i18n import NAME_LANGUAGE_ERROR, has_arabic
from services.ticket_engine import EngineError, create_and_send_ticket, recount_campaign, template_by_slug, TAX_SLUG
from services.whatsapp import normalize_phone

NINE_DIGITS = re.compile(r"^\d{9}$")

REQUIRED_COLUMNS = [
    "client_tax_id",
    "client_phone",
    "client_name",
    "tax_period",
    "vat_amount",
    "tax_advance_amount",
    "due_date",
]
OPTIONAL_COLUMNS = ["national_insurance", "company_name", "payment_link", "reporting_frequency"]
COLUMN_ALIASES = {
    "tax_id": "client_tax_id",
    "business_id": "client_tax_id",
    "phone": "client_phone",
    "whatsapp": "client_phone",
    "name": "client_name",
    "period": "tax_period",
    "vat": "vat_amount",
    "income_tax_advance": "tax_advance_amount",
    "tax_advance": "tax_advance_amount",
    "ni": "national_insurance",
    "bituach_leumi": "national_insurance",
    "company": "company_name",
    "frequency": "reporting_frequency",
}


def fmt_ils(value: float) -> str:
    return format_money(value, "ILS")


def _norm_col(col: str) -> str:
    key = re.sub(r"[\s\-]+", "_", str(col).strip().lower())
    return COLUMN_ALIASES.get(key, key)


def read_sheet(content: bytes, filename: str) -> list[dict]:
    name = (filename or "").lower()
    if not content:
        raise EngineError("הקובץ שהועלה ריק")
    try:
        if name.endswith((".xlsx", ".xlsm", ".xls")):
            df = pd.read_excel(io.BytesIO(content), dtype=str)
        else:
            for encoding in ("utf-8-sig", "cp1255", "latin-1"):
                try:
                    text = content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, sep=None, engine="python")
    except EngineError:
        raise
    except Exception as exc:
        raise EngineError(f"לא ניתן לקרוא את הגיליון: {exc}") from exc

    df.columns = [_norm_col(c) for c in df.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise EngineError("חסרות עמודות חובה: " + ", ".join(missing))
    df = df.fillna("")
    rows = []
    for record in df.to_dict("records"):
        clean = {k: ("" if v is None else str(v).strip()) for k, v in record.items()}
        if any(clean.values()):
            rows.append(clean)
    return rows


def parse_due_date(value: str) -> str:
    value = (value or "").strip()
    for fmt in ("%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%Y-%m-%d %H:%M:%S"):
        try:
            return fmt_date(datetime.strptime(value, fmt))
        except ValueError:
            continue
    try:
        return fmt_date(pd.to_datetime(value, dayfirst=True).to_pydatetime())
    except Exception as exc:
        raise ValueError(f"invalid due_date '{value}'") from exc


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _tax_id(value: str) -> str:
    """Normalize a sheet's ח.פ / ע.מ to 9 digits. Excel drops the leading zero of IDs such as
    037845129, so an 8-digit number is zero-padded; anything else that isn't 9 digits stays invalid."""
    digits = _digits(value)
    if len(digits) == 8:
        digits = "0" + digits
    return digits


def match_or_create_client(db: Session, row: dict) -> tuple[Client, bool]:
    tax_id = _tax_id(row.get("client_tax_id", ""))
    phone = normalize_phone(row.get("client_phone", ""))
    client = None
    if tax_id:
        client = next((c for c in db.scalars(select(Client).where(Client.tax_id != "")) if c.tax_id == tax_id), None)
    if client is None and phone:
        client = db.scalar(select(Client).where(Client.whatsapp_phone == phone))
    if client:
        if not client.is_active:
            client.is_active = True
        return client, False

    name = row.get("client_name", "").strip()
    frequency = (row.get("reporting_frequency") or "").strip().upper()
    if frequency in ("BIMONTHLY", "BI-MONTHLY", "דו חודשי", "דו-חודשי"):
        frequency = ReportingFrequency.BIMONTHLY
    else:
        frequency = ReportingFrequency.MONTHLY
    client = Client(
        full_name=name,
        company_name=row.get("company_name") or name,
        tax_id=tax_id,
        whatsapp_phone=phone,
        reporting_frequency=frequency,
        notes="נוצר אוטומטית מקובץ דיווח מס.",
    )
    db.add(client)
    db.flush()
    return client, True


def _validate_row(index: int, row: dict) -> tuple[dict | None, str | None]:
    line = index + 2  # header is line 1
    name = row.get("client_name", "").strip()
    if not name:
        return None, f"שורה {line}: חסר שם לקוח (client_name)"
    if has_arabic(name) or has_arabic(row.get("company_name")):
        return None, f"שורה {line}: {NAME_LANGUAGE_ERROR}"
    tax_id = _tax_id(row.get("client_tax_id", ""))
    if tax_id and not NINE_DIGITS.match(tax_id):
        return None, f"שורה {line}: מספר ח.פ / ע.מ '{row.get('client_tax_id')}' אינו תקין — נדרשות בדיוק 9 ספרות"
    if not tax_id and not normalize_phone(row.get("client_phone", "")):
        return None, f"שורה {line}: נדרש ח.פ / ע.מ או מספר וואטסאפ"
    vat = parse_amount(row.get("vat_amount"))
    advance = parse_amount(row.get("tax_advance_amount"))
    if vat is None or advance is None:
        return None, f"שורה {line}: vat_amount ו-tax_advance_amount חייבים להיות מספרים"
    try:
        due = parse_due_date(row.get("due_date", ""))
    except ValueError:
        return None, f"שורה {line}: תאריך תשלום לא תקין '{row.get('due_date', '')}'"
    ni = parse_amount(row.get("national_insurance")) or 0.0
    period = row.get("tax_period", "").strip()
    if not period:
        return None, f"שורה {line}: חסרה תקופת דיווח (tax_period)"
    return {**row, "_vat": vat, "_advance": advance, "_ni": ni, "_due": due, "_period": period}, None


def run_bulk_campaign(db: Session, rows: list[dict], title: str | None = None, worker_id: int | None = None,
                      external: bool = True) -> dict:
    if not rows:
        raise EngineError("הקובץ אינו מכיל שורות נתונים")
    template = template_by_slug(db, TAX_SLUG)
    valid, errors = [], []
    for i, row in enumerate(rows):
        parsed, err = _validate_row(i, row)
        if err:
            errors.append(err)
        else:
            valid.append(parsed)
    if not valid:
        raise EngineError("אין שורות תקינות: " + "; ".join(errors[:5]))

    period = valid[0]["_period"]
    campaign = BulkTaxCampaign(title=title or f"דיווח מע\"מ ומקדמות {period}", tax_period=period)
    db.add(campaign)
    db.flush()

    created_clients = 0
    for row in valid:
        client, created = match_or_create_client(db, row)
        created_clients += int(created)
        variables = {
            "tax_period": row["_period"],
            "vat_amount": fmt_ils(row["_vat"]),
            "tax_advance_amount": fmt_ils(row["_advance"] + row["_ni"]),
            "due_date": row["_due"],
            "national_insurance": fmt_ils(row["_ni"]),
            "total_due": fmt_ils(row["_vat"] + row["_advance"] + row["_ni"]),
        }
        if row.get("payment_link"):
            variables["payment_link"] = row["payment_link"]
        ticket, _ = create_and_send_ticket(db, client=client, template=template, variables=variables,
                                           worker_id=worker_id, external=external)
        db.add(BulkTaxRecipient(
            campaign_id=campaign.id,
            client_id=client.id,
            ticket_id=ticket.id,
            vat_amount=row["_vat"],
            income_tax_advance=row["_advance"],
            national_insurance=row["_ni"],
            total_due=round(row["_vat"] + row["_advance"] + row["_ni"], 2),
            due_date=row["_due"],
            payment_status=PaymentStatus.SENT,
        ))
    db.flush()
    db.refresh(campaign)
    recount_campaign(db, campaign)
    return {"campaign": campaign, "errors": errors, "created_clients": created_clients, "sent": len(valid)}


def default_period_and_due() -> tuple[str, str]:
    """The next 26th-of-the-month VAT deadline and the (monthly) period it reports: the month before."""
    due = next_deadline()
    period_month = due.replace(day=1) - timedelta(days=1)
    return f"{period_month.month:02d}/{period_month.year}", fmt_date(due)


def sample_rows() -> list[dict]:
    period, due = default_period_and_due()
    return [
        {"client_tax_id": "514782301", "client_phone": "+972521234501", "client_name": "משה גבאי", "tax_period": period,
         "vat_amount": "4820.00", "tax_advance_amount": "2150.00", "due_date": due, "national_insurance": "640.00"},
        {"client_tax_id": "515903377", "client_phone": "+972541234502", "client_name": "יוסי מזרחי", "tax_period": period,
         "vat_amount": "12650.00", "tax_advance_amount": "5400.00", "due_date": due, "national_insurance": "1210.00"},
        {"client_tax_id": "516220945", "client_phone": "+972501234505", "client_name": "Michael Turner", "tax_period": period,
         "vat_amount": "3175.50", "tax_advance_amount": "1890.00", "due_date": due, "national_insurance": "0"},
    ]


def sample_sheet(fmt: str = "csv") -> tuple[bytes, str, str]:
    df = pd.DataFrame(sample_rows(), columns=REQUIRED_COLUMNS + ["national_insurance"])
    if fmt == "xlsx":
        buf = io.BytesIO()
        df.to_excel(buf, index=False, sheet_name="Monthly Tax")
        return buf.getvalue(), "accountflow_tax_sheet_sample.xlsx", \
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return df.to_csv(index=False).encode("utf-8-sig"), "accountflow_tax_sheet_sample.csv", "text/csv; charset=utf-8"


def demo_batch_rows(db: Session, limit: int = 8) -> list[dict]:
    clients = db.scalars(select(Client).where(Client.is_active.is_(True)).order_by(Client.id).limit(limit)).all()
    if not clients:
        raise EngineError("אין לקוחות פעילים לשליחת הדגמה")
    period, due = default_period_and_due()
    rows = []
    for i, c in enumerate(clients):
        vat = 1850 + (i * 1373) % 9200
        advance = 950 + (i * 811) % 4800
        rows.append({
            "client_tax_id": c.tax_id, "client_phone": c.whatsapp_phone, "client_name": c.full_name,
            "tax_period": period, "vat_amount": f"{vat:.2f}", "tax_advance_amount": f"{advance:.2f}",
            "due_date": due, "national_insurance": f"{(i * 157) % 900:.2f}",
        })
    return rows


def campaign_stats(campaign: BulkTaxCampaign) -> dict:
    counts = {s.value: 0 for s in PaymentStatus}
    for r in campaign.recipients:
        counts[r.payment_status.value] += 1
    total = len(campaign.recipients)
    return {
        "total": total,
        "sent": total,
        "pending": counts["SENT"] + counts["VIEWED"],
        "viewed": counts["VIEWED"],
        "confirmed_paid": counts["CONFIRMED_PAID"],
        "requested_call": counts["QUESTION_ASKED"],
        "total_due": round(sum(r.total_due for r in campaign.recipients), 2),
        "confirmed_amount": round(sum(r.total_due for r in campaign.recipients if r.payment_status == PaymentStatus.CONFIRMED_PAID), 2),
    }


__all__ = ["REQUIRED_COLUMNS", "campaign_stats", "demo_batch_rows", "read_sheet", "run_bulk_campaign", "sample_sheet"]

