#!/usr/bin/env bash
# Locks down a fresh Ubuntu server for AccountFlow. Run it once, as your own user, from the project folder:
#   sudo bash deploy/harden.sh
# It turns on:
#   - SSH with keys only: no passwords, no direct root password login (stops password guessing)
#   - fail2ban: blocks an address after repeated failed SSH logins
#   - automatic security updates (unattended-upgrades), with a restart at 04:00 when an update needs one
#   - the firewall: only SSH (22), HTTP (80) and HTTPS (443) are open
# It changes nothing unless your login key is already installed, so it cannot lock you out.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
	echo "Run it with sudo:  sudo bash deploy/harden.sh"
	exit 1
fi
. /etc/os-release
if [ "${ID:-}" != "ubuntu" ]; then
	echo "This script is for Ubuntu (found: ${PRETTY_NAME:-unknown}). Nothing was changed."
	exit 1
fi

# The account that will keep logging in over SSH: the sudo user, or root on servers that only have root.
admin="${SUDO_USER:-root}"
home="$(getent passwd "$admin" | cut -d: -f6)"
keys="$home/.ssh/authorized_keys"
if [ ! -s "$keys" ] || ! grep -qE '^(ssh-|ecdsa-|sk-)' "$keys"; then
	cat <<EOF
No SSH login key found for $admin ($keys). Nothing was changed.
Once passwords are switched off, a key is the only way in, so add yours first. On YOUR computer:
  ssh-keygen -t ed25519            (only if you have no key yet; press Enter at the questions)
  ssh-copy-id $admin@<server address>
Then log in again with the key and run this script once more.
EOF
	exit 1
fi
echo "Login key found for $admin: SSH will accept keys only."

echo "== Installing fail2ban, automatic updates and the firewall"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq openssh-server fail2ban unattended-upgrades ufw > /dev/null

echo "== SSH: keys only"
root_login="no"
[ "$admin" = "root" ] && root_login="prohibit-password"   # root keeps key login when it is the only account
mkdir -p /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/10-accountflow.conf <<EOF
# Written by AccountFlow deploy/harden.sh
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin $root_login
PubkeyAuthentication yes
MaxAuthTries 4
EOF
# Check the configuration before using it: a broken file must never be loaded.
if ! sshd -t; then
	rm -f /etc/ssh/sshd_config.d/10-accountflow.conf
	echo "The SSH configuration did not pass its check; the change was undone and SSH is as before."
	exit 1
fi
systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || true

echo "== fail2ban: block repeated failed SSH logins"
cat > /etc/fail2ban/jail.d/accountflow.conf <<EOF
[sshd]
enabled = true
maxretry = 5
findtime = 10m
bantime = 1h
EOF
systemctl enable --now fail2ban > /dev/null 2>&1 || true
systemctl restart fail2ban 2>/dev/null || true

echo "== Automatic security updates"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<EOF
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
cat > /etc/apt/apt.conf.d/52accountflow-upgrades <<EOF
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";
EOF
systemctl enable --now unattended-upgrades > /dev/null 2>&1 || true

echo "== Firewall: SSH, HTTP and HTTPS only"
ufw allow OpenSSH > /dev/null
ufw allow 80/tcp > /dev/null
ufw allow 443/tcp > /dev/null
ufw allow 443/udp > /dev/null
ufw --force enable > /dev/null

cat <<EOF

Done. Keep this session open and, in a NEW terminal, check that you can still log in:
  ssh $admin@<server address>
If that works, the server is locked down. The containers restart by themselves after the 04:00 update restarts.
EOF
