"""Seed data: office settings, 6 Hebrew WhatsApp templates, 3 office users (1 manager, 2 workers),
10 SMB clients (Hebrew or English business names) and live tickets in every state.

Run automatically on first startup (SEED_ON_STARTUP=true) or manually:
    python seed.py          # seed only if the DB is empty
    python seed.py --reset  # drop everything and reseed
"""
from __future__ import annotations

import argparse
import sys
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import SessionLocal, init_db, reset_db
from models import (
    ChasingTicket,
    Client,
    MessageTemplate,
    MessageType,
    ReportingFrequency,
    TemplateCategory,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
)
from services.clock import local_today, utcnow
from services.demo_invoices import generate_invoice_image, parse_amount
from services.security import hash_password
from services.system_settings import get_system_settings

TEMPLATES: list[dict] = [
    {
        "slug": "missing_supplier_invoice",
        "category": TemplateCategory.MISSING_INVOICE,
        "requires_media_reply": True,
        "name_he": "חשבונית ספק חסרה",
        "body_he": (
            "שלום {{client_name}} 👋\n"
            "במסגרת בדיקת הנהלת החשבונות החודשית ראינו תשלום בסך {{amount}} לספק '{{supplier_name}}' "
            "בתאריך {{invoice_date}}, אך חשבונית המס חסרה בתיק שלך.\n"
            "נא להשיב עם צילום ברור או קובץ PDF של החשבונית כדי שנוכל לקזז עבורך את המע\"מ."
        ),
        "buttons_json": [
            {"id": "upload_photo", "action": "REQUEST_MEDIA", "he": "📷 העלאת צילום חשבונית"},
            {"id": "remind_8pm", "action": "SNOOZE_TONIGHT", "he": "⏰ תזכירו לי ב-20:00"},
            {"id": "no_document", "action": "NO_DOCUMENT", "he": "❓ אין לי אותה"},
        ],
    },
    {
        "slug": "missing_invoice_detail",
        "category": TemplateCategory.MISSING_DETAIL,
        "requires_media_reply": True,
        "name_he": "חסר פרט בחשבונית (מספר / ח.פ / פרט אחר)",
        "body_he": (
            "שלום {{client_name}} 👋\n"
            "בנוגע לחשבונית מס' {{invoice_number}} מהספק '{{supplier_name}}': חסר בה '{{missing_detail}}'.\n"
            "נא לשלוח חשבונית מתוקנת או להשיב עם הפרט החסר כדי שנוכל לרשום אותה כראוי."
        ),
        "buttons_json": [
            {"id": "send_corrected", "action": "REQUEST_MEDIA", "he": "📷 שליחת צילום מתוקן"},
            {"id": "type_detail", "action": "TYPE_DETAIL", "he": "✍️ הקלדת הפרט החסר"},
            {"id": "remind_tonight", "action": "SNOOZE_TONIGHT", "he": "⏰ תזכירו לי הערב"},
        ],
    },
    {
        "slug": "unidentified_bank_charge",
        "category": TemplateCategory.UNIDENTIFIED_CHARGE,
        "requires_media_reply": False,
        "name_he": "חיוב לא מזוהה בכרטיס / בבנק",
        "body_he": (
            "שלום {{client_name}} 👋\n"
            "מופיע חיוב בבנק / בכרטיס האשראי על סך {{charge_amount}} בתאריך {{charge_date}} "
            "(אסמכתא: {{bank_reference}}) ללא חשבונית או תיאור תואם.\n"
            "עבור מה הייתה ההוצאה, והאם אפשר לצרף את החשבונית?"
        ),
        "buttons_json": [
            {"id": "attach_receipt", "action": "REQUEST_MEDIA", "he": "📷 צירוף קבלה"},
            {"id": "business_no_receipt", "action": "BUSINESS_NO_RECEIPT", "he": "🏢 הוצאה עסקית (ללא קבלה)"},
            {"id": "personal_expense", "action": "PERSONAL_EXPENSE", "he": "🏠 הוצאה פרטית"},
        ],
    },
    {
        "slug": "tax_ready_to_pay",
        "category": TemplateCategory.TAX_READY,
        "requires_media_reply": False,
        "name_he": "דיווח מע\"מ ומקדמות מוכן לתשלום",
        "body_he": (
            "שלום {{client_name}} 👋\n"
            "הדיווח שלך עבור {{tax_period}} מוכן.\n"
            "🧾 מע\"מ לתשלום: {{vat_amount}}\n"
            "📊 מקדמות מס: {{tax_advance_amount}}\n"
            "📅 מועד אחרון לתשלום: {{due_date}}\n"
            "נא לאשר למטה לאחר התשלום או לאשר חיוב מחשבון הבנק."
        ),
        "buttons_json": [
            {"id": "paid_confirmed", "action": "PAID_CONFIRMED", "he": "✅ שולם / מאושר"},
            {"id": "pay_link", "action": "PAY_LINK", "he": "💳 תשלום בשובר / קישור"},
            {"id": "request_call", "action": "REQUEST_CALL", "he": "📞 בקשת שיחה מרו\"ח"},
        ],
    },
    {
        "slug": "blurry_or_wrong_receipt_reprompt",
        "category": TemplateCategory.MISSING_INVOICE,
        "requires_media_reply": True,
        "is_system": True,
        "name_he": "דחיית Vision AI — בקשה חוזרת",
        "body_he": (
            "תודה {{client_name}}! 🙏\n"
            "בדקתי עכשיו את הצילום ששלחת עבור '{{supplier_name}}', אבל {{rejection_reason}}.\n"
            "מכיוון שהמסמך עדיין לידך, אפשר לצלם שוב תמונה ברורה אחת שבה רואים את העמוד המלא ואת מספר החשבונית? 📷"
        ),
        "buttons_json": [
            {"id": "send_clearer", "action": "REQUEST_MEDIA", "he": "📷 שליחת צילום ברור יותר"},
            {"id": "send_to_clerk", "action": "SEND_CLERK_ANYWAY", "he": "👨‍💼 להעביר לפקיד בכל זאת"},
        ],
    },
    {
        "slug": "monthly_folder_deadline_warning",
        "category": TemplateCategory.MONTHLY_FOLDER,
        "requires_media_reply": True,
        "name_he": "הסלמה לקראת מועד הדיווח (ה-15 בחודש)",
        "body_he": (
            "⚠️ תזכורת דחופה עבור {{client_name}}:\n"
            "נותרו רק {{days_left}} ימים עד המועד האחרון לדיווח החודשי, ואנחנו עדיין ממתינים ל-{{open_items_count}} פריטים חסרים.\n"
            "נא לשלוח אותם עוד היום כדי שהדיווח או החזר המע\"מ שלך לא יתעכבו."
        ),
        "buttons_json": [
            {"id": "upload_now", "action": "REQUEST_MEDIA", "he": "📷 להעלות עכשיו"},
            {"id": "call_me", "action": "REQUEST_CALL", "he": "📞 תתקשרו אליי"},
        ],
    },
]

# Demo login passwords (documented in README.md). Change them from Settings ▸ עריכה after the first login.
SEED_PASSWORDS = {
    "maya@cohen-cpa.co.il": "maya1234",
    "rami@cohen-cpa.co.il": "rami1234",
    "dana@cohen-cpa.co.il": "dana1234",
}

USERS = [
    {"full_name": "מאיה כהן", "job_title": "מנהלת משרד", "email": "maya@cohen-cpa.co.il", "role": UserRole.MANAGER, "avatar_initials": "מכ"},
    {"full_name": "ראמי חדאד", "job_title": "פקיד הנה״ח", "email": "rami@cohen-cpa.co.il", "role": UserRole.WORKER, "avatar_initials": "רח"},
    {"full_name": "דנה לוי", "job_title": "פקידת שכר", "email": "dana@cohen-cpa.co.il", "role": UserRole.WORKER, "avatar_initials": "דל"},
]


def _clients() -> list[dict]:
    return [
        {"full_name": "משה גבאי", "company_name": "מוסך גבאי", "tax_id": "514782301", "whatsapp_phone": "+972521234501",
         "worker": 1, "notes": "מוסך בחדרה. מעדיף שיחות טלפון אחרי 18:00."},
        {"full_name": "יוסי מזרחי", "company_name": "מזרחי שיפוצים ובנייה בע\"מ", "tax_id": "515903377", "whatsapp_phone": "+972541234502",
         "worker": 2, "notes": "קבלן שיפוצים, 6 קבלני משנה."},
        {"full_name": "ד״ר רונית חדד", "company_name": "מרפאת חדד לרפואת המשפחה", "tax_id": "037845129", "whatsapp_phone": "+972501234503",
         "reporting_frequency": ReportingFrequency.BIMONTHLY, "worker": 1, "notes": "מרפאה משפחתית בחיפה. מדווחת מע\"מ דו-חודשי."},
        {"full_name": "נועה בן-דוד", "company_name": "בן-דוד הנדסה וייעוץ", "tax_id": "516447820", "whatsapp_phone": "+972531234504",
         "worker": 3, "notes": "משרד ייעוץ להנדסת מבנים."},
        {"full_name": "Michael Turner", "company_name": "Turner & Co. Digital Studio", "tax_id": "516220945", "whatsapp_phone": "+972501234505",
         "worker": 3, "notes": "מייסד יליד בריטניה; אנגלית בלבד."},
        {"full_name": "שמעון נסים", "company_name": "מינימרקט נסים", "tax_id": "039912476", "whatsapp_phone": "+972521234506",
         "worker": 2, "notes": "מינימרקט בקריית ביאליק. הרבה ספקים קטנים."},
        {"full_name": "אבי פרץ", "company_name": "פרץ קבלנות חשמל", "tax_id": "025567781", "whatsapp_phone": "+972541234507",
         "worker": 2, "notes": "קבלן חשמל, לרוב נמצא באתרי עבודה."},
        {"full_name": "לימור אוחנה", "company_name": "מאפיית אוחנה", "tax_id": "514006632", "whatsapp_phone": "+972501234508",
         "reporting_frequency": ReportingFrequency.BIMONTHLY, "worker": 1, "notes": "מאפייה ובית קפה, שני סניפים."},
        {"full_name": "Daniel Klein", "company_name": "Klein Dental Care", "tax_id": "033190458", "whatsapp_phone": "+972531234509",
         "reporting_frequency": ReportingFrequency.BIMONTHLY, "worker": 3, "notes": "מרפאת שיניים ברעננה."},
        {"full_name": "תמר אזולאי", "company_name": "אזולאי קייטרינג ואירועים", "tax_id": "515338104", "whatsapp_phone": "+972521234510",
         "worker": 1, "notes": "קייטרינג לאירועים, עומסים עונתיים."},
    ]


def _backdate(db: Session, ticket: ChasingTicket, hours_ago: float) -> None:
    """Spread a ticket's message history over the past `hours_ago` hours."""
    db.flush()
    db.refresh(ticket)
    now = utcnow()
    start = now - timedelta(hours=hours_ago)
    msgs = sorted(ticket.messages, key=lambda m: m.id)
    span = hours_ago * 0.9
    for i, m in enumerate(msgs):
        offset = span * (i / max(1, len(msgs) - 1)) if len(msgs) > 1 else 0
        m.created_at = start + timedelta(hours=offset)
    ticket.created_at = start
    if msgs:
        last_out = [m for m in msgs if m.direction.value == "OUTBOUND"]
        ticket.last_contacted_at = (last_out[-1] if last_out else msgs[-1]).created_at


def _add_reminders(db: Session, ticket: ChasingTicket, count: int) -> None:
    from services.scheduler import _reminder_text
    from services.templating import localized_buttons
    from services.ticket_engine import lang_of, send_outbound

    for _ in range(count):
        ticket.reminder_count += 1
        lang = lang_of(ticket.client)
        send_outbound(db, ticket.client, ticket, _reminder_text(ticket, lang),
                      localized_buttons(ticket.template, lang), MessageType.AUTO_REMINDER, external=False)


def _upload_demo(db: Session, ticket: ChasingTicket, scenario: str) -> None:
    from services.ticket_engine import handle_media

    ctx = ticket.context_variables_json or {}
    path, _ = generate_invoice_image(
        scenario=scenario,
        supplier_name=ctx.get("supplier_name") or "Office Supplies Ltd.",
        invoice_number=ctx.get("invoice_number"),
        client_company=ticket.client.company_name,
        amount_total=parse_amount(ctx.get("amount") or ctx.get("charge_amount")),
        invoice_date=ctx.get("invoice_date"),
        vat_rate=get_system_settings(db).vat_rate / 100.0,
        allocation_threshold=get_system_settings(db).allocation_number_threshold_nis,
    )
    handle_media(db, ticket.client, path, f"/uploads/{path.name}", "image/png", ticket.id, "📸")


def seed_demo(db: Session) -> dict:
    from services.ticket_engine import approve_ticket, create_and_send_ticket, handle_button

    if db.scalar(select(MessageTemplate.id).limit(1)):
        return {"seeded": False}

    get_system_settings(db)  # creates the single office-settings row with its defaults
    users = [User(**u, password_hash=hash_password(SEED_PASSWORDS[u["email"]])) for u in USERS]
    db.add_all(users)
    db.flush()

    templates: dict[str, MessageTemplate] = {}
    for data in TEMPLATES:
        tpl = MessageTemplate(**{"is_system": False, **data})
        db.add(tpl)
        templates[data["slug"]] = tpl
    db.flush()

    clients: list[Client] = []
    for data in _clients():
        data = dict(data)
        worker_idx = data.pop("worker")
        clients.append(Client(**data, assigned_worker_id=users[worker_idx - 1].id))
    db.add_all(clients)
    db.flush()

    today = local_today()

    def d(days_ago: int) -> str:
        return (today - timedelta(days=days_ago)).strftime("%d/%m/%Y")

    def send(client: Client, slug: str, **variables) -> ChasingTicket:
        ticket, _ = create_and_send_ticket(db, client=client, template=templates[slug], variables=variables, external=False)
        return ticket

    now = utcnow()
    c = clients

    # 1. Gabay garage — waiting, sent 30h ago
    t1 = send(c[0], "missing_supplier_invoice", supplier_name="Delek Fuel Station", amount="₪1,240.00", invoice_date=d(12))
    _backdate(db, t1, 30)
    t1.next_reminder_at = now + timedelta(hours=18)

    # 2. Mizrahi renovations (HE) — missing ח.פ, 1 reminder sent, overdue (urgent if the 26th is ≤ 3 days away)
    t2 = send(c[1], "missing_invoice_detail", supplier_name="Ace Building Supplies", invoice_number="88412",
              missing_detail="מספר עוסק מורשה של הספק")
    _add_reminders(db, t2, 1)
    _backdate(db, t2, 100)
    t2.next_reminder_at = now - timedelta(hours=2)

    # 3. Haddad clinic — unidentified card charge
    t3 = send(c[2], "unidentified_bank_charge", charge_amount="₪2,350.00", charge_date=d(9), bank_reference="CC-7781-2290")
    _backdate(db, t3, 20)
    t3.next_reminder_at = now + timedelta(hours=28)

    # 4. Ben-David engineering (HE) — sent a blurry photo → NEEDS_CORRECTION
    t4 = send(c[3], "missing_supplier_invoice", supplier_name="Office Depot Israel", amount="₪865.40", invoice_date=d(15))
    _upload_demo(db, t4, "blurry")
    _backdate(db, t4, 26)
    t4.next_reminder_at = now + timedelta(hours=22)

    # 5. Turner studio (EN) — clear invoice verified by Vision AI → NEEDS_CLERK_REVIEW
    t5 = send(c[4], "missing_supplier_invoice", supplier_name="Adobe Systems Software Ireland", amount="₪1,980.00", invoice_date=d(6))
    _upload_demo(db, t5, "clear")
    _backdate(db, t5, 8)

    # 6. Nissim mini-market — 2 reminders, overdue (urgent if the 26th is ≤ 3 days away)
    t6 = send(c[5], "missing_supplier_invoice", supplier_name="Tnuva Dairy", amount="₪3,412.75", invoice_date=d(18))
    _add_reminders(db, t6, 2)
    _backdate(db, t6, 150)
    t6.next_reminder_at = now - timedelta(hours=1)

    # 7. Peretz electric (HE) — 3 reminders ignored → ESCALATED
    t7 = send(c[6], "missing_supplier_invoice", supplier_name="Electra Wholesale", amount="₪5,760.00", invoice_date=d(24))
    _add_reminders(db, t7, 3)
    _backdate(db, t7, 200)
    t7.status = TicketStatus.ESCALATED
    t7.priority = TicketPriority.HIGH
    t7.next_reminder_at = None

    # 8. Ohana bakery — verified & approved
    t8 = send(c[7], "missing_supplier_invoice", supplier_name="Shufersal Wholesale", amount="₪2,104.30", invoice_date=d(10))
    _upload_demo(db, t8, "clear")
    approve_ticket(db, t8, users[0])
    _backdate(db, t8, 50)
    t8.resolved_at = now - timedelta(hours=4)

    # 9. Klein dental (EN) — corrected invoice verified & approved
    t9 = send(c[8], "missing_invoice_detail", supplier_name="Henry Schein Dental", invoice_number="HS-55021",
              missing_detail="מספר עוסק מורשה של הספק")
    _upload_demo(db, t9, "clear")
    approve_ticket(db, t9, users[2])
    _backdate(db, t9, 70)
    t9.resolved_at = now - timedelta(hours=20)

    # 10. Azulay catering (HE) — tapped "Remind me tonight" → SNOOZED_TONIGHT
    t10 = send(c[9], "missing_invoice_detail", supplier_name="Rami Levy Wholesale", invoice_number="771093",
               missing_detail="שם העסק המלא שלנו")
    handle_button(db, c[9], "remind_tonight", t10.id)
    _backdate(db, t10, 5)

    # Extra: Gabay garage resolved earlier this week (second approved invoice)
    t11 = send(c[0], "missing_supplier_invoice", supplier_name="Auto Parts Galil", amount="₪4,318.00", invoice_date=d(20))
    _upload_demo(db, t11, "clear")
    approve_ticket(db, t11, users[1])
    _backdate(db, t11, 90)
    t11.resolved_at = now - timedelta(hours=60)

    # 12. Mizrahi renovations (HE) — a ₪18,400 invoice is missing its Tax Authority allocation number
    t12 = send(c[1], "missing_invoice_detail", supplier_name="Ace Building Supplies", invoice_number="90233",
               missing_detail="מספר הקצאה")
    _backdate(db, t12, 3)
    t12.next_reminder_at = now + timedelta(hours=45)

    db.commit()
    return {"seeded": True, "users": len(users), "clients": len(clients), "templates": len(templates), "tickets": 12}


def seed_if_empty() -> dict:
    with SessionLocal() as db:
        return seed_demo(db)


def ensure_passwords() -> list[str]:
    """Give every user without a password one they can log in with: the demo password for the
    seeded accounts, otherwise INITIAL_USER_PASSWORD from config. Returns the affected e-mails."""
    from config import settings

    fixed: list[str] = []
    with SessionLocal() as db:
        for user in db.scalars(select(User).where(User.password_hash == "")):
            user.password_hash = hash_password(SEED_PASSWORDS.get(user.email, settings.initial_user_password))
            fixed.append(user.email)
        db.commit()
    return fixed


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the AccountFlow AI database")
    parser.add_argument("--reset", action="store_true", help="drop all tables before seeding")
    args = parser.parse_args()
    if args.reset:
        reset_db()
    else:
        init_db()
    result = seed_if_empty()
    print(result)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
