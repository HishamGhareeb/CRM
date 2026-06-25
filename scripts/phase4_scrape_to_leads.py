#!/usr/bin/env python3
"""
RAL CRM — Phase 4: Google Maps scraper -> Leads bridge.

Drives the gosom/google-maps-scraper REST API (web mode on :8080), then
maps results to Twenty Leads and imports them with dedupe. This is the
programmatic core of the "Scrape" workflow:
  enter business type + location -> scrape -> preview -> import as Leads.

(A native in-CRM Scrape *page* would require forking Twenty's frontend,
which this build deliberately avoids; this bridge + preview is the
equivalent, redeployable, and scriptable.)

Examples:
  # scrape + preview only (no writes)
  python scripts/phase4_scrape_to_leads.py "dental clinic Manama" --depth 1 --dry-run
  # scrape and import as Active leads owned by Hisham
  python scripts/phase4_scrape_to_leads.py "cafe Adliya" --depth 2 --owner Hisham --import
  # reuse an already-finished scraper job (skip scraping)
  python scripts/phase4_scrape_to_leads.py --job-id <uuid> --dry-run
"""
import argparse, csv, io, json, os, re, sys, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def load_env():
    env = dict(os.environ); p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); env.setdefault(k, v)
    return env
ENV = load_env()
TW_URL = ENV.get("TWENTY_URL", "http://localhost:3000").rstrip("/")
TOKEN = ENV.get("TWENTY_API_KEY")
SCRAPER = ENV.get("SCRAPER_URL", "http://localhost:8080").rstrip("/")

# ---------------- scraper API ----------------
def scraper_post(path, payload):
    req = urllib.request.Request(SCRAPER + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())

def scraper_get_json(path):
    return json.loads(urllib.request.urlopen(SCRAPER + path).read())

def scraper_download(job_id):
    req = urllib.request.Request(f"{SCRAPER}/api/v1/jobs/{job_id}/download")
    return urllib.request.urlopen(req).read().decode("utf-8", "replace")

def run_scrape(keywords, depth, max_time, lat, lon, radius, zoom):
    body = {"name": f"ral-{int(time.time())}", "keywords": keywords, "lang": "en",
            "depth": depth, "max_time": max_time, "email": True}
    if lat and lon:
        body.update({"lat": str(lat), "lon": str(lon), "zoom": zoom or 15})
    if radius: body["radius"] = radius
    job = scraper_post("/api/v1/jobs", body)
    jid = job["id"]
    print(f"  scraper job {jid} started; polling…")
    while True:
        time.sleep(6)
        jobs = scraper_get_json("/api/v1/jobs")
        st = next((j["Status"] for j in jobs if j["ID"] == jid), "unknown")
        print(f"    status={st}")
        if st != "working": break
    return jid

# ---------------- Twenty data API ----------------
def tw_gql(query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(f"{TW_URL}/graphql", data=body, headers={
        "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try: data = json.loads(urllib.request.urlopen(req).read())
    except urllib.error.HTTPError as e: data = json.loads(e.read())
    if "errors" in data: raise RuntimeError(json.dumps(data["errors"])[:400])
    return data["data"]

# ---------------- mapping ----------------
CATEGORY_RULES = [
    (("dental","clinic","medical","hospital","pharmac","doctor","physio","dermat","health"), "MEDICAL_HEALTH"),
    (("eye","optic","ophthalm"), "EYE_CLINIC"),
    (("cafe","coffee"), "CAFE"),
    (("restaurant","food","dining","shisha","bakery","catering"), "F_B_RESTAURANT"),
    (("gym","fitness","crossfit","yoga","boxing","martial"), "FITNESS_GYM"),
    (("academy","sport","tennis","swimming","football","basketball"), "SPORTS_ACADEMY"),
    (("real estate","property","properties","realtor"), "REAL_ESTATE"),
    (("salon","spa","beauty","barber","wellness","massage"), "BEAUTY_WELLNESS"),
    (("law","legal","advocate","attorney"), "LAW_FIRM"),
    (("hotel","resort","suites"), "HOTEL"),
    (("school","education","training","institute","tuition"), "EDUCATIONAL"),
    (("laundry","dry clean"), "LAUNDRY"),
    (("pest",), "PEST_CONTROL"),
    (("car","auto","garage","vehicle"), "CARS"),
    (("construction","contracting","contractor"), "CONSTRUCTION"),
    (("marketing","advertis","branding"), "MARKETING_AGENCY"),
    (("travel","tourism","tour"), "TRAVEL_TOURISM"),
]
def industry_from_category(cat):
    c = (cat or "").lower()
    for keys, enum in CATEGORY_RULES:
        if any(k in c for k in keys): return enum
    return "UNKNOWN"

def phone_input(raw):
    raw = (raw or "").strip()
    if not raw: return None
    s = raw.replace(" ", "")
    if s.startswith("+973"): return {"primaryPhoneNumber": s[4:], "primaryPhoneCallingCode":"+973","primaryPhoneCountryCode":"BH"}
    if s.startswith("+"):     return {"primaryPhoneNumber": s, "primaryPhoneCallingCode":"", "primaryPhoneCountryCode":""}
    return {"primaryPhoneNumber": s, "primaryPhoneCallingCode":"+973","primaryPhoneCountryCode":"BH"}

def digits(s): return re.sub(r"\D", "", s or "")

def build_lead(row, owner):
    notes = []
    if row.get("website"): notes.append(f"Web: {row['website']}")
    if row.get("emails"):  notes.append(f"Email: {row['emails']}")
    rc, rr = row.get("review_count"), row.get("review_rating")
    if rr: notes.append(f"Rating: {rr} ({rc or 0} reviews)")
    if row.get("address"): notes.append(row["address"])
    lead = {"name": (row.get("title") or "").strip(),
            "phone": phone_input(row.get("phone")),
            "source": "GOOGLE_MAPS", "bucket": "ACTIVE",
            "stage": "OPT_1_LEAD_IDENTIFIED",
            "industry": industry_from_category(row.get("category")),
            "notes": " | ".join(notes)}
    if owner: lead["owner"] = owner.upper()
    return {k: v for k, v in lead.items() if v not in (None, "")}

# ---------------- main ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="*", help="search keyword(s), e.g. 'dental clinic Manama'")
    ap.add_argument("--job-id", help="reuse an existing finished scraper job")
    ap.add_argument("--depth", type=int, default=1)
    ap.add_argument("--max-time", type=int, default=300, help="seconds")
    ap.add_argument("--lat", type=float); ap.add_argument("--lon", type=float)
    ap.add_argument("--radius", type=int); ap.add_argument("--zoom", type=int)
    ap.add_argument("--owner", choices=["Hisham","Suhaib"])
    ap.add_argument("--import", dest="do_import", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not TOKEN: sys.exit("ERROR: TWENTY_API_KEY not set")

    if a.job_id:
        jid = a.job_id
    else:
        if not a.query: sys.exit("provide a search query or --job-id")
        jid = run_scrape([" ".join(a.query)], a.depth, a.max_time*1_000_000_000,
                         a.lat, a.lon, a.radius, a.zoom)

    rows = list(csv.DictReader(io.StringIO(scraper_download(jid))))
    leads = [build_lead(r, a.owner) for r in rows if (r.get("title") or "").strip()]
    print(f"\nScraped {len(rows)} places -> {len(leads)} candidate leads")

    # dedupe within batch + against existing Leads
    existing = tw_gql("query{leads(first:1000){edges{node{name phone{primaryPhoneNumber}}}}}")["leads"]["edges"]
    seen = {(n["node"]["name"].lower(), digits((n["node"].get("phone") or {}).get("primaryPhoneNumber"))) for n in existing}
    fresh, dropped = [], 0
    for l in leads:
        key = (l["name"].lower(), digits((l.get("phone") or {}).get("primaryPhoneNumber")))
        if key in seen: dropped += 1; continue
        seen.add(key); fresh.append(l)
    print(f"After dedupe vs existing: {len(fresh)} new ({dropped} already in CRM)")

    print("\nPreview (first 10):")
    for l in fresh[:10]:
        ph = (l.get("phone") or {}).get("primaryPhoneNumber","-")
        print(f"  - {l['name']:<38} {l.get('industry','-'):<16} {ph}")

    if a.dry_run or not a.do_import:
        print("\n[preview only] re-run with --import to write these leads.")
        return
    for i in range(0, len(fresh), 40):
        tw_gql("mutation($d:[LeadCreateInput]!){createLeads(data:$d){id}}", {"d": fresh[i:i+40]})
    print(f"\nImported {len(fresh)} leads (source Google Maps, bucket Active, stage 1).")

if __name__ == "__main__":
    main()
