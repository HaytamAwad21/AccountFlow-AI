"""Checks for a real office install: no demo data, first-run manager setup, and files and live updates
that need a login. Runs on a throw-away database with SEED_ON_STARTUP=false and reports every case:

    python test_production.py
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import shutil
import struct
import sys
import tempfile
import time
import traceback
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="accountflow_prod_"))
SETUP_CODE = "test-setup-code-1234"
os.environ.update(
    DATABASE_URL=f"sqlite:///{(TMP / 'test.db').as_posix()}",
    SEED_ON_STARTUP="false",
    SETUP_CODE=SETUP_CODE,
    SCHEDULER_ENABLED="false",
    VISION_PROVIDER="local",
    OPENAI_API_KEY="",
    GEMINI_API_KEY="",
    WHATSAPP_TOKEN="",
    WHATSAPP_PHONE_NUMBER_ID="",
    WHATSAPP_APP_SECRET="",
    UPLOAD_DIR=str(TMP / "uploads"),
)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

import database  # noqa: E402
from config import settings  # noqa: E402
from main import app  # noqa: E402

logging.disable(logging.CRITICAL)

results = {"passed": 0, "failed": 0}
COOKIE = "accountflow_session"
ANON = {"Authorization": ""}
OWNER = {
    "setup_code": SETUP_CODE,
    "firm_name": "לוי ושות׳ רואי חשבון",
    "full_name": "רונית לוי",
    "job_title": "רואת חשבון",
    "email": "Ronit@Levi-CPA.co.il",
    "password": "strong-pass-2026",
}


def check(cond: bool, label: str, detail: object = "") -> None:
    if cond:
        results["passed"] += 1
        print(f"  ok   {label}")
    else:
        results["failed"] += 1
        print(f"  FAIL {label}  {detail}")


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def fresh_install_has_no_demo_data(c: TestClient, state: dict) -> None:
    check(c.get("/api/auth/users").json() == [], "no demo users on a real install")
    with database.SessionLocal() as db:
        clients = db.execute(text("SELECT COUNT(*) FROM clients")).scalar()
        templates = db.execute(text("SELECT COUNT(*) FROM message_templates")).scalar()
        offices = db.execute(text("SELECT COUNT(*) FROM system_settings")).scalar()
    check(clients == 0, "no demo clients", clients)
    check(templates == 6, "the 6 message templates are installed", templates)
    check(offices == 1, "the office settings row exists", offices)
    check(c.get("/api/auth/setup").json() == {"needed": True}, "setup is offered while there is no user")


def setup_refuses_bad_input(c: TestClient, state: dict) -> None:
    r = c.post("/api/auth/setup", json={**OWNER, "setup_code": "wrong"}, headers=ANON)
    check(r.status_code == 403, "a wrong setup code is refused (403)", r.text)
    r = c.post("/api/auth/setup", json={**OWNER, "password": "123"}, headers=ANON)
    check(r.status_code == 422, "a short password is refused (422)", r.text)
    r = c.post("/api/auth/setup", json={**OWNER, "email": "not-an-email"}, headers=ANON)
    check(r.status_code == 422, "a bad e-mail is refused (422)", r.text)
    r = c.post("/api/auth/setup", json={**OWNER, "firm_name": " "}, headers=ANON)
    check(r.status_code == 422, "an empty firm name is refused (422)", r.text)
    saved, settings.setup_code = settings.setup_code, ""
    try:
        r = c.post("/api/auth/setup", json={**OWNER, "setup_code": ""}, headers=ANON)
        check(r.status_code == 403 and "SETUP_CODE" in r.json()["detail"], "setup is closed while SETUP_CODE is not set", r.text)
    finally:
        settings.setup_code = saved
    check(c.get("/api/auth/users").json() == [], "nothing was created by refused attempts")


def setup_creates_the_first_manager(c: TestClient, state: dict) -> None:
    r = c.post("/api/auth/setup", json=OWNER, headers=ANON)
    check(r.status_code == 200, "setup succeeds with the right code", r.text)
    body = r.json()
    state["token"] = body["token"]
    check(body["user"]["role"] == "MANAGER" and body["user"]["email"] == "ronit@levi-cpa.co.il"
          and body["user"]["full_name"] == "רונית לוי" and body["user"]["job_title"] == "רואת חשבון",
          "the first user is a manager with a lowercase e-mail", body.get("user"))
    cookie = r.headers.get("set-cookie", "")
    check(COOKIE in cookie and "HttpOnly" in cookie and "samesite=strict" in cookie.lower(),
          "setup also sets the HttpOnly session cookie", cookie)
    check(c.get("/api/auth/me", headers=bearer(state["token"])).json()["id"] == body["user"]["id"], "the setup session is logged in")
    check(c.get("/api/settings", headers=bearer(state["token"])).json()["firm_name"] == OWNER["firm_name"], "the firm name is saved")
    check(c.get("/api/auth/setup").json() == {"needed": False}, "setup is no longer offered")
    r = c.post("/api/auth/setup", json={**OWNER, "email": "other@levi-cpa.co.il"}, headers=ANON)
    check(r.status_code == 409, "a second setup is refused (409)", r.text)
    cards = c.get("/api/auth/users").json()
    check(len(cards) == 1 and cards[0]["role"] == "MANAGER", "the login screen lists the new manager", cards)
    r = c.post("/api/auth/login", json={"user_id": cards[0]["id"], "password": OWNER["password"]}, headers=ANON)
    check(r.status_code == 200 and COOKIE in r.headers.get("set-cookie", ""), "the manager can log in and gets the cookie", r.text)
    state["login_token"] = r.json().get("token")


def uploaded_files_need_a_login(c: TestClient, state: dict) -> None:
    (settings.upload_dir / "in_secret.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    c.cookies.clear()
    check(c.get("/uploads/in_secret.png", headers=ANON).status_code == 401, "a document is refused without a login (401)")
    check(c.get("/uploads/in_secret.png", headers=bearer(state["token"])).status_code == 200, "a logged-in request gets the document")
    c.cookies.set(COOKIE, state["token"])
    r = c.get("/uploads/in_secret.png", headers=ANON)
    check(r.status_code == 200 and r.content.endswith(b"fake"), "the session cookie opens the document (for <img> tags)", r.status_code)
    check("no-store" in r.headers.get("cache-control", "") or "private" in r.headers.get("cache-control", ""),
          "documents are not cached by shared proxies", r.headers.get("cache-control"))
    check(c.get("/uploads/missing.png", headers=ANON).status_code == 404, "an unknown file is 404")
    check(c.get("/uploads/..%2Ftest.db", headers=ANON).status_code in (400, 404), "a path outside the upload folder is refused")
    c.cookies.set(COOKIE, "not-a-real-session")
    check(c.get("/uploads/in_secret.png", headers=ANON).status_code == 401, "a forged cookie is refused (401)")
    c.cookies.clear()


def live_updates_need_a_login(c: TestClient, state: dict) -> None:
    check(c.get("/api/events/stream", headers=ANON).status_code == 401, "the live-update stream is refused without a login (401)")


def logout_clears_only_its_own_cookie(c: TestClient, state: dict) -> None:
    other = c.post("/api/auth/login", json={"user_id": c.get("/api/auth/users").json()[0]["id"], "password": OWNER["password"]},
                   headers=ANON).json()["token"]
    c.cookies.clear()
    c.cookies.set(COOKIE, other)
    r = c.post("/api/auth/logout", headers=bearer(state["login_token"]))
    check(r.status_code == 200 and COOKIE not in r.headers.get("set-cookie", ""),
          "revoking an older session leaves the current cookie alone", r.headers.get("set-cookie"))
    r = c.post("/api/auth/logout", headers=bearer(other))
    cookie = r.headers.get("set-cookie", "")
    check(COOKIE in cookie and ("Max-Age=0" in cookie or "expires=Thu, 01 Jan 1970" in cookie),
          "logging out clears the browser's own cookie", cookie)
    c.cookies.clear()
    c.cookies.set(COOKIE, other)
    check(c.get("/uploads/in_secret.png", headers=ANON).status_code == 401, "a logged-out cookie no longer opens documents")
    c.cookies.clear()


def secure_cookie_when_configured(c: TestClient, state: dict) -> None:
    saved, settings.cookie_secure = settings.cookie_secure, True
    try:
        r = c.get("/api/auth/me", headers=bearer(state["token"]))
        cookie = r.headers.get("set-cookie", "")
        check(COOKIE in cookie and "Secure" in cookie, "COOKIE_SECURE=true marks the cookie Secure (HTTPS only)", cookie)
    finally:
        settings.cookie_secure = saved


def demo_tools_are_off(c: TestClient, state: dict) -> None:
    M = bearer(state["token"])
    check(c.get("/api/settings", headers=M).json().get("demo_mode") is False, "settings report a real office (demo_mode false)")
    r = c.post("/api/clients", headers=M, json={"full_name": "דוד כהן", "company_name": "כהן מוסכים", "tax_id": "514782301",
                                                 "whatsapp_phone": "0521234567"})
    check(r.status_code == 201, "the manager adds a real client", r.text)
    client_id = r.json().get("id")
    r = c.post("/api/campaigns/demo-batch", headers=M)
    check(r.status_code == 403, "the demo tax batch (made-up amounts to real clients) is refused", r.text)
    r = c.post("/api/scheduler/simulate-time-jump?hours=48", headers=M)
    check(r.status_code == 403, "the +48h time jump (early reminders) is refused", r.text)
    r = c.post("/api/simulator/demo-receipt", headers=M, json={"client_id": client_id, "scenario": "clear"})
    check(r.status_code == 403, "demo invoices are refused", r.text)
    r = c.post("/api/webhook/whatsapp-inbound", headers=M, json={"client_id": client_id, "text": "שלום"})
    check(r.status_code == 403, "staff cannot post a message as if the client wrote it", r.text)
    r = c.post("/api/webhook/whatsapp-inbound", headers=M, data={"client_id": str(client_id)},
               files={"file": ("x.png", b"\x89PNG\r\n\x1a\nfake", "image/png")})
    check(r.status_code == 403, "staff cannot upload a file as if the client sent it", r.text)
    r = c.post(f"/api/simulator/{client_id}/read", headers=M)
    check(r.status_code == 200 and r.json().get("updated") == 0, "opening the chat does not fake read receipts", r.text)


def totp(secret: str, offset: int = 0) -> str:
    """RFC 6238 code (30 s steps, 6 digits, SHA-1), written independently of the app's own code."""
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    step = int(time.time()) // 30 + offset
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    start = digest[-1] & 0x0F
    return f"{(struct.unpack('>I', digest[start:start + 4])[0] & 0x7FFFFFFF) % 1_000_000:06d}"


def two_step_login(c: TestClient, state: dict) -> None:
    M = bearer(state["token"])
    me = c.get("/api/auth/me", headers=M).json()
    check(me.get("two_factor_enabled") is False, "two-step login starts off", me)
    r = c.post("/api/auth/2fa/setup", headers=M)
    body = r.json() if r.status_code == 200 else {}
    secret = body.get("secret", "")
    check(r.status_code == 200 and len(secret) >= 32 and body.get("otpauth_uri", "").startswith("otpauth://totp/")
          and body.get("qr", "").startswith("data:image/png;base64,"), "setup gives a key and a QR code for the phone app", r.text[:200])
    check(c.get("/api/auth/me", headers=M).json().get("two_factor_enabled") is False, "a started setup is not on yet")
    check(c.post("/api/auth/2fa/enable", headers=M, json={"code": "000000"}).status_code == 400, "a wrong code does not turn it on")
    r = c.post("/api/auth/2fa/enable", headers=M, json={"code": totp(secret)})
    check(r.status_code == 200 and c.get("/api/auth/me", headers=M).json()["two_factor_enabled"] is True,
          "the code from the phone turns it on", r.text)
    acts = {a["action"] for a in c.get("/api/activity", headers=M).json()["items"]}
    check("TWO_FACTOR_ENABLED" in acts, "the activity log records it")

    me = c.get("/api/auth/me", headers=M).json()
    login = {"user_id": me["id"], "password": OWNER["password"]}
    for _ in range(6):  # a correct password without the code only asks for the code; it never locks the account
        r = c.post("/api/auth/login", json=login, headers=ANON)
    check(r.status_code == 401 and r.json()["detail"].get("code") == "two_factor_required",
          "the password alone is not enough: the code is asked for", r.text)
    r = c.post("/api/auth/login", json={**login, "code": "123456"}, headers=ANON)
    check(r.status_code == 401 and r.json()["detail"].get("code") == "two_factor_invalid", "a wrong code is refused", r.text)
    r = c.post("/api/auth/login", json={"user_id": me["id"], "password": "wrong-password", "code": totp(secret, 1)}, headers=ANON)
    check(r.status_code == 401, "a right code with a wrong password is refused")
    good = totp(secret, 1)
    r = c.post("/api/auth/login", json={**login, "code": good}, headers=ANON)
    check(r.status_code == 200, "password and code log in", r.text)
    state["token"] = r.json().get("token", state["token"])
    r = c.post("/api/auth/login", json={**login, "code": good}, headers=ANON)
    check(r.status_code == 401, "a code cannot be used twice (someone who saw it cannot replay it)", r.status_code)

    M = bearer(state["token"])
    r = c.post("/api/users", headers=M, json={"full_name": "עובדת בדיקה", "email": "w2fa@levi-cpa.test", "password": "worker-pass-1", "role": "WORKER"})
    worker_id = r.json()["id"]
    W = bearer(c.post("/api/auth/login", json={"user_id": worker_id, "password": "worker-pass-1"}, headers=ANON).json()["token"])
    w_secret = c.post("/api/auth/2fa/setup", headers=W).json()["secret"]
    c.post("/api/auth/2fa/enable", headers=W, json={"code": totp(w_secret)})
    staff = {u["id"]: u for u in c.get("/api/users", headers=M).json()}
    check(staff[worker_id].get("two_factor_enabled") is True, "the staff list shows who uses two-step login")
    check(c.post(f"/api/users/{me['id']}/reset-two-factor", headers=W).status_code == 403, "a worker cannot switch it off for others")
    r = c.post(f"/api/users/{worker_id}/reset-two-factor", headers=M)
    check(r.status_code == 200 and r.json().get("two_factor_enabled") is False, "a manager switches it off for a worker who lost the phone", r.text)
    check(c.post("/api/auth/login", json={"user_id": worker_id, "password": "worker-pass-1"}, headers=ANON).status_code == 200,
          "that worker logs in with the password again")
    check(c.get("/api/auth/me", headers=W).status_code == 401, "the reset signs out that worker's open sessions")

    check(c.post("/api/auth/2fa/disable", headers=M, json={"password": "wrong-password"}).status_code == 400,
          "switching it off needs the password")
    r = c.post("/api/auth/2fa/disable", headers=M, json={"password": OWNER["password"]})
    check(r.status_code == 200 and c.post("/api/auth/login", json=login, headers=ANON).status_code == 200,
          "with the password it switches off, and the password alone logs in again", r.text)


def old_schema_is_never_wiped(c: TestClient, state: dict) -> None:
    with database.SessionLocal() as db:
        before = db.execute(text("SELECT COUNT(*) FROM users")).scalar()
    with database.engine.begin() as conn:
        conn.execute(text("CREATE TABLE clerk_users (id INTEGER PRIMARY KEY)"))
    try:
        database.init_db()
        check(False, "an outdated schema stops the start-up instead of deleting data")
    except RuntimeError as e:
        check("SEED_ON_STARTUP" in str(e), "an outdated schema stops the start-up instead of deleting data", e)
    finally:
        with database.engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS clerk_users"))
    with database.SessionLocal() as db:
        users = db.execute(text("SELECT COUNT(*) FROM users")).scalar()
    check(users == before > 0, "the office's users are still there", (before, users))


CASES = [
    fresh_install_has_no_demo_data, setup_refuses_bad_input, setup_creates_the_first_manager, uploaded_files_need_a_login,
    live_updates_need_a_login, logout_clears_only_its_own_cookie, secure_cookie_when_configured, demo_tools_are_off,
    two_step_login, old_schema_is_never_wiped,
]


def main() -> int:
    state: dict = {}
    with TestClient(app, raise_server_exceptions=False) as c:
        for case in CASES:
            print(f"\n== {case.__name__}")
            try:
                case(c, state)
            except Exception:  # a crash in one case must not hide the others
                results["failed"] += 1
                print("  FAIL crashed:\n" + traceback.format_exc(limit=3))
    print(f"\n{results['passed']} passed, {results['failed']} failed")
    return 1 if results["failed"] else 0


if __name__ == "__main__":
    code = 1
    try:
        code = main()
    finally:
        database.engine.dispose()
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(code)
