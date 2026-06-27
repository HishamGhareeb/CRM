#!/usr/bin/env python3
"""
RAL CRM — regenerate every lead's WhatsApp link + email draft from the current
templates in lib_outreach (single source of truth). Run after editing the
opener/email wording so all stored assets are refreshed.

Observation is derived from the Has Website flag where present.

Usage:
  python scripts/regenerate_outreach.py --dry-run
  python scripts/regenerate_outreach.py
"""
import json, os, sys, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_outreach as L

DRY = "--dry-run" in sys.argv
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

def tw(q,v=None):
    r=urllib.request.Request(f"{TW}/graphql",data=json.dumps({"query":q,"variables":v or {}}).encode(),
        headers={"Authorization":f"Bearer {TOKEN}","Content-Type":"application/json"})
    try: d=json.loads(urllib.request.urlopen(r).read())
    except urllib.error.HTTPError as e: d=json.loads(e.read())
    if "errors" in d: raise RuntimeError(json.dumps(d["errors"])[:300])
    return d["data"]

def observation(has_website):
    if has_website=="NO": return "I noticed you don't have a website yet"
    if has_website=="YES": return "I had a look at your website"
    return None

def main():
    out,after=[],None
    while True:
        cur=f',after:"{after}"' if after else ""
        d=tw("query{leads(first:60"+cur+"){pageInfo{hasNextPage endCursor}edges{node{"
             "id name industry source owner hasWebsite phone{primaryPhoneNumber primaryPhoneCallingCode}}}}}")["leads"]
        out+=[e["node"] for e in d["edges"]]
        if not d["pageInfo"]["hasNextPage"]: break
        after=d["pageInfo"]["endCursor"]
    print(f"{len(out)} leads")
    wa=em=recat=0
    for n in out:
        # for scraped leads, fix the vertical from the business name if it was
        # mislabelled by the search term (seed/CSV leads keep their industry)
        ind=n.get("industry")
        if n.get("source")=="GOOGLE_MAPS":
            new=L.classify(None, n["name"], fallback=ind)
            if new and new!=ind:
                if not DRY:
                    tw("mutation($id:UUID!,$d:LeadUpdateInput!){updateLead(id:$id,data:$d){id}}",
                       {"id":n["id"],"d":{"industry":new}})
                ind=new; recat+=1
        n["industry"]=ind
        obs=observation(n.get("hasWebsite"))
        upd={}
        ph=n.get("phone") or {}
        link=L.whatsapp_link(n["name"],n.get("industry"),n.get("owner"),
                             ph.get("primaryPhoneNumber"),ph.get("primaryPhoneCallingCode"),obs)
        if link:
            upd["whatsappLink"]={"primaryLinkUrl":link,"primaryLinkLabel":"Message on WhatsApp"}; wa+=1
        subj,body=L.email_draft(n["name"],n.get("industry"),n.get("owner"),obs)
        upd["emailDraft"]=f"Subject: {subj}\n\n{body}"; em+=1
        if upd and not DRY:
            tw("mutation($id:UUID!,$d:LeadUpdateInput!){updateLead(id:$id,data:$d){id}}",{"id":n["id"],"d":upd})
    print(f"{'[dry-run] would update' if DRY else 'Updated'} {wa} WhatsApp links, {em} email drafts, "
          f"reclassified {recat} mislabelled verticals")

if __name__=="__main__":
    main()
