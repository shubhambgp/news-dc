#!/usr/bin/env bash
# Encrypted pg_dump of the production DB, keeping the newest 14 backups.
# Cron example (daily 03:00), from the repo directory on the server:
#   0 3 * * * cd /home/ubuntu/newsdc && ./scripts/backup_db.sh >> backups/backup.log 2>&1
# Needs BACKUP_PASSPHRASE in .env. Restore: see docs/DEPLOYMENT.md.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
: "${BACKUP_PASSPHRASE:?set BACKUP_PASSPHRASE in .env}"
umask 077
mkdir -p backups
out="backups/newsdc-$(date -u +%Y%m%dT%H%M%SZ).dump.gpg"
docker compose -f docker-compose.prod.yml exec -T db \
  pg_dump -U "${POSTGRES_USER:-newsdc}" -d "${POSTGRES_DB:-newsdc}" -Fc \
  | gpg --batch --yes --pinentry-mode loopback --symmetric --cipher-algo AES256 --passphrase-fd 3 -o "$out" 3<<<"$BACKUP_PASSPHRASE"
ls -1t backups/newsdc-*.dump.gpg | tail -n +15 | xargs -r rm --
echo "$(date -u +%FT%TZ) wrote $out ($(du -h "$out" | cut -f1))"
