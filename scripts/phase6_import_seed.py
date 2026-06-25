#!/usr/bin/env python3
"""
RAL CRM — Phase 6: import seed data via Twenty's data API.

Imports:
  data/pipeline.csv  (97)  -> Lead   (bucket Active)
  data/reengage.csv  (249) -> Lead   (bucket Re-engage)
  data/priority.csv  (16)  -> PriorityLead

Idempotent: skips records already present (Leads keyed on leadId, falling
back to name+phone; PriorityLeads keyed on priorityId). Safe to re-run.
Dedupes leads within the seed set on company name + phone digits.

Usage:
    python scripts/phase6_import_seed.py            # import
    python scripts/phase6_import_seed.py --dry-run  # parse + map only, no writes

CSVs are git-ignored (real contact PII; public repo / PDPL).
"""
import csv, json, os, re, sys, urllib.request, urllib.error

DRY = "--dry-run" in sys.argv
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")

def load_env():
    env = dict(os.environ)
    p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); env.setdefault(k, v)
    return env

ENV = load_env()
URL = ENV.get("TWENTY_URL", "http://localhost:3000").rstrip("/")
TOKEN = ENV.get("TWENTY_API_KEY") or sys.exit("ERROR: TWENTY_API_KEY not set")
GQL = f"{URL}/graphql"

def gql(query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(GQL, data=body, headers={
        "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        data = json.loads(urllib.request.urlopen(req).read())
    except urllib.error.HTTPError as e:
        data = json.loads(e.read())
    if "errors" in data:
        raise RuntimeError(json.dumps(data["errors"])[:600])
    return data["data"]

# ------------------------------------------------------------- mappers
def norm(s):
    c = "".join(ch if ch.isalnum() else "_" for ch in (s or "").upper()).strip("_")
    while "__" in c: c = c.replace("__", "_")
    return c

INDUSTRY_ENUM = {'MEDICAL_HEALTH','FITNESS_GYM','F_B_RESTAURANT','CAFE','REAL_ESTATE',
 'SPORTS_ACADEMY','BEAUTY_WELLNESS','EDUCATIONAL','LAW_FIRM','CONSTRUCTION','MARKETING_AGENCY',
 'MEDIA_AGENCY','HOTEL','LAUNDRY','PEST_CONTROL','CARS','FRAGRANCE_STORE','ENTERTAINMENT',
 'TOURISM','FOOD_INDUSTRY','CLOUD_BASED_POS','EYE_CLINIC','FLOORING_WALL_PANELS','HENNA','AC',
 'MOVING_COMPANY','CAMPS','HOSPITALITY','MULTI_SECTOR','FACILITIES_MANAGEMENT','TRAVEL_TOURISM',
 'CONSULTANCY','TECHNOLOGY','ELECTRONICS_RETAIL','PUBLIC_RELATIONS_PR','HOME_INTERIOR',
 'MANPOWER','UNKNOWN'}
INDUSTRY_ALIAS = {'MEDICAL':'MEDICAL_HEALTH','MEDICAL_CLINICS':'MEDICAL_HEALTH',
 'EDUCATION':'EDUCATIONAL','PROFESSIONAL_SERVICES':'CONSULTANCY','OTHER':'UNKNOWN',
 'TENNIS_ACADEMY':'SPORTS_ACADEMY','EVENT_MANAGEMENT_MARKETING':'MARKETING_AGENCY'}
SOURCE_ENUM = {'PHONE','INSTAGRAM','GOOGLE','LINKEDIN','WHATSAPP','GOOGLE_MAPS','CONTACT',
 'SOCIAL_MEDIA','UNKNOWN'}
SOURCE_ALIAS = {'WHATSAPP_INSTAGRAM':'WHATSAPP','WHATSAPP_INSTAGRAM_':'WHATSAPP'}

warns = []
def industry(label):
    if not label.strip(): return None
    n = norm(label)
    if n in INDUSTRY_ENUM: return n
    if n in INDUSTRY_ALIAS: return INDUSTRY_ALIAS[n]
    warns.append(f"industry '{label}' -> UNKNOWN"); return "UNKNOWN"

def source(label):
    if not label.strip(): return "UNKNOWN"
    n = norm(label)
    if n in SOURCE_ENUM: return n
    if n in SOURCE_ALIAS: return SOURCE_ALIAS[n]
    warns.append(f"source '{label}' -> UNKNOWN"); return "UNKNOWN"

def stage(label):
    if not label.strip(): return None
    return "OPT_" + norm(label)            # e.g. "3 - Replied" -> OPT_3_REPLIED

def bucket(label):
    return {"ACTIVE":"ACTIVE","RE_ENGAGE":"RE_ENGAGE","CLOSED":"CLOSED"}.get(norm(label), "ACTIVE")

def owner(label):
    n = norm(label)
    return n if n in ("HISHAM","SUHAIB") else None

def phone(raw):
    raw = (raw or "").strip()
    if not raw: return None
    s = raw.replace(" ", "")
    for cc, country in (("+973","BH"),("+971","AE"),("+966","SA")):
        if s.startswith(cc):
            return {"primaryPhoneNumber": s[len(cc):], "primaryPhoneCallingCode": cc,
                    "primaryPhoneCountryCode": country}
    if s.startswith("971"):
        return {"primaryPhoneNumber": s[3:], "primaryPhoneCallingCode":"+971","primaryPhoneCountryCode":"AE"}
    if s.startswith("+"):
        return {"primaryPhoneNumber": s, "primaryPhoneCallingCode":"", "primaryPhoneCountryCode":""}
    return {"primaryPhoneNumber": s, "primaryPhoneCallingCode":"+973", "primaryPhoneCountryCode":"BH"}

def currency(raw):
    raw = (raw or "").strip()
    if raw == "": return None
    try: amt = float(raw)
    except ValueError: return None
    return {"amountMicros": int(round(amt * 1_000_000)), "currencyCode": "BHD"}

def date(raw):
    raw = (raw or "").strip()
    return raw if re.match(r"^\d{4}-\d{2}-\d{2}$", raw) else None

def phone_digits(raw):
    return re.sub(r"\D", "", raw or "")

def clean(d):
    return {k: v for k, v in d.items() if v not in (None, "")}

def read_csv(name):
    return list(csv.DictReader(open(os.path.join(DATA, name), encoding="utf-8")))

# ------------------------------------------------------------- build payloads
def build_leads():
    seen = set(); out = []
    def add(row, b, src_col, status_to_notes=False):
        name = row["Company Name"].strip()
        ph = phone(row.get("Phone",""))
        key = (name.lower(), phone_digits(row.get("Phone","")))
        if key in seen:
            warns.append(f"dup lead skipped: {name}"); return
        seen.add(key)
        notes = (row.get("Notes","") or "").strip()
        if status_to_notes and row.get("Status","").strip():
            notes = (f"Status: {row['Status'].strip()}" + (f" | {notes}" if notes else ""))
        out.append(clean({
            "name": name,
            "leadId": (row.get("Lead ID","") or "").strip(),
            "industry": industry(row.get("Industry","")),
            "phone": ph,
            "source": source(row.get(src_col,"")),
            "stage": stage(row.get("Stage","")),
            "bucket": b,
            "owner": owner(row.get("Owner","")),
            "estDeal": currency(row.get("Est Deal (BHD)","")),
            "lastContact": date(row.get("Last Contact","")),
            "nextFollowup": date(row.get("Next Followup","")),
            "notes": notes,
            "offerAngle": (row.get("Offer Angle","") or "").strip(),
        }))
    for r in read_csv("pipeline.csv"): add(r, "ACTIVE", "Source")
    for r in read_csv("reengage.csv"): add(r, "RE_ENGAGE", "Source", status_to_notes=True)
    return out

def build_priority():
    out = []
    for r in read_csv("priority.csv"):
        out.append(clean({
            "name": r["Company Name"].strip(),
            "priorityId": (r.get("Priority ID","") or "").strip(),
            "phone": phone(r.get("Phone","")),
            "contactName": (r.get("Contact","") or "").strip(),
            "industry": industry(r.get("Industry","")),
            "stage": stage(r.get("Stage","")),
            "nextAction": (r.get("Notes","") or "").strip(),
            "estDeal": currency(r.get("Est Deal (BHD)","")),
            "owner": owner(r.get("Owner","")),
        }))
    return out

# ------------------------------------------------------------- existing (idempotency)
def existing_keys(plural, fields):
    """Return set of identifying keys already in the workspace."""
    q = "query{" + plural + "(first:500){edges{node{" + fields + "}}}}"
    edges = gql(q)[plural]["edges"]
    return [e["node"] for e in edges]

def batched_create(mutation, items, label):
    if DRY:
        print(f"  [dry-run] would create {len(items)} {label}"); return 0
    created = 0
    for i in range(0, len(items), 40):
        chunk = items[i:i+40]
        gql(f"mutation($data:[{mutation}]!){{create{mutation.replace('CreateInput','s')}(data:$data){{id}}}}",
            {"data": chunk})
        created += len(chunk)
        print(f"  …{created}/{len(items)} {label}")
    return created

def main():
    leads = build_leads()
    prio = build_priority()
    print(f"Parsed: {len(leads)} leads (after dedupe), {len(prio)} priority leads")

    # idempotency: skip existing
    lead_nodes = existing_keys("leads", "leadId name") if not DRY else []
    have_leadids = {n["leadId"] for n in lead_nodes if n.get("leadId")}
    have_names = {n["name"] for n in lead_nodes}
    leads = [l for l in leads if l.get("leadId","") not in have_leadids
             and not (not l.get("leadId") and l["name"] in have_names)]

    prio_nodes = existing_keys("priorityLeads", "priorityId") if not DRY else []
    have_prio = {n["priorityId"] for n in prio_nodes if n.get("priorityId")}
    prio = [p for p in prio if p.get("priorityId","") not in have_prio]

    print(f"To import (new only): {len(leads)} leads, {len(prio)} priority leads")
    batched_create("LeadCreateInput", leads, "leads")
    batched_create("PriorityLeadCreateInput", prio, "priority leads")

    if warns:
        print(f"\n{len(warns)} mapping notes (first 20):")
        for w in warns[:20]: print(f"  - {w}")

    if not DRY:
        n_lead = gql("query{leads(first:0){totalCount}}")["leads"]["totalCount"]
        n_prio = gql("query{priorityLeads(first:0){totalCount}}")["priorityLeads"]["totalCount"]
        n_active = gql('query{leads(first:0,filter:{bucket:{eq:ACTIVE}}){totalCount}}')["leads"]["totalCount"]
        n_re = gql('query{leads(first:0,filter:{bucket:{eq:RE_ENGAGE}}){totalCount}}')["leads"]["totalCount"]
        print(f"\nVerify — Leads total: {n_lead} (Active {n_active}, Re-engage {n_re}); PriorityLeads: {n_prio}")

if __name__ == "__main__":
    main()
