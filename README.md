# RAL CRM

Self-hosted, fully-branded CRM for **RAL Technologies**, built on
[Twenty CRM](https://github.com/twentyhq/twenty) with a built-in Google Maps
lead scraper. Designed for Oracle Cloud Free Tier ($0/month) at
**crm.raltech.dev**; runs identically on any Docker host.

- **Day-to-day usage:** see [`docs/ADMIN-GUIDE.md`](docs/ADMIN-GUIDE.md)
- **Dashboard & automations setup:** see [`docs/PHASE5-dashboard-and-automations.md`](docs/PHASE5-dashboard-and-automations.md)
- **Stack / brand / build phases:** see [`CLAUDE.md`](CLAUDE.md)

## What's in it
- **Objects:** Lead (Pipeline), Priority Lead, Contact, Activity — full field
  set, select options, and Contact/Activity→Lead relations.
- **Views:** Pipeline Kanban, Pipeline List, Priority Leads, Re-engage Pool,
  Overdue Follow-ups, Inactive Leads.
- **Scraper:** gosom/google-maps-scraper as a second container + a bridge that
  imports scraped businesses as Leads with dedupe.
- **Seed data:** 346 leads (97 Active + 249 Re-engage) + 16 Priority Leads.

---

## Architecture

```
            Nginx (TLS, :443)  ──►  Twenty server (:3000)  ──►  Postgres
                                          │                      Redis
                                          └─ worker
            Scrape bridge  ──►  google-maps-scraper (:8080)  ──►  Twenty API
```
All app containers bind to `127.0.0.1`; Nginx is the only public entry point.

---

## Run locally (Docker Desktop)
```bash
git clone https://github.com/HishamGhareeb/CRM.git && cd CRM
cp .env.example .env          # set APP_SECRET + PG_DATABASE_PASSWORD/URL (openssl rand -base64 32)
docker compose up -d          # server, worker, db, redis, scraper
```
Open http://localhost:3000, create the workspace, then build schema + data:
```bash
# put your Twenty API key (Settings -> APIs & Webhooks) into .env as TWENTY_API_KEY
python scripts/phase3_build_schema.py     # objects + fields
python scripts/phase5_build_views.py      # the six views
python scripts/phase6_import_seed.py      # seed CSVs from data/ (git-ignored)
```

## Deploy to the server (Oracle Cloud ARM, Ubuntu 24.04)
Prerequisites: A1 instance running with ports 80/443/22 open; DNS
`crm.raltech.dev` → public IP.
```bash
sudo mkdir -p /opt/ral-crm && sudo chown "$USER" /opt/ral-crm
git clone https://github.com/HishamGhareeb/CRM.git /opt/ral-crm && cd /opt/ral-crm
bash scripts/setup-server.sh          # Docker, Nginx, certbot, firewall (log out/in after)
cp .env.example .env                  # set secrets; SERVER_URL/FRONTEND_URL=https://crm.raltech.dev
docker compose up -d                  # bring up the stack
bash scripts/setup-ssl.sh             # Let's Encrypt + reverse proxy
bash scripts/install-backup-cron.sh   # daily 03:00 Postgres backup, 14-day retention
```
Then run the phase 3/5/6 scripts above (with `TWENTY_URL=https://crm.raltech.dev`).

---

## Repo layout
| Path | Purpose |
|---|---|
| `docker-compose.yml` | Stack: server, worker, Postgres, Redis, scraper |
| `.env.example` | Config template — copy to `.env`, never commit `.env` |
| `nginx/` | Reverse-proxy site config (TLS via certbot) |
| `scripts/setup-server.sh` | Installs Docker, Nginx, certbot, firewall |
| `scripts/setup-ssl.sh` | Issues Let's Encrypt cert, installs proxy config |
| `scripts/backup-postgres.sh` · `install-backup-cron.sh` | Daily DB backup + cron |
| `scripts/phase3_build_schema.py` | Creates the 4 objects + fields (idempotent) |
| `scripts/phase5_build_views.py` | Creates the 6 lead views (idempotent) |
| `scripts/phase6_import_seed.py` | Imports the seed CSVs (idempotent, dedupes) |
| `scripts/phase4_scrape_to_leads.py` | Scrape Google Maps → import as Leads |
| `data/` | Seed CSVs — **git-ignored** (real contact PII / PDPL) |
| `brand/` | Logo assets + generator |
| `docs/` | Admin guide, dashboard & automations setup |

## Security & compliance
- Secrets live only in `.env` (git-ignored). Never hardcode.
- App containers bind to `127.0.0.1`; Nginx is the sole public entry point.
- Seed/lead data (phone numbers, contact notes) is **never committed** — this
  GitHub repo is public; keep personal data to public business info per
  Bahrain PDPL.
