# Moving RAL CRM to another laptop

Everything is reproducible: the **code** lives in git, the **data** (leads,
views, dashboard, config, uploaded files) lives in the Docker volumes. Moving
machines = move the code + a one-shot data bundle.

## On the OLD machine
```bash
cd D:/CRM            # or wherever the repo is
bash scripts/export-workspace.sh
```
This creates `migration/ral-crm-export-<timestamp>.tar.gz` containing the
Postgres dump, Redis dump, uploaded files, and your `.env`.

> ⚠️ The bundle contains secrets **and** real lead phone numbers/notes. Keep it
> private (USB / encrypted transfer). It is git-ignored and must never be pushed.

## On the NEW machine
1. Install **Docker Desktop** (and Git).
2. Get the code and the bundle:
   ```bash
   git clone https://github.com/HishamGhareeb/CRM.git
   cd CRM
   # copy ral-crm-export-<timestamp>.tar.gz into ./migration/
   ```
3. Restore:
   ```bash
   bash scripts/import-workspace.sh migration/ral-crm-export-<timestamp>.tar.gz
   ```
   This restores `.env`, brings up Postgres/Redis, loads the dump, restores
   uploaded files, and starts the full stack.
4. Open http://localhost:3000 and log in — all your leads, views, dashboard,
   and the scraper are exactly as they were.

## Notes
- The scraper and its data come up with `docker compose up -d` automatically.
- `.env` carries your `TWENTY_API_KEY`; the phase scripts read it, so you can
  re-run any of them on the new machine unchanged.
- To instead move to the **Oracle server** (when capacity frees), follow the
  "Deploy to the server" steps in the [README](../README.md) and restore the
  same bundle there.
- Python 3 is needed only to re-run the helper scripts (`scripts/*.py`); the
  CRM itself needs only Docker.
