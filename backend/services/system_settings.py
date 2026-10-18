"""Office configuration (single `system_settings` row) shared by every engine.

The row is created on first access from the env defaults in `config.py`; afterwards
managers edit it from the Settings tab and every engine reads the live values:
VAT rate (Vision AI math check + demo invoices), allocation-number threshold,
reminder cadence, max reminders and the firm name shown on WhatsApp. The VAT deadline is
not a setting: it is always the 26th (services/clock.py).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings as env
from models import SystemSettings


def get_system_settings(db: Session) -> SystemSettings:
    row = db.scalar(select(SystemSettings).order_by(SystemSettings.id).limit(1))
    if row is None:
        row = SystemSettings(
            firm_name=env.firm_name,
            vat_rate=round(env.vat_rate * 100, 2),
            allocation_number_threshold_nis=env.allocation_number_threshold_nis,
            reminder_interval_hours=env.reminder_interval_hours,
            max_reminders=env.default_max_reminders,
            auto_approve_verified=env.auto_approve_verified,
        )
        db.add(row)
        db.flush()
    return row


def vat_fraction(db: Session) -> float:
    """VAT as a fraction (18.0 % -> 0.18)."""
    return get_system_settings(db).vat_rate / 100.0


def firm_name(db: Session) -> str:
    return get_system_settings(db).firm_name


def auto_approve_enabled(db: Session) -> bool:
    return bool(get_system_settings(db).auto_approve_verified)
