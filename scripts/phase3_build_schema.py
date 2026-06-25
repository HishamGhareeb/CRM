#!/usr/bin/env python3
"""
RAL CRM — Phase 3: build the data model via Twenty's metadata API.

Creates custom objects (Lead, Priority Lead, Contact, Activity) with all
fields and select options from the build brief. Idempotent: existing
objects/fields are detected and skipped, so it is safe to re-run.

Usage:
    TWENTY_API_KEY=...  TWENTY_URL=http://localhost:3000  python scripts/phase3_build_schema.py

Reads TWENTY_API_KEY and TWENTY_URL from the environment or the repo .env.
"""
import json
import os
import sys
import urllib.request
import urllib.error

# ---------------------------------------------------------------- config
def load_env():
    env = dict(os.environ)
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    envpath = os.path.join(here, ".env")
    if os.path.exists(envpath):
        for line in open(envpath, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k, v)
    return env

ENV = load_env()
URL = ENV.get("TWENTY_URL", "http://localhost:3000").rstrip("/")
TOKEN = ENV.get("TWENTY_API_KEY")
if not TOKEN:
    sys.exit("ERROR: TWENTY_API_KEY not set (env or .env)")

META = f"{URL}/metadata"

# ---------------------------------------------------------------- gql client
def gql(query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        META, data=body,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req)
        data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        data = json.loads(e.read())
    if "errors" in data:
        raise RuntimeError(json.dumps(data["errors"], indent=2))
    return data["data"]

# ---------------------------------------------------------------- helpers
def list_objects():
    q = """query{objects(paging:{first:200}){edges{node{
        id nameSingular namePlural isSystem
        fields(paging:{first:200}){edges{node{id name type}}}
    }}}}"""
    return [e["node"] for e in gql(q)["objects"]["edges"]]

def find_object(objs, name_singular):
    for o in objs:
        if o["nameSingular"] == name_singular:
            return o
    return None

def create_object(o):
    q = """mutation($input:CreateOneObjectInput!){createOneObject(input:$input){
        id nameSingular fields(paging:{first:50}){edges{node{id name type}}}}}"""
    return gql(q, {"input": {"object": o}})["createOneObject"]

def create_field(f):
    q = "mutation($input:CreateOneFieldMetadataInput!){createOneField(input:$input){id name type}}"
    return gql(q, {"input": {"field": f}})["createOneField"]

def rename_label_field(obj, new_label):
    """Rename the auto-created 'name' label field (e.g. Name -> Company Name)."""
    name_field = next((fe["node"] for fe in obj["fields"]["edges"]
                       if fe["node"]["name"] == "name"), None)
    if not name_field:
        return
    q = """mutation($input:UpdateOneFieldMetadataInput!){updateOneField(input:$input){id label}}"""
    try:
        gql(q, {"input": {"id": name_field["id"],
                          "update": {"label": new_label, "isLabelSyncedWithName": False}}})
        print(f"      renamed label field -> '{new_label}'")
    except RuntimeError as e:
        print(f"      (could not rename label field: {str(e)[:80]})")

# ---------------------------------------------------------------- option builders
COLORS = ["green","turquoise","sky","blue","purple","pink","red","orange","yellow","gray"]

def opts(values):
    """values: list of (label) or (label,color). Returns Twenty SELECT options JSON."""
    out = []
    for i, v in enumerate(values):
        if isinstance(v, tuple):
            label, color = v
        else:
            label, color = v, COLORS[i % len(COLORS)]
        code = "".join(c if c.isalnum() else "_" for c in label.upper()).strip("_")
        while "__" in code:
            code = code.replace("__", "_")
        if code[:1].isdigit():            # Twenty requires values to start with a letter/_
            code = "OPT_" + code
        out.append({"label": label, "value": code, "color": color, "position": i})
    return out

INDUSTRIES = ["Medical & Health","Fitness & Gym","F&B / Restaurant","Cafe","Real Estate",
    "Sports Academy","Beauty & Wellness","Educational","Law Firm","Construction",
    "Marketing Agency","Media Agency","Hotel","Laundry","Pest Control","Cars",
    "Fragrance Store","Entertainment","Tourism","Food Industry","Cloud Based POS",
    "Eye Clinic","Flooring / Wall Panels","Henna","AC","Moving Company","Camps",
    "Hospitality","Multi-sector","Facilities Management","Travel & Tourism","Consultancy",
    "Technology","Electronics Retail","Public Relations (PR)","Home & Interior","Manpower","Unknown"]

STAGES = [("1 - Lead Identified","sky"),("2 - Contacted","yellow"),("3 - Replied","green"),
    ("4 - Discovery Call Booked","purple"),("5 - Proposal Sent","orange"),
    ("6 - Negotiation","orange"),("7 - Closed Won","green"),("8 - Closed Lost","red")]

SOURCES = ["Phone","Instagram","Google","LinkedIn","WhatsApp","Google Maps","Contact",
    "Social Media","Unknown"]

BUCKETS = [("Active","green"),("Re-engage","yellow"),("Closed","gray")]

OWNERS = [("Hisham","blue"),("Suhaib","purple")]

ACTIVITY_TYPES = [("Call","blue"),("WhatsApp","green"),("Email","purple"),
    ("Meeting","orange"),("Note","gray")]

# ---------------------------------------------------------------- field specs
def f(name, label, ftype, **kw):
    d = {"name": name, "label": label, "type": ftype}
    d.update(kw)
    return d

# ---------------------------------------------------------------- main build
def ensure_object(objs, spec, label_rename, fields):
    existing = find_object(objs, spec["nameSingular"])
    if existing:
        print(f"  • {spec['labelSingular']}: exists (id {existing['id'][:8]}…)")
        obj = existing
        have = {fe["node"]["name"] for fe in obj["fields"]["edges"]}
    else:
        print(f"  + creating object '{spec['labelSingular']}'")
        created = create_object(spec)
        obj = created
        # normalise shape to match list_objects()
        obj["fields"] = created["fields"]
        have = {fe["node"]["name"] for fe in obj["fields"]["edges"]}
        if label_rename:
            rename_label_field(obj, label_rename)
    oid = obj["id"]
    for fld in fields:
        if fld["name"] in have:
            print(f"      = field '{fld['name']}' exists, skip")
            continue
        payload = dict(fld)
        payload["objectMetadataId"] = oid
        try:
            create_field(payload)
            print(f"      + field '{fld['name']}' ({fld['type']})")
        except RuntimeError as e:
            print(f"      ! field '{fld['name']}' FAILED: {str(e)[:120]}")
    return obj

def main():
    objs = list_objects()
    print(f"Connected to {URL} — {len(objs)} objects currently.\n")

    # ---- 1. Lead (Pipeline) ----
    print("Lead (Pipeline)")
    lead_fields = [
        f("leadId","Lead ID","TEXT"),
        f("industry","Industry","SELECT", options=opts(INDUSTRIES)),
        f("phone","Phone","PHONES"),
        f("source","Source","SELECT", options=opts(SOURCES)),
        f("stage","Stage","SELECT", options=opts(STAGES)),
        f("bucket","Bucket","SELECT", options=opts(BUCKETS)),
        f("owner","Owner","SELECT", options=opts(OWNERS)),
        f("estDeal","Est. Deal (BHD)","CURRENCY"),
        f("lastContact","Last Contact","DATE"),
        f("nextFollowup","Next Follow-up","DATE"),
        f("notes","Notes","TEXT"),
        f("offerAngle","Offer Angle","TEXT"),
    ]
    lead = ensure_object(objs, {
        "nameSingular":"lead","namePlural":"leads",
        "labelSingular":"Lead","labelPlural":"Leads",
        "icon":"IconTargetArrow","description":"Pipeline lead (RAL-PIP)"},
        "Company Name", lead_fields)

    # ---- 2. Priority Lead ----
    print("Priority Lead")
    prio_fields = [
        f("priorityId","Priority ID","TEXT"),
        f("phone","Phone","PHONES"),
        f("contactName","Contact Name","TEXT"),
        f("industry","Industry","SELECT", options=opts(INDUSTRIES)),
        f("stage","Stage","SELECT", options=opts(STAGES)),
        f("nextAction","Notes / Next Action","TEXT"),
        f("estDeal","Est. Deal (BHD)","CURRENCY"),
        f("owner","Owner","SELECT", options=opts(OWNERS)),
    ]
    ensure_object(objs, {
        "nameSingular":"priorityLead","namePlural":"priorityLeads",
        "labelSingular":"Priority Lead","labelPlural":"Priority Leads",
        "icon":"IconStar","description":"High-priority lead (RAL-PRI)"},
        "Company Name", prio_fields)

    # ---- 3. Contact ----
    print("Contact")
    contact_fields = [
        f("roleTitle","Role / Title","TEXT"),
        f("phone","Phone","PHONES"),
        f("email","Email","EMAILS"),
        f("whatsapp","WhatsApp","PHONES"),
        f("notes","Notes","TEXT"),
        f("linkedLead","Linked Lead","RELATION",
          relationCreationPayload={
              "targetObjectMetadataId": lead["id"],
              "type":"MANY_TO_ONE",
              "targetFieldLabel":"Contacts",
              "targetFieldIcon":"IconUser"}),
    ]
    ensure_object(objs, {
        "nameSingular":"contact","namePlural":"contacts",
        "labelSingular":"Contact","labelPlural":"Contacts",
        "icon":"IconAddressBook","description":"Person linked to a lead"},
        "Full Name", contact_fields)

    # ---- 4. Activity ----
    print("Activity")
    activity_fields = [
        f("activityType","Type","SELECT", options=opts(ACTIVITY_TYPES)),
        f("activityDate","Date","DATE_TIME"),
        f("summary","Summary","TEXT"),
        f("owner","Owner","SELECT", options=opts(OWNERS)),
        f("nextAction","Next Action","TEXT"),
        f("followupDate","Follow-up Date","DATE"),
        f("linkedLead","Linked Lead","RELATION",
          relationCreationPayload={
              "targetObjectMetadataId": lead["id"],
              "type":"MANY_TO_ONE",
              "targetFieldLabel":"Activities",
              "targetFieldIcon":"IconActivity"}),
    ]
    ensure_object(objs, {
        "nameSingular":"activity","namePlural":"activities",
        "labelSingular":"Activity","labelPlural":"Activities",
        "icon":"IconActivity","description":"Logged touch on a lead"},
        "Title", activity_fields)

    print("\nDone. Final object list:")
    for o in list_objects():
        if not o.get("isSystem"):
            print(f"  - {o['nameSingular']}")

if __name__ == "__main__":
    main()
