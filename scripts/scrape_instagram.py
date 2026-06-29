#!/usr/bin/env python3
"""
RAL CRM — Instagram lead scraper (DIY, USE A THROWAWAY ACCOUNT).

⚠️  Instagram prohibits scraping and BANS accounts that do it. This logs in with
    an account (required — anonymous access is 403'd) and pulls PUBLIC business
    profile data. Use a disposable account, keep volume low, and expect Meta to
    break this periodically. Your real/business IG must NOT be used here.

Pulls per public profile: name, bio, category, external link, followers, and
any phone/email/WhatsApp found in the bio. Maps to Leads (source = Instagram),
enriches + dedupes + imports like the Google Maps scraper.

Setup: put a throwaway account in .env  ->  IG_USER=...  IG_PASS=...
Usage:
  python scripts/scrape_instagram.py --usernames cafe_x,gym_y,clinic_z
  python scripts/scrape_instagram.py --usernames-file handles.txt
  python scripts/scrape_instagram.py --hashtag bahrainsalon --limit 25
"""
import argparse, json, os, random, re, sys, time, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_outreach as L

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def load_env():
    env=dict(os.environ); p=os.path.join(HERE,".env")
    if os.path.exists(p):
        for line in open(p,encoding="utf-8"):
            line=line.strip()
            if line and not line.startswith("#") and "=" in line:
                k,v=line.split("=",1); env.setdefault(k,v)
    return env
ENV=load_env()
TW=ENV.get("TWENTY_URL","http://localhost:3000").rstrip("/")
TOKEN=ENV.get("TWENTY_API_KEY") or sys.exit("TWENTY_API_KEY not set")
IG_USER=ENV.get("IG_USER"); IG_PASS=ENV.get("IG_PASS")
OWNER="HISHAM"

def tw(q,v=None):
    r=urllib.request.Request(f"{TW}/graphql",data=json.dumps({"query":q,"variables":v or {}}).encode(),
        headers={"Authorization":f"Bearer {TOKEN}","Content-Type":"application/json"})
    try: d=json.loads(urllib.request.urlopen(r).read())
    except urllib.error.HTTPError as e: d=json.loads(e.read())
    if "errors" in d: raise RuntimeError(json.dumps(d["errors"])[:300])
    return d["data"]

# ---- contact extraction from bio ----
def parse_phone(text):
    t=(text or "").replace("‏","").replace("‎","")
    # +973 / 973 / bare 8-digit Bahrain mobile
    m=re.search(r"(\+?973[\s-]?\d{4}[\s-]?\d{4})", t) or re.search(r"\b([36]\d{3}[\s-]?\d{4})\b", t)
    if not m: return None
    digits=re.sub(r"\D","",m.group(1))
    if digits.startswith("973"): digits=digits[3:]
    if len(digits)!=8: return None
    return {"primaryPhoneNumber":digits,"primaryPhoneCallingCode":"+973","primaryPhoneCountryCode":"BH"}

def parse_email(text):
    m=re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text or "")
    return m.group(0) if m and L.valid_email(m.group(0)) else None

def build_lead(p, seen):
    name=(p.full_name or p.username or "").strip()
    if not name: return None
    bio=p.biography or ""
    industry=L.classify(p.business_category_name, name+" "+bio, fallback="UNKNOWN")
    website=(p.external_url or "").strip()
    has_site="YES" if website and "linktr.ee" not in website and "instagram.com" not in website else "NO"
    ph=parse_phone(bio); email=parse_email(bio)
    score=40+L.PRIORITY.get(industry,6)+(8 if (p.followers or 0)>=1000 else 0)+(5 if has_site=="NO" else 0)
    lead={"name":name,"industry":industry,"source":"INSTAGRAM","bucket":"ACTIVE",
          "stage":"OPT_1_LEAD_IDENTIFIED","owner":OWNER,
          "hasWebsite":has_site,"leadScore":max(0,min(100,score)),
          "notes":f"Instagram @{p.username} | {p.followers} followers"+(f" | {bio[:120]}" if bio else "")}
    if website: lead["website"]={"primaryLinkUrl":website,"primaryLinkLabel":"Website"}
    if email: lead["email"]={"primaryEmail":email,"additionalEmails":[]}
    if ph:
        lead["phone"]=ph
        wl=L.whatsapp_link(name,industry,OWNER,ph["primaryPhoneNumber"],ph["primaryPhoneCallingCode"],has_site)
        if wl: lead["whatsappLink"]={"primaryLinkUrl":wl,"primaryLinkLabel":"Message on WhatsApp"}
    subj,bdy=L.email_draft(name,industry,OWNER,has_site)
    lead["emailDraft"]=f"Subject: {subj}\n\n{bdy}"
    return {k:v for k,v in lead.items() if v not in (None,"",[])}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--usernames",default="")
    ap.add_argument("--usernames-file",default="")
    ap.add_argument("--hashtag",default="")
    ap.add_argument("--limit",type=int,default=25)
    a=ap.parse_args()
    if not IG_USER or not IG_PASS:
        sys.exit("Add a THROWAWAY account to .env: IG_USER=... IG_PASS=...  (never your real IG)")
    import instaloader
    il=instaloader.Instaloader(quiet=True, download_pictures=False, download_videos=False,
                               download_comments=False, save_metadata=False)
    sess=os.path.join(HERE,"data",f"ig-session-{IG_USER}")
    try:
        il.load_session_from_file(IG_USER, sess); print("loaded saved session")
    except FileNotFoundError:
        print("logging in (first run)…")
        il.login(IG_USER, IG_PASS); il.save_session_to_file(sess)

    # collect target usernames
    targets=[]
    if a.usernames: targets+= [u.strip().lstrip("@") for u in a.usernames.split(",") if u.strip()]
    if a.usernames_file and os.path.exists(a.usernames_file):
        targets+=[l.strip().lstrip("@") for l in open(a.usernames_file,encoding="utf-8") if l.strip()]
    if a.hashtag:
        print(f"discovering profiles under #{a.hashtag} (rate-limited)…")
        tag=instaloader.Hashtag.from_name(il.context, a.hashtag.lstrip("#"))
        seen_u=set()
        for post in tag.get_posts():
            u=post.owner_username
            if u not in seen_u:
                seen_u.add(u); targets.append(u)
            if len(targets)>=a.limit: break
            time.sleep(random.uniform(2,5))
    targets=list(dict.fromkeys(targets))[:a.limit]
    print(f"{len(targets)} profiles to fetch")

    seen={(n["node"]["name"].lower(),) for n in
          tw("query{leads(first:2000){edges{node{name}}}}")["leads"]["edges"]}
    batch=[]
    for i,u in enumerate(targets):
        try:
            p=instaloader.Profile.from_username(il.context,u)
            lead=build_lead(p,seen)
            if not lead: continue
            if (lead["name"].lower(),) in seen: print(f"  = {u}: dup, skip"); continue
            seen.add((lead["name"].lower(),)); batch.append(lead)
            print(f"  + {u} -> {lead['name'][:28]} [{lead['industry']}] score {lead['leadScore']}")
        except Exception as e:
            print(f"  ! {u}: {type(e).__name__} {str(e)[:80]}")
        time.sleep(random.uniform(8,18))   # hard rate-limit to reduce ban risk
    if batch:
        for j in range(0,len(batch),40):
            tw("mutation($d:[LeadCreateInput]!){createLeads(data:$d){id}}",{"d":batch[j:j+40]})
    print(f"\nImported {len(batch)} Instagram leads.")

if __name__=="__main__":
    main()
