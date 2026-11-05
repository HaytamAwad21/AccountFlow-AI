#!/bin/sh
# Backup of a real office install: the database (pg_dump) and the uploaded documents, encrypted with
# BACKUP_PASSPHRASE (AES-256, openssl) into /backups (the backups/ folder next to docker-compose.prod.yml).
# When BACKUP_REMOTE is set (an rclone remote, see .env.production.example), each backup is also copied
# off the server. Copies older than BACKUP_KEEP_DAYS are removed, here and off the server.
#   backup.sh          one backup now
#   backup.sh --loop   one backup now and then every 24 hours (how the backup service runs it)
# Restoring: restore.sh, and DEPLOY.md "Restore a backup".
set -eu
set -o pipefail

encrypt() {
	openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass env:BACKUP_PASSPHRASE -out "$1"
}

backup_once() {
	if [ -z "${BACKUP_PASSPHRASE:-}" ]; then
		echo "$(date '+%Y-%m-%d %H:%M') NO BACKUP: BACKUP_PASSPHRASE is not set in .env" >&2
		return 1
	fi
	stamp=$(date +%Y-%m-%d_%H%M%S)
	db="db_$stamp.dump.enc"
	files="uploads_$stamp.tar.gz.enc"
	# Write to a temporary name first, so a half-written file is never mistaken for a backup.
	pg_dump --format=custom | encrypt "/backups/.$db.tmp"
	mv "/backups/.$db.tmp" "/backups/$db"
	tar -czf - -C /uploads . | encrypt "/backups/.$files.tmp"
	mv "/backups/.$files.tmp" "/backups/$files"
	keep="${BACKUP_KEEP_DAYS:-14}"
	find /backups -maxdepth 1 \( -name 'db_*.dump*' -o -name 'uploads_*.tar.gz*' \) -mtime +"$keep" -delete
	where="on this server"
	if [ -n "${BACKUP_REMOTE:-}" ]; then
		rclone copy /backups "$BACKUP_REMOTE" --include "$db" --include "$files"
		rclone delete "$BACKUP_REMOTE" --min-age "${keep}d" --include "db_*" --include "uploads_*"
		where="on this server and in $BACKUP_REMOTE"
	fi
	echo "$(date '+%Y-%m-%d %H:%M') backup done ($where): $db, $files"
}

if [ "${1:-}" = "--loop" ]; then
	while true; do
		backup_once || echo "$(date '+%Y-%m-%d %H:%M') BACKUP FAILED" >&2
		rm -f /backups/.*.tmp
		sleep 86400
	done
else
	backup_once
fi
