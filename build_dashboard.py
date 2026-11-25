import csv
import json
import time

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

def load_json(path, default):
    try:
        return json.load(open(path))
    except Exception:
        return default

def to_secs(stamp):
    return time.mktime(time.strptime(stamp, "%Y-%m-%d %H:%M:%S"))

def change_24h(series):
    last_t, last_p = series[-1]
    target = to_secs(last_t) - 24 * 3600
    old = None
    for stamp, p in series:
        if to_secs(stamp) <= target:
            old = p
    if old is None or old == 0:
        return None
    return round((last_p - old) / old * 100, 2)

groups = {}
names = {}
for label, path in (("manual", "watchlist.txt"), ("auto", "auto_watchlist.txt"), ("paper", "paper_list.txt")):
    for addr, name in read_list(path):
        groups.setdefault(addr, []).append(label)
        names.setdefault(addr, name)

rows = {}
try:
    with open("prices.csv") as f:
        for row in csv.reader(f):
            if len(row) != 4:
                continue
            stamp, name, addr, price = row
            try:
                rows.setdefault(addr, []).append((stamp, float(price)))
            except ValueError:
                continue
except FileNotFoundError:
    pass

signals = {}
for item in load_json("signals.json", {}).get("items", []):
    signals[item["address"]] = item
hist = load_json("scan_history.json", {})
banned = load_json("banned.json", {})
groups = {a: g for a, g in groups.items() if a not in banned}

tokens = []
for addr, gl in groups.items():
    series = rows.get(addr, [])
    sig = signals.get(addr, {})
    h = hist.get(addr, {})
    entry = {
        "name": names[addr],
        "address": addr,
        "groups": gl,
        "records": len(series),
        "verdict": sig.get("verdict"),
        "reasons": sig.get("reasons", []),
        "checked_by": sig.get("checked_by", []),
        "liquidity": sig.get("liquidity"),
        "scans": h.get("scans", 0),
        "accept_streak": h.get("accept_streak", 0),
        "ready": bool(h.get("ready", False)),
    }
    if series:
        prices = [p for _, p in series]
        entry["price"] = prices[-1]
        entry["high"] = max(prices)
        entry["low"] = min(prices)
        entry["change_total"] = round((prices[-1] - prices[0]) / prices[0] * 100, 2) if prices[0] else None
        entry["change_24h"] = change_24h(series)
        entry["last_time"] = series[-1][0]
        entry["series"] = prices[-96:]
    else:
        entry["price"] = None
        entry["series"] = []
    tokens.append(entry)

tokens.sort(key=lambda e: (0 if "paper" in e["groups"] else 1, 0 if "manual" in e["groups"] else 1, e["name"]))

with open("dashboard.json", "w") as f:
    json.dump({"updated": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), "tokens": tokens, "banned": [{"name": v.get("symbol"), "address": k, "reason": v.get("reason")} for k, v in banned.items()]}, f)
print(len(tokens), "tokens written")
