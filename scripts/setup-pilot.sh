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
if [[ -f .env ]]; then
  echo 'Existing .env detected: refusing to overwrite credentials.' >&2
  echo 'Configure accounts and launch manually, or review the existing installation.' >&2
  exit 1
fi
# Root is permitted for initial Docker-host setup, but the application container
# must never inherit root's UID. Use a dedicated unprivileged numeric ID instead.
# Existing installations are protected above by the .env existence check.
if ss -lnt 2>/dev/null | grep -Eq '(^|[[:space:]])(127\.0\.0\.1:8765|0\.0\.0\.0:8765|\*:8765)[[:space:]]'; then
  echo 'Port 8765 is already in use: choose another bind port before proceeding.' >&2
  exit 1
fi
if ! command -v openssl >/dev/null; then
  echo 'openssl is required to generate a random application secret.' >&2
  exit 1
fi
umask 077
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
# Secrets remain in an ignored, owner-only local .env file.
sed -e "s|^APP_SECRET_KEY=.*|APP_SECRET_KEY=$key|" \
    -e 's|^COOKIE_SECURE=.*|COOKIE_SECURE=0|' \
    -e "s|^HUB_UID=.*|HUB_UID=$uid|" \
    -e "s|^HUB_GID=.*|HUB_GID=$gid|" .env.example > .env
chmod 600 .env
chmod 700 config data
printf '\nBuilding isolated anthias-hub pilot image ...\n'
docker compose -p anthias-hub build
for role in it marketing; do
  printf '\nSet a unique 12+ character password for %s:\n' "$role"
  docker run --rm -it --user "$uid:$gid" \
    --mount "type=bind,source=$(pwd)/config,target=/config" \
    --entrypoint python anthias-hub:pilot \
    -m scripts.create_user /config/users.json "$role" "$role"
done
printf '\nStarting hub on 127.0.0.1:8765 ...\n'
docker compose -p anthias-hub up -d
printf '\nHub status:\n'
docker compose -p anthias-hub ps
if curl -fsS --max-time 5 http://127.0.0.1:8765/healthz; then
  echo 'Ready for localhost/SSH tunnel pilot.'
else
  echo 'Container started, but HTTP health check is not available yet. Inspect:' >&2
  echo 'docker compose -p anthias-hub logs --tail=80' >&2
fi
