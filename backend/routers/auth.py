"""Login, logout and the current session.

POST /api/auth/login   {user_id, password} -> {token, expires_at, user}
POST /api/auth/logout  revokes the presented token
GET  /api/auth/me      the user behind the token
GET  /api/auth/users   public list of active user cards for the login screen (no e-mails)
GET  /api/auth/deadline-day  public VAT deadline day, for the logo on the login screen
POST /api/auth/change-password  the logged-in user changes their own password
POST /api/auth/2fa/setup | enable {code} | disable {password}  the logged-in user's two-step login
GET  /api/auth/setup   public: {"needed": true} while a new office has no user yet
POST /api/auth/setup   {setup_code, firm_name, full_name, job_title, email, password} creates the first manager

Login, setup and /me also set the session cookie (see routers/deps.py); logout clears it.

Wrong passwords are NOT written to the activity log. They are counted in `login_failures`;
after LOGIN_MAX_FAILURES failures within LOGIN_LOCKOUT_MINUTES the user is temporarily locked
(HTTP 429). A successful login clears the user's failures.
"""
from __future__ import annotations

import hmac
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import LoginFailure, User, UserRole, UserSession
from routers.deps import (SESSION_COOKIE, bearer_token, clear_session_cookie, client_ip, current_session, require_user,
                          set_session_cookie)
from schemas import (ChangePasswordRequest, FirstSetupRequest, LoginRequest, LoginResponse, LoginUser, PasswordConfirm,
                     TwoFactorCode, UserOut, user_out)
from services.activity import log_activity
from services.clock import utcnow
from services.security import (hash_password, new_session_token, new_totp_secret, otpauth_uri, password_problem, qr_data_uri,
                               token_digest, verify_password, verify_totp)
from services.system_settings import deadline_day, get_system_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _start_session(db: Session, user: User, request: Request, response: Response) -> LoginResponse:
    """A new login session for `user`: stored hashed, returned once, and set as the session cookie."""
    token = new_session_token()
    now = utcnow()
    session = UserSession(
        user_id=user.id,
        token_hash=token_digest(token),
        created_at=now,
        expires_at=now + timedelta(hours=settings.session_hours),
        ip_address=client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:300],
    )
    db.add(session)
    set_session_cookie(response, token)
    return LoginResponse(token=token, expires_at=session.expires_at, user=user_out(user))


@router.get("/setup")
def setup_status(db: Session = Depends(get_db)):
    return {"needed": db.scalar(select(User.id).limit(1)) is None}


@router.post("/setup", response_model=LoginResponse)
def first_setup(body: FirstSetupRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    from routers.core import initials_for

    if db.scalar(select(User.id).limit(1)) is not None:
        raise HTTPException(409, "המשרד כבר הוקם במערכת. יש להתחבר עם אחד המשתמשים הקיימים.")
    if not settings.setup_code:
        raise HTTPException(403, "הקמת המשרד סגורה: יש להגדיר SETUP_CODE בקובץ ההגדרות של השרת ולהפעיל אותו מחדש.")
    if not hmac.compare_digest(body.setup_code.strip().encode(), settings.setup_code.encode()):
        raise HTTPException(403, "קוד ההקמה שגוי. הקוד מופיע בקובץ ההגדרות של השרת (SETUP_CODE).")
    problem = password_problem(body.password)
    if problem:
        raise HTTPException(422, problem)
    office = get_system_settings(db)
    office.firm_name = body.firm_name
    user = User(full_name=body.full_name, job_title=body.job_title, email=body.email.strip().lower(), role=UserRole.MANAGER,
                is_active=True, avatar_initials=initials_for(body.full_name), password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    result = _start_session(db, user, request, response)
    log_activity(db, user, "OFFICE_SETUP", f"{user.full_name} הקים/ה את המשרד '{office.firm_name}' במערכת",
                 entity_type="user", entity_id=user.id, ip_address=client_ip(request))
    db.commit()
    return result


@router.get("/users", response_model=list[LoginUser])
def login_users(db: Session = Depends(get_db)):
    stmt = select(User).where(User.is_active.is_(True)).order_by((User.role != UserRole.MANAGER), User.id)
    return [LoginUser.model_validate(u) for u in db.scalars(stmt)]


@router.get("/deadline-day")
def public_deadline_day(db: Session = Depends(get_db)):
    return {"vat_deadline_day": deadline_day(db)}


def _recent_failures(db: Session, user_id: int) -> int:
    since = utcnow() - timedelta(minutes=settings.login_lockout_minutes)
    db.execute(delete(LoginFailure).where(LoginFailure.created_at <= since))  # purge expired attempts
    return db.scalar(
        select(func.count(LoginFailure.id)).where(LoginFailure.user_id == user_id, LoginFailure.created_at > since)
    ) or 0


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = client_ip(request)
    user = db.get(User, body.user_id)
    if user is None:
        raise HTTPException(401, "שם משתמש או סיסמה שגויים")
    if not user.is_active:
        raise HTTPException(403, "המשתמש הושעה — פנו למנהל/ת המשרד")
    if _recent_failures(db, user.id) >= settings.login_max_failures:
        raise HTTPException(429, f"יותר מדי ניסיונות כושלים. נסו שוב בעוד {settings.login_lockout_minutes} דקות.")
    if not verify_password(body.password, user.password_hash):
        db.add(LoginFailure(user_id=user.id, ip_address=ip, created_at=utcnow()))
        db.commit()
        raise HTTPException(401, "הסיסמה שגויה")
    if user.totp_enabled:
        # The right password without a code only asks for the code; a wrong code counts towards the lockout.
        if not (body.code or "").strip():
            raise HTTPException(401, {"code": "two_factor_required", "message": "יש להזין את הקוד בן 6 הספרות מאפליקציית האימות בטלפון"})
        step = verify_totp(user.totp_secret, body.code, user.totp_last_step)
        if step is None:
            db.add(LoginFailure(user_id=user.id, ip_address=ip, created_at=utcnow()))
            db.commit()
            raise HTTPException(401, {"code": "two_factor_invalid", "message": "הקוד שגוי או שכבר נוצל. יש להזין את הקוד שמופיע עכשיו באפליקציה."})
        user.totp_last_step = step

    result = _start_session(db, user, request, response)
    db.execute(delete(LoginFailure).where(LoginFailure.user_id == user.id))
    log_activity(db, user, "LOGIN", f"{user.full_name} התחבר/ה למערכת", ip_address=ip)
    db.commit()
    return result


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db), authorization: str | None = Header(default=None)):
    token = bearer_token(authorization)
    if not token:
        return {"ok": True}
    # Switching users revokes the replaced session after the new login: keep the new session's cookie.
    if request.cookies.get(SESSION_COOKIE) == token:
        clear_session_cookie(response)
    session = db.scalar(select(UserSession).where(UserSession.token_hash == token_digest(token)))
    if session and session.revoked_at is None:
        session.revoked_at = utcnow()
        log_activity(db, session.user, "LOGOUT", f"{session.user.full_name} התנתק/ה מהמערכת", ip_address=client_ip(request))
        db.commit()
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(request: Request, response: Response, user: User = Depends(require_user)):
    # A session restored from an earlier visit may predate the cookie, or the cookie may have expired.
    token = bearer_token(request.headers.get("authorization"))
    if token and request.cookies.get(SESSION_COOKIE) != token:
        set_session_cookie(response, token)
    return user_out(user)


@router.post("/2fa/setup")
def two_factor_setup(db: Session = Depends(get_db), user: User = Depends(require_user)):
    """A new authenticator key for the logged-in user. It takes effect only after /2fa/enable with a code."""
    if user.totp_enabled:
        raise HTTPException(409, "האימות הדו-שלבי כבר פעיל. כדי להחליף טלפון, יש לכבות אותו ולהפעיל מחדש.")
    user.totp_secret = new_totp_secret()
    user.totp_last_step = 0
    db.commit()
    uri = otpauth_uri(user.totp_secret, user.email, f"AccountFlow · {get_system_settings(db).firm_name}")
    return {"secret": user.totp_secret, "otpauth_uri": uri, "qr": qr_data_uri(uri)}


@router.post("/2fa/enable", response_model=UserOut)
def two_factor_enable(body: TwoFactorCode, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if user.totp_enabled:
        raise HTTPException(409, "האימות הדו-שלבי כבר פעיל")
    step = verify_totp(user.totp_secret, body.code, user.totp_last_step)
    if step is None:
        raise HTTPException(400, "הקוד שגוי. יש להזין את הקוד שמופיע עכשיו באפליקציה, אחרי סריקת הקוד.")
    user.totp_enabled = True
    user.totp_last_step = step
    log_activity(db, user, "TWO_FACTOR_ENABLED", f"{user.full_name} הפעיל/ה אימות דו-שלבי", entity_type="user",
                 entity_id=user.id, ip_address=client_ip(request))
    db.commit()
    return user_out(user)


@router.post("/2fa/disable", response_model=UserOut)
def two_factor_disable(body: PasswordConfirm, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(400, "הסיסמה שגויה")
    user.totp_enabled, user.totp_secret, user.totp_last_step = False, "", 0
    log_activity(db, user, "TWO_FACTOR_DISABLED", f"{user.full_name} כיבה/תה את האימות הדו-שלבי", entity_type="user",
                 entity_id=user.id, ip_address=client_ip(request))
    db.commit()
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
