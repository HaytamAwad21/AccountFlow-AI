---
name: AccountFlow AI
description: The office dashboard that counts down to the 26th, in flat midnight, electric blue and cantaloupe.
colors:
  field: "#0d1533"
  field-muted: "#b9c2df"
  canvas: "#f4f6fb"
  surface: "#ffffff"
  white: "#ffffff"
  link: "#1f55e0"
  accent: "#ffb27a"
  accent-deep: "#ffa05c"
  accent-ink: "#0d1533"
  accent-ink-hover: "#1a2450"
  ink-50: "#f6f7fb"
  ink-100: "#eef0f6"
  ink-200: "#e1e5ee"
  ink-300: "#c9cfde"
  ink-400: "#6b7594"
  ink-500: "#5a6585"
  ink-600: "#495476"
  ink-700: "#333e5f"
  ink-800: "#1f2947"
  ink-900: "#0d1533"
  brand-50: "#eef3ff"
  brand-200: "#c3d4ff"
  brand-300: "#9db8ff"
  brand-500: "#4a7bfb"
  brand-600: "#2a62f5"
  warning: "#b45309"
  warning-mark: "#d97706"
  warning-tint: "#fffbeb"
  danger: "#dc2626"
  danger-deep: "#b91c1c"
  danger-tint: "#fef2f2"
  success: "#059669"
  canvas-dark: "#0a1029"
  surface-dark: "#121b3d"
  link-dark: "#9db8ff"
  ink-50-dark: "#141d42"
  ink-100-dark: "#1a2450"
  ink-200-dark: "#232e5e"
  ink-300-dark: "#303c70"
  ink-400-dark: "#97a2c8"
  ink-500-dark: "#aab3d3"
  ink-600-dark: "#bdc5df"
  ink-700-dark: "#d2d8ea"
  ink-800-dark: "#e6e9f4"
  ink-900-dark: "#ffffff"
  brand-50-dark: "#16225a"
  brand-200-dark: "#27398a"
  brand-300-dark: "#3a4fa8"
  brand-500-dark: "#7fa0ff"
  warning-dark: "#fcd34d"
  danger-dark: "#fca5a5"
  success-dark: "#6ee7b7"
  wa-header: "#075e54"
  wa-teal: "#128c7e"
  wa-green: "#25d366"
  wa-bubble: "#dcf8c6"
  wa-wall: "#efe7dd"
  wa-link: "#027eb5"
  wa-card: "#ffffff"
  wa-bar: "#f0f2f5"
  wa-wall-dark: "#0b141a"
  wa-bubble-dark: "#005c4b"
  wa-card-dark: "#1f2c34"
  wa-link-dark: "#53bdeb"
typography:
  countdown:
    fontFamily: "Secular One, Assistant, sans-serif"
    fontSize: "2.75rem"
    fontWeight: 400
    lineHeight: 0.95
  headline:
    fontFamily: "Secular One, Assistant, sans-serif"
    fontSize: "1.625rem"
    fontWeight: 400
    lineHeight: 1.25
  title-popup:
    fontFamily: "Secular One, Assistant, sans-serif"
    fontSize: "1.3125rem"
    fontWeight: 400
    lineHeight: 1.25
  title-section:
    fontFamily: "Secular One, Assistant, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 400
    lineHeight: 1.25
  body:
    fontFamily: "Assistant, Noto Sans Hebrew, system-ui, Segoe UI, Arial, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: "1.35rem"
    fontFeature: "tnum"
  body-strong:
    fontFamily: "Assistant, Noto Sans Hebrew, system-ui, Segoe UI, Arial, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 600
    lineHeight: "1.35rem"
    fontFeature: "tnum"
  label:
    fontFamily: "Assistant, Noto Sans Hebrew, system-ui, Segoe UI, Arial, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 700
    lineHeight: "1.15rem"
    fontFeature: "tnum"
  caption:
    fontFamily: "Assistant, Noto Sans Hebrew, system-ui, Segoe UI, Arial, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: "1.15rem"
    fontFeature: "tnum"
rounded:
  none: "0px"
  full: "9999px"
  wa-inner: "6px"
  wa-bubble: "8px"
  wa-phone: "2.2rem"
spacing:
  "1": "4px"
  "1.5": "6px"
  "2": "8px"
  "2.5": "10px"
  "3": "12px"
  "4": "16px"
  "5": "20px"
  "6": "24px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-ink}"
    typography: "{typography.body-strong}"
    rounded: "{rounded.none}"
    padding: "0 16px"
    height: "40px"
  button-primary-hover:
    backgroundColor: "{colors.accent-deep}"
  button-primary-disabled:
    backgroundColor: "{colors.ink-200}"
    textColor: "{colors.ink-500}"
  button-on-accent:
    backgroundColor: "{colors.accent-ink}"
    textColor: "{colors.white}"
    rounded: "{rounded.none}"
    padding: "0 16px"
    height: "40px"
  button-on-accent-hover:
    backgroundColor: "{colors.accent-ink-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink-900}"
    typography: "{typography.body-strong}"
    rounded: "{rounded.none}"
    padding: "0 16px"
    height: "40px"
  button-secondary-hover:
    backgroundColor: "{colors.ink-100}"
  button-ghost:
    textColor: "{colors.ink-700}"
    rounded: "{rounded.none}"
    padding: "0 16px"
    height: "40px"
  button-ghost-hover:
    backgroundColor: "{colors.ink-100}"
    textColor: "{colors.ink-900}"
  button-danger:
    backgroundColor: "{colors.danger}"
    textColor: "{colors.white}"
    rounded: "{rounded.none}"
    padding: "0 16px"
    height: "40px"
  button-danger-hover:
    backgroundColor: "{colors.danger-deep}"
  button-field-ghost:
    textColor: "{colors.white}"
    rounded: "{rounded.none}"
    padding: "0 10px"
    height: "32px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink-900}"
    typography: "{typography.body}"
    rounded: "{rounded.none}"
    padding: "8px 12px"
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.none}"
    padding: "12px"
  tab-active:
    backgroundColor: "{colors.brand-600}"
    textColor: "{colors.white}"
    typography: "{typography.body-strong}"
    rounded: "{rounded.none}"
    padding: "6px 12px"
  nav-item:
    textColor: "{colors.field-muted}"
    typography: "{typography.body-strong}"
    rounded: "{rounded.none}"
    padding: "10px 12px"
  nav-item-active:
    backgroundColor: "{colors.brand-600}"
    textColor: "{colors.white}"
  month-band:
    backgroundColor: "{colors.field}"
    textColor: "{colors.white}"
    rounded: "{rounded.none}"
    padding: "12px 24px"
  deadline-disc-band:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-ink}"
    rounded: "{rounded.full}"
    size: "44px"
  deadline-disc-logo:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-ink}"
    rounded: "{rounded.full}"
    size: "36px"
  step-disc:
    backgroundColor: "{colors.brand-600}"
    textColor: "{colors.white}"
    typography: "{typography.caption}"
    rounded: "{rounded.full}"
    size: "24px"
  status-mark:
    size: "12px"
  table-row:
    textColor: "{colors.ink-800}"
    typography: "{typography.body}"
    padding: "10px 12px"
  table-head:
    backgroundColor: "{colors.ink-50}"
    textColor: "{colors.ink-700}"
    typography: "{typography.label}"
    padding: "10px 12px"
  review-banner:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-ink}"
    rounded: "{rounded.none}"
    padding: "12px 16px"
  modal:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.none}"
    width: "576px"
  modal-wide:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.none}"
    width: "1152px"
  toast:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.none}"
    padding: "14px"
---

# Design System: AccountFlow AI

## Overview

**Creative North Star: "The Deadline Poster"**

The office lives by the 26th, so the 26th is the one shape in the product. A midnight rail and band form one L-shaped field around a pale grey-blue page, and a single cantaloupe disc hangs over the edge of that field to show where the month is heading. Flat colour and confident Hebrew from the Israeli poster and stamp tradition set the tone; badges are gone, and state reads as a small flat mark.

The world is built for a clerk who keeps it open all day. Work sits in white panels with thin borders on the tinted page, because the user asked for clear separation between sections. Panels stay square and flat, with no shadows or gradients. Rank comes from size and weight. Cantaloupe is rationed so the clerk's next action is the loudest thing on any screen, and electric blue shows where the clerk is and what is selected. One form repeats at every scale, from the logo to the month band to the login poster.

Three decisions were made by the builder during review and still await the user. They are described below as built and marked **Pending user decision**: Secular One on section titles, popup titles and the countdown as well as page titles; page actions directly under the page title instead of in the title row; and outlined bars for scheduled reminders beside the white bars in the month strip.

**Key Characteristics:**
- An L-shaped midnight field, a pale page, white bordered panels, one cantaloupe disc.
- Square corners and flat colour everywhere except the WhatsApp simulator.
- Electric blue for selection and place, cantaloupe for the 26th and the next action.
- Secular One for titles and headline figures, Assistant for everything else, tabular figures throughout.
- Hebrew right to left first, with numbers, phones and IDs kept left to right inside it.
- Light and dark themes share one set of tokens, swapped at the root.

## Colors

Midnight navy, electric blue and cantaloupe orange on a pale grey-blue page, with amber and red held back for true warnings and a quarantined WhatsApp palette for the simulator.

### Primary
- **Midnight** (#0d1533): the rail and band in both themes, and the strongest ink in light mode. Popups and the mobile drawer use it at 70% opacity as their backdrop.
- **Field Mist** (#b9c2df): quiet text on the field, such as inactive navigation, role labels and the strip's day numbers. It does not change between themes.

### Secondary
- **Electric Blue** (#2a62f5): the active navigation item, active tabs, the selected client, template and date, the chosen request button and the on state of toggles. It also fills step discs, staff avatars and the "paid" share of a campaign bar. It is the same in both themes.
- **Link Blue** (#1f55e0, dark #9db8ff): text links, info icons and the blue state marks.
- **Focus Blue** (#4a7bfb, dark #7fa0ff): the focus ring and drag highlight.
- **Sky Tints** (#eef3ff, #c3d4ff, #9db8ff; dark #16225a, #27398a, #3a4fa8): selected rows in lists, today's ring in the date picker and the "viewed" share of a campaign bar.

### Tertiary
- **Cantaloupe** (#ffb27a): the 26 disc, the today marker, the primary action, the review banner and the review state mark. It stays the same in both themes. Hover moves to Ripe Cantaloupe (#ffa05c).
- **Ink on Cantaloupe** (#0d1533): text on cantaloupe in both themes, and the fill of the one button that sits on a cantaloupe banner, with hover at #1a2450.

### Neutral
- **Pale Page** (#f4f6fb, dark #0a1029): the page behind everything, carrying the explanation under the band.
- **Panel White** (#ffffff, dark #121b3d): panels, popups, toasts and inputs.
- **Body Ink** (#1f2947, dark #e6e9f4): default text. Titles, keys and values step up to Midnight in light mode and white in dark mode.
- **Slate Inks** (#333e5f, #495476, #5a6585, #6b7594): secondary text, hints and placeholders in steps of decreasing rank.
- **Line and Tint Greys** (#c9cfde, #e1e5ee, #eef0f6, #f6f7fb): panel borders, row hairlines, hover fills and table heads.

### Semantic
- **Warning Amber** (#b45309 for text, #d97706 for the triangle mark, #fffbeb for tints; dark #fcd34d): correction needed, high priority and risky conditions.
- **Alert Red** (#dc2626, hover #b91c1c, tint #fef2f2; dark #fca5a5): escalation, errors, invalid fields and destructive actions.
- **Confirmed Green** (#059669; dark #6ee7b7): the success toast icon and the active worker label.
- **WhatsApp Palette** (the `wa-*` tokens): WhatsApp's own colours for the simulator and message bubbles, with WhatsApp's own dark values.

### Named Rules
**The Two Meanings Rule.** Cantaloupe means the 26th or the clerk's next action. That covers the disc, the strip's today marker, the primary button, the review banner, the review state mark and the "requested a call" share of a campaign. The text caret and text selection are the only ambient uses.

**The One Cantaloupe Button Rule.** A view has at most one cantaloupe button. A disabled primary turns grey, so cantaloupe never sits on something that cannot be pressed.

**The Current Place Rule.** A solid electric blue fill with white text means selected or current. Step discs, avatars and the paid share of a campaign bar are the only other fills.

**The True Warning Rule.** Amber and red appear only for real warnings, failures and destructive actions, never for emphasis.

**The WhatsApp Quarantine Rule.** The `wa-*` colours, soft corners and bubble shadow exist only where the client's WhatsApp is being shown. They never leak into the dashboard, and the dashboard's rules never reshape WhatsApp.

## Typography

**Display Font:** Secular One (with Assistant, sans-serif)
**Body Font:** Assistant (with Noto Sans Hebrew, system-ui, Segoe UI, Arial, sans-serif)

**Character:** Secular One is a heavy single-weight Hebrew poster voice; Assistant is an even, practical working face. The scale sits one step above Tailwind's defaults because Assistant reads small. Both are self-hosted.

### Hierarchy
- **Countdown** (400, 2.75rem, 0.95): the days-left figure, always the largest type in the band.
- **Headline** (400, 1.625rem, 1.25): page titles and the login title; also tally figures on the review banner and campaign summary at line height 1.
- **Popup Title** (400, 1.3125rem, 1.25): popup headers.
- **Section Title** (400, 1.125rem, 1.25): panel and section titles.
- **Body** (400, 0.9375rem, 1.35rem): table rows, the explanation under the band and most running text. 600 weight for buttons, tabs and navigation, 700 for names and keys in a row.
- **Label** (700, 0.8125rem, 1.15rem): form field labels and table headers.
- **Caption** (400, 0.8125rem, 1.15rem): hints, sub-lines and metadata.

### Named Rules
**The Poster Voice Rule.** Secular One carries only page, section and popup titles, the countdown, headline tally figures, the disc numeral and the wordmark. Everything else is Assistant. It has one weight, so it is never bolded. Pending user decision: the original direction limited it to page titles; the build extends it to section titles, popup titles and the countdown.

**The Size and Weight Rule.** Rank comes from size and weight, with the strongest ink for the highest rank. No letter-spacing, no decorative labels above titles, no coloured headings.

**The Exact Figures Rule.** Tabular figures are on globally, and numbers, phones and IDs sit in left-to-right runs inside Hebrew text. A tax or money figure is never rounded, hidden or decorated.

## Layout

The app shell is a fixed window: a midnight rail on the inline start (right in Hebrew), the content column beside it, and the phone simulator on the far side. The rail is 224px from 1024px up and 256px from 1536px, and becomes a 256px drawer below 1024px with a small field-coloured top bar. The simulator is 340px from 1280px, 400px from 1536px, and a fixed overlay below 1280px.

Pages lay out by the width of the content column through container queries, not by the window, because the rail and simulator take a different share at every size. Content is centred at a 1280px maximum with 16px padding, rising to 24px from a 768px column, and 20px between panels. Panels hold 12px padding on Send Request, 16px on working pages and 20px on Settings; panels holding a table run it edge to edge. Table rows use 10px vertical and 12px horizontal padding.

The band is sticky at the top of each page. In a column of 768px or more it splits in two: the page title with actions under it on one side, the countdown and month strip on the other. Below that it keeps the title and countdown and drops the strip. Pending user decision: page actions sit directly under the title, not in the title row. The page's explanation sits on the pale page under the band in full, never truncated.

From a 672px column up, Send Request fills the window with no page scroll, and only its inner lists scroll. The band stays low enough for this to hold on a 720px window, which is why the disc hangs over the band's edge instead of making it taller.

### Named Rules
**The L-Field Rule.** The rail and band are one continuous midnight field, marked only by a 10% white hairline, and every authenticated page carries the band.

**The Fixed Window Rule.** The band and Send Request keep their height budget. New band content must not push Send Request into a page scroll on laptop sizes.

## Elevation & Depth

The system is flat. Tailwind's shadow scale is set to none, so depth comes from tone, borders and overlap alone: white panels on the pale page, the Midnight backdrop behind popups, a thin border around floating panels, and the disc hanging over the band's edge. The only surviving shadow belongs to WhatsApp.

### Shadow Vocabulary
- **WhatsApp bubble** (`box-shadow: 0 1px 0.5px rgba(0,0,0,0.13)`): message bubbles and quick-reply buttons in the simulator and ticket timeline. Nothing else.

### Named Rules
**The Flat Poster Rule.** No shadows or gradients on dashboard surfaces. A surface separates by colour, by a thin border or by overlap. The WhatsApp wallpaper's dot texture and bubble shadow stay as part of the WhatsApp Quarantine Rule.

## Shapes

Every rectangle is square. Tailwind's radius scale is set to 0 from `sm` through `3xl`, so even source classes that name a radius render with sharp corners, and only `rounded-full` and explicit pixel radii produce a curve.

Circles are the system's second form. They carry the 26 disc at every size, from the 28px mobile logo through the 36px rail logo and 44px band disc to the 78vh login poster. Smaller blue or white discs hold numbers and initials: 24px step numbers in section titles, and avatars. The toggle is the one pill. State marks use a 12px flat vocabulary of circle, half circle, triangle, square and tick.

Panel, popup and toast borders are 1px Line Grey. Row hairlines are one step lighter, and field dividers are 1px white at 10%. The phone frame and its contents keep WhatsApp's own radii (6px, 8px, 2.2rem).

### Named Rules
**The Square and Disc Rule.** Rectangles are square; a curve is a full circle, and the toggle is the only exception. New round forms hold a number, a person's initials or a state, and a numbered cantaloupe disc always reads 26.

## Components

### Buttons
Flat, square and direct.
- **Shape:** square corners at 32px small, 40px default and 48px large.
- **Primary:** Cantaloupe with midnight text, semibold. The clerk's next action on the screen.
- **Hover / Focus:** a colour-only 150ms transition; hover moves to Ripe Cantaloupe. Keyboard focus shows a 2px Focus Blue ring with 1px offset.
- **Secondary:** Panel White with a 1px inset Line Grey outline; hover fills the palest grey. This is the default variant.
- **Ghost:** Slate Ink text with no outline; hover fills the palest grey.
- **Danger:** Alert Red with white text, for destructive confirmations.
- **On Accent:** midnight with white text, only inside a cantaloupe banner.
- **Field Ghost:** white text with a 40% white outline, only on the band. Page actions in the band use this unless they are the page's primary action.
- **Disabled and loading:** the primary greys out; others fade. Loading swaps the icon for a spinner.

### Request Selector
Send Request's template choices are a wrapping row of 32px square buttons with a 1px Line Grey outline, reversing to solid Electric Blue when chosen. Their icons drop out in the narrow column range to save width.

### Tabs
Page tabs and filters are reversed text: Electric Blue with white text when active, plain ink with a pale hover otherwise. Counts stay inside the label at lower opacity. An alerting filter shows its label in red.

### Panels
- **Corner Style:** square.
- **Background:** Panel White on the Pale Page.
- **Shadow Strategy:** none; see Elevation & Depth.
- **Border:** 1px Line Grey on all sides.
- **Internal Padding:** set per use at 12px, 16px or 20px; zero when a table fills the panel, with a thin rule under any toolbar.
- **Contents:** a Section Title with an optional caption, 24px step disc and control aligned to the far side.

### Inputs / Fields
- **Style:** Panel White with a 1px inset Line Grey outline, square, 8px by 12px padding.
- **Focus:** the outline becomes a 2px inset Focus Blue ring; hover moves to a mid slate outline.
- **Error / Disabled:** a 2px red ring for invalid values, the palest grey and mid ink for disabled.
- **Labels:** a Label above the field, with an optional Caption below it.
- **Direction:** passwords, numbers and IDs are left to right, using physical sides for their inner controls.

### Navigation
- **Style:** semibold icon-and-label rows on the field, in Field Mist.
- **Hover:** a 10% white fill with white text.
- **Active:** filled Electric Blue with white text. The board item shows its open count as plain bold text.
- **Mobile:** a slide-in drawer over the Midnight backdrop, opened from a slim field-coloured bar that carries a 28px disc.

### Month Band
The signature component. A band in the field colour carries the page title, the countdown figure with its two-line caption, and a month strip of one column per day. Solid white 6px bars show requests opened, today is marked in cantaloupe, and the 26th is a 44px cantaloupe disc hanging 20px over the band's lower edge. Pending user decision: outlined white bars show reminders still scheduled, stacked above the solid bars. Bars run from 4px to 28px, scaled to the month's busiest day, with day numbers at the 1st, every fifth day and today.

### Deadline Disc
The 26 in Secular One on a cantaloupe circle. It is the logo in the rail and the mobile bar, the login mark, the band's end point and the cropped poster shape on the login screen. The login screen is otherwise the field with one white panel.

### State Mark
A 12px flat shape in a fixed position before its label, so a column scans by form as well as colour: open ring for open, solid blue circle for waiting, half circle for snoozed, amber triangle for correction, cantaloupe disc with a midnight centre for clerk review, red square for escalated, and a tick for resolved. It is never a coloured pill.

### Data Table
Every table shares one row size. The header is a bold Label on the palest grey over a 1px Line Grey rule, rows sit on 1px hairlines, and rows hover to the palest grey. Names and references are bold, supporting columns step down in ink, and long values truncate to one line with the full text on hover. Escalated rows take a faint red tint and urgent rows a faint amber tint.

### Review Banner
A full-width cantaloupe band above the board, shown only when requests await the clerk: the count in Secular One, one sentence naming the next client, and an On Accent button.

### Popups and Toasts
Popups are square bordered panels, 576px or 1152px wide, over the Midnight backdrop, with a 1px rule under the title. They slide in over 180ms. Toasts are compact bordered panels with a tone icon, centred at the bottom of the window.

### Phone Simulator
A side panel holding a WhatsApp phone that must keep looking like real WhatsApp, including its own colours, radii, type sizes and dark theme.

## Do's and Don'ts

### Do:
- **Do** let cantaloupe mark the single next action on each view, with midnight text.
- **Do** put working sections in white panels with a 1px border on the Pale Page.
- **Do** show state with a State Mark and a text label, in a fixed position.
- **Do** keep every table row on one type size and, where the column allows it, one line.
- **Do** use the Deadline Disc whenever the 26th is named visually.
- **Do** lay pages out with container queries against the content column.
- **Do** check every new surface in light mode, dark mode and right-to-left, with figures left to right.
- **Do** keep the phone simulator faithful to WhatsApp, whatever the dashboard does.

### Don't:
- **Don't** use coloured status pills or badges for state.
- **Don't** add shadows, gradients or rounded rectangles to dashboard surfaces.
- **Don't** use cantaloupe for decoration or for a second button on a view.
- **Don't** use amber or red for emphasis without a real warning behind it.
- **Don't** use `wa-*` tokens or WhatsApp radii outside WhatsApp views.
- **Don't** put any number but 26 in a cantaloupe disc.
- **Don't** use Secular One for body text, form labels, table rows or buttons.
- **Don't** render manager-only controls as disabled or hidden elements for workers; leave them out.
