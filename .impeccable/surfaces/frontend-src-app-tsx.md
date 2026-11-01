---
version: 1
slug: "frontend-src-app-tsx"
primary_target: "frontend/src/App.tsx"
related_targets: ["frontend/src/pages/QuickDispatch.tsx","frontend/src/pages/ChasingBoard.tsx","frontend/src/pages/BulkTax.tsx","frontend/src/pages/ClientsTemplates.tsx","frontend/src/pages/Settings.tsx","frontend/src/pages/ActivityLog.tsx"]
---

# Surface brief: AccountFlow office dashboard

Scope: the whole authenticated dashboard plus the login screen. Visitor mode: Operate.

Audience and job: bookkeeping and payroll clerks work through client requests for much of the day; the firm owner checks in occasionally. Constraints: Hebrew RTL, light and dark themes, phone simulator keeps looking like real WhatsApp, Send Request fits the window without scrolling on laptop sizes and up, manager-only controls stay unrendered for workers. No behavior, endpoint or Hebrew business copy changes.

User complaints the build must answer: generic, cluttered, hard to scan, not premium.

## Direction contract

THESIS: The office lives by the 26th, so the 26th is the one shape in the product. Flat colour fields and confident Hebrew from the Israeli poster school replace the card-and-badge admin template.

OWN-WORLD: Midnight field, electric-blue selection, one cantaloupe disc, on a pale grey-blue page. Working sections are white panels with thin borders, because the user asked for clear separation. Square corners, no shadows, no gradients. Secular One for page, section and popup titles and the countdown, Assistant for everything else, tabular figures. Cantaloupe means only two things: the 26th, and the clerk's next action. Electric blue means selection and the current place. Rank comes from size and weight. All table rows share one type size and, where a column can carry it, one line. State is a small flat geometric mark in a fixed cell beside its label, never a coloured pill. One form repeats at every scale: the 26 disc is the logo, the month band and the favicon. Amber and red appear only as true warnings.

STORY: A clerk opens the app, sees how many days remain to the 26th and what needs them next, acts, and moves on without hunting. The owner reads the same band and board in one glance.

FIRST VIEWPORT: Midnight rail on the right with a 26 disc logo and plain navigation; the active item is filled electric blue. A midnight band runs across the top of the content, joining the rail into one L-shaped field. The band holds the page title in Secular One with page actions directly under it and, on the opposite side, the countdown as the band's largest type beside a month strip: one column per day, flat white bars for requests opened, outlined bars for reminders still scheduled, today marked in cantaloupe, the 26th as a cantaloupe disc hanging over the band's lower edge. The page's explanation sits under the band in full. Below it the pale work area holds the page's task in bordered white panels. The primary action on each screen is cantaloupe with midnight text.

FORM: Israeli modernist poster and stamp programme, position 6 of my ordered list. seed:e9af3dd82ad8afa3. Signature move: the month band with the 26 disc. Raises kept: hierarchy from size and weight only (Type Specimen); one form at every scale (Bitmap Specimen); one row size with rank from weight and reversal (Timetable Rack); state as a fixed mark in a fixed cell (Convention Catalog).

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Unresolved decisions

These three were changed by the builder during review and await the user's answer:

- Secular One also on section and popup titles and the countdown, not page titles only.
- Page actions directly under the title, not in the title row.
- Outlined bars for scheduled reminders in the month strip, beside the white bars.
