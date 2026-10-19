"""Users, clients, templates, suppliers, office settings and dashboard KPIs.

Role rules (enforced here, mirrored in the UI):
  * MANAGER – add / edit / deactivate clients, edit templates, edit office settings, manage users.
  * WORKER  – read everything above; send messages, work the chasing board, approve invoices.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import (
    ChasingTicket,
    Client,
    MessageDirection,
    MessageTemplate,
    MessageType,
    TicketStatus,
    User,
    UserRole,
    UserSession,
    WhatsAppMessageLog,
)
from routers.deps import client_ip, get_client_or_404, require_manager, require_user
from schemas import (
    ClientIn,
    ClientOut,
    ClientUpdate,
    KpiOut,
    MessageOut,
    PreviewOut,
    PreviewRequest,
    SettingsOut,
    SettingsUpdate,
    TemplateOut,
    TemplateUpdate,
    UserIn,
    UserOut,
    UserUpdate,
    message_out,
    template_out,
    user_out,
)
from services.activity import log_activity
from services.clock import VAT_DEADLINE_DAY, days_until_deadline, fmt_date, local_to_utc, local_today, next_deadline, utcnow
from services.events import queue_event
from services.i18n import NAME_LANGUAGE_ERROR, has_arabic
from services.no_emoji import strip_buttons, strip_emoji
from services.scheduler import scheduler_status
from services.security import hash_password
from services.system_settings import get_system_settings
from services.templating import body_for, localized_buttons, render_text, text_direction
from services.ticket_engine import ACTIVE_STATUSES, CLIENT_PENDING_STATUSES, auto_variables, missing_variables
from services.vision_ocr import active_provider
from services.whatsapp import normalize_phone

router = APIRouter(prefix="/api", tags=["core"])


@router.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name, "time": utcnow().isoformat() + "Z"}


# ── users (office workers) ───────────────────────────────────────────────────

def initials_for(full_name: str) -> str:
    """'מאיה כהן - מנהלת משרד' -> 'מכ' (title after the dash is ignored)."""
    name = full_name.split(" - ")[0].strip()
    parts = [p for p in name.replace("-", " ").split() if p]
    if not parts:
        return "?"
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()


@router.get("/users", response_model=list[UserOut])
def list_users(include_inactive: bool = True, db: Session = Depends(get_db), _user: User = Depends(require_user)):
    stmt = select(User).order_by((User.role != UserRole.MANAGER), User.id)
    if not include_inactive:
        stmt = stmt.where(User.is_active.is_(True))
    return [user_out(u) for u in db.scalars(stmt)]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserIn, request: Request, db: Session = Depends(get_db), manager: User = Depends(require_manager)):
    if db.scalar(select(User).where(func.lower(User.email) == body.email.lower())):
        raise HTTPException(409, "כתובת האימייל כבר רשומה במערכת")
    user = User(full_name=body.full_name.strip(), job_title=body.job_title.strip(), email=body.email.lower(), role=body.role,
                is_active=body.is_active, avatar_initials=initials_for(body.full_name), password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    title = f" · {user.job_title}" if user.job_title else ""
    role_label = "מנהל משרד" if user.role == UserRole.MANAGER else "עובד משרד"
    status_label = "" if user.is_active else ", מושעה"
    log_activity(db, manager, "USER_CREATED", f"נוסף/ה עובד/ת: {user.full_name}{title} ({role_label}{status_label})",
                 entity_type="user", entity_id=user.id, ip_address=client_ip(request))
    queue_event(db, {"type": "users"})
    db.commit()
    return user_out(user)


def _active_manager_count(db: Session, exclude_id: int | None = None) -> int:
    stmt = select(func.count(User.id)).where(User.role == UserRole.MANAGER, User.is_active.is_(True))
    if exclude_id:
        stmt = stmt.where(User.id != exclude_id)
    return db.scalar(stmt) or 0


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, request: Request, db: Session = Depends(get_db),
                manager: User = Depends(require_manager)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "המשתמש לא נמצא")
    data = body.model_dump(exclude_unset=True)
    losing_manager = user.role == UserRole.MANAGER and (
        data.get("role") == UserRole.WORKER or data.get("is_active") is False
    )
    if losing_manager and _active_manager_count(db, exclude_id=user.id) == 0:
        raise HTTPException(409, "חייב להישאר לפחות מנהל/ת משרד פעיל/ה אחד/ת")
    changes: dict[str, list] = {}
    if "full_name" in data and data["full_name"] and data["full_name"].strip() != user.full_name:
        changes["full_name"] = [user.full_name, data["full_name"].strip()]
        user.full_name = data["full_name"].strip()
        user.avatar_initials = initials_for(user.full_name)
    if "job_title" in data and data["job_title"] is not None and data["job_title"].strip() != user.job_title:
        changes["job_title"] = [user.job_title, data["job_title"].strip()]
        user.job_title = data["job_title"].strip()
    if "role" in data and data["role"] is not None and data["role"] != user.role:
        changes["role"] = [user.role.value, data["role"].value]
        user.role = data["role"]
    if "is_active" in data and data["is_active"] is not None and data["is_active"] != user.is_active:
        changes["is_active"] = [user.is_active, data["is_active"]]
        user.is_active = data["is_active"]
    ip = client_ip(request)
    if changes.get("is_active") == [True, False]:
        # suspended: sign the user out everywhere
        db.execute(update(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
    if changes:
        labels = {"full_name": "שם", "job_title": "תפקיד במשרד", "role": "הרשאה", "is_active": "סטטוס"}
        log_activity(db, manager, "USER_UPDATED", f"עודכנו פרטי {user.full_name}: {', '.join(labels[k] for k in changes)}",
                     entity_type="user", entity_id=user.id, details=changes, ip_address=ip)
    if data.get("password"):
        user.password_hash = hash_password(data["password"])
        db.execute(update(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
        log_activity(db, manager, "PASSWORD_RESET", f"אופסה הסיסמה של {user.full_name}", entity_type="user", entity_id=user.id, ip_address=ip)
    queue_event(db, {"type": "users"})
    db.commit()
    return user_out(user)


# ── clients ──────────────────────────────────────────────────────────────────

def _clients_out(db: Session, clients: list[Client]) -> list[ClientOut]:
    ids = [c.id for c in clients]
    if not ids:
        return []
    open_counts = dict(
        db.execute(
            select(ChasingTicket.client_id, func.count(ChasingTicket.id))
            .where(ChasingTicket.client_id.in_(ids), ChasingTicket.status.in_(CLIENT_PENDING_STATUSES + (TicketStatus.NEEDS_CLERK_REVIEW,)))
            .group_by(ChasingTicket.client_id)
        ).all()
    )
    last_ids = dict(
        db.execute(
            select(WhatsAppMessageLog.client_id, func.max(WhatsAppMessageLog.id))
            .where(WhatsAppMessageLog.client_id.in_(ids))
            .group_by(WhatsAppMessageLog.client_id)
        ).all()
    )
    last_msgs = {
        m.client_id: m
        for m in db.scalars(select(WhatsAppMessageLog).where(WhatsAppMessageLog.id.in_(list(last_ids.values()) or [0])))
    }
    out = []
    for c in clients:
        item = ClientOut.model_validate(c)
        item.assigned_worker_name = c.assigned_worker.full_name if c.assigned_worker else None
        item.open_ticket_count = open_counts.get(c.id, 0)
        item.days_to_deadline = days_until_deadline(c.reporting_frequency)
        item.next_deadline = fmt_date(next_deadline(c.reporting_frequency))
        last = last_msgs.get(c.id)
        if last:
            item.last_message_at = last.created_at
            item.last_message_preview = (last.content_text or "קובץ מצורף")[:90]
        out.append(item)
    return out


@router.get("/clients", response_model=list[ClientOut])
def list_clients(q: str = "", include_inactive: bool = False, db: Session = Depends(get_db), _user: User = Depends(require_user)):
    stmt = select(Client)
    if not include_inactive:
        stmt = stmt.where(Client.is_active.is_(True))
    if q.strip():
        like = f"%{q.strip()}%"
        digits = "".join(ch for ch in q if ch.isdigit())
        conds = [Client.full_name.ilike(like), Client.company_name.ilike(like), Client.tax_id.ilike(like), Client.whatsapp_phone.ilike(like)]
        if digits:
            conds.append(Client.whatsapp_phone.ilike(f"%{digits}%"))
        stmt = stmt.where(or_(*conds))
    return _clients_out(db, list(db.scalars(stmt.order_by(Client.full_name))))


@router.get("/clients/{client_id}", response_model=ClientOut)
def get_client(client_id: int, db: Session = Depends(get_db), _user: User = Depends(require_user)):
    return _clients_out(db, [get_client_or_404(db, client_id)])[0]


def _check_unique(db: Session, *, phone: str | None = None, tax_id: str | None = None, exclude_id: int | None = None) -> None:
    if phone:
        stmt = select(Client).where(Client.whatsapp_phone == phone)
        if exclude_id:
            stmt = stmt.where(Client.id != exclude_id)
        if db.scalar(stmt):
            raise HTTPException(409, f"מספר הוואטסאפ {phone} כבר משויך ללקוח אחר")
    if tax_id:
        stmt = select(Client).where(Client.tax_id == tax_id, Client.is_active.is_(True))
        if exclude_id:
            stmt = stmt.where(Client.id != exclude_id)
        if db.scalar(stmt):
            raise HTTPException(409, f"מספר ח.פ / ע.מ {tax_id} כבר משויך ללקוח פעיל אחר")


def _check_names(*names: str | None) -> None:
    if any(has_arabic(n) for n in names):
        raise HTTPException(422, NAME_LANGUAGE_ERROR)


def _check_worker(db: Session, worker_id: int | None) -> None:
    if worker_id:
        worker = db.get(User, worker_id)
        if not worker or not worker.is_active:
            raise HTTPException(422, "העובד/ת שנבחר/ה אינו/ה קיים/ת או מושבת/ת")


@router.post("/clients", response_model=ClientOut, status_code=201)
def create_client(body: ClientIn, request: Request, db: Session = Depends(get_db), manager: User = Depends(require_manager)):
    data = body.model_dump()
    data["whatsapp_phone"] = normalize_phone(data["whatsapp_phone"])
    if len(data["whatsapp_phone"]) < 8:
        raise HTTPException(422, "מספר וואטסאפ לא תקין")
    _check_names(data["full_name"], data["company_name"])
    _check_unique(db, phone=data["whatsapp_phone"], tax_id=data["tax_id"])
    _check_worker(db, data.get("assigned_worker_id"))
    client = Client(**data)
    db.add(client)
    db.flush()
    log_activity(db, manager, "CLIENT_CREATED", f"נוסף לקוח: {client.full_name} ({client.company_name}) · ח.פ {client.tax_id}",
                 entity_type="client", entity_id=client.id, ip_address=client_ip(request))
    queue_event(db, {"type": "client", "client_id": client.id})
    db.commit()
    return _clients_out(db, [client])[0]


@router.put("/clients/{client_id}", response_model=ClientOut)
def update_client(client_id: int, body: ClientUpdate, request: Request, db: Session = Depends(get_db),
                  manager: User = Depends(require_manager)):
    client = get_client_or_404(db, client_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("whatsapp_phone"):
        data["whatsapp_phone"] = normalize_phone(data["whatsapp_phone"])
    _check_names(data.get("full_name"), data.get("company_name"))
    _check_unique(db, phone=data.get("whatsapp_phone"), tax_id=data.get("tax_id"), exclude_id=client.id)
    _check_worker(db, data.get("assigned_worker_id"))
    changes: dict[str, list] = {}
    for key, value in data.items():
        if key == "reporting_frequency" and value is None:
            continue
        old = getattr(client, key)
        if old != value:
            changes[key] = [getattr(old, "value", old), getattr(value, "value", value)]
        setattr(client, key, value)
    if changes:
        log_activity(db, manager, "CLIENT_UPDATED", f"עודכן הלקוח {client.full_name}: {', '.join(changes)}",
                     entity_type="client", entity_id=client.id, details=changes, ip_address=client_ip(request))
    queue_event(db, {"type": "client", "client_id": client.id})
    db.commit()
    return _clients_out(db, [client])[0]


@router.delete("/clients/{client_id}", response_model=ClientOut)
def deactivate_client(client_id: int, request: Request, db: Session = Depends(get_db), manager: User = Depends(require_manager)):
    """Soft delete: the client is deactivated and their open tickets are closed (history is kept)."""
    client = get_client_or_404(db, client_id)
    client.is_active = False
    now = utcnow()
    for ticket in db.scalars(select(ChasingTicket).where(ChasingTicket.client_id == client.id, ChasingTicket.status.in_(ACTIVE_STATUSES))):
        ticket.status = TicketStatus.RESOLVED
        ticket.resolved_at = now
        ticket.next_reminder_at = None
        ticket.resolution_note = "נסגר אוטומטית: הלקוח הושבת."
    log_activity(db, manager, "CLIENT_DEACTIVATED", f"הושבת הלקוח {client.full_name} ({client.company_name})",
                 entity_type="client", entity_id=client.id, ip_address=client_ip(request))
    queue_event(db, {"type": "client", "client_id": client.id})
    db.commit()
    return _clients_out(db, [client])[0]


@router.get("/clients/{client_id}/messages", response_model=list[MessageOut])
def client_messages(client_id: int, limit: int = Query(300, le=1000), db: Session = Depends(get_db), _user: User = Depends(require_user)):
    get_client_or_404(db, client_id)
    rows = db.scalars(
        select(WhatsAppMessageLog)
        .where(WhatsAppMessageLog.client_id == client_id)
        .order_by(WhatsAppMessageLog.created_at.desc(), WhatsAppMessageLog.id.desc())
        .limit(limit)
    ).all()
    return [message_out(m) for m in reversed(rows)]


# ── templates ────────────────────────────────────────────────────────────────

@router.get("/templates", response_model=list[TemplateOut])
def list_templates(db: Session = Depends(get_db), _user: User = Depends(require_user)):
    return [template_out(t) for t in db.scalars(select(MessageTemplate).order_by(MessageTemplate.id))]


@router.put("/templates/{template_id}", response_model=TemplateOut)
def update_template(template_id: int, body: TemplateUpdate, request: Request, db: Session = Depends(get_db),
                    manager: User = Depends(require_manager)):
    tpl = db.get(MessageTemplate, template_id)
    if not tpl:
        raise HTTPException(404, "התבנית לא נמצאה")
    data = body.model_dump(exclude_unset=True)
    if "buttons_json" in data:
        buttons = data.pop("buttons_json") or []
        if len(buttons) > 3:
            raise HTTPException(422, "וואטסאפ מאפשר עד 3 כפתורי תגובה מהירה")
        ids = [b["id"] for b in buttons]
        if len(ids) != len(set(ids)):
            raise HTTPException(422, "מזהי הכפתורים חייבים להיות ייחודיים")
        tpl.buttons_json = strip_buttons(buttons)
    for key, value in data.items():
        if isinstance(value, str):
            value = strip_emoji(value)
        if key.startswith("body_") and not str(value).strip():
            raise HTTPException(422, "גוף ההודעה אינו יכול להיות ריק")
        setattr(tpl, key, value)
    log_activity(db, manager, "TEMPLATE_UPDATED", f"עודכנה התבנית ”{tpl.name_he}“", entity_type="template", entity_id=tpl.id,
                 ip_address=client_ip(request))
    queue_event(db, {"type": "template", "template_id": tpl.id})
    db.commit()
    return template_out(tpl)


@router.post("/templates/{template_id}/preview", response_model=PreviewOut)
def preview_template(template_id: int, body: PreviewRequest, db: Session = Depends(get_db), _user: User = Depends(require_user)):
    tpl = db.get(MessageTemplate, template_id)
    if not tpl:
        raise HTTPException(404, "התבנית לא נמצאה")
    client = get_client_or_404(db, body.client_id)
    lang = "he"
    variables = {**auto_variables(db, client), **{k: str(v) for k, v in body.variables.items() if v not in (None, "")}}
    return PreviewOut(
        direction=text_direction(lang),
        text=render_text(body_for(tpl, lang), variables),
        buttons=localized_buttons(tpl, lang),
        missing=missing_variables(tpl, variables),
    )


# ── suppliers autocomplete ───────────────────────────────────────────────────

@router.get("/suppliers/suggestions", response_model=list[str])
def supplier_suggestions(client_id: int | None = None, q: str = "", limit: int = 12, db: Session = Depends(get_db), _user: User = Depends(require_user)):
    counts: dict[str, list] = {}
    for t in db.scalars(select(ChasingTicket).order_by(ChasingTicket.created_at.desc()).limit(2000)):
        names = {(t.context_variables_json or {}).get("supplier_name"), (t.ocr_validation_json or {}).get("supplier_name")}
        for name in filter(None, names):
            name = str(name).strip()
            if q and q.lower() not in name.lower():
                continue
            entry = counts.setdefault(name, [0, 0])
            entry[0] += 1
            if client_id and t.client_id == client_id:
                entry[1] += 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1][1], -kv[1][0], kv[0].lower()))
    return [name for name, _ in ranked[:limit]]


# ── office settings ──────────────────────────────────────────────────────────

def _settings_out(db: Session) -> SettingsOut:
    row = get_system_settings(db)
    return SettingsOut(
        id=row.id,
        firm_name=row.firm_name,
        vat_rate=row.vat_rate,
        allocation_number_threshold_nis=row.allocation_number_threshold_nis,
        reminder_interval_hours=row.reminder_interval_hours,
        max_reminders=row.max_reminders,
        vat_deadline_day=VAT_DEADLINE_DAY,
        auto_approve_verified=row.auto_approve_verified,
        updated_at=row.updated_at,
        updated_by_user_id=row.updated_by_user_id,
        updated_by_name=row.updated_by.full_name if row.updated_by else None,
        vision_provider=active_provider(),
        whatsapp_live=settings.whatsapp_live,
        timezone=settings.timezone,
        urgent_deadline_days=settings.urgent_deadline_days,
        scheduler=scheduler_status(),
    )


@router.get("/settings", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db), _user: User = Depends(require_user)):
    out = _settings_out(db)
    db.commit()  # persists the row if it was created on first access
    return out


@router.put("/settings", response_model=SettingsOut)
def update_settings(body: SettingsUpdate, request: Request, db: Session = Depends(get_db), manager: User = Depends(require_manager)):
    row = get_system_settings(db)
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    if "firm_name" in data:
        data["firm_name"] = data["firm_name"].strip()
    changes = {k: [getattr(row, k), v] for k, v in data.items() if getattr(row, k) != v}
    for key, value in data.items():
        setattr(row, key, value)
    if changes:
        labels = {"firm_name": "שם המשרד", "vat_rate": "שיעור מע״מ", "allocation_number_threshold_nis": "סף מספר הקצאה",
                  "reminder_interval_hours": "מרווח תזכורות", "max_reminders": "מספר תזכורות", "auto_approve_verified": "אישור אוטומטי"}
        summary = ", ".join(f"{labels.get(k, k)}: {old} ← {new}" for k, (old, new) in changes.items())
        log_activity(db, manager, "SETTINGS_UPDATED", f"עודכנו הגדרות המשרד — {summary}", entity_type="settings", entity_id=row.id,
                     details=changes, ip_address=client_ip(request))
    if "max_reminders" in data:
        # open chases follow the new limit immediately
        for ticket in db.scalars(select(ChasingTicket).where(ChasingTicket.status.in_(CLIENT_PENDING_STATUSES))):
            ticket.max_reminders = data["max_reminders"]
    row.updated_by_user_id = manager.id
    row.updated_at = utcnow()
    queue_event(db, {"type": "settings"})
    db.commit()
    db.refresh(row)
    return _settings_out(db)


# ── dashboard ────────────────────────────────────────────────────────────────

MINUTES_PER_AUTOMATED_MESSAGE = 4
MINUTES_PER_OCR_CHECK = 6


@router.get("/dashboard/kpis", response_model=KpiOut)
def kpis(db: Session = Depends(get_db), _user: User = Depends(require_user)):
    now = utcnow()
    month_start = local_to_utc(datetime.combine(local_today().replace(day=1), datetime.min.time()))

    def count_status(*statuses):
        return db.scalar(select(func.count(ChasingTicket.id)).where(ChasingTicket.status.in_(statuses))) or 0

    auto_reminders = db.scalar(
        select(func.count(WhatsAppMessageLog.id)).where(
            WhatsAppMessageLog.message_type == MessageType.AUTO_REMINDER, WhatsAppMessageLog.created_at >= month_start
        )
    ) or 0
    automated_msgs = db.scalar(
        select(func.count(WhatsAppMessageLog.id)).where(
            WhatsAppMessageLog.direction == MessageDirection.OUTBOUND, WhatsAppMessageLog.created_at >= month_start
        )
    ) or 0
    ocr_checks = db.scalar(
        select(func.count(WhatsAppMessageLog.id)).where(
            WhatsAppMessageLog.message_type == MessageType.OCR_FEEDBACK, WhatsAppMessageLog.created_at >= month_start
        )
    ) or 0
    resolved_week = db.scalar(
        select(func.count(ChasingTicket.id)).where(
            ChasingTicket.status == TicketStatus.RESOLVED, ChasingTicket.resolved_at >= now - timedelta(days=7)
        )
    ) or 0
    hours = round((automated_msgs * MINUTES_PER_AUTOMATED_MESSAGE + ocr_checks * MINUTES_PER_OCR_CHECK) / 60, 1)
    return KpiOut(
        active_waiting=count_status(TicketStatus.WAITING_FOR_CLIENT, TicketStatus.SNOOZED_TONIGHT, TicketStatus.OPEN),
        auto_reminders_this_month=auto_reminders,
        needs_clerk_review=count_status(TicketStatus.NEEDS_CLERK_REVIEW),
        resolved_this_week=resolved_week,
        escalated=count_status(TicketStatus.ESCALATED),
        needs_correction=count_status(TicketStatus.NEEDS_CORRECTION),
        estimated_hours_saved=hours,
        hours_saved_basis=(
            f"{automated_msgs} הודעות וואטסאפ אוטומטיות × {MINUTES_PER_AUTOMATED_MESSAGE} דק׳ + "
            f"{ocr_checks} בדיקות Vision AI × {MINUTES_PER_OCR_CHECK} דק׳ החודש"
        ),
    )
