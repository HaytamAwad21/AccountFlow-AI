"""Regression checks for logic bugs found by review, through the real HTTP API on a throw-away database.

Unlike test_flow.py this run does not stop at the first failure, so every case is reported:

    python test_regressions.py
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import logging
import os
import shutil
import sys
import tempfile
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="accountflow_regress_"))
SECRET = "test-app-secret"
os.environ.update(
    DATABASE_URL=f"sqlite:///{(TMP / 'test.db').as_posix()}",
    SCHEDULER_ENABLED="false",
    VISION_PROVIDER="local",
    OPENAI_API_KEY="",
    GEMINI_API_KEY="",
    WHATSAPP_TOKEN="",
    WHATSAPP_PHONE_NUMBER_ID="",
    WHATSAPP_APP_SECRET=SECRET,
    AUTO_APPROVE_VERIFIED="false",
    UPLOAD_DIR=str(TMP / "uploads"),
)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

import routers.webhook as webhook_router  # noqa: E402
import services.clock as clock  # noqa: E402
import services.whatsapp as whatsapp_service  # noqa: E402
from config import settings  # noqa: E402
from database import SessionLocal  # noqa: E402
from main import app  # noqa: E402
from models import ChasingTicket, Client, TicketStatus, WhatsAppMessageLog  # noqa: E402

logging.disable(logging.CRITICAL)

_real_local_today = clock.local_today
results = {"passed": 0, "failed": 0}
VARS = {"supplier_name": "Ace Ltd", "amount": "1000", "invoice_date": "2026-10-03", "invoice_number": "881", "missing_detail": "מספר הקצאה",
        "tax_period": "2026-10", "vat_amount": "500", "tax_advance_amount": "200", "due_date": "2026-11-26", "charge_amount": "100",
        "charge_date": "2026-10-03", "bank_reference": "R1"}
SHEET = {"tax_period": "10/2026", "vat_amount": "100", "tax_advance_amount": "50", "due_date": "26/11/2026"}


def check(cond: bool, label: str, detail: object = "") -> None:
    if cond:
        results["passed"] += 1
        print(f"  ok   {label}")
    else:
        results["failed"] += 1
        print(f"  FAIL {label}  {detail}")


def freeze_day(day: int | None) -> None:
    clock.local_today = _real_local_today if day is None else (lambda now_utc=None: _real_local_today(now_utc).replace(day=day))


class Api:
    def __init__(self, c: TestClient):
        self.c = c
        users = c.get("/api/auth/users").json()
        manager = next(u for u in users if u["role"] == "MANAGER")
        token = c.post("/api/auth/login", json={"user_id": manager["id"], "password": "maya1234"}).json()["token"]
        c.headers.update({"Authorization": f"Bearer {token}"})
        self.templates = {t["slug"]: t for t in c.get("/api/templates").json()}
        self.serial = 0

    def client(self, tax_id: str | None = None, phone: str | None = None) -> dict:
        self.serial += 1
        n = self.serial
        r = self.c.post("/api/clients", json={"full_name": f"Client {n}", "company_name": f"Company {n}", "tax_id": tax_id or f"7{n:08d}",
                                              "whatsapp_phone": phone or f"05290{n:05d}"})
        assert r.status_code == 201, r.text
        return r.json()

    def send(self, client: dict, slug: str) -> dict:
        r = self.c.post("/api/tickets/quick-send", json={"client_id": client["id"], "template_slug": slug, "context_variables": VARS})
        assert r.status_code == 201, r.text
        return r.json()["ticket"]

    def tap(self, client: dict, slug: str, action: str, ticket_id: int):
        button = next(b["id"] for b in self.templates[slug]["buttons_json"] if b["action"] == action)
        return self.c.post("/api/webhook/whatsapp-inbound", json={"client_id": client["id"], "type": "button", "button_id": button, "ticket_id": ticket_id})

    def ticket(self, ticket: dict) -> dict:
        return self.c.get(f"/api/tickets/{ticket['id']}").json()

    def chat(self, client: dict) -> list[dict]:
        return self.c.get(f"/api/clients/{client['id']}/messages").json()

    def jump(self) -> dict:
        return self.c.post("/api/scheduler/simulate-time-jump?hours=48").json()

    def meta(self, envelope: dict):
        raw = json.dumps(envelope).encode()
        signature = "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
        return self.c.post("/api/webhook/whatsapp-inbound", content=raw, headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature})

    def upload(self, rows: list[dict] | None = None, name: str = "sheet.csv", content: bytes | None = None):
        if content is None:
            content = pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig")
        return self.c.post("/api/campaigns/bulk-tax-upload", files={"file": (name, content)})


def messages_envelope(*messages: dict) -> dict:
    return {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"messages": list(messages)}}]}]}


def from_phone(client: dict) -> str:
    return client["whatsapp_phone"].lstrip("+")


def old_button_cannot_touch_another_request(a: Api) -> None:
    client = a.client()
    tax, invoice = a.send(client, "tax_ready_to_pay"), a.send(client, "missing_supplier_invoice")
    a.tap(client, "tax_ready_to_pay", "PAID_CONFIRMED", tax["id"])
    a.tap(client, "tax_ready_to_pay", "PAID_CONFIRMED", tax["id"])
    check(a.ticket(invoice)["status"] == "WAITING_FOR_CLIENT", "second tap on a closed ticket's button leaves the other open request alone",
          a.ticket(invoice)["status"])
    check("כבר טופלה" in a.chat(client)[-1]["content_text"], "the client is told that request is already closed", a.chat(client)[-1]["content_text"])

    client = a.client()
    charge, invoice = a.send(client, "unidentified_bank_charge"), a.send(client, "missing_supplier_invoice")
    a.tap(client, "unidentified_bank_charge", "PERSONAL_EXPENSE", charge["id"])
    a.tap(client, "unidentified_bank_charge", "PERSONAL_EXPENSE", charge["id"])
    check(a.ticket(invoice)["status"] == "WAITING_FOR_CLIENT", "a double tap on a bank-charge button does not close an invoice request",
          a.ticket(invoice)["status"])


def old_button_cannot_undo_clerk_review(a: Api) -> None:
    client = a.client()
    ticket = a.send(client, "missing_supplier_invoice")
    a.c.post("/api/simulator/demo-receipt", json={"client_id": client["id"], "scenario": "clear", "ticket_id": ticket["id"]})
    a.tap(client, "missing_supplier_invoice", "SNOOZE_TONIGHT", ticket["id"])
    after = a.ticket(ticket)
    check(after["status"] == "NEEDS_CLERK_REVIEW" and after["next_reminder_at"] is None, "old snooze button keeps the invoice in clerk review", after["status"])
    check("אצל רואה החשבון" in a.chat(client)[-1]["content_text"], "the client is told the document is already with the accountant", a.chat(client)[-1]["content_text"])

    client = a.client()
    ticket = a.send(client, "missing_supplier_invoice")
    a.c.post("/api/simulator/demo-receipt", json={"client_id": client["id"], "scenario": "clear", "ticket_id": ticket["id"]})
    a.tap(client, "missing_supplier_invoice", "REQUEST_MEDIA", ticket["id"])
    check("נא לשלוח" not in a.chat(client)[-1]["content_text"], "old upload button does not ask for a photo the app would ignore", a.chat(client)[-1]["content_text"])


def bulk_prefers_the_active_client(a: Api) -> None:
    old = a.client(tax_id="777000111", phone="0529111111")
    a.c.delete(f"/api/clients/{old['id']}")
    current = a.client(tax_id="777000111", phone="0529222222")
    r = a.upload([{**SHEET, "client_tax_id": "777000111", "client_phone": "", "client_name": current["full_name"]}])
    recipient = r.json()["campaign"]["recipients"][0]
    check(recipient["client_id"] == current["id"], "tax notice goes to the active client, not a deactivated one with the same ID", recipient["client_id"])
    clients = {x["id"]: x for x in a.c.get("/api/clients?include_inactive=true").json()}
    check(clients[old["id"]]["is_active"] is False, "the deactivated duplicate stays deactivated")


def invitation_is_repeated_after_the_interval(a: Api) -> None:
    posted: list[dict] = []

    class Ok:
        status_code = 200
        text = "{}"

        def json(self):
            return {"messages": [{"id": "x"}]}

    real_post = whatsapp_service.httpx.post
    saved = {k: getattr(settings, k) for k in ("whatsapp_token", "whatsapp_phone_number_id", "whatsapp_reengage_template")}
    whatsapp_service.httpx.post = lambda url, **kw: (posted.append(kw["json"]), Ok())[1]
    settings.whatsapp_token, settings.whatsapp_phone_number_id, settings.whatsapp_reengage_template = "token", "1234", "tpl"

    def templates(expected: int) -> int:
        deadline = time.time() + 2
        while time.time() < deadline and sum(p.get("type") == "template" for p in posted) < expected:
            time.sleep(0.02)
        time.sleep(0.1)
        return sum(p.get("type") == "template" for p in posted)

    try:
        client = a.client()
        a.send(client, "missing_supplier_invoice")
        check(templates(1) == 1, "first held message sends the invitation", templates(1))
        a.send(client, "tax_ready_to_pay")
        check(templates(2) == 1, "a second message soon after sends no second invitation", templates(2))
        with SessionLocal() as db:
            row = db.get(Client, client["id"])
            row.last_reengage_at = datetime.utcnow() - timedelta(hours=settings.whatsapp_reengage_interval_hours + 1)
            db.commit()
        a.send(client, "unidentified_bank_charge")
        check(templates(2) == 2, "a client who ignored the invitation gets a new one after the interval", templates(2))
    finally:
        whatsapp_service.httpx.post = real_post
        for key, value in saved.items():
            setattr(settings, key, value)


def deactivated_clients_get_no_reminders(a: Api) -> None:
    client = a.client()
    ticket = a.send(client, "missing_supplier_invoice")
    a.c.delete(f"/api/clients/{client['id']}")
    r = a.c.post(f"/api/tickets/{ticket['id']}/reopen")
    check(r.status_code == 400, "a deactivated client's ticket cannot be reopened", r.status_code)
    with SessionLocal() as db:  # also covers a ticket left open by an older release
        row = db.get(ChasingTicket, ticket["id"])
        row.status = TicketStatus.WAITING_FOR_CLIENT
        row.next_reminder_at = datetime.utcnow()
        db.commit()
    before = len(a.ticket(ticket)["messages"])
    actions = a.jump()["actions"]
    check(not [x for x in actions if x["client_id"] == client["id"]] and len(a.ticket(ticket)["messages"]) == before,
          "the reminder cycle skips deactivated clients", actions)


def repeated_webhook_delivery_is_ignored(a: Api) -> None:
    client = a.client()
    a.send(client, "missing_supplier_invoice")
    message = {"from": from_phone(client), "id": "wamid.same", "type": "text", "text": {"body": "שלום"}}
    a.meta(messages_envelope(message))
    a.meta(messages_envelope(message))
    chat = a.chat(client)
    check(sum(m["direction"] == "INBOUND" for m in chat) == 1, "the same message delivered twice is saved once", sum(m["direction"] == "INBOUND" for m in chat))
    check(sum("ההודעה שלך" in m["content_text"] for m in chat) == 1, "the same message delivered twice is answered once")

    webhook_router.download_cloud_media = lambda _id: (b"PK", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    client = a.client()
    r = a.meta(messages_envelope({"from": from_phone(client), "id": "wamid.doc", "type": "document", "document": {"id": "d1", "filename": "report.docx"}}))
    check(r.status_code == 200, "an unsupported file does not make Meta retry the batch", r.status_code)
    check(any("report.docx" in m["content_text"] for m in a.chat(client)), "the office sees that an unsupported file arrived", a.chat(client))


def non_text_messages_reach_the_office(a: Api) -> None:
    client = a.client()
    a.meta(messages_envelope({"from": from_phone(client), "id": "wamid.voice", "type": "audio", "audio": {"id": "a1"}}))
    inbound = [m for m in a.chat(client) if m["direction"] == "INBOUND"]
    check(len(inbound) == 1 and inbound[0]["content_text"] == "[הודעה קולית]", "a voice note appears in the chat", inbound)
    a.meta(messages_envelope({"from": from_phone(client), "id": "wamid.video", "type": "video", "video": {"id": "v1"}}))
    check(a.chat(client)[-1]["content_text"] == "[סרטון]", "a video appears in the chat", a.chat(client)[-1]["content_text"])


def excel_dates_become_a_tax_period(a: Api) -> None:
    buffer = io.BytesIO()
    pd.DataFrame([{**SHEET, "tax_period": datetime(2026, 10, 1), "due_date": datetime(2026, 11, 26), "client_tax_id": "666000111",
                   "client_phone": "0529333333", "client_name": "Excel"}]).to_excel(buffer, index=False)
    campaign = a.upload(name="sheet.xlsx", content=buffer.getvalue()).json()["campaign"]
    check(campaign["tax_period"] == "10/2026", "an Excel date becomes MM/YYYY", campaign["tax_period"])
    ticket = a.c.get(f"/api/tickets?client_id={campaign['recipients'][0]['client_id']}").json()[0]
    check("00:00:00" not in a.ticket(ticket)["messages"][0]["content_text"], "the client's message has no raw timestamp")
    r = a.upload([{**SHEET, "tax_period": "ספטמבר-אוקטובר 2026", "client_tax_id": "666000112", "client_phone": "0529333334", "client_name": "Free text"}])
    check(r.json()["campaign"]["tax_period"] == "ספטמבר-אוקטובר 2026", "a period written in words is kept as it is")


def bulk_rows_without_a_phone_are_reported(a: Api) -> None:
    rows = [{**SHEET, "client_tax_id": "888000001", "client_phone": "", "client_name": "No phone A"},
            {**SHEET, "client_tax_id": "888000002", "client_phone": "", "client_name": "No phone B"},
            {**SHEET, "client_tax_id": "888000003", "client_phone": "0529444444", "client_name": "Has phone"}]
    r = a.upload(rows)
    check(r.status_code == 201, "new clients without a phone do not fail the whole upload", r.status_code)
    if r.status_code == 201:
        body = r.json()
        check(body["sent"] == 1 and len(body["errors"]) == 2 and "שורה 2" in body["errors"][0], "those rows are skipped and reported by line", body["errors"])
    r = a.upload(rows[:2])
    check(r.status_code == 400, "a sheet with no sendable row is refused", r.status_code)


def trunk_zero_is_removed(_a: Api) -> None:
    for raw in ("+972-050-1234567", "972 050 1234567", "00972501234567", "050-1234567", "+972501234567"):
        check(whatsapp_service.normalize_phone(raw) == "+972501234567", f"phone {raw} is normalized", whatsapp_service.normalize_phone(raw))
    check(whatsapp_service.normalize_phone("+15550001111") == "+15550001111", "foreign numbers are left alone")


def typed_detail_reminder_asks_for_the_detail(a: Api) -> None:
    client = a.client()
    ticket = a.send(client, "missing_invoice_detail")
    a.c.post("/api/webhook/whatsapp-inbound", json={"client_id": client["id"], "type": "text", "text": "12345"})
    a.jump()
    text = a.ticket(ticket)["messages"][-1]["content_text"]
    check("9 ספרות" in text and "צילום" not in text, "a mistyped number is chased as a number, not a photo", text)


def urgent_label_clears_after_the_deadline(a: Api) -> None:
    client = a.client()
    ticket = a.send(client, "missing_supplier_invoice")
    try:
        freeze_day(25)
        a.jump()
        check(a.ticket(ticket)["priority"] == "URGENT_DEADLINE", "near the deadline the ticket is urgent", a.ticket(ticket)["priority"])
        freeze_day(27)
        a.c.post("/api/scheduler/trigger-48h-check")
        check(a.ticket(ticket)["priority"] == "NORMAL", "after the 26th the urgent label is gone", a.ticket(ticket)["priority"])
    finally:
        freeze_day(None)


def dashboard_counts(a: Api) -> None:
    def automated() -> int:
        return int(a.c.get("/api/dashboard/kpis").json()["hours_saved_basis"].split()[0])

    client = a.client()
    before = automated()
    a.c.post("/api/whatsapp/manual-send", data={"client_id": client["id"], "content_text": "כתבתי בעצמי"})
    check(automated() == before, "hours saved does not count a manual message as automated", (before, automated()))

    ticket = a.send(client, "missing_supplier_invoice")
    with SessionLocal() as db:
        message = db.scalar(select(WhatsAppMessageLog).where(WhatsAppMessageLog.ticket_id == ticket["id"]))
        message.external_id = "ext.1"
        message_id = message.id
        db.commit()
    for status in ("read", "delivered"):
        a.meta({"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"statuses": [{"id": "ext.1", "status": status}]}}]}]})
    with SessionLocal() as db:
        state = db.get(WhatsAppMessageLog, message_id).delivery_status.value
    check(state == "READ", "a late 'delivered' does not undo 'read'", state)


CASES = [
    old_button_cannot_touch_another_request, old_button_cannot_undo_clerk_review, bulk_prefers_the_active_client,
    invitation_is_repeated_after_the_interval, deactivated_clients_get_no_reminders, repeated_webhook_delivery_is_ignored,
    non_text_messages_reach_the_office, excel_dates_become_a_tax_period, bulk_rows_without_a_phone_are_reported, trunk_zero_is_removed,
    typed_detail_reminder_asks_for_the_detail, urgent_label_clears_after_the_deadline, dashboard_counts,
]


def main() -> int:
    with TestClient(app, raise_server_exceptions=False) as c:
        api = Api(c)
        for case in CASES:
            print(f"\n== {case.__name__}")
            try:
                case(api)
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
        from database import engine

        engine.dispose()
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(code)
