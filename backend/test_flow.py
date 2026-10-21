"""End-to-end verification of the AccountFlow AI backend.

Runs against a throw-away SQLite database with the background scheduler disabled and the
offline Vision simulator, exercising every engine through the real HTTP API:

    python test_flow.py
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="accountflow_test_"))
META_SECRET = "test-app-secret"
os.environ.update(
    DATABASE_URL=f"sqlite:///{(TMP / 'test.db').as_posix()}",
    SCHEDULER_ENABLED="false",
    VISION_PROVIDER="local",
    OPENAI_API_KEY="",
    GEMINI_API_KEY="",
    WHATSAPP_TOKEN="",
    WHATSAPP_PHONE_NUMBER_ID="",
    WHATSAPP_APP_SECRET=META_SECRET,
    AUTO_APPROVE_VERIFIED="false",
    UPLOAD_DIR=str(TMP / "uploads"),
)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

import services.clock as clock  # noqa: E402
import services.whatsapp as whatsapp_service  # noqa: E402
from config import settings  # noqa: E402
from main import app  # noqa: E402
from services.vision_ocr import validate_extraction  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from models import ActivityLog, LoginFailure, MessageTemplate  # noqa: E402
from services.activity import cleanup_legacy_activity  # noqa: E402
from services.no_emoji import has_emoji, purge_emojis_from_db  # noqa: E402
from services.scheduler import describe_reminder_actions  # noqa: E402

_real_local_today = clock.local_today


def freeze_day(day: int | None) -> None:
    """Pin 'today' to a day of the current month (None restores the real clock) so the
    26th-of-the-month deadline logic is deterministic whatever date the suite runs on."""
    if day is None:
        clock.local_today = _real_local_today
    else:
        clock.local_today = lambda now_utc=None: _real_local_today(now_utc).replace(day=day)

AR = re.compile(r"[\u0600-\u06FF]")
HE = re.compile(r"[֐-׿]")
ALLOCATION_REPLY = "מספר ההקצאה שהזנת אינו תקין. לפי הוראות רשות המסים, מספר הקצאה חייב להכיל בדיוק 9 ספרות. אנא הקלד את המספר המדויק מחדש."
passed = 0


def check(cond: bool, label: str, detail: object = "") -> None:
    global passed
    if not cond:
        print(f"  FAIL {label}  {detail}")
        raise AssertionError(label)
    passed += 1
    print(f"  ok   {label}")


def section(title: str) -> None:
    print(f"\n== {title}")


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


SEED_PASSWORDS = {"maya@cohen-cpa.co.il": "maya1234", "rami@cohen-cpa.co.il": "rami1234", "dana@cohen-cpa.co.il": "dana1234"}
ANON = {"Authorization": ""}


def login(c: TestClient, user_id: int, password: str) -> dict:
    r = c.post("/api/auth/login", json={"user_id": user_id, "password": password}, headers=ANON)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def meta_post(c: TestClient, envelope: dict, secret: str = META_SECRET, signature: str | None = None):
    """POST a Cloud API envelope the way Meta does: raw JSON, X-Hub-Signature-256, no session.
    `signature=""` sends no signature header."""
    raw = json.dumps(envelope).encode()
    if signature is None:
        signature = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    headers = {**ANON, "Content-Type": "application/json"}
    if signature:
        headers["X-Hub-Signature-256"] = signature
    return c.post("/api/webhook/whatsapp-inbound", content=raw, headers=headers)


def main() -> None:
    with TestClient(app) as c:
        section("Login with passwords")
        cards = c.get("/api/auth/users").json()
        check(all("email" not in u for u in cards) and len(cards) == 3, "public login list has 3 users and no e-mails")
        manager = next(u for u in cards if u["role"] == "MANAGER")
        worker = next(u for u in cards if u["role"] == "WORKER" and u["full_name"].startswith("ראמי"))
        dana = next(u for u in cards if u["full_name"].startswith("דנה"))
        check(c.get("/api/clients", headers=ANON).status_code == 401, "data endpoints require login (401)")
        check(c.put("/api/settings", json={"vat_rate": 5}, headers={**ANON, "X-User-Id": str(manager["id"])}).status_code == 401,
              "X-User-Id header alone no longer authenticates")
        r = c.post("/api/auth/login", json={"user_id": manager["id"], "password": "wrong-password"}, headers=ANON)
        check(r.status_code == 401 and r.json()["detail"] == "הסיסמה שגויה", "wrong password rejected")
        r = c.post("/api/auth/login", json={"user_id": manager["id"], "password": "maya1234"}, headers=ANON)
        check(r.status_code == 200 and len(r.json()["token"]) >= 40 and r.json()["user"]["role"] == "MANAGER", "manager logs in with password")
        M = {"Authorization": f"Bearer {r.json()['token']}"}
        W = login(c, worker["id"], "rami1234")
        c.headers.update(W)  # default identity for the rest of the run: the worker
        me = c.get("/api/auth/me", headers=M).json()
        check(me["id"] == manager["id"] and me["full_name"] == "מאיה כהן" and me["job_title"] == "מנהלת משרד",
              "/api/auth/me resolves the token (name and job title stored separately)")
        users = c.get("/api/users").json()
        check(bool(next(u for u in users if u["id"] == manager["id"])["avatar_initials"]), "avatar initials stored")
        for _ in range(5):
            c.post("/api/auth/login", json={"user_id": dana["id"], "password": "nope"}, headers=ANON)
        r = c.post("/api/auth/login", json={"user_id": dana["id"], "password": "dana1234"}, headers=ANON)
        check(r.status_code == 429, "5 failed attempts lock the account temporarily (429)")
        tmp = login(c, worker["id"], "rami1234")
        c.post("/api/auth/logout", headers=tmp)
        check(c.get("/api/auth/me", headers=tmp).status_code == 401, "logout revokes the session token")
        r = c.post("/api/auth/change-password", json={"current_password": "bad", "new_password": "rami5678"}, headers=W)
        check(r.status_code == 400, "change-password requires the current password")
        check(c.post("/api/auth/change-password", json={"current_password": "rami1234", "new_password": "rami5678"}, headers=W).status_code == 200
              and c.get("/api/auth/me", headers=W).status_code == 200, "user changes own password (current session kept)")
        check(c.post("/api/auth/login", json={"user_id": worker["id"], "password": "rami1234"}, headers=ANON).status_code == 401
              and c.post("/api/auth/login", json={"user_id": worker["id"], "password": "rami5678"}, headers=ANON).status_code == 200,
              "old password stops working, new one works")

        section("Seed data & office settings")

        s = c.get("/api/settings").json()
        check(s["firm_name"] == "כהן ושות׳ - רואי חשבון" and s["vat_rate"] == 18.0, "system_settings defaults (firm, 18% VAT)")
        check(s["allocation_number_threshold_nis"] == 10000 and s["reminder_interval_hours"] == 48 and s["max_reminders"] == 3,
              "allocation threshold 10,000 ₪ · 48h · 3 reminders")
        check(s["vat_deadline_day"] == 26 and "default_deadline_day" not in s, "VAT deadline fixed to the 26th (no setting)")
        check({cl["reporting_frequency"] for cl in c.get("/api/clients").json()} == {"MONTHLY", "BIMONTHLY"},
              "seeded clients report monthly and bi-monthly")

        templates = {t["slug"]: t for t in c.get("/api/templates").json()}
        check(len(templates) == 6, "6 Hebrew templates seeded")
        seeded = c.get("/api/clients").json()
        check(len(seeded) == 10, "10 demo clients seeded")
        check(all(re.fullmatch(r"\d{9}", cl["tax_id"]) for cl in seeded), "every seeded ח.פ / ע.מ has 9 digits")
        check(all(cl["assigned_worker_name"] for cl in seeded), "clients linked to a worker (FK users.id)")

        section("Role-based permissions")
        new = {"full_name": "שירה גולן", "company_name": "גולן עיצובים", "tax_id": "517011902",
               "whatsapp_phone": "0541119002"}
        check(c.post("/api/clients", json=new, headers=W).status_code == 403, "worker cannot add a client (403)")
        check(c.post("/api/clients", json=new, headers=ANON).status_code == 401, "anonymous caller cannot add a client (401)")
        check(c.put(f"/api/clients/{seeded[0]['id']}", json={"notes": "x"}, headers=W).status_code == 403, "worker cannot edit a client")
        check(c.delete(f"/api/clients/{seeded[0]['id']}", headers=W).status_code == 403, "worker cannot deactivate a client")
        check(c.put("/api/settings", json={"vat_rate": 17}, headers=W).status_code == 403, "worker cannot change the VAT rate")
        check(c.put(f"/api/templates/{templates['tax_ready_to_pay']['id']}", json={"name_en": "x"}, headers=W).status_code == 403,
              "worker cannot edit templates")
        check(c.post("/api/users", json={"full_name": "x y", "email": "x@y.co", "password": "secret1"}, headers=W).status_code == 403,
              "worker cannot add users")
        bad_tax = c.post("/api/clients", json={**new, "tax_id": "51701"}, headers=M)
        check(bad_tax.status_code == 422, "client ח.פ with 5 digits rejected (^\\d{9}$)")

        new_clients = {}
        for lang, name, phone, tax in (("he2", "יוסף ברק", "0521119001", "517011901"), ("he", "שירה גולן", "0541119002", "517011902"),
                                       ("en", "Olivia Grant", "0501119003", "517011903")):
            r = c.post("/api/clients", json={"full_name": name, "company_name": f"{name} Ltd", "tax_id": tax,
                                             "whatsapp_phone": phone,
                                             "assigned_worker_id": worker["id"]}, headers=M)
            check(r.status_code == 201 and "preferred_language" not in r.json(), f"manager creates client {name}", r.text[:200])
            new_clients[lang] = r.json()
        r = c.post("/api/clients", json={"full_name": "مازن جبران", "company_name": "Jubran Ltd", "tax_id": "517011904",
                                         "whatsapp_phone": "0521119004"}, headers=M)
        check(r.status_code == 422 and "עברית או באנגלית" in r.json()["detail"], "Arabic contact name rejected (Hebrew / English only)")
        r = c.post("/api/clients", json={"full_name": "Sami", "company_name": "مخبز الشرق", "tax_id": "517011905",
                                         "whatsapp_phone": "0521119005"}, headers=M)
        check(r.status_code == 422, "Arabic business name rejected")
        check(c.put(f"/api/clients/{new_clients['en']['id']}", json={"company_name": "شركة"}, headers=M).status_code == 422,
              "renaming a business to Arabic rejected")
        check(not any(AR.search(cl["full_name"] + cl["company_name"]) for cl in c.get("/api/clients").json()),
              "no Arabic-named businesses in the seed data")
        tpl_any = c.get("/api/templates").json()[0]
        check("body_he" in tpl_any and "body_en" not in tpl_any and "body_ar" not in tpl_any
              and all(set(b) == {"id", "action", "he"} for b in tpl_any["buttons_json"]), "templates are Hebrew-only")
        check(new_clients["he"]["whatsapp_phone"] == "+972541119002", "phone normalized to E.164")
        check(new_clients["he"]["reporting_frequency"] == "MONTHLY" and new_clients["he"]["next_deadline"].startswith("26/"),
              "new client defaults to monthly reporting, deadline on the 26th")
        r = c.put(f"/api/clients/{new_clients['he2']['id']}", json={"reporting_frequency": "BIMONTHLY"}, headers=M).json()
        check(r["reporting_frequency"] == "BIMONTHLY" and int(r["next_deadline"].split("/")[1]) % 2 == 1
              and r["next_deadline"].startswith("26/"), "bi-monthly client: deadline on the 26th of an odd month")
        check(c.put(f"/api/clients/{new_clients['he2']['id']}", json={"reporting_frequency": "WEEKLY"}, headers=M).status_code == 422,
              "invalid reporting frequency rejected")
        c.put(f"/api/clients/{new_clients['he2']['id']}", json={"reporting_frequency": "MONTHLY"}, headers=M)
        for day, freq, expected in ((10, "MONTHLY", 16), (26, "MONTHLY", 0), (27, "MONTHLY", None)):
            freeze_day(day)
            left = clock.days_until_deadline(freq)
            check(left == expected if expected is not None else left >= 27, f"day {day}: {left} days to the 26th")
        freeze_day(None)
        check(c.put(f"/api/clients/{new_clients['en']['id']}", json={"notes": "VIP"}, headers=M).json()["notes"] == "VIP",
              "manager edits a client")
        check(c.post("/api/users", json={"full_name": "יוסי לוי", "email": "yossi@cohen-cpa.co.il"}, headers=M).status_code == 422,
              "new worker requires a password")
        r = c.post("/api/users", json={"full_name": "יוסי לוי", "job_title": "מתמחה", "email": "yossi@cohen-cpa.co.il",
                                       "password": "yossi123"}, headers=M)
        check(r.status_code == 201 and r.json()["role"] == "WORKER" and r.json()["job_title"] == "מתמחה" and "password_hash" not in r.json(),
              "manager adds a worker with name, job title and password")
        intern = r.json()
        INTERN = login(c, intern["id"], "yossi123")
        r = c.put(f"/api/users/{intern['id']}", json={"role": "MANAGER"}, headers=M)
        check(r.json()["role"] == "MANAGER", "manager promotes a worker to MANAGER")
        c.put(f"/api/users/{intern['id']}", json={"role": "WORKER"}, headers=M)
        check(c.put(f"/api/users/{intern['id']}", json={"full_name": "האקר"}, headers=W).status_code == 403,
              "worker cannot edit users (PUT /api/users 403)")
        r = c.put(f"/api/users/{intern['id']}", json={"full_name": "יוסף לוי", "job_title": "פקיד הנה״ח", "is_active": False}, headers=M).json()
        check(r["full_name"] == "יוסף לוי" and r["job_title"] == "פקיד הנה״ח" and r["avatar_initials"] == "יל" and r["is_active"] is False,
              "manager renames and suspends a worker (initials recomputed)")
        check(c.get("/api/auth/me", headers=INTERN).status_code == 401, "suspended user's session is rejected by the API")
        check(c.post("/api/auth/login", json={"user_id": intern["id"], "password": "yossi123"}, headers=ANON).status_code == 403,
              "suspended user cannot log in")
        check(c.put(f"/api/users/{intern['id']}", json={"is_active": True}, headers=M).json()["is_active"] is True, "manager reactivates the worker")
        INTERN = login(c, intern["id"], "yossi123")
        check(c.put(f"/api/users/{intern['id']}", json={"password": "short"}, headers=M).status_code == 422, "reset password needs ≥ 6 characters")
        c.put(f"/api/users/{intern['id']}", json={"password": "yossi999"}, headers=M)
        check(c.get("/api/auth/me", headers=INTERN).status_code == 401, "password reset by manager signs the user out")
        check(c.post("/api/auth/login", json={"user_id": intern["id"], "password": "yossi999"}, headers=ANON).status_code == 200,
              "user logs in with the reset password")
        r = c.put(f"/api/users/{manager['id']}", json={"role": "WORKER"}, headers=M)
        check(r.status_code == 409, "last active manager cannot be demoted")

        section("Engine A — 3-second trigger (worker), Hebrew WhatsApp for Hebrew- and English-named businesses")
        check(c.post("/api/tickets/quick-send", json={"client_id": new_clients["he"]["id"], "template_slug": "missing_supplier_invoice",
                                                      "context_variables": {}}, headers=ANON).status_code == 401, "quick-send needs a logged-in user")
        tickets = {}
        tpl = templates["missing_supplier_invoice"]
        for lang, cl in new_clients.items():
            r = c.post("/api/tickets/quick-send", headers=W, json={
                "client_id": cl["id"], "template_id": tpl["id"],
                "context_variables": {"supplier_name": "Mega Office Supply", "amount": "₪1,180.00", "invoice_date": "03/10/2026"},
            })
            check(r.status_code == 201, f"[{lang}] worker quick-send created", r.text[:200])
            body = r.json()
            tk = body["ticket"]
            tickets[lang] = tk
            check(tk["status"] == "WAITING_FOR_CLIENT" and tk["worker_name"] == worker["full_name"], f"[{lang}] WAITING_FOR_CLIENT, attributed to worker")
            check(body["direction"] == "rtl", f"[{lang}] Hebrew message, right-to-left")
            check("{{" not in body["rendered_text"] and "Mega Office Supply" in body["rendered_text"], f"[{lang}] variables interpolated")
            check(body["rendered_text"].startswith("שלום") and not AR.search(body["rendered_text"]),
                  f"[{lang}] WhatsApp text is Hebrew (also for an English-named business)")
            gap = (parse_ts(tk["next_reminder_at"]) - parse_ts(tk["last_contacted_at"])).total_seconds() / 3600
            check(abs(gap - 48) < 0.01, f"[{lang}] next_reminder_at = now + 48h (from settings)")
            check(body["elapsed_ms"] < 100, f"[{lang}] server time {body['elapsed_ms']} ms < 100 ms")
            check(body["message"]["sender_name"] == "כהן ושות׳ - רואי חשבון", f"[{lang}] sent as the firm name from settings")
        r = c.post("/api/tickets/quick-send", headers=W, json={"client_id": new_clients["en"]["id"], "template_slug": "missing_invoice_detail",
                                                               "context_variables": {"supplier_name": "X"}})
        check(r.status_code == 422 and set(r.json()["missing"]) == {"invoice_number", "missing_detail"}, "missing variables rejected with 422")

        section("Strict variable types and currency (₪ / $)")
        check(body["ticket"]["context_variables_json"]["amount"] == "1,180 ₪" and "1,180 ₪" in body["rendered_text"],
              "symbol amount ₪1,180.00 stored and rendered as 1,180 ₪")
        typed_client = seeded[1]["id"]

        def typed_send(variables: dict, currencies: dict | None = None, slug: str = "missing_supplier_invoice"):
            payload = {"client_id": typed_client, "template_slug": slug, "context_variables": variables}
            if currencies is not None:
                payload["currencies"] = currencies
            return c.post("/api/tickets/quick-send", headers=W, json=payload)

        for bad, why in (("12a", "letters"), ("abc", "letters only"), ("1.234", "3 decimals"), ("-50", "negative"), ("0", "zero"),
                         ("1 000", "space"), ("₪$5", "two currencies")):
            r = typed_send({"supplier_name": "Typed Ltd", "amount": bad, "invoice_date": "2026-10-03"})
            check(r.status_code == 422, f"amount '{bad}' rejected ({why})", r.text[:160])
        r = typed_send({"supplier_name": "Typed Ltd", "amount": "12abc", "invoice_date": "2026-10-03"})
        check("נא להזין מספרים בלבד" in r.json()["detail"][0]["msg"], "Hebrew 'numbers only' message for letters in an amount")
        for bad in ("31/02/2026", "2026-13-01", "03-10-2026", "yesterday", "1/1/1999"):
            check(typed_send({"supplier_name": "Typed Ltd", "amount": "500", "invoice_date": bad}).status_code == 422, f"date '{bad}' rejected")
        check(typed_send({"supplier_name": "Typed Ltd", "amount": "500", "invoice_date": "2026-10-03"}, {"amount": "EUR"}).status_code == 422,
              "unsupported currency rejected")
        check(typed_send({"supplier_name": "Typed Ltd", "amount": "500", "invoice_date": "2026-10-03"}, {"supplier_name": "USD"}).status_code == 422,
              "currency on a non-money field rejected")
        check(typed_send({"supplier_name": "Typed Ltd", "amount": "$500", "invoice_date": "2026-10-03"}, {"amount": "ILS"}).status_code == 422,
              "currency selector must match a typed symbol")
        r = typed_send({"supplier_name": "Typed Ltd", "amount": "500", "invoice_date": "2026-10-03"})
        check(r.status_code == 201 and r.json()["ticket"]["context_variables_json"]["amount"] == "500 ₪"
              and "500 ₪" in r.json()["rendered_text"], "500 with the default currency becomes '500 ₪'")
        check(r.json()["ticket"]["context_variables_json"]["invoice_date"] == "03/10/2026" and "03/10/2026" in r.json()["rendered_text"],
              "HTML date 2026-10-03 stored and rendered as 03/10/2026")
        r = typed_send({"supplier_name": "Typed Ltd", "amount": "1240.5", "invoice_date": "03/10/2026"}, {"amount": "USD"})
        check(r.status_code == 201 and r.json()["ticket"]["context_variables_json"]["amount"] == "$1,240.50"
              and "$1,240.50" in r.json()["rendered_text"], "1240.5 in dollars becomes '$1,240.50'")
        r = typed_send({"tax_period": "2026-09", "vat_amount": "4820", "tax_advance_amount": "99.9", "due_date": "2026-10-26"},
                       {"vat_amount": "ILS", "tax_advance_amount": "USD"}, slug="tax_ready_to_pay")
        ctx = r.json()["ticket"]["context_variables_json"] if r.status_code == 201 else {}
        check(ctx.get("tax_period") == "09/2026" and ctx.get("vat_amount") == "4,820 ₪" and ctx.get("tax_advance_amount") == "$99.90"
              and ctx.get("due_date") == "26/10/2026", "month picker, per-field currencies and due date normalized", r.text[:200])
        check(typed_send({"tax_period": "13/2026", "vat_amount": "1", "tax_advance_amount": "1", "due_date": "2026-10-26"},
                         slug="tax_ready_to_pay").status_code == 422, "invalid month rejected")
        check(typed_send({"days_left": "3a", "open_items_count": "2"}, slug="monthly_folder_deadline_warning").status_code == 422,
              "counts must be whole numbers")

        section("Engine B — 48h auto-nagging & 26th-of-the-month escalation")
        freeze_day(10)  # 16 days before the 26th → friendly reminders only
        r = c.post("/api/scheduler/simulate-time-jump?hours=48").json()
        freeze_day(None)
        mine = {a["ticket_id"]: a for a in r["actions"]}
        for lang, tk in tickets.items():
            check(mine.get(tk["id"], {}).get("kind") == "FRIENDLY_REMINDER", f"[{lang}] friendly reminder dispatched")
        reminder = [m for m in c.get(f"/api/clients/{new_clients['he2']['id']}/messages").json() if m["message_type"] == "AUTO_REMINDER"][-1]
        check("תזכורת ידידותית" in reminder["content_text"] and "(1/3)" in reminder["content_text"], "Hebrew reminder with counter 1/3")
        check(not any(a["kind"] == "URGENT_DEADLINE_WARNING" for a in r["actions"]), "no urgent warnings 16 days before the 26th")
        freeze_day(24)  # 2 days before the 26th → monthly reporters get the deadline escalation
        r = c.post("/api/scheduler/simulate-time-jump?hours=48").json()
        freeze_day(None)
        urgent = [a for a in r["actions"] if a["kind"] == "URGENT_DEADLINE_WARNING"]
        check(len(urgent) >= 1, f"24th of the month → URGENT_DEADLINE_WARNING ({len(urgent)})")
        check("2" in next(m["content_text"] for m in c.get(f"/api/tickets/{urgent[0]['ticket_id']}").json()["messages"]
                          if m["message_type"] == "AUTO_REMINDER" and "תזכורת דחופה" in m["content_text"]), "warning says 2 days are left")
        check(c.get(f"/api/tickets/{urgent[0]['ticket_id']}").json()["priority"] == "URGENT_DEADLINE", "priority → URGENT_DEADLINE")

        section("Israel Tax Authority — typed allocation number (מספר הקצאה)")
        alloc = c.post("/api/tickets/quick-send", headers=W, json={
            "client_id": new_clients["he"]["id"], "template_slug": "missing_invoice_detail",
            "context_variables": {"supplier_name": "Ace Building Supplies", "invoice_number": "90233", "missing_detail": "מספר הקצאה"},
        }).json()["ticket"]
        check(alloc["context_variables_json"]["detail_kind"] == "allocation_number", "request classified as allocation number")
        c.post("/api/webhook/whatsapp-inbound", json={"client_id": new_clients["he"]["id"], "type": "button",
                                                      "button_id": "type_detail", "ticket_id": alloc["id"]})
        r = c.post("/api/webhook/whatsapp-inbound", json={"client_id": new_clients["he"]["id"], "type": "text",
                                                          "text": "12345", "ticket_id": alloc["id"]}).json()
        check(r["ticket"]["status"] == "NEEDS_CORRECTION", "5-digit allocation number → NEEDS_CORRECTION (ticket stays open)")
        check(r["reply"] == ALLOCATION_REPLY, "exact Hebrew Tax Authority auto-reply sent")
        check(r["validation"] == {"field": "allocation_number", "valid": False, "value": "12345"}, "validation result returned")
        last = c.get(f"/api/clients/{new_clients['he']['id']}/messages").json()[-1]
        check(last["direction"] == "OUTBOUND" and last["content_text"] == ALLOCATION_REPLY, "rejection logged as outbound WhatsApp")
        r = c.post("/api/webhook/whatsapp-inbound", json={"client_id": new_clients["he"]["id"], "type": "text", "text": "1234567890"}).json()
        check(r["ticket"]["id"] == alloc["id"] and r["ticket"]["status"] == "NEEDS_CORRECTION", "10 digits also rejected")
        r = c.post("/api/webhook/whatsapp-inbound", json={"client_id": new_clients["he"]["id"], "type": "text", "text": "12a456789"}).json()
        check(r["validation"]["valid"] is False, "letters inside the number rejected")
        r = c.post("/api/webhook/whatsapp-inbound", json={"client_id": new_clients["he"]["id"], "type": "text", "text": "123-456-789"}).json()
        check(r["ticket"]["status"] == "NEEDS_CLERK_REVIEW" and r["ticket"]["context_variables_json"]["allocation_number"] == "123456789",
              "valid 9-digit allocation number accepted → NEEDS_CLERK_REVIEW")

        section("Israel Tax Authority — typed ח.פ / עוסק מורשה")
        tid = c.post("/api/tickets/quick-send", headers=W, json={
            "client_id": new_clients["he2"]["id"], "template_slug": "missing_invoice_detail",
            "context_variables": {"supplier_name": "Al-Nour Supplies", "invoice_number": "5521", "missing_detail": "ח.פ של הספק"},
        }).json()["ticket"]
        check(tid["context_variables_json"]["detail_kind"] == "tax_id", "request classified as ח.פ / ע.מ")
        r = c.post("/api/webhook/whatsapp-inbound", json={"client_id": new_clients["he2"]["id"], "type": "text",
                                                          "text": "51477", "ticket_id": tid["id"]}).json()
        check(r["ticket"]["status"] == "NEEDS_CORRECTION" and "9 ספרות" in r["reply"],
              "invalid ח.פ rejected with an auto-reply asking for 9 digits")
        r = c.post("/api/webhook/whatsapp-inbound", json={"client_id": new_clients["he2"]["id"], "type": "text",
                                                          "text": "514778899", "ticket_id": tid["id"]}).json()
        check(r["ticket"]["status"] == "NEEDS_CLERK_REVIEW" and r["ticket"]["context_variables_json"]["tax_id"] == "514778899",
              "valid 9-digit ח.פ accepted")

        section("Engine C — Vision AI")
        r = c.post("/api/simulator/demo-receipt", json={"client_id": new_clients["he2"]["id"], "ticket_id": tickets["he2"]["id"], "scenario": "blurry"}).json()
        check(r["ticket"]["status"] == "NEEDS_CORRECTION" and r["ocr"]["rejection_codes"] == ["blurry"], "blurry photo → NEEDS_CORRECTION")
        check(r["elapsed_ms"] < 3000 and "מטושטש" in r["reply"], "Hebrew re-prompt in < 3 s")
        r = c.post("/api/simulator/demo-receipt", json={"client_id": new_clients["he"]["id"], "ticket_id": tickets["he"]["id"], "scenario": "missing_number"}).json()
        check("missing_number" in r["ocr"]["rejection_codes"] and "מספר החשבונית" in r["reply"], "missing invoice number rejected (Hebrew)")
        r = c.post("/api/simulator/demo-receipt", json={"client_id": new_clients["he"]["id"], "ticket_id": tickets["he"]["id"], "scenario": "clear"}).json()
        ocr = r["ocr"]
        check(r["ticket"]["status"] == "NEEDS_CLERK_REVIEW" and ocr["is_valid"] is True, "clear invoice verified → NEEDS_CLERK_REVIEW")
        check(ocr["checks"]["tax_id"] is True and re.fullmatch(r"\d{9}", ocr["business_id"]) is not None, "supplier ח.פ has 9 digits")
        check(abs(ocr["total_amount"] - 1180.0) < 0.01 and ocr["vat_rate_applied"] == 18.0, "₪1,180 total validated at 18% VAT")
        r = c.post("/api/simulator/demo-receipt", json={"client_id": new_clients["en"]["id"], "ticket_id": tickets["en"]["id"], "scenario": "invalid_tax_id"}).json()
        check("invalid_tax_id" in r["ocr"]["rejection_codes"], "invoice with a 6-digit supplier ח.פ rejected")
        r = c.post("/api/simulator/demo-receipt", json={"client_id": new_clients["en"]["id"], "ticket_id": tickets["en"]["id"], "scenario": "missing_allocation"}).json()
        check("missing_allocation" in r["ocr"]["rejection_codes"] and r["ocr"]["allocation_required"] is True,
              "invoice ≥ 10,000 ₪ without מספר הקצאה rejected")
        big = c.post("/api/tickets/quick-send", headers=W, json={"client_id": new_clients["en"]["id"], "template_slug": "missing_supplier_invoice",
                                                                 "context_variables": {"supplier_name": "Electra Wholesale", "amount": "₪23,600.00",
                                                                                       "invoice_date": "02/10/2026"}}).json()["ticket"]
        r = c.post("/api/simulator/demo-receipt", json={"client_id": new_clients["en"]["id"], "ticket_id": big["id"], "scenario": "clear"}).json()
        check(r["ocr"]["is_valid"] is True and re.fullmatch(r"\d{9}", r["ocr"]["allocation_number"] or "") is not None,
              "₪23,600 invoice with a 9-digit allocation number passes")

        section("Settings — live VAT rate & threshold drive validation")
        r = c.put("/api/settings", headers=M, json={"vat_rate": 17, "allocation_number_threshold_nis": 25000, "firm_name": "כהן ושות׳ - רו״ח",
                                                   "reminder_interval_hours": 24, "max_reminders": 4})
        check(r.status_code == 200 and r.json()["vat_rate"] == 17 and r.json()["updated_by_name"] == manager["full_name"],
              "manager saves settings (updated_by tracked)")
        ex18 = {"is_legible": True, "has_tax_invoice_header": True, "invoice_number": "1", "supplier_name": "A", "business_id": "514000111",
                "net_amount": 1000.0, "vat_amount": 180.0, "total_amount": 1180.0}
        check("vat_rate_mismatch" in validate_extraction(ex18, vat_rate=0.17)["rejection_codes"], "18% invoice rejected when VAT is 17%")
        check(validate_extraction(ex18, vat_rate=0.18)["is_valid"] is True, "same invoice passes at 18%")
        t17 = c.post("/api/tickets/quick-send", headers=W, json={"client_id": new_clients["he"]["id"], "template_slug": "missing_supplier_invoice",
                                                                 "context_variables": {"supplier_name": "Paz Oil", "amount": "₪1,170.00",
                                                                                       "invoice_date": "01/10/2026"}}).json()["ticket"]
        gap = (parse_ts(t17["next_reminder_at"]) - parse_ts(t17["last_contacted_at"])).total_seconds() / 3600
        check(abs(gap - 24) < 0.01 and t17["max_reminders"] == 4, "new tickets use 24h cadence & 4 reminders")
        r = c.post("/api/simulator/demo-receipt", json={"client_id": new_clients["he"]["id"], "ticket_id": t17["id"], "scenario": "clear"}).json()
        check(r["ocr"]["is_valid"] is True and r["ocr"]["vat_rate_applied"] == 17.0 and abs(r["ocr"]["vat_amount"] - 170.0) < 0.01,
              "OCR validator now checks VAT at 17%")
        last = c.get(f"/api/clients/{new_clients['he']['id']}/messages").json()[-1]
        check(last["sender_name"] == "כהן ושות׳ - רו״ח", "WhatsApp sender uses the new firm name")
        r = c.put("/api/settings", headers=M, json={"default_deadline_day": 5}).json()
        check("default_deadline_day" not in r and r["vat_deadline_day"] == 26, "deadline day cannot be changed (always the 26th)")
        c.put("/api/settings", headers=M, json={"vat_rate": 18, "allocation_number_threshold_nis": 10000, "reminder_interval_hours": 48, "max_reminders": 3})

        section("Real uploads, buttons, escalation")
        sharp = Image.new("RGB", (1000, 1300), "white")
        d = ImageDraw.Draw(sharp)
        for i in range(40):
            d.text((60, 60 + i * 30), f"Line {i} TAX INVOICE 4711 total 1,180.00 ILS supplier Mega Office Supply", fill="black")
        buf = io.BytesIO()
        sharp.filter(ImageFilter.GaussianBlur(6)).save(buf, format="JPEG", quality=80)
        r = c.post("/api/webhook/whatsapp-inbound", data={"client_id": str(new_clients["en"]["id"]), "ticket_id": str(tickets["en"]["id"])},
                   files={"file": ("blurry.jpg", buf.getvalue(), "image/jpeg")}).json()
        check(r["ocr"]["is_blurry"] is True, "real blurry JPEG rejected by blur detector")
        snooze = c.post("/api/tickets/quick-send", headers=W, json={"client_id": new_clients["he2"]["id"], "template_slug": "missing_supplier_invoice",
                                                                    "context_variables": {"supplier_name": "Bezeq", "amount": "₪220", "invoice_date": "05/10/2026"}}).json()["ticket"]
        r = c.post("/api/webhook/whatsapp-inbound", json={"client_id": new_clients["he2"]["id"], "type": "button", "payload": f"t{snooze['id']}:remind_8pm"}).json()
        check(r["ticket"]["status"] == "SNOOZED_TONIGHT", "Remind Me at 8 PM → SNOOZED_TONIGHT")
        esc = c.post("/api/tickets/quick-send", headers=W, json={"client_id": new_clients["en"]["id"], "template_slug": "missing_supplier_invoice",
                                                                 "context_variables": {"supplier_name": "Hot Mobile", "amount": "₪99", "invoice_date": "05/10/2026"}}).json()["ticket"]
        for _ in range(4):
            c.post("/api/scheduler/simulate-time-jump?hours=48")
        esc = c.get(f"/api/tickets/{esc['id']}").json()
        check(esc["reminder_count"] == 3 and esc["status"] == "ESCALATED", "3 reminders then ESCALATED")
        r = c.post(f"/api/tickets/{tickets['he']['id']}/approve", headers=W, json={"note": ""})
        check(r.status_code == 200 and r.json()["status"] == "RESOLVED", "worker approves a verified invoice")
        r = c.post(f"/api/tickets/{tickets['he']['id']}/reject", headers=W, json={"reason": "חסר מספר הקצאה"})
        check(r.status_code == 409, "a resolved ticket cannot be rejected before reopening (409)")
        r = c.post(f"/api/tickets/{tickets['he2']['id']}/reject", headers=W, json={"reason": "הסכום בחשבונית לא תואם לתשלום"})
        rj = r.json()
        check(r.status_code == 200 and rj["status"] == "NEEDS_CORRECTION" and rj["context_variables_json"].get("awaiting_media") is True,
              "worker rejects an invoice → NEEDS_CORRECTION, waiting for a new photo")
        check("הסכום בחשבונית לא תואם לתשלום" in rj["messages"][-1]["content_text"] and rj["messages"][-1]["direction"] == "OUTBOUND",
              "the client gets the rejection reason in Hebrew on WhatsApp")
        check(c.post(f"/api/tickets/{tickets['he2']['id']}/reject", headers=W, json={"reason": ""}).status_code == 422,
              "a rejection needs a reason")
        check("exported_to_erp" not in r.json(), "ERP export fields removed")
        check(c.get("/api/exports/erp-csv").status_code == 404, "ERP export endpoint removed")

        section("Engine D — bulk tax campaign (worker)")
        demo = c.post("/api/campaigns/demo-batch", headers=W).json()
        check(demo["sent"] == 8, "demo batch dispatched to 8 clients")
        first = demo["campaign"]["recipients"][0]
        c.post("/api/webhook/whatsapp-inbound", json={"client_id": first["client_id"], "type": "button", "button_id": "paid_confirmed", "ticket_id": first["ticket_id"]})
        check(c.get(f"/api/campaigns/{demo['campaign']['id']}").json()["stats"]["confirmed_paid"] == 1, "Paid / Confirmed tracked")
        bad = ("client_tax_id,client_phone,client_name,tax_period,vat_amount,tax_advance_amount,due_date\n"
               "51477,0529998877,לקוח שגוי,10/2026,100,10,15/11/2026\n"
               "37845129,0501234503,ד״ר רונית חדד,10/2026,200,50,15/11/2026\n"
               "514000999,0529998879,شركة النور,10/2026,300,60,15/11/2026\n")
        r = c.post("/api/campaigns/bulk-tax-upload", files={"file": ("tax.csv", bad.encode(), "text/csv")}, headers=W).json()
        check(r["sent"] == 1 and len(r["errors"]) == 2 and "9 ספרות" in r["errors"][0], "sheet row with a 5-digit ח.פ rejected")
        check("עברית או באנגלית" in r["errors"][1], "sheet row with an Arabic business name rejected")
        check(r["created_clients"] == 0, "8-digit Excel ID zero-padded and matched to the existing client")

        section("Legacy English / Arabic WhatsApp history converted to Hebrew")
        from database import SessionLocal
        from models import ChasingTicket, MessageDirection, MessageType, WhatsAppMessageLog
        from services.history import hebrewize_message_history

        legacy_ticket_id = tickets["en"]["id"]
        with SessionLocal() as db:
            tk = db.get(ChasingTicket, legacy_ticket_id)
            rows = [
                WhatsAppMessageLog(ticket_id=tk.id, client_id=tk.client_id, direction=MessageDirection.OUTBOUND, sender_name="firm",
                                   message_type=MessageType.TEMPLATE, content_text="Hello Olivia Grant \U0001F44B During our monthly bookkeeping review…",
                                   buttons_json=[{"id": "upload_photo", "title": "\U0001F4F7 Upload Invoice Photo", "action": "REQUEST_MEDIA"}]),
                WhatsAppMessageLog(ticket_id=tk.id, client_id=tk.client_id, direction=MessageDirection.OUTBOUND, sender_name="firm",
                                   message_type=MessageType.AUTO_REMINDER, content_text="\U0001F514 Friendly reminder (2/3): we're still waiting for the invoice"),
                WhatsAppMessageLog(ticket_id=tk.id, client_id=tk.client_id, direction=MessageDirection.OUTBOUND, sender_name="firm",
                                   message_type=MessageType.TEXT, content_text="\u23F0 لا مشكلة! سنذكّرك الليلة الساعة 20:00."),
            ]
            db.add_all(rows)
            db.commit()
            ids = [r.id for r in rows]
            check(hebrewize_message_history(db) >= 3, "legacy messages rewritten on startup")
            converted = [db.get(WhatsAppMessageLog, i) for i in ids]
            check(all(HE.search(m.content_text) and not AR.search(m.content_text) for m in converted), "English and Arabic history is now Hebrew")
            check(converted[0].content_text.startswith("שלום Olivia Grant") and converted[0].buttons_json[0]["title"] == "העלאת צילום חשבונית",
                  "template message and its buttons re-rendered from the Hebrew template")
            check("(2/3)" in converted[1].content_text and "תזכורת ידידותית" in converted[1].content_text, "reminder keeps its counter")
            check(hebrewize_message_history(db) == 0, "conversion is idempotent")
            purge_emojis_from_db(db)
            cleaned = [db.get(WhatsAppMessageLog, i) for i in ids]
            check(not any(has_emoji(m.content_text) or any(has_emoji(b.get("title")) for b in (m.buttons_json or [])) for m in cleaned),
                  "emojis removed from converted legacy history")
            tpl_row = db.scalar(select(MessageTemplate).where(MessageTemplate.slug == "missing_supplier_invoice"))
            original_body, original_buttons = tpl_row.body_he, tpl_row.buttons_json
            tpl_row.body_he = "\U0001F44B " + original_body + " \U0001F64F"
            tpl_row.buttons_json = [{**b, "he": "\U0001F4F7 " + b["he"]} for b in original_buttons]
            db.commit()
            check(purge_emojis_from_db(db) >= 1, "startup purge cleans emojis stored by older releases")
            db.refresh(tpl_row)
            check(tpl_row.body_he == original_body and tpl_row.buttons_json == original_buttons,
                  "template body and quick-reply buttons are clean Hebrew text again")
            check(purge_emojis_from_db(db) == 0, "emoji purge is idempotent")

        section("Manual worker messages (text + pictures) and automated labels")
        cid = seeded[0]["id"]
        history = c.get(f"/api/clients/{cid}/messages").json()
        auto = [m for m in history if m["direction"] == "OUTBOUND"]
        check(bool(auto) and all(m["is_automated"] and m["sender_user_id"] is None for m in auto),
              f"template / reminder / Vision AI messages are automated ({len(auto)})")
        check(all(not m["is_automated"] for m in history if m["direction"] == "INBOUND"), "inbound client messages are not automated")
        check(c.post("/api/whatsapp/manual-send", data={"client_id": cid, "content_text": "x"}, headers=ANON).status_code == 401,
              "manual send requires login")
        r = c.post("/api/whatsapp/manual-send", data={"client_id": cid, "content_text": "שלום, בדקתי את התיק שלך \U0001F64F"})
        check(r.status_code == 201, "worker sends a manual text message", r.text)
        manual = r.json()
        check(manual["is_automated"] is False and manual["sender_user_id"] == worker["id"] and manual["sender_name"] == worker["full_name"]
              and manual["direction"] == "OUTBOUND" and manual["ticket_id"] is None, "manual message is OUTBOUND, not automated, from the worker")
        check(manual["content_text"] == "שלום, בדקתי את התיק שלך", "emojis stripped from the manual text")
        buf = io.BytesIO()
        Image.new("RGB", (40, 30), "white").save(buf, format="PNG")
        png = buf.getvalue()
        r = c.post("/api/whatsapp/manual-send", data={"client_id": str(cid), "content_text": ""},
                   files={"image_file": ("scan.png", png, "image/png")})
        check(r.status_code == 201 and r.json()["media_url"].startswith("/uploads/out_") and r.json()["message_type"] == "IMAGE_UPLOAD",
              "worker sends a picture without text", r.text)
        check(c.get(r.json()["media_url"]).status_code == 200, "the picture is served from /uploads")
        r = c.post("/api/whatsapp/manual-send", data={"client_id": cid, "content_text": "החשבונית המתוקנת",
                                                      "image_base64": "data:image/png;base64," + base64.b64encode(png).decode()})
        check(r.status_code == 201 and r.json()["media_url"].endswith(".png") and r.json()["content_text"] == "החשבונית המתוקנת",
              "base64 picture with a caption")
        check(c.post("/api/whatsapp/manual-send", data={"client_id": cid, "content_text": "  "}).status_code == 400,
              "empty manual message rejected")
        check(c.post("/api/whatsapp/manual-send", data={"client_id": cid},
                     files={"image_file": ("a.gif", b"GIF89a", "image/gif")}).status_code == 422, "unsupported attachment type rejected")
        check(c.post("/api/whatsapp/manual-send", data={"client_id": 999999, "content_text": "x"}).status_code == 404, "unknown client 404")
        from services.whatsapp import _cloud_payload, customer_header, with_header
        with SessionLocal() as db:
            mrow = db.get(WhatsAppMessageLog, manual["id"])
            arow = db.get(WhatsAppMessageLog, auto[0]["id"])
            check(customer_header(arow) == "הודעה אוטומטית" and customer_header(mrow) == f"הודעה מאת {worker['full_name']}",
                  "customer-facing headers: automated vs worker name")
        check(with_header("הודעה אוטומטית", "גוף") == "*הודעה אוטומטית*\nגוף", "Cloud API text starts with the header line")
        payload = _cloud_payload("+972501234567", "*הודעה מאת ראמי*", [], None, "media.1", "image")
        check(payload["type"] == "image" and payload["image"] == {"id": "media.1", "caption": "*הודעה מאת ראמי*"}
              and "link" not in payload["image"], "manual picture goes to the Cloud API by media ID, not by link")
        payload = _cloud_payload("+972501234567", "*הודעה מאת ראמי*", [], None, "media.2", "document", "out_1.pdf")
        check(payload["type"] == "document" and payload["document"]["filename"] == "out_1.pdf", "manual PDF goes as a document")
        everything = [m for cl in c.get("/api/clients").json() for m in c.get(f"/api/clients/{cl['id']}/messages").json()]
        check(not any(has_emoji(m["content_text"]) or any(has_emoji(b.get("title")) for b in (m["buttons_json"] or [])) for m in everything),
              f"no emojis in any WhatsApp message ({len(everything)} checked)")
        check(not any(has_emoji(t["body_he"]) or has_emoji(t["name_he"]) or any(has_emoji(b["he"]) for b in t["buttons_json"])
                      for t in c.get("/api/templates").json()), "no emojis in any template or quick-reply button")

        section("Manual message to a group of selected clients")
        group = [seeded[2]["id"], seeded[3]["id"], seeded[4]["id"]]
        counts = {cid: len(c.get(f"/api/clients/{cid}/messages").json()) for cid in group}
        check(c.post("/api/whatsapp/manual-broadcast", json={"client_ids": group, "content_text": "x"}, headers=ANON).status_code == 401,
              "group message requires login")
        check(c.post("/api/whatsapp/manual-broadcast", json={"client_ids": [], "content_text": "שלום"}).status_code == 422,
              "at least one client is required")
        check(c.post("/api/whatsapp/manual-broadcast", json={"client_ids": group, "content_text": ""}).status_code == 422,
              "empty group message rejected")
        check(c.post("/api/whatsapp/manual-broadcast", json={"client_ids": group + [999999], "content_text": "שלום"}).status_code == 404,
              "unknown client in the group rejected (nothing sent)")
        check(all(len(c.get(f"/api/clients/{cid}/messages").json()) == counts[cid] for cid in group), "a rejected group send sends nothing")
        r = c.post("/api/whatsapp/manual-broadcast",
                   json={"client_ids": group + [group[0]], "content_text": "המשרד יהיה סגור ביום שישי \U0001F64F"})
        check(r.status_code == 201 and r.json()["sent"] == 3 and r.json()["client_ids"] == group, "group message sent once per client", r.text[:200])
        for cid in group:
            last = c.get(f"/api/clients/{cid}/messages").json()[-1]
            check(last["direction"] == "OUTBOUND" and last["is_automated"] is False and last["sender_user_id"] == worker["id"]
                  and last["content_text"] == "המשרד יהיה סגור ביום שישי" and last["ticket_id"] is None,
                  f"client {cid}: manual message from the worker, emoji stripped, no ticket")

        section("Unsolicited client messages: saved silently, no bot reply")
        r = c.post("/api/clients", json={"full_name": "רונן שקט", "company_name": "שקט בע\"מ", "tax_id": "517011906",
                                         "whatsapp_phone": "0521119006", "assigned_worker_id": worker["id"]}, headers=M)
        check(r.status_code == 201, "client without requests created", r.text[:200])
        quiet = r.json()["id"]

        def chat(client_id: int) -> list[dict]:
            return c.get(f"/api/clients/{client_id}/messages").json()

        r = c.post("/api/webhook/whatsapp-inbound", json={"client_id": quiet, "type": "text", "text": "שלום, מה שלומכם?"}).json()
        check(r["unsolicited"] is True and r["reply"] is None and r["ticket"] is None, "text without an open request: no reply")
        r = c.post("/api/webhook/whatsapp-inbound", data={"client_id": str(quiet)}, files={"file": ("random.png", png, "image/png")}).json()
        check(r["unsolicited"] is True and r["ocr"] is None and r["reply"] is None, "photo without an open request: no Vision AI, no reply")
        r = c.post("/api/simulator/demo-receipt", json={"client_id": quiet, "scenario": "clear"}).json()
        check(r["unsolicited"] is True and r["ocr"] is None, "simulator receipt without an open request is silent too")
        history = chat(quiet)
        check(len(history) == 3 and all(m["direction"] == "INBOUND" and m["ticket_id"] is None for m in history),
              "all 3 inputs saved as INBOUND chat history, nothing sent back")
        check(history[1]["media_url"] and history[1]["media_url"].startswith("/uploads/in_") and c.get(history[1]["media_url"]).status_code == 200,
              "the unsolicited photo is kept and viewable by the office")

        tax_tpl = templates["tax_ready_to_pay"]
        r = c.post("/api/tickets/quick-send", headers=W, json={"client_id": quiet, "template_id": tax_tpl["id"], "context_variables": {
            "tax_period": "09/2026", "vat_amount": "1200", "tax_advance_amount": "300", "due_date": "26/10/2026"}})
        check(r.status_code == 201, "tax-ready notification sent", r.text[:200])
        tax_ticket = r.json()["ticket"]
        before = len(chat(quiet))
        r = c.post("/api/webhook/whatsapp-inbound", data={"client_id": str(quiet), "ticket_id": str(tax_ticket["id"])},
                   files={"file": ("selfie.png", png, "image/png")}).json()
        tk = c.get(f"/api/tickets/{tax_ticket['id']}").json()
        check(r["unsolicited"] is True and r["ocr"] is None, "photo to a request that does not expect a document: silent")
        check(tk["status"] == "WAITING_FOR_CLIENT" and tk["ocr_validation_json"] is None and tk["media_file_path"] is None,
              "the tax-ready ticket is unchanged (status, OCR, media)")
        after = chat(quiet)
        check(len(after) == before + 1 and after[-1]["direction"] == "INBOUND" and after[-1]["ticket_id"] is None,
              "only the inbound photo was added to the chat")
        r = c.post("/api/webhook/whatsapp-inbound", json={"client_id": quiet, "type": "text", "text": "שילמתי אתמול"}).json()
        check(r["unsolicited"] is False and r["reply"] and r["ticket"]["id"] == tax_ticket["id"],
              "text while a request waits for the client is still answered")

        c.post(f"/api/tickets/{tax_ticket['id']}/resolve", json={"note": "בדיקה"})
        r = c.post("/api/webhook/whatsapp-inbound", json={"client_id": quiet, "type": "text", "text": "עוד שאלה"}).json()
        check(r["unsolicited"] is True and r["reply"] is None, "after the request is closed, new text is silent again")
        envelope = {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"messages": [
            {"from": "972521119006", "id": "wamid.Q", "type": "text", "text": {"body": "בוקר טוב"}}]}}]}]}
        before = len(chat(quiet))
        check(meta_post(c, envelope).json()["processed"] == 1
              and [m["direction"] for m in chat(quiet)[before:]] == ["INBOUND"], "Meta webhook text without a request: logged, no reply")

        section("Webhook security: Meta signature, simulator needs a login")
        sim = {"client_id": quiet, "type": "text", "text": "שלום"}
        check(c.post("/api/webhook/whatsapp-inbound", json=sim, headers=ANON).status_code == 401,
              "simulator text without a login is refused (401)")
        check(c.post("/api/webhook/whatsapp-inbound", data={"client_id": str(quiet)},
                     files={"file": ("x.png", png, "image/png")}, headers=ANON).status_code == 401,
              "simulator upload without a login is refused (401)")
        forged = {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"messages": [
            {"from": "972521119006", "id": "wamid.F", "type": "text", "text": {"body": "הודעה מזויפת"}}]}}]}]}
        before = len(chat(quiet))
        check(meta_post(c, forged, signature="").status_code == 403, "Meta envelope without X-Hub-Signature-256 is refused (403)")
        check(meta_post(c, forged, secret="wrong-secret").status_code == 403, "Meta envelope signed with the wrong secret is refused")
        check(c.post("/api/webhook/whatsapp-inbound", json=forged).status_code == 403,
              "a logged-in session does not replace the Meta signature")
        settings.whatsapp_app_secret = ""
        try:
            check(meta_post(c, forged).status_code == 403, "Meta envelopes are refused while WHATSAPP_APP_SECRET is empty")
        finally:
            settings.whatsapp_app_secret = META_SECRET
        check(len(chat(quiet)) == before, "refused webhook posts add nothing to the chat")

        section("Activity log (manager only)")
        check(c.get("/api/activity", headers=W).status_code == 403, "worker cannot read the activity log (403)")
        log = c.get("/api/activity?limit=500", headers=M).json()
        actions = {e["action"] for e in log["items"]}
        for a in ("LOGIN", "LOGOUT", "TICKET_SENT", "MANUAL_MESSAGE_SENT", "MANUAL_BROADCAST_SENT", "REMINDERS_SENT", "CAMPAIGN_SENT", "TICKET_APPROVED", "TICKET_REJECTED",
                  "CLIENT_CREATED", "CLIENT_UPDATED", "SETTINGS_UPDATED", "USER_CREATED", "USER_UPDATED", "PASSWORD_RESET",
                  "PASSWORD_CHANGED"):
            check(a in actions, f"activity log records {a} ({log['actions'][a]})")
        check(log["actions"]["LOGIN"] == "התחברות למערכת" and log["actions"]["LOGOUT"] == "התנתקות מהמערכת", "session events use the Hebrew labels")
        check(not actions & {"LOGIN_FAILED", "SIMULATOR_RECEIPT", "SCHEDULER_RUN"} and "LOGIN_FAILED" not in log["actions"],
              "no failed-login, simulator or scheduler-debug entries")
        rem = next(e for e in log["items"] if e["action"] == "REMINDERS_SENT")
        check(rem["user_name"] == worker["full_name"] and "תזכורות" in rem["description"], f"reminders entry: {rem['description']}")
        rej = next(e for e in log["items"] if e["action"] == "TICKET_REJECTED")
        check("הסכום בחשבונית לא תואם לתשלום" in rej["description"], "rejection entry keeps the reason")
        man = next(e for e in log["items"] if e["action"] == "MANUAL_MESSAGE_SENT")
        check(man["user_name"] == worker["full_name"] and man["description"].startswith("שליחת הודעה ידנית ללקוח ")
              and seeded[0]["full_name"] in man["description"], f"manual message entry: {man['description']}")
        sent = next(e for e in log["items"] if e["action"] == "TICKET_SENT")
        check(sent["user_name"] == worker["full_name"] and "נשלחה בקשה מסוג" in sent["description"] and "ללקוח" in sent["description"],
              f"request entries name the worker, the request type and the client: {sent['description']}")
        vat = [e for e in log["items"] if e["action"] == "SETTINGS_UPDATED" and "vat_rate" in (e["details"] or {})]
        check([18.0, 17] in [e["details"]["vat_rate"] for e in vat] and [17.0, 18] in [e["details"]["vat_rate"] for e in vat]
              and all(e["user_name"] == manager["full_name"] for e in vat), "settings changes keep old → new values")
        mine = c.get(f"/api/activity?user_id={worker['id']}&action=TICKET_SENT", headers=M).json()
        check(mine["total"] > 0 and all(e["user_id"] == worker["id"] and e["action"] == "TICKET_SENT" for e in mine["items"]),
              "filter by user and action")
        failed = c.get(f"/api/activity?user_id={dana['id']}&action=LOGIN_FAILED", headers=M).json()
        check(failed["total"] == 0, "failed logins are not in the activity log")
        with SessionLocal() as db:
            check(db.scalar(select(func.count(LoginFailure.id)).where(LoginFailure.user_id == dana["id"])) >= 5,
                  "failed logins kept separately (login_failures) for the lockout")
            db.add_all([ActivityLog(user_id=dana["id"], action="LOGIN_FAILED", description="legacy", created_at=clock.utcnow()),
                        ActivityLog(user_id=None, action="SIMULATOR_RECEIPT", description="legacy", created_at=clock.utcnow()),
                        ActivityLog(user_id=None, action="SCHEDULER_RUN", description="legacy", created_at=clock.utcnow())])
            db.commit()
            check(cleanup_legacy_activity(db) == 3 and cleanup_legacy_activity(db) == 0, "startup cleanup deletes legacy rows (idempotent)")
            check(db.scalar(select(func.count(ActivityLog.id)).where(ActivityLog.action.in_(("LOGIN_FAILED", "SIMULATOR_RECEIPT", "SCHEDULER_RUN")))) == 0,
                  "no legacy action codes left")
        check(describe_reminder_actions([{"kind": "FRIENDLY_REMINDER"}, {"kind": "FRIENDLY_REMINDER"}, {"kind": "ESCALATED"}])
              == "2 תזכורות ידידותיות, 1 פניות שהוסלמו לשיחה", "reminder summary in Hebrew")

        section("Deactivate client (manager) + Meta webhook + dashboard")
        r = c.delete(f"/api/clients/{new_clients['en']['id']}", headers=M).json()
        check(r["is_active"] is False and r["open_ticket_count"] == 0, "manager deactivates a client; open tickets closed")
        envelope = {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"messages": [
            {"from": "972521119001", "id": "wamid.X", "type": "text", "text": {"body": "תודה"}}]}}]}]}
        check(meta_post(c, envelope).json()["processed"] == 1, "Meta webhook envelope processed")
        k = c.get("/api/dashboard/kpis").json()
        check(k["auto_reminders_this_month"] > 0 and "הודעות" in k["hours_saved_basis"], f"KPIs ({k['estimated_hours_saved']} h saved)")

        section("Live WhatsApp: 24-hour window, held messages, re-engagement template")
        sent: list[dict] = []
        fail_next: list[int] = []  # Meta error codes to answer the next message sends with

        class FakeResponse:
            def __init__(self, status: int, body: dict) -> None:
                self.status_code, self._body, self.text = status, body, json.dumps(body)

            def json(self) -> dict:
                return self._body

        uploads: list[dict] = []  # files posted to the Cloud API /media endpoint
        fail_upload: list[int] = []  # HTTP statuses to answer the next media uploads with

        def fake_post(url: str, headers: dict, timeout: float, json: dict | None = None,  # noqa: A002
                      data: dict | None = None, files: dict | None = None) -> FakeResponse:
            if url.endswith("/media"):
                if fail_upload:
                    return FakeResponse(fail_upload.pop(0), {"error": {"code": 100, "message": "Invalid file"}})
                name, content, mime = files["file"]
                uploads.append({"url": url, "data": data, "name": name, "size": len(content), "mime": mime})
                return FakeResponse(200, {"id": f"media.{len(uploads)}"})
            if fail_next and json["type"] != "template":
                return FakeResponse(400, {"error": {"code": fail_next.pop(0), "message": "Re-engagement message"}})
            sent.append(json)
            return FakeResponse(200, {"messages": [{"id": f"wamid.OUT{len(sent)}"}]})

        def wait_sent(n: int) -> bool:
            end = time.monotonic() + 5
            while len(sent) < n and time.monotonic() < end:
                time.sleep(0.05)
            time.sleep(0.2)  # let anything unexpected arrive too
            return len(sent) == n

        live = {"whatsapp_token": "test-token", "whatsapp_phone_number_id": "1234567890",
                "whatsapp_reengage_template": "accountflow_pending_update"}
        saved = {k: getattr(settings, k) for k in live}
        real_post = whatsapp_service.httpx.post
        for k, v in live.items():
            setattr(settings, k, v)
        whatsapp_service.httpx.post = fake_post
        try:
            r = c.post("/api/clients", json={"full_name": "אבי חלון", "company_name": "חלון בע\"מ", "tax_id": "517011907",
                                             "whatsapp_phone": "0521119007", "assigned_worker_id": worker["id"]}, headers=M)
            check(r.status_code == 201, "client who never wrote created", r.text[:200])
            win = r.json()["id"]
            meta_from = "972521119007"

            def held(client_id: int) -> list[dict]:
                return [m for m in chat(client_id) if m["direction"] == "OUTBOUND" and m["awaiting_window"]]

            r = c.post("/api/tickets/quick-send", headers=W, json={
                "client_id": win, "template_id": tpl["id"],
                "context_variables": {"supplier_name": "Mega Office Supply", "amount": "₪1,180.00", "invoice_date": "03/10/2026"}})
            check(r.status_code == 201, "request to a client whose window is closed is accepted", r.text[:200])
            check(wait_sent(1) and sent[0]["type"] == "template", "window closed: only the re-engagement template is sent")
            tmpl = sent[0]["template"]
            check(tmpl["name"] == "accountflow_pending_update" and tmpl["language"]["code"] == "he"
                  and [p["text"] for p in tmpl["components"][0]["parameters"]] == ["אבי חלון", c.get("/api/settings").json()["firm_name"]]
                  and tmpl["components"][1]["parameters"][0]["payload"] == "t0:show_held",
                  "template carries the client name, firm name and the show-held button payload")
            check(len(held(win)) == 1, "the request is held (awaiting_window) in the chat")
            check(c.post("/api/whatsapp/manual-send", data={"client_id": str(win), "content_text": "עוד הודעה"}).status_code < 300,
                  "manual message while the window is closed is accepted")
            check(wait_sent(1) and len(held(win)) == 2, "second held message does not send another template")

            tap = {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"messages": [
                {"from": meta_from, "id": "wamid.T", "type": "button", "button": {"payload": "t0:show_held", "text": "הצגת ההודעה"}}]}}]}]}
            outbound_before = len([m for m in chat(win) if m["direction"] == "OUTBOUND"])
            check(meta_post(c, tap).json()["processed"] == 1, "client taps the template button")
            check(wait_sent(3) and sent[1]["type"] == "interactive" and sent[2]["type"] == "text"
                  and "עוד הודעה" in sent[2]["text"]["body"], "held messages go out in order (request with buttons, then text)")
            check(not held(win) and len([m for m in chat(win) if m["direction"] == "OUTBOUND"]) == outbound_before,
                  "nothing left held, and the tap gets no extra bot reply")

            check(c.post("/api/whatsapp/manual-send", data={"client_id": str(win), "content_text": "החלון פתוח"}).status_code < 300
                  and wait_sent(4) and sent[3]["type"] == "text" and not held(win), "window open: messages are sent directly")

            fail_next.append(131047)
            c.post("/api/whatsapp/manual-send", data={"client_id": str(win), "content_text": "נדחתה ע״י Meta"})
            check(wait_sent(5) and sent[4]["type"] == "template" and len(held(win)) == 1,
                  "Meta error 131047 holds the message and sends the template")
            wrote = {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"messages": [
                {"from": meta_from, "id": "wamid.W", "type": "text", "text": {"body": "הנה אני"}}]}}]}]}
            meta_post(c, wrote)
            check(wait_sent(7) and "נדחתה" in sent[5]["text"]["body"] and not held(win),
                  "a typed reply releases held messages before the bot answers it")

            settings.whatsapp_reengage_template = ""
            r = c.post("/api/clients", json={"full_name": "דנה שקטה", "company_name": "שקטה בע\"מ", "tax_id": "517011908",
                                             "whatsapp_phone": "0521119008", "assigned_worker_id": worker["id"]}, headers=M)
            silent = r.json()["id"]
            c.post("/api/whatsapp/manual-send", data={"client_id": str(silent), "content_text": "שלום"})
            h = held(silent)
            check(wait_sent(7) and len(h) == 1 and "WHATSAPP_REENGAGE_TEMPLATE" in (h[0]["error_text"] or ""),
                  "no template configured: held with an explanation, nothing sent")
            settings.whatsapp_reengage_template = live["whatsapp_reengage_template"]

            r = c.post("/api/whatsapp/manual-send", data={"client_id": str(win), "content_text": "הסיכום החודשי"},
                       files={"image_file": ("summary.png", png, "image/png")})
            check(r.status_code == 201 and wait_sent(8), "window open: manual picture is sent", r.text[:200])
            check(len(uploads) == 1 and uploads[0]["url"].endswith("/1234567890/media") and uploads[0]["mime"] == "image/png"
                  and uploads[0]["data"] == {"messaging_product": "whatsapp", "type": "image/png"} and uploads[0]["size"] == len(png),
                  "the picture file is uploaded to the Cloud API media endpoint first")
            check(sent[7]["type"] == "image" and sent[7]["image"]["id"] == "media.1" and "link" not in sent[7]["image"]
                  and "הסיכום החודשי" in sent[7]["image"]["caption"] and "הודעה מאת" in sent[7]["image"]["caption"],
                  "then sent by media ID with the worker header and text as caption (no public URL needed)")
            fail_upload.append(400)
            r = c.post("/api/whatsapp/manual-send", data={"client_id": str(win), "content_text": ""},
                       files={"image_file": ("bad.png", png, "image/png")})
            time.sleep(0.5)
            failed = [m for m in chat(win) if m["id"] == r.json()["id"]][0]
            check(wait_sent(8) and failed["delivery_status"] == "FAILED" and "העלאת הקובץ ל-WhatsApp נכשלה" in (failed["error_text"] or ""),
                  "a failed upload marks the message FAILED with a Hebrew reason and sends nothing")

            # Gap 1: held messages must not pile up when the client comes back.
            from datetime import timedelta as _td

            from models import Client as ClientRow
            from services.ticket_engine import send_outbound
            from services.whatsapp import SKIP_OLDER_REMINDER, SKIP_REQUEST_PENDING, SKIP_TICKET_CLOSED

            r = c.post("/api/clients", json={"full_name": "חן מתעכב", "company_name": "מתעכב בע\"מ", "tax_id": "517011909",
                                             "whatsapp_phone": "0521119009", "assigned_worker_id": worker["id"]}, headers=M)
            late = r.json()["id"]
            late_from = "972521119009"

            def remind(ticket_id: int, label: str) -> None:
                with SessionLocal() as db:
                    tk = db.get(ChasingTicket, ticket_id)
                    send_outbound(db, db.get(ClientRow, late), tk, f"תזכורת {label}", [{"id": "upload_photo", "title": "העלאה",
                                                                                         "action": "REQUEST_MEDIA"}], MessageType.AUTO_REMINDER)
                    db.commit()

            def close_window(client_id: int) -> None:
                with SessionLocal() as db:
                    for m in db.scalars(select(WhatsAppMessageLog).where(WhatsAppMessageLog.client_id == client_id,
                                                                           WhatsAppMessageLog.direction == MessageDirection.INBOUND)):
                        m.created_at -= _td(hours=25)
                    db.commit()

            def by_text(client_id: int, text: str) -> dict:
                return next(m for m in chat(client_id) if m["content_text"] == text)

            base = len(sent)
            r = c.post("/api/tickets/quick-send", headers=W, json={
                "client_id": late, "template_id": tpl["id"],
                "context_variables": {"supplier_name": "Late Supplies", "amount": "500", "invoice_date": "2026-10-03"}})
            late_ticket = r.json()["ticket"]["id"]
            remind(late_ticket, "א")
            remind(late_ticket, "ב")
            check(wait_sent(base + 1) and sent[base]["type"] == "template" and len(held(late)) == 3,
                  "request + 2 reminders held, one re-engagement template sent")
            tap_late = {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"messages": [
                {"from": late_from, "id": "wamid.L1", "type": "button", "button": {"payload": "t0:show_held", "text": "הצגת ההודעה"}}]}}]}]}
            meta_post(c, tap_late)
            check(wait_sent(base + 2) and sent[base + 1]["type"] == "interactive" and "Late Supplies" in sent[base + 1]["interactive"]["body"]["text"],
                  "on return, only the original request is sent")
            check(all(by_text(late, f"תזכורת {x}")["delivery_status"] == "SKIPPED"
                      and by_text(late, f"תזכורת {x}")["error_text"] == SKIP_REQUEST_PENDING for x in ("א", "ב")) and not held(late),
                  "its held reminders are dropped (SKIPPED, Hebrew reason)")

            close_window(late)
            base = len(sent)
            remind(late_ticket, "ג")
            remind(late_ticket, "ד")
            remind(late_ticket, "ה")
            check(wait_sent(base + 1) and sent[base]["type"] == "template" and len(held(late)) == 3,
                  "request already delivered, window closed again: 3 reminders held")
            wrote_late = {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"messages": [
                {"from": late_from, "id": "wamid.L2", "type": "text", "text": {"body": "חזרתי"}}]}}]}]}
            meta_post(c, wrote_late)
            check(wait_sent(base + 3) and "תזכורת ה" in sent[base + 1]["interactive"]["body"]["text"]
                  and sent[base + 2]["type"] == "text", "only the newest reminder goes out, then the bot's reply")
            check(by_text(late, "תזכורת ג")["error_text"] == SKIP_OLDER_REMINDER and by_text(late, "תזכורת ד")["delivery_status"] == "SKIPPED"
                  and by_text(late, "תזכורת ה")["delivery_status"] != "SKIPPED", "older reminders are SKIPPED")

            close_window(late)
            base = len(sent)
            remind(late_ticket, "ו")
            check(wait_sent(base + 1) and sent[base]["type"] == "template", "reminder held for a ticket that is still open")
            c.post(f"/api/tickets/{late_ticket}/resolve", json={"note": "טופל טלפונית"})
            wrote_again = {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"messages": [
                {"from": late_from, "id": "wamid.L3", "type": "text", "text": {"body": "שוב אני"}}]}}]}]}
            meta_post(c, wrote_again)
            check(wait_sent(base + 1) and by_text(late, "תזכורת ו")["error_text"] == SKIP_TICKET_CLOSED and not held(late),
                  "ticket closed meanwhile: its held reminder is dropped, nothing sent")
        finally:
            whatsapp_service.httpx.post = real_post
            for k, v in saved.items():
                setattr(settings, k, v)

    print(f"\nALL {passed} CHECKS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        from database import engine

        engine.dispose()
        shutil.rmtree(TMP, ignore_errors=True)
