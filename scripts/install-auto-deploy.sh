#!/usr/bin/env bash
# One-time installer for a host-local systemd timer. Run as root after manual GHCR migration.
set -euo pipefail
if [[ "$(id -u)" != 0 || "$#" != 1 ]]; then
  printf 'Usage: sudo bash scripts/install-auto-deploy.sh DOCKER_CAPABLE_USER\n' >&2
  exit 2
fi
user=$1
if [[ ! "$user" =~ ^[a-z_][a-z0-9_-]*$ ]] || ! id "$user" >/dev/null 2>&1; then
  printf 'Use an existing local account name (no spaces).\n' >&2
  exit 2
fi
checkout=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
if [[ "$checkout" == *[[:space:]%]* ]]; then
  printf 'Checkout path must not contain whitespace or %% for the systemd unit.\n' >&2
  exit 2
fi
for file in "$checkout/.env" "$checkout/config/users.json" "$checkout/data/devices.json" "$checkout/compose.cd.yaml"; do
  if [[ ! -f "$file" ]]; then
    printf 'Missing existing Hub state: %s\n' "$file" >&2
    exit 1
  fi
done
if ! runuser -u "$user" -- test -w "$checkout" || ! runuser -u "$user" -- test -w "$checkout/data"; then
  printf 'User must be able to write the checkout lock and data/ quarantine marker.\n' >&2
  exit 1
fi
if ! runuser -u "$user" -- docker info >/dev/null 2>&1; then
  printf 'User cannot access the Docker daemon; do not grant access just for CD.\n' >&2
  exit 1
fi
if ! runuser -u "$user" -- docker compose -f "$checkout/compose.cd.yaml" -p anthias-hub ps -q anthias-hub | grep -q .; then
  printf 'First migrate and verify the existing Hub using compose.cd.yaml.\n' >&2
  exit 1
fi
# Deliberately do not read or rewrite .env, config/ or data/.
service=/etc/systemd/system/anthias-hub-cd.service
timer=/etc/systemd/system/anthias-hub-cd.timer
if [[ -e "$service" || -e "$timer" ]]; then
  printf 'Units already exist; refusing to overwrite them.\n' >&2
  exit 1
fi
python=$(command -v python3)
printf '[Unit]\nDescription=Anthias Hub pull-only deploy with health check and rollback\nWants=network-online.target\nAfter=network-online.target docker.service\n\n[Service]\nType=oneshot\nUser=%s\nWorkingDirectory=%s\nExecStart=%s %s/scripts/auto_deploy.py\nTimeoutStartSec=15min\n' "$user" "$checkout" "$python" "$checkout" > "$service"
printf '[Unit]\nDescription=Check Anthias Hub image for updates\n\n[Timer]\nOnBootSec=5min\nOnUnitActiveSec=15min\nRandomizedDelaySec=2min\nPersistent=true\nUnit=anthias-hub-cd.service\n\n[Install]\nWantedBy=timers.target\n' > "$timer"
chmod 644 "$service" "$timer"
systemctl daemon-reload
systemctl enable --now anthias-hub-cd.timer
printf 'Installed. Inspect: systemctl status anthias-hub-cd.timer; journalctl -u anthias-hub-cd.service -n 50\n'
