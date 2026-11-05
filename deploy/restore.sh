#!/bin/sh
# Restores one backup made by backup.sh: the database, and the documents into /restore-uploads.
#   restore.sh 2026-11-04_020000    (the date and time in the backup's file names)
# A backup that is not in /backups is fetched from BACKUP_REMOTE first (a new server after losing the old one).
# Needs the same BACKUP_PASSPHRASE the backup was made with. Stop the API first: DEPLOY.md, "Restore a backup".
set -eu
set -o pipefail

stamp="${1:?give the backup to restore, for example 2026-11-04_020000}"
db="db_$stamp.dump.enc"
files="uploads_$stamp.tar.gz.enc"
: "${BACKUP_PASSPHRASE:?BACKUP_PASSPHRASE is not set in .env: without it the backup cannot be opened}"

if [ ! -f "/backups/$db" ] && [ -n "${BACKUP_REMOTE:-}" ]; then
	echo "Fetching $db and $files from $BACKUP_REMOTE"
	rclone copy "$BACKUP_REMOTE" /backups --include "$db" --include "$files"
fi
[ -f "/backups/$db" ] || { echo "Backup /backups/$db not found" >&2; exit 1; }

decrypt() {
	openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_PASSPHRASE -in "$1"
}

# Check the passphrase before touching anything: a wrong one fails here, with the database untouched.
decrypt "/backups/$db" > /tmp/restore.dump || { echo "Cannot decrypt: wrong BACKUP_PASSPHRASE?" >&2; rm -f /tmp/restore.dump; exit 1; }
pg_restore --clean --if-exists --no-owner -d "$PGDATABASE" /tmp/restore.dump
rm -f /tmp/restore.dump
echo "Database restored from $db"
if [ -f "/backups/$files" ]; then
	decrypt "/backups/$files" | tar -xzf - -C /restore-uploads
	echo "Documents restored from $files"
fi
