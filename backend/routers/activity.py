"""Manager-only activity log ("יומן פעילות")."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from models import ActivityLog, User
from routers.deps import require_manager
from schemas import ActivityOut, ActivityPage
from services.activity import ACTION_LABELS
from services.clock import local_to_utc

router = APIRouter(prefix="/api/activity", tags=["activity"])


@router.get("", response_model=ActivityPage)
def list_activity(
    user_id: int | None = None,
    action: str | None = None,
    date_from: str | None = Query(None, description="YYYY-MM-DD (office local time)"),
    date_to: str | None = Query(None, description="YYYY-MM-DD inclusive (office local time)"),
    q: str = "",
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _manager: User = Depends(require_manager),
):
    stmt = select(ActivityLog)
    if user_id:
        stmt = stmt.where(ActivityLog.user_id == user_id)
    if action:
        stmt = stmt.where(ActivityLog.action == action)
    if date_from:
        stmt = stmt.where(ActivityLog.created_at >= local_to_utc(datetime.fromisoformat(date_from)))
    if date_to:
        stmt = stmt.where(ActivityLog.created_at < local_to_utc(datetime.fromisoformat(date_to) + timedelta(days=1)))
    if q.strip():
        stmt = stmt.where(ActivityLog.description.ilike(f"%{q.strip()}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc()).offset(offset).limit(limit)).all()
    items = [
        ActivityOut(
            id=r.id,
            created_at=r.created_at,
            user_id=r.user_id,
            user_name=r.user.full_name if r.user else None,
            user_role=r.user.role if r.user else None,
            action=r.action,
            action_label=ACTION_LABELS.get(r.action, r.action),
            description=r.description,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            details=r.details_json,
            ip_address=r.ip_address,
        )
        for r in rows
    ]
    return ActivityPage(total=total, items=items, actions=ACTION_LABELS)
