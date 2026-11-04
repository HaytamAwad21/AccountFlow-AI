# Deploying AccountFlow AI for an accounting firm

This guide puts one copy of the app on a cloud server for one firm, at an address such as `https://app.levi-cpa.co.il`. Every firm gets its own server (or at least its own copy and database): firms never share data.

What runs on the server, all in Docker:

| Part | What it does | Reachable from the internet |
| --- | --- | --- |
| Caddy | HTTPS certificate (free, renewed automatically) and the public entry point | Yes, ports 80 and 443 |
| frontend | The dashboard (nginx) | No |
| backend | The API, the reminder engine and the WhatsApp webhook | No |
| db | PostgreSQL 16 | No |
| backup | Nightly encrypted copy of the database and the uploaded documents, in `backups/` and off the server | No |

Every command below runs on the server, inside the `AccountFlow-AI` folder.

## 1. What you need

- **A server** running Ubuntu 24.04, with 2 CPUs, 4 GB of memory and 40 GB of disk. Any cloud works. To keep client data in Israel, pick a Tel Aviv region (AWS `il-central-1`, Google Cloud `me-west1` or Azure Israel Central).
- **A domain name** you control, for example a subdomain of the firm's site.
- **An OpenAI API key** from platform.openai.com, with pay-as-you-go billing. This is not a ChatGPT subscription. Set a monthly spending limit in the billing settings.
- **For live WhatsApp** (can come later): a Meta Business account for the firm and a phone number that is not used in the regular WhatsApp app. See step 7.
- **Storage for off-site backups**: a bucket in any S3-compatible storage (AWS S3 in Tel Aviv, Cloudflare R2, Backblaze B2). See step 8.
- **An SSH key** on your own computer, to log in to the server without a password. See step 3.

## 2. Point the domain at the server

In the domain's DNS settings, add an **A record**: the name (for example `app`) points at the server's public IP address. Wait until `ping app.levi-cpa.co.il` answers from that IP; it usually takes a few minutes.

## 3. Prepare and lock down the server

**Your login key.** On your own computer, create a key if you have none, and copy it to the server. Use the user name your cloud provider gave you (often `ubuntu` or `root`):

```bash
ssh-keygen -t ed25519
```

```bash
ssh-copy-id ubuntu@<server address>
```

Log in with `ssh ubuntu@<server address>`; it no longer asks for the server's password. Then install Docker:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

Log out and back in, so `docker` works without `sudo`. Get the code (step 4), then lock the server down:

```bash
sudo bash deploy/harden.sh
```

`deploy/harden.sh` does four things:

- **SSH with keys only:** password logins and root password logins are switched off, so nobody can guess their way in.
- **fail2ban:** an address that fails to log in 5 times is blocked for an hour.
- **Automatic security updates:** Ubuntu installs them every day and restarts at 04:00 when an update needs it. The app's containers start again by themselves.
- **Firewall:** only SSH (22), HTTP (80) and HTTPS (443) are open.

It refuses to change anything until your login key is installed, so it cannot lock you out. When it finishes, check from a **new** terminal that `ssh ubuntu@<server address>` still works before closing the old one.

## 4. Get the code and create the settings

```bash
git clone https://github.com/HaytamAwad21/AccountFlow-AI.git
cd AccountFlow-AI
bash deploy/setup.sh
```

If the repository is private, GitHub asks for a username and a personal access token instead of a password.

`deploy/setup.sh` asks for the site address and the OpenAI key. It then writes `.env` with a fresh database password, a WhatsApp verify token, a **setup code** and a **backup passphrase**, and prints the last two:

- **Setup code:** keep it for step 6.
- **Backup passphrase:** save it **now, outside the server**, in a password manager or printed and locked away. Every backup is encrypted with it. If the server is lost and the passphrase is lost too, no backup can be opened, not even by you.

`.env` holds secrets: never commit it, email it or paste it into chats.

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
5. **Two-step login for everyone.** Each person clicks **אימות דו-שלבי** under their name in the sidebar and scans the QR code with Google Authenticator or Microsoft Authenticator. From then on a login needs the password and the 6-digit code from the phone, so a stolen password alone is useless. Start with the managers.
   - **Someone lost their phone:** a manager opens **עריכה** for that person and presses **איפוס (הטלפון אבד)**. They log in with the password and set it up on the new phone.
   - **The staff list** shows who has turned it on.

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

The `backup` service backs up the database and the uploaded documents when it starts and then every 24 hours:

- **Encrypted:** each backup is encrypted with `BACKUP_PASSPHRASE` (AES-256). The files in `backups/` end in `.enc` and cannot be read without the passphrase.
- **Off the server:** when `BACKUP_REMOTE` is set, each backup is also copied to your storage bucket. A copy that stays on the server is lost with the server.
- **Kept 14 days** (`BACKUP_KEEP_DAYS`), on the server and in the bucket.

**Set up the off-site copy** (do this before the firm starts):

1. Create a bucket, for example in AWS S3, region `il-central-1` (Tel Aviv).
2. Create an access key that can only write to that bucket.
3. In `.env`, remove the `#` signs in the `BACKUP_REMOTE` and `RCLONE_CONFIG_OFFSITE_*` lines and fill in the bucket name and the key. `.env.production.example` shows examples for AWS, Cloudflare R2 and Backblaze B2.
4. Restart the backup service and check its log. It should end with `backup done (on this server and in offsite:...)`.

```bash
docker compose -f docker-compose.prod.yml up -d --force-recreate backup
```

```bash
docker compose -f docker-compose.prod.yml logs --tail 5 backup
```

To make a backup right now (for example before an update):

```bash
docker compose -f docker-compose.prod.yml exec backup sh /usr/local/bin/backup.sh
```

### Restore a backup

The backup's name is the date and time in its file names, for example `2026-11-04_0200` for `db_2026-11-04_0200.dump.enc`. Stop the API, restore, start it again:

```bash
docker compose -f docker-compose.prod.yml stop backend
```

```bash
docker compose -f docker-compose.prod.yml run --rm --no-deps -v accountflow_uploads:/restore-uploads --entrypoint sh backup /usr/local/bin/restore.sh 2026-11-04_0200
```

```bash
docker compose -f docker-compose.prod.yml start backend
```

A wrong passphrase stops the restore before anything is changed.

**The server is gone:** set up a new server with steps 2 to 4. Then, before starting the app, put the **saved** backup passphrase and the same `BACKUP_REMOTE` settings into the new `.env`. Start the app, and restore as above: a backup that is not on the server is fetched from the bucket first.

## 9. Updating to a new version

```bash
docker compose -f docker-compose.prod.yml exec backup sh /usr/local/bin/backup.sh
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

Updating from a version whose backups were not encrypted: run `bash deploy/setup.sh` on a copy, or add a `BACKUP_PASSPHRASE` line to `.env` yourself (letters, digits and dashes, at least 24 characters), and save it outside the server. Then delete the old unencrypted `backups/db_*.dump` and `backups/uploads_*.tar.gz` files.

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
| The backup log says `NO BACKUP` | `BACKUP_PASSPHRASE` is missing from `.env`. |
| The backup log shows an rclone error | The bucket name, region and access key in `.env`, and that the key may write to the bucket. |

## Before the firm starts using it

- A written agreement with the firm on how you handle their clients' data (Israel's Privacy Protection Law and its data-security regulations apply). Have a lawyer review it.
- The firm knows, and agrees in writing, that invoice photos are sent to OpenAI (outside Israel) to be read.
- The WhatsApp Business account and phone number are in the firm's name, and Meta bills the firm.
- A monthly spending limit is set on the OpenAI account.
- About 20 real invoices from different suppliers, including blurry ones, were tested.
- `deploy/harden.sh` ran, and logging in with the key still works.
- The backup passphrase is saved outside the server. Backups reach the bucket, and one restore was tried.
- Every manager has turned on two-step login.
