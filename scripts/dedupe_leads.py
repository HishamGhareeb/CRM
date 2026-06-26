#!/usr/bin/env python3
"""
RAL CRM — lead de-duplication / hygiene.

Volume scraping across overlapping area searches inevitably creates duplicate
leads (same business, same phone). This finds duplicate groups (by phone digits,
then by normalised company name) and keeps the richest record in each group,
destroying the rest.

"Richest" = most populated business fields, tie-broken by lead score, then by
earliest creation (keep the original).

Usage:
  python scripts/dedupe_leads.py            # dry-run: report duplicate groups
  python scripts/dedupe_leads.py --apply    # merge: destroy the redundant copies
"""
import json, os, re, sys, urllib.request, urllib.error

APPLY = "--apply" in sys.argv
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

def norm(s): return re.sub(r"[^a-z0-9]","",(s or "").lower())
def digits(s): return re.sub(r"\D","",s or "")

def fetch():
    out,after=[],None
    while True:
        cur=f',after:"{after}"' if after else ""
        q=("query{leads(first:60"+cur+"){pageInfo{hasNextPage endCursor}edges{node{"
           "id name createdAt leadScore bucket website{primaryLinkUrl} email{primaryEmail} "
           "painPoints notes offerAngle rating phone{primaryPhoneNumber}}}}}")
        d=tw(q)["leads"]; out+=[e["node"] for e in d["edges"]]
        if not d["pageInfo"]["hasNextPage"]: break
        after=d["pageInfo"]["endCursor"]
    return out

def richness(n):
    score=0
    for k in ("painPoints","notes","offerAngle"):
        if (n.get(k) or "").strip(): score+=1
    if (n.get("website") or {}).get("primaryLinkUrl"): score+=1
    if (n.get("email") or {}).get("primaryEmail"): score+=1
    if (n.get("phone") or {}).get("primaryPhoneNumber"): score+=1
    if n.get("rating"): score+=1
    return score

def best(group):
    return sorted(group,key=lambda n:(-richness(n),-(n.get("leadScore") or 0),n.get("createdAt") or ""))[0]

def main():
    leads=fetch()
    print(f"{len(leads)} leads loaded")
    # group by phone digits (len>=8), then by normalised name for phone-less
    groups={}
    for n in leads:
        ph=digits((n.get("phone") or {}).get("primaryPhoneNumber"))
        key=("p",ph) if len(ph)>=8 else ("n",norm(n["name"]))
        if not key[1]: continue
        groups.setdefault(key,[]).append(n)
    dups={k:v for k,v in groups.items() if len(v)>1}
    total_extra=sum(len(v)-1 for v in dups.values())
    print(f"{len(dups)} duplicate groups, {total_extra} redundant records\n")
    destroyed=0
    for k,v in list(dups.items())[:60]:
        keep=best(v); drop=[n for n in v if n["id"]!=keep["id"]]
        print(f"  [{k[0]}:{k[1][:14]}] keep '{keep['name'][:28]}' (rich {richness(keep)}), drop {len(drop)}")
        if APPLY:
            for n in drop:
                tw("mutation($id:UUID!){destroyLead(id:$id){id}}",{"id":n["id"]}); destroyed+=1
    print(f"\n{'Destroyed '+str(destroyed)+' duplicates.' if APPLY else 'DRY-RUN — re-run with --apply to merge.'}")

if __name__=="__main__":
    main()
