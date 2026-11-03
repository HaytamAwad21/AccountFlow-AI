"""Shared FastAPI dependencies: the authenticated office user and role enforcement.

The dashboard logs in with a password (`POST /api/auth/login`) and sends the returned token
as `Authorization: Bearer <token>` on every request. The server resolves the token to a live,
non-revoked, non-expired session of an active user; anything else is rejected with 401.
Manager-only endpoints additionally reject workers with 403.

Browsers cannot add that header to <img> tags or to the live-update stream, so login also sets the
same token as an HttpOnly, SameSite=Strict cookie. Only those read-only GETs (uploaded documents and
the event stream) accept the cookie; every API call still needs the header, so the cookie cannot be
used for cross-site requests.
"""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import ChasingTicket, Client, User, UserRole, UserSession
from services.clock import utcnow
from services.security import token_digest

MANAGER_ONLY = "הרשאת מנהל בלבד — פעולה זו זמינה למנהל/ת המשרד בלבד."
NOT_LOGGED_IN = "יש להתחבר למערכת עם שם משתמש וסיסמה"
SESSION_COOKIE = "accountflow_session"
DEMO_ONLY = "כלי הדגמה זמינים רק בהתקנת הדגמה. במשרד אמיתי הם היו שולחים הודעות ללקוחות אמיתיים."


def require_demo_mode() -> None:
    """Demo tools (simulated client replies, time jump, demo batches) on a demo install only."""
    if not settings.demo_mode:
        raise HTTPException(403, DEMO_ONLY)


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(SESSION_COOKIE, token, max_age=settings.session_hours * 3600, httponly=True,
                        samesite="strict", secure=settings.cookie_secure, path="/")


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="strict", secure=settings.cookie_secure)


def live_session(db: Session, token: str | None) -> UserSession | None:
    """The live session of an active user behind a token, or None."""
    if not token:
        return None
    session = db.scalar(select(UserSession).where(UserSession.token_hash == token_digest(token)))
    if session is None or session.revoked_at is not None or session.expires_at <= utcnow() or not session.user.is_active:
        return None
    return session


def request_session(db: Session, request: Request) -> UserSession | None:
    """The session behind the request's token header or, failing that, its session cookie."""
    return live_session(db, bearer_token(request.headers.get("authorization"))) or live_session(
        db, request.cookies.get(SESSION_COOKIE)
    )


def require_header_or_cookie(request: Request, db: Session = Depends(get_db)) -> User:
    """For GETs a browser makes on its own (<img src>, EventSource): the header or the session cookie."""
    session = request_session(db, request)
    if session is None:
        raise HTTPException(401, NOT_LOGGED_IN)
    return session.user


def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def current_session(db: Session = Depends(get_db), authorization: str | None = Header(default=None)) -> UserSession | None:
    token = bearer_token(authorization)
    if not token:
        return None
    session = db.scalar(select(UserSession).where(UserSession.token_hash == token_digest(token)))
    if session is None or session.revoked_at is not None or session.expires_at <= utcnow():
        raise HTTPException(401, "פג תוקף ההתחברות — יש להתחבר מחדש")
    if not session.user.is_active:
        raise HTTPException(401, "המשתמש הושעה — פנו למנהל/ת המשרד")
    return session


def current_user(session: UserSession | None = Depends(current_session)) -> User | None:
    """The logged-in user, or None for anonymous callers (e.g. the Meta webhook)."""
    return session.user if session else None


def require_user(user: User | None = Depends(current_user)) -> User:
    if user is None:
        raise HTTPException(401, NOT_LOGGED_IN)
    return user


def require_manager(user: User = Depends(require_user)) -> User:
    if user.role != UserRole.MANAGER:
        raise HTTPException(403, MANAGER_ONLY)
    return user


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "")[:64]


def get_client_or_404(db: Session, client_id: int) -> Client:
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(404, f"לקוח {client_id} לא נמצא")
    return client


def get_ticket_or_404(db: Session, ticket_id: int) -> ChasingTicket:
    ticket = db.get(ChasingTicket, ticket_id)
    if not ticket:
        raise HTTPException(404, f"פנייה {ticket_id} לא נמצאה")
    return ticket
