#!/usr/bin/env bash
# One-time root-only CIFS mount coordinator installer.
set -euo pipefail
if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root" >&2; exit 2
fi
checkout=$(cd "$(dirname "$0")/.." && pwd -P)
if [[ ! -d "$checkout/data" || ! -f "$checkout/scripts/sync_media_mounts.py" ]]; then
  echo "Existing Anthias Hub installation required" >&2; exit 1
fi
if [[ "$checkout" == *[[:space:]]* ]]; then
  echo "Checkout path must not contain whitespace" >&2; exit 1
fi
for cmd in python3 mount.cifs findmnt systemctl; do
  if ! command -v "$cmd" >/dev/null; then echo "Missing: $cmd" >&2; exit 1; fi
done
if [[ ! -f /etc/anthias-hub/smb-allowlist.json ]]; then
  echo "Root-owned SMB allowlist is required at /etc/anthias-hub/smb-allowlist.json" >&2
  exit 1
fi
service=/etc/systemd/system/anthias-hub-smb-mounts.service
timer=/etc/systemd/system/anthias-hub-smb-mounts.timer
if [[ -e "$service" || -e "$timer" ]]; then
  echo "Service/timer already installed; refusing overwrite" >&2; exit 1
fi
cat > "$service" <<EOF
[Unit]
Description=Anthias Hub allowed read-only SMB sources
Wants=network-online.target
After=network-online.target remote-fs.target

[Service]
Type=oneshot
User=root
WorkingDirectory=$checkout
ExecStart=/usr/bin/python3 -m scripts.sync_media_mounts --registry $checkout/data/media-sources.json --status $checkout/data/media-mount-status.json
TimeoutStartSec=5min
EOF
cat > "$timer" <<EOF
[Unit]
Description=Reconcile Anthias Hub approved SMB mounts

[Timer]
OnBootSec=2min
OnUnitActiveSec=1min
Persistent=true
Unit=anthias-hub-smb-mounts.service

[Install]
WantedBy=timers.target
EOF
chmod 0644 "$service" "$timer"
systemctl daemon-reload
systemctl enable --now anthias-hub-smb-mounts.timer
echo "Installed; start anthias-hub-smb-mounts.service for an immediate check."
