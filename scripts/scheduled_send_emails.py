#!/usr/bin/env python3
"""
RAL CRM — hourly wrapper around send_emails.py for Windows Task Scheduler.

Everything here is local (Docker Desktop + Twenty CRM on this machine), so a
scheduled run at an hour when the laptop is asleep or Docker isn't up would
otherwise show up as a hard failure. This checks Twenty's own /healthz first
and skips cleanly (logged, exit 0) instead of erroring when it's unreachable.

Every run (skipped or real) appends one line to logs/scheduled_send.log so
the whole day's activity can be reviewed without having watched it live.

Usage (what Task Scheduler actually calls):
  python scripts/scheduled_send_emails.py --limit 15
"""
import argparse, datetime, os, subprocess, sys, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LOG_DIR = os.path.join(ROOT, "logs")
LOG_FILE = os.path.join(LOG_DIR, "scheduled_send.log")

def load_env():
    env = dict(os.environ); p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); env.setdefault(k, v)
    return env

def crm_reachable(url, timeout=5):
    try:
        urllib.request.urlopen(f"{url.rstrip('/')}/healthz", timeout=timeout)
        return True
    except (urllib.error.URLError, OSError):
        return False

def log(line):
    os.makedirs(LOG_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{stamp}] {line}\n")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--min-score", type=int, default=0)
    ap.add_argument("--industry", default="")
    a = ap.parse_args()

    env = load_env()
    twenty_url = env.get("TWENTY_URL", "http://localhost:3000")

    if not crm_reachable(twenty_url):
        log(f"SKIPPED — CRM not reachable at {twenty_url} (Docker/laptop likely asleep)")
        return

    cmd = [sys.executable, os.path.join(HERE, "send_emails.py"),
           "--limit", str(a.limit), "--send"]
    if a.min_score: cmd += ["--min-score", str(a.min_score)]
    if a.industry: cmd += ["--industry", a.industry]

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    log(f"RAN (limit {a.limit}) exit={result.returncode}\n{result.stdout}{result.stderr}")

if __name__ == "__main__":
    main()
