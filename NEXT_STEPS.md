# Next steps

Plan for taking AccountFlow AI from demo to a real office. The app runs on the office computer; clients keep using WhatsApp through the Meta WhatsApp Cloud API.

## Done

- Webhook hardening (PR #1): Meta posts to `POST /api/webhook/whatsapp-inbound` must carry a valid `X-Hub-Signature-256` keyed with `WHATSAPP_APP_SECRET`; simulator posts need a logged-in user. `backend/test_flow.py` passes 243 checks.

- 24-hour window: when a client's window is closed, messages are held and one approved re-engagement template is sent; held messages go out when the client taps it or writes. See README ▸ The 24-hour window. `test_flow.py` passes 257 checks.

## Code gaps to fix before real use

1. **Reminders pile up while a message is held.** A client who stays silent for days gets every held reminder at once when they come back. Consider sending only the newest held message per ticket.
2. **Manual pictures need a public URL.** A worker's manual picture is sent by link (`PUBLIC_BASE_URL`), so Meta must download it from the office computer. Upload the file to the Cloud API media endpoint first and send it by media ID instead, so only the webhook needs to be reachable.

## Deployment plan

1. **Phone number.** Get a dedicated number for the business (mobile, landline or virtual). It only needs to receive one verification code by SMS or voice call. Do not use a number that is active on the regular WhatsApp or WhatsApp Business app.
2. **Meta setup.** Create a Meta Business account and a Meta developer app with the WhatsApp product. Register the number, complete business verification, and create a system user with a permanent access token.
3. **Create the re-engagement template** in WhatsApp Manager (README ▸ The 24-hour window has the suggested text) and wait for approval. Fix the code gaps above.
4. **Expose only the webhook.** Run a tunnel (for example Cloudflare Tunnel) that forwards only `/api/webhook/whatsapp-inbound` to the office computer over https. The dashboard, login and data stay private. Point the Meta app's webhook at that address.
5. **Configure `.env`:**
   - `WHATSAPP_TOKEN`: the system user's permanent token.
   - `WHATSAPP_PHONE_NUMBER_ID`
   - `WHATSAPP_APP_SECRET`: Meta app ▸ App settings ▸ Basic ▸ App Secret. Without it every Meta webhook post is refused.
   - `WHATSAPP_VERIFY_TOKEN`: replace the default `accountflow-verify` with a random value.
   - `WHATSAPP_REENGAGE_TEMPLATE`: the approved template's name, e.g. `accountflow_pending_update`.
6. **Change the demo passwords** (`maya1234`, `rami1234`, `dana1234`) or replace the seeded users.
7. **Test with your own phone** before real clients: request, reply, photo, reminder after 24 hours.

## Notes

- Meta charges per business-initiated message (price depends on country and template category); replies inside the 24-hour window are free. Check Meta's current pricing for Israel.
- The office computer must stay on: reminders do not run while it is off. Meta retries failed webhook deliveries for a limited time, so replies sent while it is off usually arrive later.
