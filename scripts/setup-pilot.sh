#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ ! -f compose.yaml || ! -f .env.example ]]; then
  echo 'Run from the Anthias Hub checkout.' >&2
  exit 1
fi
if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
  echo 'Docker Compose is required and must be accessible to this user.' >&2
  exit 1
fi
if [[ "${1:-}" != '' && "${1:-}" != '--reset-users' ]]; then
  echo 'Usage: bash scripts/setup-pilot.sh [--reset-users]' >&2
  exit 2
fi
reset_users=${1:-}
# Only a fresh installation needs an unused port and a new secret.
if [[ ! -f .env ]] && ss -lnt 2>/dev/null | grep -Eq '(^|[[:space:]])(127\.0\.0\.1:8765|0\.0\.0\.0:8765|\*:8765)[[:space:]]'; then
  echo 'Port 8765 is already in use: choose another bind port before proceeding.' >&2
  exit 1
fi
# Root is permitted for initial Docker-host setup, but the application container
# must never inherit root's UID. Use a dedicated unprivileged numeric ID instead.
if ! command -v openssl >/dev/null; then
  echo 'openssl is required to generate a random application secret.' >&2
  exit 1
fi
umask 077
if [[ ! -f .env ]]; then
  mkdir -p config data
  uid=$(id -u)
  gid=$(id -g)
  if [[ "$uid" -eq 0 ]]; then
    uid=10001
    gid=10001
    chown "$uid:$gid" config data
    echo 'Root setup detected: container and writable directories will use UID/GID 10001:10001 (not root).'
  fi
  key=$(openssl rand -hex 48)
  # Create the secret only once. A rerun never replaces an existing .env.
  sed -e "s|^APP_SECRET_KEY=.*|APP_SECRET_KEY=$key|" \
      -e 's|^COOKIE_SECURE=.*|COOKIE_SECURE=0|' \
      -e "s|^HUB_UID=.*|HUB_UID=$uid|" \
      -e "s|^HUB_GID=.*|HUB_GID=$gid|" .env.example > .env
  chmod 600 .env
  chmod 700 config data
else
  echo 'Resuming existing installation; preserving .env, config and data.'
fi
# Compose reads the existing UID/GID and image pin from .env.
uid=$(sed -n 's/^HUB_UID=//p' .env)
gid=$(sed -n 's/^HUB_GID=//p' .env)
if [[ ! "$uid" =~ ^[0-9]+$ || ! "$gid" =~ ^[0-9]+$ ]]; then
  echo 'Missing or invalid HUB_UID/HUB_GID in .env; refusing to change existing files.' >&2
  exit 1
fi
if grep -q '^ANTHIAS_HUB_IMAGE=' .env; then
  compose=(docker compose -f compose.cd.yaml -p anthias-hub)
  image=$("${compose[@]}" config --images)
  [[ -n "$image" ]] || { echo 'No pinned image resolved by Compose.' >&2; exit 1; }
  if ! docker image inspect "$image" >/dev/null 2>&1; then
    "${compose[@]}" pull anthias-hub
  fi
else
  compose=(docker compose -p anthias-hub)
  image=anthias-hub:pilot
  if ! docker image inspect "$image" >/dev/null 2>&1; then
    printf '\nBuilding isolated anthias-hub pilot image ...\n'
    "${compose[@]}" build
  fi
fi
# Detect missing roles using the image's Python; malformed files fail closed.
for role in it marketing; do
  status=0
  docker run --rm --user "$uid:$gid" \
    --mount "type=bind,source=$(pwd)/config,target=/config,readonly" \
    --entrypoint python "$image" -c '
import json, pathlib, sys
p = pathlib.Path("/config/users.json")
try:
    users = json.loads(p.read_text())["users"] if p.exists() else []
    if not isinstance(users, list): raise ValueError("users must be a list")
    present = any(u["username"] == sys.argv[1] and u["role"] == sys.argv[1] and u.get("password_hash") for u in users)
except (ValueError, KeyError, TypeError) as e:
    print(f"Invalid users.json: {e}", file=sys.stderr)
    sys.exit(2)
sys.exit(0 if present else 1)
' "$role" || status=$?
  if [[ "$status" -gt 1 ]]; then
    echo "Could not inspect $role account (exit $status); refusing to change users.json." >&2
    exit 1
  fi
  if [[ "$status" -eq 0 && "$reset_users" != '--reset-users' ]]; then
    echo "Keeping existing $role account."
    continue
  fi
  if [[ "$status" -eq 0 ]]; then
    read -r -p "Replace password for $role? [y/N] " answer
    [[ "$answer" =~ ^[Yy]$ ]] || continue
  fi
  printf '\nSet a unique 12+ character password for %s (retry setup if interrupted):\n' "$role"
  docker run --rm -it --user "$uid:$gid" \
    --mount "type=bind,source=$(pwd)/config,target=/config" \
    --entrypoint python "$image" \
    -m scripts.create_user /config/users.json "$role" "$role"
done
printf '\nStarting hub on 127.0.0.1:8765 ...\n'
"${compose[@]}" up -d
printf '\nHub status:\n'
"${compose[@]}" ps
if curl -fsS --max-time 5 http://127.0.0.1:8765/healthz; then
  echo 'Ready for localhost/SSH tunnel pilot.'
else
  echo 'Container started, but HTTP health check is not available yet. Inspect:' >&2
  echo 'docker compose -p anthias-hub logs --tail=80' >&2
fi
