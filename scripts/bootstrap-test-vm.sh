#!/usr/bin/env bash
# Optional convenience workflow for the disposable co-located TEST VM only.
# No apt installs, git pulls/resets, secret replacement or CD timer installation.
set -euo pipefail
umask 077

hub_dir=$(cd "$(dirname "$0")/.." && pwd -P)
apps_dir=$(dirname "$hub_dir")
rss_dir=$apps_dir/rss2slideshow
key=$HOME/.ssh/rss2slideshow_deploy_ed25519
if [[ -n $(printenv RSS_DEPLOY_KEY 2>/dev/null || true) ]]; then
  key=$RSS_DEPLOY_KEY
fi

say() { printf '%s\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || fail "Missing $1; install it first (no automatic package changes)."; }
in_repo() { git -C "$1" rev-parse --is-inside-work-tree >/dev/null 2>&1; }
# Checking only -s is unsafe: a directory can also have a nonzero size.
runtime_file() { [[ -f "$1" && -s "$1" ]]; }
report_runtime_file() {
  if runtime_file "$1"; then
    say "OK   $1"
  elif [[ -d "$1" ]]; then
    say "BAD  $1 is a DIRECTORY, expected a regular file (Docker may have created it)"
    return 1
  else
    say "MISS $1 (missing, empty or not a regular file)"
    return 1
  fi
}
docker_ready() {
  need docker
  docker compose version >/dev/null 2>&1 || fail "Docker Compose plugin is missing."
  docker info >/dev/null 2>&1 || fail "Docker daemon unavailable to this account."
}
rss_ready() {
  [[ -d "$rss_dir" ]] && in_repo "$rss_dir" ||
    fail "No RSS checkout in $rss_dir; run key, register the key on GitHub, then clone-rss."
}
usage() {
  cat <<'USAGE'
Usage: bash scripts/bootstrap-test-vm.sh COMMAND
  doctor     Inspect prerequisites and local runtime state (read-only)
  key        Create/show THIS VM's read-only RSS GitHub deploy public key
  clone-rss  Clone/configure private RSS repo with the registered SSH key
  init       Create only missing sample RSS files; initialize fresh Hub accounts
  deploy     Explicitly build/start BOTH independent pilot Compose projects
  status     Show service status and localhost HTTP checks (read-only)
Run this script from any directory. No automatic Git update or production deploy.
USAGE
}
doctor() {
  say "Host: $(hostname) | app directory: $apps_dir"
  local bad=0 tool
  for tool in git curl openssl ssh ssh-keygen docker; do
    if command -v "$tool" >/dev/null 2>&1; then say "OK   $tool"; else say "MISS $tool"; bad=1; fi
  done
  if command -v docker >/dev/null 2>&1; then
    docker compose version || bad=1
    if docker info >/dev/null 2>&1; then say "OK   Docker daemon"; else say "MISS Docker daemon access"; bad=1; fi
  fi
  if in_repo "$hub_dir"; then say "OK   Anthias Hub checkout"; else say "MISS Hub checkout"; bad=1; fi
  if in_repo "$rss_dir"; then say "OK   RSS checkout"; else say "MISS RSS checkout (see key / clone-rss)"; bad=1; fi
  for path in "$hub_dir/.env" "$hub_dir/config/users.json" "$rss_dir/.env" "$rss_dir/config.yaml" "$rss_dir/content/feeds.txt"; do
    report_runtime_file "$path" || bad=1
  done
  if [[ -f "$key" ]]; then say "OK   RSS SSH private key exists (not displayed)"; else say "MISS RSS SSH key ($key)"; fi
  return "$bad"
}
prepare_key() {
  need ssh-keygen
  install -d -m 700 "$(dirname "$key")"
  if [[ ! -e "$key" ]]; then
    [[ ! -e "$key.pub" ]] || fail "Public key exists but private key missing; investigate, do not overwrite."
    ssh-keygen -q -t ed25519 -f "$key" -C 'rss2slideshow-test-vm' -N ''
  fi
  chmod 600 "$key"
  say "Register this PUBLIC key as a READ-ONLY deploy key at:"
  say "https://github.com/ffworker/rss2slideshow/settings/keys"
  ssh-keygen -y -f "$key"
  say "Verify GitHub's SSH host fingerprint on first connection; never disable host-key checking."
}
clone_rss() {
  need git; need ssh
  [[ -f "$key" ]] || fail "Missing $key; run key first."
  local quoted ssh_cmd origin
  printf -v quoted '%q' "$key"
  ssh_cmd="ssh -i $quoted -o IdentitiesOnly=yes -o BatchMode=yes"
  say "Checking read-only SSH access to private RSS repository..."
  GIT_SSH_COMMAND="$ssh_cmd" git ls-remote git@github.com:ffworker/rss2slideshow.git HEAD >/dev/null ||
    fail "Access denied or GitHub host not trusted. Register the public deploy key and verify GitHub host fingerprint."
  if [[ -e "$rss_dir" ]]; then
    rss_ready
    origin=$(git -C "$rss_dir" remote get-url origin)
    case "$origin" in
      git@github.com:ffworker/rss2slideshow.git|https://github.com/ffworker/rss2slideshow.git)
        ;;
      *) fail "Unexpected RSS origin: $origin. Refusing to modify."; ;;
    esac
    say "Existing RSS checkout preserved."
  else
    GIT_SSH_COMMAND="$ssh_cmd" git clone git@github.com:ffworker/rss2slideshow.git "$rss_dir"
  fi
  git -C "$rss_dir" remote set-url origin git@github.com:ffworker/rss2slideshow.git
  git -C "$rss_dir" config --local core.sshCommand "$ssh_cmd"
  say "RSS clone configured to use the VM-specific key; no pull/reset performed."
}
copy_if_missing() {
  local source=$1 target=$2
  [[ -f "$source" ]] || fail "Missing template $source; check repository layout."
  if [[ -d "$target" ]]; then
    fail "$target is a directory, expected a file. Stop the container; if empty, remove with rmdir and rerun init. No automatic deletion."
  fi
  if [[ -e "$target" || -L "$target" ]]; then say "KEEP $target"; return; fi
  cp "$source" "$target"
  chmod 600 "$target"
  say "NEW  $target (review before deployment)"
}
init() {
  need git; need curl; need openssl
  docker_ready; rss_ready
  [[ -f "$rss_dir/.env.example" && -f "$rss_dir/config.example.yaml" &&
     -f "$rss_dir/content/feeds.example.txt" ]] ||
    fail "RSS sample templates missing; verify this repository revision."
  mkdir -p "$rss_dir/content"
  copy_if_missing "$rss_dir/.env.example" "$rss_dir/.env"
  copy_if_missing "$rss_dir/config.example.yaml" "$rss_dir/config.yaml"
  copy_if_missing "$rss_dir/content/feeds.example.txt" "$rss_dir/content/feeds.txt"
  if [[ -e "$hub_dir/.env" ]]; then
    say "KEEP $hub_dir/.env (never overwrite credentials)"
    runtime_file "$hub_dir/.env" ||
      fail "Hub .env is missing, empty or not a regular file; recover it before proceeding."
    runtime_file "$hub_dir/config/users.json" ||
      fail "Hub .env exists but config/users.json is missing/empty. Restore users from backup or follow Hub account recovery docs."
  else
    [[ ! -e "$hub_dir/config/users.json" ]] ||
      fail "Hub users exist without .env: stop and recover matching secret/config first."
    [[ -t 0 && -t 1 ]] || fail "Fresh Hub setup needs an interactive console for account passwords."
    say "Initializing a NEW Hub only; this prompts for IT/Marketing passwords and starts its pilot container."
    ( cd "$hub_dir" && bash scripts/setup-pilot.sh )
  fi
  say "Initialization complete. Review RSS .env, config.yaml and feeds.txt before deploy."
}
validate() {
  docker_ready; rss_ready
  local path
  for path in "$hub_dir/.env" "$hub_dir/config/users.json" \
    "$rss_dir/.env" "$rss_dir/config.yaml" "$rss_dir/content/feeds.txt"; do
    runtime_file "$path" ||
      fail "$path must be a nonempty regular file (not a directory). Run doctor; for an empty Docker-created directory, stop the container and use rmdir before init."
  done
  if grep -Eq '^ANTHIAS_HUB_IMAGE=' "$hub_dir/.env"; then
    fail "Hub .env has a pinned image reference. Refusing to replace a CD/production deployment with pilot Compose."
  fi
  if grep -Eq '^APP_SECRET_KEY=(REPLACE_|[[:space:]]*$)' "$hub_dir/.env"; then
    fail "Hub APP_SECRET_KEY is a placeholder; do not deploy."
  fi
  ( cd "$hub_dir" && docker compose -p anthias-hub config --quiet )
  ( cd "$rss_dir" && docker compose -p rss2slideshow config --quiet )
}
deploy() {
  validate
  if cmp -s "$rss_dir/content/feeds.txt" "$rss_dir/content/feeds.example.txt"; then
    say "WARNING: RSS is using example feeds; this is NOT an acceptance test for production."
  fi
  say "Explicitly building and starting Anthias Hub (pilot Compose)..."
  ( cd "$hub_dir" && docker compose -p anthias-hub up -d --build )
  say "Explicitly building and starting RSS2Slideshow (separate Compose project)..."
  ( cd "$rss_dir" && docker compose -p rss2slideshow up -d --build )
  status
}
status() {
  docker_ready; rss_ready
  say "=== Anthias Hub ==="
  ( cd "$hub_dir" && docker compose -p anthias-hub ps )
  say "=== RSS2Slideshow ==="
  ( cd "$rss_dir" && docker compose -p rss2slideshow ps )
  say "=== HTTP checks (do not prove Pi or TV output) ==="
  local bad=0 bind host port
  if curl -fsS --max-time 6 http://127.0.0.1:8765/healthz >/dev/null; then
    say "OK   Hub /healthz on localhost:8765"
  else
    say "FAIL Hub /healthz; check docker compose -p anthias-hub logs --tail=80"
    bad=1
  fi
  bind=$(cd "$rss_dir" && docker compose -p rss2slideshow port signage 8080 2>/dev/null | head -n 1) || true
  if [[ -z "$bind" ]]; then
    say "FAIL RSS port binding (signage container not running?)"
    bad=1
  else
    host=$(printf '%s' "$bind" | sed -E 's/:[0-9]+$//')
    port=$(printf '%s' "$bind" | sed -E 's/^.*:([0-9]+)$/\1/')
    case "$host" in '0.0.0.0'|'::'|'[::]') host=127.0.0.1;; esac
    if curl -fsS --max-time 8 "http://$host:$port/healthz" >/dev/null &&
       curl -fsS --max-time 8 "http://$host:$port/api/articles" >/dev/null; then
      say "OK   RSS /healthz and /api/articles on $host:$port"
    else
      say "FAIL RSS HTTP checks on $host:$port; inspect logs and BIND_IP/HTTP_PORT."
      bad=1
    fi
  fi
  say "Still required: check article freshness, login, player playlist and actual TV display."
  return "$bad"
}
if (( $# == 0 )); then cmd=help; else cmd=$1; fi
case "$cmd" in
  doctor) doctor ;;
  key) prepare_key ;;
  clone-rss) clone_rss ;;
  init) init ;;
  deploy) deploy ;;
  status) status ;;
  help|-h|--help) usage ;;
  *) usage >&2; exit 2 ;;
esac
