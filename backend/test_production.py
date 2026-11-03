"""Checks for a real office install: no demo data, first-run manager setup, and files and live updates
that need a login. Runs on a throw-away database with SEED_ON_STARTUP=false and reports every case:

    python test_production.py
"""
from __future__ import annotations

import logging
import os
import shutil
import sys
import tempfile
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


def old_schema_is_never_wiped(c: TestClient, state: dict) -> None:
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
    check(users == 1, "the office's users are still there", users)


CASES = [
    fresh_install_has_no_demo_data, setup_refuses_bad_input, setup_creates_the_first_manager, uploaded_files_need_a_login,
    live_updates_need_a_login, logout_clears_only_its_own_cookie, secure_cookie_when_configured, demo_tools_are_off,
    old_schema_is_never_wiped,
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
