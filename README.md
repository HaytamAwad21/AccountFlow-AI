# AccountFlow AI

Automated client-chasing, missing-invoice collection and monthly tax notifications for Israeli accounting & bookkeeping firms.

- **Office staff** work in a fast web dashboard that is fully in Hebrew and laid out right to left.
- **End-clients** (garages, contractors, clinics, mini-markets…) never install anything. They get structured WhatsApp messages with quick-reply buttons, **always in Hebrew**. Business and contact names may be Hebrew or English; Arabic names are rejected. Older English or Arabic chat history is rewritten in Hebrew on startup (`services/history.py`).
- A **nagging engine** follows up automatically. It sends a reminder every 48 hours by default, escalates near the monthly filing deadline, and hands silent clients to a worker for a phone call.
- A **Vision AI validator** checks every receipt photo within seconds:
  - Blur.
  - Tax-invoice header and invoice number.
  - Supplier match.
  - Net + VAT = total, at the office's live VAT rate.
  - **Israel Tax Authority (רשות המסים) rules:** a 9-digit supplier ח.פ / ע.מ, and a 9-digit **מספר הקצאה** (allocation number) on invoices at or above the allocation threshold.
- **Manager / worker roles.** Managers administer clients, templates, office settings and staff. Workers send messages, work the chasing board and approve invoices.

## Quick start

```bash
./run_dev.sh
```

The script creates the Python virtualenv, installs backend and frontend dependencies, then starts both servers:

| Service | URL |
| --- | --- |
| Office dashboard (Vite) | http://localhost:5173 |
| API + Swagger UI | http://localhost:8000/docs |

On first start the backend creates `backend/accountflow.db` and seeds it with the following data:

- The office settings row.
- 6 Hebrew WhatsApp templates.
- 3 office users (name, job title and permission are separate fields):
  - מאיה כהן, מנהלת משרד (`MANAGER`).
  - ראמי חדאד, פקיד הנה״ח (`WORKER`).
  - דנה לוי, פקידת שכר (`WORKER`).
- 10 SMB clients, each with a 9-digit ח.פ, an assigned worker and a reporting frequency (monthly or bi-monthly).
- 12 tickets in every state. One of them is a pending allocation-number request.

The VAT deadline is fixed to the 26th of the reporting month. The urgent-deadline escalation therefore fires when the 26th is 3 days away or less. `test_flow.py` pins the date so this path is tested on any day.

A database created by an older release is detected on startup, rebuilt and reseeded automatically.

Options:

```bash
./run_dev.sh --test    # run the backend end-to-end checks first
./run_dev.sh --reset   # wipe and reseed the demo database
```

### Manual start

```bash
cd backend
python -m venv .venv && .venv/bin/pip install -r requirements.txt   # Windows: .venv\Scripts\pip
.venv/bin/python -m uvicorn main:app --reload --port 8000 --timeout-graceful-shutdown 3

cd ../frontend
npm install
npm run dev
```

### Docker (PostgreSQL)

```bash
docker compose up --build
```

This runs PostgreSQL 16, the FastAPI backend and an nginx-served production build of the UI on http://localhost:5173. The only change from local mode is `DATABASE_URL`. No code differs.

## Login and activity log

The dashboard requires a **password login**. The login screen, and the "התחברות למערכת" modal behind the sidebar profile button, both work in two steps:

1. Pick your user card.
2. Type your password.

### Demo logins

These accounts exist only in a freshly seeded demo database. They are not the accounts of a running office.

| Name (`full_name`) | Job title (`job_title`) | Permission (`role`) | E-mail | Password |
| --- | --- | --- | --- | --- |
| מאיה כהן | מנהלת משרד | `MANAGER` (מנהל משרד) | `maya@cohen-cpa.co.il` | `maya1234` |
| ראמי חדאד | פקיד הנה״ח | `WORKER` (עובד משרד) | `rami@cohen-cpa.co.il` | `rami1234` |
| דנה לוי | פקידת שכר | `WORKER` (עובד משרד) | `dana@cohen-cpa.co.il` | `dana1234` |

Change these after the first login:
- Each user can change their own password with **שינוי סיסמה** under the profile button in the sidebar.
- A manager can reset anyone's password from Settings ▸ עובדי המשרד ▸ **עריכה**.

Every password field has an eye button that shows or hides the text.

Upgrading a database from a release without passwords adds the column in place and keeps all data. The seeded accounts get the passwords above. Any other existing user gets `INITIAL_USER_PASSWORD` from `.env` (default `ChangeMe123`).

### Office users (עובדי המשרד)

Each user has three separate fields, plus a status:

| Field | Shown as | Example |
| --- | --- | --- |
| `full_name` (**שם מלא**) | The name on the profile button, login cards and activity log | יעל לוי |
| `job_title` (**תפקיד במשרד**) | A small line under the name; optional | פקידת הנה״ח |
| `role` (**הרשאה**) | A badge: מנהל משרד or עובד משרד; this is what decides permissions | `WORKER` |
| `is_active` (**סטטוס**) | פעיל / הושעה; a suspended user cannot log in and is signed out at once | `true` |

Managers manage users in **הגדרות ▸ עובדי המשרד**:

- **הוספת עובד/ת** opens a popup with these fields:
  - Full name.
  - Job title, with suggestions such as פקיד/ת הנה״ח or פקיד/ת שכר.
  - E-mail.
  - Permission: two cards, one for manager and one for worker.
  - An initial password and its confirmation, at least 6 characters.
  - Status.
- **עריכה** on each row opens the edit popup. It changes the same fields and can set a new password. Leave the password empty to keep the current one. A reset signs the user out of every open session.
- Workers never see these buttons: manager-only controls are not rendered at all for them. The API refuses them with HTTP 403 as well.
- The last active manager cannot be demoted or suspended.

Older databases stored the name and title together, as `"שם - תפקיד"` in `full_name`. On startup they are split into `full_name` and `job_title` automatically, and no data is lost.

### How it works

- **Password storage:** passwords are stored as salted PBKDF2-SHA256 hashes (`services/security.py`) and are never returned by the API.
- **Sessions:**
  - `POST /api/auth/login` returns a random session token. The browser sends it as `Authorization: Bearer <token>`.
  - Only the token's SHA-256 digest is stored, in `user_sessions`.
  - Sessions expire after `SESSION_HOURS` (default 12).
  - Logout, a password reset or suspending a user revokes that user's sessions immediately.
- **Lockout:** after `LOGIN_MAX_FAILURES` wrong passwords (default 5) within `LOGIN_LOCKOUT_MINUTES` (default 15), the account is locked temporarily with HTTP 429.
  - Wrong passwords are counted in a separate `login_failures` table. They never appear in the activity log.
  - A successful login clears that user's failures, and expired attempts are purged automatically.
- **Protected endpoints:** every data endpoint requires a valid session, and `X-User-Id` headers are no longer trusted. These stay public:
  - The WhatsApp webhook, for Meta only: every Cloud API post must carry a valid `X-Hub-Signature-256` (see [WhatsApp](#whatsapp)). Simulator messages and uploads on the same path need a login.
  - The login-screen user list, which has no e-mails.
  - `/api/health`.
  - The real-time event stream, which carries only change notifications.

### Activity log (יומן פעילות)

The `activity_log` table records real operational events only: who did what, when, and from which IP.

| Group | Events (label in the tab) |
| --- | --- |
| Session | **התחברות למערכת** and **התנתקות מהמערכת** |
| Sending | **שליחת בקשה ללקוח** from שליחת בקשה, with the request type and the client's name, e.g. `נשלחה בקשה מסוג ”חשבונית ספק חסרה“ ללקוח …` |
| | **שליחת תזכורות**: manual reminder runs (by the worker) and automatic 48h cycles (shown as **מערכת**), with a count per reminder type |
| | **שליחת דיווח מס בתפוצה** for bulk "הדיווח מוכן" broadcasts |
| Invoices and tickets | **אישור חשבונית**, **דחיית חשבונית** (with the reason), **סגירת פנייה**, **פתיחת פנייה מחדש**, **תיקון שדות חשבונית** |
| Management | Client added, edited or deactivated; template and office settings changes, with old and new values (e.g. the VAT rate); worker accounts added, edited or reset; password changes |

Each row is written in the same database transaction as the change it describes.

**Not logged:** failed logins and mistyped passwords, phone-simulator demo receipts, and automatic cycles that sent nothing. On startup, older `LOGIN_FAILED` and `SIMULATOR_RECEIPT` rows are deleted, and older `SCHEDULER_RUN` rows are renamed to **שליחת תזכורות**. The cleanup is idempotent.

**Who can see it:**
- `GET /api/activity` (filters: `user_id`, `action`, `date_from`, `date_to`, `q`) is manager-only; workers get 403.
- The **יומן פעילות** tab is hidden for workers.

## Roles and permissions

The profile button at the top of the sidebar shows the logged-in user and their role badge (`מנהל משרד` or `עובד משרד`). Clicking it opens the **התחברות למערכת** modal: pick a user and type their password. Suspended users are listed but cannot log in. The API enforces the rules below from the session token, and the UI mirrors them.

| Action | Manager (מנהל משרד) | Worker (עובד משרד) |
| --- | --- | --- |
| Send messages (templates and manual text / pictures), bulk tax broadcasts, WhatsApp simulator | Yes | Yes |
| Live chasing board, approve, reject or close tickets, correct OCR fields | Yes | Yes |
| Add, edit or deactivate clients (buttons and the actions column) | Yes | hidden |
| Edit message templates | Yes | hidden; workers see the Hebrew text only |
| **הגדרות** tab: VAT rate, allocation threshold, reminder interval, max reminders, firm name, auto-approve | Yes, edit | Read-only: inputs disabled, no שמירת הגדרות / ביטול שינויים buttons |
| **הוספת עובד/ת** (name, job title, e-mail, permission, initial password, status) and **עריכה** (same fields + password reset) via `POST /api/users` and `PUT /api/users/{user_id}` | Yes | hidden: the whole **עובדי המשרד** section is not rendered |
| Read the activity log (`GET /api/activity`, **יומן פעילות** tab) | Yes | tab hidden |
| Auto-approve switch on the chasing board | Yes | hidden |

"Hidden" means the control is not rendered at all, not merely disabled or marked with a lock. Workers can view and search clients and templates and read the office rules in הגדרות, but every management action is hidden. A worker who opens `#activity` directly is sent back to **שליחת בקשה**. The API enforces the same rules: endpoints answer `401` without a valid session and `403` (`הרשאת מנהל בלבד`) when the user is a worker. The last active manager cannot be demoted or deactivated.

### Sidebar and dark mode

- **Navigation order:** שליחת בקשה, לוח מעקב חי, הדיווח מוכן, לקוחות ותבניות, יומן פעילות (managers only), הגדרות. הגדרות is always last and visible to everyone.
- **Profile card:** the logged-in user's avatar, name, role badge, **שינוי סיסמה** and **התנתקות** sit at the bottom of the sidebar, under the phone-simulator button.
- **Dark mode:** click the blue robot logo at the top to switch between light and dark mode. Hovering it shows the tooltip "מעבר למצב כהה / בהיר".
  - The choice is saved in `localStorage` as `accountflow.theme`. Without a saved choice, the app follows the system setting.
  - The theme is applied before the first paint, so the page doesn't flash white on load.
  - The whole UI switches, including cards, tables, modals and inputs. The phone simulator uses WhatsApp's own dark colors.
  - All dark colors are defined in one place, the dark-mode block in `frontend/src/index.css`.

## Israel Tax Authority rules

**Typed replies.** Ask a client for a detail with the *פרט חסר* template and put `מספר הקצאה`, or a ח.פ / ע.מ, in the "missing detail" field. The bot then validates the client's typed WhatsApp reply against `^\d{9}$`. Spaces and dashes are ignored, so `123-456-789` is accepted.

- **Invalid reply** (5 digits, 10 digits, letters…): the ticket moves to `NEEDS_CORRECTION`, stays open, and the client immediately gets this reply:
  > מספר ההקצאה שהזנת אינו תקין. לפי הוראות רשות המסים, מספר הקצאה חייב להכיל בדיוק 9 ספרות. אנא הקלד את המספר המדויק מחדש.

  An invalid ח.פ / ע.מ gets the equivalent message asking for a valid 9-digit ID.
- **Valid reply:** the value is stored on the ticket, the client gets a confirmation, and the ticket moves to `NEEDS_CLERK_REVIEW`.

**Invoice photos.** Vision AI rejects the following:
- A supplier ח.פ that isn't 9 digits.
- A missing or invalid allocation number when the invoice's amount before VAT is at or above `allocation_number_threshold_nis` (default ₪10,000).
- A VAT amount that doesn't match the current VAT rate.

**Other places.** Client records and bulk tax sheets require a 9-digit ח.פ / ע.מ. Excel's dropped leading zero is restored for 8-digit IDs.

## Office settings (הגדרות)

Settings live in a single `system_settings` row. `GET /api/settings` returns it, and `PUT /api/settings` updates it (manager only). Every engine reads the live values.

| Setting | Default | Effect |
| --- | --- | --- |
| `vat_rate` (%) | 18 | Vision AI math check, demo invoices, VAT breakdowns in the UI |
| `allocation_number_threshold_nis` | 10,000 | Amount before VAT from which an allocation number is mandatory |
| `reminder_interval_hours` | 48 | Reminder cadence for new reminders |
| `max_reminders` | 3 | Reminders before escalation; also applied to open tickets |
| `firm_name` | כהן ושות׳ - רואי חשבון | WhatsApp sender name and simulator header |
| `auto_approve_verified` | false | Resolve fully verified invoices without worker review |

The row also records `updated_at` and `updated_by_user_id`. The values in `.env` are only the initial defaults.

The VAT deadline is not a setting. It is always the **26th** of the reporting month (`VAT_DEADLINE_DAY` in `services/clock.py`), and the API returns it read-only as `vat_deadline_day`.

### Reporting frequency

Each client has a `reporting_frequency`:

- `MONTHLY` (דיווח חד חודשי): the deadline is the 26th of every month.
- `BIMONTHLY` (דיווח דו חודשי): periods are Jan–Feb, Mar–Apr and so on. Each period is reported on the 26th of the following odd month (Jan, Mar, May, Jul, Sep, Nov).

Managers set the frequency in the client form. The clients table shows it next to the next deadline. Bulk tax sheets may include an optional `reporting_frequency` column for new clients.

## 5-minute demo script

1. **שליחת בקשה.**
   1. Search for a client and press Enter.
   2. Choose **חשבונית חסרה** and type a supplier and an amount. `1240` becomes `₪1,240.00`, and the VAT breakdown at the live rate appears under the field.
   3. Press **Enter**. The message appears on the client's phone, with buttons.
2. **Phone simulator.**
   1. Tap **קבלה מטושטשת**. Vision AI rejects the photo, and the bot answers within a second.
   2. Tap **חשבונית תקינה**. The ticket moves to *ממתין לבדיקת פקיד*.
3. **Allocation number.**
   1. Select יוסי מזרחי in the simulator.
   2. On the allocation-number request, tap **הקלדת הפרט החסר** and type `12345`. The Tax Authority rejection arrives, and the ticket stays open.
   3. Type `123456789`. The number is accepted.
4. **לוח מעקב חי.** Click **הדמיית +48 שעות**. Notifications list every reminder and deadline escalation that was sent. Open a ticket to see the following:
   - The WhatsApp timeline.
   - The receipt.
   - The six Vision AI and Tax Authority checks.
   - **אישור החשבונית וסגירה**.
5. **Roles.**
   1. Switch to ראמי חדאד from the profile card at the bottom of the sidebar. The client and template editing buttons disappear, and so does the יומן פעילות tab. הגדרות stays, read-only, without the team section.
   2. Switch back to מאיה כהן and change the VAT rate to 17%. New invoice checks now use 17%.

## Architecture

```
backend/
  main.py                 FastAPI app, lifespan (DB init + schema upgrade, seed, SSE loop, APScheduler)
  config.py               env-driven settings (.env) — initial values for system_settings
  database.py             SQLAlchemy 2.0 engine/session (SQLite ⇄ PostgreSQL), outdated-schema rebuild
  models.py               User, Client, SystemSettings, MessageTemplate, ChasingTicket, WhatsAppMessageLog,
                          BulkTaxCampaign, BulkTaxRecipient
  schemas.py              Pydantic v2 request/response models + serializers
  seed.py                 settings, users, Hebrew templates, Hebrew / English-named clients, tickets in every state
  test_flow.py            end-to-end verification (257 checks)
  services/
    system_settings.py    live office configuration accessors
    ticket_engine.py      quick-send, button/text/media state machine, 9-digit Tax Authority validation
    scheduler.py          reminders, 20:00 snooze pings, deadline escalation
    vision_ocr.py         Vision AI: OpenAI gpt-4o-mini | Gemini 2.5 Flash | offline simulator + ITA rules
    demo_invoices.py      renders realistic invoice PNGs (incl. allocation numbers) for the demo buttons
    bulk_tax.py           CSV/XLSX tax sheet → personalised broadcast
    whatsapp.py           Meta Cloud API adapter + E.164 normalisation
    events.py             commit-aware Server-Sent-Events broker
    i18n.py               Hebrew engine replies, Hebrew / English name rule (no Arabic)
  routers/                deps (roles), core (users, clients, templates, settings, KPIs),
                          tickets, webhook, scheduler, campaigns
frontend/src/             Hebrew, RTL (dir="rtl", logical Tailwind classes)
  App.tsx                 sidebar shell, profile switcher, 5 tabs, phone simulator
  context/AppContext.tsx  shared state, signed-in user, SSE stream with polling fallback, toasts
  pages/                  QuickDispatch, ChasingBoard, BulkTax, ClientsTemplates, Settings
  components/             PhoneSimulator, WaBubble, TicketModal, ui kit (LockBadge, RoleBadge…)
```

### Ticket state machine

```
quick-send ──► WAITING_FOR_CLIENT ──(interval, ≤ max)──► reminder ──(no reply)──► ESCALATED
                 │   ▲                 └─ deadline ≤3 days → URGENT_DEADLINE warning (24h cadence)
   "Remind 8PM" ─┘   └── 20:00 ping ── SNOOZED_TONIGHT
                 │
   photo/PDF ──► Vision AI ──fail──► NEEDS_CORRECTION (instant re-prompt, chase continues)
                     └──pass──► NEEDS_CLERK_REVIEW ──Approve──► RESOLVED
   typed מספר הקצאה / ח.פ ──not 9 digits──► NEEDS_CORRECTION (Tax Authority reply)
                          └──9 digits────► NEEDS_CLERK_REVIEW
   buttons: Paid / Business / Personal expense ──► RESOLVED     Call me ──► ESCALATED
```

### Vision AI

The provider depends on the API keys you set:

- **`OPENAI_API_KEY` set:** OpenAI `gpt-4o-mini` reads images and PDFs and returns JSON. The JSON includes the allocation number.
- **`GEMINI_API_KEY` set:** Gemini `gemini-2.5-flash` does the same.
- **No key:** the deterministic offline simulator runs.
  - It runs the real Laplacian blur detector on any photo.
  - It reads the embedded text layer of the simulator's demo invoices.
  - A sharp real photo it cannot read goes to worker review, where the worker can type the fields. The fields are then re-validated.

A network or quota failure in a provider falls back to offline mode automatically.

### WhatsApp

Every outbound message goes to the in-app simulator over SSE. When `WHATSAPP_TOKEN` and `WHATSAPP_PHONE_NUMBER_ID` are set, it is also sent through the Meta Cloud API as an interactive reply-button message.

Point your Meta app webhook at `POST /api/webhook/whatsapp-inbound`. The verify token is `WHATSAPP_VERIFY_TOKEN`.

Set `WHATSAPP_APP_SECRET` to your Meta App Secret (App settings ▸ Basic). The webhook checks the `X-Hub-Signature-256` header on every Meta post: an HMAC-SHA256 of the raw body, keyed with that secret. A missing or wrong signature gets HTTP 403, and nothing is processed. While the secret is empty, every Meta post is refused.

Meta also limits reply-button titles to 20 characters.

#### The 24-hour window

Meta accepts free-form and reply-button messages only within 24 hours of the client's last message. Requests and reminders usually go out after that window has closed, so the app handles it like this:

1. **Window open** (the client wrote in the last 24 hours): messages are sent directly, as before.
2. **Window closed:** the message is saved in the chat but held. The dashboard marks it **ממתינה ללקוח**. The app sends the client one Meta-approved template instead, which invites them to tap **הצגת ההודעה**. Further messages to the same client are held too, without another template.
3. **The client taps the button or writes anything:** every held message goes out, oldest first, before any bot reply.
4. **Outdated held messages are dropped, not sent:** per request, only the newest held reminder goes out. If the request itself was still held, it goes out without its reminders; if the request was closed meanwhile, none of its held messages go out. Dropped messages show **לא נשלחה** in the chat (status `SKIPPED`). Manual messages always go out.

If Meta still answers a send with error `131047` (window closed), the message is held the same way.

Create the template in WhatsApp Manager and set its name in `WHATSAPP_REENGAGE_TEMPLATE` (language `WHATSAPP_TEMPLATE_LANGUAGE`, default `he`). Suggested template:

| Field | Value |
| --- | --- |
| Name | `accountflow_pending_update` |
| Category | Utility |
| Language | Hebrew (`he`) |
| Body | `שלום {{1}}, יש לך הודעה חדשה מ{{2}} בנוגע לתיק שלך. לחצו על הכפתור כדי לקרוא אותה.` |
| Button | Quick reply: `הצגת ההודעה` |

`{{1}}` is the client's name and `{{2}}` the firm name from הגדרות. Without a template name, closed-window messages are held until the client writes on their own, and the dashboard explains why.

This applies only when the Cloud API is configured. In simulator-only mode every message appears on the simulated phone at once.

## Key API endpoints

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| GET / POST / PUT | `/api/users`, `/api/users/{id}` | read: logged-in · write: manager | Office staff: `full_name`, `job_title`, `role`, `is_active`, password |
| GET / POST | `/api/auth/users`, `/api/auth/login`, `/api/auth/logout`, `/api/auth/me`, `/api/auth/change-password` | login list: public · rest: session | Password login and sessions |
| GET | `/api/activity` | manager | Activity log (יומן פעילות) |
| GET / PUT | `/api/settings` | read: all · write: manager | Office configuration |
| POST / PUT / DELETE | `/api/clients…` | manager | Client management (soft delete) |
| POST | `/api/tickets/quick-send` | any user | Render in the client's language, create the ticket, dispatch |
| POST | `/api/whatsapp/manual-send` | any user | Worker's manual message (multipart: `client_id`, `content_text`, `image_file` / `image_base64` / `media_url`); not automated, logged as **שליחת הודעה ידנית ללקוח** |
| POST | `/api/tickets/{id}/approve` | any user | Approve a verified invoice |
| POST | `/api/tickets/{id}/reject` | any user | Reject the invoice `{reason}`: the client gets the Hebrew re-prompt with the reason, and the ticket returns to NEEDS_CORRECTION |
| POST | `/api/webhook/whatsapp-inbound` | Meta: signed (`X-Hub-Signature-256`) · simulator: any user | Simulator JSON, Meta envelope or multipart upload; 9-digit validation |
| POST | `/api/simulator/demo-receipt` | public | `clear`, `blurry`, `missing_number`, `wrong_supplier`, `bad_math`, `missing_allocation`, `invalid_tax_id` |
| POST | `/api/scheduler/simulate-time-jump?hours=48` | public | Move pending reminders back, run the cycle (demo) |
| POST | `/api/campaigns/bulk-tax-upload`, `/api/campaigns/demo-batch` | any user | Bulk "tax is ready" broadcast |
| GET | `/api/events/stream` | public | Server-Sent Events for real-time UI updates |

Full interactive docs are at `/docs`.

## Tests

```bash
cd backend && python test_flow.py
```

The test runs against a temporary database through the real HTTP API. It covers the following:

- **Seed data:** seeded users and settings.
- **Permissions:**
  - A worker gets `403` on clients, settings, templates and users.
  - An anonymous caller gets `401`.
  - The last manager is protected.
- **Messaging:**
  - Trilingual quick-send.
  - Reminders and deadline escalation.
- **Typed-reply rules:** allocation-number and ח.פ validation, including the exact Hebrew reply for 5-digit, 10-digit, alphanumeric and valid inputs.
- **Vision AI:**
  - Blurry, missing-number, invalid-ח.פ and missing-allocation invoices.
  - Live VAT-rate and threshold changes.
  - Real JPEG uploads.
- **Other flows:**
  - Bulk sheet validation.
  - Client deactivation.
  - The Meta webhook format.
  - Webhook security: unsigned, wrongly signed or secret-less Meta posts get `403`; simulator posts without a login get `401`.
  - The 24-hour window, against a faked Cloud API: held messages, one re-engagement template, release in order on a tap or a reply, error `131047`, and no template configured.
