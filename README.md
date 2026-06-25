# RAL CRM

Self-hosted, fully-branded CRM for **RAL Technologies**, built on
[Twenty CRM](https://github.com/twentyhq/twenty) with a built-in
Google Maps lead scraper. Runs on Oracle Cloud Free Tier ($0/month target)
at **crm.raltech.dev**.

See [`CLAUDE.md`](CLAUDE.md) for the full stack, brand, and build-phase overview.

---

## Phase 1 — Base infrastructure (current)

This repo holds the deployment as infrastructure-as-code. To stand up a
fresh Oracle Cloud ARM VM (Ubuntu 24.04 Minimal, aarch64):

### 0. Prerequisites (manual)
- Oracle Cloud Always-Free Ampere A1 instance running, ports 80/443/22 open
  in the Oracle security list.
- DNS A-record: `crm.raltech.dev` → instance public IP.

### 1. Clone & bootstrap
```bash
sudo mkdir -p /opt/ral-crm && sudo chown "$USER" /opt/ral-crm
git clone https://github.com/HishamGhareeb/CRM.git /opt/ral-crm
cd /opt/ral-crm
bash scripts/setup-server.sh      # Docker, Nginx, certbot, firewall
```
Log out/in once so the `docker` group applies.

### 2. Configure environment
```bash
cp .env.example .env
# Generate secrets:  openssl rand -base64 32
nano .env                          # set APP_SECRET, PG_DATABASE_PASSWORD, PG_DATABASE_URL
```

### 3. SSL + reverse proxy
```bash
bash scripts/setup-ssl.sh          # Let's Encrypt cert + Nginx proxy for crm.raltech.dev
```

### 4. Daily backups
```bash
bash scripts/install-backup-cron.sh   # 03:00 daily Postgres dump -> $BACKUP_DIR, 14-day retention
```

> Phase 1 deliverable: empty server ready, SSL working, backups scheduled.
> The Twenty stack itself (`docker compose up -d`) is brought up in **Phase 2**.

---

## Repo layout
| Path | Purpose |
|---|---|
| `docker-compose.yml` | Twenty stack: server, worker, Postgres, Redis |
| `.env.example` | Config template — copy to `.env` on server, never commit `.env` |
| `nginx/` | Reverse-proxy site config (TLS via certbot) |
| `scripts/setup-server.sh` | Installs Docker, Nginx, certbot, firewall |
| `scripts/setup-ssl.sh` | Issues Let's Encrypt cert, installs proxy config |
| `scripts/backup-postgres.sh` | Gzipped daily DB dump with retention |
| `scripts/install-backup-cron.sh` | Schedules the backup at 03:00 |

## Security
- Secrets live only in `.env` (git-ignored). Never hardcode.
- Twenty containers bind to `127.0.0.1` only; Nginx is the sole public entry point.
