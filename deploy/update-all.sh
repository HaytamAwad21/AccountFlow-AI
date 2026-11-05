#!/usr/bin/env bash
# Updates every firm's server, one after another, from YOUR computer. List the servers in a file, one per line:
#   ubuntu@app.levi-cpa.co.il
#   ubuntu@app.cohen-cpa.co.il   AccountFlow-AI      (optional second column: the folder, default AccountFlow-AI)
# Lines starting with # are skipped. Then:
#   bash deploy/update-all.sh servers.txt            update each server (deploy/update.sh --yes on it)
#   bash deploy/update-all.sh servers.txt --check    only show what each server would get
# A server that fails is rolled back by update.sh itself; the others still get updated, and the summary at
# the end names every server that needs a look.
set -uo pipefail

list="${1:?give the file with the servers, for example: bash deploy/update-all.sh servers.txt}"
mode="${2:---yes}"
[ -f "$list" ] || { echo "No such file: $list"; exit 1; }

ok=()
failed=()
while read -r server folder _; do
	case "$server" in "" | \#*) continue ;; esac
	folder="${folder:-AccountFlow-AI}"
	printf '\n######## %s\n' "$server"
	# -n: ssh must not read the server list from this loop's input
	if ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$server" "cd '$folder' && bash deploy/update.sh $mode"; then
		ok+=("$server")
	else
		failed+=("$server")
	fi
done < "$list"

printf '\n######## Summary\n'
for s in "${ok[@]}"; do echo "  ok      $s"; done
for s in "${failed[@]}"; do echo "  FAILED  $s   (see its output above; update.sh rolled it back)"; done
[ ${#failed[@]} -eq 0 ]
