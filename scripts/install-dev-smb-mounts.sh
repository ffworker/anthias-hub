#!/usr/bin/env bash
# ROOT-only opt-in for independent DEV SMB mounts. Production untouched.
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo "Run as root" >&2; exit 1; }
cd "$(dirname "${BASH_SOURCE[0]}")/.."
[[ $(pwd -P) == /root/apps/anthias-hub-dev ]] ||
  { echo 'Only /root/apps/anthias-hub-dev is supported.' >&2; exit 1; }
[[ -f .env && -f data/media-sources.json ]] ||
  { echo 'Save the source in the DEV UI first.' >&2; exit 1; }

allowlist=/etc/anthias-hub-dev/smb-allowlist.json
creds=/etc/anthias-hub-dev/secrets
root=/srv/anthias-dev-sources
service=/etc/systemd/system/anthias-hub-dev-smb-mounts.service
timer=/etc/systemd/system/anthias-hub-dev-smb-mounts.timer

for bin in python3 mount.cifs findmnt systemctl; do
  command -v "$bin" >/dev/null || { echo "Missing: $bin" >&2; exit 1; }
done
[[ -f "$allowlist" && ! -L "$allowlist" ]] || {
  echo "Missing DEV root-owned allowlist: $allowlist" >&2; exit 1;
}
[[ -d "$creds" && ! -L "$creds" ]] || {
  echo "Missing DEV credentials directory: $creds" >&2; exit 1;
}
[[ ! -L "$root" ]] || { echo "DEV source root cannot be a symlink" >&2; exit 1; }
install -d -m 0755 "$root"
[[ $(stat -c %u "$root") == 0 ]] || { echo "DEV root must belong to root" >&2; exit 1; }
[[ ! -e "$service" && ! -e "$timer" ]] || {
  echo 'DEV mount service already exists; refusing overwrite.' >&2; exit 1;
}

# Validation occurs before systemd installation, with no mount write.
python3 -m scripts.sync_media_mounts \
  --registry /root/apps/anthias-hub-dev/data/media-sources.json \
  --status "$root/.mount-status.json" \
  --root "$root" --allowlist "$allowlist" --credentials-root "$creds" --check

cat > "$service" <<'UNIT'
[Unit]
Description=Anthias DEV independently allowlisted read-only SMB mounts
Wants=network-online.target
After=network-online.target remote-fs.target

[Service]
Type=oneshot
User=root
WorkingDirectory=/root/apps/anthias-hub-dev
ExecStart=/usr/bin/python3 -m scripts.sync_media_mounts --registry /root/apps/anthias-hub-dev/data/media-sources.json --status /srv/anthias-dev-sources/.mount-status.json --root /srv/anthias-dev-sources --allowlist /etc/anthias-hub-dev/smb-allowlist.json --credentials-root /etc/anthias-hub-dev/secrets
TimeoutStartSec=5min
UNIT
cat > "$timer" <<'UNIT'
[Unit]
Description=Periodically verify Anthias DEV SMB sources

[Timer]
OnBootSec=1min
OnUnitActiveSec=1min
Persistent=true
Unit=anthias-hub-dev-smb-mounts.service

[Install]
WantedBy=timers.target
UNIT
chmod 0644 "$service" "$timer"
systemctl daemon-reload
systemctl enable --now anthias-hub-dev-smb-mounts.timer
systemctl start anthias-hub-dev-smb-mounts.service
echo 'DEV SMB timer installed. Check mount then enable DEV_SMB_MODE=1:'
findmnt -M /srv/anthias-dev-sources/default -o TARGET,SOURCE,FSTYPE,OPTIONS || true
systemctl --no-pager status anthias-hub-dev-smb-mounts.service || true
