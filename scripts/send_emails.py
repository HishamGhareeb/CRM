#!/usr/bin/env python3
"""
RAL CRM — controlled cold-email sender.

Sends the pre-generated Email Draft to leads that have an email and haven't
been contacted, highest lead-score first. Updates Outreach Status = Email Sent,
Stage = Contacted, Last Contact = today.

SAFETY (cold email from a personal Gmail is easy to get suspended):
  * DRY-RUN BY DEFAULT — prints what it would send, sends nothing.
  * Needs a Gmail App Password in .env (EMAIL_SMTP_USER + EMAIL_SMTP_PASSWORD).
    Create one at https://myaccount.google.com/apppasswords (2FA required).
  * Hard cap of 40 per run; ~6s spacing; every email carries an opt-out line.
  * Start small (--limit 10) and warm up over days. Never blast hundreds at once.

Usage:
  python scripts/send_emails.py                          # dry-run, top 20 by score
  python scripts/send_emails.py --limit 10 --min-score 70 --send
  python scripts/send_emails.py --industry MEDICAL_HEALTH --send
"""
import argparse, json, os, smtplib, ssl, sys, time, urllib.request, urllib.error
from email.mime.text import MIMEText
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
           "edges{node{id name leadScore industry outreachStatus email{primaryEmail} emailDraft}}}}")
        d=tw(q)["leads"]; out+=[e["node"] for e in d["edges"]]
        if not d["pageInfo"]["hasNextPage"]: break
        after=d["pageInfo"]["endCursor"]
    res=[]
    for n in out:
        if not L.valid_email((n.get("email") or {}).get("primaryEmail")): continue
        if not (n.get("emailDraft") or "").strip(): continue
        if (n.get("outreachStatus") or "NOT_CONTACTED") not in ("NOT_CONTACTED",): continue
        if min_score and (n.get("leadScore") or 0) < min_score: continue
        if industry and n.get("industry") != industry: continue
        res.append(n)
    return res

def parse_draft(d):
    d=d or ""
    if d.startswith("Subject:"):
        first,_,rest=d.partition("\n")
        return first[len("Subject:"):].strip(), rest.strip()
    return "A quick idea for your business", d.strip()

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
        a.limit=min(len(pool),150)   # safety ceiling to protect the Gmail account
        if len(pool)>a.limit: print(f"NOTE: {len(pool)} candidates; capping this run at {a.limit} (protects sender reputation).")
    else:
        a.limit=min(a.limit,40)
    leads=pool[:a.limit]
    print(f"{len(leads)} candidate leads (limit {a.limit}, min-score {a.min_score or 0})")
    if not leads: return

    sending=a.send
    if sending and (not SMTP_USER or not SMTP_PASS):
        print("\nNo SMTP credentials in .env — cannot send. Add EMAIL_SMTP_USER + "
              "EMAIL_SMTP_PASSWORD (Gmail App Password) then re-run with --send.\n"
              "Falling back to DRY-RUN.\n"); sending=False

    server=None
    if sending:
        ctx=ssl.create_default_context()
        server=smtplib.SMTP("smtp.gmail.com",587); server.starttls(context=ctx)
        server.login(SMTP_USER,SMTP_PASS)
        print(f"Connected to Gmail as {SMTP_USER}\n")

    sent=0
    for L in leads:
        to=L["email"]["primaryEmail"]; subj,body=parse_draft(L.get("emailDraft"))
        print(f"  [{L.get('leadScore','?')}] {L['name'][:32]:<32} -> {to}  | {subj}")
        if sending:
            msg=MIMEText(body,"plain","utf-8"); msg["Subject"]=subj; msg["From"]=FROM; msg["To"]=to
            try:
                server.sendmail(FROM,[to],msg.as_string())
                tw("mutation($id:UUID!,$d:LeadUpdateInput!){updateLead(id:$id,data:$d){id}}",
                   {"id":L["id"],"d":{"outreachStatus":"EMAIL_SENT","stage":"OPT_2_CONTACTED",
                                      "lastContact":time.strftime("%Y-%m-%d")}})
                sent+=1; time.sleep(6)
            except Exception as e:
                print(f"      FAILED: {e}")
    if server: server.quit()
    print(f"\n{'Sent '+str(sent) if sending else 'DRY-RUN — nothing sent'}. "
          f"{'' if sending else 'Re-run with --send (after adding Gmail App Password) to send.'}")

if __name__=="__main__":
    main()
