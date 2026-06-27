#!/usr/bin/env python3
"""
RAL CRM — shared outreach engine.

Given a business's signals (industry, website presence, rating, review count),
produce: pain points, a lead score, a personalised first-touch WhatsApp opener
(with a genuine specific observation, per the RAL Discovery Script), and a
ready-to-send cold email draft (per the RAL Proposal tone). Imported by the
scraper orchestrator and the re-enrich command.
"""
import re, urllib.parse

# vertical -> (noun, manual pain phrase, internal offer angle / RAL system)
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
 "F_B_RESTAURANT": ("restaurants", "orders and reservations over DMs",
    "Restaurant system: direct online ordering, reservations, customer follow-up"),
 "CAFE": ("cafes", "orders and reservations over DMs",
    "Cafe system: online ordering, loyalty, customer follow-up"),
 "EDUCATIONAL": ("schools & training centres", "enrolment, fees and parent comms",
    "School system: online enrolment, fee tracking, attendance, parent portal"),
 "REAL_ESTATE": ("real estate offices", "listings and enquiry follow-up",
    "Real estate system: property listings site, lead capture, WhatsApp follow-up"),
}
DEFAULT = ("businesses", "enquiries, bookings and follow-up",
           "Website + workflow automation to capture and convert more leads")

# verticals RAL prioritises (Sales Playbook §4), highest first
PRIORITY = {"SPORTS_ACADEMY":25,"FITNESS_GYM":22,"MEDICAL_HEALTH":20,"EYE_CLINIC":20,
            "BEAUTY_WELLNESS":18,"EDUCATIONAL":16,"F_B_RESTAURANT":12,"CAFE":10,"REAL_ESTATE":10}

OWNER_NAME = {"HISHAM": "Hisham", "SUHAIB": "Suhaib"}

def fnum(x):
    try: return float(x)
    except (TypeError, ValueError): return None

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_BAD_DOMAINS = ("yoursite.com","domain.com","example.com","email.com","sentry.io",
                "wixpress.com","cloudflare.com","2x.png","2x.jpg","schema.org")
_BAD_EXT = (".png",".jpg",".jpeg",".gif",".svg",".webp",".css",".js")
def valid_email(e):
    """Reject placeholders, image filenames, CDN/tracking strings the scraper mis-grabs."""
    e = (e or "").strip().lower()
    if not _EMAIL_RE.match(e): return False
    if any(b in e for b in _BAD_DOMAINS): return False
    if e.endswith(_BAD_EXT): return False
    if e.startswith(("https@","http@","www@")): return False
    dom = e.split("@",1)[1]
    if len(dom.split(".")[0]) < 2: return False
    return True

def analyze(industry, website, rating, review_count):
    """Return (pains:list[str], has_website:'Yes'|'No', score:int, headline_observation)."""
    has_site = bool((website or "").strip())
    rat = fnum(rating); rc = fnum(review_count)
    pains, obs = [], None

    if not has_site:
        pains.append("No website — invisible to customers searching online; can't take bookings/orders digitally")
        obs = "I noticed you don't have a website yet"
    else:
        pains.append("Has a website but likely no booking/automation layer on top")
        obs = "I had a look at your website"

    if rat is not None and rat < 4.2 and rc and rc >= 5:
        pains.append(f"Reputation gap (rating {rat:g}) — review-request automation would lift it")
    if rc is not None and rc < 20:
        pains.append(f"Low online visibility ({int(rc)} reviews) — automated review asks would help")
    elif rc is not None and rc >= 100 and (rat or 0) >= 4.3:
        pains.append(f"Strong demand ({int(rc)} reviews @ {rat:g}) — ripe to scale with automation")

    # score 0-100
    score = 40 + PRIORITY.get(industry or "", 6)
    if not has_site: score += 25          # no website = best fit for RAL's entry pitch
    if rc and rc >= 50: score += 8        # established, real business
    if rat and rat >= 4.3: score += 5
    if rc and rc < 5: score -= 10         # too small / unverified
    score = max(0, min(100, score))
    return pains, ("Yes" if has_site else "No"), score, obs

def wa_capable(number, calling_code):
    """Heuristic: is this number likely on WhatsApp (i.e. a mobile)?
    Bahrain (+973): mobiles start 3 or 6; landlines start 1/7, special 8.
    Other countries: unknown -> assume capable."""
    num = re.sub(r"\D", "", number or "")
    cc = re.sub(r"\D", "", calling_code or "")
    if cc in ("", "973") :
        # strip a leading 973 if it slipped into the number
        if num.startswith("973") and len(num) > 8: num = num[3:]
        if not num: return None
        return num[0] in ("3", "6")
    return True  # non-Bahrain: can't reliably tell, allow

def opener(company, industry, owner, observation=None):
    noun, pain, _ = V.get(industry or "", DEFAULT)
    who = OWNER_NAME.get(owner, "the team")
    obs = (observation + " — ") if observation else ""
    return (f"Hi {company} \U0001F44B I'm {who} from RAL Technologies. {obs}"
            f"we build custom websites & automation systems for {noun} in Bahrain "
            f"(our team has delivered software for the likes of CrediMax and Ahli United Bank). "
            f"Many {noun} still handle {pain} by hand, so we start by fixing the single most "
            f"painful piece fast and low-risk, then build from there. "
            f"Could I grab 15 minutes to show you one thing we could automate for you?")

def whatsapp_link(company, industry, owner, num, cc, observation=None):
    d = re.sub(r"\D", "", (cc or "") + (num or ""))
    if len(d) < 8: return None
    return "https://wa.me/" + d + "?text=" + urllib.parse.quote(opener(company, industry, owner, observation))

def email_draft(company, industry, owner, observation=None):
    """Return (subject, body) — short cold email in RAL Proposal/Playbook tone."""
    noun, pain, _ = V.get(industry or "", DEFAULT)
    who = OWNER_NAME.get(owner, "Hisham")
    subject = f"A quick idea for {company}"
    obs = (observation + ". ") if observation else ""
    body = (
        f"Hi {company} team,\n\n"
        f"I'm {who} from RAL Technologies, a Bahrain software studio. {obs}"
        f"We build custom websites and automation systems for {noun} — our team has delivered "
        f"software for organisations including CrediMax and Ahli United Bank.\n\n"
        f"Most {noun} we speak to still handle {pain} manually, which quietly costs time and "
        f"lost customers. We don't start with a big project — we fix the single most painful "
        f"piece first (a small, fast entry package), prove it works, then build from there.\n\n"
        f"Would you be open to a 15-minute call this week so I can show you one specific thing "
        f"we could automate for {company}? If it's not a fit, I'll tell you straight.\n\n"
        f"Best regards,\n{who}\nRAL Technologies · raltech.dev · +973 3821 8181"
    )
    return subject, body
