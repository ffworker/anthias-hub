#!/usr/bin/env bash
# For a FRESH isolated test host only. Explicitly reject pinned production CD.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

usage() {
  cat <<'USAGE'
Usage: bash scripts/dev-sandbox.sh start|status|logs|stop
Test host only. First run: bash scripts/setup-pilot.sh --solo
Then: mkdir -p dev-sources/demo
Never run this on Produktiv-Hub production.
USAGE
}

refuse_production() {
  [[ -f .env && -f config/users.json ]] ||
    { echo 'Fresh local setup missing: run scripts/setup-pilot.sh --solo first.' >&2; exit 1; }
  if grep -Eq '^(ANTHIAS_HUB_IMAGE|HUB_COMPOSE_OVERRIDE)=' .env; then
    echo 'STOP: This checkout looks like a production/CD deployment. No changes made.' >&2
    exit 1
  fi
  local running_image
  running_image=$(docker inspect anthias-hub-anthias-hub-1 \
    --format '{{.Config.Image}}' 2>/dev/null || true)
  case "$running_image" in
    ghcr.io/*) echo 'STOP: Existing GHCR Hub container detected; refusing to alter production.' >&2; exit 1 ;;
  esac
}

command="${1:-help}"
case "$command" in
  start|status|logs|stop)
    command -v docker >/dev/null || { echo 'Docker is missing.' >&2; exit 1; }
    docker compose version >/dev/null || { echo 'Docker Compose plugin is missing.' >&2; exit 1; }
    refuse_production
    ;;
  help|-h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

dc=(docker compose -p anthias-hub -f compose.yaml -f compose.dev.yaml)
case "$command" in
  start)
    mkdir -p dev-sources/demo
    "${dc[@]}" config --quiet
    "${dc[@]}" up -d --build anthias-hub anthias-folder-import
    "${dc[@]}" ps
    echo 'Dev sandbox ready on http://127.0.0.1:8765 (use SSH tunnel remotely).'
    echo 'Folder importer uses local ./dev-sources/demo; automatic Pi publish OFF by default.'
    ;;
  status)
    "${dc[@]}" ps
    echo '=== Web health ==='
    curl -fsS --max-time 5 http://127.0.0.1:8765/healthz || true
    echo '=== Importer settings (no secrets) ==='
    docker inspect anthias-hub-anthias-folder-import-1 \
      --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null \
      | grep -E '^(FOLDER_SYNC_INTERVAL|FOLDER_AUTO_PUBLISH|FOLDER_PRUNE_MISSING)=' || true
    ;;
  logs)
    "${dc[@]}" logs --tail=80 anthias-hub anthias-folder-import
    ;;
  stop)
    "${dc[@]}" stop anthias-folder-import anthias-hub
    echo 'Sandbox stopped. Local ./data, ./config and ./dev-sources preserved.'
    ;;
esac
