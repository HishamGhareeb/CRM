#!/usr/bin/env python3
"""
RAL CRM — Instagram lead scraper (open-source instagrapi, THROWAWAY ACCOUNT).

Uses instagrapi (https://github.com/subzeroid/instagrapi, MIT) — an open-source
Instagram private-API client. It returns a business profile's PUBLIC contact
fields directly (public_email, contact_phone_number, category, external_url,
followers), so no bio-guessing.

⚠️  Instagram bans accounts that scrape. Use a DISPOSABLE account, keep volume
    low, expect Meta to break this periodically. NEVER use your real/business IG.

Maps profiles to Leads (source = Instagram), enriches + dedupes + imports like
the Google Maps scraper. Session is cached so you only log in once.

Setup:  .env  ->  IG_USER=throwaway   IG_PASS=...
Usage:
  python scripts/scrape_instagram.py --usernames gym_x,salon_y,clinic_z
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

def phone_from_user(u):
    cc=re.sub(r"\D","",(u.public_phone_country_code or "")) or "973"
    num=re.sub(r"\D","",(u.public_phone_number or ""))
    if not num:
        raw=re.sub(r"\D","",(u.contact_phone_number or "")) or _phone_from_bio(u.biography)
        if not raw: return None
        if raw.startswith("973"): raw=raw[3:]
        if len(raw)!=8: return None
        num=raw
    return {"primaryPhoneNumber":num,"primaryPhoneCallingCode":"+"+cc,
            "primaryPhoneCountryCode":"BH" if cc=="973" else ""}

def _phone_from_bio(text):
    m=re.search(r"(\+?973[\s-]?\d{4}[\s-]?\d{4})", text or "") or re.search(r"\b([36]\d{3}[\s-]?\d{4})\b", text or "")
    return re.sub(r"\D","",m.group(1)) if m else ""

def build_lead(u):
    name=(u.full_name or u.username or "").strip()
    if not name: return None
    bio=u.biography or ""
    cat=u.business_category_name or u.category_name or u.category or ""
    industry=L.classify(cat, name+" "+bio, fallback="UNKNOWN")
    website=(str(u.external_url) if u.external_url else "").strip()
    has_site="YES" if website and "linktr.ee" not in website and "instagram.com" not in website else "NO"
    email=(u.public_email or "").strip()
    ph=phone_from_user(u)
    fol=u.follower_count or 0
    score=40+L.PRIORITY.get(industry,6)+(8 if fol>=1000 else 0)+(5 if has_site=="NO" else 0)
    lead={"name":name,"industry":industry,"source":"INSTAGRAM","bucket":"ACTIVE",
          "stage":"OPT_1_LEAD_IDENTIFIED","owner":OWNER,
          "hasWebsite":has_site,"leadScore":max(0,min(100,score)),
          "notes":f"Instagram @{u.username} | {fol} followers"+(f" | {cat}" if cat else "")+(f" | {bio[:120]}" if bio else "")}
    if website: lead["website"]={"primaryLinkUrl":website,"primaryLinkLabel":"Website"}
    if email and L.valid_email(email): lead["email"]={"primaryEmail":email,"additionalEmails":[]}
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
    from instagrapi import Client
    cl=Client(); cl.delay_range=[3,8]
    # interactive challenge handler — when IG sends a code to the account's
    # email/SMS, paste it here (only works when run in your own terminal)
    cl.challenge_code_handler = lambda username, choice: input(f"  Enter the code IG sent via {choice}: ").strip()
    sess=os.path.join(HERE,"data",f"ig-{IG_USER}.json")
    try:
        cl.load_settings(sess); cl.login(IG_USER, IG_PASS); print("session loaded")
    except Exception:
        print("logging in (first run)…"); cl.login(IG_USER, IG_PASS); cl.dump_settings(sess)

    targets=[u.strip().lstrip("@") for u in a.usernames.split(",") if u.strip()]
    if a.usernames_file and os.path.exists(a.usernames_file):
        targets+=[l.strip().lstrip("@") for l in open(a.usernames_file,encoding="utf-8") if l.strip()]
    if a.hashtag:
        print(f"discovering under #{a.hashtag}…")
        for m in cl.hashtag_medias_recent(a.hashtag.lstrip("#"), amount=a.limit*2):
            targets.append(m.user.username)
            if len(set(targets))>=a.limit: break
    targets=list(dict.fromkeys(targets))[:a.limit]
    print(f"{len(targets)} profiles to fetch")

    seen={n["node"]["name"].lower() for n in
          tw("query{leads(first:2000){edges{node{name}}}}")["leads"]["edges"]}
    batch=[]
    for u in targets:
        try:
            user=cl.user_info_by_username(u)
            lead=build_lead(user)
            if not lead: continue
            if lead["name"].lower() in seen: print(f"  = {u}: dup"); continue
            seen.add(lead["name"].lower()); batch.append(lead)
            c="email" if lead.get("email") else ("phone" if lead.get("phone") else "no-contact")
            print(f"  + @{u} -> {lead['name'][:26]} [{lead['industry']}] {c} score {lead['leadScore']}")
        except Exception as e:
            print(f"  ! @{u}: {type(e).__name__} {str(e)[:90]}")
        time.sleep(random.uniform(6,14))   # rate-limit to reduce ban risk
    if batch:
        for j in range(0,len(batch),40):
            tw("mutation($d:[LeadCreateInput]!){createLeads(data:$d){id}}",{"d":batch[j:j+40]})
    print(f"\nImported {len(batch)} Instagram leads.")

if __name__=="__main__":
    main()
