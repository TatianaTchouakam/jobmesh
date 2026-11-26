#!/usr/bin/env python3
"""Offline tenant discovery from the Common Crawl URL index.

Reads the CDX index page by page (matchType=domain, output=json) for each
ATS domain, over the most recent crawls, and writes unique career-site tokens
to data/discovery/<platform>.txt. Resumable (checkpoints per page), polite
(pauses between pages, retries 5xx/timeouts with backoff). Standard library
only, so it runs anywhere with python3.

Run overnight:  nohup python3 scripts/discover_tenants.py > data/discovery/run.out 2>&1 &
"""
import json, os, re, sys, time, urllib.request, urllib.error

UA = "JobmeshBot/0.1 (+https://github.com/TatianaTchouakam/jobmesh)"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "discovery")
OUT = os.path.abspath(OUT)
STATE = os.path.join(OUT, "_state.json")
LOG = os.path.join(OUT, "discovery.log")
N_CRAWLS = int(os.getenv("DISC_CRAWLS", "3"))      # how many recent crawls to scan
PAGE_PAUSE = int(os.getenv("DISC_PAUSE", "8"))     # seconds between page requests
MAX_SECONDS = int(os.getenv("DISC_MAXSEC", "0"))   # >0: stop (checkpointed) after N seconds
MAX_RETRY = 6
BACKOFF = [5, 15, 30, 60, 120, 180]

# platform -> (domain, extractor)
def ex_workday(u):
    m = re.match(r'https?://([a-z0-9][a-z0-9-]*)\.(wd\d+)\.myworkdayjobs\.com/(.*)?$', u, re.I)
    if not m: return None
    tenant, wd, rest = m.group(1).lower(), m.group(2).lower(), (m.group(3) or "")
    for s in [x for x in rest.split("/") if x]:
        if re.match(r'^[a-z]{2}-[a-zA-Z]{2}$', s): continue
        if s.lower() in ("wday","cxs","job","jobs","en","details","apply","search","task","d"): continue
        return f"{tenant}:{wd}:{s}"
    return None

def ex_oracle(u):
    m = re.match(r'https?://([a-z0-9-]+)\.fa\.([a-z0-9-]+)\.oraclecloud\.com', u, re.I)
    return f"{m.group(1).lower()}.fa.{m.group(2).lower()}" if m else None

def ex_sf(u):
    m = re.search(r'([a-z0-9-]+)\.successfactors\.(com|eu)', u, re.I)
    h = m.group(1).lower() if m else None
    return h if h and h not in ("www","performancemanager","performancemanager4","jobs") else (f"{h}.{m.group(2)}" if m else None)

def ex_icims(u):
    m = re.match(r'https?://([a-z0-9-]+)\.icims\.com', u, re.I)
    if not m: return None
    h = m.group(1).lower()
    return h if h not in ("www","careers","configure","login") else None

def ex_sr(u):
    m = re.match(r'https?://(?:careers|jobs)\.smartrecruiters\.com/([A-Za-z0-9_.-]+)', u)
    return m.group(1) if m else None

def ex_gh(u):
    m = re.match(r'https?://(?:job-)?boards(?:\.eu)?\.greenhouse\.io/([a-z0-9_-]+)', u, re.I)
    if not m: return None
    t = m.group(1).lower()
    return t if t not in ("embed","v1") else None

def ex_lever(u):
    m = re.match(r'https?://jobs\.(?:eu\.)?lever\.co/([a-z0-9_.-]+)', u, re.I)
    return m.group(1).lower() if m else None

def ex_ashby(u):
    m = re.match(r'https?://jobs\.ashbyhq\.com/([a-z0-9_.-]+)', u, re.I)
    if not m: return None
    t = m.group(1).lower()
    return t if t not in ("api","assets") else None

def ex_paylocity(u):
    m = re.search(r'recruiting\.paylocity\.com/recruiting/jobs/(?:All/)?([0-9A-Fa-f-]{6,})', u)
    return m.group(1) if m else None

def ex_adp(u):
    m = re.search(r'[?&]cid=([0-9a-f-]+).*?[?&]ccId=([0-9]+)', u, re.I)
    if m: return f"{m.group(1)}:{m.group(2)}"
    m = re.match(r'https?://myjobs\.adp\.com/([a-z0-9_-]+)', u, re.I)
    return m.group(1).lower() if m else None

def ex_dayforce(u):
    m = re.match(r'https?://([a-z0-9-]+)\.dayforcehcm\.com', u, re.I)
    if not m: return None
    h = m.group(1).lower()
    return h if h not in ("www","us241","east","usconfigr57") else h

PLATFORMS = {
    "workday":        ("myworkdayjobs.com", ex_workday),
    "oracle":         ("oraclecloud.com",   ex_oracle),
    "successfactors": ("successfactors.com", ex_sf),
    "successfactors_eu": ("successfactors.eu", ex_sf),
    "icims":          ("icims.com",         ex_icims),
    "smartrecruiters":("smartrecruiters.com", ex_sr),
    "greenhouse":     ("greenhouse.io",     ex_gh),
    "lever":          ("lever.co",          ex_lever),
    "ashby":          ("ashbyhq.com",       ex_ashby),
    "paylocity":      ("paylocity.com",     ex_paylocity),
    "adp":            ("adp.com",           ex_adp),
    "dayforce":       ("dayforcehcm.com",   ex_dayforce),
}

def log(msg):
    line = time.strftime("%Y-%m-%d %H:%M:%S") + "  " + msg
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f: f.write(line + "\n")

def load_json(p, default):
    try:
        with open(p, encoding="utf-8") as f: return json.load(f)
    except Exception: return default

def save_json(p, obj):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(obj, f)
    os.replace(tmp, p)

def http(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for i in range(MAX_RETRY):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (503, 504, 500, 502, 429) and i < MAX_RETRY - 1:
                time.sleep(BACKOFF[i]); continue
            return e.code, ""
        except Exception:
            if i < MAX_RETRY - 1: time.sleep(BACKOFF[i]); continue
            return None, ""
    return None, ""

def main():
    os.makedirs(OUT, exist_ok=True)
    st, body = http("https://index.commoncrawl.org/collinfo.json")
    coll = json.loads(body) if body else []
    crawls = [c["cdx-api"] for c in coll[:N_CRAWLS]]
    log(f"start: {len(crawls)} crawls, {len(PLATFORMS)} platforms")
    state = load_json(STATE, {})
    t0 = time.time()
    for plat, (domain, extract) in PLATFORMS.items():
        fpath = os.path.join(OUT, plat + ".txt")
        seen = set()
        if os.path.exists(fpath):
            seen = set(l.strip() for l in open(fpath, encoding="utf-8") if l.strip())
        fh = open(fpath, "a", encoding="utf-8")
        for cdx in crawls:
            cid = cdx.rsplit("/", 1)[-1]
            key = f"{plat}|{cid}"
            start_page = state.get(key, {}).get("page", 0)
            if state.get(key, {}).get("done"):
                log(f"{plat} {cid}: already done ({len(seen)} tokens)"); continue
            page = start_page
            empties = 0
            while True:
                url = f"{cdx}?url={domain}&matchType=domain&fl=url&output=json&page={page}"
                code, data = http(url)
                if code is None:
                    log(f"{plat} {cid} p{page}: giving up (network); will resume"); break
                if code == 404 or (code == 200 and not data.strip()):
                    state.setdefault(key, {})["done"] = True; save_json(STATE, state)
                    log(f"{plat} {cid}: finished at page {page} ({len(seen)} tokens)"); break
                if code != 200:
                    log(f"{plat} {cid} p{page}: HTTP {code}; stop domain, resume later"); break
                new = 0
                for line in data.splitlines():
                    if not line.strip(): continue
                    try: rec = json.loads(line)
                    except Exception: continue
                    tok = extract(rec.get("url", ""))
                    if tok and tok not in seen:
                        seen.add(tok); fh.write(tok + "\n"); new += 1
                fh.flush()
                state[key] = {"page": page + 1, "done": False}; save_json(STATE, state)
                if new == 0:
                    empties += 1
                    if empties >= 5:
                        state[key]["done"] = True; save_json(STATE, state)
                        log(f"{plat} {cid}: 5 empty pages, assume done p{page} ({len(seen)})"); break
                else:
                    empties = 0
                if page % 20 == 0:
                    log(f"{plat} {cid}: page {page}, {len(seen)} unique tokens")
                page += 1
                if MAX_SECONDS and time.time() - t0 > MAX_SECONDS:
                    log(f"time budget {MAX_SECONDS}s reached at {plat} {cid} p{page}; checkpointed"); return
                time.sleep(PAGE_PAUSE)
        fh.close()
        log(f"{plat}: TOTAL {len(seen)} unique tokens -> {plat}.txt")
    log("ALL DONE")

if __name__ == "__main__":
    main()
