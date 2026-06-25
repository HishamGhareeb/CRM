#!/usr/bin/env python3
"""
RAL CRM — Phase 5: build the RAL Dashboard (page layout + chart widgets).

Creates a DASHBOARD page layout with a tab and GRAPH widgets, then links it
to the "RAL Dashboard" record. Idempotent on the layout name: if a layout
named "RAL Dashboard Layout" exists it is reused (widgets are not duplicated).

Usage: python scripts/phase5_build_dashboard.py
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

def gql(endpoint, query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(f"{URL}/{endpoint}", data=body, headers={
        "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try: data = json.loads(urllib.request.urlopen(req).read())
    except urllib.error.HTTPError as e: data = json.loads(e.read())
    if "errors" in data: raise RuntimeError(json.dumps(data["errors"])[:500])
    return data["data"]
meta = lambda q, v=None: gql("metadata", q, v)
core = lambda q, v=None: gql("graphql", q, v)

# ---- lead object + field ids ----
def lead_fields():
    q = """query{objects(paging:{first:200}){edges{node{nameSingular id
        fields(paging:{first:140}){edges{node{id name}}}}}}}"""
    for e in meta(q)["objects"]["edges"]:
        n = e["node"]
        if n["nameSingular"] == "lead":
            return n["id"], {fe["node"]["name"]: fe["node"]["id"] for fe in n["fields"]["edges"]}
    sys.exit("lead object not found")
OBJ, F = lead_fields()

# ---- filters (record-filter JSON used by widget configuration) ----
def sel_filter(field, values):
    return {field: {"in": values}}

LAYOUT_NAME = "RAL Dashboard Layout"

def get_layout():
    for l in meta("query{getPageLayouts{id name type}}")["getPageLayouts"]:
        if l["name"] == LAYOUT_NAME:
            return l["id"]
    return None

def main():
    if get_layout():
        print("Layout already exists — skipping (delete it to rebuild)."); return

    layout = meta('mutation($i:CreatePageLayoutInput!){createPageLayout(input:$i){id}}',
                  {"i": {"name": LAYOUT_NAME, "type": "DASHBOARD"}})["createPageLayout"]
    lid = layout["id"]
    tab = meta('mutation($i:CreatePageLayoutTabInput!){createPageLayoutTab(input:$i){id}}',
               {"i": {"title": "Overview", "position": 0, "pageLayoutId": lid}})["createPageLayoutTab"]
    tid = tab["id"]
    print(f"Created layout {lid[:8]}… / tab {tid[:8]}…")

    def widget(title, conf, grid):
        meta('mutation($i:CreatePageLayoutWidgetInput!){createPageLayoutWidget(input:$i){id}}',
             {"i": {"pageLayoutTabId": tid, "title": title, "type": "GRAPH",
                    "objectMetadataId": OBJ, "gridPosition": grid, "configuration": conf}})
        print(f"  + widget: {title}")

    def agg(label, op, field, filt=None):
        c = {"configurationType":"AGGREGATE_CHART","aggregateOperation":op,
             "aggregateFieldMetadataId":F[field],"label":label}
        if filt: c["filter"] = filt
        return c
    def bar(group, filt=None):
        c = {"configurationType":"BAR_CHART","aggregateOperation":"COUNT",
             "aggregateFieldMetadataId":F["name"],"primaryAxisGroupByFieldMetadataId":F[group],
             "layout":"VERTICAL"}
        if filt: c["filter"] = filt
        return c
    def pie(group, filt=None):
        c = {"configurationType":"PIE_CHART","aggregateOperation":"COUNT",
             "aggregateFieldMetadataId":F["name"],"groupByFieldMetadataId":F[group]}
        if filt: c["filter"] = filt
        return c

    WARM = ["OPT_3_REPLIED","OPT_4_DISCOVERY_CALL_BOOKED","OPT_5_PROPOSAL_SENT",
            "OPT_6_NEGOTIATION","OPT_7_CLOSED_WON"]
    g = lambda r,c,rs,cs: {"row":r,"column":c,"rowSpan":rs,"columnSpan":cs}

    # row 0: KPI number cards
    widget("Active Leads",        agg("Active Leads","COUNT","name", sel_filter("bucket",["ACTIVE"])),       g(0,0,2,3))
    widget("Warm Leads (3+)",     agg("Warm (Stage 3+)","COUNT","name", sel_filter("stage",WARM)),           g(0,3,2,3))
    widget("Re-engage Pool",      agg("Re-engage","COUNT","name", sel_filter("bucket",["RE_ENGAGE"])),        g(0,6,2,3))
    widget("Deals Won",           agg("Deals Won","COUNT","name", sel_filter("stage",["OPT_7_CLOSED_WON"])),  g(0,9,2,3))
    # row 2-: charts
    widget("Pipeline by Stage",   bar("stage", sel_filter("bucket",["ACTIVE"])),  g(2,0,4,6))
    widget("Leads by Bucket",     pie("bucket"),                                  g(2,6,4,6))
    widget("Leads by Industry",   bar("industry"),                               g(6,0,4,6))
    widget("Leads by Owner",      pie("owner"),                                  g(6,6,4,6))

    # link the RAL Dashboard record to this layout
    dash = core('query{dashboards(first:20){edges{node{id title}}}}')["dashboards"]["edges"]
    rid = next((d["node"]["id"] for d in dash if d["node"]["title"] == "RAL Dashboard"), None)
    if rid:
        core('mutation($id:UUID!,$d:DashboardUpdateInput!){updateDashboard(id:$id,data:$d){id}}',
             {"id": rid, "d": {"pageLayoutId": lid}})
        print(f"Linked 'RAL Dashboard' record -> layout {lid[:8]}…")
    else:
        print("WARN: 'RAL Dashboard' record not found; create it or link manually.")

if __name__ == "__main__":
    main()
