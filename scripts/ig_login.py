#!/usr/bin/env python3
"""One-off Instagram login that waits for a verification code via a file,
so the code can be relayed in. On success it caches the session for the
scraper. Run: python scripts/ig_login.py"""
import os, sys, time
HERE=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def env():
    e={}
    for l in open(os.path.join(HERE,".env"),encoding="utf-8"):
        l=l.strip()
        if l and not l.startswith("#") and "=" in l:
            k,v=l.split("=",1); e[k]=v
    return e
E=env(); U=E.get("IG_USER"); P=E.get("IG_PASS")
CODE_FILE=os.path.join(HERE,"data","ig_code.txt")
SESS=os.path.join(HERE,"data",f"ig-{U}.json")
if os.path.exists(CODE_FILE): os.remove(CODE_FILE)

def code_handler(username, choice):
    print(f"CODE_REQUIRED via {choice}", flush=True)
    for _ in range(90):                       # wait up to ~7.5 min
        if os.path.exists(CODE_FILE):
            c=open(CODE_FILE,encoding="utf-8").read().strip()
            os.remove(CODE_FILE)
            if c: print(f"got code {c}", flush=True); return c
        time.sleep(5)
    raise Exception("no code supplied in time")

from instagrapi import Client
cl=Client(); cl.delay_range=[2,5]
cl.challenge_code_handler=code_handler
SID=E.get("IG_SESSIONID","").strip()
try:
    if SID:                                   # bypass checkpoint via browser cookie
        print("logging in via sessionid…", flush=True)
        cl.login_by_sessionid(SID)
    else:
        cl.login(U,P)
    cl.dump_settings(SESS)
    me=cl.account_info()
    print(f"LOGIN_OK as @{me.username}", flush=True)
except Exception as e:
    print(f"LOGIN_FAILED {type(e).__name__}: {str(e)[:200]}", flush=True)
    sys.exit(1)
