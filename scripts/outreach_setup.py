#!/usr/bin/env python3
"""
RAL CRM — outreach setup (aligned to the RAL Sales Playbook).

For every Lead:
  1. Fill the Offer Angle (if empty) with the RAL system pitch for that
     vertical (land-and-expand: the operational system we expand into).
     Existing angles are preserved.
  2. Generate a one-click WhatsApp link (wa.me) with a short, diagnostic
     first-touch opener — playbook tone: warm, names the vertical's real
     operational pain, light credibility, soft CTA (a 15-min call to find
     one thing we can fix fast). NOT a hard pitch, no price.

The rep opens the lead, clicks the WhatsApp link, message is pre-filled,
they personalise the first line and send.

Usage:
  python scripts/outreach_setup.py --dry-run    # preview, no writes
  python scripts/outreach_setup.py              # apply
"""
import json, os, re, sys, urllib.parse, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_outreach as _L  # canonical message templates

DRY = "--dry-run" in sys.argv
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

def gql(query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(f"{URL}/graphql", data=body, headers={
        "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try: data = json.loads(urllib.request.urlopen(req).read())
    except urllib.error.HTTPError as e: data = json.loads(e.read())
    if "errors" in data: raise RuntimeError(json.dumps(data["errors"])[:400])
    return data["data"]

# ---- per-vertical pitch: noun, operational pain, internal offer angle ----
# noun  = how we describe the vertical in the opener
# pain  = the manual operation they likely run today (their language)
# angle = internal Offer Angle = the RAL system we expand into
V = {
 "SPORTS_ACADEMY": ("sports academies", "registration, attendance and chasing fees",
    "Sports Academy system: online registration, attendance, auto fee reminders, parent updates, student CRM"),
 "FITNESS_GYM": ("gyms & fitness studios", "sign-ups, class bookings and membership renewals",
    "Gym system: online sign-ups, class booking, auto renewal reminders, member CRM"),
 "MEDICAL_HEALTH": ("clinics", "bookings, reminders and patient follow-up",
    "Clinic system: online booking, auto reminders, treatment recall, patient records"),
 "EYE_CLINIC": ("clinics", "bookings, reminders and patient follow-up",
    "Clinic system: online booking, auto reminders, treatment recall, patient records"),
 "BEAUTY_WELLNESS": ("salons & spas", "bookings and rebooking over DMs",
    "Salon system: online booking, reminders, rebooking, client CRM"),
 "HENNA": ("salons & beauty studios", "bookings over DMs",
    "Salon system: online booking, reminders, rebooking, client CRM"),
 "F_B_RESTAURANT": ("restaurants", "orders and reservations over DMs",
    "Restaurant system: direct online ordering, reservations, customer follow-up"),
 "CAFE": ("cafes", "orders and reservations over DMs",
    "Cafe system: online ordering, loyalty, customer follow-up"),
 "FOOD_INDUSTRY": ("food businesses", "orders and customer follow-up",
    "Online ordering + customer follow-up automation"),
 "EDUCATIONAL": ("schools & training centres", "enrolment, fees and parent comms",
    "School system: online enrolment, fee tracking, attendance, parent portal"),
 "CAMPS": ("camps & training centres", "enrolment, fees and parent comms",
    "Enrolment, scheduling and parent comms automation"),
 "REAL_ESTATE": ("real estate offices", "listings and enquiry follow-up",
    "Real estate system: property listings site, lead capture, WhatsApp follow-up"),
 "HOTEL": ("hotels", "bookings and guest follow-up",
    "Online booking + guest follow-up automation"),
 "HOSPITALITY": ("hospitality businesses", "bookings and guest follow-up",
    "Online booking + guest follow-up automation"),
 "TOURISM": ("tourism businesses", "bookings and customer follow-up",
    "Online booking + customer follow-up automation"),
 "TRAVEL_TOURISM": ("travel businesses", "bookings and customer follow-up",
    "Online booking + customer follow-up automation"),
 "LAW_FIRM": ("law firms", "client intake and enquiries",
    "Professional website + automated client intake"),
 "CONSULTANCY": ("consultancies", "client intake and enquiries",
    "Professional website + automated client intake"),
 "MARKETING_AGENCY": ("agencies", "client delivery and reporting",
    "Automation + CRM to scale client delivery"),
 "MEDIA_AGENCY": ("agencies", "client delivery and reporting",
    "Automation + CRM to scale client delivery"),
 "PUBLIC_RELATIONS_PR": ("PR agencies", "client delivery and reporting",
    "Automation + CRM to scale client delivery"),
 "LAUNDRY": ("laundry businesses", "orders, pickups and customer updates",
    "Online orders, pickup scheduling, customer update automation"),
 "MOVING_COMPANY": ("moving companies", "quote requests and customer updates",
    "Online quotes + shipment/customer update automation"),
 "PEST_CONTROL": ("service businesses", "quotes, bookings and reminders",
    "Online quotes + service reminder automation"),
 "AC": ("service businesses", "quotes, bookings and reminders",
    "Online quotes + service reminder automation"),
 "CARS": ("auto businesses", "bookings, service reminders and follow-up",
    "Online booking, service reminders, customer follow-up"),
 "FRAGRANCE_STORE": ("retailers", "orders and customer follow-up",
    "Online store + customer follow-up"),
 "ELECTRONICS_RETAIL": ("retailers", "orders and customer follow-up",
    "Online store + customer follow-up"),
 "HOME_INTERIOR": ("interior businesses", "enquiries and lead follow-up",
    "Portfolio website + lead capture automation"),
 "FLOORING_WALL_PANELS": ("interior businesses", "enquiries and lead follow-up",
    "Portfolio website + lead capture automation"),
 "CONSTRUCTION": ("construction firms", "enquiries and lead follow-up",
    "Professional website + lead capture automation"),
 "FACILITIES_MANAGEMENT": ("facilities businesses", "enquiries and lead follow-up",
    "Professional website + lead capture automation"),
 "MANPOWER": ("manpower agencies", "applicant and client enquiries",
    "Professional website + applicant/lead automation"),
}
DEFAULT = ("businesses", "enquiries, bookings and follow-up",
           "Website + workflow automation to capture and convert more leads")

OWNER_NAME = {"HISHAM": "Hisham", "SUHAIB": "Suhaib"}

def opener(company, industry, owner):
    # delegate to the single source of truth so wording stays consistent
    return _L.opener(company, industry, owner)

def angle_for(industry):
    return V.get(industry or "", DEFAULT)[2]

def digits(num, cc):
    return re.sub(r"\D", "", (cc or "") + (num or ""))

def wa_link(company, industry, owner, num, cc):
    d = digits(num, cc)
    if not d or len(d) < 8: return None
    return "https://wa.me/" + d + "?text=" + urllib.parse.quote(opener(company, industry, owner))

def fetch_leads():
    out, after = [], None
    while True:
        cur = f',after:"{after}"' if after else ""
        q = ("query{leads(first:60"+cur+"){pageInfo{hasNextPage endCursor} edges{node{"
             "id name industry offerAngle owner phone{primaryPhoneNumber primaryPhoneCallingCode}}}}}")
        d = gql(q)["leads"]
        out += [e["node"] for e in d["edges"]]
        if not d["pageInfo"]["hasNextPage"]: break
        after = d["pageInfo"]["endCursor"]
    return out

def main():
    leads = fetch_leads()
    print(f"{len(leads)} leads fetched")
    angle_fills = link_fills = 0; samples = []
    for L in leads:
        update = {}
        if not (L.get("offerAngle") or "").strip():
            update["offerAngle"] = angle_for(L.get("industry")); angle_fills += 1
        ph = L.get("phone") or {}
        link = wa_link(L["name"], L.get("industry"), L.get("owner"),
                       ph.get("primaryPhoneNumber"), ph.get("primaryPhoneCallingCode"))
        if link:
            update["whatsappLink"] = {"primaryLinkUrl": link, "primaryLinkLabel": "Message on WhatsApp"}
            link_fills += 1
        if update and not DRY:
            gql("mutation($id:UUID!,$d:LeadUpdateInput!){updateLead(id:$id,data:$d){id}}",
                {"id": L["id"], "d": update})
        if len(samples) < 4 and link:
            samples.append((L["name"], L.get("industry"), update.get("offerAngle","(kept)")))

    print(f"\nOffer angles filled: {angle_fills} (existing preserved)")
    print(f"WhatsApp links generated: {link_fills}")
    print("\nSample opener:")
    if samples:
        n, ind, _ = samples[0]
        print(f'  [{n} / {ind}]')
        print("  " + opener(n, ind, "HISHAM"))
        print("\nAngles set (samples):")
        for n, ind, a in samples:
            print(f"  - {n[:30]:<30} {ind:<16} {a[:50]}")
    if DRY: print("\n[dry-run] no writes made.")

if __name__ == "__main__":
    main()
