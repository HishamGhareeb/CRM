#!/usr/bin/env python3
"""
RAL CRM — WhatsApp queue sender (fast, human-in-the-loop).

Runs a tiny local web app. It queues your uncontacted leads (highest lead
score first), and for each one:
  1. shows the company + the pre-written message,
  2. "Open WhatsApp" opens the chat with the message already typed,
  3. you review & press send in WhatsApp,
  4. "Sent -> Next" marks the lead WhatsApp Sent + Contacted + today, and
     serves the next lead.

No auto-sending (so your number stays safe) — just a much faster workflow than
clicking links one by one in the CRM. The API token stays server-side; the
browser never sees it. Localhost only.

Usage:
  python scripts/whatsapp_sender.py            # then open http://localhost:8765
  python scripts/whatsapp_sender.py --min-score 70 --industry MEDICAL_HEALTH
"""
import argparse, json, os, sys, time, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_outreach as L

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
TW=ENV.get("TWENTY_URL","http://localhost:3000").rstrip("/")
TOKEN=ENV.get("TWENTY_API_KEY") or sys.exit("TWENTY_API_KEY not set")

def tw(q,v=None):
    r=urllib.request.Request(f"{TW}/graphql",data=json.dumps({"query":q,"variables":v or {}}).encode(),
        headers={"Authorization":f"Bearer {TOKEN}","Content-Type":"application/json"})
    try: d=json.loads(urllib.request.urlopen(r).read())
    except urllib.error.HTTPError as e: d=json.loads(e.read())
    if "errors" in d: raise RuntimeError(json.dumps(d["errors"])[:300])
    return d["data"]

MIN_SCORE=0; INDUSTRY=""; INCLUDE_LANDLINE=False; SKIPPED_LANDLINE=0

def load_queue():
    out,after=[],None
    while True:
        cur=f',after:"{after}"' if after else ""
        q=("query{leads(first:60"+cur+",orderBy:[{leadScore:DescNullsLast}]){pageInfo{hasNextPage endCursor}"
           "edges{node{id name industry owner hasWebsite leadScore outreachStatus bucket "
           "phone{primaryPhoneNumber primaryPhoneCallingCode}}}}}")
        d=tw(q)["leads"]; out+=[e["node"] for e in d["edges"]]
        if not d["pageInfo"]["hasNextPage"]: break
        after=d["pageInfo"]["endCursor"]
    global SKIPPED_LANDLINE; SKIPPED_LANDLINE=0
    res=[]
    for n in out:
        if n.get("bucket")!="ACTIVE": continue
        if (n.get("outreachStatus") or "NOT_CONTACTED")!="NOT_CONTACTED": continue
        if MIN_SCORE and (n.get("leadScore") or 0)<MIN_SCORE: continue
        if INDUSTRY and n.get("industry")!=INDUSTRY: continue
        ph=n.get("phone") or {}
        num,cc=ph.get("primaryPhoneNumber"),ph.get("primaryPhoneCallingCode")
        cap=L.wa_capable(num,cc)
        if cap is False and not INCLUDE_LANDLINE:   # Bahrain landline -> not on WhatsApp
            SKIPPED_LANDLINE+=1; continue
        obs_en,obs_ar=L.observations(n.get("hasWebsite"))
        url_en=L.whatsapp_link(n["name"],n.get("industry"),n.get("owner"),num,cc,obs_en)
        url_ar=L.whatsapp_link_ar(n["name"],n.get("industry"),n.get("owner"),num,cc,obs_ar)
        if not url_en: continue
        res.append({"id":n["id"],"name":n["name"],"industry":n.get("industry"),
                    "score":n.get("leadScore"),"mobile":(cap is not False),
                    "url_en":url_en,"url_ar":url_ar})
    return res

def mark_sent(lead_id):
    tw("mutation($id:UUID!,$d:LeadUpdateInput!){updateLead(id:$id,data:$d){id}}",
       {"id":lead_id,"d":{"outreachStatus":"WHATSAPP_SENT","stage":"OPT_2_CONTACTED",
                          "lastContact":time.strftime("%Y-%m-%d")}})

PAGE="""<!doctype html><html><head><meta charset=utf-8><title>RAL WhatsApp Sender</title>
<style>body{font-family:Inter,system-ui,sans-serif;background:#2E2347;color:#F1EEF7;margin:0;padding:40px;text-align:center}
.card{max-width:640px;margin:0 auto;background:#392c54;border-radius:16px;padding:32px;box-shadow:0 8px 30px #0005}
h1{color:#B5852A;margin:0 0 4px}.sub{opacity:.7;margin-bottom:24px}
.name{font-size:24px;font-weight:700;margin:8px 0}.meta{opacity:.8;margin-bottom:16px}
.col{display:flex;gap:14px;text-align:left;margin-top:8px}.half{flex:1}
.lang{font-size:12px;opacity:.7;margin:6px 2px}
.msg{background:#241a3a;border-radius:10px;padding:14px;white-space:pre-wrap;font-size:13px;line-height:1.5;max-height:300px;overflow:auto}
.msg.ar{direction:rtl;text-align:right}
button{font-size:15px;font-weight:600;border:0;border-radius:10px;padding:12px 18px;margin:10px 6px 0;cursor:pointer}
.en{background:#25D366;color:#06351b}.ar{background:#2C7A77;color:#fff}.skip{background:#5a4b78;color:#F1EEF7}
.done{font-size:20px;margin-top:40px}.count{opacity:.7;margin-top:18px;font-size:13px}</style></head>
<body><div class=card><h1>RAL WhatsApp Sender</h1><div class=sub>Hottest leads first · pick a language · you press send · no auto-blasting</div>
<div id=body>Loading…</div></div>
<script>
let cur=null,sentCount=0;
async function next(){let r=await fetch('/api/next');let d=await r.json();render(d)}
async function send(lang){if(!cur)return;window.open(lang=='ar'?cur.ar.url:cur.en.url,'_blank','noopener');
 await fetch('/api/sent?id='+cur.lead.id);sentCount++;next()}
async function skip(){await fetch('/api/skip?id='+(cur&&cur.lead?cur.lead.id:''));next()}
function render(d){cur=d;let b=document.getElementById('body');
 if(!d.lead){b.innerHTML=`<div class=done>🎉 Queue empty — all caught up.</div><div class=count>Sent this session: ${sentCount}</div>`;return}
 b.innerHTML=`<div class=name>${esc(d.lead.name)}</div>
 <div class=meta>${esc(d.lead.industry||'')} · score ${d.lead.score??'-'}</div>
 <div class=col>
   <div class=half><div class=lang>English</div><div class=msg>${esc(d.en.msg)}</div>
     <button class="en" onclick="send('en')">Send English ▶</button></div>
   <div class=half><div class=lang>العربية</div><div class="msg ar">${esc(d.ar.msg)}</div>
     <button class="ar" onclick="send('ar')">إرسال بالعربية ▶</button></div>
 </div>
 <button class="skip" onclick=skip()>Skip</button>
 <div class=count>Sent this session: ${sentCount} · ${d.remaining} left in queue</div>`}
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
next();
</script></body></html>"""

class H(BaseHTTPRequestHandler):
    queue=[]
    def log_message(self,*a): pass
    def _send(self,code,body,ctype="application/json"):
        self.send_response(code); self.send_header("Content-Type",ctype); self.end_headers()
        self.wfile.write(body.encode() if isinstance(body,str) else body)
    def do_GET(self):
        u=urlparse(self.path); qs=parse_qs(u.query)
        if u.path=="/":
            return self._send(200,PAGE,"text/html; charset=utf-8")
        if u.path=="/api/next":
            from urllib.parse import unquote
            lead=H.queue[0] if H.queue else None
            en=ar=""
            if lead:
                en=unquote(lead["url_en"].split("text=",1)[1]) if "text=" in lead["url_en"] else ""
                ar=unquote(lead["url_ar"].split("text=",1)[1]) if lead.get("url_ar") and "text=" in lead["url_ar"] else ""
            return self._send(200,json.dumps({"lead":lead,
                "en":{"url":lead["url_en"] if lead else "","msg":en},
                "ar":{"url":lead.get("url_ar") if lead else "","msg":ar},
                "remaining":len(H.queue)}))
        if u.path in("/api/sent","/api/skip"):
            lid=(qs.get("id") or [""])[0]
            if u.path=="/api/sent" and lid:
                try: mark_sent(lid)
                except Exception as e: print("mark failed:",e)
            if H.queue and H.queue[0]["id"]==lid: H.queue.pop(0)
            return self._send(200,json.dumps({"ok":True,"remaining":len(H.queue)}))
        self._send(404,"{}")

def main():
    global MIN_SCORE,INDUSTRY
    ap=argparse.ArgumentParser()
    ap.add_argument("--min-score",type=int,default=0)
    ap.add_argument("--industry",default="")
    ap.add_argument("--include-landline",action="store_true",
                    help="also queue Bahrain landline numbers (likely NOT on WhatsApp)")
    ap.add_argument("--port",type=int,default=8765)
    a=ap.parse_args(); MIN_SCORE=a.min_score; INDUSTRY=a.industry
    global INCLUDE_LANDLINE; INCLUDE_LANDLINE=a.include_landline
    H.queue=load_queue()
    print(f"Loaded {len(H.queue)} uncontacted MOBILE leads with WhatsApp links"
          f"{f' (score>={MIN_SCORE})' if MIN_SCORE else ''}.")
    print(f"Skipped {SKIPPED_LANDLINE} Bahrain landline numbers (not on WhatsApp)"
          f"{' — pass --include-landline to keep them' if SKIPPED_LANDLINE else ''}.")
    print(f"\n  ➜  Open  http://localhost:{a.port}  in your browser.\n     Ctrl+C to stop.")
    HTTPServer(("127.0.0.1",a.port),H).serve_forever()

if __name__=="__main__":
    main()
