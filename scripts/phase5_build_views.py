#!/usr/bin/env python3
"""
RAL CRM — Phase 5: build views via Twenty's metadata API.

Creates four lead views (idempotent — skips views whose name already exists):
  1. Pipeline (Kanban)  — KANBAN grouped by Stage, Active bucket
  2. Pipeline (List)    — TABLE, Active bucket, sorted by Lead ID
  3. Priority Leads     — TABLE, Stage 3-7, sorted by Next Follow-up ASC
  4. Re-engage Pool     — TABLE, Re-engage bucket, sorted by Last Contact ASC

Usage: python scripts/phase5_build_views.py
"""
import json, os, sys, urllib.request, urllib.error

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
URL = ENV.get("TWENTY_URL", "http://localhost:3000").rstrip("/")
TOKEN = ENV.get("TWENTY_API_KEY") or sys.exit("ERROR: TWENTY_API_KEY not set")
META = f"{URL}/metadata"

def gql(query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(META, data=body, headers={
        "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try: data = json.loads(urllib.request.urlopen(req).read())
    except urllib.error.HTTPError as e: data = json.loads(e.read())
    if "errors" in data: raise RuntimeError(json.dumps(data["errors"])[:500])
    return data["data"]

# ---- discover lead object + fields --------------------------------
def lead_meta():
    q = """query{objects(paging:{first:200}){edges{node{nameSingular id
        fields(paging:{first:120}){edges{node{id name type options}}}}}}}"""
    for e in gql(q)["objects"]["edges"]:
        n = e["node"]
        if n["nameSingular"] == "lead":
            fields = {fe["node"]["name"]: fe["node"] for fe in n["fields"]["edges"]}
            return n["id"], fields
    sys.exit("lead object not found — run phase3 first")

OBJ, F = lead_meta()
def fid(name): return F[name]["id"]
STAGE_OPTS = sorted(F["stage"]["options"], key=lambda o: o["position"])

# ---- view builders ------------------------------------------------
def existing_views():
    return {v["name"]: v for v in gql("query{getViews{id name objectMetadataId}}")["getViews"]}

def create_view(v):
    q = "mutation($input:CreateViewInput!){createView(input:$input){id name}}"
    return gql(q, {"input": v})["createView"]

def add_filter(view_id, field, operand, value=""):
    q = "mutation($input:CreateViewFilterInput!){createViewFilter(input:$input){id}}"
    gql(q, {"input": {"viewId": view_id, "fieldMetadataId": field,
                      "operand": operand, "value": value}})

def add_sort(view_id, field, direction):
    q = "mutation($input:CreateViewSortInput!){createViewSort(input:$input){id}}"
    gql(q, {"input": {"viewId": view_id, "fieldMetadataId": field, "direction": direction}})

def add_fields(view_id, names):
    q = "mutation($input:CreateViewFieldInput!){createViewField(input:$input){id}}"
    for i, nm in enumerate(names):
        gql(q, {"input": {"viewId": view_id, "fieldMetadataId": fid(nm),
                          "isVisible": True, "position": i, "size": 180}})

# Note: Twenty auto-creates kanban view groups from the grouped-by select
# field's options, so we do NOT create them manually (that produced dupes).

# stage values 3..7 (Replied .. Closed Won) for the Priority view
WARM = [o["value"] for o in STAGE_OPTS if o["value"] in
        ("OPT_3_REPLIED","OPT_4_DISCOVERY_CALL_BOOKED","OPT_5_PROPOSAL_SENT",
         "OPT_6_NEGOTIATION","OPT_7_CLOSED_WON")]
# stages 1-6 (exclude Closed Won / Closed Lost) for the overdue view
OPEN_STAGES = [o["value"] for o in STAGE_OPTS
               if o["value"] not in ("OPT_7_CLOSED_WON","OPT_8_CLOSED_LOST")]
# stages 2-3 (contacted / replied) for the inactivity view
ACTIVE_EARLY = [o["value"] for o in STAGE_OPTS
                if o["value"] in ("OPT_2_CONTACTED","OPT_3_REPLIED")]

# Twenty requires the label-identifier field (name) at the lowest position.
COLS = ["name","industry","stage","source","owner","phone","estDeal","lastContact","nextFollowup",
        "offerAngle","whatsappLink","notes","website","email","rating","reviewCount","fullAddress"]

def main():
    have = existing_views()
    def ensure(name, builder):
        if name in have:
            print(f"  • '{name}' exists, skip"); return
        builder(name); print(f"  + '{name}' created")

    print("Building views on Lead…")

    # 1. Pipeline (Kanban)
    def kanban(name):
        v = create_view({"name": name, "objectMetadataId": OBJ, "type": "KANBAN",
                         "icon": "IconLayoutKanban", "position": 1,
                         "mainGroupByFieldMetadataId": fid("stage")})
        add_filter(v["id"], fid("bucket"), "IS", json.dumps(["ACTIVE"]))
        add_fields(v["id"], ["name","industry","owner","lastContact"])
    ensure("Pipeline (Kanban)", kanban)

    # 2. Pipeline (List)
    def plist(name):
        v = create_view({"name": name, "objectMetadataId": OBJ, "type": "TABLE",
                         "icon": "IconList", "position": 2})
        add_filter(v["id"], fid("bucket"), "IS", json.dumps(["ACTIVE"]))
        add_sort(v["id"], fid("lastContact"), "DESC")
        add_fields(v["id"], COLS)
    ensure("Pipeline (List)", plist)

    # 3. Priority Leads (warm + soonest follow-up)
    def priority(name):
        v = create_view({"name": name, "objectMetadataId": OBJ, "type": "TABLE",
                         "icon": "IconStar", "position": 3})
        add_filter(v["id"], fid("stage"), "IS", json.dumps(WARM))
        add_sort(v["id"], fid("nextFollowup"), "ASC")
        add_fields(v["id"], ["name","industry","stage","owner","nextFollowup","lastContact","phone","notes"])
    ensure("Priority Leads", priority)

    # 4. Re-engage Pool
    def reengage(name):
        v = create_view({"name": name, "objectMetadataId": OBJ, "type": "TABLE",
                         "icon": "IconRefresh", "position": 4})
        add_filter(v["id"], fid("bucket"), "IS", json.dumps(["RE_ENGAGE"]))
        add_sort(v["id"], fid("lastContact"), "ASC")
        add_fields(v["id"], ["name","industry","source","phone","lastContact","notes"])
    ensure("Re-engage Pool", reengage)

    # 5. Overdue Follow-ups (automation rule 1: follow-up past due, still open)
    def overdue(name):
        v = create_view({"name": name, "objectMetadataId": OBJ, "type": "TABLE",
                         "icon": "IconAlertTriangle", "position": 5})
        add_filter(v["id"], fid("nextFollowup"), "IS_IN_PAST")
        add_filter(v["id"], fid("stage"), "IS", json.dumps(OPEN_STAGES))
        add_sort(v["id"], fid("nextFollowup"), "ASC")
        add_fields(v["id"], ["name","industry","stage","owner","nextFollowup","phone","notes"])
    ensure("Overdue Follow-ups", overdue)

    # 6. Inactive Leads (automation rule 4: contacted/replied but gone quiet;
    #    oldest contact first surfaces the most stale)
    def inactive(name):
        v = create_view({"name": name, "objectMetadataId": OBJ, "type": "TABLE",
                         "icon": "IconClockExclamation", "position": 6})
        add_filter(v["id"], fid("lastContact"), "IS_IN_PAST")
        add_filter(v["id"], fid("stage"), "IS", json.dumps(ACTIVE_EARLY))
        add_sort(v["id"], fid("lastContact"), "ASC")
        add_fields(v["id"], ["name","industry","stage","owner","lastContact","phone","notes"])
    ensure("Inactive Leads", inactive)

    print("\nViews now on Lead:")
    for n in existing_views():
        if n in ("Pipeline (Kanban)","Pipeline (List)","Priority Leads","Re-engage Pool",
                 "Overdue Follow-ups","Inactive Leads"):
            print(f"  - {n}")

if __name__ == "__main__":
    main()
