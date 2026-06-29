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

# strong keyword -> vertical, checked in order (first match wins).
# Used to classify a business by its Google category and/or its name, so a
# beauty centre found under a "sports academy" search isn't mislabelled.
_CLASSIFY = [
    (("dental","dentist"), "MEDICAL_HEALTH"),
    (("optic","ophthalm","eye clinic","eye center","eye centre"), "EYE_CLINIC"),
    (("clinic","medical","hospital","polyclinic","physio","dermat","skin care",
      "pharmac","doctor","health center","health centre","rehab","therapy"), "MEDICAL_HEALTH"),
    (("salon","spa","beauty","barber","hair","makeup","nails","wellness","massage"), "BEAUTY_WELLNESS"),
    (("academy","football","swimming","tennis","padel","karate","martial","taekwondo",
      "boxing","gymnastics","sports club"), "SPORTS_ACADEMY"),
    (("gym","fitness","crossfit","workout"), "FITNESS_GYM"),
    (("school","nursery","kindergarten","kg ","institute","tuition","training center",
      "training centre","education","montessori"), "EDUCATIONAL"),
    (("cafe","coffee","cafeteria"), "CAFE"),
    (("restaurant","kitchen","grill","shisha","bbq","dining","catering","bakery","sweets","food"), "F_B_RESTAURANT"),
    (("real estate","properties","property","realtor","realty"), "REAL_ESTATE"),
]
def classify(category=None, name=None, fallback=None):
    """Pick the vertical from the real Google category first, then the name."""
    for text in (category, name):
        t = (text or "").lower()
        if not t: continue
        for keys, enum in _CLASSIFY:
            if any(k in t for k in keys):
                return enum
    return fallback

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
        obs = "I noticed you don't have a website yet — so customers searching for you online can't easily find or book you"
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

# ---- Arabic (Gulf business tone) ----------------------------------
OWNER_NAME_AR = {"HISHAM": "هشام", "SUHAIB": "صهيب"}
# vertical -> (noun_ar, pain_ar)
V_AR = {
 "SPORTS_ACADEMY": ("الأكاديميات الرياضية", "التسجيل والحضور وتحصيل الرسوم"),
 "FITNESS_GYM": ("الصالات الرياضية ومراكز اللياقة", "الاشتراكات وحجز الحصص وتجديد العضويات"),
 "MEDICAL_HEALTH": ("العيادات والمراكز الطبية", "الحجوزات والتذكيرات ومتابعة المرضى"),
 "EYE_CLINIC": ("عيادات العيون", "الحجوزات والتذكيرات ومتابعة المرضى"),
 "BEAUTY_WELLNESS": ("صالونات التجميل والسبا", "الحجوزات وإعادة الحجز عبر الرسائل"),
 "F_B_RESTAURANT": ("المطاعم", "الطلبات والحجوزات عبر الرسائل"),
 "CAFE": ("المقاهي", "الطلبات ومتابعة العملاء"),
 "EDUCATIONAL": ("المدارس ومراكز التدريب", "التسجيل والرسوم والتواصل مع أولياء الأمور"),
 "REAL_ESTATE": ("مكاتب العقارات", "عرض العقارات ومتابعة الاستفسارات"),
}
V_AR_DEFAULT = ("الأعمال", "الاستفسارات والحجوزات والمتابعة")

def observations(has_website):
    """Return (english, arabic) opening observation based on website presence."""
    if has_website == "NO":
        return ("I noticed you don't have a website yet — so customers searching for you online can't easily find or book you",
                "لاحظت أنه ليس لديكم موقع إلكتروني بعد، مما يعني أن من يبحث عنكم عبر الإنترنت قد لا يجدكم أو يحجز بسهولة")
    if has_website == "YES":
        return ("I had a look at your website", "اطّلعت على موقعكم الإلكتروني")
    return (None, None)

def _lam(word):
    """Attach the Arabic preposition 'lam' correctly: ل + الأكاديميات -> للأكاديميات."""
    w = (word or "").strip()
    if w.startswith("ال"): return "ل" + w[1:]   # drop the alif -> لل…
    return "ل" + w

def _hook_ar(noun, pain, has_website):
    if has_website == "NO":
        return (f"لاحظت أنه ليس لديكم موقع إلكتروني بعد، وغالباً يعني ذلك أن {pain} "
                f"ما زالت تُدار عبر واتساب ودفتر — يسهل أن تضيع المتابعة ويصعب التوسّع.")
    if has_website == "YES":
        return f"اطّلعت على موقعكم — بداية جيدة، لكن غالباً ما زالت {pain} تُدار يدوياً خلفه."
    return f"أغلب {noun} التي نعمل معها ما زالت تدير {pain} عبر واتساب ودفتر، ما يصعّب المتابعة والتوسّع."

def opener_ar(company, industry, owner, has_website=None):
    noun, pain = V_AR.get(industry or "", V_AR_DEFAULT)
    who = OWNER_NAME_AR.get(owner, "فريق RAL")
    return (
        f"مرحباً {company}،\n\n"
        f"معكم {who} من RAL Technologies. {_hook_ar(noun, pain, has_website)}\n\n"
        f"أغلب الشركات هنا ستقدّم لكم مجرد موقع جاهز من قالب. نحن مختلفون — فريق بحريني، "
        f"بنى مهندسوه أنظمة بمستوى البنوك لمؤسسات مثل كريديماكس والبنك الأهلي المتحد. "
        f"نصمّم ونبرمج ونستضيف وندعم كل شيء داخلياً، فلن تجدوا أنفسكم مع موقع نصف مكتمل "
        f"ومبرمج مستقل اختفى.\n\n"
        f"لا نبيعكم مشروعاً كبيراً من البداية — بل نحلّ أولاً أكثر نقطة تكلّفكم، ونثبت جدواها، ثم نتوسّع.\n\n"
        f"هل تمنحونني 15 دقيقة؟ لديّ فكرة محددة لـ{company}."
    )

def whatsapp_link_ar(company, industry, owner, num, cc, has_website=None):
    d = re.sub(r"\D", "", (cc or "") + (num or ""))
    if len(d) < 8: return None
    return "https://wa.me/" + d + "?text=" + urllib.parse.quote(opener_ar(company, industry, owner, has_website))

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

def _hook_en(noun, pain, has_website):
    if has_website == "NO":
        return (f"I noticed you don't have a website yet — which usually means {pain} are still "
                f"run over WhatsApp and a notebook. Easy to lose track of, and hard to grow on.")
    if has_website == "YES":
        return (f"I had a look at your website — a solid start, but {pain} are likely still "
                f"handled by hand behind it.")
    return (f"Most {noun} we work with still run {pain} over WhatsApp and a notebook — "
            f"easy to lose track of, and hard to grow on.")

def opener(company, industry, owner, has_website=None):
    noun, pain, _ = V.get(industry or "", DEFAULT)
    who = OWNER_NAME.get(owner, "the team")
    return (
        f"Hi {company},\n\n"
        f"{who} here from RAL Technologies. {_hook_en(noun, pain, has_website)}\n\n"
        f"Most agencies here would just hand you a template site. We're a different kind of shop — "
        f"a Bahraini team whose engineers have built bank-grade systems for the likes of CrediMax "
        f"and Ahli United Bank. We design, build, host and support the whole thing in-house, so "
        f"you're never left with a half-finished site and a freelancer who's disappeared.\n\n"
        f"We don't sell you a big project up front. We fix the one thing costing you most "
        f"(for {noun}, usually {re.split(r',| and ', pain)[0].strip()}), prove it pays for itself, then grow from there.\n\n"
        f"Worth a quick 15-minute call? I already have one specific idea for {company}."
    )

def whatsapp_link(company, industry, owner, num, cc, has_website=None):
    d = re.sub(r"\D", "", (cc or "") + (num or ""))
    if len(d) < 8: return None
    return "https://wa.me/" + d + "?text=" + urllib.parse.quote(opener(company, industry, owner, has_website))

def email_draft(company, industry, owner, has_website=None):
    """Return (subject, body) — short cold email in RAL Proposal/Playbook tone."""
    noun, pain, _ = V.get(industry or "", DEFAULT)
    who = OWNER_NAME.get(owner, "Hisham")
    subject = f"A sharper system for {company}"
    body = (
        f"Hi {company} team,\n\n"
        f"{who} here from RAL Technologies. {_hook_en(noun, pain, has_website)}\n\n"
        f"Most agencies would just hand you a template site. We're a different kind of shop — a "
        f"Bahraini team whose engineers have built bank-grade systems for the likes of CrediMax "
        f"and Ahli United Bank. We design, build, host and support everything in-house, so you're "
        f"never left with a half-finished site and a freelancer who's disappeared.\n\n"
        f"We don't sell a big project up front. We fix the one thing costing you most "
        f"(for {noun}, usually {re.split(r',| and ', pain)[0].strip()}), prove it pays for itself, then grow from there.\n\n"
        f"Would you be open to a 15-minute call this week? I already have one specific idea for "
        f"{company}.\n\n"
        f"Best regards,\n{who}\n"
        f"RAL Technologies — raltech.dev — +973 3821 8181"
    )
    return subject, body
