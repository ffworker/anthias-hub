#!/usr/bin/env bash
# Anthias Hub — read-only Docker host preflight, no changes or Pi writes.
# Keep output private; it can reveal operational version information.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2
show() { printf '%-29s %s\n' "$1" "$2"; }
echo "Anthias Hub: read-only inventory (NOT production acceptance)"

if command -v git >/dev/null 2>&1; then
  show "Checkout commit" "$(git rev-parse --short HEAD 2>/dev/null || echo unavailable)"
  show "Dirty checkout files" "$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
fi

if [[ -f .env ]]; then
  override="$(sed -n 's/^HUB_COMPOSE_OVERRIDE=//p' .env | tail -n 1)"
  if [[ -z "$override" ]]; then
    show "External Compose override" "not configured"
  elif [[ -f "$override" ]]; then
    show "External Compose override" "configured; file present"
  else
    show "External Compose override" "configured; FILE MISSING"
  fi
else
  show ".env" "missing"
fi

if command -v systemctl >/dev/null 2>&1; then
  for unit in anthias-hub-cd.timer anthias-hub-smb-mounts.timer caddy.service; do
    enabled="$(systemctl is-enabled "$unit" 2>/dev/null || true)"
    [[ -n "$enabled" ]] || enabled="unavailable"
    active="$(systemctl is-active "$unit" 2>/dev/null || true)"
    [[ -n "$active" ]] || active="unavailable"
    show "$unit" "$enabled / $active"
  done
fi

if command -v curl >/dev/null 2>&1 && curl -fsS -o /dev/null --max-time 5 http://127.0.0.1:8765/healthz; then
  show "Hub HTTP health" "reachable (NOT Pi/HDMI proof)"
else
  show "Hub HTTP health" "unreachable"
fi

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  for service in anthias-hub anthias-folder-import; do
    ids="$(docker ps -q --filter label=com.docker.compose.project=anthias-hub --filter "label=com.docker.compose.service=$service" 2>/dev/null)"
    count="$(printf '%s\n' "$ids" | grep -c . || true)"
    if [[ "$count" == 1 ]]; then
      show "$service" "running"
      show "$service image" "$(docker inspect --format '{{.Config.Image}}' "$ids" 2>/dev/null || echo unknown)"
      if [[ "$service" == anthias-folder-import ]]; then
        flag="$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$ids" 2>/dev/null | awk -F= '$1=="FOLDER_AUTO_PUBLISH" {print $2}' | tail -n 1)"
        show "FOLDER_AUTO_PUBLISH" "${flag:-unknown} (expected 0 before test approval)"
      fi
    else
      show "$service" "$count running container(s)"
    fi
  done
else
  show "Docker daemon / access" "unavailable"
fi

if command -v findmnt >/dev/null 2>&1; then
  options="$(findmnt -M /srv/anthias-sources/default -t cifs -n -o OPTIONS 2>/dev/null || true)"
  if [[ -z "$options" ]]; then
    show "Default SMB parent" "NOT confirmed as CIFS mount"
  elif [[ ",$options," == *,ro,* ]]; then
    show "Default SMB parent" "CIFS mount with read-only option"
  else
    show "Default SMB parent" "CIFS mount, read-only NOT confirmed"
  fi
else
  show "findmnt" "unavailable"
fi

if [[ -r /srv/anthias-sources/.mount-status.json ]] && command -v python3 >/dev/null 2>&1; then
  state="$(python3 - /srv/anthias-sources/.mount-status.json <<'PY'
import json, sys, time
try:
    with open(sys.argv[1], encoding='utf-8') as file:
        data = json.load(file)
    state = data.get('sources', {}).get('default', {}).get('state', 'not registered')
    age = time.time() - float(data.get('checked_at', 0))
    print(f'{state}; recent={0 <= age <= 300}')
except (OSError, ValueError, TypeError, AttributeError):
    print('unreadable')
PY
)"
  show "Host mount verification" "$state"
else
  show "Host mount verification" "unavailable"
fi
echo "STOP: this does not check backups, Pi assets, roles, network ACLs or physical TV playback."
