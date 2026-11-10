# Deployment

Production runs `docker-compose.prod.yml` on one VPS: Caddy (ports 80/443, automatic HTTPS) → `/api/*` to `backend:8000` (FastAPI) and everything else to `frontend:8080` (Nginx serving the Vite build). The `worker` runs scheduled ingestion, the AI pipeline and the weekly brief. `db` is Postgres 16 + pgvector with no public port.

Live instance: `https://news-dc.atinus.co` (VPS `15.235.142.100`, Ubuntu 26.04, 2 vCPU / 4 GB, repo in `/home/ubuntu/newsdc`).

## 1. Server setup (once)

```bash
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git
sudo usermod -aG docker $USER          # log out and in again
sudo ufw allow OpenSSH && sudo ufw allow 80/tcp && sudo ufw allow 443 && sudo ufw enable
```
Recommended hardening: add your SSH key (`ssh-copy-id ubuntu@<ip>`), then set `PasswordAuthentication no` in `/etc/ssh/sshd_config` and `sudo systemctl restart ssh`.

## 2. DNS

Create an **A record** for the hostname pointing to the server's IPv4 address (for `news-dc.atinus.co`: name `news-dc`, value `15.235.142.100`). If the zone is on Cloudflare, set the record to **DNS only** (grey cloud) so Caddy gets the Let's Encrypt certificate itself. If you later turn the proxy on, use SSL mode **Full (strict)**. Caddy retries the certificate on its own until the record resolves.

## 3. Configure and start

```bash
git clone https://github.com/shubhambgp/news-dc.git newsdc && cd newsdc
cp .env.example .env && chmod 600 .env
```
Set these in `.env` (generate secrets with `openssl rand -hex 32`):

| Variable | Value |
|---|---|
| `DOMAIN` | `news-dc.atinus.co` |
| `CORS_ORIGINS` | `https://news-dc.atinus.co` (also the allowed Origin for admin writes) |
| `VITE_API_BASE_URL` | empty (same origin) |
| `POSTGRES_PASSWORD`, `ADMIN_TOKEN`, `SESSION_SECRET`, `BACKUP_PASSPHRASE` | separate long random values |
| `ANTHROPIC_API_KEY`, `CLASSIFIER_MODEL`, `ASSISTANT_MODEL` and the `*_USD_PER_MTOK` prices | see `docs/AI_CONFIG.md` |

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps        # backend, db, frontend: healthy
```
The backend runs `alembic upgrade head` before it starts, and seeds categories and sources on startup. The fastembed model (bge-small, about 130 MB) is downloaded on first use into the `models` volume, so it survives rebuilds without being baked into the image.

## 4. First data load

The worker enqueues an ingest on start and every `INGEST_INTERVAL_MINUTES`, and a pipeline run after each ingest. To fill the site with a year of history (the pipeline makes paid LLM calls, capped by `MAX_LLM_ITEMS_PER_RUN` and `DAILY_LLM_BUDGET_USD`):
```bash
docker compose -f docker-compose.prod.yml exec backend python -m app.ingest --all --since-days 365
docker compose -f docker-compose.prod.yml exec backend python -m app.pipeline --limit 3000
```

## 5. Check it

```bash
./scripts/smoke_test.sh https://news-dc.atinus.co    # health, frontend, feed, article, search, ask (one paid call), admin 401, export
```
Then open the site: feeds have data, Ask AI answers with citations, `/admin` accepts `ADMIN_TOKEN`.

Run these with `exec` only while you won't run `up -d`: any `up -d` (even `up -d caddy`) recreates a container whose `.env` values changed, and that kills a pipeline running inside it. Already stored items are safe; the rest stay `new` and the worker processes them later (or `python -m app.jobs enqueue pipeline`).

## Update

```bash
cd ~/newsdc && git pull && docker compose -f docker-compose.prod.yml up -d --build
```
Migrations run on backend start. The worker gets up to 60 s to put its running job back.

## Logs

```bash
docker compose -f docker-compose.prod.yml logs -f --tail 100 backend worker   # JSON lines
docker compose -f docker-compose.prod.yml logs caddy                            # certificates, proxy errors
docker compose -f docker-compose.prod.yml exec backend python -m app.jobs list  # job queue
```
Docker rotates every container's log at 10 MB, keeping 5 files.

## Backup and restore

`scripts/backup_db.sh` writes an AES-256 encrypted `pg_dump` (custom format) to `backups/` (mode 600) and keeps the newest 14. It needs `gpg` and `BACKUP_PASSPHRASE` in `.env`. Keep a copy of the passphrase outside the server, or the backups can't be read. Daily at 03:00 UTC:
```bash
crontab -e
0 3 * * * cd /home/ubuntu/newsdc && ./scripts/backup_db.sh >> backups/backup.log 2>&1
```
Copy `backups/` off the server regularly (e.g. `rsync` to another machine).

Restore (into a fresh database, then swap):
```bash
set -a; . ./.env; set +a
f=backups/newsdc-<timestamp>.dump.gpg
docker compose -f docker-compose.prod.yml stop backend worker
docker compose -f docker-compose.prod.yml exec -T db dropdb -U newsdc newsdc
docker compose -f docker-compose.prod.yml exec -T db createdb -U newsdc newsdc
gpg --batch --pinentry-mode loopback --passphrase "$BACKUP_PASSPHRASE" -d "$f" \
  | docker compose -f docker-compose.prod.yml exec -T db pg_restore -U newsdc -d newsdc --no-owner
docker compose -f docker-compose.prod.yml start backend worker
```
To test a backup without touching production, restore into a scratch database instead (`createdb newsdc_restore_test`, `pg_restore -d newsdc_restore_test`, count `items`, `dropdb`). That test is recorded in `VERIFICATION_LOG.md`.

## Secret rotation

Change the value in `.env`, then `docker compose -f docker-compose.prod.yml up -d` (recreates containers whose env changed).
- `ADMIN_TOKEN`, `SESSION_SECRET`: rotating `SESSION_SECRET` logs every admin out.
- `ANTHROPIC_API_KEY`: create the new key in the console, deploy, then revoke the old one.
- `POSTGRES_PASSWORD`: the variable only applies when the volume is first created. Change it in the DB first: `docker compose -f docker-compose.prod.yml exec db psql -U newsdc -c "ALTER USER newsdc PASSWORD '<new>'"`, then in `.env`, then `up -d`.
- `BACKUP_PASSPHRASE`: old backups still need the old passphrase; keep it until they age out.

## Performance notes

- `GET` responses from the public API carry `Cache-Control: public, max-age=30`; `/admin`, `/health` and `/ready` are `no-store`. `/topics` and `/stats` are cached in memory for 60 s per backend process.
- Vite assets have hashed names and are served `immutable` for a year; `index.html` is `no-cache`. Caddy compresses with zstd/gzip, except the `/ask` event stream.
- Routes are lazy-loaded. Bundle sizes (gzip): main 111 KB, Dashboard (Recharts) 113 KB, Markdown 36 KB.
