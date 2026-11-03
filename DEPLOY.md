# Deploying AccountFlow AI for an accounting firm

This guide puts one copy of the app on a cloud server for one firm, at an address such as `https://app.levi-cpa.co.il`. Every firm gets its own server (or at least its own copy and database): firms never share data.

What runs on the server, all in Docker:

| Part | What it does | Reachable from the internet |
| --- | --- | --- |
| Caddy | HTTPS certificate (free, renewed automatically) and the public entry point | Yes, ports 80 and 443 |
| frontend | The dashboard (nginx) | No |
| backend | The API, the reminder engine and the WhatsApp webhook | No |
| db | PostgreSQL 16 | No |
| backup | Nightly copy of the database and the uploaded documents into `backups/` | No |

Every command below runs on the server, inside the `AccountFlow-AI` folder.

## 1. What you need

- **A server** running Ubuntu 24.04, with 2 CPUs, 4 GB of memory and 40 GB of disk. Any cloud works. To keep client data in Israel, pick a Tel Aviv region (AWS `il-central-1`, Google Cloud `me-west1` or Azure Israel Central).
- **A domain name** you control, for example a subdomain of the firm's site.
- **An OpenAI API key** from platform.openai.com, with pay-as-you-go billing. This is not a ChatGPT subscription. Set a monthly spending limit in the billing settings.
- **For live WhatsApp** (can come later): a Meta Business account for the firm and a phone number that is not used in the regular WhatsApp app. See step 7.

## 2. Point the domain at the server

In the domain's DNS settings, add an **A record**: the name (for example `app`) points at the server's public IP address. Wait until `ping app.levi-cpa.co.il` answers from that IP; it usually takes a few minutes.

## 3. Prepare the server

Connect with SSH, then install Docker and turn on the firewall:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
sudo ufw allow OpenSSH
sudo ufw allow 80,443/tcp
sudo ufw allow 443/udp
sudo ufw --force enable
```

Log out and back in, so `docker` works without `sudo`.

## 4. Get the code and create the settings

```bash
git clone https://github.com/HaytamAwad21/AccountFlow-AI.git
cd AccountFlow-AI
bash deploy/setup.sh
```

If the repository is private, GitHub asks for a username and a personal access token instead of a password.

`deploy/setup.sh` asks for the site address and the OpenAI key. It then writes `.env` with a fresh database password, a WhatsApp verify token and a **setup code**, and prints the setup code. Keep it for step 6. `.env` holds secrets: never commit it, email it or paste it into chats.

## 5. Start the app

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

The first build takes a few minutes. Check that every part is up:

```bash
docker compose -f docker-compose.prod.yml ps
```

`db` and `backend` should say `healthy`. Caddy gets the HTTPS certificate on the first visit; if the site does not open, see "When something goes wrong".

## 6. Set up the office

1. Open `https://<your domain>`. A new install shows **הקמת המשרד במערכת** instead of the login screen.
2. Type the setup code, the firm's name and the first manager's name, e-mail and password. That manager is logged in at once.
3. In **הגדרות**:
   - Check the VAT rate, the VAT deadline day and the reminder rules.
   - Add the workers under **עובדי המשרד**.
4. In **לקוחות ותבניות**, add the clients. A tax-notice sheet uploaded in **הדיווח מוכן** also adds any client it does not know yet.

There is no demo data on this install: no demo users, clients or requests. The six message templates are installed.

## 7. Connect WhatsApp

Until this step, messages appear only in the in-app phone simulator and nothing reaches real clients.

1. In business.facebook.com, create or open the firm's business account and complete business verification.
2. In developers.facebook.com, create an app of type **Business** and add the **WhatsApp** product.
3. Under WhatsApp, **API Setup**, add the firm's phone number and verify it by SMS. Copy the **Phone number ID**.
4. In the business settings, create a **System user**. Give it the app, then generate a permanent token with the `whatsapp_business_messaging` and `whatsapp_business_management` permissions.
5. In the app's **App settings, Basic**, copy the **App secret**.
6. Put the values in `.env` with `nano .env`:
   - `WHATSAPP_TOKEN`: the permanent token.
   - `WHATSAPP_PHONE_NUMBER_ID`: the phone number ID.
   - `WHATSAPP_APP_SECRET`: the app secret.
7. Under WhatsApp, **Configuration**, set the webhook:
   - Callback URL: `https://<your domain>/api/webhook/whatsapp-inbound`
   - Verify token: the `WHATSAPP_VERIFY_TOKEN` value from `.env`
   - Subscribe to the **messages** field.
8. In WhatsApp Manager, create the re-engagement template described in README.md, "The 24-hour window". Once Meta approves it, put its name in `WHATSAPP_REENGAGE_TEMPLATE`.
9. Restart the API so it reads the new values:

```bash
docker compose -f docker-compose.prod.yml up -d --force-recreate backend
```

Test with one real phone before the firm starts: send a request to it and answer with a photo of an invoice.

**Once WhatsApp is connected, do not use the phone simulator.** The app answers a simulated message the same way it answers a real one, so its replies go to the real client's WhatsApp.

## 8. Backups

The `backup` service copies the database and the uploaded documents into the `backups/` folder when it starts and then every 24 hours. It keeps 14 days (`BACKUP_KEEP_DAYS` in `.env`).

A copy that stays on the same server is lost with the server, so copy `backups/` somewhere else regularly. For example, from your own computer:

```bash
scp -r user@server-ip:AccountFlow-AI/backups ./accountflow-backups
```

To make a backup right now (for example before an update):

```bash
docker compose -f docker-compose.prod.yml exec backup sh /backup.sh
```

### Restore a backup

Replace the file names with the ones you want from `backups/`:

```bash
docker compose -f docker-compose.prod.yml stop backend
docker compose -f docker-compose.prod.yml exec -T db pg_restore --clean --if-exists -U accountflow -d accountflow < backups/db_2026-11-03_0200.dump
docker compose -f docker-compose.prod.yml run --rm --no-deps -v "$PWD/backups:/backups" backend sh -c "tar -xzf /backups/uploads_2026-11-03_0200.tar.gz -C /app/uploads"
docker compose -f docker-compose.prod.yml start backend
```

## 9. Updating to a new version

```bash
docker compose -f docker-compose.prod.yml exec backup sh /backup.sh
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

The data stays in Docker volumes; rebuilding does not touch it. The app upgrades its database tables on start. If a database is too old to upgrade in place, the API stops with a message and changes nothing; it never deletes data on its own.

## When something goes wrong

See the API's messages:

```bash
docker compose -f docker-compose.prod.yml logs --tail 100 backend
```

| Problem | Check |
| --- | --- |
| The site does not open, or the browser warns about the certificate | `docker compose -f docker-compose.prod.yml logs caddy`. The domain's A record must point at this server, and ports 80 and 443 must be open in the cloud provider's firewall as well. |
| The setup screen says the code is wrong | Compare with `grep SETUP_CODE .env`. After editing `.env`, run `docker compose -f docker-compose.prod.yml up -d --force-recreate backend`. |
| Invoices are not read, every photo goes to a clerk | `OPENAI_API_KEY` in `.env`, and credit in the OpenAI billing page. The API log shows `openai failed` when a call fails. |
| Clients get nothing on WhatsApp | The log line of the send, the token and phone number ID in `.env`, and the 24-hour window (README.md). |

## Before the firm starts using it

- A written agreement with the firm on how you handle their clients' data (Israel's Privacy Protection Law and its data-security regulations apply). Have a lawyer review it.
- The firm knows, and agrees in writing, that invoice photos are sent to OpenAI (outside Israel) to be read.
- The WhatsApp Business account and phone number are in the firm's name, and Meta bills the firm.
- A monthly spending limit is set on the OpenAI account.
- About 20 real invoices from different suppliers, including blurry ones, were tested.
- Backups are copied off the server, and one restore was tried.
