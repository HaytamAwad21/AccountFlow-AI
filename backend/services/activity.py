"""Office activity log (audit trail). Written by the API routers, read by managers only.

Only meaningful operational events are recorded: sessions (login / logout), requests and
reminders sent to clients, tax broadcasts, invoice / ticket decisions and management changes.
Failed logins are NOT activity: they are tracked separately (models.LoginFailure) for lockout.
"""
from __future__ import annotations

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from models import ActivityLog, User
from services.clock import utcnow
from services.events import queue_event

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
    "USER_CREATED": "הוספת עובד",
    "USER_UPDATED": "עדכון עובד",
    "PASSWORD_RESET": "איפוס סיסמה",
    "PASSWORD_CHANGED": "שינוי סיסמה אישית",
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
