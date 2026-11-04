"""Office activity log (audit trail). Written by the API routers, read by managers only.

Only meaningful operational events are recorded: sessions (login / logout), requests and
reminders sent to clients, tax broadcasts, invoice / ticket decisions and management changes.
Failed logins are NOT activity: they are tracked separately (models.LoginFailure) for lockout.

Each row also names the device ("Chrome · Windows"): every computer in an office reaches an internet server
from the office's one public address, so the address alone cannot tell the office's computers apart.
"""
from __future__ import annotations

from contextvars import ContextVar

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from models import ActivityLog, User
from services.clock import utcnow
from services.events import queue_event

# The device of the HTTP request being handled (set by a middleware in main.py); empty for the scheduler.
request_device: ContextVar[str] = ContextVar("request_device", default="")

_BROWSERS = (("Edg/", "Edge"), ("OPR/", "Opera"), ("SamsungBrowser/", "Samsung Internet"), ("Firefox/", "Firefox"),
             ("FxiOS/", "Firefox"), ("CriOS/", "Chrome"), ("Chrome/", "Chrome"), ("Safari/", "Safari"))
_SYSTEMS = (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"), ("Windows", "Windows"),
            ("Mac OS X", "Mac"), ("CrOS", "ChromeOS"), ("Linux", "Linux"))


def describe_device(user_agent: str | None) -> str:
    """'Chrome · Windows' from a browser's User-Agent; empty when it is not a known browser or system."""
    agent = user_agent or ""
    browser = next((name for key, name in _BROWSERS if key in agent), "")
    system = next((name for key, name in _SYSTEMS if key in agent), "")
    return " · ".join(part for part in (browser, system) if part)

# action code -> Hebrew label shown in the "יומן פעילות" tab
ACTION_LABELS: dict[str, str] = {
    "LOGIN": "התחברות למערכת",
    "LOGOUT": "התנתקות מהמערכת",
    "TICKET_SENT": "שליחת בקשה ללקוח",
    "MANUAL_MESSAGE_SENT": "שליחת הודעה ידנית ללקוח",
    "MANUAL_BROADCAST_SENT": "שליחת הודעה ידנית לקבוצת לקוחות",
    "REMINDERS_SENT": "שליחת תזכורות",
    "CAMPAIGN_SENT": "שליחת דיווח מס בתפוצה",
    "TICKET_APPROVED": "אישור חשבונית",
    "TICKET_REJECTED": "דחיית חשבונית",
    "TICKET_RESOLVED": "סגירת פנייה",
    "TICKET_REOPENED": "פתיחת פנייה מחדש",
    "OCR_EDITED": "תיקון שדות חשבונית",
    "CLIENT_CREATED": "הוספת לקוח",
    "CLIENT_UPDATED": "עדכון לקוח",
    "CLIENT_DEACTIVATED": "השבתת לקוח",
    "TEMPLATE_UPDATED": "עדכון תבנית הודעה",
    "SETTINGS_UPDATED": "עדכון הגדרות המשרד",
    "OFFICE_SETUP": "הקמת המשרד במערכת",
    "USER_CREATED": "הוספת עובד",
    "USER_UPDATED": "עדכון עובד",
    "PASSWORD_RESET": "איפוס סיסמה",
    "PASSWORD_CHANGED": "שינוי סיסמה אישית",
    "TWO_FACTOR_ENABLED": "הפעלת אימות דו-שלבי",
    "TWO_FACTOR_DISABLED": "כיבוי אימות דו-שלבי",
    "TWO_FACTOR_RESET": "איפוס אימות דו-שלבי לעובד",
}

# Action codes written by older releases that are no longer activity events.
REMOVED_ACTIONS = ("LOGIN_FAILED", "SIMULATOR_RECEIPT")
RENAMED_ACTIONS = {"SCHEDULER_RUN": "REMINDERS_SENT"}


def log_activity(
    db: Session,
    user: User | None,
    action: str,
    description: str,
    *,
    entity_type: str | None = None,
    entity_id: int | None = None,
    details: dict | None = None,
    ip_address: str = "",
) -> ActivityLog:
    """Add an audit row to the current transaction (it is saved together with the change it describes)."""
    entry = ActivityLog(
        user_id=user.id if user else None,
        action=action,
        description=description,
        entity_type=entity_type,
        entity_id=entity_id,
        details_json=details or None,
        ip_address=ip_address or "",
        device=request_device.get(),
        created_at=utcnow(),
    )
    db.add(entry)
    queue_event(db, {"type": "activity"})
    return entry


def cleanup_legacy_activity(db: Session) -> int:
    """Delete failed-login / simulator rows and rename old action codes. Idempotent; returns rows changed."""
    removed = db.execute(delete(ActivityLog).where(ActivityLog.action.in_(REMOVED_ACTIONS))).rowcount or 0
    renamed = 0
    for old, new in RENAMED_ACTIONS.items():
        renamed += db.execute(update(ActivityLog).where(ActivityLog.action == old).values(action=new)).rowcount or 0
    if removed or renamed:
        db.commit()
    return removed + renamed
