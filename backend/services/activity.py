"""Office activity log (audit trail). Written by the API routers, read by managers only."""
from __future__ import annotations

from sqlalchemy.orm import Session

from models import ActivityLog, User
from services.clock import utcnow
from services.events import queue_event

# action code -> Hebrew label shown in the "יומן פעילות" tab
ACTION_LABELS: dict[str, str] = {
    "LOGIN": "התחברות",
    "LOGIN_FAILED": "ניסיון התחברות כושל",
    "LOGOUT": "התנתקות",
    "TICKET_SENT": "שליחת בקשה ללקוח",
    "TICKET_APPROVED": "אישור חשבונית",
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
    "CAMPAIGN_SENT": "שליחת דיווח מס בתפוצה",
    "SCHEDULER_RUN": "הרצת מחזור תזכורות",
    "SIMULATOR_RECEIPT": "הדמיית קבלה בסימולטור",
}


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
