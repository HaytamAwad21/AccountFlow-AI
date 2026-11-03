#!/bin/sh
# Backup of a real office install: the database (pg_dump) and the uploaded documents, into /backups
# (the backups/ folder next to docker-compose.prod.yml). Copies older than BACKUP_KEEP_DAYS are removed.
#   sh /backup.sh          one backup now
#   sh /backup.sh --loop   one backup now and then every 24 hours (how the backup service runs it)
# Restoring: DEPLOY.md, "Restore a backup".
set -eu

backup_once() {
	stamp=$(date +%Y-%m-%d_%H%M)
	# Write to a temporary name first, so a half-written file is never mistaken for a backup.
	pg_dump --format=custom --file="/backups/.db_$stamp.tmp"
	mv "/backups/.db_$stamp.tmp" "/backups/db_$stamp.dump"
	tar -czf "/backups/.uploads_$stamp.tmp" -C /uploads .
	mv "/backups/.uploads_$stamp.tmp" "/backups/uploads_$stamp.tar.gz"
	keep="${BACKUP_KEEP_DAYS:-14}"
	find /backups -maxdepth 1 \( -name 'db_*.dump' -o -name 'uploads_*.tar.gz' \) -mtime +"$keep" -delete
	echo "$(date '+%Y-%m-%d %H:%M') backup done: db_$stamp.dump, uploads_$stamp.tar.gz"
}

if [ "${1:-}" = "--loop" ]; then
	while true; do
		backup_once || echo "$(date '+%Y-%m-%d %H:%M') BACKUP FAILED" >&2
		rm -f /backups/.db_*.tmp /backups/.uploads_*.tmp
		sleep 86400
	done
else
	backup_once
fi
