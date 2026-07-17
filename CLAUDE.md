# RAL Technologies CRM

## Stack
- Twenty CRM (self-hosted, Docker Compose, rebranded — stock `twentycrm/twenty`
  image, branding applied via Settings, not a frontend fork)
- gosom/google-maps-scraper (separate Docker service, REST API) — pinned to a
  specific tag, not `:latest` (see Known issues below)
- PostgreSQL + Redis (Twenty deps)
- Hosted on any standard Ubuntu 22.04/24.04 server, x86_64 or ARM64 (Twenty's
  images are multi-arch — no cloud-provider-specific setup). Default domain:
  crm.raltech.dev — override via `.env` / script args if deployed elsewhere.

## Brand
- Plum #2B1B3D / Lilac #D1C4E9 / Font Inter — RAL's actual brand palette
  (matches every RAL proposal/deck generator in the main workspace repo).
  Logo assets + generator: `brand/` (see `brand/generate-logos.py`).

## Rules
- Never hardcode secrets — .env only
- Lead ID format: RAL-PIP-XXXX, auto-increment from 0196
- Users: Hisham Ghareeb (Admin/GM), Suhaib (co-founder)
- Ask clarifying questions before large/irreversible changes (bulk sends,
  schema changes, deploys)

## What's built
- **Data model**: Lead, Priority Lead, Contact, Activity objects (`scripts/phase3_build_schema.py`,
  idempotent) — includes `Country` (Bahrain/Saudi Arabia/UAE/Kuwait/Qatar/Oman/Other)
  and dual-language `Email Draft` (English) + `Email Draft (Arabic)` fields.
- **Views & dashboard**: 7 pipeline views (`scripts/phase5_build_views.py`), dashboard + automations
  (see `docs/PHASE5-dashboard-and-automations.md`).
- **Lead sourcing — Google Maps scraper**: `scripts/scrape_industries.py` loops
  target verticals x region areas (Bahrain + Saudi Eastern Province presets in
  `REGIONS`), scrapes, classifies, scores, and imports as Leads with dedupe.
  `scripts/phase4_scrape_to_leads.py` is the single-query version.
  **Known issue**: the scraper's Playwright driver auto-download can break
  (Microsoft retired the artifact its Go library expects) — see
  `scripts/fix-scraper-driver.sh` and the note in `docs/ADMIN-GUIDE.md`.
- **Lead sourcing — Instagram scraper**: `scripts/scrape_instagram.py` +
  `scripts/ig_login.py` (throwaway account, rate-limited, session-cookie login
  to avoid repeated password auth).
- **Outreach engine** (`scripts/lib_outreach.py`, single source of truth):
  pain-point analysis, lead scoring, WhatsApp openers, and email drafts —
  English (`email_draft`) and Arabic (`email_draft_ar`, natural Gulf dialect,
  not a literal translation). `scripts/regenerate_outreach.py` refreshes all
  stored drafts/links from the current templates.
- **Cold email sending** (`scripts/send_emails.py`): dry-run by default,
  configurable SMTP (Zoho, Gmail, or any provider via `.env`), sends both
  English + Arabic to Saudi leads, one language to everyone else. `--limit`
  counts emails sent (not leads). Stops cleanly on a provider-side block
  instead of hammering a dead connection. `scripts/scheduled_send_emails.py`
  wraps it for hourly automation (Windows Task Scheduler locally; cron on the
  server) with a CRM-reachability check so a missed run just skips, not errors.
  **Ramp up sending volume slowly** — cold-email providers (Zoho included)
  will flag/block a new sender that jumps to a high hourly volume too fast.
- **Multi-instance lead merge** (`scripts/export_leads.py` / `import_leads.py`):
  export one instance's Leads + Priority Leads to JSON, import into another
  with dedupe (name + phone) and automatic enum sanitization for schema drift
  between instances.

## Repo layout
- `docker-compose.yml`         — Twenty stack (server, worker, db, redis, scraper)
- `.env.example`               — all config; copy to `.env` on server, never commit `.env`
- `nginx/`                     — reverse proxy site config
- `scripts/`                   — everything above, plus server bootstrap, SSL, backup
- `brand/`                     — RAL logo assets + generator (`generate-logos.py`)
- `data/` / `migration/`       — seed CSVs / cross-instance export bundles — **git-ignored** (PII)

## Contacts
- GM / Admin: Hisham Ghareeb — hisham0ghareeb@gmail.com — +973 3821 8181
- Developer: Suhaib (co-founder)
- Company: RAL Technologies — crm.raltech.dev — info@raltech.dev
