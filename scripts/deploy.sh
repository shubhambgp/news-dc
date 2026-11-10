#!/usr/bin/env bash
# Pull main and rebuild the production stack (run by the CI deploy job, docs/DEPLOYMENT.md).
# The CI key's authorized_keys entry forces this script, so the key can't open a shell.
# Everything is inside main(): bash reads the whole function before git pull rewrites this file.
set -euo pipefail
main() {
  cd "$(dirname "$0")/.."
  git pull --ff-only
  local dc="docker compose -f docker-compose.prod.yml"
  $dc up -d --build --remove-orphans
  for _ in $(seq 1 36); do  # up to 3 minutes for migrations + startup
    [ "$($dc ps backend --format '{{.Health}}')" = healthy ] && break
    sleep 5
  done
  $dc ps --format '{{.Service}} {{.Status}}'
  [ "$($dc ps backend --format '{{.Health}}')" = healthy ] || { echo "backend not healthy"; exit 1; }
  docker image prune -f > /dev/null
  echo "deployed $(git rev-parse --short HEAD)"
}
main "$@"
