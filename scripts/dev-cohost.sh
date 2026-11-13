#!/usr/bin/env bash
# Separate development installation alongside production on the same host.
# Only operate in a NEW, independent directory named anthias-hub-dev.
set -euo pipefail
cd "$(dirname "$BASH_SOURCE")/.."
project=anthias-hub-dev
image=anthias-hub:dev-cohost
port=8766
root=$(pwd -P)
dc() {
  local -a files=(-f compose.yaml -f compose.dev.yaml)
  if [[ -f .env ]] && grep -qx 'DEV_SMB_MODE=1' .env; then
    files+=(-f compose.dev.smb.yaml)
  fi
  docker compose -p "$project" "${files[@]}" "$@"
}
fail() { printf 'STOP: %s\n' "$*" >&2; exit 1; }
say() { printf '%s\n' "$*"; }
usage() {
  cat <<'HELP'
On the existing Docker host, clone into a NEW directory:
  git clone -b dev/cohosted-staging-isolation-20261113 \
    https://github.com/ffworker/anthias-hub.git /root/apps/anthias-hub-dev
  cd /root/apps/anthias-hub-dev
  bash scripts/dev-cohost.sh init
  bash scripts/dev-cohost.sh start
  bash scripts/dev-cohost.sh status
  bash scripts/dev-cohost.sh logs
  bash scripts/dev-cohost.sh stop
No production upgrades, shared storage, reused image tag or remove-orphans.
HELP
}
guard() {
  [[ "$(basename "$root")" == anthias-hub-dev ]] ||
    fail 'Run only from a separate directory named anthias-hub-dev.'
  # The DEV checkout may switch feature branches. The real safety boundary
  # is the dedicated checkout, Compose project, port, image and storage.
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || fail 'Missing Git checkout.'
  for file in .env config data dev-sources; do
    [[ ! -L "$file" ]] || fail "Symlink at $file is not permitted."
  done
  command -v docker >/dev/null || fail 'Docker unavailable.'
  docker compose version >/dev/null 2>&1 || fail 'Compose plugin missing.'
  [[ -f compose.dev.yaml && -f compose.yaml && -f .env.example ]] ||
    fail 'Missing development Compose files.'
  local prod_dir
  prod_dir=$(docker inspect anthias-hub-anthias-hub-1 \
    --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' 2>/dev/null || true)
  if [[ -n "$prod_dir" && "$prod_dir" != '<no value>' ]]; then
    [[ "$(realpath -m "$prod_dir")" != "$root" ]] ||
      fail 'Production container points at this directory.'
  fi
  if [[ -f .env ]]; then
    if grep -Eq '^ANTHIAS_HUB_IMAGE=|^HUB_COMPOSE_OVERRIDE=' .env; then
      fail 'Found production/CD settings in local .env.'
    fi
    grep -qx "HUB_BIND_PORT=$port" .env || fail 'Expected dev port 8766.'
    grep -qx "HUB_LOCAL_IMAGE=$image" .env || fail 'Expected separate dev image tag.'
  fi
}
init() {
  # A password typo may interrupt a first run AFTER the dev-only .env was
  # written but BEFORE config/users.json exists. Resume safely instead of
  # trapping the operator between "already initialized" and "run init".
  if [[ -f .env && ! -s config/users.json ]]; then
    [[ -t 0 && -t 1 ]] || fail 'Account recovery needs an interactive terminal.'
    local resume_uid resume_gid
    resume_uid=$(sed -n 's/^HUB_UID=//p' .env)
    resume_gid=$(sed -n 's/^HUB_GID=//p' .env)
    [[ "$resume_uid" =~ ^[0-9]+$ && "$resume_gid" =~ ^[0-9]+$ ]] ||
      fail 'Invalid DEV UID/GID in existing .env; refusing changes.'
    [[ -d config && ! -L config ]] || fail 'DEV config directory missing or unsafe.'
    dc build anthias-hub
    say 'Resuming missing DEV owner account; your existing .env stays unchanged.'
    docker run --rm -it --user "$resume_uid:$resume_gid" \
      --mount "type=bind,source=$root/config,target=/config" \
      --entrypoint python "$image" \
      -m scripts.create_user /config/users.json owner owner
    [[ -s config/users.json ]] || fail 'DEV account still missing; retry init.'
    say 'DEV owner created successfully. Run bash scripts/dev-cohost.sh start.'
    return
  fi
  [[ ! -e .env && ! -e config/users.json ]] ||
    fail 'Already initialized. Existing account and secrets were preserved.'
  command -v openssl >/dev/null || fail 'OpenSSL missing.'
  [[ -t 0 && -t 1 ]] || fail 'Initialize interactively to set a private dev password.'
  docker info >/dev/null 2>&1 || fail 'Docker daemon inaccessible.'
  if command -v ss >/dev/null && ss -H -lnt | grep -Eq "[:.]$port[[:space:]]"; then
    fail "Port $port already listening; resolve that before init."
  fi
  umask 077
  mkdir -p config data dev-sources/demo
  local uid gid key
  uid=$(id -u); gid=$(id -g)
  if [[ "$uid" == 0 ]]; then
    uid=11001; gid=11001
    chown "$uid:$gid" config data
  fi
  chmod 700 config data
  chmod 755 dev-sources dev-sources/demo
  key=$(openssl rand -hex 48)
  sed -e "s|^APP_SECRET_KEY=.*|APP_SECRET_KEY=$key|" \
      -e 's|^COOKIE_SECURE=.*|COOKIE_SECURE=0|' \
      -e "s|^HUB_UID=.*|HUB_UID=$uid|" \
      -e "s|^HUB_GID=.*|HUB_GID=$gid|" \
      -e 's|^ANTHIAS_ALLOWED_CIDRS=.*|ANTHIAS_ALLOWED_CIDRS=127.0.0.0/8|' \
      .env.example > .env
  cat >> .env <<EOF
HUB_BIND_PORT=$port
HUB_LOCAL_IMAGE=$image
FOLDER_SYNC_INTERVAL=60
DEV_AUTO_PUBLISH=0
DEV_PRUNE_MISSING=0
EOF
  chmod 600 .env
  dc config --quiet
  say 'Building dedicated development image...'
  dc build anthias-hub
  say 'Create the DEV owner password; this is NOT the production account:'
  docker run --rm -it --user "$uid:$gid" \
    --mount "type=bind,source=$root/config,target=/config" \
    --entrypoint python "$image" \
    -m scripts.create_user /config/users.json owner owner
  [[ -s config/users.json ]] || fail 'Test account creation failed.'
  say 'DEV initialized with local ./dev-sources/demo and a separate owner account.'
  say 'Default player allowlist is loopback-only: set ONLY the test Pi /32 before device registration.'
  say 'Automatic Pi publishing remains OFF. Run: bash scripts/dev-cohost.sh start'
}
prod_id() { docker inspect anthias-hub-anthias-hub-1 --format '{{.Id}}' 2>/dev/null || true; }
start() {
  [[ -f .env && -s config/users.json ]] || fail 'Run init first.'
  docker info >/dev/null 2>&1 || fail 'Docker daemon unavailable.'
  local before after
  before=$(prod_id)
  mkdir -p dev-sources/demo
  if grep -qx 'DEV_SMB_MODE=1' .env; then
    # Docker's default bind propagation can hide CIFS submounts added after
    # container startup. Require an actual mounted test source FIRST, then
    # force-recreate only the DEV services below.
    local fstype
    fstype=$(findmnt -n -M /srv/anthias-dev-sources/default -o FSTYPE 2>/dev/null || true)
    [[ "$fstype" == cifs ]] ||
      fail 'DEV_SMB_MODE=1 needs a verified DEV CIFS mount at /srv/anthias-dev-sources/default.'
  fi
  dc config --quiet
  dc build anthias-hub
  # Refresh only DEV services, including changes to DEV .env/player allowlist.
  dc up -d --no-build --no-deps --force-recreate anthias-hub anthias-folder-import
  after=$(prod_id)
  [[ "$before" == "$after" ]] || fail 'Production ID changed unexpectedly; inspect both projects.'
  say "DEV only: http://127.0.0.1:$port"
  say "Compose project $project; local image $image; production container untouched."
}
status() {
  dc ps
  curl -fsS --max-time 5 "http://127.0.0.1:$port/healthz" || true
  local id
  id=$(dc ps -q anthias-folder-import 2>/dev/null || true)
  if [[ -n "$id" ]]; then
    docker inspect "$id" --format '{{range .Config.Env}}{{println .}}{{end}}' |
      grep -E '^(FOLDER_SYNC_INTERVAL|FOLDER_AUTO_PUBLISH|FOLDER_PRUNE_MISSING)=' || true
  fi
}
if [[ "$#" -eq 0 ]]; then command=help; else command=$1; fi
case "$command" in
  init) guard; init ;;
  start) guard; start ;;
  status) guard; status ;;
  logs) guard; dc logs --tail=90 anthias-hub anthias-folder-import ;;
  stop) guard; dc stop anthias-folder-import anthias-hub; say 'DEV stopped; data preserved.' ;;
  help|-h|--help) usage ;;
  *) usage >&2; exit 2 ;;
esac
