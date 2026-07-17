# RAL CRM — Project Overview (catch-up)

A self-hosted, branded CRM for RAL Technologies built on Twenty CRM, with a
Google-Maps lead-scraping + enrichment + outreach machine on top. Runs locally
on Docker today; deploys unchanged to any standard Ubuntu server (x86_64 or
ARM — Twenty's images are multi-arch).

## What was built, in order

### Core CRM (phases 1–7)
1. **Infrastructure as code** — Docker Compose stack (Twenty server/worker,
   Postgres, Redis), Nginx + Let's Encrypt config, daily Postgres backup cron.
2. **Branding** — workspace renamed RAL CRM, logo, theme.
3. **Data model** — Lead, Priority Lead, Contact, Activity objects with all
   fields, select options, and Contact/Activity→Lead relations (built via the
   metadata API, reproducible).
4. **Scraper** — gosom/google-maps-scraper as a second container + a bridge
   that imports scraped businesses as Leads.
5. **Views, dashboard, automations** — 7 views; an 8-widget dashboard built via
   API; overdue/inactivity rules as live views (workflow note below).
6. **Seed import** — 362 real records (97 active + 249 re-engage + 16 priority).
7. **Handover docs** — README, admin guide, migration guide.

### Outreach machine
- **Offer angles** filled per vertical for every lead (existing ones preserved).
- **One-click WhatsApp** links (`wa.me`) with a playbook-aligned opener,
  personalised per vertical + sender. Human clicks to send (ban-safe, PDPL-ok).
- **Outreach engine** (`lib_outreach.py`) — turns business signals (website
  presence, rating, reviews) into **pain points**, a **lead score (0–100)**
  weighted by RAL's priority verticals, a personalised opener, and a cold
  **email draft** in proposal tone. All grounded in the RAL Sales Playbook,
  Discovery Script, Proposal, and vertical decks (read from Drive).
- **Volume scraping** (`scrape_industries.py`) — loops the decked verticals ×
  Bahrain areas, scrapes, enriches, dedupes, imports, and logs findings.

### Three new features (chosen + built autonomously)
1. **Lead scoring + Hot Leads view** — prioritise outreach by fit score; no
   website + decent reviews + priority vertical ranks highest.
2. **Outreach status + controlled email sender** (`send_emails.py`) — dry-run
   by default, Gmail App Password to send, hard cap 40/run, ~6s spacing, opt-out
   line; marks Email Sent / Contacted / Last Contact and ranks by score.
3. **Dedupe / hygiene tool** (`dedupe_leads.py`) — merges duplicate leads
   (by phone, then name), keeping the richest record.

### Migration
- `export-workspace.sh` / `import-workspace.sh` + `docs/MIGRATION.md` — one
  bundle (DB + Redis + files + .env) moves the whole CRM to another laptop or
  the server.

## Current data snapshot
- ~427 leads and growing (scrape running): 178 Active, 249 Re-engage.
- 309 from Google Maps; ~45 with **no website** (prime entry-package targets);
  ~59 scored ≥ 70.
- 16 Priority Leads.

## Known limitations (deliberate, documented)
- **Email auto-send** is gated on a Gmail App Password and capped — mass cold
  email from a personal Gmail would get it suspended; send in small warm-up
  batches via `send_emails.py --send`.
- **Workflows** (stage-change log, new-lead email) must be built in Twenty's UI
  builder — the API forbids workflow creation. See
  `PHASE5-dashboard-and-automations.md`.
- **Instagram scraping** skipped — no legitimate API, high ban risk; enrichment
  uses business websites instead.

## How to operate (cheat-sheet)
```bash
# scrape more volume (decked verticals, 100 each)
python scripts/scrape_industries.py --target 100
# clean duplicates
python scripts/dedupe_leads.py --apply
# re-fill angles + WhatsApp links on any leads missing them
python scripts/outreach_setup.py
# preview / send cold emails (top by score)
python scripts/send_emails.py --limit 10 --min-score 70           # dry-run
python scripts/send_emails.py --limit 10 --min-score 70 --send    # needs Gmail App Password in .env
# back up to move machines
bash scripts/export-workspace.sh
```
Day-to-day usage: see `ADMIN-GUIDE.md`.
