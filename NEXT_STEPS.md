# Next steps

Plan for taking AccountFlow AI from demo to a real office. The app runs on the office computer; clients keep using WhatsApp through the Meta WhatsApp Cloud API.

## Done

- Webhook hardening (PR #1): Meta posts to `POST /api/webhook/whatsapp-inbound` must carry a valid `X-Hub-Signature-256` keyed with `WHATSAPP_APP_SECRET`; simulator posts need a logged-in user. `backend/test_flow.py` passes 243 checks.

## Code gaps to fix before real use

1. **Template messages outside the 24-hour window.** Meta only accepts free-form text and reply-button messages within 24 hours of the client's last message. After that, a business may send only Meta-approved template messages. `backend/services/whatsapp.py` sends only `text` and `interactive` messages, so first requests and reminders to clients who have not written recently will be rejected by Meta.
   - Define the Hebrew messages (requests, reminders, deadline escalation) as WhatsApp templates and submit them for approval.
   - Track each client's last inbound message time; send a template when the 24-hour window is closed, and the current interactive message when it is open.
   - Add `test_flow.py` checks for both paths.
2. **Manual pictures need a public URL.** A worker's manual picture is sent by link (`PUBLIC_BASE_URL`), so Meta must download it from the office computer. Upload the file to the Cloud API media endpoint first and send it by media ID instead, so only the webhook needs to be reachable.

## Deployment plan

1. **Phone number.** Get a dedicated number for the business (mobile, landline or virtual). It only needs to receive one verification code by SMS or voice call. Do not use a number that is active on the regular WhatsApp or WhatsApp Business app.
2. **Meta setup.** Create a Meta Business account and a Meta developer app with the WhatsApp product. Register the number, complete business verification, and create a system user with a permanent access token.
3. **Fix the two code gaps above**, then submit the templates for approval.
4. **Expose only the webhook.** Run a tunnel (for example Cloudflare Tunnel) that forwards only `/api/webhook/whatsapp-inbound` to the office computer over https. The dashboard, login and data stay private. Point the Meta app's webhook at that address.
5. **Configure `.env`:**
   - `WHATSAPP_TOKEN`: the system user's permanent token.
   - `WHATSAPP_PHONE_NUMBER_ID`
   - `WHATSAPP_APP_SECRET`: Meta app ▸ App settings ▸ Basic ▸ App Secret. Without it every Meta webhook post is refused.
   - `WHATSAPP_VERIFY_TOKEN`: replace the default `accountflow-verify` with a random value.
6. **Change the demo passwords** (`maya1234`, `rami1234`, `dana1234`) or replace the seeded users.
7. **Test with your own phone** before real clients: request, reply, photo, reminder after 24 hours.

## Notes

- Meta charges per business-initiated message (price depends on country and template category); replies inside the 24-hour window are free. Check Meta's current pricing for Israel.
- The office computer must stay on: reminders do not run while it is off. Meta retries failed webhook deliveries for a limited time, so replies sent while it is off usually arrive later.
