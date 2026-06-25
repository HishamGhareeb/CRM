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

A **RAL Dashboard** record is created (appears under *Dashboards* in the sidebar).
Twenty builds dashboard charts through its visual widget editor; the per-widget
config isn't reliably scriptable across versions, so add these widgets in the UI
(**Dashboards → RAL Dashboard → Edit → Add widget**). Recommended widgets:

| Widget | Type | Source / config |
|---|---|---|
| Active Leads | Number | Leads, count, filter Bucket = Active |
| Warm Leads (Stage 3+) | Number | Leads, count, filter Stage in 3–7 |
| Deals Won | Number | Leads, count, filter Stage = 7 |
| Revenue Won (BHD) | Number | Leads, sum of Est. Deal, filter Stage = 7 |
| Pipeline by Stage | Bar | Leads grouped by Stage (Active) |
| Leads by Industry | Bar | Leads grouped by Industry |
| Leads by Owner | Bar/Pie | Leads grouped by Owner |
| Re-engage pool | Number | Leads, count, filter Bucket = Re-engage |

**Live metric snapshot at build time** (sanity check the widgets against these):
- Active Leads: **111**  (97 seed + 14 scraped)
- Re-engage pool: **249**
- Warm (Stage 3+): **23**
- Deals Won: **0**

Quick recompute any metric from the API:
```bash
TOKEN=$(grep ^TWENTY_API_KEY= .env | cut -d= -f2-)
curl -s -X POST http://localhost:3000/graphql -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"query{leads(first:0,filter:{bucket:{in:[ACTIVE]}}){totalCount}}"}'
```

---

## Automations #2 & #3 (Twenty Workflows)

These two need Twenty's **Workflow** builder (and #3 needs SMTP). Build under
**Settings → Workflows → New workflow** (or the *Workflows* sidebar item).

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
