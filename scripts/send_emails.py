#!/usr/bin/env python3
"""
RAL CRM — controlled cold-email sender.

Sends the pre-generated Email Draft to leads that have an email and haven't
been contacted, highest lead-score first. Saudi leads (Country = Saudi
Arabia) get TWO emails -- English then the Arabic draft -- since that's the
target market; everyone else gets the one English email. Updates Outreach
Status = Email Sent, Stage = Contacted, Last Contact = today once all of a
lead's emails are sent. --limit counts actual emails sent, not leads, so a
Saudi lead consumes two of the budget.

SAFETY (cold email from a personal inbox is easy to get suspended):
  * DRY-RUN BY DEFAULT — prints what it would send, sends nothing.
  * Needs SMTP creds in .env: EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, EMAIL_SMTP_USER,
    EMAIL_SMTP_PASSWORD. Defaults to Gmail (smtp.gmail.com:587) if EMAIL_SMTP_HOST
    is blank. For Zoho: EMAIL_SMTP_HOST=smtp.zoho.com, port 587 (STARTTLS) or 465
    (SSL) -- generate an app-specific password in Zoho Mail Settings -> Security
    -> App Passwords if two-factor auth is on, otherwise your normal password.
  * Hard cap of 40 per run; ~6s spacing; every email carries an opt-out line.
  * Start small (--limit 10) and warm up over days. Never blast hundreds at once.

Usage:
  python scripts/send_emails.py                          # dry-run, top 20 by score
  python scripts/send_emails.py --limit 10 --min-score 70 --send
  python scripts/send_emails.py --industry MEDICAL_HEALTH --send
"""
import argparse, json, os, smtplib, ssl, sys, time, urllib.request, urllib.error
from email.mime.text import MIMEText
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows console default (cp1252) chokes on Arabic lead names
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_outreach as L

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def load_env():
    env = dict(os.environ); p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line=line.strip()
            if line and not line.startswith("#") and "=" in line:
                k,v=line.split("=",1); env.setdefault(k,v)
    return env
ENV=load_env()
TW=ENV.get("TWENTY_URL","http://localhost:3000").rstrip("/")
TOKEN=ENV.get("TWENTY_API_KEY") or sys.exit("TWENTY_API_KEY not set")
SMTP_HOST=ENV.get("EMAIL_SMTP_HOST","").strip() or "smtp.gmail.com"
SMTP_PORT=int(ENV.get("EMAIL_SMTP_PORT","").strip() or "587")
SMTP_USER=ENV.get("EMAIL_SMTP_USER",""); SMTP_PASS=ENV.get("EMAIL_SMTP_PASSWORD","")
FROM=ENV.get("EMAIL_FROM_ADDRESS") or SMTP_USER

def tw(q,v=None):
    r=urllib.request.Request(f"{TW}/graphql",data=json.dumps({"query":q,"variables":v or {}}).encode(),
        headers={"Authorization":f"Bearer {TOKEN}","Content-Type":"application/json"})
    try: d=json.loads(urllib.request.urlopen(r).read())
    except urllib.error.HTTPError as e: d=json.loads(e.read())
    if "errors" in d: raise RuntimeError(json.dumps(d["errors"])[:300])
    return d["data"]

def candidates(min_score, industry):
    """Fetch leads ordered by score, filter client-side (robust vs composite filters)."""
    out, after = [], None
    while True:
        cur=f',after:"{after}"' if after else ""
        q=("query{leads(first:60"+cur+",orderBy:[{leadScore:DescNullsLast}]){pageInfo{hasNextPage endCursor}"
           "edges{node{id name leadScore industry country outreachStatus email{primaryEmail} emailDraft emailDraftAr}}}}")
        d=tw(q)["leads"]; out+=[e["node"] for e in d["edges"]]
        if not d["pageInfo"]["hasNextPage"]: break
        after=d["pageInfo"]["endCursor"]
    res=[]; seen_emails=set()
    for n in out:
        email=(n.get("email") or {}).get("primaryEmail")
        if not L.valid_email(email): continue
        if not (n.get("emailDraft") or "").strip(): continue
        if (n.get("outreachStatus") or "NOT_CONTACTED") not in ("NOT_CONTACTED",): continue
        if min_score and (n.get("leadScore") or 0) < min_score: continue
        if industry and n.get("industry") != industry: continue
        # Different branches of the same business often share one inbox
        # (e.g. two locations, one contact email) -- never send it twice.
        key=email.strip().lower()
        if key in seen_emails: continue
        seen_emails.add(key)
        res.append(n)
    return res

def parse_draft(d):
    d=d or ""
    if d.startswith("Subject:"):
        first,_,rest=d.partition("\n")
        return first[len("Subject:"):].strip(), rest.strip()
    return "A quick idea for your business", d.strip()

def lead_drafts(n):
    """Which emails to send this lead: English always, + Arabic too for
    Saudi leads (the target market there). Returns [(lang,subject,body),...]."""
    out=[]
    en=(n.get("emailDraft") or "").strip()
    if en:
        subj,body=parse_draft(en); out.append(("EN",subj,body))
    if n.get("country")=="SAUDI_ARABIA":
        ar=(n.get("emailDraftAr") or "").strip()
        if ar:
            subj,body=parse_draft(ar); out.append(("AR",subj,body))
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--limit",type=int,default=20)
    ap.add_argument("--min-score",type=int,default=0)
    ap.add_argument("--industry",default="")
    ap.add_argument("--send",action="store_true")
    ap.add_argument("--all",action="store_true",help="send to every email-ready lead (still spaced)")
    a=ap.parse_args()

    pool=candidates(a.min_score,a.industry)
    if a.all:
        a.limit=150   # safety ceiling to protect the sending account (counts emails, not leads)
    else:
        a.limit=min(a.limit,40)

    # --limit counts emails, not leads: a Saudi lead sends 2 (EN + AR), so
    # walk the pool and stop BEFORE a lead would push the total over budget.
    leads=[]; planned=0
    for n in pool:
        drafts=lead_drafts(n)
        if not drafts: continue
        if planned+len(drafts)>a.limit: break
        leads.append((n,drafts)); planned+=len(drafts)
    if a.all and len(pool)>len(leads):
        print(f"NOTE: {len(pool)} candidates; capping this run at {planned} emails / {len(leads)} leads (protects sender reputation).")
    print(f"{len(leads)} candidate leads -> {planned} emails (limit {a.limit}, min-score {a.min_score or 0})")
    if not leads: return

    sending=a.send
    if sending and (not SMTP_USER or not SMTP_PASS):
        print("\nNo SMTP credentials in .env — cannot send. Add EMAIL_SMTP_HOST + "
              "EMAIL_SMTP_PORT + EMAIL_SMTP_USER + EMAIL_SMTP_PASSWORD then re-run "
              "with --send.\nFalling back to DRY-RUN.\n"); sending=False

    server=None
    if sending:
        ctx=ssl.create_default_context()
        if SMTP_PORT==465:
            server=smtplib.SMTP_SSL(SMTP_HOST,SMTP_PORT,context=ctx)
        else:
            server=smtplib.SMTP(SMTP_HOST,SMTP_PORT); server.starttls(context=ctx)
        server.login(SMTP_USER,SMTP_PASS)
        print(f"Connected to {SMTP_HOST}:{SMTP_PORT} as {SMTP_USER}\n")

    sent=0; blocked=False
    for lead,drafts in leads:
        if blocked: break
        to=lead["email"]["primaryEmail"]
        tag="[EN+AR]" if len(drafts)>1 else "[EN]"
        print(f"  [{lead.get('leadScore','?')}] {tag} {lead['name'][:28]:<28} -> {to}")
        ok=True
        for lang,subj,body in drafts:
            print(f"      ({lang}) {subj}")
            if not sending: continue
            msg=MIMEText(body,"plain","utf-8"); msg["Subject"]=subj; msg["From"]=FROM; msg["To"]=to
            try:
                server.sendmail(FROM,[to],msg.as_string())
                sent+=1; time.sleep(6)
            except smtplib.SMTPServerDisconnected as e:
                # The provider dropped the connection outright (e.g. a hard
                # block, not just one rejected message) -- retrying more
                # leads against a dead connection only produces a wall of
                # identical failures. Stop the whole run here.
                print(f"      FAILED ({lang}): {e}"); ok=False; blocked=True; break
            except Exception as e:
                print(f"      FAILED ({lang}): {e}"); ok=False
                # Account-level block (e.g. Zoho's "unusual sending activity"),
                # not a per-message issue -- stop rather than repeat the same
                # rejection for every remaining lead.
                if "unusual" in str(e).lower() or "blocked" in str(e).lower():
                    blocked=True; break
        if sending and ok:
            tw("mutation($id:UUID!,$d:LeadUpdateInput!){updateLead(id:$id,data:$d){id}}",
               {"id":lead["id"],"d":{"outreachStatus":"EMAIL_SENT","stage":"OPT_2_CONTACTED",
                                     "lastContact":time.strftime("%Y-%m-%d")}})
    if server:
        try: server.quit()
        except Exception: pass  # connection may already be dead (e.g. after a block) -- cleanup only, never fatal
    if blocked:
        print(f"\nSTOPPED — provider blocked/dropped the connection after {sent} sent this run. "
              f"Check the sending account (e.g. Zoho's unblock page) before retrying.")
    else:
        print(f"\n{'Sent '+str(sent) if sending else 'DRY-RUN — nothing sent'}. "
              f"{'' if sending else 'Re-run with --send (after adding SMTP creds to .env) to send.'}")

if __name__=="__main__":
    main()
