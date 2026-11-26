import json
import os
import time
import urllib.error
import urllib.request

BASE = "https://api.geckoterminal.com/api/v2"
MAX_NEW = 3
MAX_LOOKUPS = 8
MAX_PAGES = 8
FREE_DAYS = 180
PAUSE = 4

def get(url):
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(20 if e.code == 429 else 5)
        except Exception:
            time.sleep(5)
    return None

def read_list(path):
    items = []
    try:
        for line in open(path):
            parts = line.split()
            if len(parts) == 2:
                items.append((parts[0], parts[1]))
    except FileNotFoundError:
        pass
    return items

def path_for(addr):
    return "history/" + addr + ".csv"

def find_pool(addr):
    data = get(BASE + "/networks/solana/tokens/" + addr + "/pools?page=1")
    if not data:
        return None
    best = None
    best_liq = -1.0
    for p in data.get("data", []):
        a = p.get("attributes", {})
        try:
            liq = float(a.get("reserve_in_usd") or 0)
        except ValueError:
            liq = 0.0
        if a.get("address") and liq > best_liq:
            best_liq = liq
            best = a["address"]
    return best

def candles(pool, addr, before=None):
    url = BASE + "/networks/solana/pools/" + pool + "/ohlcv/hour?aggregate=1&limit=1000&currency=usd&include_empty_intervals=true&token=" + addr
    if before:
        url += "&before_timestamp=" + str(before)
    data = get(url)
    if not data:
        return None
    lst = ((data.get("data") or {}).get("attributes") or {}).get("ohlcv_list")
    return lst if isinstance(lst, list) else None

def backfill(addr, pool):
    rows = {}
    oldest_allowed = time.time() - FREE_DAYS * 86400
    before = None
    for page in range(MAX_PAGES):
        lst = candles(pool, addr, before)
        time.sleep(PAUSE)
        if not lst:
            break
        for c in lst:
            rows[int(c[0])] = [str(int(c[0]))] + ["%.12g" % float(x) for x in c[1:6]]
        oldest = min(int(c[0]) for c in lst)
        if len(lst) < 1000 or oldest <= oldest_allowed:
            break
        before = oldest - 1
    if rows:
        with open(path_for(addr), "w") as f:
            f.write("ts,open,high,low,close,volume\n")
            for ts in sorted(rows):
                f.write(",".join(rows[ts]) + "\n")
    return len(rows)

os.makedirs("history", exist_ok=True)
try:
    banned = json.load(open("banned.json"))
except Exception:
    banned = {}

need = []
seen = set()
for path in ("paper_list.txt", "watchlist.txt", "auto_watchlist.txt"):
    for addr, name in read_list(path):
        if addr in seen or addr in banned:
            continue
        seen.add(addr)
        if not os.path.exists(path_for(addr)):
            need.append((addr, name))

done = 0
looked = 0
for addr, name in need:
    if done >= MAX_NEW or looked >= MAX_LOOKUPS:
        break
    pool = find_pool(addr)
    looked += 1
    time.sleep(PAUSE)
    if not pool:
        print(name, "no pool found")
        continue
    n = backfill(addr, pool)
    done += 1
    print(name, "saved", n, "hourly candles" if n else "- no candles returned")

print(len(need), "tokens still need history before this run;", done, "backfilled now")
