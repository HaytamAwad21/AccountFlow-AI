"""Time helpers. The DB stores naive UTC datetimes; business rules use the firm's local timezone."""
from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from config import settings

LOCAL_TZ = ZoneInfo(settings.timezone)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_local(dt_utc: datetime) -> datetime:
    return dt_utc.replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ)


def local_to_utc(dt_local: datetime) -> datetime:
    if dt_local.tzinfo is None:
        dt_local = dt_local.replace(tzinfo=LOCAL_TZ)
    return dt_local.astimezone(timezone.utc).replace(tzinfo=None)


def local_today(now_utc: datetime | None = None) -> date:
    return to_local(now_utc or utcnow()).date()


def next_local_hour(hour: int, now_utc: datetime | None = None) -> datetime:
    """Next occurrence of HH:00 local time (today if still ahead, otherwise tomorrow), as naive UTC."""
    now_local = to_local(now_utc or utcnow())
    target = datetime.combine(now_local.date(), time(hour=hour), tzinfo=LOCAL_TZ)
    if target <= now_local:
        target += timedelta(days=1)
    return local_to_utc(target)


# Israeli VAT reports and payments are due on the 26th of the reporting month (not configurable).
VAT_DEADLINE_DAY = 26


def _frequency(value) -> str:
    return str(getattr(value, "value", value) or "MONTHLY").upper()


def is_reporting_month(month: int, frequency="MONTHLY") -> bool:
    """Monthly reporters file every month. Bi-monthly periods (Jan–Feb, Mar–Apr, …) are filed in the
    month after the period ends, i.e. in the odd months: Jan, Mar, May, Jul, Sep, Nov."""
    return _frequency(frequency) != "BIMONTHLY" or month % 2 == 1


def next_deadline(frequency="MONTHLY", now_utc: datetime | None = None) -> date:
    """Next 26th-of-the-month VAT deadline for a client with the given reporting frequency."""
    today = local_today(now_utc)
    year, month = today.year, today.month
    if today.day > VAT_DEADLINE_DAY:
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    while not is_reporting_month(month, frequency):
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return date(year, month, min(VAT_DEADLINE_DAY, calendar.monthrange(year, month)[1]))


def days_until_deadline(frequency="MONTHLY", now_utc: datetime | None = None) -> int:
    return (next_deadline(frequency, now_utc) - local_today(now_utc)).days


def fmt_date(d: date | datetime) -> str:
    return d.strftime("%d/%m/%Y")
