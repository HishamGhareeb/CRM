# RAL CRM

Self-hosted, fully-branded CRM for **RAL Technologies**, built on
[Twenty CRM](https://github.com/twentyhq/twenty) with a Google Maps + Instagram
lead-sourcing pipeline and a bilingual (EN/AR) cold-outreach engine on top.
Runs on any standard Docker host — x86_64 or ARM, no cloud-provider-specific
setup required.

- **Day-to-day usage:** see [`docs/ADMIN-GUIDE.md`](docs/ADMIN-GUIDE.md)
- **Dashboard & automations setup:** see [`docs/PHASE5-dashboard-and-automations.md`](docs/PHASE5-dashboard-and-automations.md)
- **Moving to another machine/server:** see [`docs/MIGRATION.md`](docs/MIGRATION.md)
  (whole-instance move) or the lead-merge tools below (combining two instances)
- **Stack / brand / build notes:** see [`CLAUDE.md`](CLAUDE.md)

## What's in it
- **Objects:** Lead (Pipeline), Priority Lead, Contact, Activity — full field
  set, select options, and Contact/Activity→Lead relations. Includes `Country`
  (Bahrain/Saudi/UAE/Kuwait/Qatar/Oman/Other) and dual-language `Email Draft`
  (English) + `Email Draft (Arabic)`.
- **Views:** 7 pipeline views — Kanban, List, Priority Leads, Hot Leads,
  Re-engage Pool, Overdue Follow-ups, Inactive Leads.
- **Lead sourcing:**
  - Google Maps — `gosom/google-maps-scraper` as a second container +
    `scripts/scrape_industries.py` (volume, multi-region, multi-industry) or
    `scripts/phase4_scrape_to_leads.py` (single query). Imports as Leads with
    dedupe and per-business enrichment (rating, hours, pain points, lead score).
  - Instagram — `scripts/scrape_instagram.py` (throwaway account, rate-limited).
- **Outreach:** personalized WhatsApp openers and cold-email drafts per lead
  (English + natural-dialect Arabic for Saudi leads), generated from a single
  template source (`scripts/lib_outreach.py`). `scripts/send_emails.py` sends
  them — dry-run by default, any SMTP provider, safe rate-limited automation
  via `scripts/scheduled_send_emails.py`.
- **Multi-instance merge:** `scripts/export_leads.py` / `import_leads.py` —
  move or combine leads between two separate CRM instances (e.g. two people
  each scraping independently, then merging into one).

---

## Architecture

```
            Nginx (TLS, :443)  ──►  Twenty server (:3000)  ──►  Postgres
                                          │                      Redis
                                          └─ worker
            Scrape bridge  ──►  google-maps-scraper (:8080)  ──►  Twenty API
            scheduled_send_emails.py (cron/Task Scheduler) ──►  send_emails.py ──►  SMTP
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
python scripts/phase5_build_views.py      # the seven views
python scripts/phase6_import_seed.py      # seed CSVs from data/ (git-ignored)
```
If the scraper fails on first run with a driver-install error, see
`docs/ADMIN-GUIDE.md` ("If the scraper fails...") — one known upstream issue,
one command to fix it.

## Deploy to a server
Works on any Ubuntu 22.04/24.04 host with Docker — a VPS, a cloud VM, bare
metal, whatever's available. Twenty's images are multi-arch (x86_64 and ARM64
both work unmodified).

Prerequisites: the server has ports 80/443/22 open (in its firewall *and* any
cloud provider's separate network security group, if applicable); DNS for
your chosen domain points at its public IP.
```bash
sudo mkdir -p /opt/ral-crm && sudo chown "$USER" /opt/ral-crm
git clone https://github.com/HishamGhareeb/CRM.git /opt/ral-crm && cd /opt/ral-crm
bash scripts/setup-server.sh          # Docker, Nginx, certbot, firewall (log out/in after)
cp .env.example .env                  # set secrets; SERVER_URL/FRONTEND_URL/DOMAIN for your domain
docker compose up -d                  # bring up the stack
bash scripts/setup-ssl.sh             # Let's Encrypt + reverse proxy (reads DOMAIN from .env)
bash scripts/install-backup-cron.sh   # daily 03:00 Postgres backup, 14-day retention
```
Then run the phase 3/5/6 scripts above (with `TWENTY_URL=https://<your-domain>`).
Deploying under a domain other than `crm.raltech.dev`: copy
`nginx/crm.raltech.dev.conf` to `nginx/<your-domain>.conf`, replace the domain
inside it, and set `DOMAIN=<your-domain>` in `.env` before running `setup-ssl.sh`.

---

## Repo layout
| Path | Purpose |
|---|---|
| `docker-compose.yml` | Stack: server, worker, Postgres, Redis, scraper |
| `.env.example` | Config template — copy to `.env`, never commit `.env` |
| `nginx/` | Reverse-proxy site config (TLS via certbot) |
| `brand/` | RAL logo assets + generator (`generate-logos.py`) |
| `data/` / `migration/` | Seed CSVs / cross-instance export bundles — **git-ignored** (PII) |

**Setup & ops**
| Script | Purpose |
|---|---|
| `scripts/setup-server.sh` | Installs Docker, Nginx, certbot, firewall |
| `scripts/setup-ssl.sh` | Issues Let's Encrypt cert, installs proxy config |
| `scripts/fix-scraper-driver.sh` | Fixes a known Playwright-driver install failure in the scraper image |
| `scripts/backup-postgres.sh` · `install-backup-cron.sh` | Daily DB backup + cron |
| `scripts/export-workspace.sh` · `import-workspace.sh` | Move the whole instance to another machine |

**Data model & views**
| Script | Purpose |
|---|---|
| `scripts/phase3_build_schema.py` | Creates the 4 objects + all fields (idempotent) |
| `scripts/phase5_build_views.py` | Creates the 7 lead views (idempotent) |
| `scripts/phase5_build_dashboard.py` | Builds the dashboard widgets |
| `scripts/phase6_import_seed.py` | Imports seed CSVs from `data/` (idempotent, dedupes) |

**Lead sourcing**
| Script | Purpose |
|---|---|
| `scripts/scrape_industries.py` | Volume scrape: verticals x regions (Bahrain/Saudi presets), imports with dedupe |
| `scripts/phase4_scrape_to_leads.py` | Single Google Maps query → preview → import |
| `scripts/scrape_instagram.py` · `ig_login.py` | Instagram lead sourcing (throwaway account) |
| `scripts/dedupe_leads.py` | Merge duplicate leads (phone/name match), keep the richest record |

**Outreach**
| Script | Purpose |
|---|---|
| `scripts/lib_outreach.py` | Single source of truth: pain points, lead score, WhatsApp/email copy (EN+AR) |
| `scripts/regenerate_outreach.py` | Refresh every lead's stored drafts/links from current templates |
| `scripts/outreach_setup.py` | Fill in outreach fields on leads missing them |
| `scripts/whatsapp_sender.py` | Human-in-the-loop WhatsApp queue sender (local web UI) |
| `scripts/send_emails.py` | Cold-email sender — dry-run default, any SMTP provider, EN+AR for Saudi leads |
| `scripts/scheduled_send_emails.py` | Cron/Task-Scheduler wrapper for `send_emails.py` — rate-limited, reachability-checked |

**Multi-instance**
| Script | Purpose |
|---|---|
| `scripts/export_leads.py` | Export this instance's Leads + Priority Leads to JSON |
| `scripts/import_leads.py` | Merge an export from another instance into this one, with dedupe |

## Security & compliance
- Secrets live only in `.env` (git-ignored). Never hardcode.
- App containers bind to `127.0.0.1`; Nginx is the sole public entry point.
- Seed/lead/migration data (phone numbers, contact notes) is **never
  committed**, regardless of whether this repo is public or private —
  collaborators with repo access still shouldn't need it in git history.
  Keep personal data to public business info per Bahrain PDPL / Saudi PDPL
  as applicable to the lead's country.
- Cold-email sending: ramp up volume gradually on a new sending account —
  providers (Zoho, Gmail, etc.) will flag/block a sender that jumps straight
  to high hourly volume, regardless of the provider's nominal rate limit.
