#!/usr/bin/env bash
# Writes .env for a real office server: asks for the domain and the OpenAI key, and generates the
# database password, the setup code and the WhatsApp verify token. Run it once, from the project folder:
#   bash deploy/setup.sh
set -euo pipefail

cd "$(dirname "$0")/.."
if [ -e .env ]; then
	echo ".env already exists. Nothing was changed."
	echo "To start over, move it away first:  mv .env .env.old"
	exit 1
fi
if [ ! -f .env.production.example ]; then
	echo "Run this from the AccountFlow-AI folder (.env.production.example is missing)."
	exit 1
fi

random_hex() { head -c "$1" /dev/urandom | od -An -tx1 | tr -d ' \n'; }

read -r -p "The site's address, without https:// (for example app.levi-cpa.co.il): " domain
domain="${domain#https://}"
domain="${domain#http://}"
domain="${domain%%/*}"
if [ -z "$domain" ]; then
	echo "An address is required."
	exit 1
fi
read -r -p "OpenAI API key (starts with sk-; Enter to add it later): " openai_key

db_password="$(random_hex 24)"
setup_code="$(random_hex 4)-$(random_hex 4)-$(random_hex 4)"
verify_token="$(random_hex 16)"
backup_passphrase="$(random_hex 4)-$(random_hex 4)-$(random_hex 4)-$(random_hex 4)-$(random_hex 4)-$(random_hex 4)"

sed \
	-e "s|^DOMAIN=.*|DOMAIN=$domain|" \
	-e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$db_password|" \
	-e "s|^SETUP_CODE=.*|SETUP_CODE=$setup_code|" \
	-e "s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=$openai_key|" \
	-e "s|^WHATSAPP_VERIFY_TOKEN=.*|WHATSAPP_VERIFY_TOKEN=$verify_token|" \
	-e "s|^BACKUP_PASSPHRASE=.*|BACKUP_PASSPHRASE=$backup_passphrase|" \
	.env.production.example > .env
chmod 600 .env
mkdir -p backups

cat <<EOF

.env is ready (only you can read it).

  Setup code for the first manager:  $setup_code

  Backup passphrase:                 $backup_passphrase
  Save it NOW outside this server (a password manager, or printed and locked away).
  Every backup is encrypted with it: if the server is lost and this is lost too, no backup can be opened.

Next:
  1. Start the app:   docker compose -f docker-compose.prod.yml up -d --build
  2. Open https://$domain and fill in the setup screen with the code above.
  3. Continue with DEPLOY.md from "Set up the office".
EOF
