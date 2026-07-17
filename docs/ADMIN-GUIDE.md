# RAL CRM — Admin Guide

Day-to-day operations for the person running RAL CRM. Commands assume you're
in the project directory (`/opt/ral-crm` on the server, `D:\CRM` locally).

---

## 1. Logging in
- Local: http://localhost:3000
- Production: https://crm.raltech.dev
- Admin user: **Hisham Ghareeb** (hisham0ghareeb@gmail.com).

## 2. The views (left sidebar → Leads → view switcher)
| View | Use it for |
|---|---|
| **Pipeline (Kanban)** | Daily pipeline — drag a lead between stages |
| **Pipeline (List)** | Full active list, filter/sort/export to CSV |
| **Priority Leads** | Warm leads (Stage 3+), soonest follow-up first |
| **Overdue Follow-ups** | Follow-up date already passed, deal still open |
| **Inactive Leads** | Contacted/replied but gone quiet (oldest first) |
| **Re-engage Pool** | The 249 "not interested" leads to re-approach |

The **Notes / Log** column holds the imported notes (distinct from Twenty's
built-in Notes timeline on each record).

## 3. Adding users
Settings → **Members** → *Invite*. Enter the email (e.g. Suhaib) and pick a
role. Sales reps can be limited via role permissions in Settings → Roles.
After Suhaib joins, you can reassign the **Owner** field on leads (currently a
Hisham/Suhaib select).

## 4. Running the lead scraper
Scrape Google Maps and import results as Leads (dedupes against existing):
```bash
# preview only (no writes)
python scripts/phase4_scrape_to_leads.py "dental clinic Manama" --depth 1 --dry-run
# scrape deeper and import, owned by Hisham
python scripts/phase4_scrape_to_leads.py "cafe Adliya" --depth 2 --owner Hisham --import
```
- `--depth` raises how many results are scrolled (more = more leads, slower).
- Geo-target with `--lat --lon --radius` for "all X within N metres".
- Imported leads get **Source = Google Maps, Bucket = Active, Stage = 1**.
- The scraper UI is also at http://localhost:8080 (or behind the proxy).

> Keep scraping to **public business data** (name, public phone, website,
> public email) per Bahrain PDPL. Avoid LinkedIn bulk scraping.

**If the scraper fails with `could not install driver` / a CDN 404:**
Microsoft retired the standalone Playwright "driver" zip that gosom's Go
scraper fetches (Python/JS Playwright are unaffected — they bundle their
driver instead of fetching it separately), so every gosom image tag hits
a dead URL on first run. Fix once per fresh scraper container:
```bash
bash scripts/fix-scraper-driver.sh          # assembles the driver from
                                             # nodejs.org + npm instead
```
It persists in the `scraper-playwright` volume until that volume is
removed — re-run after recreating the container or bumping the image tag
(pinned in `docker-compose.yml`; check `docker compose logs scraper` for
the exact driver version it's asking for if this drifts).

## 5. Backups
- Automatic: daily 03:00 Postgres dump to `$BACKUP_DIR` (default
  `/opt/ral-crm/backups`), 14-day retention. Log: `/var/log/ral-crm-backup.log`.
- Manual backup now:
  ```bash
  bash scripts/backup-postgres.sh
  ```
- Restore a dump:
  ```bash
  gunzip -c backups/ral-crm-twenty-YYYYMMDD-HHMMSS.sql.gz \
    | docker compose exec -T db psql -U twenty twenty
  ```

## 6. Start / stop / update the stack
```bash
docker compose ps                 # status
docker compose stop               # stop (data persists in volumes)
docker compose start              # resume
docker compose logs -f server     # tail server logs (worker for email/automations)
docker compose pull && docker compose up -d   # update to newer Twenty images
```
> Before updating Twenty images in production, take a manual backup first.

## 7. Re-running the build scripts
All four `scripts/phase*.py` are **idempotent** — safe to re-run. They read
`TWENTY_URL` and `TWENTY_API_KEY` from `.env`. Use them to rebuild schema,
views, or re-import seed data on a fresh environment.

## 8. Dashboard & automations
Chart widgets and the two Workflow automations (stage-change → Activity log,
new-lead → email) are set up in the UI — see
[`PHASE5-dashboard-and-automations.md`](PHASE5-dashboard-and-automations.md).
The new-lead email needs SMTP configured in `.env` (`EMAIL_DRIVER=smtp` + creds);
locally it uses `logger`, which writes the email to `docker compose logs worker`.

## 9. Branding
Workspace name + logo: Settings → General. Accent colour: Settings →
Experience. Logo assets live in `brand/` (regenerate with
`python brand/generate-logos.py`).

---

### Contacts
- GM / Admin: Hisham Ghareeb — hisham0ghareeb@gmail.com — +973 3821 8181
- Developer: Suhaib (co-founder)
- Company: RAL Technologies — crm.raltech.dev — info@raltech.dev
