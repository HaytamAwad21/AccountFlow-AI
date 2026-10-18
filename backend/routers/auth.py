"""Login, logout and the current session.

POST /api/auth/login   {user_id, password} -> {token, expires_at, user}
POST /api/auth/logout  revokes the presented token
GET  /api/auth/me      the user behind the token
GET  /api/auth/users   public list of user cards for the login screen (no e-mails)
POST /api/auth/change-password  the logged-in user changes their own password

Failed attempts are written to the activity log; after LOGIN_MAX_FAILURES failures within
LOGIN_LOCKOUT_MINUTES the user is temporarily locked (HTTP 429).
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import ActivityLog, User, UserRole, UserSession
from routers.deps import bearer_token, client_ip, current_session, require_user
from schemas import ChangePasswordRequest, LoginRequest, LoginResponse, LoginUser, UserOut, user_out
from services.activity import log_activity
from services.clock import utcnow
from services.security import hash_password, new_session_token, password_problem, token_digest, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/users", response_model=list[LoginUser])
def login_users(db: Session = Depends(get_db)):
    stmt = select(User).order_by((User.role != UserRole.MANAGER), User.id)
    return [LoginUser.model_validate(u) for u in db.scalars(stmt)]


def _recent_failures(db: Session, user_id: int) -> int:
    since = utcnow() - timedelta(minutes=settings.login_lockout_minutes)
    last_success = db.scalar(
        select(func.max(ActivityLog.created_at)).where(ActivityLog.user_id == user_id, ActivityLog.action == "LOGIN")
    )
    if last_success and last_success > since:
        since = last_success
    return db.scalar(
        select(func.count(ActivityLog.id)).where(
            ActivityLog.user_id == user_id, ActivityLog.action == "LOGIN_FAILED", ActivityLog.created_at > since
        )
    ) or 0


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    user = db.get(User, body.user_id)
    if user is None:
        raise HTTPException(401, "שם משתמש או סיסמה שגויים")
    if not user.is_active:
        raise HTTPException(403, "המשתמש הושעה — פנו למנהל/ת המשרד")
    if _recent_failures(db, user.id) >= settings.login_max_failures:
        raise HTTPException(429, f"יותר מדי ניסיונות כושלים. נסו שוב בעוד {settings.login_lockout_minutes} דקות.")
    if not verify_password(body.password, user.password_hash):
        log_activity(db, user, "LOGIN_FAILED", f"ניסיון התחברות עם סיסמה שגויה לחשבון של {user.full_name}", ip_address=ip)
        db.commit()
        raise HTTPException(401, "הסיסמה שגויה")

    token = new_session_token()
    now = utcnow()
    session = UserSession(
        user_id=user.id,
        token_hash=token_digest(token),
        created_at=now,
        expires_at=now + timedelta(hours=settings.session_hours),
        ip_address=ip,
        user_agent=(request.headers.get("user-agent") or "")[:300],
    )
    db.add(session)
    log_activity(db, user, "LOGIN", f"{user.full_name} התחבר/ה למערכת", ip_address=ip)
    db.commit()
    return LoginResponse(token=token, expires_at=session.expires_at, user=user_out(user))


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db), authorization: str | None = Header(default=None)):
    token = bearer_token(authorization)
    if not token:
        return {"ok": True}
    session = db.scalar(select(UserSession).where(UserSession.token_hash == token_digest(token)))
    if session and session.revoked_at is None:
        session.revoked_at = utcnow()
        log_activity(db, session.user, "LOGOUT", f"{session.user.full_name} התנתק/ה מהמערכת", ip_address=client_ip(request))
        db.commit()
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(require_user)):
    return user_out(user)


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    session: UserSession | None = Depends(current_session),
):
    if session is None:
        raise HTTPException(401, "יש להתחבר למערכת")
    user = session.user
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "הסיסמה הנוכחית שגויה")
    problem = password_problem(body.new_password)
    if problem:
        raise HTTPException(422, problem)
    user.password_hash = hash_password(body.new_password)
    # sign out every other browser of this user; keep the current one
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.id != session.id, UserSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    log_activity(db, user, "PASSWORD_CHANGED", f"{user.full_name} שינה/תה את הסיסמה האישית", entity_type="user",
                 entity_id=user.id, ip_address=client_ip(request))
    db.commit()
    return {"ok": True}
