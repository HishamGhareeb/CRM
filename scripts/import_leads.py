#!/usr/bin/env python3
"""
RAL CRM — import Leads + Priority Leads from a JSON export (export_leads.py)
into THIS instance, de-duplicating against what's already here.

Run this ON THE TARGET machine (the CRM you want to merge leads INTO).
Reads TWENTY_URL / TWENTY_API_KEY from the target's .env.

- Dedupes incoming vs existing (and within the file) on company name + phone.
- Validates every SELECT/enum value against the target's schema and drops any
  value the target doesn't have (so a mismatched option never fails the import).

Usage:
  python scripts/import_leads.py migration/leads-export.json
  python scripts/import_leads.py leads-export.json --dry-run
"""
import argparse, json, os, re, sys, urllib.request, urllib.error

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

def enum_values(typename):
    t=gql('query{__type(name:"%s"){enumValues{name}}}'%typename)["__type"]
    return {v["name"] for v in t["enumValues"]} if t else set()

def digits(s): return re.sub(r"\D","",s or "")
def key(rec):
    return (rec.get("name","").lower(), digits((rec.get("phone") or {}).get("primaryPhoneNumber")))

def sanitize(rec, enum_map):
    """Drop enum values the target doesn't know."""
    out=dict(rec)
    for field, allowed in enum_map.items():
        if field in out and out[field] not in allowed:
            out.pop(field)
    return out

def existing_keys(plural):
    out,after=[],None
    while True:
        cur=f',after:"{after}"' if after else ""
        d=gql("query{"+plural+"(first:60"+cur+"){pageInfo{hasNextPage endCursor}edges{node{name phone{primaryPhoneNumber}}}}}")[plural]
        out+=[e["node"] for e in d["edges"]]
        if not d["pageInfo"]["hasNextPage"]: break
        after=d["pageInfo"]["endCursor"]
    return {(n["name"].lower(), digits((n.get("phone") or {}).get("primaryPhoneNumber"))) for n in out}

def do(kind, records, create_input, enum_map, seen, dry):
    fresh=[]
    for r in records:
        r=sanitize(r, enum_map)
        k=key(r)
        if k in seen: continue
        seen.add(k); fresh.append(r)
    print(f"{kind}: {len(records)} in file, {len(fresh)} new after dedupe")
    if dry or not fresh: return len(fresh)
    n=0
    for i in range(0,len(fresh),40):
        chunk=fresh[i:i+40]
        gql("mutation($d:["+create_input+"]!){create"+kind+"(data:$d){id}}",{"d":chunk})
        n+=len(chunk); print(f"  …{n}/{len(fresh)}")
    return n

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("file"); ap.add_argument("--dry-run",action="store_true")
    a=ap.parse_args()
    data=json.load(open(a.file,encoding="utf-8"))
    print(f"Merging from {data.get('source','?')} (exported {data.get('exported_at','?')}) into {URL}")

    lead_enums={"industry":enum_values("LeadIndustryEnum"),"source":enum_values("LeadSourceEnum"),
        "stage":enum_values("LeadStageEnum"),"bucket":enum_values("LeadBucketEnum"),
        "owner":enum_values("LeadOwnerEnum"),"hasWebsite":enum_values("LeadHasWebsiteEnum"),
        "outreachStatus":enum_values("LeadOutreachStatusEnum")}
    prio_enums={"industry":enum_values("PriorityLeadIndustryEnum"),
        "stage":enum_values("PriorityLeadStageEnum"),"owner":enum_values("PriorityLeadOwnerEnum")}

    seen=existing_keys("leads")   # always dedupe against what's already here
    do("Leads", data.get("leads",[]), "LeadCreateInput", lead_enums, seen, a.dry_run)
    pseen=set()  # priority leads keyed separately (dedupe within file only + name)
    do("PriorityLeads", data.get("priorityLeads",[]), "PriorityLeadCreateInput", prio_enums, pseen, a.dry_run)

    if not a.dry_run:
        tot=gql("query{leads(first:0){totalCount}}")["leads"]["totalCount"]
        print(f"\nDone. Target now has {tot} leads.")

if __name__=="__main__":
    main()
