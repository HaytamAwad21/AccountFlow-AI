"""Engine B endpoints: on-demand nag cycle and the +48h demo time machine."""
from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from database import get_db
from models import User
from routers.deps import client_ip, require_user
from schemas import SchedulerResult
from services.activity import log_activity
from services.scheduler import describe_reminder_actions, scheduler_status, simulate_time_jump, trigger_cycle

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


def _summary(actions: list[dict]) -> dict[str, int]:
    return dict(Counter(a["kind"] for a in actions))


@router.post("/trigger-48h-check", response_model=SchedulerResult)
def trigger_48h_check(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Run the reminder cycle now against the real clock."""
    actions = trigger_cycle(db)
    log_activity(db, user, "REMINDERS_SENT", f"שליחת תזכורות ידנית: {describe_reminder_actions(actions)}",
                 details={"source": "manual", **_summary(actions)}, ip_address=client_ip(request))
    db.commit()
    return SchedulerResult(actions=actions, summary=_summary(actions))


@router.post("/simulate-time-jump", response_model=SchedulerResult)
def time_jump(request: Request, hours: int = Query(48, ge=1, le=24 * 30), db: Session = Depends(get_db),
              user: User = Depends(require_user)):
    """Advance every pending reminder by `hours` and run the cycle immediately (sales-demo mode)."""
    shifted, actions = simulate_time_jump(db, hours)
    log_activity(db, user, "REMINDERS_SENT", f"שליחת תזכורות (הדמיית +{hours} שעות): {describe_reminder_actions(actions)}",
                 details={"source": "time_jump", **_summary(actions)}, ip_address=client_ip(request))
    db.commit()
    return SchedulerResult(shifted_tickets=shifted, actions=actions, summary=_summary(actions))


@router.get("/status")
def status():
    return scheduler_status()
