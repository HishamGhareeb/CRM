#!/usr/bin/env python3
"""
RAL CRM — volume scraping machine.

Loops the decked verticals x Bahrain areas, scrapes Google Maps, enriches each
business (pain points, lead score, has-website, personalised WhatsApp opener +
email draft via lib_outreach), dedupes, and imports as Leads. Writes running
findings to docs/scrape-findings.md.

Usage:
  python scripts/scrape_industries.py                  # all verticals, per-industry defaults
  python scripts/scrape_industries.py --target 100 --depth 10   # uniform override
  python scripts/scrape_industries.py --only MEDICAL_HEALTH,FITNESS_GYM
"""
import argparse, csv, io, json, os, sys, time, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_outreach as L

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def load_env():
    env = dict(os.environ); p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line=line.strip()
            if line and not line.startswith("#") and "=" in line:
                k,v=line.split("=",1); env.setdefault(k,v)
    return env
ENV=load_env()
TW=ENV.get("TWENTY_URL","http://localhost:3000").rstrip("/")
TOKEN=ENV.get("TWENTY_API_KEY") or sys.exit("TWENTY_API_KEY not set")
SCRAPER=ENV.get("SCRAPER_URL","http://localhost:8080").rstrip("/")
OWNER="HISHAM"

def tw(q,v=None):
    body=json.dumps({"query":q,"variables":v or {}}).encode()
    r=urllib.request.Request(f"{TW}/graphql",data=body,headers={"Authorization":f"Bearer {TOKEN}","Content-Type":"application/json"})
    try: d=json.loads(urllib.request.urlopen(r).read())
    except urllib.error.HTTPError as e: d=json.loads(e.read())
    if "errors" in d: raise RuntimeError(json.dumps(d["errors"])[:300])
    return d["data"]

def sc_post(path,payload):
    r=urllib.request.Request(SCRAPER+path,data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(r).read())
def sc_get(path):
    return json.loads(urllib.request.urlopen(SCRAPER+path).read())
def sc_dl(jid):
    return urllib.request.urlopen(f"{SCRAPER}/api/v1/jobs/{jid}/download").read().decode("utf-8","replace")

INDUSTRIES={
 # medical first and broadest (user priority)
 "MEDICAL_HEALTH":["medical center","dental clinic","medical clinic","polyclinic",
   "specialist clinic","dermatology clinic","skin clinic","physiotherapy clinic",
   "ENT clinic","orthopedic clinic","pediatric clinic","gynecology clinic","eye clinic"],
 "SPORTS_ACADEMY":["sports academy","football academy","swimming academy","tennis academy","martial arts academy"],
 "FITNESS_GYM":["gym","fitness center","ladies gym","crossfit"],
 "BEAUTY_WELLNESS":["beauty salon","spa","ladies salon","skin care clinic"],
 "EDUCATIONAL":["private school","nursery","training institute"],
 "REAL_ESTATE":["real estate"],
 # F&B deliberately excluded from the volume-scraping targets (RAL priority call).
}
# Region presets: search areas + phone/country defaults for each market RAL scrapes.
REGIONS={
 "BAHRAIN":{"country":"BAHRAIN","calling_code":"+973","country_code":"BH",
   "areas":["Manama","Riffa","Seef","Muharraq","Saar","Budaiya","Isa Town","Hamad Town",
            "Sitra","Adliya","Juffair","Amwaj"]},
 "SAUDI_EASTERN":{"country":"SAUDI_ARABIA","calling_code":"+966","country_code":"SA",
   "areas":["Dammam","Al Khobar","Dhahran","Jubail","Qatif","Al-Ahsa","Hofuf",
            "Ras Tanura","Khafji","Saihat","Safwa"]},
}

# Per-industry lead targets, used when --target isn't passed explicitly.
# Medical is RAL's top priority vertical -> double the rest.
DEFAULT_TARGET=25
TARGET_OVERRIDES={"MEDICAL_HEALTH":50}

def phone_input(raw,calling_code,country_code):
    raw=(raw or "").strip().replace(" ","")
    if not raw: return None
    if raw.startswith(calling_code): return {"primaryPhoneNumber":raw[len(calling_code):],"primaryPhoneCallingCode":calling_code,"primaryPhoneCountryCode":country_code}
    if raw.startswith("+"): return {"primaryPhoneNumber":raw,"primaryPhoneCallingCode":"","primaryPhoneCountryCode":""}
    return {"primaryPhoneNumber":raw,"primaryPhoneCallingCode":calling_code,"primaryPhoneCountryCode":country_code}
def digits(s):
    import re; return re.sub(r"\D","",s or "")

def build_lead(row, search_industry, region):
    name=(row.get("title") or "").strip()
    if not name: return None
    # classify by the business's real Google category/name, not the search term
    industry=L.classify(row.get("category"), name, fallback=search_industry)
    website=(row.get("website") or "").strip()
    rating=row.get("review_rating"); rc=row.get("review_count")
    pains,has_site,score,obs=L.analyze(industry,website,rating,rc)
    emails=[e.strip() for e in (row.get("emails") or "").split(",") if L.valid_email(e.strip())]
    ph=phone_input(row.get("phone"),region["calling_code"],region["country_code"])
    lead={"name":name,"industry":industry,"source":"GOOGLE_MAPS","bucket":"ACTIVE",
          "stage":"OPT_1_LEAD_IDENTIFIED","owner":OWNER,"country":region["country"],
          "fullAddress":(row.get("address") or row.get("complete_address") or "").strip(),
          "painPoints":" | ".join(pains),"leadScore":score,"hasWebsite":has_site.upper(),
          "offerAngle":L.V.get(industry,L.DEFAULT)[2]}
    note=["Source: Google Maps.", "Website: "+("yes" if has_site else "NO")]
    if rating: note.append(f"Rating {rating} ({rc or 0} reviews)")
    if pains: note.append("Pain: "+" | ".join(pains))
    if (row.get("address") or "").strip(): note.append(row["address"].strip())
    # Deep-dive fields the scraper visits each business's detail page for —
    # no dedicated columns for these yet, so they ride in Notes.
    if (row.get("open_hours") or "").strip(): note.append("Hours: "+row["open_hours"].strip()[:200])
    if (row.get("price_range") or "").strip(): note.append("Price range: "+row["price_range"].strip())
    if (row.get("credit_cards_accepted") or "").strip():
        note.append("Cards accepted: "+row["credit_cards_accepted"].strip())
    about=(row.get("about") or row.get("descriptions") or "").strip()
    if about: note.append("About: "+about[:300])
    lead["notes"]=" | ".join(note)
    if website: lead["website"]={"primaryLinkUrl":website,"primaryLinkLabel":"Website"}
    if emails: lead["email"]={"primaryEmail":emails[0],"additionalEmails":emails[1:]}
    if rating:
        try: lead["rating"]=float(rating)
        except: pass
    if rc:
        try: lead["reviewCount"]=float(rc)
        except: pass
    if ph:
        lead["phone"]=ph
        wl=L.whatsapp_link(name,industry,OWNER,ph["primaryPhoneNumber"],ph["primaryPhoneCallingCode"],has_site.upper())
        if wl: lead["whatsappLink"]={"primaryLinkUrl":wl,"primaryLinkLabel":"Message on WhatsApp"}
    subj,bdy=L.email_draft(name,industry,OWNER,has_site.upper())
    lead["emailDraft"]=f"Subject: {subj}\n\n{bdy}"
    subj_ar,bdy_ar=L.email_draft_ar(name,industry,OWNER,has_site.upper())
    lead["emailDraftAr"]=f"Subject: {subj_ar}\n\n{bdy_ar}"
    return {k:v for k,v in lead.items() if v not in (None,"",[])}

def run_job(term,area,depth,max_time):
    # fast_mode=True was tried and rejected: it skips the email-crawl step
    # entirely (confirmed empirically -- zero email jobs fired even with
    # email:True), so it can't deliver what's actually wanted (name/email/
    # phone). email discovery requires the slower per-place path; the real
    # lever for speed is `depth` (fewer results found -> fewer slow website
    # visits), not fast_mode.
    job=sc_post("/api/v1/jobs",{"name":f"{term}-{area}","keywords":[f"{term} {area}"],"lang":"en","depth":depth,"fast_mode":False,"max_time":max_time*1_000_000_000,"email":True})
    jid=job["id"]
    waited=0
    st="pending"
    patience=max_time+600
    while waited<patience:
        time.sleep(8); waited+=8
        st=next((j["Status"] for j in sc_get("/api/v1/jobs") if j["ID"]==jid),"unknown")
        if st not in ("working","pending"): break   # wait through the queue, not just 'working'
    if st!="ok":
        print(f"    job ended status={st} after {waited}s (patience {patience}s), skipping",flush=True); return []
    try: return list(csv.DictReader(io.StringIO(sc_dl(jid))))
    except Exception as e: print(f"    download failed: {e}",flush=True); return []

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--target",type=int,default=None,
        help="uniform target for every industry; 0 = unlimited (scrape every area/term); "
             f"omit to use per-industry defaults (medical={TARGET_OVERRIDES['MEDICAL_HEALTH']}, others={DEFAULT_TARGET})")
    ap.add_argument("--depth",type=int,default=3,
        help="Google Maps result-page scroll depth; lower = fewer results found "
             "= fewer slow per-site email-crawl visits (was 10, cut for speed)")
    ap.add_argument("--max-time",type=int,default=900,
        help="per-job scraper time budget in seconds; deep-dive jobs on popular "
             "categories (schools, clinics) have taken 12-20 min in practice")
    ap.add_argument("--only",default="")
    ap.add_argument("--skip-areas",default="",help="comma list of areas to skip (already covered)")
    ap.add_argument("--region",choices=sorted(REGIONS),default="BAHRAIN")
    a=ap.parse_args()
    only=set(x.strip() for x in a.only.split(",") if x.strip())
    skip_areas=set(x.strip().lower() for x in a.skip_areas.split(",") if x.strip())
    region=REGIONS[a.region]
    areas=[ar for ar in region["areas"] if ar.lower() not in skip_areas]

    seen={(n["node"]["name"].lower(),digits((n["node"].get("phone") or {}).get("primaryPhoneNumber")))
          for n in tw("query{leads(first:2000){edges{node{name phone{primaryPhoneNumber}}}}}")["leads"]["edges"]}
    print(f"{len(seen)} existing lead keys loaded — region {a.region}")
    findings=[]
    for ind,terms in INDUSTRIES.items():
        if only and ind not in only: continue
        target=a.target if a.target is not None else TARGET_OVERRIDES.get(ind,DEFAULT_TARGET)
        if target<=0: target=float("inf")
        got=0; stats={"total":0,"no_site":0,"rsum":0.0,"rn":0,"ssum":0}
        print(f"\n=== {ind} (target {target}) ===")
        for area in areas:
            if got>=target: break
            for term in terms:
                if got>=target: break
                print(f"  scraping '{term} {area}'…")
                rows=run_job(term,area,a.depth,a.max_time)
                batch=[]
                for r in rows:
                    lead=build_lead(r,ind,region)
                    if not lead: continue
                    key=(lead["name"].lower(),digits((lead.get("phone") or {}).get("primaryPhoneNumber")))
                    if key in seen: continue
                    seen.add(key); batch.append(lead)
                    stats["total"]+=1; got+=1
                    if lead.get("hasWebsite")=="NO": stats["no_site"]+=1
                    if lead.get("rating"): stats["rsum"]+=lead["rating"]; stats["rn"]+=1
                    stats["ssum"]+=lead.get("leadScore",0)
                for i in range(0,len(batch),40):
                    tw("mutation($d:[LeadCreateInput]!){createLeads(data:$d){id}}",{"d":batch[i:i+40]})
                print(f"    +{len(batch)} new (running total {got})")
        if stats["total"]:
            avg_r=stats["rsum"]/stats["rn"] if stats["rn"] else 0
            avg_s=stats["ssum"]/stats["total"]
            line=(f"- **{ind}**: {stats['total']} new leads, "
                  f"{stats['no_site']} ({100*stats['no_site']//stats['total']}%) have NO website "
                  f"(prime targets), avg rating {avg_r:.1f}, avg lead-score {avg_s:.0f}")
            findings.append(line); print("  "+line)

    # write findings
    path=os.path.join(HERE,"docs","scrape-findings.md")
    with open(path,"a",encoding="utf-8") as f:
        f.write(f"\n## Scrape run {time.strftime('%Y-%m-%d %H:%M')}\n\n"+"\n".join(findings)+"\n")
    print(f"\nFindings appended to {path}")

if __name__=="__main__":
    main()
