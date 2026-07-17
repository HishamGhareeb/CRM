#!/usr/bin/env python3
"""
RAL CRM — export all Leads + Priority Leads to a JSON file, so a second
instance's data can be merged into another (see import_leads.py).

Run this ON THE SOURCE machine (the CRM you want to copy leads OUT of).
Reads TWENTY_URL / TWENTY_API_KEY from that machine's .env (or env vars).

Usage:
  python scripts/export_leads.py                 # -> migration/leads-export.json
  python scripts/export_leads.py --out mine.json
"""
import argparse, json, os, sys, time, urllib.request, urllib.error

HERE=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def load_env():
    env=dict(os.environ); p=os.path.join(HERE,".env")
    if os.path.exists(p):
        for line in open(p,encoding="utf-8"):
            line=line.strip()
            if line and not line.startswith("#") and "=" in line:
                k,v=line.split("=",1); env.setdefault(k,v)
    return env
ENV=load_env()
URL=ENV.get("TWENTY_URL","http://localhost:3000").rstrip("/")
TOKEN=ENV.get("TWENTY_API_KEY") or sys.exit("TWENTY_API_KEY not set")

def gql(q,v=None):
    r=urllib.request.Request(f"{URL}/graphql",data=json.dumps({"query":q,"variables":v or {}}).encode(),
        headers={"Authorization":f"Bearer {TOKEN}","Content-Type":"application/json"})
    try: d=json.loads(urllib.request.urlopen(r).read())
    except urllib.error.HTTPError as e: d=json.loads(e.read())
    if "errors" in d: raise RuntimeError(json.dumps(d["errors"])[:400])
    return d["data"]

LEAD_FIELDS = """name leadId industry source stage bucket owner
  lastContact nextFollowup notes offerAngle rating reviewCount fullAddress
  painPoints leadScore hasWebsite outreachStatus emailDraft
  phone{primaryPhoneNumber primaryPhoneCallingCode primaryPhoneCountryCode}
  estDeal{amountMicros currencyCode}
  website{primaryLinkUrl primaryLinkLabel}
  email{primaryEmail additionalEmails}
  whatsappLink{primaryLinkUrl primaryLinkLabel}"""
PRIO_FIELDS = """name priorityId contactName industry stage nextAction owner
  phone{primaryPhoneNumber primaryPhoneCallingCode primaryPhoneCountryCode}
  estDeal{amountMicros currencyCode}"""

def dump(plural, fields):
    out,after=[],None
    while True:
        cur=f',after:"{after}"' if after else ""
        d=gql("query{"+plural+"(first:60"+cur+"){pageInfo{hasNextPage endCursor}edges{node{"+fields+"}}}}")[plural]
        out+=[e["node"] for e in d["edges"]]
        if not d["pageInfo"]["hasNextPage"]: break
        after=d["pageInfo"]["endCursor"]
    return out

def clean(rec):
    # drop null/empty and __typename so the record is a clean create-input
    def c(v):
        if isinstance(v,dict):
            v={k:c(x) for k,x in v.items() if k!="__typename"}
            return {k:x for k,x in v.items() if x not in (None,"",[])} or None
        return v
    return {k:c(v) for k,v in rec.items() if c(v) not in (None,"",[])}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--out",default=os.path.join(HERE,"migration","leads-export.json"))
    a=ap.parse_args()
    leads=[clean(r) for r in dump("leads",LEAD_FIELDS)]
    prio=[clean(r) for r in dump("priorityLeads",PRIO_FIELDS)]
    os.makedirs(os.path.dirname(a.out),exist_ok=True)
    json.dump({"source":URL,"exported_at":time.strftime("%Y-%m-%d %H:%M"),
               "leads":leads,"priorityLeads":prio}, open(a.out,"w",encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Exported {len(leads)} leads + {len(prio)} priority leads -> {a.out}")

if __name__=="__main__":
    main()
