#!/usr/bin/env bash
# Updates this server to the newest version on GitHub, safely. Run it from the AccountFlow-AI folder:
#   bash deploy/update.sh            show what is new, ask, then update
#   bash deploy/update.sh --check    only show what is new; change nothing
#   bash deploy/update.sh --yes      update without asking (for deploy/update-all.sh)
# Steps: an encrypted backup, the new code, a rebuild, and a health check of the whole chain
# (Caddy, dashboard, API). If the new version does not come up healthy, the previous version is put back
# and rebuilt automatically, and the backup made at the start is named in case the data needs restoring.
set -euo pipefail

cd "$(dirname "$0")/.."
export COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
mode="${1:-}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-150}"

say() { printf '\n== %s\n' "$*"; }
fail() { printf '\nSTOPPED: %s\n' "$*" >&2; exit 1; }

[ -f .env ] || fail "no .env here: run this in the AccountFlow-AI folder of an installed server."
domain="$(grep -E '^DOMAIN=' .env | head -1 | cut -d= -f2- | cut -d, -f1 | tr -d ' "')"
[ -n "$domain" ] || fail "DOMAIN is not set in .env."
branch="$(git rev-parse --abbrev-ref HEAD)"
[ "$branch" != "HEAD" ] || fail "the code is not on a branch (detached). Run: git checkout main"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
	git status --short --untracked-files=no
	fail "files of the app were changed on this server (listed above). An update would overwrite them; nothing was done."
fi

healthy() {
	# The whole chain, the way a browser reaches it: HTTPS on this server, the dashboard, then the API.
	# (Output goes to /dev/null by redirect, not curl -o, which some Windows builds of curl cannot write to.)
	curl -fsk --max-time 5 --resolve "$domain:443:127.0.0.1" "https://$domain/" > /dev/null &&
		curl -fsk --max-time 5 --resolve "$domain:443:127.0.0.1" "https://$domain/api/health" > /dev/null
}
wait_healthy() {
	local waited=0
	until healthy; do
		[ "$waited" -ge "$HEALTH_TIMEOUT" ] && return 1
		sleep 5
		waited=$((waited + 5))
	done
}

say "Looking for a new version ($branch)"
git fetch --quiet origin "$branch"
current="$(git rev-parse HEAD)"
target="$(git rev-parse "origin/$branch")"
if [ "$current" = "$target" ]; then
	echo "Already up to date: $(git log -1 --format='%h %s')"
	exit 0
fi
git merge-base --is-ancestor "$current" "$target" || fail "this server's code has commits GitHub does not have; update it by hand."
echo "New since $(git log -1 --format='%h' "$current"):"
git log --format='  %h  %s' "$current..$target"
[ "$mode" = "--check" ] && exit 0
if [ "$mode" != "--yes" ]; then
	read -r -p "Update this server now? The app restarts for about a minute. [y/N] " answer
	[ "$answer" = "y" ] || [ "$answer" = "Y" ] || fail "not updated."
fi

say "Backup before the update"
backup_line="$(docker compose exec -T backup sh /usr/local/bin/backup.sh 2>&1 | tail -1)" || true
echo "$backup_line"
case "$backup_line" in
	*"backup done"*) ;;
	*) fail "the backup did not succeed, so nothing was updated. Check: docker compose logs backup" ;;
esac
stamp="$(echo "$backup_line" | sed -n 's/.*db_\([0-9_-]*\)\.dump\.enc.*/\1/p')"

say "Installing $(git log -1 --format='%h %s' "$target")"
git merge --ff-only --quiet "$target"
if docker compose up -d --build --remove-orphans && wait_healthy; then
	say "Updated and healthy: $(git log -1 --format='%h %s')"
	echo "The backup made before the update: $stamp"
	exit 0
fi

say "The new version did not come up healthy. Putting the previous version back"
docker compose logs --tail 30 backend >&2 || true
git reset --hard --quiet "$current"
if docker compose up -d --build --remove-orphans && wait_healthy; then
	echo "Back on the previous version, and healthy: $(git log -1 --format='%h %s')"
else
	echo "The previous version does not come up either. See: docker compose logs backend" >&2
fi
cat >&2 <<EOF

The update was undone. The data was not touched by this script.
If the new version changed or damaged data before it failed, restore the backup made at the start:
  docker compose -f docker-compose.prod.yml stop backend
  docker compose -f docker-compose.prod.yml run --rm --no-deps -v accountflow_uploads:/restore-uploads --entrypoint sh backup /usr/local/bin/restore.sh $stamp
  docker compose -f docker-compose.prod.yml start backend
EOF
exit 1
