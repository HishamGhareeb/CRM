# Phase 5 — Views, Dashboard & Automations

## What's built automatically (via `scripts/phase5_build_views.py`)

Six Lead views, created idempotently through the metadata API:

| View | Type | Filter | Sort |
|---|---|---|---|
| **Pipeline (Kanban)** | Kanban by Stage | Bucket = Active | — |
| **Pipeline (List)** | Table | Bucket = Active | Last Contact ↓ |
| **Priority Leads** | Table | Stage 3–7 | Next Follow-up ↑ |
| **Re-engage Pool** | Table | Bucket = Re-engage | Last Contact ↑ |
| **Overdue Follow-ups** | Table | Next Follow-up in past **and** Stage 1–6 | Next Follow-up ↑ |
| **Inactive Leads** | Table | Last Contact in past **and** Stage 2–3 | Last Contact ↑ (oldest first) |

The last two **are** automation rules #1 (overdue follow-up) and #4 (inactivity
alert) from the brief — expressed as live filtered views, which is how the brief
frames them ("red flag in list view", "surface in Priority view"). To make
overdue rows visually red: open *Overdue Follow-ups* → the Stage chips already
colour-code; optionally add a conditional format on Next Follow-up in the UI.

---

## Dashboard

Built automatically by **`scripts/phase5_build_dashboard.py`** — creates a
DASHBOARD page layout with an *Overview* tab and 8 GRAPH widgets, then links it
to the **RAL Dashboard** record (sidebar → *Dashboards*). Re-running is a no-op
while the layout exists; to rebuild, destroy the "RAL Dashboard Layout" page
layout and re-run.

| Widget | Type | Config |
|---|---|---|
| Active Leads | Number | count, filter Bucket = Active |
| Warm Leads (3+) | Number | count, filter Stage 3–7 |
| Re-engage Pool | Number | count, filter Bucket = Re-engage |
| Deals Won | Number | count, filter Stage = 7 |
| Pipeline by Stage | Bar | count grouped by Stage (Active) |
| Leads by Bucket | Pie | count grouped by Bucket |
| Leads by Industry | Bar | count grouped by Industry |
| Leads by Owner | Pie | count grouped by Owner |

To add more (e.g. Revenue Won = SUM of Est. Deal filtered to Stage 7), either
extend the script or use **RAL Dashboard → Edit → Add widget** in the UI.

**Live metric snapshot at build time:** Active **111**, Re-engage **249**,
Warm (3+) **23**, Deals Won **0**.

---

## Automations #2 & #3 (Twenty Workflows)

> **API note:** unlike the objects/fields/views/dashboard (all built via the
> metadata API), **workflows can't be created via the API** — Twenty returns
> "Method not allowed" on `createWorkflowVersions` for API keys and exposes no
> builder mutations. They must be built in the in-app **Workflow** builder.
> #3 additionally needs a **connected email account** (the Send Email action
> sends from a connected Gmail/SMTP account, not just `EMAIL_DRIVER`).

Build under the **Workflows** sidebar item → **New workflow**.

### #2 — Stage change → log an Activity
1. Trigger: **Record is updated** → Object **Lead** → watch field **Stage**.
2. Action: **Create Record** → Object **Activity** with:
   - Type = `Note`
   - Summary = `Stage changed to {{stage}}` (use the record variable)
   - Linked Lead = the triggering record
   - Date = now
3. Activate.

### #3 — New lead → email Hisham
> Requires SMTP. In `.env` set `EMAIL_DRIVER=smtp` plus `EMAIL_SMTP_HOST/PORT/USER/PASSWORD`
> and `EMAIL_FROM_ADDRESS`, then `docker compose up -d server worker`.
> (Locally we run `EMAIL_DRIVER=logger`, so the email is written to the worker
> logs instead of actually sent — fine for testing.)

1. Trigger: **Record is created** → Object **Lead**.
2. Action: **Send Email** → To `hisham0ghareeb@gmail.com`,
   Subject `New lead: {{name}}`, body with `{{industry}}`, `{{source}}`, `{{phone}}`.
3. Activate.

To watch the logged email locally: `docker compose logs -f worker`.
