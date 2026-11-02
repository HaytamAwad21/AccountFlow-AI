# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Office staff (primary):** bookkeeping clerks and payroll clerks at Israeli accounting and bookkeeping firms. They keep the dashboard open for much of the working day and work through clients, requests and tickets.
- **Firm owner or office manager (occasional):** opens it once in a while to see what is stuck, and manages clients, templates, settings and staff.
- **End clients (never in this app):** garages, contractors, clinics and mini-markets. They only ever see WhatsApp messages with quick-reply buttons, always in Hebrew.

## Product Purpose

AccountFlow AI chases clients for missing invoices and documents, checks every receipt photo, and sends monthly tax notifications, so a firm's staff stop spending their days on phone calls and manual follow-ups. Success means fewer open requests, fewer clients who need a phone call, and every filing deadline met.

## Positioning

The firm's clients do not install or learn anything: everything happens in WhatsApp, in Hebrew. A nagging engine follows up on its own, Vision AI checks each receipt against Israel Tax Authority rules (9-digit ח.פ / ע.מ, allocation number above the threshold, VAT math at the office's live rate), and silent clients are handed to a clerk for a call.

## Operating Context

- Locally hosted on the firm's own computer, used in the office. It is not a public website.
- The working rhythm follows the VAT deadline, by default the 26th of the reporting month and editable in the office settings, for monthly and bi-monthly clients.
- A clerk's typical pass: send a request, watch the live board, open a ticket, read the WhatsApp timeline and the receipt, approve or reject.
- A built-in phone simulator shows exactly what the client sees in WhatsApp.

## Capabilities and Constraints

- The UI is entirely Hebrew and right to left. Numbers, phone numbers and IDs stay left to right inside Hebrew text.
- Tabs: שליחת בקשה, לוח מעקב חי, הדיווח מוכן, לקוחות ותבניות, יומן פעילות (managers only), הגדרות (always last).
- Manager-only controls are not rendered for workers at all.
- Light and dark themes are both required.
- The phone simulator stays, and keeps looking like real WhatsApp.
- The layout must work on every screen size; the Send Request page must fit the window without scrolling on normal laptop sizes and up.
- React 18, TypeScript, Vite, Tailwind 3.4 with container queries. No component library.

## Brand Commitments

- Name: AccountFlow AI.
- Palette chosen with the user: midnight navy, electric blue and cantaloupe orange.
- The robot logo is not binding and may be redrawn.

## Evidence on Hand

- All names, clients, tickets and firms in the database are seeded demo data.
- There are no real customers, testimonials, benchmarks or prices yet. None may be invented.

## Product Principles

1. The clerk's next action is always the most visible thing on the screen.
2. Tax and money facts are exact. A number is never rounded, hidden or decorated.
3. The client's WhatsApp experience is the truth; the dashboard must show it faithfully.
4. Automation stays visible: what the bot did, and when, is always readable.
5. Looks like something an accounting firm would be proud to pay for, and stays calm through a full working day.

## Accessibility & Inclusion

Hebrew RTL is a first-class requirement. Long daily sessions call for comfortable contrast and no reliance on colour alone for status.
