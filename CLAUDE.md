# RAL Technologies CRM

## Stack
- Twenty CRM (self-hosted, Docker Compose, forked + rebranded)
- gosom/google-maps-scraper (separate Docker service, REST API)
- PostgreSQL + Redis (Twenty deps)
- React/TypeScript frontend, NestJS backend
- Deployed on Oracle Cloud Free Tier (Ubuntu 24.04 ARM) at crm.raltech.dev

## Brand
- Plum #2B1B3D / Lilac #D1C4E9 / Font Inter — RAL's actual brand palette
  (matches every RAL proposal/deck generator in the main workspace repo).
  Logo assets + generator: `brand/` (see `brand/generate-logos.py`).

## Rules
- Never hardcode secrets — .env only
- Lead ID format: RAL-PIP-XXXX, auto-increment from 0196
- One user at launch: Hisham Ghareeb (Admin). Suhaib (Sales Rep) added later.
- Build order: infra → CRM fork+rebrand → data model → scraper integration → views → seed import
- Ask clarifying questions before each phase

## Build phases
- **Phase 1** — Base infrastructure: Docker, Nginx reverse proxy + Let's Encrypt SSL, daily Postgres backup cron. (this repo holds it as IaC)
- **Phase 2** — Twenty CRM deploy + rebrand to "RAL CRM" (logo, theme, font)
- **Phase 3** — Data model: Lead, Priority Lead, Contact, Activity objects + select options
- **Phase 4** — Scraper integration (gosom google-maps-scraper) + in-CRM Scrape page
- **Phase 5** — Views, dashboard, automations
- **Phase 6** — Seed data import (97 pipeline + 16 priority + 249 re-engage = 362 records)
- **Phase 7** — Handover docs + backup verification

## Repo layout
- `docker-compose.yml`         — Twenty stack (server, worker, db, redis)
- `.env.example`               — all config; copy to `.env` on server, never commit `.env`
- `nginx/`                     — reverse proxy site config
- `scripts/`                   — server bootstrap, SSL, backup
- `data/`                      — seed CSVs (added in Phase 6)

## Contacts
- GM / Admin: Hisham Ghareeb — hisham0ghareeb@gmail.com — +973 3821 8181
- Developer: Suhaib (co-founder)
- Company: RAL Technologies — crm.raltech.dev — info@raltech.dev
